# Rust Agent Kernel - API Status

This document describes the current gRPC API status for Phase 2 architecture.

## Core APIs (Required for New Architecture)

### ComposerService

| Method | Status | Description |
|--------|--------|-------------|
| `Compose` | ✅ Implemented | Compose blocks into context |
| `ExecuteBash` | ✅ Implemented | Execute bash commands via skill |
| `ValidateToken` | ✅ Implemented | Token validation |
| `RevokeToken` | ✅ Implemented | Token revocation |
| `HealthCheck` | ✅ Implemented | Service health check |

**Optional (Not Implemented)**:
- `QueryBlocks` - Block query interface
- `GetTrace/ListTraces/ReplayTrace` - Tracing features
- `GetMetrics` - Metrics (partial: only cache stats)
- `SubscribeTraces` - Trace streaming (returns empty stream)

### AgentKernelService

| Method | Status | Description |
|--------|--------|-------------|
| `CreateThread` | ✅ Implemented | Create new thread |
| `SpawnExecutor` | ✅ Implemented | Spawn executor for thread |
| `ControlExecutor` | ✅ Implemented | Pause/resume executor |
| `KillExecutor` | ✅ Implemented | Kill executor |
| `StreamExecutorEvents` | ✅ Implemented | Stream executor events |
| `ExecuteSkill` | ✅ Implemented | Execute skill via coordinator |
| `HealthCheck` | ✅ Implemented | Service health check |
| `Shutdown` | ✅ Implemented | Graceful shutdown |

**Simplified**:
- `GetResourceStatus` - Returns empty response (lock status not exposed)
- `GetTicketStatus` - Returns placeholder (TicketTracker not implemented)
- `GetSystemStatus` - Returns basic stats (pending_tickets always 0, skill_stats empty)

## New ComposerSkill Interface (Rust Internal)

The `ComposerSkill` provides a unified internal interface:

```rust
pub struct ComposerSkill {
    // Block management
    pub async fn upsert_block(...);
    pub async fn remove_block(...);
    pub async fn get_block(...);
    pub async fn list_all_blocks(...);
    pub async fn list_blocks_by_type(...);
    
    // Composition
    pub async fn compose(...);
    pub async fn compose_and_generate(...);
    
    // Execution with directory lock
    pub async fn execute_with_lock(...);
}
```

## Recommended Simplification

For the new architecture, consider exposing these minimal gRPC methods:

1. **Block Management** (via ComposerService or new ComposerSkillService)
   - `UpsertBlock`
   - `RemoveBlock`
   - `ListBlocks`

2. **Composition & Generation**
   - `Compose` (existing)
   - `ComposeAndGenerate` (new: compose + LLM generate)

3. **Execution**
   - `ExecuteAction` (with directory lock)
   - `ExecuteSkill` (existing)

4. **Health**
   - `HealthCheck`

## Notes

- Directory locking with FIFO queue is fully implemented internally
- Session/Process/Thread management is available via `SessionHostSkills`
- `TicketTracker` is a placeholder for future quota/throttling features
- Tracing/Metrics are optional for core functionality
