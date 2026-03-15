# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

ProClaw is an AI agent system with a dual-layer architecture:
- **agent-kernel/apps/gateway**: TypeScript/NestJS control layer (ACTIVE - used by both kernel implementations)
- **agent-kernel/apps/python-kernel**: Python intelligence layer (DEPRECATED - being replaced)
- **kernel-v2/**: Rust kernel v0.1.0 (ACTIVE - replaces Python kernel)

The system architecture is: **TypeScript Gateway → Rust Kernel**

The Python kernel has been completely removed. Recent commits confirm: "完全去掉python内核，rust 0.1.0内核进入发布" (Completely removed Python kernel, Rust 0.1.0 kernel entering release).

The TypeScript gateway (agent-kernel/apps/gateway) remains the active frontend and is used to communicate with the Rust kernel.

## Build and Test Commands

### Building
```bash
cd kernel-v2

# Development build
cargo build

# Release build (optimized)
cargo build --release

# The binary name is: proclaw-composer
```

### Testing
```bash
cd kernel-v2

# Run all tests
cargo test

# Run specific test file
cargo test --test integration_test

# Run with output
cargo test -- --nocapture

# Manual test script
./test-manual.sh
```

### Running
```bash
cd kernel-v2

# Run with default config
cargo run -- --config /etc/proclaw/composer.yaml --llm-api-key <key>

# Override settings
cargo run -- \
  --socket /tmp/proclaw.sock \
  --data-dir ./data \
  --llm-api-key $OPENAI_API_KEY \
  --llm-model gpt-4 \
  --llm-base-url https://api.openai.com/v1

# Or use environment variable
export OPENAI_API_KEY=<key>
cargo run -- --config config.yaml
```

### Benchmarks
```bash
cd kernel-v2
cargo bench
```

## Architecture Overview

### Three-Layer gRPC Service Architecture

The kernel-v2 is built as three interconnected gRPC services:

1. **BlockComposer** (Unix socket: `/tmp/proclaw/composer.sock`)
   - Context composition and caching service
   - L1 (in-memory LRU) + L2 (SQLite) caching
   - Provides context blocks for Prime/Session/Task levels

2. **AgentKernel** (Unix socket: same as BlockComposer)
   - Core agent execution service
   - Manages sessions, processes, and threads
   - Coordinates skill execution
   - Handles resource locking via Coordinator

3. **PrimePersonality** (TCP: `127.0.0.1:50051`)
   - Stateless orchestration layer
   - LLM-powered decision making
   - XML-based communication protocol
   - Uses IR (Intermediate Representation) executor for tool calls

### Key Components

**Scheduler** (`src/scheduler/`):
- `ThreadExecutor`: Executes individual agent threads with step-by-step execution
- `BatchTaskExecutor`: Parallel batch execution with timeout/depth limits
- `MultiSessionOrchestrator`: Coordinates multiple sessions
- `ParallelActionExecutor`: Executes actions in parallel with dependency analysis
- `TimeBudgetMonitor`: Tracks time budgets and warns on overruns
- `SnapshotCollector`: Collects task snapshots for observability
- `XmlOutputParser`: Parses XML responses from LLM

**Session** (`src/session/`):
- Session and process lifecycle management
- SQLite-based state persistence
- Skill registry and execution

**LLM** (`src/llm/`):
- LLM client with router for multiple providers
- Supports OpenAI-compatible APIs
- Configurable model, temperature, max_tokens

**Coordinator** (`src/coordinator/`):
- Resource coordination and locking
- Ticket-based access control
- Skill registry management

**Skills** (`src/skills/`):
- `BashSkill`: Execute bash commands
- `ComposerSkill`: Access BlockComposer
- `GatewaySkill`: Communicate with gateway
- `OsInterfaceSkill`: OS-level operations
- `SchedulerSkill`: Scheduler control

### XML Communication Protocol

The system uses XML for agent communication. Key structures:

```xml
<agent-response>
  <reasoning>
    <observation>...</observation>
    <thought>...</thought>
    <plan>
      <step order="1">...</step>
    </plan>
  </reasoning>

  <explanation>...</explanation>

  <actions>
    <action type="tool_call" id="...">
      <skill name="..."/>
      <tool name="..."/>
      <parameters>...</parameters>
    </action>
  </actions>
</agent-response>
```

See `src/scheduler/xml_models.rs` and `src/scheduler/xml_parser.rs` for implementation.

### Batch Execution Architecture

Recent work adds parallel batch execution (see `.sisyphus/plans/batch-execution-plan.md`):

- **Map-Reduce pattern**: Parallel execution → Aggregated results
- **Anti-blocking mechanisms**: Timeout control, depth limits, step limits, cycle detection
- **Result aggregation**: Multiple modes (SimpleList, StructuredReport, MergeArtifacts, SmartSummary)
- **Configuration**: `BatchConfig` with max_parallel_tasks, task_timeout_seconds, max_steps_per_task, max_depth

## Configuration

Configuration is YAML-based (default: `/etc/proclaw/composer.yaml`). Key sections:

- `server`: Socket path, workers, timeouts
- `cache`: L1/L2 cache settings
- `providers`: Bash, code, memory providers
- `permissions`: Token TTL, max calls, policies
- `observability`: Metrics (port 9090), traces, audit logs
- `gateway`: Gateway URL and auth token

CLI args override config: `--socket`, `--data-dir`, `--llm-api-key`, `--llm-model`, `--llm-base-url`

## Development Patterns

### Async/Await with Tokio
All I/O operations use async/await with Tokio runtime. Use `#[tokio::test]` for async tests.

### Error Handling
- Use `anyhow::Result` for application errors
- Use `thiserror` for custom error types
- Propagate errors with `?` operator

### Protobuf Code Generation
Proto files in `proto/` are compiled by `build.rs` using `tonic-build`. Generated code goes to `target/*/build/.../out/`.

To modify services:
1. Edit `.proto` files in `proto/`
2. Run `cargo build` to regenerate
3. Update service implementations in `src/server/`

### Storage
SQLite is used for persistence:
- Thread state: `data/threads.db`
- Cache: `data/cache.db`
- Memory: `data/memory.db`
- Code index: `data/code_index.db`

### Testing Strategy
- Unit tests: In module files with `#[cfg(test)]`
- Integration tests: In `tests/` directory
- End-to-end tests: `tests/e2e_integration_tests.rs`, `tests/full_chain_integration_test.rs`
- Benchmarks: `benches/composition_benchmark.rs`

