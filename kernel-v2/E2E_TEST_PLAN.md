# 端到端测试计划 (E2E Test Plan)

## 目标

验证完整的 Rust Agent Kernel 功能链：
- 数据面 (Data Plane): Agent Thread + Block Composer + Execution
- 控制面 (Control Plane): OS Interface + Scheduler + Session Management
- 权限系统 (P0/P1/P3): Capability-based access control
- gRPC 服务: Full API availability

## 测试环境

### 硬件要求
- CPU: 2+ cores
- RAM: 4GB+
- Disk: 10GB free space

### 软件依赖
- Rust 1.75+
- protoc (Protocol Buffers)
- SQLite3
- (可选) LLM API Key (OpenAI/Ark)

### 测试配置
```bash
# 编译
cargo build --release --features control-plane

# 数据目录
export DATA_PATH=/tmp/proclaw_e2e_test
export SOCKET_PATH=/tmp/proclaw_test.sock
```

## 测试阶段

### Phase 1: 数据面基础功能 (1-2天)

#### 1.1 Block Composer 测试
**目标**: 验证 Block 管理和 Composition

```rust
#[tokio::test]
async fn test_block_composer_full() {
    // 1. 创建 ComposerEngine
    let composer = BlockComposerEngine::new(&config).await?;
    
    // 2. 添加不同类型的 Blocks
    composer.upsert_block(task_block).await;
    composer.upsert_block(context_block).await;
    composer.upsert_block(memory_block).await;
    
    // 3. 列出所有 Blocks
    let blocks = composer.list_all_blocks().await;
    assert_eq!(blocks.len(), 3);
    
    // 4. 按类型查询
    let task_blocks = composer.list_blocks_by_type(7).await; // TASK_GOAL
    
    // 5. 更新 Block
    composer.upsert_block(updated_block).await;
    
    // 6. 删除 Block
    composer.remove_block("block_id").await;
    
    // 7. 清空所有
    composer.clear_all_blocks().await;
}
```

**验证点**:
- ✅ Block CRUD 操作
- ✅ 按类型查询
- ✅ Block 元数据正确

#### 1.2 ComposerSkill 测试
**目标**: 验证统一接口

```rust
#[tokio::test]
async fn test_composer_skill_full() {
    let skill = ComposerSkill::new(...);
    
    // 1. Block 管理
    skill.upsert_block("task", 7, "Implement auth", 100).await;
    
    // 2. 三种 Profile 的 Composition
    let prime_result = skill.compose("s1", "t1", Profile::Prime).await?;
    let session_result = skill.compose("s1", "t1", Profile::Session).await?;
    let task_result = skill.compose("s1", "t1", Profile::Task).await?;
    
    // 3. 验证不同 Profile 的 token 预算
    assert!(prime_result.total_tokens <= 2000);
    assert!(session_result.total_tokens <= 3000);
    assert!(task_result.total_tokens <= 4000);
    
    // 4. 带锁执行
    let result = skill.execute_with_lock(
        PathBuf::from("/tmp/test"),
        action,
        "session",
        "executor",
        60,
    ).await?;
}
```

**验证点**:
- ✅ 三种 Profile (Prime/Session/Task) 正常工作
- ✅ 带锁执行成功
- ✅ 返回结果格式正确

#### 1.3 Directory Lock Manager 测试
**目标**: 验证 FIFO 队列和并发控制

```rust
#[tokio::test]
async fn test_lock_manager_full() {
    let lm = DirectoryLockManager::new(db_path)?;
    
    // 1. 基础获取/释放
    let lock1 = lm.acquire_lock(dir, exec1, session1, Write, 60).await?;
    lm.release_lock(lock1).await?;
    
    // 2. 并发获取（FIFO队列）
    let lock_a = lm.acquire_lock(dir, exec_a, session_a, Write, 60).await?;
    // exec_b 应该进入等待队列
    let lock_b_future = lm.acquire_lock(dir, exec_b, session_b, Write, 60);
    
    // 3. 查询锁状态
    let status = lm.query_lock_status(dir).await?;
    assert!(status.is_locked);
    assert_eq!(status.queue_length, 1);
    
    // 4. 列出活跃锁
    let active = lm.list_active_locks().await?;
    
    // 5. 超时测试
    let timeout_result = lm.acquire_lock(dir, exec_c, session_c, Write, 1).await;
    // 应该超时失败
}
```

**验证点**:
- ✅ FIFO 队列正确排序
- ✅ 锁状态查询准确
- ✅ 超时机制工作

---

### Phase 2: Agent Thread 执行 (1-2天)

#### 2.1 Thread 生命周期
**目标**: 验证 Thread 创建、启动、停止

