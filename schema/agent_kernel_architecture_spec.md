# Agent Kernel Architecture Spec（精简版）

## 1. 文档目的

本文档只保留当前版本仍然成立的核心设计，用于固定系统的宏观架构、信息流关系与关键哲学。

当前阶段不展开：

- 具体接口
- 低层 schema
- 存储引擎细节
- 传输协议
- UI 细节
- 知识库内部结构细节

---

## 2. 核心哲学

### 2.1 LLM 是可替换插件，不是系统本体

LLM 的角色是可替换的认知插件，用于生成文本，并在文本中体现某一领域、某一任务、某一视角下的智能。

系统的连续性不依赖某个固定模型，而依赖：

- 信息流结构
- 上下文编译机制
- 长期记忆与知识沉淀
- 基础 Prompt 核

### 2.2 系统通过上下文治理使用模型智能

系统不会把全部控制权交给模型，而是通过严格的上下文控制，有选择地调用模型的局部智能。

因此，系统能力来自：

**模型能力 × 信息流治理**

### 2.3 人格不属于单一模型

人格连续性不来自某个模型本身，而来自：

- 相对稳定的基础 Prompt 核
- 长期记忆与偏好连续性
- 信息如何被筛选、编译、沉淀和再利用

### 2.4 主人格是跨 Session 的

`Prime Personality` 不是某个单独 Session 的子对象，而是跨 Session 的统一人格入口层。

它高于单个 Session，负责维持系统对外表现出的稳定身份、解释框架与基础行为风格。

### 2.5 图中 *N 对象是平等展开

图中未完整展开的 `*N` 对象与完整画出的对象是平等的，不是从属特例。

### 2.6 Agent 是统一行为载体

当前系统中的多个关键模块虽然职责不同，但其行为生成都依赖 Agent 机制。

因此，`Agent` 需要被视为本系统中的统一行为载体，而不是只等同于执行层里的“Agent 线程”。

也就是说：

- 主人格层依赖 Agent 机制生成对外表达
- Host / 编排层依赖 Agent 机制进行高层判断与决策
- Context Compiler 依赖 Agent 机制完成上下文选择、压缩或组织
- 执行层中的 Agent 线程则是最直接的 Agent 实例形态

从这个角度看，系统中的很多对象并不是“不是 Agent”，而是“不同作用域、不同权限、不同职责的 Agent 实例或 Agent 容器”。

### 2.7 Agent 是基础算子，不是系统视角下的智能主体

在本系统的哲学中，`Agent` 更接近一种基础算子（primitive operator），而不是系统视角下拥有完整智能的主体。

它知道的是：

- 自己要做什么
- 自己该如何在当前约束下做
- 自己能调用哪些能力

它不知道的是：

- 整个系统的完整智能全貌
- 高层连续性本身
- 系统级身份的全部来源

因此，从系统视角看：

- Agent 的能力并不来自它自身固有的智能
- Agent 的能力主要依赖基础模型
- Agent 的表现取决于被喂入的上下文、规则和权限边界

也就是说，`Agent` 更像是这套 AgenticOS 的“CPU 能力单元”：

- 它负责执行
- 它负责在局部上下文中进行推理与行为生成
- 但系统级智能来自更高层的信息流治理，而不是某个 Agent 自身

### 2.8 Agent 的关键分界：是否参与自身上下文编辑

当前版本中，原子级 Agent 与高级 Agent 的关键区别，不在于是否“用了 LLM”，而在于：

**它是否引入同等级智能，通过 Context Manager / Context Compiler 对自身可用记忆与上下文进行编辑、压缩、筛选、补充和重组。**

也就是说：

- 原子级 Agent 更接近固定规则驱动的基础算子
- 高级 Agent 则通过上下文治理能力参与“自身可用上下文的再生产”

因此，高级能力并不是来自某个 Agent 单体天然更神奇，而更接近：

**同等级智能单元 + Context Manager / Context Compiler + Memory Base 协同作用下的涌现能力。**

---

## 3. 顶层结构

系统由七个宏观层组成：

1. 外部接入层
2. 请求源层
3. 人格入口层
4. 信息路由层
5. Session 编排层
6. Task 执行层
7. 记忆与上下文支撑层

它们共同构成一个长期运行的 Agent Kernel。

---

## 4. 关键对象

### 4.0 Agent Primitive（统一定义）