### Observability
- Tracing: Use `tracing` crate macros (`info!`, `warn!`, `error!`, `debug!`)
- Metrics: Prometheus metrics on port 9090 at `/metrics`
- Traces: Stored in `data/traces/` with compression

## Important Notes

### Protobuf Compiler
The project requires `protoc` (Protocol Buffers compiler). The test script sets:
```bash
export PROTOC="$HOME/.local/bin/bin/protoc"
```

### Data Directory
The `--data-dir` flag (default: `./data`) controls where SQLite databases and traces are stored. This directory is created automatically.

### LLM Configuration
The system requires an OpenAI-compatible API:
- Set `OPENAI_API_KEY` environment variable, or
- Pass `--llm-api-key` flag
- Default model: `gpt-4`
- Default base URL: `https://api.openai.com/v1`

**Current Working Configuration (ARK API):**
- API Base URL: `https://ark.cn-beijing.volces.com/api/v3`
- Working Model: `glm-4-7-251222` (verified functional)
- Alternative Models: `deepseek-v3-241226`, `doubao-pro-32k-functioncall-241028`, `kimi-k2-250905`
- To get available models: `curl -s https://ark.cn-beijing.volces.com/api/v3/models -H "Authorization: Bearer <key>" | jq -r '.data[].id'`

## Service Management

### Using proclaw.sh Script (Recommended)

The `proclaw.sh` script in the project root manages all services:

