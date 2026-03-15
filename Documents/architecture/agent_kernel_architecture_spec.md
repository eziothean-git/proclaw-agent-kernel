# Agent Kernel Architecture Spec（重构版 / 当前稳定版）

## 1. 文档目标与适用范围

### 1.1 文档目标

本文档用于固定当前版本仍然成立的宏观设计，重点描述：

- 系统的顶层结构
- 关键对象与边界
- 主要信息流
- 稳定的哲学判断
- 当前阶段明确不做的事情

本文档的目标不是提供可直接编码的低层接口说明，而是为后续实现、拆图、定义 schema 和技术选型提供统一语义底座。

### 1.2 适用范围

当前 `Agent Kernel` 并不只服务于纯软件形态的 AgenticOS。

它同时是一个可扩展到机器人 embodied 控制系统的统一内核。也就是说，本文档描述的不是“聊天 agent 的局部实现”，而是一个可同时承载：

- 纯软件任务执行
- 多 Session 信息治理
- 工具 / Skill / MCP 调用
- 机器人感知-规划-执行链路接入

的长期运行信息流内核。

### 1.3 当前不展开的内容

当前阶段不在本文档中继续展开：

- 低层 API / RPC / MCP 接口细节
- 具体 schema 与字段级定义
- 存储引擎与索引内部实现
- UI 与具体交互界面
- 长期知识库内部结构
- 机器人导航方案与基座模型的最终选型
- 机器人安全策略与控制器参数细节

这些内容后续应由独立文档维护。

---

## 2. 核心哲学

### 2.1 LLM 是可替换插件，不是系统本体

LLM 在本系统中的角色是可替换的认知插件，而不是系统本体。

系统的连续性不依赖某个固定模型，而依赖：

- 信息流结构
- 上下文编译机制
- 长期记忆与知识沉淀
- 基础 Prompt 核
- 作用域与权限治理

因此，模型可以替换，系统身份与长期连续性不应随之坍塌。

### 2.2 系统能力来自“模型能力 × 信息流治理”

系统不会把全部控制权交给模型，而是通过上下文治理、能力边界、执行基础设施与记忆机制，有选择地调用模型的局部智能。

因此，系统能力不应被理解为“某个模型本身有多强”，而应理解为：

**模型能力 × 信息流治理**

### 2.3 人格不属于单一模型

人格连续性不来自某个模型本身，而来自：

- 相对稳定的 Prompt / Rule Kernel
- 长期记忆与偏好连续性
- 上下文如何被筛选、编译、沉淀和再利用

### 2.4 `Prime Personality` 是跨 Session 的统一人格入口

`Prime Personality` 不是某个单独 Session 的子对象，而是跨 Session 的统一人格入口层。

它负责维持系统对外表现出的稳定身份、解释框架与基础行为风格，但它本身不持有底层执行状态。

当前版本中，`Prime Personality` 应视为：

- 跨 Session
- 统一入口
- 高层解释壳层
- **stateless**

### 2.5 `Agent Primitive` 是基础算子，不是系统级智能主体

在本系统中，`Agent Primitive` 更接近基础算子，而不是系统视角下拥有完整智能的主体。

它知道的是：

- 当前要做什么
- 当前该如何在约束下做
- 当前允许调用哪些能力

它不知道的是：

- 系统级完整真相
- 长期连续性的全部来源
- 全局身份的完整结构

因此，`Agent Primitive` 更像这套 Kernel 的“CPU 能力单元”：

- 在局部上下文中解释问题
- 在局部作用域内做出决策
- 生成动作意图或结构化结果
- 但不天然拥有系统级连续性与全局真相

### 2.6 Agent 的关键分界：是否参与自身上下文再生产

当前版本中，原子级 Agent 与高级 Agent 的关键区别，不在于是否调用 LLM，而在于：

**它是否引入同等级智能，通过 Context Manager / Context Compiler 对自身可用 Context / Memory 进行再编辑。**

也就是说：