`Agent Primitive` 是本系统中的统一行为载体，也是 AgenticOS 的基础算子。

它不是系统视角下的完整智能主体，不等同于“人格本身”“系统本身”或“长期连续性本身”，而是：

**在给定规则核、局部上下文和权限边界下，调用基础模型完成解释、决策、能力请求与结构化结果生成的主动执行单元。**

换句话说，Agent Primitive 是这套系统中的“CPU 能力原语”：

- 它负责在局部上下文中进行推理与行为生成
- 它负责把当前任务转化为下一步动作
- 它可以请求能力调用，但不天然拥有系统全部执行权
- 它不天然拥有系统级身份、系统级连续性或全局真相

### 4.0A 完整定义

一个 Agent Primitive 至少由以下六个要素共同定义：

1. **Model Substrate**
   - 即基础模型能力来源
   - Agent Primitive 的推理、语言生成与局部决策能力主要依赖这里

2. **Rule Kernel**
   - 即 prompt / rules / 不可轻易漂移的行为约束核
   - 用于限定它“应如何理解任务”和“允许以何种方式行动”

3. **Compiled Context**
   - 即由 Context Compiler 提供的局部上下文
   - Agent Primitive 不自行拥有长期真相，而只消费被编译后的上下文视图

4. **Capability Boundary**
   - 即可调用能力边界
   - 包括 Skill / Tool / MCP / 系统接口 / 特殊能力暴露范围
   - Agent Primitive 只能在被允许的边界内行动

5. **Scope & Privilege**
   - 即所处作用域与权限等级
   - 决定它看到什么、能做什么、能影响哪一层状态

6. **Lifecycle Envelope**
   - 即调用轮次、执行期限、停止条件、回放与可观测边界
   - 用于确保 Agent Primitive 是受控算子，而不是无限自治体

### 4.0B 原子能力

参考 OpenAI 的 “LLM + decision + tools + guardrails” 结构骨架，以及 Claude Code 的 “subagents + hooks + memory + skills” 可组合能力面，本系统中的 Agent Primitive 至少具备以下原子能力：

#### 1. Goal Interpretation
能在局部上下文中解释“当前要做什么”。

#### 2. Local Decision
能在当前限制下决定“下一步做什么”。

#### 3. Capability Request
能生成 toolcall / skill call / MCP call / 系统请求，但不等于自己直接执行所有外部能力。

#### 4. Observation Consumption
能消费工具结果、检索结果、上下文补充和运行反馈，并据此更新局部判断。

#### 5. Structured Output
能输出结构化结果，而不只是自然语言文本。

#### 6. Bounded Iteration
能进行局部循环，但循环必须受权限、轮次、预算和生命周期边界约束。

### 4.0C 分级：原子级 Agent 与高级 Agent

#### 原子级 Agent Primitive

原子级 Agent Primitive 完全依赖预先写好的规则核与给定输入工作。

它的特点是：

- 不主动编辑自身长期记忆结构
- 不主动重组自身可用上下文体系
- 主要在既定上下文中完成局部任务求解
- 能力主要体现为基础模型在当前任务上的局部执行力

#### 高级 Agent Primitive

高级 Agent Primitive 除了局部任务求解外，还具备借助 `Context Manager / Context Compiler` 对可用上下文进行再组织的能力。

它的特点是：

- 会参与上下文筛选、压缩、补充和重组
- 会通过上下文管理机制影响自身后续可见信息
- 会借助同等级智能单元协同涌现更高级技能
- 高阶能力并非来自单体 Agent 神化，而来自上下文治理体系的协同

因此，当前文档建议把 Agent 的高级性理解为：

**是否引入同等级智能，对自身可用 Context / Memory 进行再编辑。**

### 4.0D 它不是什么

为了避免把 Agent 神化，必须明确 Agent Primitive 不等于：

- 不等于系统本体
- 不等于系统级人格连续性
- 不等于长期记忆本身
- 不等于执行基础设施
- 不等于操作系统能力本身
- 不等于统一调度器

因此：

- `Prime Personality` 不是“因为它神秘所以成立”，而是人格级 Agent Primitive 的一种实例化
- `Session Host` 不是纯状态容器，而是 Session 级 Agent Primitive / Agent 容器
- `主 Context Compiler` 与 `进程 Context Compiler` 不是纯静态工具，而是编译器型 Agent Primitive
- `Agent 线程` 则是最直接的执行级 Agent Primitive

