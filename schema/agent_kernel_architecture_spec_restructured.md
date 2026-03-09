# Agent Kernel Architecture Spec（重构版）

## 0. 文档定位

本文档用于固定当前版本仍然成立的 **Agent Kernel 宏观架构、核心对象、信息流边界与关键哲学**。

它不是接口文档，也不是实现细节文档。当前阶段本文档 **不展开**：

- 具体 API / schema
- 存储引擎细节
- 传输协议细节
- UI 设计
- 长期记忆内部结构细拆
- 机器人导航方案与基座模型的具体选型

本文档的目标，是把系统的 **结构、层级、职责、作用域和稳定判断** 先钉死。

---

## 1. 系统定位

`Agent Kernel` 不是“一个大 Agent”，而是一个长期运行的信息流内核。

它负责组织：

- 多层级 `Agent Primitive`
- 上下文编译机制
- 请求治理与执行基础设施
- 运行态快照与持久化记忆
- 外部能力、工具与环境交互

当前内核 **不只面向纯软件 AgenticOS**，也面向正在开发中的 **机器人 embodied 控制系统**。

因此，这个内核从一开始就应被理解为一个 **跨数字环境与物理环境的统一编排内核**：

- 在纯软件场景中，它对接文件、工具、服务、系统接口。
- 在具身场景中，它对接导航、基座模型、感知/跟踪输入与低层控制模块。

二者共用同一套上层哲学：

**模型能力 × 信息流治理 × 受控能力边界**

---

## 2. 核心哲学

### 2.1 LLM 是可替换插件，不是系统本体

LLM 是可替换的认知插件，用于提供局部推理、解释和文本生成能力。

系统的连续性不依赖某个固定模型，而依赖：

- 信息流结构
- 上下文编译机制
- 长期记忆与知识沉淀
- 基础 Prompt / Rule Kernel

### 2.2 系统通过上下文治理使用模型智能

系统不会把全部控制权交给模型，而是通过上下文治理与能力边界，选择性调用模型的局部智能。

因此系统能力不是“模型自己变成了系统”，而是：

**模型能力 × 信息流治理**

### 2.3 人格不属于单一模型

人格连续性不来自某个模型本身，而来自：

- 相对稳定的基础 Prompt 核
- 长期记忆与偏好连续性
- 信息如何被筛选、编译、沉淀和再利用

### 2.4 `Prime Personality` 是跨 Session 的统一人格入口

`Prime Personality` 不是某个单独 Session 的子对象，而是跨 Session 的统一人格入口层。

它高于单个 Session，负责维持系统对外表现出的稳定身份、解释框架与基础行为风格。

### 2.5 Agent 是基础算子，不是系统视角下的完整智能主体

在本系统里，`Agent` 更接近一种基础算子（primitive operator），而不是系统视角下拥有完整智能的主体。

它知道的是：

- 自己当前要做什么
- 自己在当前约束下该怎么做
- 自己能调用哪些能力

它不知道的是：

- 整个系统的完整智能全貌
- 高层连续性本身
- 系统级身份的全部来源

因此，从系统视角看：

- Agent 的能力不来自它自身天然完整的“智能主体性”
- Agent 的能力主要依赖基础模型
- Agent 的表现取决于被喂入的上下文、规则核和权限边界

### 2.6 三类“上下文”必须严格区分

这是当前版本最重要的术语边界之一。

#### A. Compiled Context

由 `Context Compiler` 生成的、供某个 Agent Primitive 消费的 **编译后上下文视图**。

它是输入视图，不等于全部真相。

#### B. Runtime Working Context

执行线程在运行过程中维护的 **有界工作上下文**。

它服务于局部 SEE-ACT-UPDATE 闭环，通常由规则式构造器从：

- 初始输入
- 事件日志
- 中间产物
- 当前 phase / 状态位

投影出下一轮 prompt 视图。

它不是 `Context Compiler`，也不等于“上下文再生产”。

#### C. Long-term / Curated Memory

长期记忆、整理后的知识、偏好与可复用经验。

它主要由 `Memory Base` 承载，通常经由 `Context Compiler` 被选择性使用，而不是直接裸喂给执行层。

### 2.7 原子级 Agent 与高级 Agent 的关键分界

原子级 Agent 与高级 Agent 的关键区别，不在于是否“用了 LLM”，而在于：

