# Agent Thread Runtime 架构文档

## 概述

Agent Thread Runtime 是 Agent Kernel 的最底层执行模块，实现了原子级 Agent 的执行基础设施。它采用 **Event Log + Working Set** 架构替代传统的对话历史模型，通过规则驱动的上下文构建实现有界、可控的 Agent 执行。

## 核心设计原则

### 1. Event Log + Working Set 模型

**传统模型 vs 新模型：**

```
传统模型：
[对话历史] → [不断增长] → [上下文爆炸]

新模型：
[完整事件日志] → [规则筛选] → [有界工作集] → [固定大小Prompt]
```

**优势：**
- **防止上下文膨胀**：Working Set 保持固定大小
- **确定性**：规则驱动的上下文选择，非LLM决策
- **可观测性**：完整事件日志供上层诊断
- **可干预性**：上层可以查看全量日志并干预执行

### 2. SEE-ACT-UPDATE 循环

Agent Thread 的标准执行循环：

```
SEE (观察)
   ↓
构建 Working Set ← 从 Event Log + Artifacts + Rules
   ↓
ACT (行动)
   ↓
调用 LLM 生成意图
   ↓
解析意图 (tool_call / phase_transition / final_answer)
   ↓
UPDATE (更新)
   ↓
执行操作 → 记录事件到 Event Log
   ↓
更新 Artifacts → 循环继续
```

### 3. Phase-based 执行

支持三个执行阶段：

- **EXPLORE** (探索)：信息收集、上下文理解
- **EXECUTE** (执行)：基于收集的信息执行动作
- **COMPLETE** (完成)：总结结果、收尾

Phase 由 Agent 自主决定切换，但上层可以强制干预。

## 模块架构

### 模块依赖关系

```
┌─────────────────────────────────────────────┐
│          Agent Thread (Runtime)             │
├─────────────────────────────────────────────┤
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  │
│  │ Event    │  │ Working  │  │ Output   │  │
│  │ Log      │  │ Set      │  │ Parser   │  │
│  │ Manager  │  │ Builder  │  │          │  │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  │
│       │             │             │        │
│       └─────────────┴─────────────┘        │
│                     │                      │
│              ┌──────────────┐              │
│              │ SEE-ACT-     │              │
│              │ UPDATE Loop  │              │
│              └──────────────┘              │
└─────────────────────┬───────────────────────┘
                      │
┌─────────────────────┴───────────────────────┐
│      Request Execution Coordinator          │
├─────────────────────────────────────────────┤
│  ┌──────────────┐    ┌──────────────────┐  │
│  │ Local Skill  │    │ Remote Executor  │  │
│  │ Registry     │    │ Client           │  │
│  └──────────────┘    └──────────────────┘  │
└─────────────────────┬───────────────────────┘
                      │
┌─────────────────────┴───────────────────────┐
│        Agentic OS Interface Skill           │
│     (系统级协调 + 原子操作管理)              │
└─────────────────────────────────────────────┘
```

## 核心组件详解

### 1. Event Log Manager

**职责：**
- 记录完整的执行事件流
- 提供事件查询和过滤
- 支持全量导出供上层查看

**事件类型：**
```python
EventType:
- AGENT_ACTION      # Agent 发起的动作
- TOOL_CALL         # 工具调用请求
- TOOL_RESULT       # 工具执行结果
- OBSERVATION       # 环境观察
- PHASE_CHANGE      # 阶段切换
- ARTIFACT_UPDATE   # 产物更新
- ERROR             # 错误事件
- SYSTEM            # 系统事件
```

**使用示例：**
```python
from thread_runtime.event_log import EventLogManager

# 创建 Event Log
event_log = EventLogManager(task_id="task_001")

# 记录工具调用
event_log.append_tool_call(
    actor="thread_001",
    phase=Phase.EXPLORE,
    skill_name="fs-skill",
    tool_name="read_file",
    parameters={"path": "/tmp/test.txt"},
)

# 记录工具结果
event_log.append_tool_result(
    actor="thread_001",
    phase=Phase.EXPLORE,
    skill_name="fs-skill",
    tool_name="read_file",
    success=True,
    result={"content": "Hello World"},
)

# 查询最近事件
recent = event_log.get_recent(count=10)

# 导出全量日志（供上层查看）
full_log = event_log.export_for_debug()
```

