# Agent Kernel

[![Rust](https://img.shields.io/badge/rust-1.75%2B-orange)](https://www.rust-lang.org/)
[![TypeScript](https://img.shields.io/badge/typescript-5.0%2B-blue)](https://www.typescriptlang.org/)
[![gRPC](https://img.shields.io/badge/gRPC-1.65%2B-green)](https://grpc.io/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

> **长期运行的信息流内核** —— 不是"一个大智能体"，而是一个智能体编排与上下文治理系统。

Agent Kernel 是一个多层级智能体原语编排系统，专注于上下文编译、请求治理、运行时快照和持久化记忆。系统将 LLM 视为可替换的插件，而非系统本身。

## 核心特性

- **7层宏观架构** —— 从外部访问到内存支持的分层设计
- **Control Plane / Data Plane 分离** —— 基于权限等级的安全架构
- **Event Log + Working Set** —— 替代传统聊天记录的上下文管理模型
- **SEE-ACT-UPDATE 执行循环** —— 标准化的智能体执行模式
- **gRPC 通信** —— Gateway ↔ Request Manager ↔ Rust Kernel 全链路 gRPC
- **IR 中间表示** —— 带 `content.text` 的结构化响应格式

## 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                    7 Macro Layers                           │
├─────────────────────────────────────────────────────────────┤
│ 1. External Access Layer    │ Gateway (NestJS)              │
│ 2. Request Source Layer     │ Priority Queue, Worker Pool   │
│ 3. Personality Entry Layer  │ Prime Personality (Rust)      │
│ 4. System Interface Layer   │ OS Interface Skill (P0)       │
│ 5. Session Orchestration    │ Session Host, Context Compilers│
│ 6. Task Execution Layer     │ Agent Thread, Executor        │
│ 7. Memory & Capability      │ Memory Base, SKILL Library    │
└─────────────────────────────────────────────────────────────┘
```

### 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| Gateway | TypeScript + NestJS | HTTP API + Webhook |
| Request Manager | TypeScript + gRPC | 请求队列 + 任务调度 |
| Prime Personality | Rust + tonic | IR 生成 + 意图分类 |
| Kernel Core | Rust + tokio | Data/Control Plane |

### 关键概念

**Compiled Context**: 由上下文编译器生成的输入视图，非完整真相  
**Runtime Working Context**: 通过 Event Log + Working Set 维护的有限工作上下文  
**SEE-ACT-UPDATE Loop**:
- **SEE**: 读取观察/工具结果/环境反馈
- **ACT**: 生成能力请求或结构化动作意图
- **UPDATE**: 写入 Event Log/Artifact Slots，重建 Working Set

**Intermediate Representation (IR)**:
- `intent`: 用户意图分类
- `goals`: 任务目标列表
- `processes`: 可执行流程定义
- `content.text`: 直接返回给用户的内容

## 实现状态

| 组件 | 状态 | 说明 |
|------|------|------|
| Gateway | ✅ 完整 | NestJS 网关，HTTP + gRPC 客户端 |
| Request Manager | ✅ 完整 | gRPC 请求队列，Priority Queue |
| Prime Personality | ✅ 完整 | Rust gRPC 服务，IR 生成 |
| Gateway Skill | ✅ 完整 | HTTP POST 回传结果到 Gateway |
| Scheduler | ✅ 完整 | 智能体线程调度基础设施 |
| Atomic Agent Thread | ✅ 完整 | Event Log + Working Set 架构 |
| Context Compilers | ✅ 完整 | Master/Process/Compiler Agent |
| Session Host | ✅ 完整 | 任务编排 + 长期记忆管理 |
| Memory Base | ✅ 基础 | 文件系统长期记忆存储 |
| Multi-Agent Collaboration | ⏳ 未实现 | 多智能体协作（未来增强） |

**测试状态**: ✅ 端到端流程测试通过

## 快速开始

### 环境要求

- **Rust** 1.75+ (with cargo)
- **Node.js** 18+
- **pnpm** or **npm**
- **Protocol Buffers** (`protoc`)

```bash
# 安装 Rust (如果未安装)
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

# 安装 Protocol Buffers
# Ubuntu/Debian:
sudo apt-get install -y protobuf-compiler
# macOS:
brew install protobuf
```

### 安装依赖

```bash
# 1. 克隆仓库
cd /home/eziothean/ProClaw

# 2. 构建 Rust Kernel
cd kernel-v2
cargo build --release --features control-plane

# 3. 安装 TypeScript 依赖
cd ../agent-kernel
npm install

# 4. 构建 Gateway 和 Request Manager
cd apps/gateway && npm run build
cd ../request-manager && npm run build
```

### 启动服务

使用统一脚本管理所有服务：

```bash
# 启动所有服务（Prime + Gateway + Request Manager）
./proclaw.sh start

# 查看状态
./proclaw.sh status

# 测试系统
./proclaw.sh test

# 查看日志
./proclaw.sh logs prime
./proclaw.sh logs gateway
./proclaw.sh logs request-manager

# 优雅停止
./proclaw.sh stop

# 强制结束（如果有残留进程）
./proclaw.sh kill

# 清除日志
./proclaw.sh clear-logs
```

### 手动启动（开发调试用）

```bash
# Terminal 1: Prime Personality (Rust)
cd kernel-v2
./target/release/proclaw-composer \
    --config ./config/composer.yaml \
    --data-dir ./data \
    --llm-api-key "YOUR_API_KEY" \
    --llm-base-url "https://api.example.com/v1" \
    --llm-model "your-model"

# Terminal 2: Gateway (TypeScript)
cd agent-kernel/apps/gateway
npm run start

# Terminal 3: Request Manager (TypeScript)
cd agent-kernel/apps/request-manager
npm run start
```

### 测试 API

```bash
# 发送聊天请求
curl -X POST http://localhost:3000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "sessionId": "test-session",
    "userId": "test-user",
    "message": "你好！"
  }'

# 响应示例：
# {
#   "requestId": "xxx",
#   "status": "accepted",
#   "message": "Request accepted"
# }

# 查看响应结果
cat agent-kernel/apps/gateway/data/storage/outbox/$(date +%Y-%m-%d)/xxx.json
```

## 项目结构

```
ProClaw/
├── kernel-v2/                    # Rust Kernel (核心)
│   ├── src/
│   │   ├── personality/          # Prime Personality
│   │   │   ├── prime.rs          # IR 生成
│   │   │   ├── models.rs         # IR 结构定义
│   │   │   └── config.rs         # 系统 Prompt
│   │   ├── skills/               # Skills 实现
│   │   │   ├── gateway_skill.rs  # Gateway Skill
│   │   │   ├── composer_skill.rs # Block Composer
│   │   │   └── bash_skill.rs     # Bash 执行
│   │   ├── server/               # gRPC 服务
│   │   │   ├── prime_personality_server.rs
│   │   │   └── agent_kernel.rs
│   │   └── coordinator/          # 执行协调器
│   ├── proto/                    # Protocol Buffers
│   └── config/                   # 配置文件
│
├── agent-kernel/
│   ├── apps/
│   │   ├── gateway/              # NestJS 网关
│   │   │   ├── src/gateway/      # Webhook 控制器
│   │   │   └── data/storage/     # 文件系统邮箱
│   │   └── request-manager/      # gRPC 请求管理
│   │       ├── src/services/     # Worker Pool
│   │       └── src/grpc/         # Prime gRPC 客户端
│   └── packages/
│       └── shared-schema/        # 共享类型
│
├── deprecated/                   # 已弃用组件
│   └── python-kernel/            # Python 实现（已迁移到 Rust）
│
├── proclaw.sh                    # 统一启动脚本
└── README.md                     # 本文件
```

## 核心组件

### 1. Prime Personality (Rust)

主人格层，负责将用户请求转换为结构化中间表示 (IR)：

- **意图分类**: conversation, file_operation, code_generation, analysis
- **任务分解**: 复杂任务拆分为可执行流程
- **IR 生成**: 包含 `content.text` 的结构化响应
- **gRPC 服务**: 端口 50051，接收 Request Manager 请求

**IR 结构示例**:
```json
{
  "intent": "conversation",
  "goals": ["Respond to user greeting"],
  "processes": [...],
  "content": {
    "text": "你好！很高兴见到你。有什么我可以帮助你的吗？"
  }
}
```

### 2. Gateway Skill

Gateway Skill 负责将 Prime 生成的 IR 回传到 Gateway：

- **HTTP POST**: `POST /gateway/webhook/kernel-response`
- **身份验证**: Bearer Token
- **响应格式**: 提取 `content.text` 作为 `body` 字段
- **超时**: 5 秒

**数据流**: Prime → Gateway Skill → Gateway Webhook → Outbox

### 3. Request Manager

请求管理器负责任务调度和队列管理：

- **Priority Queue**: P0-P4 优先级队列
- **Worker Pool**: 最大 5 个并发任务
- **Session Affinity**: 同一会话任务串行执行
- **gRPC 客户端**: 调用 Prime Personality (端口 50051)

### 4. Gateway

基于文件系统邮箱的轻量级网关：

- **HTTP API**: RESTful 端点 `/api/v1/chat`
- **Webhook**: 接收 Kernel 回调 `/gateway/webhook/kernel-response`
- **文件系统邮箱**: Inbox → Processing → Outbox
- **响应格式**: JSON，包含 `body` 字段（即 `content.text`）

## 配置

### 环境变量

**Rust Kernel**:
- `DATA_PATH` - 数据存储路径（默认：./data）
- `OPENAI_API_KEY` / `ARK_API_KEY` - LLM API 密钥
- `RUST_LOG` - 日志级别（默认：info）

**Gateway**:
- `GATEWAY_STORAGE_PATH` - 文件系统邮箱基础路径
- `PORT` - HTTP 端口（默认：3000）

**Request Manager**:
- `PRIME_PERSONALITY_HOST` - Prime 地址（默认：localhost:50051）
- `PORT` - gRPC 端口（默认：50052）

**LLM 配置** (kernel-v2/config/composer.yaml):
```yaml
llm:
  api_key: "your-api-key"
  base_url: "https://api.example.com/v1"
  model: "your-model"
```

## 开发指南

### 构建 Rust Kernel

```bash
cd kernel-v2

# 开发模式 (Data Plane only)
cargo build
cargo test

# 生产模式 (含 Control Plane)
cargo build --release --features control-plane
cargo test --features control-plane

# 代码检查
cargo check
cargo clippy -- -D warnings
cargo fmt
```

### 构建 TypeScript 组件

```bash
cd agent-kernel

# 构建所有包
npm run build

# 代码检查
npm run lint
npm run typecheck
```

### 运行测试

```bash
# 1. 启动服务
./proclaw.sh start

# 2. 发送测试请求
./proclaw.sh test

# 3. 检查响应
cat agent-kernel/apps/gateway/data/storage/outbox/$(date +%Y-%m-%d)/*.json
```

## 架构文档

- [架构规范](./schema/agent_kernel_architecture_spec_restructured.md) - 完整架构定义
- [AGENTS.md](./AGENTS.md) - Agent 开发指南
- [Control Plane 概念](./kernel-v2/CONTROL_PLANE_CONCEPT.md) - 控制面设计
- [API 状态](./kernel-v2/API_STATUS.md) - gRPC API 文档
- [E2E 测试计划](./kernel-v2/E2E_TEST_PLAN.md) - 端到端测试

## 设计原则

1. **无聊天记录膨胀** —— 使用 Event Log + Working Set，而非增长的聊天上下文
2. **规则驱动视图** —— Working Set Builder 使用规则而非 LLM 构造提示视图
3. **Control/Data Plane 分离** —— 基于权限等级的安全架构
4. **系统元数据不经过 LLM** —— `request_id` 等由规则生成
5. **gRPC 全链路** —— Gateway → Request Manager → Prime 全 gRPC 通信

## 路线图

- [x] Gateway + Request Manager 基础架构
- [x] **Rust Kernel v2** - Prime Personality + Skills
- [x] **Gateway Skill** - HTTP 回传结果
- [x] **IR content.text** - 结构化响应格式
- [x] **gRPC 通信** - TypeScript ↔ Rust 全链路
- [x] 端到端集成测试
- [ ] 长期记忆检索与利用
- [ ] 多智能体协作能力
- [ ] 可视化监控仪表板

## 迁移说明

### Python Kernel → Rust Kernel

Python Kernel 已迁移至 `deprecated/python-kernel/`，新系统使用 Rust 实现：

| 功能 | Python (旧) | Rust (新) |
|------|-------------|-----------|
| Prime Personality | Python FastAPI | Rust tonic |
| IR 生成 | Pydantic 模型 | Serde 结构体 |
| 通信 | HTTP REST | gRPC |
| 性能 | 解释型 | 编译型，更高性能 |

**迁移原因**:
- 更好的类型安全（Rust 所有权系统）
- 更高的性能（编译型语言）
- 更强的并发能力（tokio 异步运行时）
- gRPC 原生支持（tonic）

## 贡献

我们欢迎贡献！请查看我们的 [贡献指南](./CONTRIBUTING.md) 了解详情。

## 许可证

[MIT](LICENSE) © Agent Kernel Contributors

---

**状态**: ✅ 核心功能完整实现。Rust Kernel v2 已上线，支持 IR content.text 格式和 gRPC 全链路通信。