```rust
#[tokio::test]
async fn test_thread_lifecycle() {
    let tm = ThreadManager::new(...);
    
    // 1. 创建 Thread
    let input = ImmutableInput {
        task_goal: "Test task".to_string(),
        constraints: vec!["max_steps: 10"],
        allowed_capabilities: vec!["bash"],
        forbidden_capabilities: vec![],
        session_context: HashMap::new(),
        compiled_at: Utc::now(),
    };
    let thread_id = tm.create_thread(session_id, input).await?;
    
    // 2. 启动 Thread（Spawn）
    let executor_id = tm.spawn_thread(thread_id).await?;
    
    // 3. 查询状态
    let info = tm.get_thread_info(&thread_id).await?;
    assert_eq!(info.status, ThreadStatus::Running);
    
    // 4. 暂停 Thread
    tm.pause_thread(&thread_id).await?;
    
    // 5. 恢复 Thread
    tm.resume_thread(&thread_id).await?;
    
    // 6. 取消 Thread
    tm.cancel_thread(&thread_id).await?;
}
```

**验证点**:
- ✅ Thread 状态转换正确
- ✅ Event Log 记录完整
- ✅ 暂停/恢复/取消工作

#### 2.2 SEE-ACT-UPDATE 循环
**目标**: 验证执行循环

```rust
#[tokio::test]
async fn test_see_act_update_loop() {
    // 1. 创建 ThreadExecutor
    let executor = ThreadExecutor::new(...).await?;
    
    // 2. 执行一步（SEE）
    let step_result = executor.step().await?;
    
    // 3. 验证 Working Set 构建
    let working_set = executor.working_set_builder.build(...).await?;
    
    // 4. 验证 Event Log 追加
    let events = executor.storage.read_event_log().await?;
    assert!(!events.is_empty());
    
    // 5. 验证 Phase 转换
    // Explore -> Execute -> Complete
}
```

**验证点**:
- ✅ Working Set 正确构建
- ✅ Event Log 增长
- ✅ Phase 正确切换

---

### Phase 3: 控制面功能 (1-2天)

#### 3.1 OS Interface Skill (P0)
**目标**: 验证 Prime 权限功能

```rust
#[tokio::test]
async fn test_os_interface_skill() {
    let skill = OSInterfaceSkill::new(pm, tm);
    
    // 1. create_process
    let result = skill.execute(
        "create_process",
        json!({
            "session_id": "test_session",
            "process_goal": "Test process",
            "tags": ["test"]
        }),
        context, // CapabilityLevel::Prime
    ).await?;
    let process_id = result.process_id;
    
    // 2. list_sessions
    let result = skill.execute(
        "list_sessions",
        json!({}),
        context,
    ).await?;
    
    // 3. get_session_info
    let result = skill.execute(
        "get_session_info",
        json!({"session_id": "test_session"}),
        context,
    ).await?;
    
    // 4. delete_session
    let result = skill.execute(
        "delete_session",
        json!({
            "session_id": "test_session",
            "force": false
        }),
        context,
    ).await?;
}
```

**验证点**:
- ✅ 所有 tools 可调用
- ✅ 只有 P0 可以访问
- ✅ P1/P3 被拒绝访问

#### 3.2 Scheduler Skill (P1)
**目标**: 验证 Host 权限功能

```rust
#[tokio::test]
async fn test_scheduler_skill() {
    let skill = SchedulerSkill::new(tm);
    
    // 1. create_thread
    let result = skill.execute(
        "create_thread",
        json!({
            "session_id": "test_session",
            "task_goal": "Test task",
            "constraints": ["max_steps: 10"]
        }),
        context, // CapabilityLevel::Host
    ).await?;
    let thread_id = result.thread_id;
    
    // 2. spawn_thread
    let result = skill.execute(
        "spawn_thread",
        json!({"thread_id": thread_id}),
        context,
    ).await?;
    
    // 3. pause_thread
    let result = skill.execute(
        "pause_thread",
        json!({"thread_id": thread_id}),
        context,
    ).await?;
    
    // 4. resume_thread
    let result = skill.execute(
        "resume_thread",
        json!({"thread_id": thread_id}),
        context,
    ).await?;
    
    // 5. cancel_thread
    let result = skill.execute(
        "cancel_thread",
        json!({"thread_id": thread_id}),
        context,
    ).await?;
}
```

**验证点**:
- ✅ 所有 tools 可调用
- ✅ P1/P0 可以访问
- ✅ P3 被拒绝访问

#### 3.3 Session Host 集成
**目标**: 验证 Session 管理

```rust
#[tokio::test]
async fn test_session_host_full() {
    let sh = SessionHostSkills::new(...).await?;
    
    // 1. 创建 Process
    let process_id = sh.create_process(
        SessionId("test".to_string()),
        "Test process".to_string(),
        vec!["test".to_string()],
    ).await?;
    
    // 2. 在 Process 中创建 Thread
    let thread_id = sh.create_thread_in_process(
        &process_id,
        input,
    ).await?;
    
    // 3. 列出 Process 的所有 Threads
    let threads = sh.list_process_threads(&process_id).await?;
    
    // 4. 查询 Thread 状态
    let status = sh.get_thread_in_process_status(&process_id, &thread_id).await?;
}
```

**验证点**:
- ✅ Process-Thread 层级正确
- ✅ 状态查询准确

