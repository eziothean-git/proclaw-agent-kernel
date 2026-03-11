# Agent Kernel v2 - 编译错误记录 (85个错误)

**生成时间**: 2026-03-11
**错误总数**: 85

---

## 错误分类统计

| 错误类型 | 数量 | 主要文件 |
|---------|------|----------|
| 枚举类型引用问题 | ~25 | agent_kernel.rs |
| 类型名称冲突 | ~20 | agent_kernel.rs (ThreadStatus/Event 等) |
| 方法参数问题 | ~10 | storage.rs, coordinator_impl.rs |
| 类型不匹配 | ~15 | 多个文件 |
| 所有权/借用错误 | ~5 | session/skills.rs, process.rs |
| 字段/方法不存在 | ~10 | 多个文件 |

---

## 详细错误列表

### 1. 枚举类型引用问题

**错误**: 无法解析 `executor_status::ExecutorStatus::Paused`
**文件**: `src/server/agent_kernel.rs:365, 369, 373, 386`
**原因**: proto 生成的枚举值前缀已更改，但未更新引用
**修复**: 
- 旧: `executor_status::ExecutorStatus::Paused`
- 新: `proto::ExecutorStatus::EXECUTOR_PAUSED`

**错误**: 无法解析 `thread_status::ThreadStatus::Created`
**文件**: `src/server/agent_kernel.rs:529-533, 558, 578-582`
**原因**: proto 生成的枚举值前缀已更改，但未更新引用
**修复**:
- 旧: `thread_status::ThreadStatus::Created`
- 新: `proto::ThreadStatus::THREAD_STATUS_CREATED`

---

### 2. 类型名称冲突

**错误**: `ThreadStatus` 是模糊的 (ambiguous)
**文件**: `src/server/agent_kernel.rs:331, 412, 529-533, 578-582`
**原因**: `models::*` 和 `proto::*` 都有 `ThreadStatus`
**修复**: 使用完全限定名或重命名导入
```rust
use crate::agent_thread::models::ThreadStatus as ModelsThreadStatus;
use crate::server::agent_kernel::proto::ThreadStatus as ProtoThreadStatus;
```

**错误**: `Event` 是模糊的
**文件**: `src/server/agent_kernel.rs:480`
**原因**: `models::Event` 和 `proto::Event` 冲突
**修复**: 使用完全限定名

**错误**: `ExecutorEvent` 类型冲突
**文件**: `src/server/agent_kernel.rs:442`
**原因**: `scheduler::ExecutorEvent` 与 `proto::ExecutorEvent` 不同
**修复**: gRPC 返回应使用 `proto::ExecutorEvent`，需要转换

---

### 3. 方法参数问题

**错误**: `thread_path` 方法参数不匹配
**文件**: `src/agent_thread/storage.rs:53, 96, 119, 362`
**原因**: 定义了 `fn thread_path(&self)`，但调用时传入 2 个参数
**修复**: 统一方法签名

**错误**: `SkillContext` 缺少 `capability_level` 字段
**文件**: `src/scheduler/thread_executor.rs:325`
**原因**: 已添加该字段，但未在构造时初始化
**修复**: 在创建 SkillContext 时添加 `capability_level`

---

### 4. 类型不匹配

**错误**: `ExecutorId` 和 `SessionId` 期望 struct，但传入 String
**文件**: `src/coordinator/coordinator_impl.rs:81-82`
**原因**: SkillContext 的字段现在是 String，但方法期望 NewType 包装器
**修复**: 
- 方案 A: 将 SkillContext 字段改回 `ExecutorId`/`SessionId`
- 方案 B: 在 coordinator 中转换 String -> ExecutorId

**错误**: `CoordinatorStats` 未实现 Clone
**文件**: `src/coordinator/coordinator_impl.rs:223`
**原因**: `DashMap` 的 value 需要 Clone
**修复**: 为 `CoordinatorStats` 添加 `#[derive(Clone)]`

**错误**: `anyhow::Error` 不能转换为 `ThreadError`
**文件**: `src/agent_thread/storage.rs:128, 159`
**原因**: `event.to_json_line()` 返回 `anyhow::Result`，但方法返回 `Result<_, ThreadError>`
**修复**: 为 `ThreadError` 添加 `From<anyhow::Error>` 实现

---

### 5. 所有权/借用错误

**错误**: 不能同时使用可变和不可变借用
**文件**: `src/session/process.rs:243`
**代码**:
```rust
if let Some(summary) = self.thread_summaries.get_mut(&thread_id.0) {
    let summary_path = self.threads_dir().join(...);  // 不可变借用
    // summary 是可变借用
}
```
**修复**: 重构逻辑，先获取需要的数据，再更新

**错误**: value moved 后再次使用
**文件**: `src/session/skills.rs:314, 325`
**原因**: `String` 被 move 到 async block，后续无法使用
**修复**: 使用 `clone()` 保留原始值

---

### 6. 字段/方法不存在

**错误**: `BashRequest` 没有 `working_dir` 字段
**文件**: `src/skills/bash_skill.rs:94`
**原因**: 实际字段名是 `working_directory`
**修复**: 更正字段名

**错误**: `skill_router` 没有 `route` 方法
**文件**: `src/coordinator/coordinator_impl.rs:91`
**原因**: `SkillRouter` 只有占位实现
**修复**: 实现 `route` 方法或直接使用 SkillRegistry

**错误**: `CoordinatorStats` 未实现 Clone
**文件**: `src/coordinator/coordinator_impl.rs:223`
**修复**: 添加 `#[derive(Clone)]`

---

## 修复优先级建议

### P0 (阻止编译)
1. 修复所有 proto 枚举引用 (添加前缀)
2. 解决类型名称冲突 (使用完全限定名)
3. 修复方法参数不匹配问题

### P1 (类型系统)
4. 修复 `ExecutorId`/`SessionId` String 转换
5. 修复 `SkillContext` 缺少字段
6. 实现 `From<anyhow::Error>` for `ThreadError`

### P2 (所有权)
7. 修复借用冲突
8. 修复 move 语义问题

### P3 (其他)
9. 修复字段名错误
10. 实现缺失的方法

---

## 完整错误文件

详细错误信息保存在: `kernel-v2/COMPILATION_ERRORS.md`

可以使用以下命令查看:
```bash
cd kernel-v2 && cargo check 2>&1 | tee errors.log
```