```bash
# Start all services (Gateway, Prime Personality, Request Manager)
./proclaw.sh start

# Stop all services gracefully
./proclaw.sh stop

# Force kill all services
./proclaw.sh kill

# Restart all services
./proclaw.sh restart

# Check service status
./proclaw.sh status

# View logs
./proclaw.sh logs prime           # Rust kernel logs
./proclaw.sh logs gateway          # Gateway logs
./proclaw.sh logs request-manager  # Request Manager logs

# Clear all logs
./proclaw.sh clear-logs

# Test system with sample request
./proclaw.sh test
```

**Service Ports:**
- Prime Personality (Rust): `127.0.0.1:50051`
- Gateway (TypeScript): `http://localhost:3000`
- Request Manager (TypeScript): `127.0.0.1:50052`

**Log Files:**
- Prime: `/tmp/prime.log`
- Gateway: `/tmp/gateway.log`
- Request Manager: `/tmp/request-manager.log`

### Recent Development Focus
Based on git status, current work includes:
- Batch execution with parallel task processing
- Multi-session orchestration
- Time budget monitoring
- XML parser improvements
- Snapshot collection for observability

Files being actively developed:
- `src/scheduler/batch_task_executor.rs`
- `src/scheduler/multi_session_orchestrator.rs`
- `src/scheduler/parallel_executor.rs`
- `src/scheduler/time_budget_monitor.rs`
- `src/scheduler/snapshot_collector.rs`
- `src/scheduler/xml_parser.rs`
- `src/scheduler/xml_models.rs`

## Common Issues and Troubleshooting

### Compilation Errors

**Issue: Missing `batch_tasks` field in ParsedIntent**
- **Cause:** Struct definition updated but initializers not updated
- **Solution:** Add `batch_tasks: None` to all `ParsedIntent` initializers

**Issue: `anyhow::Error` doesn't implement Clone**
- **Cause:** Deriving `Clone` on structs containing `anyhow::Result`
- **Solution:** Remove `Clone` derive or use `Arc<anyhow::Error>`

**Issue: Module not found (feature-gated)**
- **Cause:** Module gated behind feature flag but imported unconditionally
- **Solution:** Add `#[cfg(feature = "...")]` to import

### Runtime Issues

**Issue: Model not found error from ARK API**
- **Cause:** Model name doesn't exist or no access
- **Solution:** Query available models:
  ```bash
  curl -s https://ark.cn-beijing.volces.com/api/v3/models \
    -H "Authorization: Bearer <key>" | jq -r '.data[].id'
  ```

**Issue: Services won't start**
- **Cause:** Ports already in use or permission issues
- **Solution:**
  ```bash
  ./proclaw.sh kill  # Force kill existing processes
  ./proclaw.sh start # Restart
  ```

**Issue: Gateway fails with EACCES mkdir '/var/gateway'**
- **Cause:** No permission to create /var/gateway
- **Solution:** Use `proclaw.sh` which sets correct data directories

### Development Tips

1. **Always check feature gates** when encountering "not found" errors
2. **Use `proclaw.sh` for service management** instead of manual starts
3. **Check logs** in `/tmp/` for debugging: `prime.log`, `gateway.log`, `request-manager.log`
4. **Verify model availability** before configuring LLM settings
5. **Use `cargo fix --lib --allow-dirty`** to auto-fix simple warnings

## Recent Fixes (2026-03-15)

- ✅ Fixed 22 compilation errors across scheduler, executor, and server modules
- ✅ Resolved missing `batch_tasks` field in ParsedIntent (8 locations)
- ✅ Fixed Clone trait issues in parallel executor
- ✅ Corrected function signature mismatches in multi-session orchestrator
- ✅ Added proper feature gates for conditional compilation
- ✅ Cleaned up 20+ unused imports
- ✅ Verified end-to-end functionality with ARK API (glm-4-7-251222 model)
- ✅ Updated proclaw.sh with working configuration

See `Documents/2026-03-15-rust-kernel-fixes.md` for detailed fix documentation.