**它是否引入同等级智能，通过 `Context Manager / Context Compiler` 对自身可用 Context / Memory 进行再编辑。**

也就是说：

- 原子级 Agent 可以有局部循环，可以消费 observation，也可以维护规则驱动的运行态工作上下文。
- 只有当它开始参与对自身可用上下文或记忆的语义级筛选、压缩、补充和重组时，它才越过了原子级边界。

因此：

- **规则驱动的运行态 working set 更新** 不等于高级 Agent。
- **借助同等级智能进行上下文再编辑** 才是高级 Agent 的关键标志。

### 2.8 图中的 `*N` 对象是平等展开

图中未完整展开的 `*N` 对象与完整画出的对象是平等的，不是从属特例。

---

## 3. 宏观层次

当前内核可分为七个宏观层：

1. 外部接入层
2. 请求源层
3. 人格入口层
4. 特权系统接口 / 路由层
5. Session 编排层
6. Task 执行层
7. 记忆与能力支撑层

其中：

- 纯软件能力主要落在执行层与能力支撑层。
- 具身控制能力同样通过执行层和能力支撑层接入，只是能力边界更强、实时约束更高。

---

## 4. 对象家族与统一抽象

### 4.1 两大家族

系统中的对象建议明确划分为两类：

#### A. Agent Primitive 家族

负责解释、判断、生成行为意图和结构化结果。

包括：

- `Prime Personality`
- `Prime Context Compiler`
- `Session Host`
- `Process Context Compiler`
- `Agent Thread`

#### B. Infrastructure 家族

负责队列、执行、存储、接入、运行态快照、外部能力承接与记忆底座。

包括：

- `Gateway`
- `Request Queue Manager`
- `Scheduled Request Dispatcher`
- `Request Executor / Coordinator`
- `Thread Context / Runtime Memory Manager`
- `Memory Base`
- `SKILL lib`

### 4.2 `Agent Primitive` 的统一定义

`Agent Primitive` 是本系统中的统一行为载体，也是 Kernel 的基础算子。

它不是系统本体，也不是长期连续性本身，而是：

**在给定规则核、局部上下文和权限边界下，调用基础模型完成解释、决策、能力请求与结构化结果生成的主动执行单元。**

一个 Agent Primitive 至少由以下六个要素共同定义：

1. `Model Substrate`
2. `Rule Kernel`
3. `Compiled Context`
4. `Capability Boundary`
5. `Scope & Privilege`
6. `Lifecycle Envelope`

### 4.3 Agent Primitive 的四种层级形态

当前版本至少存在四种层级形态：

1. **人格级 Agent Primitive**
   - 对应 `Prime Personality`
   - 负责统一对外解释与表达

2. **Session 级 Agent Primitive**
   - 对应 `Session Host`
   - 负责 Session 范围内的局部治理

3. **编译器型 Agent Primitive**
   - 对应 `Prime Context Compiler` 与 `Process Context Compiler`
   - 负责上下文筛选、收敛、压缩与组织

4. **执行级 Agent Primitive**
   - 对应 `Agent Thread`
   - 负责具体子任务执行、toolcall 生成与局部闭环

### 4.4 分级：原子级与高级 Agent

#### 原子级 Agent Primitive

原子级 Agent Primitive：

- 不主动编辑自身长期记忆结构
- 不主动通过同等级智能重组自身可用上下文体系
- 主要在既定上下文中完成局部任务求解
- 可以维护规则驱动的工作集与局部状态

#### 高级 Agent Primitive

高级 Agent Primitive：

- 会借助 `Context Manager / Context Compiler` 参与上下文再组织
- 会通过上下文管理机制影响自身后续可见信息
- 会参与上下文筛选、压缩、补充和重组

当前版本中：

- `Prime Personality`、`Prime Context Compiler`、`Session Host`、`Process Context Compiler` 都属于高级 Agent Primitive
- `Agent Thread` 默认属于 **执行级原子 Agent Primitive**

但要注意：

**`Agent Thread` 的“原子性”并不意味着它不能有反馈循环；它只是不能演化成一个会语义性改写自身上下文的微型高级 Agent。**

---

## 5. 作用域与状态单元

这是当前架构最重要的作用域层次：

### 5.1 Prime / Global Scope

跨 Session 的统一人格入口与全局系统视角。

### 5.2 Session Scope

单个 Session 的长期局部主体范围。

