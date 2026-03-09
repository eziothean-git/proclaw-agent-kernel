# Agent Kernel Architecture Spec 本轮合并摘要

## 主要结构性调整

1. **重构了整份文档结构**
   - 从“按对象顺次堆叠”改为“目标与范围 → 核心哲学 → 统一抽象模型 → 上下文模型 → 关键对象 → 信息流 → 闭环 → 稳定锚点 → 延后项 → 开放问题”。
   - 目的是让文档更适合作为后续实现与继续讨论的稳定底座，而不是历史讨论堆栈。

2. **正式把 `Info Router` 收敛为 `Agentic OS Interface Skill`**
   - 明确它是主人格使用的特权系统 Skill / MCP。
   - 不再把它表述为独立 agent 节点。

3. **重写了 `主 Context Compiler` 的定位**
   - 明确为“规则优先、受限特权、编译器型高级 Agent Primitive”。
   - 强调第一轮应纯规则编译，必要时才触发受限上下文工具补丁。
   - 明确它只能修改当前轮的 `Compiled Context`，不能直接改写 Session 真相或长期记忆。

4. **修正了执行层的核心结构**
   - 不再把 `Agent 线程` 理解为不断膨胀的聊天上下文。
   - 改为“`Immutable Input Bundle` + `Event Log` + `Working Set Builder` + `Runtime Working Set` + `Artifact Slots`”的受控结构。
   - 正式把执行循环表述为 SEE-ACT-UPDATE。

5. **明确了原子级 Agent 的边界**
   - 补充了“规则驱动的运行态工作集更新，不等于上下文再生产”。
   - 因而当前 `Agent 线程` 仍可被定义为执行级原子 Agent。

6. **明确延后 A2A**
   - 当前稳定版不把自由式 A2A 作为默认执行机制。
   - 如果未来需要多线程协作，优先考虑调度器介导的子任务分派与 artifact 交换。

7. **澄清了基础设施边界**
   - 明确 `Request Executor / Coordinator` 是跨 Session 的共享执行基础设施。
   - 明确 `Agent 线程调度器` 属于 Infrastructure，而不是新的 agent 层级。

8. **加入 embodied 机器人控制语境**
   - 明确该 Kernel 同时服务于软件 AgenticOS 与 embodied 控制系统。
   - 新增 embodied Session、小脑控制层、导航 / 基座模型层等说明。
   - 强调物理交互面应被收敛到少量高权限模块中。

## 这轮新增的关键术语

- `Agentic OS Interface Skill`
- `Compiled Context`
- `Runtime Working Context`
- `Event Log / Snapshot`
- `Artifact Slots`
- `Immutable Input Bundle`
- `Working Set Builder`
- embodied Session
- 小脑控制层

## 当前最重要的稳定结论

- 系统是长期运行的信息流内核，不是一个大 Agent。
- `Prime Personality` 是 stateless 的跨 Session 人格入口。
- `主 Context Compiler` 是规则优先的特权编译器，而不是另一个通用聊天 agent。
- 执行线程依靠事件日志 + 有界工作集维持循环，而不是依赖长对话历史。
- 当前执行层默认不采用自由式 A2A。
- embodied 控制是同一 Kernel 上的一组高权限执行后端，而不是独立第二套内核。
