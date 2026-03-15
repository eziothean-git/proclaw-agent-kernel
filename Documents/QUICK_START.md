# ProClaw Quick Start Guide

## Prerequisites

- Rust 1.75+ installed
- Node.js 22+ installed
- ARK API key (or OpenAI-compatible API)

## Quick Start

### 1. Start All Services

```bash
cd /home/eziothean/ProClaw
./proclaw.sh start
```

This starts:
- Prime Personality (Rust Kernel) on port 50051
- Gateway (TypeScript) on port 3000
- Request Manager (TypeScript) on port 50052

### 2. Check Status

```bash
./proclaw.sh status
```

Expected output:
```
✅ Prime Personality (Rust) (port 50051)
✅ Gateway (TypeScript) (port 3000)
✅ Request Manager (TypeScript) (port 50052)
```

### 3. Send Test Request

```bash
curl -X POST http://localhost:3000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "你好",
    "session_id": "test-session",
    "user_id": "test-user",
    "priority": 10
  }'
```

### 4. View Logs

```bash
# Rust kernel logs
./proclaw.sh logs prime

# Gateway logs
./proclaw.sh logs gateway

# Request Manager logs
./proclaw.sh logs request-manager
```

### 5. Stop Services

```bash
./proclaw.sh stop
```

## Service Management Commands

| Command | Description |
|---------|-------------|
| `./proclaw.sh start` | Start all services |
| `./proclaw.sh stop` | Stop all services gracefully |
| `./proclaw.sh restart` | Restart all services |
| `./proclaw.sh status` | Check service status |
| `./proclaw.sh kill` | Force kill all services |
| `./proclaw.sh logs <service>` | View service logs |
| `./proclaw.sh test` | Run system test |
| `./proclaw.sh clear-logs` | Clear all log files |

## Building from Source

### Rust Kernel

```bash
cd kernel-v2

# Development build
cargo build

# Release build (optimized)
cargo build --release

# Run tests
cargo test

# Run benchmarks
cargo bench
```

### Gateway (TypeScript)

```bash
cd agent-kernel/apps/gateway

# Install dependencies
npm install

# Build
npm run build

# Run in development mode
npm run dev
```

## Configuration

### LLM Configuration

The system is currently configured for ARK API:

**Current Settings (in proclaw.sh):**
- API Key: `ca199063-af7d-4d99-9613-40bdc4c82831`
- Base URL: `https://ark.cn-beijing.volces.com/api/v3`
- Model: `glm-4-7-251222`

**To change model:**
1. Query available models:
   ```bash
   curl -s https://ark.cn-beijing.volces.com/api/v3/models \
     -H "Authorization: Bearer ca199063-af7d-4d99-9613-40bdc4c82831" \
     | jq -r '.data[].id'
   ```

2. Edit `proclaw.sh` and update the `--llm-model` parameter in `start_prime()` function

**Alternative Models:**
- `glm-4-7-251222` (current, verified working)
- `deepseek-v3-241226`
- `doubao-pro-32k-functioncall-241028`
- `kimi-k2-250905`

### Data Directories

- Rust kernel data: `kernel-v2/data/`
- Gateway data: `agent-kernel/apps/gateway/data/`
- Logs: `/tmp/prime.log`, `/tmp/gateway.log`, `/tmp/request-manager.log`

## Troubleshooting

### Services Won't Start

```bash
# Check if ports are in use
ss -tlnp | grep -E '(3000|50051|50052)'

# Force kill existing processes
./proclaw.sh kill

# Try starting again
./proclaw.sh start
```

### Compilation Errors

```bash
cd kernel-v2

# Clean build
cargo clean
cargo build

# Auto-fix simple issues
cargo fix --lib --allow-dirty
```

### Model Not Found Error

Check available models and update configuration:
```bash
curl -s https://ark.cn-beijing.volces.com/api/v3/models \
  -H "Authorization: Bearer <your-key>" \
  | jq -r '.data[].id' | sort
```

### Gateway Permission Errors

The `proclaw.sh` script handles data directory creation. If running manually:
```bash
export GATEWAY_DATA_DIR=/home/eziothean/ProClaw/agent-kernel/apps/gateway/data
mkdir -p $GATEWAY_DATA_DIR
```

## API Endpoints

### Gateway Endpoints

- **Health Check:** `GET http://localhost:3000/health`
- **Chat:** `POST http://localhost:3000/api/v1/chat`
- **Request Status:** `GET http://localhost:3000/api/v1/requests/:requestId`
- **Session Status:** `GET http://localhost:3000/api/v1/sessions/:sessionId/status`

### Example Chat Request

```bash
curl -X POST http://localhost:3000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "告诉我当前时间",
    "session_id": "my-session",
    "user_id": "user123",
    "priority": 10
  }'
```

Response:
```json
{
  "requestId": "uuid-here",
  "sessionId": "sess_xxx",
  "status": "accepted",
  "timestamp": "2026-03-15T15:00:00.000Z",
  "message": "Request accepted and queued for processing"
}
```

## Architecture Overview

```
┌─────────────────┐
│   User/Client   │
└────────┬────────┘
         │ HTTP
         ▼
┌─────────────────┐
│    Gateway      │ (TypeScript, Port 3000)
│   (NestJS)      │
└────────┬────────┘
         │ gRPC
         ▼
┌─────────────────┐
│ Request Manager │ (TypeScript, Port 50052)
└────────┬────────┘
         │ gRPC
         ▼
┌─────────────────┐
│ Prime Personality│ (Rust, Port 50051)
│  (Rust Kernel)  │
└────────┬────────┘
         │
         ├─→ BlockComposer (Context)
         ├─→ AgentKernel (Execution)
         └─→ LLM Router (ARK API)
```

## Next Steps

1. **Test the system:** Send various requests to test functionality
2. **Monitor logs:** Watch `/tmp/prime.log` for execution details
3. **Customize prompts:** Modify system prompts in the codebase
4. **Add skills:** Extend functionality by adding new skills
5. **Performance tuning:** Adjust cache settings and worker counts

## Support

- **Documentation:** See `CLAUDE.md` for detailed architecture
- **Recent Fixes:** See `Documents/2026-03-15-rust-kernel-fixes.md`
- **Issues:** Check logs in `/tmp/` directory

## Version Info

- Rust Kernel: v0.1.0
- Gateway: v0.2.0
- Last Updated: 2026-03-15
- Status: ✅ Fully Functional
