# Gateway 架构文档

> 版本: 0.2.0  
> 最后更新: 2026-03-09  
> 状态: 重构为文件系统解耦架构

## 1. 概述

Gateway 是 Agent Kernel 系统的**对外网关**，采用**基于文件系统的完全解耦架构**。

**核心职责**：
1. **接收外部请求**：从 CLI、HTTP、WebSocket、QQ Bot 等接入点接收用户输入
2. **转换为 IR**：将外部消息转换为内部中间表示（Input IR）
3. **持久化到文件系统**：写入信箱目录，立即返回确认
4. **监控响应文件**：等待请求管理器处理完成
5. **推送响应**：将输出 IR 编译为平台格式，推送给用户

**架构原则**：
- **零耦合**：Gateway 不直接调用任何 Kernel 服务，仅通过文件系统通信
- **生产者-消费者模式**：Gateway 是生产者，请求管理器是消费者
- **文件系统即消息队列**：/var/gateway/inbox/ 和 /var/gateway/outbox/
- **全量持久化**：所有数据追加式写入，支持审计和 Agent 自检

## 2. 文件系统结构（信箱机制）

```
/var/gateway/
├── inbox/                    # 【请求信箱】Gateway 写入，请求管理器读取
│   ├── {YYYY-MM-DD}/         # 按日期分区
│   │   └── {request_id}.json # 输入 IR（完整消息）
│   └── index.jsonl           # 索引：request_id, timestamp, status
│
├── outbox/                   # 【响应信箱】请求管理器写入，Gateway 读取
│   ├── {YYYY-MM-DD}/
│   │   └── {request_id}.json # 输出 IR（处理结果）
│   └── index.jsonl           # 索引：request_id, timestamp, status
│
├── attachments/              # 附件存储
│   ├── {YYYY-MM-DD}/
│   │   └── {uuid}/
│   │       ├── metadata.json
│   │       └── {filename}
│   └── index.jsonl
│
├── pending/                  # 【处理中】请求管理器标记正在处理的请求
│   └── {request_id}.json     # 软链接或状态文件
│
├── archive/                  # 归档（可选）
│   └── {YYYY-MM}/            # 按月归档
│
├── sessions/                 # 会话状态
│   └── {session_id}/
│       ├── state.json
│       └── events.jsonl
│
└── logs/                     # 运行时日志
    └── gateway.log
```

**信箱协议**：
1. **写入顺序**：先写 `.json` 文件，再追加 `index.jsonl`（原子性）
2. **状态流转**：`inbox/` → `pending/` → `outbox/` → （可选）`archive/`
3. **文件命名**：`{request_id}.json`，UUIDv4 格式
4. **索引格式**：每行一个 JSON 对象，追加写入

## 3. 数据流（文件系统信箱）

```
┌──────────┐     ┌─────────────────┐     ┌─────────────────┐
│   用户    │────→│     Gateway      │────→│  inbox/         │
│ (CLI/HTTP│     │                  │     │  (请求信箱)      │
│ /QQ Bot) │     │ 1. 接收请求      │     │                 │
└──────────┘     │ 2. 转换为 IR     │     │ 3. 写入文件      │
     ▲           │ 3. 保存附件      │     │ 4. 更新索引      │
     │           │ 4. 立即返回 OK   │     └─────────────────┘
     │           └─────────────────┘              │
     │                                            │
     │           ┌─────────────────┐              │
     │           │  请求管理器      │◄─────────────┘
     │           │  (独立进程)      │     【监听文件系统】
     │           │                 │
     │           │ 1. 扫描 inbox   │
     │           │ 2. 按优先级排序  │
     │           │ 3. 串行处理      │
     │           │ 4. 调用 Prime    │
     │           │    Personality   │
     │           └─────────────────┘
     │                    │
     │                    ↓
     │           ┌─────────────────┐
     │           │  Session Host   │
     │           │  + Executor     │
     │           └─────────────────┘
     │                    │
     │                    ↓
     │           ┌─────────────────┐
     └───────────│  outbox/        │
                 │  (响应信箱)      │     【写入响应】
                 └─────────────────┘
                          │
                          ↓
                 ┌─────────────────┐
                 │     Gateway      │
                 │  【监控 outbox】 │
                 │                 │
                 │ 1. 检测新文件    │
                 │ 2. 读取响应 IR   │
                 │ 3. 编译平台格式  │
                 │ 4. 推送给用户    │
                 └─────────────────┘
```

