# 提示词审计报告

## 执行日期
2026-03-13

## 审计目标
检查 Agent Kernel 各层的上下文编译配置，确保端到端流程不会出现无限循环。

---

## 1. Prime Personality (Layer 3) - 提示词组成

### 系统提示词核心内容

**文件**: `kernel-v2/src/personality/config.rs`

**关键约束规则**:
```
## CRITICAL RULES

**DO NOT trigger exploration for simple conversation!**
- Greetings ("你好", "hello", "hi") → intent: "conversation", capabilities: []
- General questions → intent: "conversation", capabilities: []
- Only use capabilities for actual tasks (file operations, code execution, etc.)

**You are STATELESS** - no memory between calls. Use provided context only.
```

**快速意图指南**:
- "你好"/"hello" → conversation (NO capabilities, direct response)
- "What is X?" → conversation (NO capabilities, direct response)  
- "Read file X" → file_operation (capabilities: ["fs-skill"])
- "Execute command" → shell_execution (capabilities: ["shell-skill"])

### 提示词结构 (build_prompt 方法)

**Block 组成**:
1. **System Identity Block** (block_type: 1, priority: 100)
   - 基础系统提示词
   - 可选：对话上下文引用信息（总轮数、窗口大小、完整上下文路径）
   - 记忆访问规则说明

2. **Conversation History Block** (block_type: 8, priority: 80)
   - 仅当提供 context 时存在
   - 滑动窗口形式的历史对话（最近 N 轮）
   - 标记为 "Recent Conversation History (Sliding Window)"

3. **User Request Block** (block_type: 7, priority: 90)
   - 平台信息
   - 用户ID
   - Session ID
   - 优先级
   - 当前消息内容

### 防循环机制 ✅

1. **明确的简单对话规则**: 系统提示词强制要求简单对话不触发 exploration
2. **STATELESS 声明**: 明确告知 Prime 不要依赖记忆，只使用提供的上下文
3. **JSON Only 输出**: 限制输出格式为结构化 IR，防止自由文本导致的循环
4. **Fallback IR**: parse 失败时生成默认 conversation intent，避免重试

---

## 2. BlockComposer - 上下文合成引擎

### 工作原理

**文件**: `kernel-v2/src/block_composer/mod.rs`

**纯规则驱动，无 LLM 调用**:
- 接收 Block 列表
- 根据 Profile 排序（token_budget, block_type_order）
- 按预算截断
- 拼接文本

**Profile 配置**:

| Profile | Token Budget | Block Type Order |
|---------|--------------|------------------|
| Prime | 2000 | SYSTEM_IDENTITY, INTENT_ANALYSIS, GLOBAL_MEMORY |
| Session | 3000 | SESSION_CONTEXT, ACTIVE_TASKS, CONVERSATION_HISTORY |
| Task | 4000 | TASK_GOAL, WORKING_MEMORY, AVAILABLE_TOOLS, RECENT_OBSERVATIONS |

### 防循环机制 ✅

1. **无 LLM 调用**: 纯确定性算法，不会产生递归调用
2. **缓存机制**: 相同输入直接返回缓存结果
3. **Token 预算**: 硬限制防止上下文无限增长

---

## 3. Agent Thread (Layer 6) - Working Set 构建

### Context Builder 组成

**文件**: `kernel-v2/src/scheduler/context_builder.rs`

**Block 组成**:
1. **Task Goal Block** (block_type: TaskGoal, priority: 100)
   - 不可变输入的目标
   - 约束条件
   - 允许的能力列表

2. **Current Phase Block** (block_type: SystemIdentity, priority: 90)
   - 当前执行阶段（Exploration/Execution/Verification）

3. **Recent Observations Block** (block_type: RecentObservations, priority: 80)
   - 最近 10 个事件
   - 事件类型、步骤号、内容

4. **Artifact Blocks** (various types)
   - 模块映射、符号索引、上下文报告等
   - 根据优先级排序