### 2. Working Set Builder

**职责：**
- 根据规则从 Event Log 构建有界 Working Set
- 管理 Token 预算
- 支持 Phase-specific 的上下文选择

**规则配置** (`config/working_set_rules.yaml`)：

```yaml
phases:
  explore:
    slot_selection:
      slot_types: [module_map, symbol_index, context_report]
      max_slots: 3
      priority_threshold: 5
    observation_selection:
      max_count: 10
      lookback_steps: 20
      priority_event_types: [tool_result, observation, error]
  
  execute:
    slot_selection:
      slot_types: [patch_plan, dependency_summary, test_plan]
      max_slots: 4
      priority_threshold: 5
    observation_selection:
      max_count: 5
      lookback_steps: 10
      priority_event_types: [tool_result, error]

token_budget:
  max_total: 4000
  reserved_for_immutable: 500
  reserved_for_observations: 1500
  reserved_for_artifacts: 1500
  reserved_for_notes: 500
```

**使用示例：**
```python
from thread_runtime.working_set_builder import WorkingSetBuilder
from thread_runtime.models import ArtifactSlot, Phase

# 创建 Builder
builder = WorkingSetBuilder("config/working_set_rules.yaml")

# 创建 Artifacts
artifacts = {
    "module_map": ArtifactSlot(
        slot_id="slot_001",
        slot_type="module_map",
        content={"modules": ["main", "utils"]},
        priority=8,
        phase_created=Phase.EXPLORE,
    ),
}

# 构建 Working Set
working_set = builder.build(
    task_id="task_001",
    task_goal="Refactor main module",
    event_log=event_log,
    artifact_slots=artifacts,
    immutable_input={"constraints": ["no breaking changes"]},
    current_phase=Phase.EXPLORE,
    step_number=5,
)

# 转换为 Prompt
prompt = working_set.to_prompt()
```

**Working Set 结构：**
```python
WorkingSet:
- task_goal              # 任务目标
- current_phase          # 当前阶段
- step_number           # 当前步骤
- immutable_context     # 不可变约束
- confirmed_facts       # 已确认的事实
- recent_observations   # 最近的观察
- active_artifacts      # 激活的产物
- previous_action_result # 上一步结果
- pending_decisions     # 待决策事项
- context_notes         # 上下文备注
- token_estimate        # Token 估算
```

### 3. Agent Output Parser

**职责：**
- 解析 LLM 输出为结构化意图
- 支持结构化（YAML/JSON）和启发式解析
- Phase-specific 解析策略

**支持的意图类型：**
```python
IntentType:
- TOOL_CALL        # 工具调用请求
- FINAL_ANSWER     # 最终答案
- CLARIFICATION    # 需要澄清
- PHASE_TRANSITION # 阶段切换
- ERROR            # 错误
- UNKNOWN          # 未知
```

**输出格式示例：**

```yaml
# Tool Call
intent: tool_call
reasoning: "需要读取文件内容"
tool_calls:
  - skill: fs-skill
    tool: read_file
    parameters:
      path: "/path/to/file"

# Phase Transition
intent: phase_transition
from_phase: explore
to_phase: execute
reason: "已收集足够上下文"
artifacts_to_finalize: [module_map, symbol_index]

# Final Answer
intent: final_answer
answer: "任务完成结果..."
success: true
```

**使用示例：**
```python
from thread_runtime.output_parser import get_output_parser
from thread_runtime.models import Phase

parser = get_output_parser()

# LLM 输出
output = """```yaml
intent: tool_call
tool_calls:
  - skill: fs-skill
    tool: list_directory
    parameters:
      path: "/tmp"
```"""

# 解析
parsed = parser.parse(output, Phase.EXPLORE)

# 处理结果
if parsed.intent_type == IntentType.TOOL_CALL:
    for tool_call in parsed.tool_calls:
        print(f"Call {tool_call.skill_name}.{tool_call.tool_name}")
elif parsed.intent_type == IntentType.PHASE_TRANSITION:
    print(f"Transition to {parsed.phase_transition.to_phase}")
```

### 4. Request Execution Coordinator

**职责：**
- 统一的执行接口
- 路由到本地或远程技能
- 管理执行生命周期
- 确保执行原子性

**请求类型：**
```python
RequestType:
- SKILL_CALL        # 技能调用
- SYSTEM_OPERATION  # 系统操作
- INTERNAL          # 内部操作
```