**关键特性**：
- Gateway 和请求管理器完全独立，可分别重启
- 文件系统作为持久化消息队列
- 支持请求积压（文件堆积）
- 支持审计（完整历史记录）

## 4. 内部中间表示（IR）

### 4.1 输入 IR（Gateway → inbox）

文件路径：`/var/gateway/inbox/{YYYY-MM-DD}/{request_id}.json`

```json
{
  "header": {
    "timestamp": "2026-03-09T10:30:00.000Z",
    "platform": "cli|http|websocket|qq",
    "device_id": "device-uuid",
    "user_id": "user-123",
    "session_id": "sess-uuid",
    "request_id": "req-uuid",
    "source_ip": "127.0.0.1",
    "client_version": "1.0.0",
    "priority": 0
  },
  "metadata": {
    "attachments": [
      {
        "index": 0,
        "local_path": "/var/gateway/attachments/2026-03-09/uuid/file.png",
        "original_name": "screenshot.png",
        "mime_type": "image/png",
        "size_bytes": 102400,
        "checksum": "sha256-abc123..."
      }
    ],
    "tags": ["important", "debug"]
  },
  "body": "请分析这张图片 [attachment:0]"
}
```

### 4.2 输出 IR（outbox → Gateway）

文件路径：`/var/gateway/outbox/{YYYY-MM-DD}/{request_id}.json`

```json
{
  "header": {
    "request_id": "req-uuid",
    "session_id": "sess-uuid",
    "timestamp": "2026-03-09T10:30:05.000Z",
    "processing_time_ms": 5000,
    "model_version": "gpt-4",
    "compiler_version": "1.0.0"
  },
  "status": "completed|failed|partial",
  "body": "这是一张...",
  "metadata": {
    "attachments": [
      {
        "local_path": "/var/gateway/attachments/2026-03-09/uuid/output.png",
        "mime_type": "image/png",
        "description": "生成的图表"
      }
    ],
    "actions": [
      {
        "type": "tool_call",
        "skill": "filesystem",
        "tool": "read_file",
        "status": "success",
        "duration_ms": 100
      }
    ]
  },
  "error": {
    "category": "system_error|timeout|invalid_request|skill_failure|unknown",
    "code": "ERR_001",
    "message": "...",
    "recoverable": true,
    "audit_log_ref": "/var/gateway/errors/2026-03-09/req-uuid.json"
  },
  "artifacts": {
    "files_modified": ["/path/to/file"],
    "commands_executed": ["git status"]
  }
}
```

## 5. Gateway 和请求管理器的接口契约

### 5.1 Gateway 的职责（生产者）

**写入 inbox**：
```typescript
// 伪代码
async function handleUserRequest(externalMsg) {
  // 1. 生成 request_id
  const requestId = uuidv4();
  
  // 2. 转换 IR
  const inputIR = convertToInputIR(externalMsg, requestId);
  
  // 3. 保存附件
  if (externalMsg.attachments) {
    for (const att of externalMsg.attachments) {
      await saveAttachment(att.buffer, att.metadata);
    }
  }
  
  // 4. 写入 inbox
  const dateDir = getDateDir();
  const filePath = `/var/gateway/inbox/${dateDir}/${requestId}.json`;
  await fs.writeFile(filePath, JSON.stringify(inputIR, null, 2));
  
  // 5. 追加索引
  await appendToIndex('/var/gateway/inbox/index.jsonl', {
    request_id: requestId,
    timestamp: new Date().toISOString(),
    status: 'pending',
    user_id: inputIR.header.user_id,
    session_id: inputIR.header.session_id,
    priority: inputIR.header.priority || 0,
    path: filePath
  });
  
  // 6. 立即返回
  return { request_id: requestId, status: 'accepted' };
}
```