5. **Constraints Block** (block_type: WorkingMemory, priority: 70)
   - 输入约束条件

### 防循环机制 ✅

1. **固定历史窗口**: 只读取最近 10 个事件
2. **Phase 明确**: 当前阶段清晰标注，Agent 知道自己在哪个阶段
3. **Working Set 构建是单向的**: 从存储读取 → 构建 Block → 合成，无递归

---

## 4. Gateway Skill - IR 提交

### 工作原理

**文件**: `kernel-v2/src/skills/gateway_skill.rs`

**单次 HTTP 调用**:
- 接收 IR 和 request_id
- POST 到 Gateway webhook
- 包含 Bearer Token 认证
- 一次性调用，无状态保持

### 防循环机制 ✅

1. **单次调用**: 仅一次 HTTP POST，不会重试或递归
2. **无上下文依赖**: 不依赖之前的调用结果
3. **错误处理**: 失败返回错误，不会无限重试

---

## 5. 完整流程审计

### 调用链

```
用户请求
    ↓
Gateway (TypeScript)
    ↓ gRPC/HTTP
Request Manager
    ↓ gRPC ProcessRequest
Prime Personality Service
    ↓ 内部调用
Prime Personality Core
    ↓ BlockComposer.compose (无 LLM)
合成提示词
    ↓ LLM Router
LLM 生成 IR
    ↓
Gateway Skill.send_ir_result
    ↓ HTTP POST
Gateway Webhook (TypeScript)
    ↓ 编译 IR
返回给用户
```

### 循环风险分析

| 层级 | 风险点 | 评估 | 缓解措施 |
|------|--------|------|----------|
| Prime → Prime | Prime 调用自身 | ❌ 无 | 无递归调用点 |
| Prime → BlockComposer | BlockComposer 调用 Prime | ❌ 无 | BlockComposer 纯规则，无 LLM |
| Agent Thread → Prime | Agent 调用 Prime | ❌ 无 | Agent Thread 由 Session Host 调度，不直接调用 Prime |
| Gateway Skill → Prime | Skill 回调 Prime | ❌ 无 | Skill 直接调用 HTTP webhook，不经过 Prime |
| LLM → 工具 → Prime | LLM 调用工具触发 Prime | ❌ 无 | Prime 生成 IR 后即返回，工具调用在后续层级 |

### 结论 ✅

**无无限循环风险**。

1. **Prime Personality 是入口点**: 每个请求只经过一次 Prime
2. **IR 生成是终点**: Prime 生成 IR 后通过 Skill 发送，流程结束
3. **无递归调用链**: 没有层级会反向调用上层
4. **简单对话被截断**: 系统提示词确保简单对话不会触发复杂流程

---

## 6. 潜在优化建议

### 已确认安全，可选优化:

1. **添加超时控制** (已在外层实现)
   - Request Manager 有超时配置
   - Worker Pool 有任务超时

2. **限制重试次数** (已实现)
   - Skill 调用失败不重试
   - Request Manager 有最大重试次数限制

3. **Token 预算检查** (已实现)
   - Prime Profile: 2000 tokens
   - Session Profile: 3000 tokens
   - Task Profile: 4000 tokens

---

## 7. 测试建议

为确保端到端流程正常，建议测试以下场景:

1. **简单对话** (应快速返回)
   - Input: "你好"
   - Expected: IR with intent="conversation", capabilities=[]

2. **文件操作请求** (应生成对应 capability)
   - Input: "读取文件 /tmp/test.txt"
   - Expected: IR with capabilities=["fs-skill"]

3. **复杂任务** (应分解为多个 processes)
   - Input: "分析代码并生成测试"
   - Expected: IR with multiple processes

4. **超长输入** (应被截断)
   - 测试 token budget 限制

---

## 审计结论

**✅ 通过审计**

提示词配置安全，各层级职责清晰，无循环调用风险。系统可以安全地进行端到端测试。
