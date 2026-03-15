# Agent Kernel 技术选型方案（MVP / 1个月 / 单人开发版）

## 0. 文档定位

本文档用于给当前的 Agent Kernel 项目直接提供一套 **可在 1 个月内落地、适合单人开发、对 LLM / vibecoding 友好、同时保留未来扩展空间** 的技术栈方案。

该方案基于你当前的 Kernel 架构定义：系统核心是长期运行的信息流内核，而不是单个“大 Agent”；`Prime Personality`、`Session Host`、`Context Compiler`、`Agent 线程`属于 `Agent Primitive` 家族，网关、请求队列、执行器、运行态上下文管理等属于基础设施家族。该边界来自当前架构 spec，而不是临时拍脑袋的工程拆分。fileciteturn0file0

本文**不讨论长期记忆内部实现**，只讨论：

- 各模块使用什么语言
- 各模块推荐什么框架/协议
- 为什么这样选
- 哪些技术暂时不要碰
- 如何按这套技术栈搭项目脚手架

---

## 1. 最终建议：采用“TypeScript 控制面 + Python 智能面”的双语言栈

如果你的目标是：

- 单人开发
- 1 个月做出可运行内核
- 需要大量借助 LLM 写代码和补代码
- 尽量降低工程阻力
- 还希望保留多语言能力

那么当前阶段**不建议把 Rust 作为主内核语言**。

Rust 当然更适合长期做高可靠 kernel，但对单人、短周期、vibecoding 场景并不友好。相反，**TypeScript 和 Python 都有更强的 LLM 代码生成友好度、更低的冷启动成本、更成熟的 AI 工程生态**。这是工程判断；同时从框架能力上看，NestJS 原生就是一个面向高结构化后端的 TypeScript 框架，而 FastAPI 则提供了基于 type hints 的 API 开发、自动文档和异步支持，适合把智能层和控制层快速落地。citeturn1search0turn0search0turn0search4turn0search12

因此，本方案的核心结论是：

- **控制面 / 基础设施面：TypeScript（Node.js）**
- **Agent / Context Compiler / Tool 编排面：Python**
- **能力接入协议：MCP**
- **事件总线：NATS（MVP 可先不引入 JetStream）**
- **运行态存储：SQLite**
- **可观测性：OpenTelemetry**

MCP 目前的标准传输就是 `stdio` 与 `Streamable HTTP`，而且协议层使用 JSON-RPC，这非常适合你做“本地 skill + 远程 skill”的统一能力边界。citeturn0search1turn0search5

---

## 2. 为什么不是 Rust-first

不是因为 Rust 不好，而是因为你当前阶段的优化目标不是“最终形态最优”，而是：

- 最短时间跑通完整信息流
- 尽量让 LLM 能稳定补全代码
- 保持后续可替换性

在这个约束下，Rust 的主要问题不是性能，而是：

- LLM 对复杂 Rust 生命周期、trait、异步边界的补全质量通常不如 TS/Python 稳定
- 你现在最需要的是快速把 Session / Router / Executor / Compiler / Gateway 这一整条链路先打通
- 当前架构中复杂点主要是“抽象边界”和“信息流治理”，还不是“极限性能”

所以这里的技术判断是：

**先用 LLM 更容易稳定产出的语言，把 kernel 的边界、协议、模块划分做对；之后如有必要，再把最底层热点模块替换成 Rust。**

这并不违背原 spec，因为 spec 固定的是宏观架构和对象边界，不是实现语言。fileciteturn0file0

---

## 3. 推荐总技术栈（MVP 版）

### 3.1 总表