**监控 outbox**：
```typescript
// 文件系统监控（轮询或 inotify）
async function watchOutbox() {
  // 方式1：轮询（简单，跨平台）
  setInterval(async () => {
    const newFiles = await scanOutboxForNewFiles();
    for (const file of newFiles) {
      const response = await readResponseFile(file);
      await pushToUser(response);
      await markAsDelivered(file);
    }
  }, 1000); // 每秒轮询
  
  // 方式2：inotify（高效，Linux only）
  // 监听 /var/gateway/outbox/ 目录的 create 事件
}
```

### 5.2 请求管理器的职责（消费者）

**读取 inbox**：
```python
# 伪代码
async def request_manager_loop():
    while True:
        # 1. 扫描 inbox
        pending_requests = scan_inbox()
        
        # 2. 按优先级排序
        sorted_requests = sorted(
            pending_requests, 
            key=lambda r: (-r.priority, r.timestamp)
        )
        
        # 3. 串行处理（Prime Personality 单线程）
        for request in sorted_requests:
            # 标记为处理中
            mark_as_processing(request.request_id)
            
            try:
                # 4. 调用 Prime Personality
                result = await prime_personality.process(request)
                
                # 5. 路由到 Session Host
                session_result = await session_host.handle(result)
                
                # 6. 写入 outbox
                write_to_outbox(request.request_id, session_result)
                
            except Exception as e:
                # 7. 写入错误响应
                write_error_to_outbox(request.request_id, e)
            
            finally:
                # 8. 从 inbox 移除（或移到 archive）
                archive_request(request)
        
        # 9. 短暂休眠
        await asyncio.sleep(0.1)
```

**支持的请求来源**：
1. **Gateway 实时请求**：从 inbox 读取
2. **定时请求调度器**：预存在调度器队列，时间到时写入 inbox
3. **高权限 Hook**：直接写入 inbox（需审核）

### 5.3 文件格式规范

**索引文件（index.jsonl）**：
```jsonl
{"timestamp":"2026-03-09T10:30:00.000Z","request_id":"req-1","status":"pending","priority":0,"path":"inbox/2026-03-09/req-1.json"}
{"timestamp":"2026-03-09T10:31:00.000Z","request_id":"req-2","status":"processing","priority":1,"path":"pending/req-2.json"}
{"timestamp":"2026-03-09T10:32:00.000Z","request_id":"req-1","status":"completed","path":"outbox/2026-03-09/req-1.json"}
```

**状态定义**：
- `pending`：在 inbox 中等待处理
- `processing`：被请求管理器取出，正在处理
- `completed`：处理完成，响应在 outbox 中
- `failed`：处理失败，错误信息在 outbox 中

## 6. 关键组件

### 6.1 IR Converter Service

```typescript
interface IRConverterService {
  // 外部消息 → 输入 IR
  convertToInputIR(
    externalMsg: ExternalMessage, 
    requestId: string
  ): InputMessage;
  
  // 输出 IR → 平台格式
  compileOutputIR(
    ir: OutputMessage, 
    platform: string
  ): CompiledOutput;
  
  // 验证
  validateIR(ir: unknown, schema: 'input' | 'output'): ValidationResult;
}
```

### 6.2 Storage Service

```typescript
interface StorageService {
  // 写入 inbox
  saveRequest(request: InputMessage): Promise<string>;
  
  // 读取响应
  getResponse(requestId: string): Promise<OutputMessage | null>;
  
  // 保存附件
  saveAttachment(
    file: Buffer, 
    metadata: AttachmentMeta
  ): Promise<AttachmentMetadata>;
  
  // 监控 outbox（流式）
  watchOutbox(
    callback: (response: OutputMessage) => void
  ): Promise<void>;
  
  // 审计查询
  queryByDateRange(
    start: Date, 
    end: Date
  ): AsyncIterable<LogEntry>;
}
```

### 6.3 Platform Adapter

```typescript
interface PlatformAdapter {
  readonly platform: string;
  
  // 接收外部消息
  onMessage(
    handler: (msg: ExternalMessage) => Promise<void>
  ): void;
  
  // 发送回复（异步，等响应文件）
  sendResponse(
    context: RequestContext, 
    output: CompiledOutput
  ): Promise<void>;
  
  // 编译平台格式
  compileForPlatform(ir: OutputMessage): CompiledOutput;
}
```