**路由策略：**
1. 检查 `remote_only` 列表 → 强制远程
2. 检查 `local_priority` 列表 → 优先本地
3. 检查本地注册表 → 本地可用则本地执行
4. 否则 → 远程执行

**配置** (`config/coordinator.yaml`)：
```yaml
local_priority:
  - fs-skill
  - shell-skill

remote_only: []

default_routing: "auto"

timeouts:
  local_default: 30000
  remote_default: 60000
  system_operation: 10000
```

**使用示例：**
```python
from executors_client.coordinator_interface import get_execution_coordinator
from thread_runtime.models import ExecutionRequest, RequestType

coordinator = get_execution_coordinator()

# 创建请求
request = ExecutionRequest(
    request_id="exec_001",
    request_type=RequestType.SKILL_CALL,
    source="thread_001",
    target="fs-skill",
    action="read_file",
    parameters={"path": "/tmp/test.txt"},
    context={"session_id": "sess_001"},
    priority=5,
    timeout_ms=30000,
)

# 提交并执行
ticket = await coordinator.submit(request)
result = await coordinator.execute(ticket)

if result.success:
    print(f"Result: {result.result}")
else:
    print(f"Error: {result.error}")
```

### 5. Agentic OS Interface Skill

**职责：**
- 系统级协调（跨 Session）
- 消息路由和交换
- 状态查询
- 任务生命周期控制
- 确保操作原子性

**核心功能：**

```python
# 路由决策
routing_decision = await os_interface.route_request(
    request=request,
    intent="code_refactoring",
    context_hints={},
)

# 状态查询
session_state = await os_interface.query_session_state(session_id)
task_state = await os_interface.query_task_state(task_id)

# 消息交换
message = SystemMessage(
    msg_id="msg_001",
    source="prime_personality",
    target="session_001",
    msg_type="command",
    content={"command": "pause", "reason": "review"},
    priority=8,
)
result = await os_interface.send_message(message)

# 任务控制（干预 API）
await os_interface.pause_session(session_id, reason="review")
await os_interface.resume_session(session_id)
await os_interface.cancel_task(task_id, reason="obsolete")

# 线程控制
await os_interface.pause_thread(thread_id)
await os_interface.resume_thread(thread_id)
log = await os_interface.get_thread_full_log(thread_id)  # 供上层查看
await os_interface.update_thread_context(thread_id, updates={"phase": "execute"})
```

**原子性保证：**
使用 `AtomicOperationManager` 确保所有操作原子执行：
```python
async with lock:
    # 执行操作
    result = await operation()
    # 记录日志
    # 失败时回滚（如果提供 rollback 函数）
```

### 6. Agent Thread

**完整的 SEE-ACT-UPDATE 实现：**

```python
class AgentThread:
    def __init__(self, task, compiled_context, coordinator, ws_builder):
        # 核心组件
        self.coordinator = coordinator
        self.ws_builder = ws_builder
        self.parser = get_output_parser()
        
        # 状态
        self.event_log = EventLogManager(task.id)
        self.artifacts = {}
        self.current_phase = Phase.EXPLORE
        self.step_count = 0
    
    async def run(self):
        while self.step_count < self.max_steps:
            # SEE: 构建 Working Set
            working_set = self._build_working_set()
            
            # ACT: 生成并解析动作
            raw_output = await self._generate_action(working_set)
            parsed = self.parser.parse(raw_output, self.current_phase)
            
            # 处理意图
            if parsed.intent_type == IntentType.FINAL_ANSWER:
                return self._handle_final_answer(parsed)
            elif parsed.intent_type == IntentType.TOOL_CALL:
                await self._handle_tool_calls(parsed)
            elif parsed.intent_type == IntentType.PHASE_TRANSITION:
                await self._handle_phase_transition(parsed)
            
            # UPDATE: 更新状态（事件已记录，artifacts 已更新）
```

**使用示例：**
```python
from thread_runtime.agent_thread import AgentThread

# 创建 Agent Thread
agent = AgentThread(
    task=task_snapshot,
    compiled_context=compiled_context,
    coordinator=get_execution_coordinator(),
    ws_builder=WorkingSetBuilder(),
)

# 运行
result = await agent.run()

# 检查事件日志（上层视角）
log_export = agent.get_event_log_export()
print(f"Executed {log_export['event_log']['event_count']} events")
```