- 原子级 Agent 更接近规则驱动的受限执行算子
- 高级 Agent 会借助上下文治理能力参与自身可用上下文的筛选、压缩、补充和重组

这里必须特别强调：

**规则驱动的运行态状态更新，不等于上下文再生产。**

如果一个执行线程只是把 observation 追加到事件日志，再根据固定规则构造下一轮有限工作集，那么它仍然可以是原子级 Agent；只有当它引入同等级智能，对自身未来可见上下文进行语义级再编辑时，才越过边界成为高级 Agent。

### 2.7 图中 `*N` 对象是平等展开

图中未完整展开的 `*N` 对象，与完整画出的对象是平等展开，而不是从属特例。

---

## 3. 顶层结构

### 3.1 宏观层次

当前 Kernel 可被理解为七个宏观层与一组可替换执行后端共同构成的长期运行系统：

1. 外部接入层
2. 请求源层
3. 人格入口层
4. Session 交互与路由层
5. Session 编排层
6. Task 执行层
7. 记忆与上下文支撑层
8. 可替换执行后端（软件能力 / embodied 能力）

其中前七层构成统一 Kernel，本地工具、外部服务与机器人控制模块则作为可替换执行后端被接入。

### 3.2 软件与 embodied 只是执行域不同，不是两套内核

本系统并不区分“软件 Kernel”与“机器人 Kernel”两套完全不同的架构。

更准确的理解是：

- 上层的人格、Session、上下文治理与执行编排是共享的
- 下层的执行后端可以是软件工具链，也可以是 embodied 控制链路
- embodied 场景通过少量高权限模块暴露到内核，而不是单独再造一套人格-记忆-调度体系

---

## 4. 统一抽象模型

### 4.1 `Agent Primitive` 的统一定义

`Agent Primitive` 是本系统中的统一行为载体，也是 AgenticOS 的基础算子。

它不是系统本体，不等同于人格本身、长期连续性本身或基础设施本身，而是：

**在给定规则核、局部上下文、权限边界与生命周期包络下，调用基础模型完成解释、决策、能力请求与结构化结果生成的主动执行单元。**

### 4.2 `Agent Primitive` 的六个共同要素

一个 `Agent Primitive` 至少由以下六个要素共同定义：

1. **Model Substrate**  
   基础模型能力来源。

2. **Rule Kernel**  
   Prompt / rules / 不可轻易漂移的行为约束核。

3. **Compiled Context**  
   由 Context Compiler 提供的局部上下文视图。

4. **Capability Boundary**  
   Skill / Tool / MCP / 系统接口等能力边界。

5. **Scope & Privilege**  
   当前可见范围、可行动范围与可影响状态层级。

6. **Lifecycle Envelope**  
   轮次、预算、停止条件、回放边界与可观测边界。

### 4.3 `Agent Primitive` 的原子能力面

当前版本中，一个合格的 `Agent Primitive` 至少应具备以下原子能力：

1. **Goal Interpretation**：解释当前目标
2. **Local Decision**：决定下一步动作
3. **Capability Request**：产生 toolcall / skill call / 系统请求
4. **Observation Consumption**：消费外部反馈并更新局部判断
5. **Structured Output**：输出结构化结果
6. **Bounded Iteration**：在预算约束下执行局部循环

### 4.4 原子级 Agent 与高级 Agent

#### 原子级 Agent Primitive

原子级 Agent Primitive 的特点是：

- 不主动编辑自身长期记忆结构
- 不借助同等级智能重组自身可用上下文体系
- 主要在既定上下文中完成局部任务求解
- 高级能力不来自它本身，而来自其上层提供的上下文与规则

#### 高级 Agent Primitive

高级 Agent Primitive 的特点是：

- 会参与上下文筛选、压缩、补充和重组
- 会通过上下文治理机制影响自身后续可见信息
- 会借助同等级智能与 Context Manager / Context Compiler 协同涌现更高级行为

因此，当前版本建议把高级性的来源理解为：

