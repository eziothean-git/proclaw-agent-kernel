# Agentic Coding Guidelines for Agent Kernel

This document provides essential information for AI agents working on the Agent Kernel codebase.

## Project Vision

Agent Kernel is a **long-running information flow kernel**, not "a big agent". It orchestrates multi-level Agent Primitives, context compilation, request governance, runtime snapshots, and persistent memory.

**Key Philosophy:**
- LLM is a replaceable plugin, not the system itself
- System uses model intelligence through context governance
- Personality continuity comes from stable prompts + memory, not any single model
- Agent is a primitive operator, not a fully autonomous intelligent subject

## Current Implementation Status

**Implemented:**
- Gateway (TypeScript/NestJS) - Entry point with filesystem mailbox
- Request Manager (TypeScript/gRPC) - Priority-based request queue
- Scheduler (TypeScript) - Agent Thread scheduling infrastructure
- Python Kernel - FastAPI app with basic structure
  - **Atomic Agent Thread** - ✅ **FULLY IMPLEMENTED** - Event Log + Working Set architecture
    - Event Log Manager - Complete event stream tracking
    - Working Set Builder - Rule-driven context constructor (YAML configurable)
    - Agent Output Parser - Structured intent parsing (JSON/YAML/heuristic)
    - SEE-ACT-UPDATE execution loop
    - Phase-based execution (Explore → Execute → Complete)
    - Upper layer intervention APIs (pause/resume/update)
  - **Context Compilers (Master & Process)** - ✅ **IMPLEMENTED** (~3,500 lines)
    - Master Compiler - Prime scope context management (549 lines)
    - Process Compiler - Session scope context compilation (116 lines)
    - Compiler Agent - Advanced agent with exploration capabilities (513 lines)
    - Prime Compiler Agent - Prime personality compiler agent (581 lines)
    - Compilation Auditor - Quality assurance and validation (415 lines)
    - Context Compiler Skill - Context compilation as a skill (509 lines)
    - Prime Compiler Skill - Prime-specific compilation skill (341 lines)
    - Test Coverage: 52/52 tests passed (100%) - All issues fixed
  - **Prime Personality** - ✅ **IMPLEMENTED** - 集成 Master Compiler 上下文
    - 消费 CompiledContext 进行智能意图分类
    - 利用预编译的意图分析、复杂度评分
    - 支持 Agent 辅助探索收集的 Artifacts
    - 延迟初始化 Agent，支持 `force_mock` 元数据覆盖
  - **Session Host** - ✅ **IMPLEMENTED** - 会话编排 + 长期记忆
    - 任务生命周期管理和流程执行
    - Host 级长期记忆管理（不由 Agent Thread 访问）
    - `extract_and_submit_memories()` 任务后记忆提取
    - 通过 `submit_long_term_candidate()` 提交记忆
  - **Long-term Memory** - ✅ **IMPLEMENTED** - 文件系统存储
    - `LongTermMemoryStore` 基于 JSONL 的持久化存储
    - 按会话、类别、重要性查询
    - 索引文件加速查找
    - `RuntimeMemoryManager` 集成接口
  - Inbox Watcher - Filesystem mailbox integration (for Gateway integration)
  - Scheduler - Async task scheduling with Agent Thread lifecycle management
  - Execution Coordinator - Local skill registry + remote executor client
  - Agentic OS Interface Skill - System-level coordination layer
- Storage/Runtime Memory (FileStorageAdapter & SQLiteStorageAdapter)
- Integration Tests - Gateway + Python Kernel full flow testing