### 5.3 Process Scope

某个 Session 内并存的一组局部过程对象。

### 5.4 Task Snapshot Scope

真正被执行的不是整个 Session，而是某个 Task 的运行快照。

它是：

- Session 状态的局部可执行投影
- Task 状态的运行态视图
- 多线程 / 多步执行的局部沙箱

### 5.5 Agent Thread Scope

最小执行单元的局部闭环范围。

---

## 6. 关键对象

### 6.1 Gateway

`Gateway` 承接外部聊天软件、应用接口或其他接入面，例如 Web、Discord、Telegram、CLI 或机器人上层接入模块。

职责：

- 处理外部协议与消息收发
- 将外部输入收敛为内部统一中间表示
- 将系统内部中间表示编译为各平台或各终端所需的最终输出格式

平台差异应尽量停留在网关层，而不污染核心信息流。

### 6.2 内部中间表示

系统内部不围绕平台最终消息工作，而围绕统一的中间表示工作。

当前版本建议该表示保持轻量化，并优先使用 JSON 风格承载。

它主要承载：

- 主体文本
- 资源占位符 / 指示符
- 图片 / 文件 / 图表 / 传感或动作相关资源引用
- 少量结构化控制字段

### 6.3 Request Queue Manager

`Request Queue Manager` 是统一请求源层。

当前稳定约束是：

- **所有自然语言输入** 都必须先进入这里
- 再串行化后送入 `Prime Personality`
- 以避免多设备或多入口同时竞争人格入口层

它至少承接两类自然语言来源：

1. 用户请求
2. 定时请求调度器触发的预存请求

### 6.4 Scheduled Request Dispatcher

`Scheduled Request Dispatcher` 是基于规则触发的预存消息调度层。

它的本质更接近：

**主人格写给未来自己的留言系统。**

职责：

- 存放预先注册的请求或提醒
- 以定时、延迟、条件触发方式重新唤起这些请求
- 将触发后的请求以与普通用户输入等价的语义送入 `Request Queue Manager`

### 6.5 Hook 保护机制

未来请求队列的写入不应由普通执行进程随意完成。

其写入能力应通过高权限 Hook 受控暴露，用于：

- 审核哪些信息可以进入未来请求队列
- 阻止一般执行过程污染高价值未来信息
- 保证“给主人格未来自己的留言”属于高权限行为

### 6.6 Prime Personality

`Prime Personality` 是跨 Session 的统一人格入口层。

职责：

- 作为用户首先接触的外显人格壳层
- 承载基础 Prompt / Rule Kernel
- 提供系统级解释框架
- 维持跨 Session 的身份连续性
- 生成系统内部统一表达与中间表示

关键性质：

- `Prime Personality` 应视为 **stateless**
- 它不依赖自身保存长期运行态
- 每次最终送往用户的结果，都必须重新依赖 `Prime Context Compiler` 提供的上下文收敛结果

### 6.7 Prime Context Compiler（规则优先）

`Prime Context Compiler` 服务于 `Prime Personality`。

它是一个 **规则优先的特权编译器型 Agent Primitive**，不是普通聊天 Agent，也不应被实现为另一个重对话黑箱。

职责：

- 解释入口消息
- 维持主人格连续性
- 做入口级上下文收敛
- 将不同接入点的输入形式收敛为统一基础表达
- 仅向主人格暴露少量特权系统能力

当前建议的运行方式：

1. 第一轮上下文编译尽量完全规则化
2. 只有在必要时，才触发受限的 `Context Tool Call`
3. 该 tool call 只允许 **补丁式修改本轮 `Compiled Context`**
4. 它不应直接修改 Session 真相，不应直接写长期记忆，也不应绕开 `Session Host`

### 6.8 Agentic OS Interface Skill（原 Info Router）

`Agentic OS Interface Skill` 是一个 **Prime-scoped 的特权系统 Skill**。

它不是一个独立 Agent 节点，而是提供给主人格使用的系统级交互界面。

职责：

- 让 `Prime Personality` 与不同 `Session Host` 双向交换消息
- 读取或查询高层过程摘要与必要状态
- 决定请求应进入哪个 Session
- 判断应新建 Session、复用上下文，还是仅返回轻量响应
- 将请求送入正确的 `Session Host`

### 6.9 Session Host

`Session Host` 是单个 Session 的局部内核。

