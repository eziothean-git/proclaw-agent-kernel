# Request Manager（请求管理器）

基于优先级的 TypeScript + gRPC 请求管理器，完全替换原有 Python 实现。

## 特性

- **多级优先级队列**: 支持 P0-P4 五级优先级（100, 50, 10, 0, -10）
- **非抢占式调度**: 高优先级优先，但不中断正在执行的任务
- **会话亲和性**: 同一会话请求串行执行，保证顺序
- **并发控制**: 最大5个并发请求
- **超时与重试**: 按优先级不同超时时间，指数退避重试（最多3次）
- **全量持久化**: inbox + audit + state 三重持久化
- **gRPC 全链路**: Gateway ↔ Request Manager ↔ Prime Personality
- **Skill Hook**: Prime Personality 通过 Agentic OS Interface Skill 回调 Gateway

## 技术栈

- TypeScript 5.6+
- NestJS 10
- gRPC (@grpc/grpc-js)
- Protocol Buffers

## 架构

```
┌──────────┐   gRPC    ┌──────────────────────────────────────┐
│ Gateway  │──────────→│         Request Manager              │
│          │           │  ┌────────────────────────────────┐  │
│          │           │  │  Inbox (持久化)                │  │
│          │           │  │  Priority Queue (P0-P4)        │  │
│          │           │  │  Worker Pool (Max 5)           │  │
│          │           │  │  Session Affinity              │  │
│          │           │  │  Retry/Timeout                 │  │
│          │           │  │  Audit (全量记录)              │  │
│          │           │  └────────────────────────────────┘  │
└────┬─────┘           └──────────────────┬───────────────────┘
     │                                      │
     │ gRPC                                 │ gRPC
     │                                      ↓
     │                              ┌───────────────┐
     │                              │ Prime         │
     │                              │ Personality   │
     │                              └───────┬───────┘
     │                                      │
     │         Agentic OS Interface Skill   │
     │         (用户/自动化系统 Request)      │
     │                                      ↓
     │                              ┌───────────────┐
     └──────────────────────────────│   Gateway     │
        (Skill Hook 回调)            │  [写入outbox] │
                                    │  [推送给用户]  │
                                    └───────────────┘
```

## 信息流

```
1. Gateway 接收用户请求
   ↓ gRPC SubmitRequest
2. Request Manager 接收并持久化到 inbox
   ↓ 
3. 按优先级入队 (P0 > P1 > P2 > P3 > P4)
   ↓
4. Worker Pool 获取任务 (Max 5 并发)
   ↓
5. 检查 Session Affinity (同 session 串行)
   ↓
6. 调用 Prime Personality (gRPC，带超时)
   ↓
7. Prime Personality 处理完成
   ↓ 通过 Agentic OS Interface Skill
8. Gateway Skill Hook 接收响应
   ↓
9. Gateway 写入 outbox 并推送给用户
   ↓ (可选回调)
10. Request Manager 更新任务状态
```

## 安装

```bash
cd agent-kernel/apps/request-manager
npm install
```

## 配置

复制 `.env.example` 为 `.env` 并修改：

```bash
cp .env.example .env
```

关键配置项：

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `REQUEST_MANAGER_GRPC_PORT` | gRPC 服务端口 | 50052 |
| `MAX_CONCURRENT_REQUESTS` | 最大并发数 | 5 |
| `MAX_QUEUE_SIZE` | 队列最大长度 | 1000 |
| `TIMEOUT_P0_MS` | P0紧急请求超时 | 30000ms |
| `TIMEOUT_P4_MS` | P4后台任务超时 | 300000ms |
| `PRIME_PERSONALITY_GRPC_URL` | Prime Personality gRPC地址 | localhost:50051 |

## 运行

### 开发模式

```bash
npm run start:dev
```

### 生产模式

```bash
npm run build
npm run start
```

## gRPC 接口

### Gateway → Request Manager

定义在 `src/proto/request-manager.proto`

