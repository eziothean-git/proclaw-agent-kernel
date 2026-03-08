# Agent Kernel

A dual-layer AI agent architecture with TypeScript control layer and Python intelligence layer.

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────┐
│                        USER REQUEST                          │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  LAYER 1: TypeScript Control (apps/gateway)                  │
│  ├─ Gateway API (HTTP/WebSocket)                            │
│  ├─ Request Queue (per-session serialization)               │
│  ├─ Scheduler (time-based triggers)                         │
│  ├─ Executor (unified execution & MCP client)               │
│  └─ Router (session routing)                                │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│  LAYER 2: Python Intelligence (apps/python-kernel)           │
│  ├─ Prime Personality (stateless orchestration)             │
│  ├─ Master Context Compiler (main personality context)      │
│  ├─ Process Context Compiler (execution context)            │
│  ├─ Session Host (session-level agent)                      │
│  ├─ Thread Runtime (execution-level agents)                 │
│  ├─ Skills (MCP-based capabilities)                         │
│  └─ Runtime Storage (SQLite state management)               │
└─────────────────────┬───────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────┐
│                     MCP SKILLS                               │
│  ├─ File System Skill                                       │
│  ├─ Shell Execution Skill                                   │
│  └─ Custom Skills...                                        │
└─────────────────────────────────────────────────────────────┘
```

## Quick Start

### Prerequisites
- Node.js 18+
- Python 3.11+
- SQLite

### Installation

```bash
# Install dependencies
npm install

# Initialize database
npm run bootstrap

# Start all services in development mode
npm run dev
```

### Individual Service Development

```bash
# Terminal 1: Start Gateway
npm run dev --workspace=apps/gateway

# Terminal 2: Start Python Kernel
cd apps/python-kernel
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python main.py
```

## Project Structure

- `apps/gateway/` - NestJS API gateway and control layer
- `apps/python-kernel/` - Python agent intelligence layer
- `packages/shared-schema/` - TypeScript/Python shared schemas
- `packages/skill-protocol/` - MCP protocol definitions
- `skills/local/` - Local MCP skill implementations
- `docs/` - Architecture documentation

## Key Design Principles

1. **Dual Layer Architecture**: TS handles control flow, Python handles intelligence
2. **Stateless Orchestration**: Prime Personality is stateless
3. **Context Governance**: Context Compilers control information visibility
4. **MCP Uniformity**: All skills integrate via MCP protocol
5. **Observability First**: OpenTelemetry integration throughout

## Documentation

- [Architecture Overview](docs/architecture/INFO_FLOW.md)
- [MCP Integration](docs/protocols/MCP_INTEGRATION.md)
- [Tech Stack Decisions](docs/decisions/TECH_STACK.md)

## License

MIT