### 4.0E 与基础设施的边界

当前文档建议把系统中的对象分成两类：

#### A. Agent Primitive 家族
负责解释、判断、生成行为和输出结果。

包括：
- `Prime Personality`
- `Session Host`
- `主 Context Compiler`
- `进程 Context Compiler`
- `Agent 线程`

#### B. Infrastructure 家族
负责队列、执行、存储、接入、记忆底座与外部能力承接。

包括：
- `对外网关`
- `请求队列管理器`
- `Request Executor / Coordinator`
- `Thread Context / Runtime Memory Manager`
- `Memory Base`
- `SKILL lib`

这种划分的意义是：

- Agent Primitive 负责“做判断并产出动作意图”
- Infrastructure 负责“承托、约束、执行、保存和适配这些动作”

### 4.0F 层级实例化

当前架构中，Agent Primitive 至少可分为四种层级形态：

1. **人格级 Agent Primitive**
   - 对应 `Prime Personality`
   - 负责系统对外统一表达与高层解释

2. **Session 级 Agent Primitive**
   - 对应 `Session Host`
   - 负责某个 Session 范围内的局部治理、经验提升和上下文组织

3. **编译器型 Agent Primitive**
   - 对应 `主 Context Compiler` 与 `进程 Context Compiler`
   - 负责上下文筛选、压缩、收敛与组织

4. **执行级 Agent Primitive**
   - 对应 `Agent 线程`
   - 负责具体子任务执行、toolcall 生成与局部协作

### 4.0G 在 AgenticOS 中的哲学定位

在本系统中，Agent Primitive 最重要的哲学定位是：

**Agent 不具备系统视角下的完整智能。**

它只在自己的局部作用域内知道：

- 要做什么
- 怎么做
- 能调用什么

系统级智能来自：

- 多层 Agent Primitive 的组织
- Context Compiler 的上下文治理
- Memory Base 的长期沉淀
- 请求队列与执行基础设施的约束
- 基础 Prompt 核提供的身份与行为边界

因此，系统能力不是“某个 Agent 很聪明”，而是：

**基础模型能力 × Agent Primitive × 信息流治理**

### 4.0H 统一理解方式

因此，当前文档建议采用如下统一理解：

- `Prime Personality` 是人格级 Agent Primitive
- `Session Host` 是 Session 级 Agent Primitive / Agent 容器
- `主 Context Compiler` 与 `进程 Context Compiler` 是编译器型 Agent Primitive
- `Agent 线程` 是执行级 Agent Primitive

而 `Request Executor / Coordinator`、`请求队列管理器`、`对外网关` 这类对象，则更偏向系统基础设施，而不是 Agent Primitive 本体。

### 4.1 对外网关

`对外网关` 用于承接实际聊天软件或外部接入面，例如 Discord、Telegram 等。

职责：

- 处理各外部平台的接入协议与消息收发
- 将不同平台的外部输入转交给请求源层
- 接收系统内部产出的中间表示，并将其编译为各平台所需的最终输出格式

平台差异应尽量停留在网关层，而不是污染系统内部核心信息流。

### 4.2 内部中间表示

系统内部不直接围绕平台最终消息工作，而围绕统一的中间表示工作。

当前版本中，中间表示应尽量保持轻量化，并优先采用 JSON 作为基础承载形式。

它主要承载：

- 主体文本
- 少量图表 / 图片 / 文件的指示符
- 指示符对应的资源链接或资源引用

也就是说，它更接近：

**JSON 形式的文本主体 + 资源占位符 / 指示符 + 资源引用**

除了最终输出外，入口进入系统的自然语言消息也应尽量先收敛到这一类内部中间表示。

### 4.3 请求队列管理器

`请求队列管理器` 是统一的请求源层。

当前系统的所有自然语言输入，都应先进入这里，再串行化后送入 `Prime Personality`。

当前至少存在两类入口请求源：

1. 用户请求
2. 定时请求调度器触发的预存请求

这样设计的目的，是确保即使来自不同设备、不同平台或不同触发器的消息同时到达，也不会直接竞争 `Prime Personality` 或下游执行链路。

### 4.4 定时请求调度器

`定时请求调度器` 不是普通后台计时器，而是一个基于规则触发的预存消息队列调度层。

其本质更接近：

