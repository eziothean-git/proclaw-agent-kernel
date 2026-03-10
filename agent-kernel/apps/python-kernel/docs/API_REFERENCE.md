# Agent Thread API 参考手册

## 目录
1. [Models (thread_runtime/models.py)](#models)
2. [Event Log Manager (thread_runtime/event_log.py)](#event-log-manager)
3. [Working Set Builder (thread_runtime/working_set_builder.py)](#working-set-builder)
4. [Output Parser (thread_runtime/output_parser.py)](#output-parser)
5. [Execution Coordinator (executors_client/coordinator_interface.py)](#execution-coordinator)
6. [OS Interface (skills/agentic_os_interface.py)](#os-interface)
7. [Agent Thread (thread_runtime/agent_thread.py)](#agent-thread)
8. [Scheduler (thread_runtime/scheduler.py)](#scheduler)

---

## Models

### Phase
```python
class Phase(str, Enum):
    EXPLORE = "explore"      # 信息收集阶段
    EXECUTE = "execute"      # 动作执行阶段
    COMPLETE = "complete"    # 完成阶段
```

### Event
```python
class Event(BaseModel):
    event_id: str                    # 唯一标识
    timestamp: datetime              # 时间戳
    event_type: EventType            # 事件类型
    actor: str                       # 执行者ID
    phase: Phase                     # 所属阶段
    content: dict[str, Any]          # 事件内容
    metadata: dict[str, Any]         # 元数据
```

### EventLog
```python
class EventLog(BaseModel):
    task_id: str
    events: list[Event]
    
    def append(self, event: Event) → None
    def get_recent(count: int, event_type: EventType | None = None, phase: Phase | None = None) → list[Event]
    def get_by_phase(self, phase: Phase) → list[Event]
    def get_by_type(self, event_type: EventType) → list[Event]
    def export_for_debug(self) → dict[str, Any]
```

### ArtifactSlot
```python
class ArtifactSlot(BaseModel):
    slot_id: str                     # 槽位ID
    slot_type: str                   # 类型(module_map, patch_plan等)
    content: Any                     # 内容
    priority: int                    # 优先级(1-10)
    phase_created: Phase             # 创建阶段
    created_at: datetime
    updated_at: datetime
```

### WorkingSet
```python
class WorkingSet(BaseModel):
    task_id: str
    task_goal: str
    current_phase: Phase
    step_number: int
    immutable_context: dict[str, Any]
    confirmed_facts: list[str]
    recent_observations: list[dict[str, Any]]
    active_artifacts: dict[str, Any]
    previous_action_result: dict[str, Any] | None
    pending_decisions: list[str]
    context_notes: list[str]
    token_estimate: int
    built_at: datetime
    
    def to_prompt(self) → str        # 转换为Prompt文本
```

### ParsedIntent
```python
class ParsedIntent(BaseModel):
    intent_type: IntentType          # 意图类型
    confidence: float               # 置信度(0-1)
    raw_content: str                # 原始内容
    structured_data: dict[str, Any] # 结构化数据
    tool_calls: list[ToolCallIntent]
    phase_transition: PhaseTransitionIntent | None
    final_answer: str | None
    clarification_request: str | None
    error_message: str | None
```

### ExecutionRequest
```python
class ExecutionRequest(BaseModel):
    request_id: str
    request_type: RequestType        # SKILL_CALL | SYSTEM_OPERATION | INTERNAL
    source: str                      # 请求者ID
    target: str                      # 目标(技能名或系统端点)
    action: str                      # 具体动作
    parameters: dict[str, Any]
    context: dict[str, Any]
    priority: int                   # 1-10
    timeout_ms: int
    created_at: datetime
```

### ExecutionResult
```python
class ExecutionResult(BaseModel):
    ticket_id: str
    success: bool
    result: Any | None
    error: str | None
    execution_time_ms: int
    events_generated: list[str]     # 生成的事件ID
    artifacts_produced: list[str]   # 生成的Artifact ID
```

---

## Event Log Manager

### 构造函数
```python
EventLogManager(task_id: str)
```

### 方法

#### append
```python
def append(
    self,
    event_type: EventType,
    actor: str,
    phase: Phase,
    content: dict[str, Any],
    metadata: dict[str, Any] | None = None,
) → Event
```
**描述：** 追加一个通用事件

**参数：**
- `event_type`: 事件类型
- `actor`: 执行者ID
- `phase`: 当前阶段
- `content`: 事件内容
- `metadata`: 可选元数据

**返回：** 创建的 Event 对象

---

#### append_tool_call
```python
def append_tool_call(
    self,
    actor: str,
    phase: Phase,
    skill_name: str,
    tool_name: str,
    parameters: dict[str, Any],
) → Event
```
**描述：** 记录工具调用事件（便捷方法）

**示例：**
```python
event_log.append_tool_call(
    actor="thread_001",
    phase=Phase.EXPLORE,
    skill_name="fs-skill",
    tool_name="read_file",
    parameters={"path": "/tmp/test.txt"},
)
```

---

#### append_tool_result
```python
def append_tool_result(
    self,
    actor: str,
    phase: Phase,
    skill_name: str,
    tool_name: str,
    success: bool,
    result: Any,
    error: str | None = None,
) → Event
```
**描述：** 记录工具执行结果

---

#### append_observation
```python
def append_observation(
    self,
    actor: str,
    phase: Phase,
    observation_type: str,
    content: Any,
    summary: str = "",
) → Event
```
**描述：** 记录环境观察

---

#### append_phase_change
```python
def append_phase_change(
    self,
    actor: str,
    from_phase: Phase,
    to_phase: Phase,
    reason: str = "",
) → Event
```
**描述：** 记录阶段切换

---

#### get_recent
```python
def get_recent(
    self,
    count: int = 10,
    event_type: EventType | None = None,
    phase: Phase | None = None,
) → list[Event]
```
**描述：** 获取最近N条事件，支持过滤

---

#### export_for_debug
```python
def export_for_debug(self) → dict[str, Any]
```
**描述：** 导出完整日志供调试

**返回示例：**
```python
{
    "task_id": "task_001",
    "event_count": 25,
    "events": [...],
    "phase_summary": {
        "explore": 15,
        "execute": 8,
        "complete": 2
    }
}
```

---

## Working Set Builder

### 构造函数
```python
WorkingSetBuilder(config_path: str | None = None)
```
**参数：**
- `config_path`: YAML配置文件路径，None则使用默认配置

---

### 主要方法

#### build
```python
def build(
    self,
    task_id: str,
    task_goal: str,
    event_log: EventLog | EventLogManager,
    artifact_slots: dict[str, ArtifactSlot],
    immutable_input: dict[str, Any],
    current_phase: Phase,
    step_number: int = 1,
    confirmed_facts: list[str] | None = None,
    pending_decisions: list[str] | None = None,
    context_notes: list[str] | None = None,
) → WorkingSet
```
**描述：** 构建 Working Set

**流程：**
1. 获取当前Phase的规则
2. 选择符合条件的Artifacts
3. 筛选最近的Observations
4. 获取上一步结果
5. 组装Working Set
6. Token估算和截断

**示例：**
```python
working_set = builder.build(
    task_id="task_001",
    task_goal="Refactor code",
    event_log=event_log,
    artifact_slots=artifacts,
    immutable_input={"constraints": ["no breaking changes"]},
    current_phase=Phase.EXPLORE,
    step_number=5,
)
```

---

#### get_config_summary
```python
def get_config_summary(self) → dict[str, Any]
```
**描述：** 获取配置摘要

---

## Output Parser

### 全局实例获取
```python
parser = get_output_parser()
```

### 主要方法

#### parse
```python
def parse(
    self,
    raw_output: str,
    current_phase: Phase,
) → ParsedIntent
```
**描述：** 解析LLM输出

**解析顺序：**
1. 尝试JSON代码块解析
2. 尝试YAML代码块解析
3. 尝试裸JSON/YAML解析
4. 启发式解析（非结构化文本）

**返回：** ParsedIntent包含解析后的意图和结构化数据

**示例：**
```python
output = """```yaml
intent: tool_call
tool_calls:
  - skill: fs-skill
    tool: read_file
    parameters:
      path: "/test.txt"
```"""

parsed = parser.parse(output, Phase.EXPLORE)

if parsed.intent_type == IntentType.TOOL_CALL:
    for tc in parsed.tool_calls:
        print(f"{tc.skill_name}.{tc.tool_name}")
```

---

## Execution Coordinator

### 全局实例获取
```python
coordinator = get_execution_coordinator()
```

### 主要方法

#### submit
```python
async def submit(self, request: ExecutionRequest) → ExecutionTicket
```
**描述：** 提交执行请求

**示例：**
```python
request = ExecutionRequest(
    request_id="exec_001",
    request_type=RequestType.SKILL_CALL,
    source="thread_001",
    target="fs-skill",
    action="read_file",
    parameters={"path": "/test.txt"},
    priority=5,
    timeout_ms=30000,
)

ticket = await coordinator.submit(request)
```

---

#### execute
```python
async def execute(self, ticket: ExecutionTicket) → ExecutionResult
```
**描述：** 执行已提交的请求

**路由逻辑：**
1. SKILL_CALL → 路由到本地或远程技能
2. SYSTEM_OPERATION → 路由到OS Interface
3. INTERNAL → 内部处理

**示例：**
```python
result = await coordinator.execute(ticket)

if result.success:
    print(f"Success: {result.result}")
else:
    print(f"Failed: {result.error}")
```

---

#### cancel
```python
async def cancel(self, ticket_id: str, reason: str = "") → bool
```
**描述：** 取消执行

---

#### configure_routing
```python
def configure_routing(
    self,
    local_priority: list[str] | None = None,
    remote_only: list[str] | None = None,
) → None
```
**描述：** 配置路由规则

**示例：**
```python
coordinator.configure_routing(
    local_priority=["fs-skill", "shell-skill"],
    remote_only=["browser-automation"],
)
```

---

## OS Interface

### 全局实例获取
```python
os_interface = get_os_interface_skill()
```

### 生命周期方法

#### start / stop
```python
async def start(self) → None
async def stop(self) → None
```
**描述：** 启动/停止消息处理循环

---

### 路由方法

#### route_request
```python
async def route_request(
    self,
    request: Request,
    intent: str,
    context_hints: dict[str, Any],
) → RoutingDecision
```
**描述：** 决定请求路由目标

**返回：**
```python
RoutingDecision(
    decision_type="new_session" | "reuse_session" | "light_response",
    target_session_id=str | None,
    reason=str,
    confidence=float,
)
```

---

### 状态查询

#### query_session_state
```python
async def query_session_state(self, session_id: str) → SessionState | None
```

#### query_task_state
```python
async def query_task_state(self, task_id: str) → dict[str, Any] | None
```

#### get_thread_full_log
```python
async def get_thread_full_log(self, thread_id: str) → dict[str, Any] | None
```
**描述：** 获取线程完整事件日志（上层查看）

---

### 消息交换

#### send_message
```python
async def send_message(self, message: SystemMessage) → SystemOperationResult
```

#### broadcast
```python
async def broadcast(
    self,
    message: SystemMessage,
    target_sessions: list[str],
) → SystemOperationResult
```

---

### 控制方法（干预API）

#### pause_session / resume_session
```python
async def pause_session(self, session_id: str, reason: str = "") → SystemOperationResult
async def resume_session(self, session_id: str) → SystemOperationResult
```

#### pause_thread / resume_thread
```python
async def pause_thread(self, thread_id: str, reason: str = "") → SystemOperationResult
async def resume_thread(self, thread_id: str) → SystemOperationResult
```

#### update_thread_context
```python
async def update_thread_context(
    self,
    thread_id: str,
    updates: dict[str, Any],
) → SystemOperationResult
```
**描述：** 更新线程上下文（phase, max_steps等）

**示例：**
```python
await os_interface.update_thread_context(
    thread_id="thread_001",
    updates={
        "phase": "execute",
        "max_steps": 100,
    },
)
```

---

## Agent Thread

### 构造函数
```python
AgentThread(
    task: TaskSnapshot,
    compiled_context: CompiledContext,
    coordinator: Any | None = None,
    ws_builder: WorkingSetBuilder | None = None,
)
```

---

### 主要方法

#### run
```python
async def run(self) → AgentOutput
```
**描述：** 主执行循环（SEE-ACT-UPDATE）

**返回：**
```python
AgentOutput(
    task_id=str,
    content=str,           # 输出内容
    tool_calls=list,       # 工具调用列表
    observations=list,     # 观察记录
    success=bool,
    error=str | None,
    created_at=datetime,
)
```

---

### 控制接口（供OS Interface调用）

#### pause / resume
```python
async def pause(self, reason: str = "") → None
async def resume(self) → None
```

#### apply_context_update
```python
async def apply_context_update(self, updates: dict[str, Any]) → None
```

#### get_event_log_export
```python
def get_event_log_export(self) → dict[str, Any]
```
**描述：** 导出完整事件日志供上层查看

---

## Scheduler

### 全局实例获取
```python
scheduler = get_scheduler()
```

### 主要方法

#### run_task
```python
async def run_task(
    self,
    task: TaskSnapshot,
    context: CompiledContext,
) → dict[str, Any]
```
**描述：** 执行单个任务

---

### 干预API（供上层使用）

#### pause_task / resume_task
```python
async def pause_task(self, task_id: str, reason: str = "") → bool
async def resume_task(self, task_id: str) → bool
```

#### get_thread_log
```python
async def get_thread_log(self, task_id: str) → dict[str, Any] | None
```
**描述：** 获取线程事件日志（上层检查入口）

**示例：**
```python
log = await scheduler.get_thread_log("task_001")
print(f"Events: {log['event_log']['event_count']}")
print(f"Current phase: {log['current_phase']}")
```

---

#### update_thread_phase
```python
async def update_thread_phase(
    self,
    task_id: str,
    new_phase: Phase | str,
) → bool
```
**描述：** 更新线程阶段

**示例：**
```python
# 强制切换到执行阶段
await scheduler.update_thread_phase("task_001", Phase.EXECUTE)

# 或使用字符串
await scheduler.update_thread_phase("task_001", "execute")
```

---

#### update_thread_context
```python
async def update_thread_context(
    self,
    task_id: str,
    updates: dict[str, Any],
) → bool
```

#### get_active_thread_info
```python
def get_active_thread_info(self, task_id: str) → dict[str, Any] | None
```
**返回示例：**
```python
{
    "task_id": "task_001",
    "thread_id": "thread_a1b2c3d4",
    "current_phase": "explore",
    "step_count": 5,
    "is_paused": False,
    "pause_reason": None,
    "max_steps": 50,
}
```

---

#### list_active_threads
```python
def list_active_threads(self) → list[dict[str, Any]]
```

---

## 配置参考

### Working Set Rules (YAML)

```yaml
phases:
  explore:
    slot_selection:
      slot_types: [module_map, symbol_index]
      max_slots: 3
      priority_threshold: 5
    observation_selection:
      max_count: 10
      lookback_steps: 20
      priority_event_types: [tool_result, observation]

token_budget:
  max_total: 4000
  reserved_for_immutable: 500
  reserved_for_observations: 1500
  reserved_for_artifacts: 1500
  reserved_for_notes: 500
```

### Coordinator Routing (YAML)

```yaml
local_priority:
  - fs-skill
  - shell-skill

remote_only: []

timeouts:
  local_default: 30000
  remote_default: 60000
```

---

## 完整使用示例

### 1. 基本任务执行

```python
import asyncio
from thread_runtime.agent_thread import AgentThread
from thread_runtime.working_set_builder import WorkingSetBuilder
from executors_client.coordinator_interface import get_execution_coordinator
from schemas.models import CompiledContext, TaskSnapshot, TaskStatus

async def basic_execution():
    # 创建任务
    task = TaskSnapshot(
        id="task_001",
        session_id="session_001",
        process_id="process_001",
        status=TaskStatus.IDLE,
        goal="List files in /tmp",
        constraints=["max_steps: 10"],
        allowed_capabilities=["fs-skill"],
    )
    
    # 创建上下文
    context = CompiledContext(
        task_id=task.id,
        session_context={"session_id": task.session_id},
        task_goal=task.goal,
        constraints=task.constraints,
        allowed_capabilities=task.allowed_capabilities,
        forbidden_capabilities=[],
    )
    
    # 创建并运行Agent
    agent = AgentThread(
        task=task,
        compiled_context=context,
        coordinator=get_execution_coordinator(),
        ws_builder=WorkingSetBuilder(),
    )
    
    result = await agent.run()
    print(f"Success: {result.success}")
    print(f"Output: {result.content}")
```

### 2. 上层干预

```python
from thread_runtime.scheduler import get_scheduler
from thread_runtime.models import Phase

async def intervention_example():
    scheduler = get_scheduler()
    task_id = "task_001"
    
    # 查看线程状态
    info = scheduler.get_active_thread_info(task_id)
    print(f"Current phase: {info['current_phase']}")
    
    # 查看完整日志
    log = await scheduler.get_thread_log(task_id)
    event_count = log['event_log']['event_count']
    print(f"Total events: {event_count}")
    
    # 暂停进行审查
    await scheduler.pause_task(task_id, "Need to review progress")
    
    # 检查后发现可以进入执行阶段
    await scheduler.update_thread_phase(task_id, Phase.EXECUTE)
    
    # 恢复执行
    await scheduler.resume_task(task_id)
```

### 3. 自定义Working Set规则

```python
from thread_runtime.working_set_builder import WorkingSetBuilder

# 使用自定义配置
builder = WorkingSetBuilder("my_custom_rules.yaml")

# 或修改默认规则
builder = WorkingSetBuilder()
builder.slot_rules[Phase.EXPLORE].max_slots = 5
```

### 4. 注册本地技能

```python
from executors_client.local_skill_registry import get_local_skill_registry

class MySkill:
    async def my_tool(self, param1: str, param2: int) → dict:
        return {"result": f"{param1}: {param2}"}

# 注册
registry = get_local_skill_registry()
registry.register(
    skill_name="my-skill",
    skill_instance=MySkill(),
)

# 现在Agent可以使用这个技能
```