| 层级 / 模块 | 推荐语言 | 推荐框架 / 组件 | 是否 MVP 必需 | 备注 |
|---|---|---|---|---|
| 对外网关 Gateway | TypeScript | NestJS | 是 | 结构清晰，适合控制面 |
| 请求队列管理器 | TypeScript | NestJS + 内存队列 / NATS | 是 | MVP 先内存队列，后接 NATS |
| 定时请求调度器 | TypeScript | NestJS Schedule | 是 | 做“给主人格未来自己的留言” |
| Prime Personality | Python | PydanticAI | 是 | 做人格级 Agent Primitive |
| 主 Context Compiler | Python | PydanticAI + 自定义编译逻辑 | 是 | 入口上下文收敛 |
| Info Router | TypeScript 或 Python | 首选 TypeScript（NestJS service） | 是 | 更像控制面 skill |
| Session Host | Python | PydanticAI / 普通 service 对象 | 是 | Session 级 Agent / 容器 |
| 进程 Context Compiler | Python | PydanticAI + 自定义编译逻辑 | 是 | Task 上下文包生成 |
| Agent 线程调度器 | Python | asyncio | 是 | 先不要过度工程化 |
| Agent 线程 | Python | PydanticAI Agent | 是 | 执行级 Agent Primitive |
| Request Executor / Coordinator | TypeScript | NestJS service + MCP client | 是 | 统一执行入口 |
| Thread Context / Runtime Memory Manager | Python | SQLite + 本地 snapshot 管理 | 是 | 先只做运行态，不碰长期记忆 |
| Skill 接入层 | 多语言 | MCP (`stdio` / Streamable HTTP) | 是 | 本地和远程统一 |
| 事件总线 | - | NATS | 否（建议第 2 阶段） | 先跑通再加 |
| 可靠消息层 | - | JetStream | 否 | 第 2 阶段再上 |
| 热缓存 | - | Redis | 否 | MVP 不建议先加 |
| 运行态存储 | - | SQLite (WAL) | 是 | 单机最合适 |
| 可观测性 | - | OpenTelemetry | 是 | 至少 traces + logs |
| API 文档 | TypeScript/Python | OpenAPI 自动生成 | 是 | Nest/FastAPI 都支持 |

---

## 4. 分模块选型说明

### 4.1 对外网关（Gateway）

**推荐：TypeScript + NestJS**

原因：

1. 这是标准控制面 / 接入层服务，TypeScript 比 Python 更适合做长期可维护的接口编排。
2. NestJS 本身就是面向结构化 Node.js 服务的框架，模块化、依赖注入和 controller/service 分层都比较适合你这种 kernel 型项目。citeturn1search0turn1search8
3. 这一层未来大概率要接 Discord、Telegram、CLI、Web UI 等多入口。Node 生态在这种“胶水层”上会更顺手。

职责建议：

- 接收外部消息
- 统一收敛成内部 JSON 中间表示
- 调用请求队列管理器
- 接收最终回复并编译为平台输出

不建议：

- 在网关层写复杂 Agent 逻辑
- 在网关层做真正的上下文编译
- 在网关层直接耦合模型 SDK

---

### 4.2 请求队列管理器

**推荐：TypeScript + NestJS service**

MVP 阶段建议先做成：

- 单进程内队列
- 按 session/user/request source 串行化
- 支持 future scheduled requests

第 2 阶段再接 NATS。

原因：

- 你现在最重要的是先验证“所有自然语言请求必须先进入请求源层再串行送入 `Prime Personality`”这条架构约束，而不是先把消息系统搞复杂。这个约束本身来自你的 spec。fileciteturn0file0
- 如果一开始就引入 broker，你会把时间消耗在运维和调试上，而不是 Kernel 行为本身。

---

### 4.3 定时请求调度器

**推荐：TypeScript + NestJS Schedule**

原因：

- 这个组件本质是“未来请求注入器”，是控制面的一部分，不需要模型智能。
- 它和请求队列管理器、Hook 权限层关系更近，更适合放在 TypeScript 控制面。

建议能力：

- 注册未来请求
- 查看未来请求
- 触发时回注到请求队列
- 区分用户创建 / 高权限 Hook 创建

---

### 4.4 Prime Personality

**推荐：Python + PydanticAI**

理由很直接：你这里需要的是一个**适合 Agent Primitive 抽象、支持 tool、结构化输出、流式运行、MCP、未来还能上 durable execution 的 Python agent 框架**。PydanticAI 现在明确支持 tools、structured outputs、MCP，以及 durable execution 路径。citeturn1search1turn1search9turn1search13

同时，PydanticAI 也是 model-agnostic 的，内建支持多个 provider，这和你在 spec 里定义的“LLM 是可替换插件，不是系统本体”是吻合的。citeturn1search17 fileciteturn0file0

这里不建议一开始用 LangGraph 做主人格层，原因是：

- 你现在的系统不是“把一个 agent graph 跑起来”这么简单
- 你更需要清楚地区分人格层、编译器层、Session 层、执行层
- PydanticAI 更适合作为底层 agent primitive 运行框架，而不是替你定义整个系统图

---

### 4.5 主 Context Compiler

**推荐：Python + 自定义编译器逻辑 + PydanticAI 辅助**

这里要刻意强调：

`Context Compiler` 不应该被实现成“另一个普通聊天 agent”，而应该是：

- 以代码规则为主
- 以模型辅助筛选/压缩/重组为辅
- 输出明确结构化的 `Compiled Context`

建议做法：

- 主体逻辑用 Python 函数 / class 写死
- 只在需要摘要、筛选、重写时调用 PydanticAI agent
- 输出 JSON schema 固定化