```protobuf
service RequestManager {
  rpc SubmitRequest (SubmitRequestRequest) returns (SubmitRequestResponse);
  rpc GetRequestStatus (GetRequestStatusRequest) returns (GetRequestStatusResponse);
  rpc CancelRequest (CancelRequestRequest) returns (CancelRequestResponse);
  rpc StreamRequestStatus (GetRequestStatusRequest) returns (stream StatusUpdate);
  rpc GetQueueStatus (GetQueueStatusRequest) returns (GetQueueStatusResponse);
  rpc GetWorkerStatus (GetWorkerStatusRequest) returns (GetWorkerStatusResponse);
  rpc RetryRequest (RetryRequestRequest) returns (RetryRequestResponse);
}
```

### Request Manager → Prime Personality

定义在 `src/proto/prime-personality.proto`

```protobuf
service PrimePersonality {
  rpc ProcessRequest (ProcessRequestRequest) returns (ProcessRequestResponse);
  rpc HealthCheck (HealthCheckRequest) returns (HealthCheckResponse);
}
```

## 优先级定义

| 优先级 | 数值 | 名称 | 说明 |
|--------|------|------|------|
| P0 | 100 | EMERGENCY | 系统级紧急请求 |
| P1 | 50 | SCHEDULED | 定时请求（主人格留言） |
| P2 | 10 | HIGH | 高优先级用户请求 |
| P3 | 0 | NORMAL | 普通用户请求（默认） |
| P4 | -10 | BACKGROUND | 后台任务 |

## 持久化结构

```
/var/gateway/request-manager/
├── inbox/                    # 请求持久化
│   ├── {YYYY-MM-DD}/
│   │   └── {request_id}.json
│   └── index.jsonl
├── audit/                    # 审计日志（全量记录）
│   └── {YYYY-MM-DD}/
│       └── audit.jsonl
└── state/                    # 状态快照（可恢复）
    ├── current.json
    └── snapshot-{timestamp}.json
```

## 审计日志事件类型

- `request_received`: 请求接收
- `request_queued`: 请求入队
- `request_started`: 开始处理
- `prime_personality_called`: 调用主人格
- `prime_personality_completed`: 主人格处理完成
- `prime_personality_failed`: 主人格处理失败
- `request_completed`: 请求完成
- `request_failed`: 请求失败
- `retry_scheduled`: 计划重试
- `max_retries_exceeded`: 超过最大重试次数
- `manual_retry`: 手动重试

## 目录结构

```
src/
├── constants/                # 常量定义
│   └── index.ts
├── exceptions/               # 自定义异常
│   └── index.ts
├── grpc/                     # gRPC 客户端和服务
│   ├── prime-personality.client.ts
│   ├── request-manager.server.ts
│   └── proto/
│       ├── prime-personality.proto
│       └── request-manager.proto
├── interfaces/               # TypeScript 接口
│   └── index.ts
├── services/                 # 核心服务
│   ├── audit-logger.service.ts
│   ├── persistence.service.ts
│   ├── priority-queue.service.ts
│   ├── priority-request-manager.service.ts
│   ├── retry-handler.service.ts
│   ├── session-affinity.service.ts
│   └── worker-pool.service.ts
├── request-manager.module.ts
└── main.ts
```

## 开发

### 生成 gRPC 代码（如需）

```bash
npm run proto:gen
```

### 代码检查

```bash
npm run lint
npm run format
```

### 测试

```bash
npm run test
npm run test:cov
```

## 与 Gateway 集成

Request Manager 与 Gateway 通过 gRPC 通信：

1. **Gateway** 通过 gRPC 提交请求给 Request Manager
2. **Request Manager** 调度并调用 Prime Personality
3. **Prime Personality** 通过 Skill Hook 回调 Gateway
4. **Gateway** 接收响应并推送给用户

两者通过 gRPC 紧密协作，但都保持独立运行。

## License

MIT