> **实现状态:**
> - **Context Compilers** 已实现完整功能
> - **Atomic Agent** 已完成完整实现
> - **Prime Personality** 已实现：集成 Master Compiler 上下文进行智能意图分类
> - **Session Host** 已实现：会话编排 + Host 级长期记忆管理
> - **Long-term Memory** 已实现：文件系统存储，支持按会话/类别/重要性查询
> - **gRPC信息流架构** ✅ **已完成重构** - 完全移除轮询，使用gRPC流推送
>   - Gateway → Request Manager: Unary调用SubmitRequest
>   - Request Manager → Python Kernel: Server Stream推送任务
>   - Python Kernel → Request Manager: Unary调用SubmitResult
>   - Request Manager → Gateway: Server Stream推送响应
> - **优雅关闭** ✅ **已实现** - 10秒超时shutdown端点

**NOT YET Implemented:**
- 长期记忆检索与利用（会话启动时自动加载相关记忆）
- Advanced Agent capabilities (multi-agent collaboration)

## Architecture Overview

### 7 Macro Layers (top to bottom)
1. External Access Layer (Gateway)
2. Request Source Layer (Queue Manager, Scheduled Dispatcher)
3. Personality Entry Layer (Prime Personality)
4. System Interface/Routing Layer (Agentic OS Interface Skill)
5. Session Orchestration Layer (Session Host, Context Compilers)
6. Task Execution Layer (Agent Thread, Scheduler, Executor)
7. Memory & Capability Support Layer (Memory Base, SKILL lib)

### 信息流动架构 (重构后 - 2026-03-11)

**核心变更：完全基于gRPC的实时信息流**

```
┌─────────────────┐         gRPC (Unary)        ┌──────────────────┐
│    Gateway      │  ─────────────────────────> │ Request Manager  │
│   (Port 3000)   │  SubmitRequest              │   (Port 50052)   │
│                 │                             │                  │
└─────────────────┘         gRPC (Server Stream)└──────────────────┘
        ^          <─────────────────────────          │
        │             SubscribeResponses               │
        │                                              │ gRPC (Server Stream)
        │              ┌───────────────────────────────┘
        │              │ StreamTasks
        │              ▼
        │      ┌──────────────────┐
        │      │  Python Kernel   │  gRPC (Unary) SubmitResult
        │      │   (Port 8000)    │ ───────────────────────────>
        │      └──────────────────┘
        │
        │  HTTP POST /v1/shutdown
        │  (10s graceful shutdown)
```

**流类型说明：**
- **Unary**: 单次请求-响应（提交请求、提交结果）
- **Server Stream**: 服务端主动推送（任务分发、响应推送）
- **双向流**: 用于需要持续通信的场景（当前未使用）

**关键变更：**
1. **移除所有轮询** - 不再轮询文件系统inbox/outbox
2. **gRPC流推送** - Request Manager主动推送任务给Kernel，推送响应给Gateway
3. **持久化解耦** - 文件系统仅用于持久化备份，不作为通信机制
4. **优雅关闭** - 所有服务支持 `/v1/shutdown` HTTP端点，10秒超时

### Two Object Families

**Agent Primitive Family** (cognitive):
- Prime Personality, Session Host, Context Compilers, Agent Thread
- Responsible for interpretation, judgment, generating intent

**Infrastructure Family** (execution/storage):
- Gateway, Request Queue, Scheduler, Executor, Memory Manager
- Responsible for queueing, execution, storage, runtime snapshots

### Key Concepts

**Compiled Context:** Generated by Context Compiler, consumed by Agent Primitives. Input view, not the whole truth.

**Runtime Working Context:** Bounded working context maintained during execution via Event Log + Working Set (not chat history).

**Event Log + Working Set Model:**
- Event Log: Complete event stream (SEE-ACT-UPDATE loop events)
- Artifact Slots: Structured intermediate outputs (module_map, symbol_index, etc.)
- Working Set Builder: Rule-driven constructor for bounded prompt view
- Working Set: Fixed-size view actually fed to model

**SEE-ACT-UPDATE Loop:**
- SEE: Read observation/tool result/environment feedback
- ACT: Generate capability request or structured action intent
- UPDATE: Write to Event Log/Artifact Slots, rebuild Working Set