这样做的好处是：

- 更可控
- 更容易测试
- 更适合 vibecoding
- 不会把所有逻辑都变成 prompt 黑箱

这也更符合你的 spec：系统通过上下文治理使用模型智能，而不是把控制权整体交给模型。fileciteturn0file0

---

### 4.6 Info Router

**推荐：TypeScript + NestJS service**

虽然从哲学上它可以被看作特殊 Skill / MCP，但从工程上看，它更像控制面里的一个系统服务：

- 决定请求去哪一个 Session
- 是否创建新 Session
- 是否复用已有上下文
- 是否只返回轻量响应

因此 MVP 阶段我建议把它实现成 **TypeScript 服务**，供 `Prime Personality` 通过 RPC / HTTP 调用，而不是一开始就强行做成纯 MCP server。

这样可以明显降低系统复杂度。

后续如果你要强调“所有能力统一抽象”，再把它 MCP 化。

---

### 4.7 Session Host

**推荐：Python + 普通 service 对象 / PydanticAI 包装**

Session Host 是 Session 级 Agent Primitive / Agent 容器。它既不是单纯数据类，也不应该一开始就搞成复杂 actor system。fileciteturn0file0

建议实现方式：

- 一个 Session Host = 一个 Python 对象
- 内含 session metadata、process registry、task registry、经验提升入口
- 对外暴露：`handle_request()`、`spawn_task()`、`submit_long_term_candidate()` 等方法

只有当某些高层判断确实需要模型参与时，才由 Session Host 内部调用 PydanticAI。

换句话说：

- `Session Host` 的**壳**是普通 Python service
- `Session Host` 的**局部高层判断**由 agent primitive 补充

这样更稳。

---

### 4.8 进程 Context Compiler

**推荐：Python + 自定义编译器逻辑 + PydanticAI 辅助**

和主 Context Compiler 同理，但作用域更小：

- 面向 Session / Task
- 组织执行上下文包
- 接技能定义、检索结果、运行态快照
- 输出给 Thread Context Manager / Agent Threads

建议输出结构：

- `task_goal`
- `constraints`
- `allowed_capabilities`
- `working_memory`
- `relevant_artifacts`
- `stop_conditions`

不要直接把一堆原始消息拼进去。

---

### 4.9 Agent 线程调度器

**推荐：Python + asyncio**

原因很简单：

- 你当前阶段不需要上 Ray、Celery、Temporal 这类重系统
- 执行级多 Agent 协作，先本地协程调度就够
- Python 的 `asyncio` 已经足够让你跑多工具调用、多线程式 agent 流程

这里不要过度工程化。真正需要 durable / distributed execution 时，再接更重的编排系统。

PydanticAI 后续可以接 Temporal / DBOS / Prefect 做 durable execution，但官方也明确把这些列为 durable 方案，而不是你必须一开始就用的默认前提。citeturn1search13turn1search5

---

### 4.10 Agent 线程

**推荐：Python + PydanticAI Agent**

这是最适合用 PydanticAI 的位置。

因为执行级 Agent 线程正是：

- 局部目标解释
- 局部决策
- tool / MCP request 生成
- 消费观察结果
- 输出结构化结果
- 在预算内迭代

这和你 spec 里对 Agent Primitive 的原子能力定义几乎一一对应。fileciteturn0file0

建议：

- 一个 agent thread 对应一个明确 role
- 每个 role 使用固定 output schema
- tool 权限由 capability boundary 严格约束

不要让执行级 agent 拿到系统所有能力。

---

### 4.11 Request Executor / Coordinator

**推荐：TypeScript + NestJS service + MCP client**

原因：

- 这是统一执行入口，天然偏基础设施而不是偏智能体
- 它要对接本地命令、MCP server、远程 service、系统接口
- TypeScript 在“多接口胶水层”这里很合适

MVP 能力建议：

- 接收标准化 tool request
- 根据 capability type 分派：local / mcp-stdio / mcp-http / internal service
- 返回统一 observation/result
- 做超时、取消、错误标准化

MCP 之所以适合这里，是因为它已经把客户端-服务端能力调用的消息形态和传输边界明确化了，且 `stdio` 与 `Streamable HTTP` 正好分别覆盖本地工具和远程服务场景。citeturn0search1turn0search5

---

### 4.12 Thread Context / Runtime Memory Manager

**推荐：Python + SQLite**

当前你明确说“不包括记忆，这是另一个非常复杂的项目”，那么这个模块就只做：

- Task 运行快照
- Thread 局部工作记忆
- 运行中 observation log
- 上下文压缩中间件
- 时间顺序归档

