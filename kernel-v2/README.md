# ProClaw Kernel v2

Rust 实现的高性能 Agent Kernel，包含 Prime Personality、BlockComposer 和 Thread Executor。

## 架构概览

```
┌─────────────────────────────────────────────────────────────────┐
│                     TypeScript Gateway                           │
│                    (HTTP API on :3000)                          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Prime Personality (Rust)                      │
│                    (gRPC on :50051)                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │   LLM       │  │   Block     │  │   IR Process Executor   │  │
│  │   Router    │  │   Composer  │  │                         │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      Thread Executor                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │   Skills    │  │   Session   │  │   Scheduler             │  │
│  │   Registry  │  │   Host      │  │                         │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## 三层 gRPC 服务架构

1. **BlockComposer** (Unix socket: `/tmp/proclaw/composer.sock`)
   - 上下文组装和缓存服务
   - L1 (内存 LRU) + L2 (SQLite) 两级缓存
   - 提供 Session/Task/Prime 级别的上下文块

2. **AgentKernel** (同上)
   - 核心代理执行服务
   - 管理会话、进程和线程
   - 协调技能执行

3. **PrimePersonality** (TCP: `127.0.0.1:50051`)
   - 无状态编排层
   - LLM 驱动的决策
   - XML/JSON 通信协议

## Prompt 缓存优化

### 静态/动态分离架构

```
┌─────────────────────────────────────────────────────────────────┐
│  SYSTEM MESSAGE (可缓存 - ~2000 tokens, 70-80%)                 │
├─────────────────────────────────────────────────────────────────┤
│  Tier 1: 核心身份 (~300 tokens) - 缓存命中率 95%+               │
│  Tier 2: 能力定义 (~400 tokens) - 缓存命中率 90%                 │
│  Tier 3: 输出规范 (~500 tokens) - 缓存命中率 80%                 │
│  Tier 4: 行为规则 (~300 tokens) - 缓存命中率 60%                 │
│  Tier 5: Few-shot 示例 (~500 tokens) - 缓存命中率 40%            │
├─────────────────────────────────────────────────────────────────┤
│  USER MESSAGE (不缓存 - 每次请求变化)                           │
│  - current_state, task_goal, execution_history                  │
│  - artifacts, tool_results, error_context                       │
└─────────────────────────────────────────────────────────────────┘
```

### Provider 特定缓存策略

| Provider  | 策略              | 说明                              |
|-----------|-------------------|-----------------------------------|
| Claude    | `cache_control`   | 使用 `persistent`/`ephemeral` 参数 |
| DeepSeek  | system_prefix     | System message 自动缓存           |
| Kimi      | system_prefix     | System message 自动缓存           |
| GLM       | system_prefix     | System message 自动缓存           |
| MiniMax   | system_prefix     | System message 自动缓存           |

### 预期收益

- 缓存命中率: >80% (相同 session 内)
- Token 成本降低: 40-60%
- 响应延迟降低: 20-30% (缓存命中时)

## 快速开始

### 构建

```bash
cd kernel-v2

# Debug build
cargo build

# Release build (优化)
cargo build --release

# Run tests
cargo test

# Run benchmarks
cargo bench
```

### 运行

```bash
# 使用默认配置
cargo run -- --config /etc/proclaw/composer.yaml --llm-api-key <key>

# 覆盖设置
cargo run -- \
  --socket /tmp/proclaw.sock \
  --data-dir ./data \
  --llm-api-key $OPENAI_API_KEY \
  --llm-model gpt-4 \
  --llm-base-url https://api.openai.com/v1
```

### 服务管理

```bash
# 使用 proclaw.sh 脚本（推荐）
./proclaw.sh start    # 启动所有服务
./proclaw.sh stop     # 停止所有服务
./proclaw.sh restart  # 重启所有服务
./proclaw.sh status   # 检查服务状态
./proclaw.sh logs prime  # 查看 Rust kernel 日志
```

**服务端口:**
- Prime Personality (Rust): `127.0.0.1:50051`
- Gateway (TypeScript): `http://localhost:3000`
- Request Manager (TypeScript): `127.0.0.1:50052`

## 项目结构

