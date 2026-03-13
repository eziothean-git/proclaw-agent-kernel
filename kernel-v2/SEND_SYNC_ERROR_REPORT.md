# Send/Sync 编译错误报告

**日期**: 2026-03-12
**状态**: 需要人工核查
**错误类型**: future cannot be sent between threads safely

## 错误摘要

```
error: future cannot be sent between threads safely
   --> src/scheduler/thread_manager.rs:184:22
    |
184 |           let handle = tokio::spawn(async move {
    |  ______________________^
185 | |             // 运行 Executor
186 | |             let result = executor.run().await;
...   |
201 | |             info!(thread_id = %thread_id_clone.0, "Thread executor completed");
202 | |         });
    | |__________^ future created by async block is not `Send`
```

## 问题链

1. `tokio::spawn` 要求 future 是 `Send` (line 184)
2. async block 捕获 `executor` (ThreadExecutor) 并调用 `executor.run().await`
3. `run()` 返回的 future 不是 `Send`
4. 根本原因：`ThreadExecutor` 或其中的某个类型不是 `Send`

## 已尝试的修复

### 1. 给 ThreadExecutor 添加 unsafe Send/Sync impl
文件: `src/scheduler/thread_executor.rs`
```rust
unsafe impl Send for ThreadExecutor {}
unsafe impl Sync for ThreadExecutor {}
```
结果: 未解决问题

### 2. 重构 spawn_thread 方法
将 executor 的创建和运行逻辑调整，避免直接移动 executor
结果: 未解决问题

## ThreadExecutor 字段分析

```rust
pub struct ThreadExecutor {
    executor_id: ExecutorId,                          // String wrapper - 应该 Send
    storage: ThreadStorage,                           // PathBuf + ThreadId - 应该 Send
    coordinator: Arc<ExecutionCoordinator>,          // 需要检查
    llm_router: Arc<LLMRouter>,                      // 需要检查
    context_builder: Arc<ContextBuilder>,            // 应该 Send
    output_parser: Arc<OutputParser>,                // 应该 Send
    state: ExecutorState,                            // Copy - 应该 Send
    current_step: usize,                             // Copy - 应该 Send
    max_steps: usize,                                // Copy - 应该 Send
    event_tx: mpsc::Sender<ExecutorEvent>,          // 应该 Send
}
```

## 需要人工核查的内容

### 高优先级检查项

1. **ExecutionCoordinator** 及其依赖项的 Send/Sync 实现
   - DirectoryLockManager
   - SkillRegistry
   - TicketTracker

2. **LLMRouter** 及其依赖项的 Send/Sync 实现
   - 特别是 `Arc<dyn LLMClient>` 是否添加了 Send + Sync bound

3. **ThreadManager** 本身
   - 确认所有 Arc 包含的类型都实现了 Send + Sync

### 建议检查方法

```rust
// 在 thread_manager.rs 测试模块中添加
#[test]
fn check_all_types_are_send_sync() {
    fn assert_send<T: Send>() {}
    fn assert_sync<T: Sync>() {}
    
    // 逐个检查关键类型
    assert_send::<ExecutionCoordinator>();
    assert_send::<LLMRouter>();
    assert_send::<ThreadExecutor>();
    // ... 等等
}
```

### 可能的根本原因

1. 某个 `Arc<dyn Trait>` 缺少 `Send + Sync` bound
2. 使用了 `std::sync::Mutex` 而不是 `tokio::sync::Mutex` 在 async 上下文中
3. 某个自定义类型没有实现 Send/Sync
4. `ThreadExecutor::run()` 方法内部创建了非 Send 的 future

## 临时解决方案

如果无法立即修复，可以考虑：

1. 使用 `tokio::task::spawn_local` 代替 `tokio::spawn` (单线程 runtime)
2. 重构代码避免在 async block 中捕获非 Send 类型
3. 将 ThreadExecutor 的运行逻辑改为 message passing 模式

## 相关文件

- `src/scheduler/thread_manager.rs` - 错误位置
- `src/scheduler/thread_executor.rs` - ThreadExecutor 定义
- `src/coordinator/coordinator_impl.rs` - ExecutionCoordinator
- `src/llm/router.rs` - LLMRouter
- `src/skills/scheduler_skill.rs` - 调用链上游

## 编译命令

```bash
export PROTOC=$HOME/.local/bin/protoc
~/.cargo/bin/cargo build
```

## 当前编译状态

- 错误数量: 1
- 警告数量: 75
- 最后编译结果: 失败

## 关键错误位置

```rust
// src/scheduler/thread_manager.rs:184
let handle = tokio::spawn(async move {
    // 运行 Executor
    let result = executor.run().await;  // <-- 问题在这里
    
    // 记录完成状态
    if let Ok(summary) = result {
        let mut history_guard = history.write().await;
        if let Some(h) = history_guard.get_mut(&thread_id_clone) {
            h.completed_at = Some(chrono::Utc::now());
            h.final_status = Some(summary.final_status);
        }
    }
    
    // 从运行列表中移除
    executors.remove(&thread_id_clone);
    
    info!(thread_id = %thread_id_clone.0, "Thread executor completed");
});
```

## 调试建议

1. 从 ThreadExecutor 开始，逐个移除字段，编译测试
2. 使用 `cargo check` 的快速反馈循环
3. 检查 trait object 类型: `Arc<dyn SomeTrait>` 需要改为 `Arc<dyn SomeTrait + Send + Sync>`
4. 使用 `#[tokio::test]` 创建最小复现案例
