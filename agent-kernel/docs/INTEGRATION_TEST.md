# Gateway + Python Kernel 集成测试文档

本文档描述如何运行 Gateway 和 Python Kernel 的集成测试，验证全量历史记录功能和调度器集成。

## 测试目标

1. **全量历史记录功能** - 验证请求、响应、任务、事件、快照等数据的完整持久化
2. **调度器集成** - 验证请求从 Gateway → Python Kernel → Scheduler → Prime Personality 的完整流程

> **重要提示**: 本集成测试中的 Prime Personality、Context Compilers、Session Host、Agent Thread 等模块仅为了验证 **请求收发流程** 而实现的简单占位符。这些实现没有完全遵循架构设计文档中的意图，仅用于测试 Gateway 和 Python Kernel 之间的基本数据流转。完整的模块实现需要按照架构规范重新设计和开发。

## 数据流

```
用户请求
    ↓
Gateway (HTTP API)
    ↓
inbox/ 目录 (文件系统 Mailbox)
    ↓
Python Kernel (轮询/监听)
    ↓
Prime Personality (意图理解)
    ↓
Session Host (会话管理)
    ↓
Scheduler (任务调度)
    ↓
Agent Thread (执行)
    ↓
Callback → Gateway Webhook
    ↓
outbox/ 目录
    ↓
用户响应
```

## 历史记录存储

所有历史数据存储在 SQLite 数据库中 (`data/runtime.db`)：

| 表名 | 用途 |
|------|------|
| `sessions` | 会话历史 |
| `requests` | 请求历史 |
| `tasks` | 任务历史（调度器创建） |
| `events` | 事件日志（完整操作记录） |
| `snapshots` | 执行快照（中间状态） |
| `queue` | 请求队列 |
| `scheduler` | 定时任务 |

## 快速开始

### 方法一：使用 npm 命令

```bash
# 进入项目目录
cd agent-kernel

# 运行完整集成测试
npm run test:integration

# 验证历史记录（测试后运行）
npm run test:history
```

### 方法二：直接运行脚本

```bash
# 进入项目目录
cd agent-kernel

# 运行集成测试
./scripts/test-gateway-kernel-integration.sh

# 验证历史记录
python3 scripts/verify-history.py
```

### 方法三：手动测试

如果你已经启动了 Gateway 和 Python Kernel，可以手动测试：

```bash
# 1. 启动 Gateway
cd apps/gateway
npm run start:dev

# 2. 在另一个终端启动 Python Kernel
cd apps/python-kernel
python3 main.py

# 3. 发送测试请求
curl -X POST http://localhost:3000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "帮我列出当前目录的文件",
    "user_id": "test-user",
    "platform": "cli"
  }'

# 4. 验证历史记录
python3 scripts/verify-history.py --data-path ./apps/python-kernel/data
```

## 测试步骤详解

集成测试脚本 (`test-gateway-kernel-integration.sh`) 执行以下步骤：

### 1. 环境检查
- 检查 Node.js、Python3、curl 是否安装
- 检查 Gateway 是否已构建
- 检查 Python 依赖是否安装

### 2. 构建和启动
```bash
# 构建 Gateway
cd apps/gateway && npm run build

# 启动 Gateway
export GATEWAY_STORAGE_PATH=./data/gateway
export PYTHON_KERNEL_URL=http://localhost:8000
node dist/main

# 启动 Python Kernel
export KERNEL_RUN_MODE=mock  # 使用 mock 模式，不调用真实 LLM
export DATA_PATH=./data/apps/python-kernel
python3 main.py
```

### 3. 发送测试请求
```bash
curl -X POST http://localhost:3000/api/v1/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "帮我列出当前目录的文件",
    "user_id": "integration-test-user",
    "platform": "test",
    "priority": 5
  }'
```