## Project Structure

- `/agent-kernel/` - Main monorepo root
  - `apps/` - Applications
    - `gateway/` - NestJS gateway (TypeScript) - EXTERNAL ACCESS LAYER
    - `request-manager/` - Request management with gRPC (TypeScript) - REQUEST SOURCE LAYER
    - `python-kernel/` - Python intelligence layer (skeleton) - SESSION/EXECUTION LAYERS
  - `packages/` - Shared libraries
    - `shared-schema/` - Common TypeScript types/schemas
    - `skill-protocol/` - MCP skill protocol definitions
    - `observability/` - Logging and tracing utilities
  - `skills/local/` - Local MCP skills (TypeScript)
  - `tests/` - Python integration tests
- `/schema/` - Architecture specifications (READ THESE!)
- `/src/` - Legacy TypeScript source (migrating to agent-kernel)

## Build Commands

### TypeScript/JavaScript (agent-kernel/)

```bash
# Build all packages
npm run build

# Build specific app/package
cd agent-kernel/apps/gateway && npm run build

# Type checking
npm run typecheck

# Clean build artifacts
npm run clean
```

### Python (agent-kernel/apps/python-kernel/)

```bash
cd agent-kernel/apps/python-kernel

# Install dependencies
pip install -e ".[dev]"

# Run the kernel
python main.py
```

### Rust (kernel-v2/)

```bash
cd kernel-v2

# Build the project
~/.cargo/bin/cargo build

# Check compilation without building
~/.cargo/bin/cargo check

# Run the kernel
~/.cargo/bin/cargo run

# Build for release
~/.cargo/bin/cargo build --release
```

**Note**: protoc (Protocol Buffers compiler) is required for building. It's installed at `~/.local/bin/protoc`. Set the environment variable before building:
```bash
export PROTOC=$HOME/.local/bin/protoc
~/.cargo/bin/cargo build
```

## Lint Commands

### TypeScript/JavaScript

```bash
# Lint all packages
npm run lint

# Lint specific package
cd agent-kernel/apps/gateway && npm run lint

# Format code
npm run format
```

### Python

```bash
cd agent-kernel/apps/python-kernel

# Format with Black (100 char line length)
black .

# Lint with Ruff
ruff check . --fix

# Type checking
mypy .
```

### Rust

```bash
cd kernel-v2

# Format code
~/.cargo/bin/cargo fmt

# Lint with Clippy
~/.cargo/bin/cargo clippy -- -D warnings

# Check without building
~/.cargo/bin/cargo check
```

## Latest Test Results

**Date**: 2026-03-11  
**Status**: 🔄 **迁移到服务端集成测试**

### 测试策略变更

已删除所有基于 pytest 的单元测试，改为**服务端集成测试**：

| 测试类型 | 描述 | 命令 |
|----------|------|------|
| 完整集成测试 | 自动启动所有服务(Gateway+RM+Kernel) | `npm run test:integration` |
| 客户端测试 | 对运行中的服务发HTTP请求 | `python3 test-client.py` |
| 历史验证 | 检查SQLite记录完整性 | `npm run test:history` |

### 已清理的测试脚本 (2026-03-11)

**删除的启动脚本:**
- `start-all.sh` - 功能与 `launcher.sh` 重复
- `proclaw-start.sh` - 过于复杂，功能已合并

**删除的测试脚本:**
- `test-integration.sh` (根目录) - 只测试 Gateway，不完整
- `test-gateway-mailbox.sh` - 功能重复
- `agent-kernel/test-integration.sh` - 需要手动启动服务
- `test_report.sh`, `cleanup_report.sh`, `fix_report.sh` - 遗留报告

**删除的 Python 单元测试:**
- `test_context_compiler.py`
- `test_compiler_integration.py`
- `test_prime_compiler.py`
- `test_llm.py`
- `test_ark_llm.py`

