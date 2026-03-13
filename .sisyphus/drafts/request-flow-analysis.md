# 分析：Request Manager 到 Prime 到 Gateway 的信息流

## 🔍 当前状态分析

### 已实现组件

| 组件 | 文件 | 状态 |
|------|------|------|
| Rust Prime Personality gRPC Server | `kernel-v2/src/server/prime_personality_server.rs` | ✅ 已实现 |
| TypeScript Prime Personality Client | `agent-kernel/apps/request-manager/src/grpc/prime-personality.client.ts` | ✅ 已实现 |
| TypeScript Worker Pool | `agent-kernel/apps/request-manager/src/services/worker-pool.service.ts` | ✅ 已实现 |

### 关键发现

#### 1. TypeScript 端当前使用 HTTP API 而非 gRPC

在 `worker-pool.service.ts` 第 139 行：
```typescript
private async callPythonKernelHttpApi(task: RequestTask, timeoutMs: number): Promise<ProcessResult> {
    const url = `${this.pythonKernelUrl}/v1/execute`;  // http://localhost:8000/v1/execute
```

**Worker Pool 当前调用的是 Python Kernel 的 HTTP API，而不是 Rust Prime Personality 的 gRPC 服务！**

#### 2. Prime Personality Client 存在但未被使用

`PrimePersonalityClient` 类已实现 gRPC 客户端（连接 `localhost:50051`），但在代码库中搜索发现它**没有被任何其他服务注入或使用**。

#### 3. Rust Prime Personality 的双重返回机制

在 `prime_personality_server.rs` 中：

```rust
// 1. 通过 Skill 发送结果回 Gateway
if let Err(e) = self.send_ir_to_gateway(ir.clone()).await {
    warn!(error = %e, "Failed to send IR to gateway");
}

// 2. 通过 gRPC 响应返回 IR
Ok(Response::new(ProcessRequestResponse {
    request_id,
    status: ProcessingStatus::Completed as i32,
    ir: Some(proto_ir),
    error_message: String::new(),
}))
```

**问题**：`send_ir_to_gateway()` 尝试调用 `os_interface.submit_ir_result`，但这个工具**不存在**！

#### 4. OS Interface Skill 的工具列表

在 `os_interface_skill.rs` 中，可用的工具只有：
- `list_sessions`
- `get_session_info`
- `delete_session`
- `create_process`
- `list_processes`
- `get_process_info`
- `delete_process`
- `query_session_history`

**没有 `submit_ir_result`！**

## ❌ 缺失的组件

### 1. Gateway Skill（或 SendReply Skill）

根据架构描述，Prime Personality 应该通过 Skill 调用将 IR 发送回 Gateway。但 Rust kernel 中没有实现这个 Skill。

**可能的位置**：
- 新文件：`kernel-v2/src/skills/gateway_skill.rs` 或 `send_reply_skill.rs`
- 功能：接收 IR 并通过 HTTP/webhook 发送到 Gateway

### 2. TypeScript 端切换到 gRPC

当前 TypeScript Request Manager 使用 HTTP API 调用 Python Kernel。如果要使用 Rust Prime Personality，需要：

**选项 A**：修改 `worker-pool.service.ts` 使用 `PrimePersonalityClient`
**选项 B**：保持 HTTP API，让 Rust kernel 也提供 HTTP 接口

## 🔄 预期的完整流程

### 设计意图（根据架构文档）

```
┌────────────────────────────────────────────────────────────────────┐
│  Gateway (TypeScript)                                               │
│  - 接收用户请求                                                     │
│  - 提交给 Request Manager                                          │
└───────────────────────────┬────────────────────────────────────────┘
                            │ gRPC SubmitRequest
                            ▼
┌────────────────────────────────────────────────────────────────────┐
│  Request Manager (TypeScript)                                       │
│  - 优先级队列调度                                                   │
│  - Worker Pool 获取任务                                             │
└───────────────────────────┬────────────────────────────────────────┘
                            │ gRPC ProcessRequest
                            ▼
┌────────────────────────────────────────────────────────────────────┐
│  Prime Personality (Rust)                                           │
│  - gRPC 接收请求                                                    │
│  - BlockComposer 组装上下文                                          │
│  - LLM 生成 IR                                                      │
│  - 通过 Skill 调用发送 IR                                            │
└───────────────────────────┬────────────────────────────────────────┘
                            │ Skill: submit_ir_result
                            ▼
┌────────────────────────────────────────────────────────────────────┐
│  Gateway Skill / SendReply Skill                                    │
│  - 接收 IR                                                          │
│  - 通过 HTTP/webhook 发送给 Gateway                                 │
└───────────────────────────┬────────────────────────────────────────┘
                            │ HTTP POST /gateway/webhook/kernel-response
                            ▼
┌────────────────────────────────────────────────────────────────────┐
│  Gateway (TypeScript)                                               │
│  - Webhook 接收 IR                                                  │
│  - 编译 IR 为接入点格式                                              │
│  - 发送给用户                                                       │
└────────────────────────────────────────────────────────────────────┘
```

### 当前实际的流程

```
Gateway -> Request Manager -> Python Kernel HTTP API (localhost:8000)
                              -> Prime Personality (Python)
                              -> 返回 IR
                              -> Webhook 到 Gateway
```

Rust Prime Personality gRPC 服务（端口 50051）**目前没有被使用**。

## 📝 需要完成的工作

### 高优先级

1. **创建 Gateway Skill（Rust）**
   - 文件：`kernel-v2/src/skills/gateway_skill.rs`
   - 功能：
     - 工具：`submit_ir_result`
     - 接收 IR 并通过 HTTP POST 发送到 Gateway webhook
     - 配置：Gateway URL、认证信息等

2. **注册 Gateway Skill**
   - 在 `skill_registry.rs` 中注册
   - 在 `main.rs` 中初始化

3. **修复 Prime Personality Server**
   - 更改 `send_ir_to_gateway()` 使用 `gateway` skill 而不是 `os_interface`

4. **TypeScript 端切换到 gRPC（可选）**
   - 修改 `worker-pool.service.ts` 使用 `PrimePersonalityClient`
   - 或者创建适配层保持 HTTP API 兼容

### 中优先级

5. **配置管理**
   - Gateway URL 配置
   - Webhook endpoint 配置
   - 认证/安全设置

6. **错误处理**
   - Skill 调用失败的重试机制
   - 死信队列

## 🤔 需要澄清的问题

1. **Gateway Skill 的具体实现**：
   - Gateway webhook URL 是什么？（从代码看是 `/gateway/webhook/kernel-response`）
   - 需要什么认证？
   - IR 应该包装成什么格式发送？

2. **TypeScript 端切换**：
   - 应该保持 HTTP API 兼容还是完全切换到 gRPC？
   - 是否需要渐进式迁移？

3. **回调机制**：
   - 当前 Worker Pool 等待同步响应，但 Skill 调用是异步的
   - 需要如何处理这种情况？

## 🎯 建议的下一步

1. 确认 Gateway webhook 的具体实现细节
2. 创建 Gateway Skill 实现
3. 修复 Prime Personality 中的 skill 调用
4. 测试端到端流程

运行 `/start-work` 开始执行这些任务。