```
kernel-v2/
├── Cargo.toml              # Rust project config
├── proto/                  # Protocol Buffers
│   ├── block_composer.proto
│   ├── agent_kernel.proto
│   └── prime_personality.proto
├── src/
│   ├── main.rs             # Entry point
│   ├── server/             # gRPC servers
│   │   ├── prime_personality_server.rs
│   │   ├── agent_kernel_server.rs
│   │   └── block_composer_server.rs
│   ├── config/             # Configuration & Prompt Composer
│   │   ├── app.rs
│   │   ├── prompt_composer.rs
│   │   └── dynamic.rs
│   ├── personality/        # Prime Personality
│   │   ├── prime.rs
│   │   └── models.rs
│   ├── scheduler/          # Thread Executor
│   │   ├── thread_executor.rs
│   │   ├── batch_task_executor.rs
│   │   └── multi_session_orchestrator.rs
│   ├── session/            # Session & Process Management
│   ├── executor/           # IR Process Executor
│   ├── llm/                # LLM Client & Router
│   │   ├── client.rs
│   │   ├── router.rs
│   │   └── models.rs       # CacheAwareMessage, CacheControl
│   ├── skills/             # Skill implementations
│   │   ├── bash_skill.rs
│   │   ├── gateway_skill.rs
│   │   └── composer_skill.rs
│   ├── utils/              # Utilities
│   │   └── token_counter.rs  # Tiktoken integration
│   └── observability/      # Metrics & Tracing
│       └── cache_metrics.rs  # Cache hit rate metrics
├── prompts/                # Prompt assets
│   ├── compositions/       # YAML composition configs
│   │   ├── prime.yaml
│   │   └── thread.yaml
│   └── assets/             # Markdown prompt fragments
│       ├── identity/
│       ├── capabilities/
│       ├── schemas/
│       ├── rules/
│       └── examples/
├── config/                 # Configuration templates
└── tests/                  # Integration tests
```

## API

### gRPC 服务

**PrimePersonality** (TCP :50051):
- `ProcessRequest`: 处理用户请求，返回 IR
- `HealthCheck`: 健康检查

**BlockComposer** (Unix socket):
- `Compose`: 组装上下文块
- `QueryBlocks`: 查询块
- `GetMetrics`: Prometheus 指标

### HTTP API (via Gateway)

```
POST /api/v1/chat
{
  "message": "用户消息",
  "session_id": "session-id",
  "user_id": "user-id",
  "priority": 10
}

Response:
{
  "requestId": "uuid",
  "sessionId": "session-id",
  "status": "accepted"
}
```

### 查询请求状态

```
GET /api/v1/requests/{requestId}

Response:
{
  "requestId": "uuid",
  "status": "completed",
  "response": {
    "body": "响应内容"
  }
}
```

## 配置

### YAML 配置 (composer.yaml)

```yaml
server:
  socket_path: /tmp/proclaw/composer.sock
  workers: 4

cache:
  l1_max_entries: 1000
  l2_path: ./data/cache.db

observability:
  metrics:
    enabled: true
    port: 9090
    path: /metrics
```

### CLI 参数

| 参数              | 说明                    | 默认值                           |
|-------------------|-------------------------|----------------------------------|
| `--config`        | 配置文件路径            | `/etc/proclaw/composer.yaml`     |
| `--socket`        | Unix socket 路径        | 从配置文件读取                   |
| `--data-dir`      | 数据目录                | `./data`                         |
| `--llm-api-key`   | LLM API 密钥            | 从环境变量 `OPENAI_API_KEY`      |
| `--llm-model`     | LLM 模型                | `gpt-4`                          |
| `--llm-base-url`  | LLM API 基础 URL        | `https://api.openai.com/v1`      |

## 监控

### Prometheus 指标

访问 `http://localhost:9090/metrics`：

```
# 缓存指标
proclaw_cache_hits_total{provider="deepseek"} 1234
proclaw_cache_misses_total{provider="deepseek"} 56
proclaw_cache_tokens_saved{provider="deepseek"} 45678
proclaw_cache_hit_rate{provider="deepseek"} 0.96

# 组装延迟
proclaw_composition_latency_seconds_bucket{le="0.01"} 12000
```

### 日志

```bash
# 查看 Prime 日志
tail -f /tmp/prime.log

# 查看 Gateway 日志
tail -f /tmp/gateway.log
```

## 测试

### 单元测试

```bash
cargo test --lib

# 特定模块
cargo test --lib config::prompt_composer
cargo test --lib llm::models
cargo test --lib observability::cache_metrics
```

### 集成测试

```bash
cargo test --test integration_test
cargo test --test full_chain_integration_test
```

### 端到端测试

```bash
# 启动服务
./proclaw.sh start

# 发送测试请求
curl -s -X POST http://localhost:3000/api/v1/chat \
    -H "Content-Type: application/json" \
    -d '{"message": "你好", "session_id": "test", "user_id": "test"}' | jq .
```

## 性能目标

- Block composition latency: <10ms
- Cache hit rate: >90%
- Memory usage per session: <50MB
- Prompt cache token savings: 40-60%

## 许可证

MIT OR Apache-2.0