**保留的脚本:**
- `launcher.sh` - 统一启动入口（根目录）
- `stop-all.sh` - 停止服务（根目录）
- `test-client.py` - 服务端测试客户端（根目录）
- `agent-kernel/scripts/test-gateway-kernel-integration.sh` - 完整集成测试

### Full Test Report

See `agent-kernel/FULL_TEST_REPORT.md` for detailed test results and execution logs (Note: This file is deprecated as we've moved to server-side integration tests).

## Test Commands

### 测试策略 (Updated 2026-03-11)

**重要**: 本项目已统一为**服务端集成测试**策略，不再维护单元测试。所有测试都通过直接向运行中的服务发送请求来完成。

**可用测试方式:**

1. **完整集成测试** (推荐) - 自动启动所有服务并测试完整流程
   ```bash
   cd agent-kernel
   npm run test:integration
   ```

2. **手动集成测试** - 保持数据持久化
   ```bash
   cd agent-kernel
   npm run test:integration:manual
   ```

3. **客户端测试** - 对已运行的服务进行测试
   ```bash
   # 先启动服务
   ./launcher.sh
   
   # 然后运行测试客户端
   python3 test-client.py
   
   # 完整测试套件
   python3 test-client.py --full
   
   # 持续压力测试
   python3 test-client.py --continuous --interval 5
   ```

4. **验证历史记录**
   ```bash
   cd agent-kernel
   npm run test:history
   ```

### 快速测试命令

```bash
# 启动所有服务
./launcher.sh

# 服务启动后，运行测试客户端
python3 test-client.py
```

## Code Style Guidelines

### TypeScript/JavaScript

**Imports:**
- Use absolute imports for external packages
- Use path aliases for internal modules: `@shared/*`, `@skill/*`
- Group imports: external → internal → relative

**Formatting:**
- Prettier with default settings
- 2-space indentation
- Semicolons required
- Single quotes for strings

**Types:**
- Strict TypeScript configuration
- Explicit return types on public functions
- Use interfaces for object shapes
- Use `type` for unions/aliases

**Naming:**
- PascalCase for classes, interfaces, types
- camelCase for variables, functions, methods
- UPPER_SNAKE_CASE for constants

**NestJS Patterns:**
- Use decorators for metadata
- Dependency injection via constructor
- Controllers for HTTP handlers, Services for business logic

### Python

**Imports:**
- Standard library → third-party → local modules
- Use absolute imports

**Formatting:**
- Black formatter, 100 char line length
- Ruff for linting

**Types:**
- Use type hints on all functions
- Use Pydantic models with `ConfigDict(strict=True)`
- Prefer `dict[str, Any]` over `Dict[str, Any]`

**Naming:**
- snake_case for functions, variables
- PascalCase for classes

**Pydantic Pattern:**
```python
class MyModel(BaseModel):
    model_config = ConfigDict(strict=True)
    id: str = Field(description="Unique identifier")
```

**Error Handling:**
- Use explicit exception types
- Log with structlog
- FastAPI HTTPException for API errors

## Architecture Patterns

### Gateway (TypeScript)
- Entry point for all external requests
- Filesystem mailbox for inter-service communication
- NestJS with OpenTelemetry instrumentation

### Python Kernel
- FastAPI with lifespan management
- Async/await throughout
- Structlog for structured logging
- Pydantic for all data models

### Skills (TypeScript)
- MCP (Model Context Protocol) SDK
- Zod for schema validation
- Tools expose capabilities to agents

## Key Design Principles

1. **No Chat History Bloat:** Agent Threads use Event Log + Working Set, not growing chat context
2. **Rule-Driven Views:** Working Set Builder uses rules, not LLM, to construct prompt views
3. **Atomic vs Advanced Agents:** Agent Thread is atomic (no context re-editing); Context Compilers are advanced
4. **Explore/Execute as Phases:** Same Agent Thread template, different phase profiles
5. **A2A Not Required:** Single-thread MVP first; multi-agent collaboration is future enhancement

## Environment Variables

### Gateway
- `GATEWAY_STORAGE_PATH` - Filesystem mailbox base path (default: /var/gateway)
- `PORT` - Gateway HTTP port (default: 3000)
- `PYTHON_KERNEL_URL` - Python Kernel HTTP endpoint (default: http://localhost:8000)
- `NODE_ENV` - Environment mode (development/production/test)

### Python Kernel
- `PORT` - Kernel HTTP port (default: 8000)
- `HOST` - Bind address (default: 0.0.0.0)
- `KERNEL_RUN_MODE` - Execution mode:
  - `real`: Call actual LLM API (requires LLM API key)
  - `mock`: Return mock responses (for testing)
- `DATA_PATH` - Runtime data storage path (default: ./data)
- `STORAGE_TYPE` - Backend type: `file` or `sqlite` (default: file)
- `GATEWAY_INBOX_PATH` - Gateway inbox directory for filesystem mailbox integration
- `GATEWAY_URL` - Gateway base URL for callbacks (default: http://localhost:3000)
- `INBOX_POLL_INTERVAL` - Inbox polling interval in seconds (default: 1.0)

#### LLM Provider Configuration
- `LLM_PROVIDER` - LLM provider: `ark` (default), `openai`, `custom`
- `ARK_API_KEY` - Volcengine Ark API key (for Chinese market)
- `ARK_BASE_URL` - Ark API endpoint (default: https://ark.cn-beijing.volces.com/api/v3)
- `ARK_MODEL` - Ark model name (default: glm-4.7)
- `OPENAI_API_KEY` - OpenAI API key (alternative provider)
- `OPENAI_BASE_URL` - OpenAI API endpoint
- `OPENAI_MODEL` - OpenAI model name
- `LLM_TEMPERATURE` - Generation temperature (default: 0.7)
- `LLM_MAX_TOKENS` - Max tokens per generation (default: 4000)

### Rust Kernel (kernel-v2)
- `PORT` - Kernel HTTP port (default: 8000)
- `HOST` - Bind address (default: 0.0.0.0)
- `DATA_PATH` - Runtime data storage path (default: ./data)
- `OPENAI_API_KEY` - OpenAI API key for LLM calls
- `ARK_API_KEY` - ByteDance Ark API key (alternative)
- `PROTOC` - Path to protobuf compiler (default: ~/.local/bin/protoc)

### Integration Test
- `GATEWAY_STORAGE_PATH` - Test data directory for Gateway
- `DATA_PATH` - Test data directory for Python/Rust Kernel

## Integration Testing

### Quick Start

```bash
cd agent-kernel

# Run full integration test (builds, starts services, tests, verifies)
npm run test:integration

# Verify history records after test
npm run test:history

# Manual test with persistence
npm run test:integration:manual
```

### Test Flow

Integration test validates the complete data flow:
1. **Gateway** accepts HTTP request → writes to `inbox/`
2. **Inbox Watcher** detects new request → submits to processing
3. **Prime Personality** generates Intermediate Representation
4. **Session Host** orchestrates execution
5. **Scheduler** manages Agent Thread lifecycle
6. **Callback** sends result back to Gateway
7. **Gateway** writes response to `outbox/`
8. **History** records saved to storage (SQLite or files)

### Files Created

```
data/
├── gateway/                 # Gateway filesystem mailbox
│   ├── inbox/              # Input requests
│   ├── outbox/             # Output responses
│   ├── pending/            # Processing requests
│   ├── attachments/        # File attachments
│   ├── sessions/           # Session metadata
│   ├── errors/             # Error logs
│   └── logs/               # Operation logs
├── apps/python-kernel/     # Python Kernel data
│   ├── runtime.db          # SQLite database (if using sqlite storage)
│   ├── sessions/           # Session files
│   ├── requests/           # Request history
│   ├── tasks/              # Task records
│   ├── snapshots/          # Execution snapshots
│   └── events/             # Event logs
└── long_term_memory/       # Long-term memory storage (Session Host)
    ├── index.json          # Global index for fast lookups
    ├── by_session/         # Memory entries per session
    │   └── {session_id}.jsonl
    └── by_category/        # Memory entries per category
        └── {category}.jsonl
```

### Documentation

- [Integration Test Script](./scripts/test-gateway-kernel-integration.sh) - Automated integration test
- [History Verification](./scripts/verify-history.py) - History records validator
- [Atomic Agent Implementation](./apps/python-kernel/ATOMIC_AGENT_IMPLEMENTATION.md) - Implementation details
- [Context Compiler Implementation](./apps/python-kernel/CONTEXT_COMPILER_IMPLEMENTATION.md) - Compiler details
- [Test Client](../../test-client.py) - Python client for server-side testing

## Running the System

### Quick Start

```bash
# Start all services using launcher script
./launcher.sh

# Stop all services (graceful shutdown with 10s timeout)
./stop-all.sh

# Or start individually:
# Terminal 1: Request Manager (must start first)
cd agent-kernel/apps/request-manager && npm start

# Terminal 2: Python Kernel
cd agent-kernel/apps/python-kernel && python main.py

# Terminal 3: Gateway
cd agent-kernel/apps/gateway && npm run dev
```

### Service Shutdown

**重要**: 使用 `./stop-all.sh` 脚本进行优雅关闭，它会：
1. 发送 HTTP `POST /v1/shutdown` 到 Gateway 和 Python Kernel
2. 等待 10 秒让服务完成当前请求
3. 强制停止剩余进程

**手动关闭**:
```bash
# 对每个服务发送 shutdown 请求
curl -X POST http://localhost:3000/v1/shutdown   # Gateway
curl -X POST http://localhost:8000/v1/shutdown   # Python Kernel
# Request Manager 暂时使用 kill
```

### Log Locations

**Runtime Logs:**
- **Request Manager**: `/tmp/request-manager.log`
- **Python Kernel**: `/tmp/proclaw-kernel.log`
- **Gateway**: `/tmp/proclaw-gateway.log`

**Integration Test Logs:**
- `/tmp/request-manager-integration.log`
- `/tmp/kernel-integration.log`
- `/tmp/gateway-integration.log`

**Data Storage:**
- **Gateway**: `agent-kernel/data/gateway/`
  - `inbox/` - Input requests
  - `outbox/` - Output responses
  - `errors/` - Error logs
  - `logs/` - Operation logs
- **Python Kernel**: `agent-kernel/data/`
  - `sessions/` - Session files
  - `requests/` - Request history
  - `tasks/` - Task records
  - `snapshots/` - Execution snapshots
  - `events/` - Event logs
- **Long-term Memory**: `agent-kernel/data/long_term_memory/`
  - `by_session/` - Session-specific memories
  - `by_category/` - Category-organized memories

**View Logs in Real-time:**
```bash
# View all service logs
tail -f /tmp/request-manager.log /tmp/proclaw-kernel.log /tmp/proclaw-gateway.log

# View specific service log
tail -f /tmp/proclaw-kernel.log
```

## Testing Checklist

Before submitting changes:
- [ ] `npm run typecheck` passes (TypeScript/JavaScript)
- [ ] `npm run lint` passes
- [ ] Python: `ruff check .` passes
- [ ] Python: `black .` formatting applied (100 char line length)
- [ ] Integration tests pass: `npm run test:integration`
- [ ] Server-side verification: `python3 test-client.py --full`

## Resources

- Architecture specs: `/schema/agent_kernel_architecture_spec_restructured.md`
- Architecture changes summary: `/schema/agent_kernel_architecture_changes_summary.md`
- Schema diagram: `/schema/schema.png`