### 7. Scheduler (with Intervention APIs)

**职责：**
- 管理 Agent Thread 生命周期
- 提供上层干预接口

**干预 API：**

```python
scheduler = get_scheduler()

# 暂停/恢复
await scheduler.pause_task(task_id, reason="Need to review")
await scheduler.resume_task(task_id)

# 查看线程状态（上层检查）
log = await scheduler.get_thread_log(task_id)
info = scheduler.get_active_thread_info(task_id)

# 修改执行状态
await scheduler.update_thread_phase(task_id, Phase.EXECUTE)
await scheduler.update_thread_context(task_id, {
    "max_steps": 100,
    "context_notes": ["Additional constraint: be careful"],
})

# 列出所有活动线程
threads = scheduler.list_active_threads()
```

## 配置总览

### Working Set Rules
`config/working_set_rules.yaml`
- Phase-specific 槽位选择规则
- Artifact 优先级
- Token 预算分配

### Coordinator Routing
`config/coordinator.yaml`
- 本地优先的技能列表
- 强制远程的技能列表
- 超时和重试配置

## 数据流示例

### 完整的任务执行流程

```
1. Scheduler 创建 AgentThread
   ↓
2. AgentThread.run() 开始 SEE-ACT-UPDATE 循环
   ↓
3. SEE: WorkingSetBuilder 构建 Working Set
   - 从 Event Log 获取最近事件
   - 选择 Phase-appropriate Artifacts
   - 应用 Token 预算
   ↓
4. ACT: Agent 生成输出
   - LLM 调用 with Working Set
   - Output Parser 解析意图
   ↓
5. UPDATE: 根据意图类型处理
   
   Case 1: TOOL_CALL
   - 通过 Coordinator 提交 ExecutionRequest
   - Coordinator 路由到 Local/Remote Skill
   - 执行结果记录到 Event Log
   - 继续循环
   
   Case 2: PHASE_TRANSITION
   - 验证转换有效性
   - 更新 current_phase
   - 记录 PHASE_CHANGE 事件
   - 继续循环（使用新 Phase 的规则）
   
   Case 3: FINAL_ANSWER
   - 构建 AgentOutput
   - 返回给 Scheduler
   ↓
6. 结束
```

### 上层干预流程

```
上层（Prime Personality / Session Host）
   ↓
调用 scheduler.get_thread_log(task_id)
   ↓
查看全量 Event Log
   ↓
决定干预：scheduler.update_thread_phase(task_id, "execute")
   ↓
Agent Thread 在下一轮循环中使用新 Phase
   ↓
Working Set Builder 应用新 Phase 的规则
   ↓
执行继续...
```

## 最佳实践

### 1. Working Set 优化
- 为不同 Phase 配置合适的 slot_types
- 调整 token_budget 匹配模型限制
- 使用 priority_threshold 过滤低优先级 artifacts

### 2. Event Log 使用
- 始终记录关键事件（tool_call, tool_result, phase_change）
- 使用 metadata 存储额外信息
- 定期导出日志进行诊断

### 3. 干预策略
- 优先使用 pause/resume 进行临时干预
- 使用 update_thread_phase 强制切换阶段
- 避免在 Agent 执行中途频繁干预

### 4. 技能路由
- 频繁使用的简单技能 → Local
- 复杂/外部依赖 → Remote
- 在 coordinator.yaml 中明确定义路由规则

## 故障排查

### Token 超出预算
- 减少 max_slots
- 降低 lookback_steps
- 增加 priority_threshold

### 意图解析失败
- 检查 LLM prompt 是否包含输出格式说明
- 查看 parser 的 confidence 分数
- 考虑添加更多启发式规则

### 执行超时
- 调整 timeout_ms
- 检查 Skill 性能
- 考虑异步执行模式

## API 快速参考

详见各模块的 Python 类型签名和 docstrings。

核心入口：
- `AgentThread.run()` - 执行 Agent
- `WorkingSetBuilder.build()` - 构建上下文
- `get_output_parser().parse()` - 解析意图
- `get_execution_coordinator().execute()` - 执行请求
- `get_scheduler().get_thread_log()` - 查看状态
- `get_os_interface_skill().pause_thread()` - 干预执行