**主人格对未来自己的冰箱贴系统。**

它用于：

- 存放预先注册的请求或提醒
- 以延迟、定时、条件触发的方式在未来唤起这些请求
- 将触发后的请求以与用户输入等价的语义送入 `请求队列管理器`

### 4.5 Hook 保护机制

基于规则的自动调度不应由普通执行进程随意写入。

其写入能力应通过高权限 Hook 受控暴露，用于：

- 审核哪些信息可以写入未来请求队列
- 阻止一般进程随意篡改重要未来信息
- 保证“给主人格未来自己的留言”属于高权限行为，而不是普通任务副产物

### 4.6 Prime Personality（人格级高级 Agent）

`Prime Personality` 是跨 Session 的统一人格入口层。

职责：

- 作为用户首先接触的外显人格壳层
- 承载基础 Prompt 核
- 提供系统级解释框架
- 维持跨 Session 的身份连续性
- 生成系统内部统一表达与中间表示

关键性质：

- `Prime Personality` 本身应视为 **stateless**
- 它不依赖自身保存长期运行态
- 每次最终送往用户的回答，都必须重新依赖 `主 Context Compiler` 提供的上下文收敛结果

它不负责：

- 底层任务调度
- 进程管理
- 线程并发控制
- 具体 Task 执行

### 4.7 主 Context Compiler（编译器型高级 Agent）

`主 Context Compiler` 服务于 `Prime Personality`。

职责：

- 解释入口消息
- 维持主人格连续性
- 做入口级上下文收敛
- 将不同接入点的输入形式收敛为统一基础表达
- 仅向主人格暴露部分特殊系统能力（如网关编译 Skill）

### 4.8 Info Router

`Info Router` 本质上是提供给主人格使用的特殊 Skill / MCP。

它不是单纯的技术转发器，而是一个面向 Session 的系统级交互界面，用于：

- 让 `Prime Personality` 与不同 `Session Host` 直接双向交换消息
- 读取全量保存的执行过程与思考过程
- 决定请求应进入哪个 Session
- 判断应新建请求、复用上下文，还是仅返回轻量响应
- 将请求送入正确的 `Session Host`

### 4.9 Session Host（Session 级高级 Agent / Agent 容器）

`Session Host` 是单个 Session 的局部内核。

职责：

- 持有 Session 级状态
- 管理该 Session 内的请求与过程集合
- 调用 `进程 Context Compiler`
- 汇聚执行结果
- 将具有长期意义的经验提升并发送给 `Memory Base`

`Session` 是长期主体，承载持续性的局部上下文与任务空间。

### 4.10 进程 Context Compiler（编译器型高级 Agent）

`进程 Context Compiler` 服务于 `Session Host`。

职责：

- 面向具体 Session / Task 组织执行上下文
- 调用长期记忆、技能定义与检索结果
- 生成供执行层使用的上下文包

这个上下文包通常会进一步进入 `Thread Context / Runtime Memory Manager`，再被投影为具体执行单元可使用的运行态上下文快照。

### 4.11 Process N

`Process N` 表示 Session 内可并存的一组过程对象。

它们是被 `Session Host` 管理的局部运行过程集合，用于承载不同请求、不同阶段或不同任务线的状态与演化。

### 4.12 单个 Task 运行快照

真正被执行的不是整个 Session，而是某个 Task 的运行快照。

其本质是：

- Session 状态的局部可执行投影
- Task 状态的运行态视图
- 多 Agent 协作的局部沙箱

### 4.13 Request Executor / Coordinator

`Request Executor / Coordinator` 是跨 Session 的系统级执行界面，不是某个单独 Session 的私有对象。

它向上接受 Agent 产生的 toolcall / 执行请求，向下对接操作系统提供的功能与实际执行能力。

职责：

- 接收上层 Agent 的执行请求
- 协调局部消息流
- 驱动一次请求在 Task 快照中的实际执行
- 将局部执行结果汇总回运行态
- 作为跨 Session 的统一执行入口抑制竞争与冲突

### 4.14 Agent 线程调度器

`Agent 线程调度器` 负责在执行层内调度 Agent 线程实例。

它承担线程级编排职责，但不承担人格级解释职责。

### 4.15 Agent 线程（执行级原子 Agent）

`Agent 线程` 是通用模板的实例。

职责：

