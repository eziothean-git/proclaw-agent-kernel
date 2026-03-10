# ProClaw TUI - 设置指南

Terminal UI client for Agent Kernel Gateway. ProClaw是一个终端界面客户端，通过本地WebSocket/SSE连接Gateway，访问Agentic OS。

## 📋 目录

- [系统要求](#系统要求)
- [快速开始](#快速开始)
- [Docker部署](#docker部署)
- [手动安装](#手动安装)
- [配置说明](#配置说明)
- [使用指南](#使用指南)
- [故障排除](#故障排除)
- [开发指南](#开发指南)

## 🔧 系统要求

- **操作系统**: Linux, macOS, Windows (WSL2)
- **Docker**: 20.10+ (推荐用于部署)
- **Docker Compose**: 2.0+ (推荐用于部署)
- **Python**: 3.9+ (仅手动安装时需要)
- **Node.js**: 18+ (仅手动安装时需要)
- **内存**: 最少 512MB RAM，推荐 2GB+
- **磁盘**: 最少 1GB 可用空间

## 🚀 快速开始

### 方式一：Docker部署（推荐）

```bash
# 1. 克隆仓库
cd /home/eziothean/ProClaw/agent-kernel

# 2. 配置环境变量（编辑 .env 文件）
cat > .env << 'EOF'
# LLM配置（火山引擎 - GLM4.7）
LLM_PROVIDER=ark
ARK_API_KEY=62663763-1f8a-4c10-862e-b5d760b19fba
ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
ARK_MODEL=glm-4-7-251222

# 运行模式
KERNEL_RUN_MODE=real

# 存储配置
STORAGE_TYPE=file
DATA_PATH=./data
EOF

# 3. 启动服务
cd docker
docker-compose up -d

# 4. 查看日志
docker-compose logs -f

# 5. 安装并启动 TUI 客户端
cd ../apps/gateway/clients/tui
pip install -e .
proclaw
```

### 方式二：手动安装

```bash
# 1. 设置环境变量
export LLM_PROVIDER=ark
export ARK_API_KEY=62663763-1f8a-4c10-862e-b5d760b19fba
export ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
export ARK_MODEL=glm-4-7-251222
export KERNEL_RUN_MODE=real

# 2. 启动 Gateway
cd agent-kernel/apps/gateway
npm install
npm run dev

# 3. 启动 Python Kernel（新终端）
cd agent-kernel/apps/python-kernel
pip install -e "."
python main.py

# 4. 启动 TUI（新终端）
cd agent-kernel/apps/gateway/clients/tui
pip install -e .
proclaw
```

## 🐳 Docker部署

### 完整部署步骤

```bash
# 进入项目目录
cd /home/eziothean/ProClaw/agent-kernel

# 创建环境配置文件
cp .env.example .env

# 编辑 .env 文件，配置API密钥
vim .env
# 添加：
# LLM_PROVIDER=ark
# ARK_API_KEY=62663763-1f8a-4c10-862e-b5d760b19fba
# ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
# ARK_MODEL=glm-4-7-251222
# KERNEL_RUN_MODE=real

# 构建并启动
cd docker
docker-compose up --build -d

# 检查状态
docker-compose ps
docker-compose logs -f agent-kernel

# 测试 API
curl http://localhost:3000/api/v1/health
```

### Docker服务管理

```bash
# 停止服务
docker-compose down

# 停止并删除数据卷
docker-compose down -v

# 查看日志
docker-compose logs -f

# 重启服务
docker-compose restart

# 更新镜像后重建
docker-compose up -d --build
```

### 数据持久化

Docker部署会自动创建两个卷：
- `agent-kernel-data`: 存储运行数据（会话、请求历史等）
- `agent-kernel-logs`: 存储日志文件

```bash
# 查看卷信息
docker volume ls | grep agent-kernel

# 备份数据
docker run --rm -v agent-kernel-data:/data -v $(pwd):/backup alpine tar czf /backup/backup.tar.gz -C /data .

# 恢复数据
docker run --rm -v agent-kernel-data:/data -v $(pwd):/backup alpine tar xzf /backup/backup.tar.gz -C /data
```

## 📦 手动安装

### 安装 Gateway

```bash
cd agent-kernel/apps/gateway

# 安装依赖
npm install

# 构建项目
npm run build

# 运行开发模式
npm run dev

# 或生产模式
npm run build
npm run start:prod
```

### 安装 Python Kernel

```bash
cd agent-kernel/apps/python-kernel

# 创建虚拟环境（可选）
python -m venv venv
source venv/bin/activate  # Linux/macOS
# 或: venv\Scripts\activate  # Windows

# 安装依赖
pip install -e "."

# 运行
python main.py
```

### 安装 TUI 客户端

```bash
cd agent-kernel/apps/gateway/clients/tui

# 安装
pip install -e .

# 或使用 Makefile
cd agent-kernel/apps/gateway
make tui-install

# 运行
proclaw
# 或
make tui
```

## ⚙️ 配置说明

### 环境变量

创建 `.env` 文件在项目根目录：

```bash
# === LLM 配置 ===
# 火山引擎 (默认)
LLM_PROVIDER=ark
ARK_API_KEY=62663763-1f8a-4c10-862e-b5d760b19fba
ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
ARK_MODEL=glm-4-7-251222

# OpenAI (可选)
# LLM_PROVIDER=openai
# OPENAI_API_KEY=your-key-here
# OPENAI_BASE_URL=https://api.openai.com/v1
# OPENAI_MODEL=gpt-4

# === 运行模式 ===
# production: 生产模式（调用真实LLM API）
# 注意：系统已移除mock模式，所有调用均为真实API
KERNEL_RUN_MODE=production

# === 存储配置 ===
STORAGE_TYPE=file              # file 或 sqlite
DATA_PATH=./data               # 数据存储路径
GATEWAY_STORAGE_PATH=./data/gateway

# === 服务端口 ===
GATEWAY_PORT=3000
PYTHON_KERNEL_PORT=8000
GATEWAY_URL=http://localhost:3000
PYTHON_KERNEL_URL=http://localhost:8000

# === 高级配置 ===
LOG_LEVEL=INFO                 # DEBUG, INFO, WARN, ERROR
INBOX_POLL_INTERVAL=1.0        # 收件箱轮询间隔（秒）
SCHEDULER_CHECK_INTERVAL=60    # 调度器检查间隔（秒）

# LLM 参数
LLM_TEMPERATURE=0.7
LLM_MAX_TOKENS=4000
```

### TUI 客户端配置

```bash
# 命令行参数
proclaw --help

# 常用参数
proclaw \
  --url http://localhost:3000 \     # Gateway URL
  --user proclaw-user \             # 用户ID
  --debug                            # 调试模式
```

## 💬 使用指南

### 启动 TUI

```bash
# 默认连接 localhost:3000
proclaw

# 连接远程 Gateway
proclaw --url http://remote-gateway:3000

# 调试模式（显示详细日志）
proclaw --debug
```

### 界面说明

```
┌──────────────────────────────────────────────────────────────────┐
│  🧠 ProClaw Terminal v0.1.0                    [● Connected]   │
├──────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─ Conversation ──────────────────────────────────────────────┐│
│  │                                                             ││
│  │  👤 14:32:10  你好，请介绍一下自己                          ││
│  │                                                             ││
│  │  🤖 14:32:12  [completed]                                  ││
│  │      你好！我是 Agent Kernel 的 AI 助手...                  ││
│  │                                                             ││
│  └─────────────────────────────────────────────────────────────┘│
│                                                                  │
│  ┌─ System Status ────────────────────────────────────────────┐ │
│  │  Gateway: ✅ healthy (v0.2.0)                               │ │
│  │  Connection: ● connected                                    │ │
│  │  Queue: 0 pending, 0 processing, 5 completed                │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  > 输入消息... [_cursor_]                                        │
│                                                                  │
│  ● connected  |  GW: v0.2.0  |  /help                           │
└──────────────────────────────────────────────────────────────────┘
```

### 命令列表

在输入框中输入以 `/` 开头的命令：

| 命令 | 说明 |
|------|------|
| `/help` | 显示帮助信息 |
| `/clear` | 清空对话历史 |
| `/status` | 刷新系统状态 |
| `/quit` | 退出程序 |

### 快捷键

| 快捷键 | 功能 |
|--------|------|
| `Enter` | 发送消息 |
| `Ctrl+C` | 退出程序 |
| `Ctrl+R` | 刷新系统状态 |
| `Ctrl+S` | 切换侧边栏 |
| `F1` | 显示帮助 |
| `↑/↓` | 浏览历史输入 |

## 🔧 故障排除

### 问题：无法连接到 Gateway

```bash
# 检查 Gateway 是否运行
curl http://localhost:3000/api/v1/health

# 检查端口占用
lsof -i :3000  # macOS/Linux
netstat -ano | findstr :3000  # Windows

# 查看 Gateway 日志
cd agent-kernel/apps/gateway
npm run dev
```

### 问题：TUI 启动失败

```bash
# 检查 Python 版本
python --version  # 需要 3.9+

# 重新安装依赖
cd agent-kernel/apps/gateway/clients/tui
pip install --force-reinstall -e .

# 调试模式运行
proclaw --debug
```

### 问题：LLM API 调用失败

```bash
# 检查环境变量
echo $ARK_API_KEY
echo $LLM_PROVIDER

# 测试 API 连接
curl https://ark.cn-beijing.volces.com/api/v3/models \
  -H "Authorization: Bearer 62663763-1f8a-4c10-862e-b5d760b19fba"

# 查看 Python Kernel 日志
cd agent-kernel/apps/python-kernel
python main.py  # 在前台运行查看日志
```

### 问题：Docker 部署失败

```bash
# 检查 Docker 状态
docker ps
docker-compose ps

# 重建镜像
docker-compose down
docker-compose up -d --build

# 查看详细日志
docker-compose logs -f --tail=100
```

### 问题：网络连接断开

TUI 会自动重连，如果长时间无法恢复：

1. 检查网络连接
2. 按 `Ctrl+R` 手动刷新状态
3. 如果 Gateway 已重启，退出并重新启动 TUI

## 🛠️ 开发指南

### 项目结构

```
agent-kernel/
├── apps/
│   ├── gateway/              # NestJS Gateway
│   │   ├── clients/
│   │   │   └── tui/         # Python TUI 客户端
│   │   ├── src/
│   │   └── package.json
│   ├── python-kernel/       # Python FastAPI Kernel
│   │   ├── main.py
│   │   └── pyproject.toml
│   └── request-manager/     # gRPC 请求管理器
├── docker/
│   ├── docker-compose.yml
│   └── Dockerfile
└── .env                     # 环境变量配置
```

### 本地开发

```bash
# 1. 启动 Gateway (Terminal 1)
cd agent-kernel/apps/gateway
npm run dev

# 2. 启动 Python Kernel (Terminal 2)
cd agent-kernel/apps/python-kernel
export ARK_API_KEY=62663763-1f8a-4c10-862e-b5d760b19fba
export KERNEL_RUN_MODE=real
python main.py

# 3. 启动 TUI (Terminal 3)
cd agent-kernel/apps/gateway/clients/tui
proclaw --debug
```

### 代码格式化

```bash
# Python 代码
cd agent-kernel/apps/gateway/clients/tui
black .
ruff check . --fix

# TypeScript 代码
cd agent-kernel/apps/gateway
npm run lint
npm run typecheck
```

## 📚 更多信息

- [Agent Kernel 架构文档](../docs/ARCHITECTURE.md)
- [集成测试指南](../INTEGRATION_TEST_PLAN.md)
- [API 文档](http://localhost:3000/api/docs) (启动 Gateway 后访问)

## 📝 许可证

MIT

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！