**是否引入同等级智能，对自身可用 Context / Memory 进行再编辑。**

### 4.5 Agent 家族与 Infrastructure 家族

当前版本建议把系统对象分为两大家族。

#### A. Agent Primitive 家族

负责解释、判断、行为生成与结构化输出。

包括：

- `Prime Personality`
- `主 Context Compiler`
- `Session Host`
- `进程 Context Compiler`
- `Agent 线程`

#### B. Infrastructure 家族

负责接入、排队、执行、存储、适配与约束。

包括：

- `对外网关`
- `请求队列管理器`
- `定时请求调度器`
- `Request Executor / Coordinator`
- `Agent 线程调度器`
- `Thread Context / Runtime Memory Manager`
- `Memory Base`
- `SKILL lib`

这一区分的意义是：

- Agent Primitive 负责“在局部上下文中做判断并产出动作意图”
- Infrastructure 负责“承托、执行、存储、约束与适配这些动作”

### 4.6 层级实例化

当前架构中，`Agent Primitive` 至少体现为四种层级形态：

1. **人格级 Agent Primitive**：`Prime Personality`
2. **编译器型 Agent Primitive**：`主 Context Compiler`、`进程 Context Compiler`
3. **Session 级 Agent Primitive / Agent 容器**：`Session Host`
4. **执行级 Agent Primitive**：`Agent 线程`

---

## 5. 上下文模型

当前版本中，“context” 不应再被混用为一个含义模糊的大词。至少应区分以下五类对象。

### 5.1 `Compiled Context`

`Compiled Context` 是由 `主 Context Compiler` 或 `进程 Context Compiler` 输出的结构化上下文视图。

它的特征是：

- 面向特定作用域生成
- 来自规则、记忆、技能定义与检索结果的受控装配
- 是 Agent Primitive 的输入视图，而不是长期真相本身

### 5.2 `Runtime Working Context`

`Runtime Working Context` 是执行线程运行期间实际消费的有限工作集，也可理解为 **bounded working set**。

它的特征是：

- 有固定或强约束大小
- 只服务于当前局部循环
- 不是整段不断膨胀的对话历史
- 由规则式 Working Set Builder 从输入包、事件日志和 artifact 中投影而来

### 5.3 `Event Log / Snapshot`

`Event Log` 是 Task / Thread 运行过程中的完整追加式事件流。

它记录：

- 观察结果
- 工具返回
- 执行动作
- 错误
- 检查点
- 局部状态变化

它的职责是完整记录与可回放，而不是直接全部进入 prompt。

### 5.4 `Artifact Slots`

`Artifact Slots` 是线程运行中产生的结构化中间结果容器。

典型产物包括：

- 代码模块摘要
- 符号清单
- 依赖图摘要
- 候选文件列表
- patch plan
- 任务中间结论

它们用于让线程与上层消费“结构化结果”，而不是回灌整段长文本历史。

### 5.5 `Long-term / Curated Memory`

这是 `Memory Base` 中被长期沉淀并可被后续编译器选择性使用的记忆层。

它不等于：

- 单次运行日志
- 某个线程的即时 observation
- 直接可见给任意执行层的原始上下文

### 5.6 当前版本的关键判断

当前版本中，执行层不应通过“不断增长的对话历史”维持循环，而应通过：

- 完整外部事件日志
- 有界运行工作集
- 结构化 artifact

共同支撑 SEE-ACT-UPDATE 闭环。

这既能避免 prompt 膨胀，也能保持原子级执行线程的定义不被破坏。

---

## 6. 关键对象与边界

### 6.1 对外网关

`对外网关` 用于承接聊天软件、控制面或其他外部接入面，例如 Discord、Telegram、CLI、Web UI 或机器人上层控制入口。

职责：

- 处理外部平台的接入协议与消息收发
- 将不同入口收敛为内部中间表示
- 接收系统内部中间表示并编译为外部输出格式

平台差异应尽量停留在网关层，而不是污染系统核心信息流。