- 在给定上下文和规则下完成具体子工作
- 产生 toolcall / 执行请求
- 向 `Request Executor / Coordinator` 回报结果
- 通过 A2A 机制进行局部协作

### 4.16 Thread Context / Runtime Memory Manager

`Thread Context / Runtime Memory Manager` 是特殊上下文管理器。

其职责是：

- 管理运行态上下文的局部快照
- 在请求执行过程中为各 Agent 线程提供受控上下文视图
- 跟踪上下文在执行过程中的局部变化
- 进行上下文压缩
- 进行信息搜集
- 保证每个 Task 的全量信息被隔离存储
- 按时间顺序将相关快照与上下文材料沉淀到持久性记忆中，供 Context Compiler 检索
- 避免单次运行中的上下文漂移直接污染更高层 Session 结构

这些 Context Manager 在宏观上是同类组件的不同实例。

### 4.17 Memory Base

`Memory Base` 是统一记忆底座，不代表单一数据库。

它是一个宏观聚合层，内部可包含：

- 长期事实记忆
- 偏好与人格连续性记忆
- Session / workspace / global 分层记忆
- 项目知识与历史任务抽象
- 文档与笔记整理结果
- 实体、关系、主题、 canon 等高阶知识
- 面向检索的各种索引视图

知识库内部结构将在单独文档中维护，不在本 Kernel spec 中继续细拆。

### 4.18 SKILL lib

`SKILL lib` 更接近应用层能力定义源，而不是普通函数库。

它提供：

- Prompt 核来源
- 规则来源
- tool intents
- 能力边界
- 身份约束

---

## 5. 核心信息流

当前架构的主路径为：

用户
→ 对外网关
→ 统一中间表示收敛
→ 请求队列管理器
→ Prime Personality
→ Info Router
→ 选定 Session Host
→ 进程 Context Compiler 生成执行上下文包
→ Thread Context / Runtime Memory Manager 投影运行态上下文
→ Agent 线程调度器
→ Agent 线程
→ Request Executor / Coordinator
→ 操作系统 / 工具能力
→ 结果回流到 Session Host
→ Session Host 选择性向 Memory Base 提交长期经验
→ 再由 Info Router / Prime Personality 生成系统内部中间表示
→ 对外网关将中间表示编译为具体平台输出
→ 用户

其中需要特别强调：

- `Prime Personality` 是 stateless 的
- 每次最终返回给用户的结果都必须重新依赖 Context Compiler 收敛上下文
- `Prime Personality` 直接产出的是系统内部统一的中间表示，而不是平台最终消息
- 不同接入点的外层格式虽然不同，但最终应尽可能收敛为统一的基础 Prompt + 本轮对话信息结构；之后再由网关编译为平台特定输出

与此同时：

- `主 Context Compiler` 为入口层提供上下文装配
- `进程 Context Compiler` 为 Session / Task 层提供执行上下文装配
- `Thread Context / Runtime Memory Manager` 为具体执行单元提供基于快照的运行态上下文
- `Memory Base` 提供高优先级长期记忆候选，并接收 `Session Host` 提交的长期经验
- `SKILL lib` 提供规则、身份和能力边界

---

## 6. 两个核心闭环

### 6.1 生成执行闭环

请求源触发
→ 人格解释
→ 语义路由
→ Session 选定
→ 执行上下文编译
→ 多 Agent 协作执行
→ 结果返回用户

### 6.2 知识沉淀闭环

运行结果 / 中间结果
→ Session Host 判断其是否具有长期意义
→ 进入记忆与知识沉淀流程
→ 更新 Memory Base
→ 在后续 Context Compiler 中再次被利用

当前版本中，经验提升策略可以先粗略依赖模型判断。

例如：

- 当系统观察到多次重复错误
- 或相同问题反复暴露出同类失败模式

则可将其视为具有长期价值的经验候选，再由 `Session Host` 提交给 `Memory Base`。

这两个闭环共同决定系统是否具备长期连续性。

---

## 7. Memory Base 的宏观定位

当前图中的 `Memory Base` 是统一记忆底座的总括表达。

它不是某个具体实现，而是所有记忆库功能的统一抽象入口。

当前阶段不必在这份 Kernel 架构文档中继续细拆其内部实现，因为知识库内部结构将以单独文档维护。

在本 spec 中，应保留以下理解：

