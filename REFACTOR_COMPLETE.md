# gRPC信息流架构重构 - 完成总结

## 重构完成 ✅

### 最终架构

```
┌─────────────┐     gRPC Unary      ┌──────────────────┐
│   Gateway   │ ───────────────────> │ Request Manager  │
│  (Port 3000)│  SubmitRequest       │   (Port 50052)   │
└──────┬──────┘                      └────────┬─────────┘
       ^                                       │
       │          HTTP Callback                │ gRPC Server Stream
       │          (via Skill)                  ▼
       │                              ┌──────────────────┐
       │                              │  Python Kernel   │
       └──────────────────────────────│   (Port 8000)    │
                                      └──────────────────┘
```

**关键变更：**
1. **Request Manager → Kernel**: gRPC Server Stream `StreamTasks` 推送任务
2. **Kernel → Gateway**: HTTP POST `/gateway/webhook/kernel-response` 回调结果
3. **Kernel → Request Manager**: gRPC Unary `TaskComplete` 通知完成（仅调度用）
4. **移除**: GatewayListener服务、SubmitResult方法（不再需要）

## 新增文件

### 1. System Skills
```
skills/
└── system-skills/
    ├── __init__.py
    ├── gateway_callback_skill.py  # HTTP回调Gateway
    └── README.md
```

### 2. 重构文件
- `agent-kernel/apps/request-manager/src/proto/request-manager.proto` - 简化proto定义
- `agent-kernel/apps/request-manager/src/grpc/request-manager.server.ts` - 移除GatewayListener
- `agent-kernel/apps/python-kernel/grpc_worker_client.py` - 使用HTTP回调skill
- `stop-all.sh` - 优雅关闭脚本

## 数据流

### 请求处理流程
1. **Client** 发送请求到 **Gateway** (HTTP)
2. **Gateway** 通过 gRPC `SubmitRequest` 发送给 **Request Manager**
3. **Request Manager** 将任务存入队列
4. **Request Manager** 通过 gRPC `StreamTasks` 推送给 **Kernel**
5. **Kernel** 处理任务
6. **Kernel** 通过 **GatewayCallbackSkill** HTTP回调 **Gateway**
7. **Kernel** 通过 gRPC `TaskComplete` 通知 **Request Manager**（仅更新状态）
8. **Gateway** 保存结果到outbox
9. **Client** 从Gateway获取响应

### 优雅关闭流程
1. `stop-all.sh` 发送 HTTP `POST /v1/shutdown` 到 Gateway
2. `stop-all.sh` 发送 HTTP `POST /v1/shutdown` 到 Python Kernel
3. 各服务有10秒时间完成当前请求
4. 超时后强制终止

## 测试建议

### 基本测试
```bash
# 1. 启动所有服务
./launcher.sh

# 2. 发送测试请求
curl -X POST http://localhost:3000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Hello, how are you?",
    "userId": "test-user"
  }'

# 3. 优雅关闭
./stop-all.sh
```

### 验证点
- [ ] 请求能正确流转：Gateway → RM → Kernel → Gateway
- [ ] Kernel直接HTTP回调Gateway（检查webhook controller日志）
- [ ] TaskComplete通知RM（检查RM日志）
- [ ] 优雅关闭正常工作（10秒超时）
- [ ] 无文件系统轮询（检查inbox_watcher是否被禁用）

## 注意事项

1. **依赖安装**：确保安装了 `grpcio` 和 `httpx`
   ```bash
   pip install grpcio grpcio-tools httpx
   ```

2. **环境变量**：
   - `GATEWAY_URL`: Gateway地址 (默认: http://localhost:3000)
   - `REQUEST_MANAGER_GRPC_ADDRESS`: RM gRPC地址 (默认: localhost:50052)

3. **启动顺序**：Request Manager 必须先启动

4. **LSP错误**：IDE可能显示grpc_generated的导入错误，但实际运行正常

## 性能优化点（未来）

1. **连接池**：HTTP客户端已配置连接池
2. **批量回调**：当前是单个请求回调，可优化为批量
3. **心跳机制**：可添加定期心跳检查Worker健康
4. **负载均衡**：多Kernel实例支持

## 文档更新

- `AGENTS.md` - 已更新架构图和关闭说明
- `GRPC_REFACTOR_SUMMARY.md` - 重构详细记录
- `skills/system-skills/README.md` - Skill使用文档

---

**重构完成时间**: 2026-03-11
**主要变更**: 移除轮询，改为纯gRPC流+HTTP回调架构
**测试状态**: 待验证