# Agent Kernel

[![Tests](https://img.shields.io/badge/tests-117%2F117%20passing-success)](./agent-kernel/FULL_TEST_REPORT.md)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![TypeScript](https://img.shields.io/badge/typescript-5.0%2B-blue)](https://www.typescriptlang.org/)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)

> **长期运行的信息流内核** —— 不是"一个大智能体"，而是一个智能体编排与上下文治理系统。

Agent Kernel 是一个多层级智能体原语编排系统，专注于上下文编译、请求治理、运行时快照和持久化记忆。系统将 LLM 视为可替换的插件，而非系统本身。

## 核心特性

- **7层宏观架构** —— 从外部访问到内存支持的分层设计
- **Event Log + Working Set** —— 替代传统聊天记录的上下文管理模型
- **SEE-ACT-UPDATE 执行循环** —— 标准化的智能体执行模式
- **上下文编译器** —— 高级智能体，负责构建和优化上下文视图
- **原子智能体线程** —— 无上下文重新编辑的基础执行单元
- **双对象家族** —— 认知层（Agent Primitives）与执行层（Infrastructure）分离

## 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                    7 Macro Layers                           │
├─────────────────────────────────────────────────────────────┤
│ 1. External Access Layer    │ Gateway (NestJS)              │
│ 2. Request Source Layer     │ Queue Manager, Scheduler      │
│ 3. Personality Entry Layer  │ Prime Personality             │
│ 4. System Interface Layer   │ Agentic OS Interface Skill    │
│ 5. Session Orchestration    │ Session Host, Context Compilers│
│ 6. Task Execution Layer     │ Agent Thread, Executor        │
│ 7. Memory & Capability      │ Memory Base, SKILL Library    │
└─────────────────────────────────────────────────────────────┘
```

### 关键概念

**Compiled Context**: 由上下文编译器生成的输入视图，非完整真相  
**Runtime Working Context**: 通过 Event Log + Working Set 维护的有限工作上下文  
**SEE-ACT-UPDATE Loop**:
- **SEE**: 读取观察/工具结果/环境反馈
- **ACT**: 生成能力请求或结构化动作意图
- **UPDATE**: 写入 Event Log/Artifact Slots，重建 Working Set

## 实现状态

| 组件 | 状态 | 说明 |
|------|------|------|
| Gateway | ✅ 完整 | NestJS 网关，支持文件系统邮箱 |
| Request Manager | ✅ 完整 | gRPC 请求队列管理 |
| Scheduler | ✅ 完整 | 智能体线程调度基础设施 |
| Atomic Agent Thread | ✅ 完整 | Event Log + Working Set 架构 |
| Context Compilers | ✅ 完整 | Master/Process/Compiler Agent |
| Prime Personality | 🔄 占位 | 基础 mock 实现，需完善 |
| Session Host | 🔄 占位 | 基础实现，需完善 |
| Memory Base | ⏳ 未实现 | 长期记忆层（架构已定） |
| Multi-Agent Collaboration | ⏳ 未实现 | 多智能体协作（未来增强） |

**测试状态**: ✅ 117/117 测试通过 (100%)

## 快速开始

### 环境要求

- Node.js 18+
- Python 3.10+
- pnpm/npm
- SQLite (可选)

### 安装依赖

```bash
# TypeScript/JavaScript 依赖
cd agent-kernel
npm install

# Python 依赖
cd apps/python-kernel
pip install -e ".[dev]"
```

### 启动服务

```bash
# 开发模式启动所有服务
cd agent-kernel && npm run dev

# 或分别启动：
# Terminal 1: Gateway
cd agent-kernel/apps/gateway && npm run dev

# Terminal 2: Python Kernel
cd agent-kernel/apps/python-kernel && python main.py
```

### 运行测试

```bash
# 完整集成测试（推荐）
cd agent-kernel
npm run test:integration

# 验证历史记录
npm run test:history

# Python 测试
cd agent-kernel/apps/python-kernel
python -m pytest tests/ -v
```

## 项目结构

```
agent-kernel/
├── apps/
│   ├── gateway/              # NestJS 网关（外部访问层）
│   ├── request-manager/      # gRPC 请求管理器
│   └── python-kernel/        # Python 智能核心
│       ├── agent_thread/     # 原子智能体线程
│       ├── context_compiler/ # 上下文编译器
│       ├── prime/            # Prime Personality
│       └── session/          # Session Host
├── packages/
│   ├── shared-schema/        # TypeScript 共享类型
│   ├── skill-protocol/       # MCP 技能协议
│   └── observability/        # 可观测性工具
├── skills/local/             # 本地 MCP 技能
├── tests/                    # Python 集成测试
└── scripts/                  # 自动化脚本
```

## 核心组件

### 1. Atomic Agent Thread

基础执行单元，采用 Event Log + Working Set 架构：

- **Event Log Manager**: 完整事件流追踪
- **Working Set Builder**: 规则驱动的上下文构造器（YAML 可配置）
- **Agent Output Parser**: 结构化意图解析（JSON/YAML/启发式）
- **SEE-ACT-UPDATE 执行循环**

### 2. Context Compilers

上下文编译是系统的核心能力：

- **Master Compiler**: Prime Scope 上下文管理
- **Process Compiler**: Session Scope 上下文编译
- **Compiler Agent**: 带探索能力的高级编译器
- **Compilation Auditor**: 质量保证与验证

### 3. Gateway

基于文件系统邮箱的轻量级网关：

- HTTP API 端点
- 异步请求处理
- 文件系统邮箱集成
- OpenTelemetry 可观测性

## 配置

### 环境变量

**Gateway**:
- `GATEWAY_STORAGE_PATH` - 文件系统邮箱基础路径（默认：/var/gateway）
- `PORT` - 网关 HTTP 端口（默认：3000）
- `PYTHON_KERNEL_URL` - Python Kernel 端点（默认：http://localhost:8000）

**Python Kernel**:
- `PORT` - Kernel HTTP 端口（默认：8000）
- `KERNEL_RUN_MODE` - 执行模式：`real`（调用真实 LLM）或 `mock`（返回 mock 响应）
- `DATA_PATH` - 运行时数据存储路径（默认：./data）
- `STORAGE_TYPE` - 后端类型：`file` 或 `sqlite`（默认：file）

**LLM 配置**:
- `LLM_PROVIDER` - LLM 提供商：`ark`、`openai`、`custom`
- `ARK_API_KEY` - 火山引擎 Ark API 密钥
- `OPENAI_API_KEY` - OpenAI API 密钥
- `LLM_TEMPERATURE` - 生成温度（默认：0.7）
- `LLM_MAX_TOKENS` - 最大 token 数（默认：4000）

## 开发指南

### 构建

```bash
# 构建所有包
cd agent-kernel && npm run build

# 构建特定应用
cd agent-kernel/apps/gateway && npm run build
```

### 代码检查

**TypeScript/JavaScript**:
```bash
npm run lint
npm run typecheck
npm run format
```

**Python**:
```bash
cd agent-kernel/apps/python-kernel
black .                    # 格式化
ruff check . --fix         # 检查
mypy .                     # 类型检查
```

### 架构文档

- [架构规范](./schema/agent_kernel_architecture_spec_restructured.md) - 完整架构定义
- [架构变更摘要](./schema/agent_kernel_architecture_changes_summary.md) - 变更记录
- [Atomic Agent 实现](./agent-kernel/apps/python-kernel/ATOMIC_AGENT_IMPLEMENTATION.md) - 实现详情
- [集成测试报告](./agent-kernel/FULL_TEST_REPORT.md) - 完整测试报告

## 设计原则

1. **无聊天记录膨胀** —— 使用 Event Log + Working Set，而非增长的聊天上下文
2. **规则驱动视图** —— Working Set Builder 使用规则而非 LLM 构造提示视图
3. **原子与高级智能体分离** —— Agent Thread 是原子（无上下文重新编辑）；Context Compilers 是高级
4. **探索/执行作为阶段** —— 相同的 Agent Thread 模板，不同的阶段配置
5. **A2A 非必需** —— 单线程 MVP 优先；多智能体协作是未来增强

## 路线图

- [x] Gateway + Request Manager 基础架构
- [x] Python Kernel 骨架
- [x] Atomic Agent Thread 完整实现
- [x] Context Compilers 完整实现
- [x] 全要素流程测试
- [ ] Prime Personality 完整实现
- [ ] Session Host 完整实现
- [ ] Memory Base 长期记忆层
- [ ] 多智能体协作能力
- [ ] 可视化监控仪表板

## 贡献

我们欢迎贡献！请查看我们的 [贡献指南](./CONTRIBUTING.md) 了解详情。

## 许可证

[MIT](LICENSE) © Agent Kernel Contributors

---

**注意**: 当前 Prime Personality 和 Session Host 仍为 PLACEHOLDER 实现，需根据架构文档完善。Context Compilers 和 Atomic Agent Thread 已实现完整功能（测试覆盖率 100%）。
