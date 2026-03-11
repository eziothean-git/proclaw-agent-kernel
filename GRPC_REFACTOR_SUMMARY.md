# gRPC信息流架构重构总结

## 重构目标
将原有的"轮询+文件系统"混用架构重构为**纯gRPC流架构**，解决：
1. 信息流混乱（轮询和gRPC混用）
2. 服务关闭不彻底

## 架构变更

### 旧架构（混乱）
```
Gateway → Request Manager: gRPC SubmitRequest
Request Manager → Python Kernel: 文件系统inbox（Python轮询1秒）
Python Kernel → Gateway: HTTP Webhook回调
Gateway响应查询: 轮询outbox文件（500ms）
```

### 新架构（纯gRPC）
```
Gateway → Request Manager: gRPC Unary SubmitRequest
Request Manager → Python Kernel: gRPC Server Stream StreamTasks
Python Kernel → Request Manager: gRPC Unary SubmitResult
Request Manager → Gateway: gRPC Server Stream SubscribeResponses
```

## 修改文件清单

### 1. Protocol Buffer定义
- `agent-kernel/apps/request-manager/src/proto/request-manager.proto`
  - 添加 `KernelWorker` 服务（Server Streaming）
  - 添加 `GatewayListener` 服务（Server Streaming）
  - 添加 `shutdown` 和 `healthCheck` 方法
  - 添加 `KernelResponse`, `SubmitResultResponse` 等消息

### 2. Request Manager (TypeScript)
- `agent-kernel/apps/request-manager/src/grpc/request-manager.server.ts`
  - 实现 `KernelWorker.StreamTasks` - 向Python推送任务
  - 实现 `KernelWorker.SubmitResult` - 接收处理结果
  - 实现 `GatewayListener.SubscribeResponses` - 向Gateway推送响应
  - 添加任务调度器自动推送任务给可用Worker
  - 实现 `shutdown` 和 `healthCheck` 方法

### 3. Python Kernel
- `agent-kernel/apps/python-kernel/grpc_worker_client.py` (新文件)
  - gRPC客户端订阅任务流
  - 处理任务并通过Unary调用返回结果
  - 移除所有文件系统轮询

- `agent-kernel/apps/python-kernel/main.py`
  - 移除 `inbox_watcher` 轮询
  - 使用 `grpc_worker_client` 接收任务
  - 添加 `/v1/shutdown` HTTP端点（10秒超时）
  - 移除HTTP回调逻辑（改为gRPC返回结果）

### 4. Gateway (TypeScript)
- `agent-kernel/apps/gateway/src/grpc/request-manager.client.ts`
  - 添加 `subscribeResponses` 方法订阅响应流
  - 移除outbox轮询逻辑

### 5. 脚本
- `stop-all.sh`
  - 使用HTTP `/v1/shutdown` 端点优雅关闭服务
  - 10秒超时等待
  - 超时后强制清理

### 6. 文档
- `AGENTS.md`
  - 更新架构图（gRPC流架构）
  - 更新服务关闭说明
  - 更新实现状态

## 关键设计决策

### 1. 单向流 vs 双向流
**选择：单向流（Server Streaming）**
- Request Manager → Python Kernel: Server Streaming推送任务
- Python Kernel → Request Manager: Unary调用返回结果

**原因**：比双向流更简单，满足需求且易于理解和调试。

### 2. 持久化策略
**决策**：保留文件系统持久化，但不用于通信
- Request Manager仍写入inbox（作为审计日志备份）
- Python Kernel不再轮询inbox
- Gateway可选保留outbox（作为响应备份）

### 3. 关闭机制
**实现**：HTTP端点 + 10秒超时
- Gateway: `POST /v1/shutdown`
- Python Kernel: `POST /v1/shutdown`
- Request Manager: 暂时使用kill（后续可添加HTTP端点）

## 未完成的优化

由于时间限制，以下优化尚未完成：

1. **Gateway gRPC客户端更新** - 需要完整实现响应流订阅
2. **Worker池管理** - 需要更好的Worker容量管理和负载均衡
3. **错误重试机制** - gRPC连接断开时的重连逻辑
4. **测试覆盖** - 需要针对新架构的集成测试

## 测试建议

重构后需要验证：
1. 基本请求-响应流程：Gateway → RM → Kernel → RM → Gateway
2. 并发请求处理：多个请求同时处理
3. 优雅关闭：shutdown端点正确工作
4. 错误恢复：Kernel断开重连
5. 性能对比：相比轮询架构的延迟改善

## 注意事项

1. **Python依赖**：需要安装 `grpcio` 和 `grpcio-tools`
2. **Proto同步**：修改proto后需要同步到所有服务并重新生成代码
3. **端口冲突**：确保50052(gRPC), 8000(Kernel), 3000(Gateway)可用
4. **启动顺序**：Request Manager必须先启动，以便Kernel可以连接