### 6.2 内部中间表示

系统内部优先围绕统一的中间表示工作，而不是围绕各平台最终消息工作。

当前阶段建议保持中间表示轻量化，并优先采用 JSON 形式承载：

- 主体文本
- 资源占位符 / 指示符
- 对应资源引用
- 少量结构化元信息

自然语言入口消息也应尽量先收敛到同类结构。

### 6.3 请求队列管理器

`请求队列管理器` 是统一请求源层。

所有自然语言输入都应先进入这里，再被串行化送入 `Prime Personality`，以避免多设备、多入口或多触发源直接竞争下游链路。

当前至少存在三类入口请求源：

1. 用户请求
2. 定时请求调度器触发的预存请求
3. 某些高权限系统请求

### 6.4 定时请求调度器与 Hook 保护机制

`定时请求调度器` 不是普通后台计时器，而是一个规则触发的预存请求调度层。

它更接近：

**主人格对未来自己的留言系统。**

其写入能力不应向普通执行进程开放，而应通过高权限 Hook 受控暴露，用于：

- 审核哪些信息可以进入未来请求队列
- 阻止普通任务污染关键未来信息
- 保证“给未来自己的留言”是高权限行为而不是副产物

### 6.5 `Prime Personality`

`Prime Personality` 是跨 Session 的统一人格入口层。

职责：

- 对外承载统一人格壳层
- 维持系统级解释框架
- 维持跨 Session 的身份连续性
- 生成系统内部统一表达与中间表示

关键性质：

- 它本身应视为 **stateless**
- 它不负责线程级调度、进程管理或具体 Task 执行
- 每次最终输出都必须重新依赖 `主 Context Compiler` 的上下文收敛结果

### 6.6 `主 Context Compiler`

`主 Context Compiler` 服务于 `Prime Personality`，是一个 **规则优先、受限特权、编译器型高级 Agent Primitive**。

它不应被实现成“另一个通用聊天 agent”，而应被理解为：

- 入口层上下文装配器
- 人格连续性的前置编译器
- 对主人格开放的特权上下文工具使用者

职责：

- 解释入口消息
- 维持主人格连续性
- 做入口级上下文收敛
- 将不同接入点的输入形式收敛为统一基础表达
- 仅向主人格暴露部分特殊系统能力

当前版本建议其工作模式为：

1. **第一轮纯规则编译**：默认先用规则生成 `Compiled Context`
2. **必要时触发受限上下文工具调用**：只在确有缺口时做局部补丁
3. **输出结构化编译结果**：而不是直接生成开放式长文本

它可以修改的是：

- 当前轮的 `Compiled Context`
- 当前轮的上下文视图与补丁结果

它不应直接修改的是：

- `Session Host` 持有的 Session 真相
- 长期记忆本身
- 执行层运行日志

### 6.7 `Agentic OS Interface Skill`（历史命名：`Info Router`）

`Agentic OS Interface Skill` 是提供给主人格使用的特权系统 Skill / MCP。

它不是独立 agent 节点，而是一个 **Prime-only 的系统交互界面**，用于：

- 让 `Prime Personality` 与不同 `Session Host` 双向交换消息
- 读取与选择可见的 Session / Task 结果
- 决定请求应进入哪个 Session
- 判断应新建、复用还是只返回轻量响应
- 将请求送入正确的 `Session Host`

因此，当前正式口径中，历史上的 `Info Router` 应被理解为：

**由主人格调用的高权限系统 Skill，而不是额外的自治 agent。**

### 6.8 `Session Host`

`Session Host` 是单个 Session 的局部内核，也是 Session 级 Agent Primitive / Agent 容器。

职责：

- 持有 Session 级状态
- 管理该 Session 内的请求、过程与任务集合
- 调用 `进程 Context Compiler`
- 汇聚执行结果
- 将真正具有长期意义的经验选择性提交给 `Memory Base`

当前版本中，对它更稳妥的理解是：

