# Request Manager（请求管理器）

基于文件系统的信箱机制，与 Gateway 完全解耦的请求处理器。

## 架构位置

```
┌──────────┐     ┌──────────┐     ┌─────────────────┐
│  Gateway │────→│   Inbox  │────→│ Request Manager │
│ (生产者) │     │ (信箱)   │     │ (消费者)        │
└──────────┘     └──────────┘     └─────────────────┘
                                        │
                                        ↓
                                   ┌──────────┐
                                   │  Outbox  │────→ Gateway 推送
                                   │ (信箱)   │
                                   └──────────┘
```

## 文件系统结构

```
/var/gateway/
├── inbox/          # Gateway 写入，Request Manager 读取
├── outbox/         # Request Manager 写入，Gateway 读取
├── pending/        # 标记正在处理的请求
└── ...
```

## 快速开始

### 1. 启动 Gateway

```bash
cd apps/gateway
npm install
npm run start:dev
```

### 2. 启动 Request Manager（另一个终端）

```bash
cd apps/request-manager
python3 request_manager.py
```

### 3. 发送测试请求

```bash
# 使用 curl
curl -X POST http://localhost:3000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Hello, how are you?",
    "user_id": "user1",
    "platform": "http"
  }'

# 或使用 CLI
echo '{"message": "Hello", "user_id": "user1"}' | npm run cli
```

### 4. 查询响应

```bash
# 使用返回的 request_id
curl http://localhost:3000/api/v1/requests/{request_id}
```

## 工作原理

### Gateway 端（TypeScript）

1. 接收外部请求
2. 转换为 Input IR
3. 写入 `/var/gateway/inbox/{date}/{request_id}.json`
4. 更新 `inbox/index.jsonl`
5. 立即返回 `request_id`
6. 轮询 `outbox/` 目录等待响应

### Request Manager 端（Python）

1. 轮询扫描 `inbox/` 目录
2. 按优先级排序（高优先级优先）
3. 串行处理请求
4. 调用 Prime Personality（实际系统）
5. 将响应写入 `/var/gateway/outbox/{date}/{request_id}.json`
6. 更新 `outbox/index.jsonl`

## 自定义 Request Manager

你可以用任何语言实现请求管理器，只需要：

1. **读取 inbox**：扫描 `/var/gateway/inbox/` 中的 `.json` 文件
2. **处理请求**：调用你的 AI/Agent 系统
3. **写入 outbox**：将响应写入 `/var/gateway/outbox/`

### 最小实现示例

```python
import json
from pathlib import Path

INBOX = Path("/var/gateway/inbox")
OUTBOX = Path("/var/gateway/outbox")

# 读取请求
for request_file in INBOX.glob("*/*.json"):
    with open(request_file) as f:
        request = json.load(f)
    
    request_id = request["header"]["request_id"]
    
    # 处理请求（你的逻辑）
    response = process_with_your_ai(request)
    
    # 写入响应
    response_file = OUTBOX / f"{request_id}.json"
    with open(response_file, 'w') as f:
        json.dump(response, f)
```

## 优先级系统

支持 5 级优先级：

- `P0` (100): 系统级紧急请求
- `P1` (50): 定时请求（主人格留言）
- `P2` (10): 高优先级用户请求
- `P3` (0): 普通用户请求（默认）
- `P4` (-10): 后台任务

请求在 Input IR 的 `header.priority` 字段指定。

## 与真实系统集成

当前 `request_manager.py` 是模拟实现。在实际系统中，你需要替换 `process_request` 方法：

```python
async def process_request(self, request: Dict, file_path: Path) -> Dict:
    # 1. 调用 Prime Personality
    intent = await self.prime_personality.process(request)
    
    # 2. 路由到 Session Host
    session = await self.get_or_create_session(intent.session_id)
    result = await session.handle(intent)
    
    # 3. 返回响应
    return {
        "header": {...},
        "status": "completed",
        "body": result.content,
    }
```

## 环境变量

- `GATEWAY_STORAGE_PATH`: 文件系统根目录（默认: `/var/gateway`）
- `REQUEST_MANAGER_POLL_INTERVAL`: 轮询间隔秒数（默认: 0.5）
- `DEBUG`: 启用调试日志

## 开发指南

### 添加新的处理逻辑

编辑 `request_manager.py` 中的 `process_request` 方法：

```python
async def process_request(self, request: Dict, file_path: Path) -> Dict:
    # 你的自定义逻辑
    if request["header"]["platform"] == "cli":
        # CLI 特定处理
        pass
    
    # 调用外部服务
    result = await call_external_api(request)
    
    return {
        "header": {...},
        "status": "completed",
        "body": result,
    }
```

### 错误处理

Request Manager 会自动捕获异常并写入错误响应：

```json
{
  "status": "failed",
  "error": {
    "category": "system_error",
    "message": "错误详情",
    "recoverable": false
  }
}
```

## 故障排查

### Gateway 收不到响应

1. 检查 Request Manager 是否运行：`ps aux | grep request_manager`
2. 检查 outbox 目录权限：`ls -la /var/gateway/outbox/`
3. 检查日志：Request Manager 会输出处理日志

### 请求积压

如果 inbox 中文件堆积：

1. 增加 Request Manager 实例（多进程）
2. 优化处理速度
3. 增加优先级区分

### 文件系统权限

确保 Gateway 和 Request Manager 都有读写权限：

```bash
sudo chown -R $USER:$USER /var/gateway
chmod -R 755 /var/gateway
```

## 下一步

1. 实现真正的 Prime Personality 调用
2. 添加 Session Host 集成
3. 实现定时请求调度器
4. 添加监控和指标收集