它既不是纯状态容器，也不是第二个人格，而是一个 **Session 级高级 Agent Primitive / Agent 容器**。

职责：

- 持有 Session 级状态
- 管理该 Session 内的请求、Process 与 Task 集合
- 调用 `Process Context Compiler`
- 汇聚执行结果
- 决定哪些经验具有长期意义
- 将长期经验候选提交给 `Memory Base`

### 6.10 Process Context Compiler

`Process Context Compiler` 服务于 `Session Host`。

职责：

- 面向具体 Session / Process / Task 组织执行上下文
- 调用长期记忆、技能定义、检索结果与运行态快照
- 生成供执行层使用的上下文包

`Prime Context Compiler` 与 `Process Context Compiler` 本质上是 **同一类组件在不同作用域下的实例**。

### 6.11 Process

`Process` 表示 Session 内可并存的一组局部过程对象。

它们由 `Session Host` 管理，用于承载不同请求、不同阶段或不同任务线的状态与演化。

### 6.12 Task Snapshot

真正被执行的不是整个 Session，而是某个 `Task Snapshot`。

它是：

- Session 状态的局部可执行投影
- Task 的运行态视图
- 执行线程共享的受控局部沙箱

### 6.13 Request Executor / Coordinator

`Request Executor / Coordinator` 是 **跨 Session 的共享执行界面**，不是某个单独 Session 的私有对象。

职责：

- 接收上层 Agent 产生的 toolcall / 执行请求
- 协调局部消息流与能力调用
- 驱动一次请求在 `Task Snapshot` 中的实际执行
- 将局部执行结果回流到运行态
- 作为统一执行入口抑制竞争与冲突

在具身场景中，它同时是连接高层 Agent 与低层控制/导航/执行模块的统一入口。

### 6.14 Agent Thread Scheduler

`Agent Thread Scheduler` 负责在执行层内调度 `Agent Thread` 实例。

它承担线程级编排职责，但不承担人格级解释职责。

### 6.15 Agent Thread

`Agent Thread` 是 **执行级原子 Agent Primitive** 的通用模板实例。

它负责：

- 在给定上下文和规则下完成具体子工作
- 产生 toolcall / skill call / 执行请求
- 消费 observation 并推进局部闭环
- 输出结构化中间结果与最终结果

当前版本中，`Agent Thread` 的默认基线是：

- **单线程 / 单闭环可执行**
- **不依赖 A2A 才能成立**
- **可以通过 phase 切换覆盖“探索”和“执行”两类子任务**

也就是说，当前更推荐：

- 使用 **同一种线程模板**
- 通过不同 phase profile 覆盖不同子任务形态
- 而不是为“收集上下文”和“执行动作”再拆出新线程大类

### 6.16 Thread Context / Runtime Memory Manager

`Thread Context / Runtime Memory Manager` 是特殊的运行态上下文管理器。

职责：

- 管理 `Task Snapshot` 级别的运行态上下文、日志与局部快照
- 为各 `Agent Thread` 提供受控视图所需的底层材料
- 跟踪上下文在执行过程中的局部变化
- 隔离每个 Task 的全量运行信息
- 记录时间顺序上的 observation、事件与中间产物
- 为回放、诊断与后续检索提供依据
- 避免单次运行中的上下文漂移直接污染更高层 Session 结构

要特别强调：

**线程 prompt 的有界性，主要不依赖 `Session Host` 每轮重写上下文，而依赖线程内部 working set 机制。**

### 6.17 Memory Base

`Memory Base` 是统一记忆底座，不代表单一数据库。

它是一个宏观聚合层，内部可包含：

- 长期事实记忆
- 偏好与人格连续性记忆
- Session / workspace / global 分层记忆
- 项目知识与历史任务抽象
- 文档与笔记整理结果
- 实体、关系、主题、canon 等高阶知识
- 面向检索的各种索引视图

### 6.18 SKILL lib

`SKILL lib` 更接近应用层能力定义源，而不是普通函数库。

它提供：

- Prompt / Rule Kernel 来源
- 能力定义与 tool intents
- 行为规则来源
- 权限与能力边界
- 身份约束

---

## 7. Agent Thread 的内部执行模型

这是本轮重构中新增且最关键的部分。

### 7.1 设计目标

`Agent Thread` 不应维护一段不断膨胀的对话文本历史。

更优雅的方式是：