SQLite 很适合这个阶段。官方文档明确指出 WAL 模式通常更快，而且读写可并发进行：读不阻塞写，写不阻塞读。citeturn0search3

因此建议：

- 运行态 snapshot / metadata 全放 SQLite
- 启用 WAL
- 严格限制为**本机单实例访问**
- 不要拿 SQLite 当跨机器共享数据库

---

### 4.13 Skill / Tool 接入层

**推荐：统一使用 MCP**

这是整个项目里最值得统一的边界之一。

MCP 官方规范当前定义了 JSON-RPC 消息格式，并支持 `stdio` 与 `Streamable HTTP` 两种标准传输，其中客户端应尽可能支持 `stdio`。citeturn0search1turn0search5

建议具体策略：

- 本地脚本类 skill：MCP `stdio`
- 本机服务类 skill：MCP `Streamable HTTP`
- 远程服务类 skill：MCP `Streamable HTTP`
- 当前还不值得 MCP 化的内部控制面服务：先走内部 RPC / HTTP

这样做的意义是：

- 多语言天然成立
- skill 与 kernel 解耦
- 未来替换语言或模型时不伤主架构

---

## 5. 事件总线与队列：MVP 怎么做，二阶段怎么升级

### 5.1 MVP 阶段

**先不引入 broker，单进程内队列 + 本地调度即可。**

这是为了保证一个月内能完成，而不是为了否定消息系统价值。

你当前阶段的核心问题是：

- 路由是否正确
- Session 与 Task 边界是否正确
- Agent Primitive 权限边界是否正确
- Context Compiler 输出是否好用

这些都不依赖 broker 才能验证。

### 5.2 第二阶段

**引入 NATS**。

NATS Core 本身适合轻量 pub/sub 和 request-reply；官方文档明确指出 Core NATS 是 best-effort、at-most-once，而 JetStream 提供持久化与 at-least-once / exactly-once 语义。citeturn0search17turn0search2turn0search6

因此正确姿势是：

- 非关键瞬时事件：Core NATS
- 关键可恢复任务：JetStream

不要一开始全量上 JetStream，更不要为了“看起来高级”先把整个系统做成分布式消息迷宫。

---

## 6. Redis 要不要上

**MVP：不要上。**

理由：

1. 你已经有 SQLite 作为本地运行态存储。
2. 你当前没有真正的多节点横向扩展需求。
3. Redis Pub/Sub 是 at-most-once，丢了就是丢了，不适合承担关键执行链路。citeturn1search3
4. Redis Streams 虽然是 append-only log 风格，支持更强的消息处理模型，但那会把你的系统再多引入一层复杂度。citeturn1search7turn1search23

所以现阶段 Redis 只会增加复杂度，不会显著提高内核落地速度。

---

## 7. 可观测性

**推荐：OpenTelemetry，从第一天就接。**

OpenTelemetry 是 vendor-neutral 的 observability 框架，覆盖 traces、metrics、logs。citeturn1search2turn1search6turn1search14

你这个系统如果没有 trace，很快就会变成：

- 用户请求进来了
- 走了哪个 Session 不清楚
- 开了几个 Agent Thread 不清楚
- 为什么 toolcall 失败不清楚
- 哪一步 context 编译错了不清楚

所以 MVP 最低要求：

- 每个请求有 `request_id`
- 每个 session 有 `session_id`
- 每个 task 有 `task_id`
- Gateway → Personality → Router → SessionHost → Executor 整条链有 trace
- Executor 的每个 tool / MCP call 都要打 span

这不是“后期优化项”，而是让你能开发下去的前提。

---

## 8. 目录结构建议（按该技术栈创建脚手架）

建议采用 monorepo：

```text
agent-kernel/
├─ apps/
│  ├─ gateway/                 # NestJS: 对外网关、请求队列、定时调度、执行器 API
│  ├─ control-plane/           # 可选，后续做 web 管理面板
│  └─ python-kernel/           # Python: personality / session / compiler / threads
├─ packages/
│  ├─ shared-schema/           # TS/Python 共享 schema（JSON Schema / OpenAPI / protobuf 二选一）
│  ├─ skill-protocol/          # MCP capability 定义、工具结果标准结构
│  └─ observability/           # trace id、logger、telemetry 约定
├─ skills/
│  ├─ local/
│  │  ├─ fs-skill/
│  │  ├─ shell-skill/
│  │  └─ gateway-render-skill/
│  └─ remote/
├─ data/
│  ├─ runtime.sqlite3
│  └─ snapshots/
├─ docs/
│  ├─ architecture/
│  ├─ protocols/
│  └─ decisions/
├─ scripts/
│  ├─ dev/
│  └─ bootstrap/
├─ docker/
└─ README.md
```

