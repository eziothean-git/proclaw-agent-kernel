# Agent Kernel - Agent Guidelines

## Project Vision

Agent Kernel is a **long-running information flow kernel** orchestrating multi-level Agent Primitives, context compilation, and persistent memory.

**Key Philosophy:**
- LLM is a replaceable plugin, not the system
- Personality continuity from stable prompts + memory
- Agent is a primitive operator, not autonomous subject
- **Control Plane / Data Plane separation** for security and flexibility
- **Capability-based permission system** (P0/P1/P3)

## Architecture: Control Plane vs Data Plane

```
┌──────────────────────────────────────────────────────────────┐
│                    CONTROL PLANE (P0/P1)                      │
│                    #[cfg(feature = "control-plane")]          │
├──────────────────────────────────────────────────────────────┤
│  OS Interface (P0)     Scheduler (P1)      Session Host       │
│  - create_process      - create_thread     - Process mgmt     │
│  - list_sessions       - spawn_thread      - Thread registry  │
│  - delete_session      - pause/resume      - Global query     │
│  - query_history       - cancel                                │
│                                                              │
│  Permission: Prime >= P0, Host >= P1, Agent >= P3            │
└───────────────────────────┬──────────────────────────────────┘
                            │ gRPC / Internal
┌───────────────────────────▼──────────────────────────────────┐
│                      DATA PLANE (P3)                          │
│                      Always compiled                          │
├──────────────────────────────────────────────────────────────┤
│  Agent Thread          ExecutionCoordinator    Skills         │
│  - SEE-ACT-UPDATE      - DirectoryLockManager  - Bash         │
│  - Working Set         - FIFO queue            - File         │
│  - Event Log           - Skill routing         - Code         │
│  - Phase-based         - Permission check      - Composer     │
│                                                              │
│  Permission: All levels (P0/P1/P3)                           │
└──────────────────────────────────────────────────────────────┘
```

**Design Rationale:**
- **Security**: Control Plane has global access; feature-gated for safety
- **Deployment**: Workers run Data Plane only, Hosts enable Control Plane
- **Permission**: Capability-level access control (Prime/Host/Agent)

## Permission System (Capability Levels)

| Level | Value | Access |
|-------|-------|--------|
| **Prime** (P0) | 2 | All Skills (OS Interface + Scheduler + Bash) |
| **Host** (P1) | 1 | Scheduler + Bash |
| **Agent** (P3) | 0 | Bash only |

**Usage:**
```rust
// Execute with permission check
skill_registry.execute_control(request, CapabilityLevel::Prime).await;

// Permission denied if caller_level < required_level
if !caller_level.can_access(CapabilityLevel::Host) {
    return Err("Permission denied: Host level required");
}
```

## Current Implementation (Rust Kernel v2)

### Data Plane (Always Available)

| Component | Status | Description |
|-----------|--------|-------------|
| `agent_thread` | ✅ | Thread lifecycle, Event Log, Working Set |
| `scheduler` | ✅ | ThreadExecutor, SEE-ACT-UPDATE loop |
| `coordinator` | ✅ | ExecutionCoordinator, DirectoryLockManager (FIFO) |
| `block_composer` | ✅ | BlockComposerEngine, Context composition |
| `skills::BashSkill` | ✅ | Local command execution (All levels) |
| `skills::ComposerSkill` | ✅ | Unified block management + execution |

### Control Plane (`--features control-plane`)

| Component | Permission | Tools |
|-----------|------------|-------|
| `OSInterfaceSkill` | P0 (Prime) | create_process, list_sessions, delete_session, query_history |
| `SchedulerSkill` | P1 (Host) | create_thread, spawn_thread, pause_thread, resume_thread, cancel_thread |
| `SessionHostSkills` | Internal | Process/Thread management (used by Skills) |
| `ThreadManager` | Internal | Thread lifecycle management |
| `ProcessManager` | Internal | Process CRUD operations |

### Skill Registry

```rust
// All skills registered in SkillRegistry
let registry = SkillRegistry::new(bash_skill)
    .register_scheduler_skill(scheduler_skill)      // P1+
    .register_os_interface_skill(os_interface_skill); // P0+

// Execute with permission check
registry.execute_control(request, caller_level).await;
```

## Build & Test

```bash
cd kernel-v2

# Development (Data Plane only)
cargo build
cargo test

# Production with Control Plane
cargo build --release --features control-plane
cargo test --features control-plane

# Check
 cargo check
 cargo clippy -- -D warnings
 cargo fmt
```

**Requires**: `protoc` (Protocol Buffers) at `~/.local/bin/protoc`

## gRPC API

### Data Plane Services (All Levels)