**把线程内部状态拆成“完整事件日志 + 固定大小 working set”。**

也就是说：

- 增长的是事件记录与结构化中间产物
- 不是直接喂给模型的 prompt 本体

### 7.2 内部结构

一个标准 `Agent Thread` 至少包含以下运行态对象：

#### A. Immutable Input Bundle

线程启动时给定，运行中不被自由改写：

- 上层指令
- 子任务目标
- 权限边界
- 初始 `Compiled Context`
- 停止条件
- 预算与 phase 初值

#### B. Event Log

SEE-ACT-UPDATE 闭环中的完整事件流水。

典型内容包括：

- capability request
- tool result
- 文件/资源读取结果
- action outcome
- error / blocker
- checkpoint

Event Log 默认 **完整保留**，但 **不直接等于 prompt**。

#### C. Artifact Slots

线程运行过程中产出的结构化中间结果槽位。

例如：

- `module_map`
- `symbol_index`
- `dependency_summary`
- `context_report`
- `patch_plan`
- `answer_draft`

它们的价值在于：

**用结构化产物替代大量自然语言历史。**

#### D. Working Set Builder

一个 **规则驱动的视图构造器**。

它从以下输入中，构造下一轮 prompt 所需的有限视图：

- `Immutable Input Bundle`
- `Event Log`
- `Artifact Slots`
- 当前 phase / state flags

它的职责不是“重新生产上下文哲学”，而是：

- 选取固定槽位
- 应用预定义优先级规则
- 构造下一轮有界 prompt view

#### E. Working Set / Prompt View

真正进入当前轮模型调用的上下文视图。

它应保持固定形状或至少固定上界，例如只包含：

- 当前目标
- 当前 phase
- 当前步骤
- 已确认事实
- 最近关键 observation
- 关键 artifact 摘要
- 上一步结果
- 待决问题

### 7.3 SEE-ACT-UPDATE 闭环

`Agent Thread` 的标准闭环是：

1. **SEE**
   - 读取 observation / tool result / 环境反馈
2. **ACT**
   - 产生下一步 capability request 或结构化动作意图
3. **UPDATE**
   - 将结果写入 `Event Log` / `Artifact Slots`
   - 再由 `Working Set Builder` 规则式构造下一轮 `Working Set`

### 7.4 为什么这仍然属于原子级 Agent

因为这里的 UPDATE 指的是：

- 规则驱动的运行态状态更新
- 有界 working set 重建
- 对事件与产物的槽位填充

而不是：

- 借助同等级智能对自身可用 Context / Memory 做语义级再编辑
- 主动重写长期记忆结构
- 自行扩展为一个微型高级编译器

因此：

**规则式 working set 更新 ≠ 上下文再生产。**

这正是当前版本保留 `Agent Thread` 原子分类的关键理由。

### 7.5 Explore / Execute 是 phase，不是两类线程

为了避免增加新的线程类别，当前建议把：

- 上下文收集
- 实际执行

统一收敛到同一种 `Agent Thread` 模板中，只通过 phase profile 区分：

#### Explore Phase

偏向：

- 搜集信息
- 读取资源
- 形成上下文产物
- 填充 `Artifact Slots`

#### Execute Phase

偏向：

- 基于已有 artifact 执行动作
- 生成修改、提交结果或完成响应

这样做的好处是：

- 线程模型保持单一
- 抽象层次不增加
- “收集上下文”和“执行动作”共享同一套原子闭环骨架

### 7.6 A2A 的当前定位

`Agent Thread` 未来可以具备 A2A 协作扩展，但它 **不是 MVP 的成立前提**。

当前更稳定的基线是：

- 单线程闭环先跑通
- phase-based 线程先跑稳
- A2A 作为后续可选增强，而不是当前架构基础

---

## 8. 核心信息流

### 8.1 自然语言主路径

自然语言请求的主路径为：

用户 / 外部触发
→ `Gateway`
→ 内部统一中间表示
→ `Request Queue Manager`
→ `Prime Personality`
→ `Prime Context Compiler`
→ `Agentic OS Interface Skill`
→ 选定 `Session Host`
→ `Process Context Compiler`
→ `Task Snapshot`
→ `Thread Context / Runtime Memory Manager`
→ `Agent Thread Scheduler`
→ `Agent Thread`
→ `Request Executor / Coordinator`
→ 外部能力 / 工具 / 环境
→ 结果回流到 `Session Host`
→ `Session Host` 选择性向 `Memory Base` 提交长期经验
→ `Prime Personality`
→ `Gateway`
→ 用户