Python kernel 内建议进一步拆：

```text
apps/python-kernel/
├─ personality/
├─ context_compiler/
├─ session_host/
├─ thread_runtime/
├─ agents/
├─ executors_client/
├─ schemas/
├─ storage/
└─ main.py
```

NestJS gateway 内建议拆：

```text
apps/gateway/
├─ src/
│  ├─ gateway/
│  ├─ request_queue/
│  ├─ scheduler/
│  ├─ executor/
│  ├─ router_api/
│  ├─ mcp/
│  ├─ telemetry/
│  └─ app.module.ts
```

---

## 9. 各语言职责边界（非常重要）

### TypeScript 负责什么

- 外部接入
- API / control plane
- 请求排队
- 调度
- 执行器
- 平台输出编译
- MCP client / adapter

### Python 负责什么

- Prime Personality
- Context Compiler
- Session Host
- Agent Threads
- 运行态上下文组织
- 快照压缩
- 结构化智能决策

### 多语言 Skill 负责什么

- 文件系统能力
- shell 能力
- 检索能力
- 第三方 API 能力
- 平台特化能力
- 特定领域工具

这个边界必须固定，否则项目会迅速塌成“所有东西都能写在任何地方”。

---

## 10. 当前不建议选的技术

### 10.1 Rust-first

原因：

- 对 1 个月单人 vibecoding 不友好
- 会把时间耗在类型系统和并发细节上
- 当前不是性能瓶颈期

### 10.2 LangChain / LangGraph 作为系统主内核

原因：

- 容易把你的 kernel 抽象退化成“agent workflow app”
- 你的系统边界比普通 graph agent 更复杂
- 你已经有自己的系统哲学和对象定义，不该反向迁就框架

### 10.3 Kafka / Pulsar / RabbitMQ 先上

原因：

- 都太重
- 不是你当前最核心的正确性来源
- 单人一个月会明显分散精力

### 10.4 Redis 作为关键消息总线

原因：

- Pub/Sub 是 at-most-once，不够稳。citeturn1search3
- Streams 虽然更强，但仍然会引入额外复杂度。citeturn1search7turn1search23

### 10.5 一开始就上 Temporal

原因：

- Durable execution 的确有价值，但不是 MVP 前置条件
- 你现在需要的是“先把语义闭环跑通”
- PydanticAI 后面已经预留了 durable 路径，不急于今天解决全部问题。citeturn1search13turn1search5

---

## 11. 推荐落地顺序（按周）

### Week 1

先搭三件事：

1. NestJS gateway
2. Python kernel skeleton
3. SQLite runtime store

跑通：

- 用户请求 -> 网关 -> Python Personality -> 简单回复 -> 网关输出

### Week 2

加入：

- 主 Context Compiler
- Info Router
- Session Host
- 单 Task 快照

跑通：

- 同一 session 的连续请求
- 路由到正确 Session
- 生成执行上下文包

### Week 3

加入：

- Agent 线程调度器
- Agent 线程
- Request Executor
- 本地 MCP skills

跑通：

- Agent thread 发 toolcall
- Executor 分派 skill
- observation 回流

### Week 4

加入：

- 定时请求调度器
- Hook 边界
- OpenTelemetry traces
- 错误恢复与日志统一

跑通：

- future request
- 可视化调试链路
- 至少 2~3 个完整 demo

---

## 12. 最终拍板版

如果你现在就要创建项目脚手架，我建议直接按下面这套来：

### 核心语言

- **TypeScript**：控制面 / 接入层 / 执行层基础设施
- **Python**：Agent Primitive / Context Compiler / Session Host / Thread Runtime

### 核心框架

- **NestJS**：Gateway、Queue、Scheduler、Executor API
- **PydanticAI**：Prime Personality、Context Compiler、Agent Threads
- **SQLite**：运行态 snapshot / metadata / observation log
- **MCP**：Skill / Tool 标准接入
- **OpenTelemetry**：trace / log / metrics 基座

### 第二阶段再加

- **NATS**：事件总线
- **JetStream**：关键任务持久化
- **Redis**：必要时做缓存，不做主消息链
- **Temporal / DBOS / Prefect**：需要 durable execution 时再引入

---

## 13. 一句话总结

**这套项目当前最合适的不是“Rust 写一个漂亮内核”，而是“用 TypeScript + Python 先把你定义好的 Kernel 哲学和模块边界跑通”，并通过 MCP、SQLite、OpenTelemetry 把系统做成可替换、可调试、可扩展的轻量 Agent Kernel。**

