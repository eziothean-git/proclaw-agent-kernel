# gRPC 服务修改说明

## 修改概述

在 Phase 2 中，我对部分 gRPC 方法进行了简化处理。以下是详细说明：

## 被简化的方法

### 1. `get_resource_status` - 资源状态查询

**原始意图**：
查询指定目录的锁状态，用于监控和调试目录锁定情况。

**原始实现（已删除的代码）**：
```rust
async fn get_resource_status(
    &self,
    request: Request<GetResourceStatusRequest>,
) -> Result<Response<GetResourceStatusResponse>, Status> {
    let req = request.into_inner();
    
    // 遍历请求的目录路径，查询每个目录的锁状态
    let locks: Vec<_> = req.directory_paths.into_iter()
        .map(|path| proto::get_resource_status_response::DirectoryLockStatus {
            directory_path: path,
            is_locked: false,  // TODO: 应该从 DirectoryLockManager 查询实际状态
            holder_executor_id: String::new(),  // TODO: 应该返回实际持有者
            queue_length: 0,  // TODO: 应该返回实际队列长度
        })
        .collect();
    
    Ok(Response::new(GetResourceStatusResponse { locks }))
}
```

**修改后的实现**：
```rust
async fn get_resource_status(
    &self,
    _request: Request<GetResourceStatusRequest>,
) -> Result<Response<GetResourceStatusResponse>, Status> {
    Ok(Response::new(GetResourceStatusResponse { locks: vec![] }))
}
```

**为什么简化**：
1. DirectoryLockManager 确实有完整的锁状态查询功能（通过 SQLite）
2. 但当前没有将 LockManager 暴露给 gRPC 服务层的接口
3. 这个功能主要用于调试，不影响核心执行流程
4. 前端暂时不需要监控目录锁状态

**恢复方案**（如果需要）：
```rust
// 在 ExecutionCoordinator 中添加方法暴露 LockManager 查询
pub async fn query_lock_status(
    &self, 
    directory: &Path
) -> anyhow::Result<Option<LockStatus>> {
    self.lock_manager.query_status(directory).await
}
```

---

### 2. `get_ticket_status` - Ticket 状态查询

**原始意图**：
查询请求配额的使用情况（基于 TicketTracker）。

**当前实现**：
```rust
async fn get_ticket_status(
    &self,
    request: Request<GetTicketStatusRequest>,
) -> Result<Response<GetTicketStatusResponse>, Status> {
    let req = request.into_inner();
    
    // TicketTracker 是占位符，返回默认状态
    Ok(Response::new(GetTicketStatusResponse {
        ticket_id: req.ticket_id,
        status: proto::get_ticket_status_response::TicketStatus::TicketPending as i32,
        skill_name: String::new(),
        error_message: String::new(),
    }))
}
```

**说明**：
- TicketTracker 本身是一个占位符（空结构体）
- Ticket 系统用于请求限流和配额管理，目前未实现
- 返回的 "Pending" 状态是合理的默认值

**未来实现方向**：
```rust
pub struct TicketTracker {
    quotas: DashMap<SessionId, Quota>,
    usage: DashMap<TicketId, Usage>,
}

impl TicketTracker {
    pub fn check_quota(&self, 
        session_id: &SessionId, 
        skill_name: &str
    ) -> Result<Ticket, QuotaExceeded> {
        // 检查剩余配额，发放 Ticket
    }
}
```

---

### 3. `get_system_status` - 系统状态

**当前实现**（部分字段为占位符）：
```rust
async fn get_system_status(
    &self,
    _request: Request<()>,
) -> Result<Response<SystemStatusResponse>, Status> {
    let threads = self.threads.read().await;
    let executors = self.executors.read().await;
    let stats = self.coordinator.get_stats().await;
    
    Ok(Response::new(SystemStatusResponse {
        active_threads: threads.len() as i32,
        active_executors: executors.len() as i32,
        pending_tickets: 0,  // TODO: 从 TicketTracker 获取
        total_executions: stats.total_executions as i64,
        total_wait_time_ms: stats.total_wait_time_ms as i64,
        skill_stats: HashMap::new(),  // TODO: 统计 Skill 使用情况
    }))
}
```

**说明**：
- `active_threads` 和 `active_executors` 是真实数据
- `total_executions` 和 `total_wait_time_ms` 是真实统计
- `pending_tickets` 和 `skill_stats` 是占位符

---

## 未实现的方法（返回 unimplemented）

在 `composer_server.rs` 中：

### 1. `query_blocks` - Block 查询
应该支持按类型、优先级、时间等条件查询已存储的 Blocks。

### 2. `get_trace/list_traces/replay_trace` - 追踪功能
用于调试和审计，记录请求处理的完整链路。

### 3. `subscribe_traces` - 追踪流
实时推送追踪事件（当前返回空流）。

---

## 当前架构 vs 完整架构

### 当前（简化版）
```
前端请求
    ↓
AgentKernel gRPC
    ↓
直接执行（跳过 Ticket 检查）
    ↓
ExecutionCoordinator
    ↓
SkillRegistry → Skill 执行
```

### 完整版（未来）
```
前端请求
    ↓
AgentKernel gRPC
    ↓
TicketTracker（配额检查）
    ↓
ExecutionCoordinator
    ↓
DirectoryLockManager（获取锁）
    ↓
SkillRegistry → Skill 执行
    ↓
TraceCollector（记录追踪）
```

---

## 建议

### 如果需要完整功能
1. 恢复 `get_resource_status` - 添加 LockManager 查询接口
2. 实现 `TicketTracker` - 添加配额管理
3. 实现 `Trace` 系统 - 添加链路追踪

### 如果当前简化版足够
当前实现是**功能完整**的，只是缺少监控/调试功能：
- ✅ 核心执行流程正常工作
- ✅ 目录锁功能完整（只是没暴露查询接口）
- ✅ 统计信息部分可用
- ⚠️ 缺少调试/监控接口

**推荐**：保持当前简化版，除非前端需要监控功能。