### 8.2 结构化直达路径

除了自然语言路径外，系统还允许 **受控的结构化直达路径**。

其适用对象通常包括：

- 高权限系统请求
- 某些内部直接 toolcall
- 具身控制场景中的结构化控制输入

这类请求可以在满足权限边界的前提下：

- 直接进入某个特定 `Session Host`
- 或直接进入 `Request Executor / Coordinator`

但要注意：

- **自然语言请求仍然必须先经过 `Request Queue Manager` 与 `Prime Personality`**
- 只有已经结构化、且权限清晰的请求，才允许使用直达路径

### 8.3 知识沉淀路径

运行结果 / 中间结果
→ `Session Host` 判断其是否具有长期意义
→ 进入记忆与知识沉淀流程
→ 更新 `Memory Base`
→ 在后续的 `Context Compiler` 中再次被利用

---

## 9. 具身控制扩展（Embodied Extension）

这一部分是本轮重构新增的重要上下文。

### 9.1 具身控制不是独立架构，而是同一 Kernel 的能力扩展

当前内核并不只服务于纯软件 AgenticOS。

它也用于机器人 embodied 控制系统，只是把物理世界交互部分封装到更少、更硬边界的模块中。

也就是说：

- 对软件 Agent 来说，外部能力是文件、服务、工具、系统接口。
- 对具身 Agent 来说，外部能力是导航、追踪、运动控制、操作控制等模块。

二者都通过同一 Kernel 的执行入口与能力边界接入。

### 9.2 Embodied Session

当前建议把机器人高层任务接入为一个 **特殊的 Session 家族**。

这个 Session 可以接收两类输入：

1. 来自自然语言路径的高层任务
2. 受控的直接 toolcall / 结构化控制请求

这意味着：

- 自然语言仍可经由 `Prime Personality` 路由进入机器人相关 Session
- 某些上层系统也可以在权限允许时，直接向该 Session 或其执行链路发送结构化请求

### 9.3 物理交互模块的封装方式

当前设计中，物理交互部分应被封装为少量清晰模块，而不是把硬件细节直接暴露给高层 Agent。

高层 Kernel 关注的是：

- 语义解释
- 任务分解
- 模式切换
- 能力调用
- 结果整合

低层模块负责：

- 具体控制律
- 追踪闭环
- 导航执行
- 与实际机械体、传感器、执行器交互

### 9.4 Cerebellum（工作名）

当前具身方案中，可将低层动作控制抽象为一个工作名为 `Cerebellum` 的子系统。

它当前至少暴露两种模式：

#### A. 移动模式

以速度 / 角速度指令为主的控制接口。

#### B. 操作模式

以追踪输入为主的控制接口。

高层并不直接承担这些低层控制细节，而是通过受控能力边界调用它们。

### 9.5 上层导航与基座模型

在 `Cerebellum` 之上，还将接入：

- 导航能力
- 基座模型
- 面向机器人任务的高层规划或理解模块

当前阶段，这部分的具体实现仍取决于：

- 最终选择的基座模型
- 导航方案
- 感知与跟踪链路的具体拆分方式

因此，本文档只固定其 **架构位置与边界**，不固定具体技术选型。

### 9.6 具身能力的架构约束

当前建议对具身控制明确以下约束：

1. 物理世界能力必须通过更强的权限与安全边界暴露。
2. 高层 LLM/Agent 不应直接承担硬实时伺服闭环。
3. 低层控制与导航应封装为可调用模块，而不是被 prompt 直接替代。
4. 机器人相关 Session 仍然遵守 Kernel 的统一信息流，只是在能力边界和实时约束上更严格。

---

## 10. 两个核心闭环

### 10.1 生成执行闭环

请求源触发
→ 人格解释
→ 语义路由
→ Session 选定
→ 上下文编译
→ Task 执行
→ 结果回流
→ 对外输出

### 10.2 知识沉淀闭环

运行结果 / 中间结果
→ `Session Host` 判断是否具有长期意义
→ `Memory Base` 沉淀
→ 后续 `Context Compiler` 复用

在具身场景中，还可以把物理执行反馈理解为对生成执行闭环的环境侧补充，但其低层实时闭环并不由本文档展开。