- 它是 **stateful** 的 Session 治理壳层
- 它不应承担每一轮线程内部微观上下文编辑
- 它可以有高层判断，但不应退化成“所有子线程压缩都回到 Host 处理”的中心瓶颈

### 6.9 `进程 Context Compiler`

`进程 Context Compiler` 服务于 `Session Host`，负责面向具体 Session / Task 组织执行上下文。

职责：

- 汇聚 Session 级状态
- 调用长期记忆、技能定义与检索结果
- 生成供执行层使用的上下文包
- 把更高层状态投影为可执行的 Task 输入

`主 Context Compiler` 与 `进程 Context Compiler` 本质上是同一类组件在不同作用域下的实例，但它们的职责边界与权限范围不同。

### 6.10 `Process`

`Process` 表示 Session 内可并存的一组局部过程对象。

它们由 `Session Host` 管理，用于承载：

- 不同请求
- 不同任务线
- 不同执行阶段
- 不同局部状态演化

这里的 `Process` 是逻辑过程，不应机械等同于操作系统进程。

### 6.11 `Task Runtime Snapshot`

真正被执行的不是整个 Session，而是某个 Task 的运行快照。

它是：

- Session 状态的局部可执行投影
- Task 状态的运行态视图
- 受控局部沙箱

### 6.12 `Request Executor / Coordinator`

`Request Executor / Coordinator` 是跨 Session 的共享执行基础设施，而不是某个 Session 的私有对象。

职责：

- 接收上层 Agent 产生的 toolcall / 执行请求
- 对接软件工具、系统能力与 embodied 执行模块
- 协调局部消息流
- 驱动一次请求在 Task 快照中的实际执行
- 将局部执行结果汇总回运行态
- 作为统一执行入口抑制竞争与冲突

因此，它应被明确归类为 **Infrastructure**，而不是 Agent Primitive。

### 6.13 `Agent 线程调度器`

`Agent 线程调度器` 负责在线程级别编排执行实例。

职责：

- 创建、回收与切换 Agent 线程
- 维护线程级预算、轮次与生命周期
- 决定何时继续、挂起或终止某个执行线程

它同样属于 **Infrastructure**，而不是新的 agent 层级。

当前版本中应明确：

- 不把自由式 A2A 通信作为默认执行机制
- 若未来需要多线程协作，优先采用调度器介导的子任务分派与 artifact 交换
- 自由式线程互聊不属于当前稳定版架构

### 6.14 `Agent 线程`

`Agent 线程` 是执行级 Agent Primitive，也是当前版本中的 **执行级原子 Agent**。

它负责：

- 在给定规则与局部上下文下完成具体子工作
- 产生 toolcall / 执行请求
- 消费 observation 与运行反馈
- 产出结构化中间结果或最终结果

#### 6.14.1 当前稳定版的内部结构

为了避免执行层上下文无限膨胀，`Agent 线程` 当前不应被实现成“不断叠加聊天历史”的黑盒，而应由以下内部结构共同组成：

1. **Immutable Input Bundle**  
   线程启动时给定的输入包，包括上层指令、任务目标、权限边界、初始上下文、停止条件和预算。

2. **Event Log**  
   线程运行时的完整事件日志，用于记录 SEE / ACT / UPDATE 过程中的 observation、tool result、动作结果、错误与检查点。

3. **Working Set Builder**  
   规则式工作集构造器。它从输入包、事件日志与 artifact 中投影出下一轮 prompt 视图。

4. **Runtime Working Set / Prompt View**  
   当前轮真正喂给模型的有限工作集。它应强约束大小，而不是无界增长。

5. **Artifact Slots**  
   用于保存结构化中间结果，例如模块摘要、候选文件、依赖关系、patch plan、局部结论等。

6. **Agent 操作界面**  
   即当前线程能触达的能力边界，包括工具、Skill、系统请求与必要的环境读写能力。

#### 6.14.2 SEE-ACT-UPDATE 闭环