### 4. 验证流程
- ✅ 请求写入 `inbox/` 目录
- ✅ Python Kernel 读取并处理
- ✅ 调度器创建并执行任务
- ✅ Prime Personality 生成 IR
- ✅ Agent Thread 执行
- ✅ 回调 Gateway Webhook
- ✅ 响应写入 `outbox/` 目录
- ✅ 所有历史记录写入 SQLite

### 5. 验证历史记录
```bash
python3 scripts/verify-history.py
```

输出示例：
```
验证 sessions 表
  ✓ 共有 1 个会话记录

验证 requests 表
  ✓ 共有 1 个请求记录
  请求状态分布:
    - completed: 1 个

验证 tasks 表
  ✓ 共有 1 个任务记录
  任务状态分布:
    - completed: 1 个

验证 events 表
  ✓ 共有 5 个事件记录
  事件阶段分布:
    - request_queued: 1 个
    - task_started: 1 个
    - task_completed: 1 个

验证 snapshots 表
  ✓ 共有 1 个快照记录
```

## 环境变量

### Gateway
- `GATEWAY_STORAGE_PATH` - 文件系统存储路径 (默认: /var/gateway)
- `PORT` - Gateway 端口 (默认: 3000)
- `PYTHON_KERNEL_URL` - Python Kernel URL (默认: http://localhost:8000)
- `NODE_ENV` - 环境 (development/production/test)

### Python Kernel
- `PORT` - Kernel 端口 (默认: 8000)
- `HOST` - 监听地址 (默认: 0.0.0.0)
- `KERNEL_RUN_MODE` - 运行模式 (real/mock)
  - `real`: 调用真实 LLM API
  - `mock`: 返回模拟响应（用于测试）
- `DATA_PATH` - 数据目录 (默认: ./data)
- `STORAGE_TYPE` - 存储类型 (file/sqlite, 默认: file)

## 运行模式

### Mock 模式 (推荐用于集成测试)
```bash
export KERNEL_RUN_MODE=mock
```
- 不调用真实 LLM API
- 快速响应
- 适合 CI/CD 和自动化测试

### Real 模式
```bash
export KERNEL_RUN_MODE=real
export OPENAI_API_KEY=your-api-key
```
- 调用真实 LLM API
- 需要配置 API Key
- 响应较慢

## 常见问题

### 1. Gateway 启动失败
```bash
# 检查端口占用
lsof -i :3000
# 或
netstat -tlnp | grep 3000

# 清理后重试
rm -rf ./data/gateway
npm run test:integration
```

### 2. Python Kernel 启动失败
```bash
# 检查 Python 依赖
pip3 install -e ./apps/python-kernel

# 检查端口占用
lsof -i :8000

# 清理数据目录
rm -rf ./data/apps/python-kernel
```

### 3. 请求处理超时
- 检查 Python Kernel 是否正常运行
- 查看 Kernel 日志
- 确保 `KERNEL_RUN_MODE=mock` 用于测试

### 4. 历史记录为空
```bash
# 检查数据目录
ls -la ./data/apps/python-kernel/

# 手动验证
python3 scripts/verify-history.py --data-path ./data/apps/python-kernel
```

## API 参考

### Gateway API

#### 发送请求
```http
POST /api/v1/chat
Content-Type: application/json

{
  "message": "用户消息",
  "user_id": "user-id",
  "platform": "cli",
  "sessionId": "optional-session-id",
  "priority": 5
}
```

响应：
```json
{
  "requestId": "uuid",
  "sessionId": "uuid",
  "status": "accepted",
  "timestamp": "2026-03-10T...",
  "message": "Request accepted and queued for processing"
}
```

#### 查询请求状态
```http
GET /api/v1/requests/{requestId}
```

#### 健康检查
```http
GET /api/v1/health
```

### Python Kernel API

#### 执行请求
```http
POST /v1/execute
Content-Type: application/json

{
  "request_id": "uuid",
  "session_id": "uuid",
  "user_id": "user-id",
  "message": "用户消息",
  "metadata": {},
  "callback_url": "http://gateway:3000/gateway/webhook/kernel-response"
}
```

#### 查询会话状态
```http
GET /v1/sessions/{sessionId}/status
```

#### 健康检查
```http
GET /health
```

## 文件系统结构

### Gateway 存储 (`data/gateway/`)
```
gateway/
├── inbox/              # 输入请求队列
│   ├── 2026-03-10/
│   │   └── {request-id}.json
│   └── index.jsonl
├── outbox/             # 输出响应队列
│   ├── 2026-03-10/
│   │   └── {request-id}.json
│   └── index.jsonl
├── pending/            # 处理中请求
├── attachments/        # 附件存储
├── sessions/           # 会话元数据
├── errors/             # 错误日志
└── logs/               # 操作日志
```

### Python Kernel 存储 (`data/apps/python-kernel/`)
```
python-kernel/
├── runtime.db          # SQLite 数据库（所有历史记录）
├── sessions/           # 会话文件 (如果使用文件存储)
├── requests/           # 请求文件
├── tasks/              # 任务文件
├── snapshots/          # 快照文件
├── events/             # 事件文件
└── queue/              # 队列文件
```

## 调试技巧

### 查看实时日志
```bash
# Gateway 日志
tail -f ./data/gateway/logs/gateway.log

# Python Kernel 日志
# 在启动 Kernel 的终端查看
```

### 检查文件系统
```bash
# 查看 inbox
ls -la ./data/gateway/inbox/

# 查看请求内容
cat ./data/gateway/inbox/2026-03-10/*.json | jq .

# 查看 SQLite 数据库
sqlite3 ./data/apps/python-kernel/runtime.db
sqlite> .tables
sqlite> SELECT * FROM requests;
```

### 手动触发请求处理
```bash
# 直接写入 inbox 文件
mkdir -p ./data/gateway/inbox/2026-03-10
cat > ./data/gateway/inbox/2026-03-10/manual-test.json << 'EOF'
{
  "header": {
    "timestamp": "2026-03-10T12:00:00Z",
    "platform": "test",
    "deviceId": "test-device",
    "userId": "test-user",
    "sessionId": "test-session",
    "requestId": "manual-test-001"
  },
  "body": "这是一个手动测试请求"
}
EOF
```

## 持续集成

### GitHub Actions 示例
```yaml
name: Integration Tests

on: [push, pull_request]

jobs:
  integration-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Setup Node.js
        uses: actions/setup-node@v3
        with:
          node-version: '18'
      
      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.11'
      
      - name: Install dependencies
        run: |
          cd agent-kernel
          npm install
          pip3 install -e ./apps/python-kernel
      
      - name: Run integration tests
        run: |
          cd agent-kernel
          npm run test:integration
      
      - name: Verify history
        run: |
          cd agent-kernel
          npm run test:history
```

## 扩展测试

### 并发测试
```bash
# 发送多个并发请求
for i in {1..5}; do
  curl -X POST http://localhost:3000/api/v1/chat \
    -H "Content-Type: application/json" \
    -d "{\"message\": \"请求 $i\", \"user_id\": \"user-$i\"}" &
done
wait
```

### 长时间运行测试
```bash
# 测试调度器定时任务
curl -X POST http://localhost:3000/api/v1/schedule \
  -H "Content-Type: application/json" \
  -d '{
    "message": "定时任务测试",
    "user_id": "test-user",
    "cron": "*/1 * * * *"
  }'
```

## 相关文档

- [Gateway 架构文档](../apps/gateway/ARCHITECTURE.md)
- [Request Manager README](../apps/request-manager/README.md)
- [项目 AGENTS.md](../AGENTS.md)

## 支持和反馈

如遇到问题，请：
1. 查看日志文件
2. 运行 `verify-history.py` 检查数据完整性
3. 提交 Issue 到项目仓库