---

## 11. 当前稳定锚点

以下判断视为当前版本最稳定的架构结论：

1. 系统不是“一个大 Agent”，而是一个长期运行的信息流内核。
2. 该内核同时适用于纯软件 AgenticOS 和 embodied 控制场景。
3. LLM 是可替换插件，不是系统本体。
4. 人格连续性来自信息流结构、长期记忆和 Prompt / Rule Kernel，而不是某个固定模型。
5. `Prime Personality` 是跨 Session 的统一人格入口，且本身应保持 stateless。
6. `Agent` 是统一行为载体与基础算子，而不是系统视角下的完整智能主体。
7. `Prime Context Compiler` 与 `Process Context Compiler` 是同一类组件在不同作用域下的实例。
8. `Prime Context Compiler` 是规则优先的特权编译器；默认先走规则路径，必要时才使用受限 context tool call 做补丁式上下文修正。
9. `Agentic OS Interface Skill` 是提供给主人格使用的特权系统 Skill，不是独立 Agent 节点。
10. `Session Host` 是 Session 级高级 Agent Primitive / Agent 容器，而不是单纯状态容器。
11. 所有自然语言输入都必须先进入 `Request Queue Manager`，再串行化送入 `Prime Personality`。
12. 受控的结构化请求可以走直达路径，但前提是权限清晰、语义已结构化。
13. 真正被执行的是 `Task Snapshot`，而不是整个 Session。
14. `Request Executor / Coordinator` 是跨 Session 的共享执行界面，不是某个 Session 的私有对象。
15. `Agent Thread` 默认是执行级原子 Agent Primitive。
16. `Agent Thread` 的成立不依赖 A2A；MVP 基线应先跑通单线程闭环。
17. `Agent Thread` 的内部状态应采用“完整事件日志 + 有界 working set”模型，而不是不断膨胀的对话文本。
18. `Working Set Builder` 属于规则驱动的运行态视图构造器，不等于上下文再生产，也不应被误认为线程内 `Context Compiler`。
19. 规则式 working set 更新不改变 `Agent Thread` 的原子级分类。
20. `Explore / Execute` 更适合作为同一线程模板的 phase，而不是再拆出新的线程大类。
21. `Thread Context / Runtime Memory Manager` 负责 `Task Snapshot` 级运行信息、事件日志与快照的隔离、回放与持久化支撑。
22. `Memory Base` 是统一记忆底座，不是单点实现。
23. `SKILL lib` 是能力、规则与身份边界的来源。
24. 具身控制应通过专门的 Session 与能力模块接入，而不是另起一套平行架构。
25. 物理交互应封装为少量清晰模块，低层实时控制不应由高层 LLM loop 直接承担。
26. 当前具身方案中，`Cerebellum` 至少提供移动模式与操作模式两类低层能力接口。
27. 机器人相关 Session 可以接受自然语言，也可以在权限允许时接受直接 toolcall / 结构化控制请求。
28. 图中 `*N` 对象与完整画出的对象是平等展开，不是从属特例。

---

## 12. 当前阶段最值得继续思考的问题

1. `Prime Context Compiler` 的最小 schema 应如何冻结，才能既保持规则优先，又允许少量特权 tool patch。
2. `Session Host` 提交长期经验时，如何定义经验候选、证据和去重/冲突关系。
3. `Agent Thread` 的 `Artifact Slots` 应优先支持哪些结构化产物，才能最大限度减少 prompt 膨胀。
4. `A2A` 若未来启用，应如何通过调度器受控引入，而不破坏当前单线程基线。
5. 对具身控制而言，哪些结构化请求允许直达 `Session Host`，哪些必须回到自然语言或高层规划路径。
6. `Cerebellum`、导航模块与基座模型之间的边界，最终应如何划分才能兼顾实时性与可编排性。
7. 物理世界能力的权限、安全约束与人工接管机制应如何形式化。

---

## 13. 备注

本文档是当前版本的重构版架构说明，目的是：

- 合并前序讨论中已经稳定的修改点
- 去掉不必要的历史残留表述
- 明确“上下文编译”与“运行态工作集”之间的边界
- 为后续软件 Agent 与具身控制的统一落地保留一致的 Kernel 视角

后续新增内容应直接覆盖旧判断，而不是在旧文档之上继续叠加历史版本。