`Agent 线程` 的执行循环应更接近受控的 SEE-ACT-UPDATE，而不是开放式长对话。

其典型循环为：

1. **SEE**  
   消费 observation / tool result / 环境反馈，并写入 `Event Log`，必要时更新 `Artifact Slots`。

2. **BUILD**  
   `Working Set Builder` 依据固定规则，从 `Immutable Input Bundle`、近期关键 observation 与当前 artifact 生成下一轮 `Runtime Working Set`。

3. **ACT**  
   线程在当前工作集中决定下一步动作，生成 toolcall / skill call / 结构化结果。

4. **UPDATE**  
   把动作结果回写到事件日志与状态标记，直到满足停止条件。

#### 6.14.3 为什么它仍然是原子级 Agent

当前版本中，`Agent 线程` 虽然具有反馈循环，但它仍然属于原子级 Agent，原因在于：

- 工作集构造是规则驱动的
- 它不会引入同等级智能去语义级重写自身上下文体系
- 它不主动改写长期记忆
- 它不把完整日志直接回灌为下一轮 prompt

因此，**运行态工作集更新不等于上下文再生产。**

### 6.15 `Thread Context / Runtime Memory Manager`

`Thread Context / Runtime Memory Manager` 是执行层的特殊上下文管理基础设施。

职责：

- 管理 Task / Thread 级事件日志与快照
- 为线程提供受控的运行态上下文视图
- 管理可回放的执行材料与结构化 artifact
- 追踪上下文在执行过程中的局部变化
- 避免线程运行态直接污染更高层 Session 结构
- 按时间顺序沉淀可检索的 Task 全量材料，供后续编译器使用

这里的关键是：

- 完整运行历史可以保存在日志与快照中
- 但真正进入线程 prompt 的只能是有限工作集

### 6.16 `Memory Base`

`Memory Base` 是统一记忆底座，而不是单一数据库实例。

它是长期连续性与知识沉淀的总入口，内部可包含：

- 长期事实记忆
- 偏好与人格连续性记忆
- Session / workspace / global 分层记忆
- 项目知识与历史任务抽象
- 文档整理结果
- 实体、关系与主题索引
- 面向检索的异构视图

当前版本中，`Memory Base` 更应被理解为统一抽象入口，而不是单点实现。

### 6.17 `SKILL lib`

`SKILL lib` 更接近应用层能力定义源，而不是普通函数库。

它提供：

- Prompt 核来源
- 规则来源
- tool intents
- 能力边界
- 身份约束
- 部分系统能力的定义入口

### 6.18 embodied 控制扩展

当前 Kernel 同时面向机器人 embodied 控制场景，但 embodied 部分不应破坏上层统一信息流。

当前建议的 formal 口径是：

#### 6.18.1 embodied 通过少量高权限模块接入

物理交互部分应尽量被封装到少量几个高权限模块中，再经由 `Request Executor / Coordinator` 暴露给上层。

这样做的目的不是追求抽象好看，而是为了：

- 控制能力面
- 保持软件域与物理域的统一接入方式
- 降低高风险执行面的扩散

#### 6.18.2 特殊 embodied Session

机器人控制可通过一个特殊的 `Session` 接入 Kernel。

该 Session 可以接受：

- 自然语言请求
- 来自上层模块的直接 toolcall

它仍遵循统一的 Session / Task / Executor / Context 流程，只是其执行后端是 embodied 模块而不是普通软件工具。

#### 6.18.3 小脑控制层

当前 embodied 部分的低层控制被抽象为“小脑”控制层，并至少提供两种基础模式：

1. **移动模式**  
   对应速度 / 角速度指令等底层运动控制接口。

2. **操作模式**  
   对应追踪输入、操作执行或末端执行器相关控制接口。

这里的“小脑”应被理解为低层受控执行模块，而不是再引入一套独立人格或独立 Kernel。

#### 6.18.4 导航与基座模型层

在小脑之上，可以继续接入：

- 导航模块
- 基座模型 / embodied foundation model