---

### Phase 4: 权限系统 (0.5-1天)

#### 4.1 Capability Level 测试
**目标**: 验证权限边界

```rust
#[tokio::test]
async fn test_capability_levels() {
    let registry = create_registry_with_all_skills();
    
    // 1. P0 (Prime) - 可以访问所有
    let result = registry.execute_control(
        request_for_os_interface,
        CapabilityLevel::Prime,
    ).await;
    assert!(result.is_ok());
    
    // 2. P1 (Host) - 可以访问 Scheduler，不能访问 OS Interface
    let result = registry.execute_control(
        request_for_scheduler,
        CapabilityLevel::Host,
    ).await;
    assert!(result.is_ok());
    
    let result = registry.execute_control(
        request_for_os_interface,
        CapabilityLevel::Host,
    ).await;
    assert!(result.is_err()); // Permission denied
    
    // 3. P3 (Agent) - 只能访问 Bash
    let result = registry.execute_control(
        request_for_bash,
        CapabilityLevel::Agent,
    ).await;
    assert!(result.is_ok());
    
    let result = registry.execute_control(
        request_for_scheduler,
        CapabilityLevel::Agent,
    ).await;
    assert!(result.is_err()); // Permission denied
}
```

**验证点**:
- ✅ P0 访问所有
- ✅ P1 访问 Scheduler + Bash
- ✅ P3 只能访问 Bash

---

### Phase 5: gRPC 服务集成 (1-2天)

#### 5.1 完整调用链
**目标**: 验证 gRPC 服务层

```rust
#[tokio::test]
async fn test_grpc_full_chain() {
    // 1. 启动服务
    let service = AgentKernelService::new(...).await?;
    
    // 2. 通过 gRPC 创建 Thread
    let response = service.create_thread(Request::new(CreateThreadRequest {
        session_id: "test".to_string(),
        task_goal: "Test".to_string(),
        // ...
    })).await?;
    let thread_id = response.into_inner().thread_id;
    
    // 3. 通过 gRPC 执行 Skill
    let response = service.execute_skill(Request::new(ExecuteSkillRequest {
        skill_name: "bash".to_string(),
        tool_name: "execute".to_string(),
        parameters: json!({"command": "echo hello"}),
        // ...
    })).await?;
    
    // 4. 通过 gRPC 查询资源状态
    let response = service.get_resource_status(Request::new(
        GetResourceStatusRequest {
            directory_paths: vec!["/tmp/test".to_string()],
        }
    )).await?;
}
```

**验证点**:
- ✅ gRPC 接口响应正确
- ✅ 流式事件推送工作
- ✅ 错误处理正确

#### 5.2 并发测试
**目标**: 验证并发安全

```rust
#[tokio::test]
async fn test_concurrent_execution() {
    let service = Arc::new(AgentKernelService::new(...).await?);
    
    // 1. 并发创建多个 Threads
    let mut handles = vec![];
    for i in 0..10 {
        let svc = service.clone();
        handles.push(tokio::spawn(async move {
            svc.create_thread(...).await
        }));
    }
    
    // 2. 等待所有完成
    for h in handles {
        h.await??;
    }
    
    // 3. 验证数据一致性
}
```

**验证点**:
- ✅ 无数据竞争
- ✅ 资源正确释放

---

## 测试用例汇总

| Phase | 测试用例数 | 预计时间 | 关键验证点 |
|-------|-----------|----------|-----------|
| Phase 1 | 6 | 1-2天 | Block管理, Composition, Lock机制 |
| Phase 2 | 4 | 1-2天 | Thread生命周期, SEE-ACT-UPDATE |
| Phase 3 | 6 | 1-2天 | OSInterface, Scheduler, SessionHost |
| Phase 4 | 3 | 0.5-1天 | P0/P1/P3 权限边界 |
| Phase 5 | 4 | 1-2天 | gRPC集成, 并发安全 |
| **总计** | **23** | **4.5-9天** | **全覆盖** |

## 自动化脚本

```bash
#!/bin/bash
# run_e2e_tests.sh

set -e

echo "Building with control-plane features..."
cargo build --release --features control-plane

echo "Running E2E tests..."
cargo test --test e2e_tests --features control-plane -- --nocapture

echo "All tests passed!"
```

## 成功标准

- [ ] 所有 23 个测试用例通过
- [ ] 代码覆盖率 > 80%
- [ ] 无内存泄漏 (valgrind/ Miri)
- [ ] 并发测试 1000 次无失败
- [ ] 文档与代码同步

## 后续工作

1. **性能测试**: 吞吐量、延迟基准测试
2. **压力测试**: 1000+ 并发连接
3. **故障注入**: 网络分区、节点宕机
4. **集成测试**: 与 TypeScript 前端联调

## 交付物

- ✅ E2E 测试代码 (`tests/e2e_tests.rs`)
- ✅ 测试报告 (覆盖率、性能数据)
- ✅ 部署文档
- ✅ 运维手册