| Service | Method | Description | Permission |
|---------|--------|-------------|------------|
| `AgentKernel` | `ExecuteSkill` | Execute skill with directory lock | P0/P1/P3 |
| `AgentKernel` | `CreateThread` | Create Agent Thread | P0/P1/P3 |
| `AgentKernel` | `SpawnExecutor` | Start Thread execution | P0/P1/P3 |
| `AgentKernel` | `StreamEvents` | Real-time event stream | P0/P1/P3 |
| `BlockComposer` | `Compose` | Compose blocks to context | P0/P1/P3 |
| `BlockComposer` | `ExecuteBash` | Direct bash execution | P0/P1/P3 |

### Control Plane Services (P0/P1)

| Service | Method | Description | Permission |
|---------|--------|-------------|------------|
| `AgentKernel` | `GetResourceStatus` | Query directory lock status | P0/P1 |
| `AgentKernel` | `GetSystemStatus` | System-wide statistics | P0/P1 |
| *(via skills)* | `CreateProcess` | Process creation (OS Interface) | P0 |
| *(via skills)* | `CreateThread` | Thread creation (Scheduler) | P1 |
| *(via skills)* | `ListSessions` | List all sessions | P0 |

**Note**: Control plane methods are exposed via `ExecuteSkill` with permission check

## Key Features

### 1. Directory Lock Manager (FIFO)

```rust
// Automatic directory-level locking with queue
let lock = lock_manager.acquire_lock(
    directory,
    executor_id,
    session_id,
    LockLevel::Write,
    timeout_seconds,
).await?;

// Lock released when `lock` drops
```

### 2. ComposerSkill (Unified Interface)

```rust
// Block management
skill.upsert_block(id, block_type, content, priority).await;
skill.remove_block(id).await;
let blocks = skill.list_all_blocks().await;

// Composition + LLM
let response = skill.compose_and_generate(
    session_id, task_id, profile, difficulty
).await?;

// Execution with lock
let result = skill.execute_with_lock(
    directory, action, session_id, executor_id, timeout
).await?;
```

### 3. Thread Profiles

| Profile | Tokens | Use Case |
|---------|--------|----------|
| `Prime` | 2k | System identity, intent analysis |
| `Session` | 3k | Session context, active tasks |
| `Task` | 4k | Task execution, working memory |

### 4. Permission Enforcement

```rust
// In SkillRegistry::execute_control
"os_interface" => {
    if !caller_level.can_access(CapabilityLevel::Prime) {
        return Err("Permission denied: Prime level required");
    }
    // Execute...
}
```

## Testing

```bash
# Unit tests
cargo test

# With control plane features
cargo test --features control-plane

# Lock manager test
cargo test coordinator::lock_manager::tests

# Block composer test
cargo test block_composer::tests

# Integration tests
cargo test --test integration_tests
```

**Current Coverage**: 19 tests passing

## Environment Variables

```bash
# Rust Kernel
DATA_PATH=./data
OPENAI_API_KEY=sk-...
ARK_API_KEY=...
SOCKET_PATH=/run/proclaw/composer.sock

# Feature flags
# --features control-plane (enables P0/P1 skills)
```

## Running

```bash
# Data Plane only (Worker mode)
cargo run

# With Control Plane (Host mode)
cargo run --features control-plane

# Release
./target/release/proclaw-composer
```

## Code Guidelines

### Rust

```rust
// Public API: Document with docstrings
/// Query lock status for a directory
pub async fn query_lock_status(&self, directory: &Path) -> Result<Option<LockStatus>> {
    // Implementation
}

// Permission check
pub async fn execute_control(&self, request: SkillRequest, caller_level: CapabilityLevel) {
    if !caller_level.can_access(required_level) {
        return Err("Permission denied");
    }
    // Execute...
}

// Error handling: Explicit types, no unwrap in production code
let lock = self.lock_manager.acquire_lock(...).await
    .map_err(|e| Status::internal(format!("Lock failed: {}", e)))?;
```

## Resources

- Architecture: `/schema/agent_kernel_architecture_spec_restructured.md`
- Control Plane: `kernel-v2/CONTROL_PLANE_CONCEPT.md`
- API Status: `kernel-v2/API_STATUS.md`
- gRPC Changes: `kernel-v2/GRPC_CHANGES.md`
- Test Plan: `kernel-v2/E2E_TEST_PLAN.md`

## Status

**Phase 1**: ✅ Complete - Core execution layer (Data Plane)
**Phase 2**: ✅ Complete - Control Plane + Full gRPC API + Permission System
**Phase 3**: 🔄 Ready - End-to-end integration testing

**Next**: End-to-end integration test with TypeScript frontend