它们当前仍是可替换后端，具体实现方式需要根据后续的导航方案与基座模型选型决定，因此本 spec 只固定它们的架构位置，不固定具体技术实现。

---

## 7. 核心信息流

### 7.1 自然语言主路径

用户
→ 对外网关
→ 内部中间表示收敛
→ 请求队列管理器
→ `Prime Personality`
→ `主 Context Compiler`
→ `Agentic OS Interface Skill`
→ 选定 `Session Host`
→ `进程 Context Compiler`
→ `Thread Context / Runtime Memory Manager`
→ `Agent 线程调度器`
→ `Agent 线程`
→ `Request Executor / Coordinator`
→ 软件工具 / 系统能力 / embodied 模块
→ 结果回流到 `Session Host`
→ `Prime Personality` 生成内部中间表示
→ 对外网关编译为外部输出
→ 用户

### 7.2 定时请求路径

预存请求
→ 定时请求调度器
→ 请求队列管理器
→ 后续进入与普通用户请求等价的主路径

### 7.3 高权限系统请求路径

高权限 Hook / 系统请求
→ 请求队列管理器 或 直接进入受控 Session 接口
→ 后续按相同治理边界进入 Kernel

### 7.4 embodied 控制路径

自然语言或直接 toolcall
→ 特殊 embodied Session
→ `Session Host`
→ `进程 Context Compiler`
→ `Agent 线程` / 或受控直接执行链路
→ `Request Executor / Coordinator`
→ embodied 模块（导航 / 小脑 / 其他物理执行器）
→ 环境反馈 / 传感反馈
→ 运行日志与结果回流

### 7.5 当前版本中特别强调的几点

- `Prime Personality` 是 stateless 的
- `Request Executor / Coordinator` 是跨 Session 共享执行入口
- `Agentic OS Interface Skill` 是主人格可调用的特权系统 Skill，而不是独立 agent 节点
- 执行层默认不依赖自由式 A2A 互聊
- 执行层上下文不应以无界对话历史形式维持，而应通过事件日志 + 有界工作集 + artifact 运转

---

## 8. 核心闭环

### 8.1 全局生成-执行闭环

请求源触发
→ 主人格解释
→ Session 选择
→ 执行上下文编译
→ 线程执行
→ 执行结果回流
→ 主人格输出

### 8.2 知识沉淀闭环

运行结果 / 中间 artifact
→ `Session Host` 判断是否具有长期意义
→ 进入记忆沉淀流程
→ 更新 `Memory Base`
→ 在后续 Context Compiler 中再次被利用

### 8.3 线程级 SEE-ACT-UPDATE 闭环

输入包
→ Observation / 环境反馈
→ 事件日志追加
→ Working Set Builder 投影视图
→ 线程决策 / 执行请求
→ 新 observation 返回
→ 循环直到满足停止条件

### 8.4 embodied 行为闭环

上层意图
→ embodied Session / Task
→ 执行后端（导航 / 小脑 / 操作）
→ 物理反馈 / 传感反馈
→ 事件日志与结果回流
→ 上层继续决策或结束

---

## 9. 当前稳定锚点

以下判断视为当前版本的稳定架构结论：