## 7. API 端点（Gateway 暴露）

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/v1/chat` | 接收用户请求，立即返回 request_id（不等待处理） |
| GET | `/api/v1/requests/{request_id}` | 查询请求状态（读取 outbox） |
| GET | `/api/v1/requests/{request_id}/status` | 轮询状态（轻量级） |
| GET | `/api/v1/sessions/{session_id}/history` | 查询会话历史 |
| WS | `/ws/v1/stream` | WebSocket：请求提交 + 响应推送 |

**注意**：所有端点只操作文件系统，不直接调用 Kernel。

## 8. 实现阶段

### 阶段 1: 文件系统信箱（P0）
- [x] JSON Schema（input/output）
- [x] Storage Service（文件系统）
- [x] IR Converter Service
- [ ] Outbox 监控（轮询或 inotify）
- [ ] 请求状态查询 API

### 阶段 2: CLI 适配器（P0）
- [x] CLI Adapter 框架
- [ ] 集成完整流程（接收 → 写入 inbox → 监控 outbox → 推送）

### 阶段 3: HTTP + WebSocket（P1）
- [ ] HTTP REST API（异步）
- [ ] WebSocket 实时推送

### 阶段 4: 请求管理器协议（P1）
- [ ] 请求管理器实现指南
- [ ] 定时请求调度器接口
- [ ] 高权限 Hook 机制

### 阶段 5: QQ Bot（P2，暂不实现）

## 9. 设计决策记录

### 决策 1: 文件系统解耦
**原因**：Gateway 和请求管理器完全独立，可分别开发、测试、部署

### 决策 2: 无 HTTP 回调
**原因**：完全依赖文件系统，避免网络复杂性

### 决策 3: 追加式索引（JSONL）
**原因**：支持并发写入，流式读取，易于审计

### 决策 4: 轮询 vs inotify
**当前**：先实现轮询（简单、跨平台）  
**未来**：可优化为 inotify（Linux）或 FSEvents（macOS）

### 决策 5: 长期保留
**原因**：目录结构反映时间，便于审计和 Agent 自检

## 10. 请求管理器实现指南

### 10.1 最小实现（Python）

```python
#!/usr/bin/env python3
"""
最小请求管理器实现示例
监听 inbox，串行处理，写入 outbox
"""
import asyncio
import json
import os
from pathlib import Path
from datetime import datetime

INBOX_DIR = "/var/gateway/inbox"
OUTBOX_DIR = "/var/gateway/outbox"
PENDING_DIR = "/var/gateway/pending"

async def process_request(request_path: Path):
    """处理单个请求"""
    # 1. 读取请求
    with open(request_path) as f:
        request = json.load(f)
    
    request_id = request["header"]["request_id"]
    
    # 2. 标记为处理中
    pending_path = Path(PENDING_DIR) / f"{request_id}.json"
    pending_path.symlink_to(request_path.absolute())
    
    try:
        # 3. 调用 Prime Personality（伪代码）
        # result = await prime_personality.process(request)
        result = {
            "header": {
                "request_id": request_id,
                "session_id": request["header"]["session_id"],
                "timestamp": datetime.utcnow().isoformat(),
            },
            "status": "completed",
            "body": f"Processed: {request['body'][:50]}...",
        }
        
        # 4. 写入 outbox
        date_dir = datetime.now().strftime("%Y-%m-%d")
        outbox_date_dir = Path(OUTBOX_DIR) / date_dir
        outbox_date_dir.mkdir(parents=True, exist_ok=True)
        
        outbox_path = outbox_date_dir / f"{request_id}.json"
        with open(outbox_path, 'w') as f:
            json.dump(result, f, indent=2)
        
        # 5. 更新索引
        index_path = Path(OUTBOX_DIR) / "index.jsonl"
        with open(index_path, 'a') as f:
            f.write(json.dumps({
                "timestamp": datetime.utcnow().isoformat(),
                "request_id": request_id,
                "status": "completed",
                "path": str(outbox_path),
            }) + "\n")
        
        print(f"✓ Processed: {request_id}")
        
    except Exception as e:
        # 6. 错误处理
        error_result = {
            "header": {
                "request_id": request_id,
                "timestamp": datetime.utcnow().isoformat(),
            },
            "status": "failed",
            "body": "",
            "error": {
                "category": "system_error",
                "message": str(e),
                "recoverable": False,
            }
        }
        # 写入 outbox（失败响应）
        ...
        
    finally:
        # 7. 清理
        pending_path.unlink(missing_ok=True)
        # 可选：归档或删除 inbox 文件
        # request_path.unlink()