1. 它是长期连续性与知识沉淀的总入口。
2. 它同时服务人格连续性与任务连续性。
3. 它通常通过 Context Compiler 被选择性使用，而不是直接裸喂给执行层。
4. 它内部允许异构，不要求单一格式或单一索引。

---

## 8. 当前稳定锚点

以下判断视为当前版本的稳定架构结论：

1. 系统不是“一个大 Agent”，而是一个长期运行的信息流内核。
2. 外部平台接入差异应主要停留在对外网关层，而不是污染系统核心内部流。
3. 系统入口不是单一用户输入，而是统一的请求源层。
4. 所有自然语言输入都必须先进入请求队列管理器，再串行化送入 `Prime Personality`，以避免多设备或多入口并发竞争。
5. 用户请求与定时调度触发的预存请求在进入 `Prime Personality` 前都统一进入请求源层。
6. LLM 是可替换插件，不是系统本体。
7. 人格连续性来自信息流结构、长期记忆和基础 Prompt 核。
8. `Agent` 是系统中的统一行为载体与基础算子，而不是仅指执行层的 `Agent 线程`。
9. `Prime Personality` 是跨 Session 的统一人格入口，且本身是 stateless 的。
10. `Info Router` 本质上是提供给主人格使用的特殊 Skill / MCP，并支持主人格与 `Session Host` 的直接双向消息交换。
11. 定时请求调度器本质上是主人格对未来自己的留言系统，其写入侧受高权限 Hook 保护。
12. `Session` 是长期主体。
13. 真正被执行的是单个 Task 的运行快照，而不是整个 Session。
14. `Request Executor / Coordinator` 是跨 Session 的系统级执行界面，用于抑制并发竞争，并向下对接操作系统能力。
15. Agent 是通用模板的实例，但会以人格级、Session 级、编译器型和执行级等不同形态出现；其能力主要依赖基础模型，而不是被视为系统级独立智能主体。
16. 原子级 Agent 与高级 Agent 的关键区别，在于是否借助 Context Manager / Context Compiler 参与自身可用上下文与记忆的再编辑。
17. `主 Context Compiler` 与 `进程 Context Compiler` 本质上是同一组件在不同作用域下的实例。
18. 执行级上下文不会被简单直接长期持有，而会进一步经由 `Thread Context / Runtime Memory Manager` 转化为基于快照的运行态上下文视图。
19. 所有 Context Manager 都具备快照、上下文压缩和信息搜集能力，并负责按时间顺序沉淀可检索的 Task 全量信息。
20. `Prime Personality` 直接输出的是系统内部统一的中间表示，而不是平台最终消息。
21. 对外网关负责将内部中间表示编译为 Discord、Telegram 等平台特定输出。
22. 当前版本的内部中间表示应尽量轻量化，并优先采用 JSON 作为基础承载形式；入口消息也应收敛到同类结构。
23. 网关编译的主要职责应集中在不同平台对图片、文件、图表等资源的嵌入方式适配，而不是重新改写核心语义内容。
24. 网关中的“中间表示 → 平台输出”编译过程当前可先作为特殊 Skill 仅对 `Prime Personality` 受控开放。
25. `Session Host` 负责将真正具有长期意义的经验选择性提交给 `Memory Base`。
26. 当前版本中，经验提升可先粗略依赖模型判断，例如对多次重复错误进行经验沉淀。
27. `Memory Base` 是统一记忆底座，不是单点实现。
28. `SKILL lib` 是能力、规则与身份约束来源。
29. 图中 `*N` 的对象与完整画出的对象是平等展开，不是从属特例。

---

## 9. 当前阶段最值得继续思考的问题

1. `Session Host` 与更高层全局 Kernel 的关系是否需要再次显式画出。
2. 高权限 Hook 的授权边界应如何定义，才能既允许未来留言，又避免普通进程污染关键请求队列。
3. 多接入点在进入入口编译器之前，哪些平台差异必须保留，哪些应强制归一化。
4. 作为特殊 Skill 开放的网关编译过程，未来何时需要从“先跑起来”升级到更严格的治理机制。
5. 人格级、Session 级、编译器型、执行级 Agent 之间，未来是否需要一套更形式化的统一抽象，以更清楚地区分“基础算子能力”与“系统级智能组织”。

## 10. 备注

本文档为当前版本的精简架构说明，仅保留最新有效设计。后续新增内容应直接覆盖旧判断，而不是继续叠加历史版本。