1. 系统不是“一个大 Agent”，而是一个长期运行的信息流内核。
2. LLM 是可替换插件，不是系统本体。
3. 人格连续性来自 Prompt 核、信息流结构与长期记忆，而不是某个固定模型本身。
4. `Prime Personality` 是跨 Session 的统一人格入口，且本身是 stateless 的。
5. 所有自然语言输入都必须先进入请求队列管理器，再进入 `Prime Personality`。
6. `Agent Primitive` 是系统中的统一行为载体与基础算子，而不只等于执行层线程。
7. 原子级 Agent 与高级 Agent 的关键分界，在于是否借助同等级智能参与自身可用 Context / Memory 的再编辑。
8. 规则驱动的运行态工作集更新，不等于上下文再生产。
9. `主 Context Compiler` 是规则优先的入口编译器，而不是另一个通用聊天 agent。
10. `主 Context Compiler` 可以在必要时使用受限上下文工具修补当前轮上下文，但不直接改写 Session 真相或长期记忆。
11. 历史上的 `Info Router` 在当前正式口径中应被理解为 `Agentic OS Interface Skill`，即主人格使用的特权系统 Skill。
12. `Session Host` 是 Session 级状态治理壳层，不应承担每轮线程内部的微观上下文编辑。
13. `主 Context Compiler` 与 `进程 Context Compiler` 是同类组件在不同作用域下的实例。
14. `Request Executor / Coordinator` 是跨 Session 共享的执行基础设施，而不是某个 Session 私有模块。
15. `Agent 线程调度器` 属于基础设施，而不是新的 Agent 层级。
16. `Agent 线程` 当前稳定版应实现为“事件日志 + 有界工作集 + artifact”的受控执行结构，而不是不断增长的聊天黑盒。
17. `Agent 线程` 当前仍属于执行级原子 Agent。
18. 自由式 A2A 通信不属于当前稳定版默认执行机制。
19. `Thread Context / Runtime Memory Manager` 负责完整运行材料的日志化、快照化与受控投影，而不是把全部历史直接回灌到 prompt。
20. `Memory Base` 是统一记忆底座的抽象入口，不是单点实现。
21. `SKILL lib` 是规则、能力边界与身份约束的定义来源。
22. 网关层负责平台差异适配，而不应重写系统核心语义。
23. 当前内部中间表示应尽量轻量化，并优先采用 JSON 类结构承载。
24. embodied 控制不是独立第二套 Kernel，而是同一 Kernel 上接入的一组高权限执行后端。
25. 机器人物理交互面应被尽量收敛到少量高权限模块中。
26. embodied 场景下至少存在一个特殊 Session，用于承接自然语言或直接 toolcall 的机器人控制请求。
27. 小脑控制层当前至少抽象为移动模式与操作模式两种基础执行模式。
28. 导航方案与基座模型当前仍是可替换后端，不在本 spec 中固定实现。
29. 图中 `*N` 对象与完整画出的对象是平等展开，而不是从属特例。

---

## 10. 当前明确延后的内容

以下内容不属于当前稳定版强承诺：

1. 自由式 A2A 多线程互聊机制
2. 执行线程内部的开放式上下文自编译
3. 让 `Session Host` 成为每轮线程上下文编辑中心
4. `Memory Base` 的内部数据模型细拆
5. embodied 导航系统与基座模型的最终选型
6. 更严格的物理安全策略、仲裁与故障恢复细节
7. 低层 schema、事件协议与持久化实现细节

---

## 11. 当前阶段最值得继续思考的问题

1. `Session Host` 与更高层全局 Kernel 的关系，是否需要在图中再次显式画出。
2. `主 Context Compiler` 的受限上下文工具集合应如何定义，才能既快又稳定。
3. `Working Set Builder` 的规则边界应如何冻结，才能避免它向“线程内小型编译器”漂移。
4. `Thread Context / Runtime Memory Manager` 与线程内部 `Working Set Builder` 的接口边界应如何定义。
5. 高权限 Hook 的授权边界应如何定义，才能既允许未来留言，又避免普通任务污染关键请求队列。
6. embodied 场景下的特殊 Session 与普通软件 Session，是否需要不同的权限模板与停止条件模板。
7. embodied 导航模块与基座模型层，应如何被抽象成统一能力接口，而又不丢失具体系统的可调性。
8. 物理执行链路中的安全约束、人工接管与 emergency stop 机制，应如何进入统一执行框架。

---

## 12. 备注

本文档为当前版本的重构版架构说明，目标是把已稳定下来的判断重新组织成更清晰的结构，而不是继续叠加历史讨论痕迹。

后续新增内容应尽量直接覆盖旧表述，避免在主架构文档中不断堆叠版本历史。