async def main():
    """主循环"""
    Path(INBOX_DIR).mkdir(parents=True, exist_ok=True)
    Path(OUTBOX_DIR).mkdir(parents=True, exist_ok=True)
    Path(PENDING_DIR).mkdir(parents=True, exist_ok=True)
    
    print("Request Manager started")
    print(f"Watching: {INBOX_DIR}")
    
    while True:
        # 扫描 inbox
        inbox_files = list(Path(INBOX_DIR).glob("**/*.json"))
        
        # 过滤掉正在处理的
        pending_files = {p.name for p in Path(PENDING_DIR).glob("*.json")}
        new_files = [f for f in inbox_files if f.name not in pending_files]
        
        if new_files:
            # 按优先级排序（读取文件内容）
            requests = []
            for f in new_files:
                with open(f) as fp:
                    req = json.load(fp)
                    requests.append((req["header"].get("priority", 0), f, req))
            
            requests.sort(reverse=True)  # 高优先级在前
            
            # 串行处理
            for priority, file_path, request in requests:
                await process_request(file_path)
        
        await asyncio.sleep(0.5)  # 轮询间隔

if __name__ == "__main__":
    asyncio.run(main())
```

### 10.2 定时请求调度器接口

```python
# 定时请求通过写入 inbox 触发
async def schedule_request(request_data: dict, execute_at: datetime):
    """定时请求：到时间后写入 inbox"""
    await asyncio.sleep((execute_at - datetime.now()).total_seconds())
    
    # 写入 inbox
    request_id = str(uuid.uuid4())
    date_dir = datetime.now().strftime("%Y-%m-%d")
    inbox_path = Path(INBOX_DIR) / date_dir / f"{request_id}.json"
    
    request_data["header"]["request_id"] = request_id
    request_data["header"]["timestamp"] = datetime.utcnow().isoformat()
    
    with open(inbox_path, 'w') as f:
        json.dump(request_data, f, indent=2)
    
    print(f"Scheduled request triggered: {request_id}")
```

## 11. 设计决策记录

### 决策 1: 文件系统解耦
**原因**: Gateway 和请求管理器完全独立，可分别开发、测试、部署

### 决策 2: 无 HTTP 回调
**原因**: 完全依赖文件系统，避免网络复杂性

### 决策 3: 追加式索引（JSONL）
**原因**: 支持并发写入，流式读取，易于审计

### 决策 4: 轮询 vs inotify
**当前**: 先实现轮询（简单、跨平台）  
**未来**: 可优化为 inotify（Linux）或 FSEvents（macOS）

### 决策 5: 长期保留
**原因**: 目录结构反映时间，便于审计和 Agent 自检

### 决策 6: 无写入队列（KISS 原则）
**原因**: 
- Node.js `fs.appendFile` 是原子操作，不会损坏 index.jsonl
- 文件系统 I/O 通常很快（毫秒级）
- Node.js 事件循环自动序列化 I/O 操作
- 实际并发量不大时，额外队列增加复杂度

**潜在风险**: 极端高并发下可能出现 I/O 竞争，但不会影响数据完整性

## 12. 相关文档

- `./schemas/input-message.json` - 输入 IR JSON Schema
- `./schemas/output-message.json` - 输出 IR JSON Schema
- `../python-kernel/` - Python Kernel 实现（Prime Personality 等）

## 13. 待解决问题

1. **并发控制**（低优先级）：极端高并发下可能需要文件锁或批量写入
2. **大文件处理**：附件过大时的流式处理
3. **磁盘空间**：长期保留策略，自动归档/压缩
4. **性能优化**：从轮询迁移到 inotify/kqueue
5. **备份恢复**：文件系统备份策略

---

*本文档随实现迭代更新*
