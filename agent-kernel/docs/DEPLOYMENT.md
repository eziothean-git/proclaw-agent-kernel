# Agent Kernel Docker Deployment Guide

本文档介绍如何使用 Docker 部署 Agent Kernel 服务。

## 📋 目录

- [系统要求](#系统要求)
- [快速开始](#快速开始)
- [详细部署](#详细部署)
- [管理命令](#管理命令)
- [数据管理](#数据管理)
- [故障排除](#故障排除)
- [高级配置](#高级配置)

---

## 🖥️ 系统要求

### 最低配置
- **操作系统**: Linux (推荐 Ubuntu 20.04+ / Debian 11+ / CentOS 8+)
- **CPU**: 2 核心
- **内存**: 2 GB RAM
- **存储**: 10 GB 可用空间
- **网络**: 能够访问 LLM API (Ark/OpenAI)

### 软件依赖
- Docker 20.10+
- Docker Compose 2.0+ (可选，用于编排)

### 端口
- `3000`: Gateway HTTP API (外部访问)
- `8000`: Python Kernel HTTP API (调试/内部访问)

---

## 🚀 快速开始

### 1. 克隆代码

```bash
git clone https://github.com/yourusername/agent-kernel.git
cd agent-kernel
```

### 2. 配置 LLM

运行交互式配置脚本：

```bash
./scripts/setup.sh
```

按照提示选择 LLM 提供商并输入 API 密钥：
- **Volcengine Ark** (推荐，国内可用)
- **OpenAI** (GPT-4/GPT-3.5)
- **Custom** (OpenAI-compatible API)

配置将保存在 `~/.agent-kernel/config/.env`

### 3. 构建镜像

```bash
./scripts/build.sh
```

可选参数：
```bash
./scripts/build.sh --tag v1.0.0     # 指定版本标签
./scripts/build.sh --no-cache       # 不使用缓存构建
```

### 4. 启动服务

```bash
./scripts/start.sh
```

服务将在后台启动，访问：
- Gateway API: http://localhost:3000
- Health Check: http://localhost:3000/health

---

## 📖 详细部署

### 环境变量配置

所有配置都存储在 `~/.agent-kernel/config/.env`，格式如下：

```bash
# LLM Provider
LLM_PROVIDER=ark

# Volcengine Ark Settings
ARK_API_KEY=your-api-key-here
ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
ARK_MODEL=glm-4-7-251222

# LLM Settings
LLM_TEMPERATURE=0.7
LLM_MAX_TOKENS=4000

# Run Mode
KERNEL_RUN_MODE=real
```

### 手动配置

如果不想使用交互式脚本，可以手动创建配置文件：

```bash
mkdir -p ~/.agent-kernel/config
cat > ~/.agent-kernel/config/.env <<'EOF'
LLM_PROVIDER=ark
ARK_API_KEY=your-api-key
ARK_MODEL=glm-4-7-251222
LLM_TEMPERATURE=0.7
LLM_MAX_TOKENS=4000
EOF
```

### 使用 Docker Compose

如果使用 Docker Compose：

```bash
cd docker
docker-compose up -d
```

这将：
- 构建镜像（如果不存在）
- 创建命名卷 `agent-kernel-data`
- 启动容器并映射端口
- 应用 `.env` 文件中的配置

---

## 🔧 管理命令

### 容器管理

```bash
# 启动服务
./scripts/start.sh start

# 停止服务
./scripts/start.sh stop

# 重启服务
./scripts/start.sh restart

# 查看状态
./scripts/start.sh status

# 查看日志
./scripts/start.sh logs

# 进入容器shell
./scripts/start.sh shell

# 删除容器（保留数据）
./scripts/start.sh remove
```

### Docker 命令

```bash
# 查看运行中的容器
docker ps

# 查看容器日志
docker logs -f agent-kernel

# 查看所有容器（包括停止的）
docker ps -a

# 停止容器
docker stop agent-kernel

# 删除容器
docker rm agent-kernel

# 查看镜像
docker images agent-kernel
```

### 进程管理

容器内使用 supervisord 管理进程：

```bash
# 进入容器
docker exec -it agent-kernel /bin/sh

# 查看进程状态
supervisorctl status

# 重启 Gateway
supervisorctl restart gateway

# 重启 Python Kernel
supervisorctl restart python-kernel

# 查看进程日志
tail -f /var/log/supervisor/gateway.log
tail -f /var/log/supervisor/python-kernel.log
```

---

## 💾 数据管理

### 数据存储位置

容器使用 Docker 命名卷持久化数据：

```
agent-kernel-data
├── data/
│   ├── gateway/          # Gateway mailbox
│   ├── python-kernel/    # Sessions, tasks, memory
│   │   ├── sessions/
│   │   ├── tasks/
│   │   ├── events/
│   │   └── long_term_memory/
│   └── runtime.db        # SQLite database (if using sqlite storage)
└── logs/                 # Application logs
```

### 备份数据

```bash
# 创建备份
./scripts/start.sh backup

# 备份将保存到 ~/.agent-kernel/backups/
# 文件名格式: agent-kernel-data-YYYYMMDD_HHMMSS.tar.gz
```

### 恢复数据

```bash
# 从备份恢复
./scripts/start.sh restore

# 选择要恢复的备份文件
```

### 手动备份

```bash
# 导出数据卷
docker run --rm \
  -v agent-kernel-data:/data \
  -v $(pwd):/backup \
  alpine tar czf /backup/backup.tar.gz -C /data .

# 导入数据卷
docker run --rm \
  -v agent-kernel-data:/data \
  -v $(pwd):/backup \
  alpine tar xzf /backup/backup.tar.gz -C /data
```

---

## 🔍 故障排除

### 检查服务状态

```bash
# 容器状态
docker ps | grep agent-kernel

# 健康检查
curl http://localhost:3000/health

# 容器日志
docker logs agent-kernel --tail 100
```

### 常见问题

#### 1. 容器无法启动

```bash
# 检查日志
docker logs agent-kernel

# 常见原因：
# - 端口被占用: lsof -i :3000
# - 配置错误: 检查 ~/.agent-kernel/config/.env
# - 镜像损坏: 重新构建 ./scripts/build.sh --no-cache
```

#### 2. API 返回错误

```bash
# 检查 LLM 配置
cat ~/.agent-kernel/config/.env | grep -E "(API_KEY|PROVIDER)"

# 测试 LLM 连接
docker exec agent-kernel python -c "
import httpx
response = httpx.get('https://ark.cn-beijing.volces.com/api/v3/models', 
                     headers={'Authorization': 'Bearer YOUR_KEY'})
print(response.status_code)
"
```

#### 3. 内存/CPU 过高

```bash
# 查看资源使用
docker stats agent-kernel

# 调整资源限制
docker update --memory=4g --cpus=2 agent-kernel
```

#### 4. 权限问题

```bash
# 检查卷权限
docker volume inspect agent-kernel-data

# 修复权限（如果需要）
docker run --rm -v agent-kernel-data:/data alpine chown -R 1000:1000 /data
```

### 调试模式

启动时启用调试日志：

```bash
# 临时修改环境变量
docker run -d \
  --name agent-kernel-debug \
  -p 3000:3000 \
  -e LOG_LEVEL=DEBUG \
  --env-file ~/.agent-kernel/config/.env \
  agent-kernel:latest
```

---

## ⚙️ 高级配置

### 自定义端口

编辑 `~/.agent-kernel/config/.env`：

```bash
GATEWAY_PORT=8080
PYTHON_KERNEL_PORT=8081
```

启动时映射不同端口：

```bash
docker run -d \
  --name agent-kernel \
  -p 8080:3000 \
  -p 8081:8000 \
  --env-file ~/.agent-kernel/config/.env \
  agent-kernel:latest
```

### 资源限制

```bash
docker run -d \
  --name agent-kernel \
  --memory=4g \
  --cpus=2 \
  --memory-swap=4g \
  --oom-kill-disable \
  agent-kernel:latest
```

### 使用自定义网络

```bash
# 创建网络
docker network create agent-kernel-network

# 启动容器
docker run -d \
  --name agent-kernel \
  --network agent-kernel-network \
  agent-kernel:latest
```

### 集成 Nginx 反向代理

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://localhost:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_cache_bypass $http_upgrade;
    }
}
```

### 自动重启配置

使用 systemd 管理容器：

```ini
# /etc/systemd/system/agent-kernel.service
[Unit]
Description=Agent Kernel
Requires=docker.service
After=docker.service

[Service]
Restart=always
ExecStart=/usr/bin/docker start -a agent-kernel
ExecStop=/usr/bin/docker stop -t 30 agent-kernel

[Install]
WantedBy=multi-user.target
```

启用服务：

```bash
sudo systemctl daemon-reload
sudo systemctl enable agent-kernel
sudo systemctl start agent-kernel
```

---

## 📦 发布到 GitHub

### 准备工作

1. 确保代码已推送到 GitHub
2. 登录 GitHub Container Registry：

```bash
# 创建 GitHub Personal Access Token (需要有 write:packages 权限)
# 然后登录：
echo "YOUR_GITHUB_TOKEN" | docker login ghcr.io -u USERNAME --password-stdin
```

### 发布流程

```bash
# 运行发布脚本
./release/publish.sh v1.0.0
```

该脚本将：
1. 构建 Docker 镜像
2. 推送到 GitHub Container Registry
3. 创建 Git 标签
4. 创建 GitHub Release

### 拉取已发布镜像

```bash
# 登录 GitHub Container Registry
docker login ghcr.io -u USERNAME

# 拉取镜像
docker pull ghcr.io/username/agent-kernel:v1.0.0

# 运行
docker run -d \
  --name agent-kernel \
  -p 3000:3000 \
  --env-file ~/.agent-kernel/config/.env \
  ghcr.io/username/agent-kernel:v1.0.0
```

---

## 📝 更新日志

### 版本升级

```bash
# 1. 停止当前容器
./scripts/start.sh stop

# 2. 拉取/构建新镜像
./scripts/build.sh --tag v1.1.0

# 3. 删除旧容器（数据会保留）
docker rm agent-kernel

# 4. 启动新容器
./scripts/start.sh start
```

### 数据迁移

如果需要在不同主机间迁移：

```bash
# 源主机：导出数据
docker run --rm \
  -v agent-kernel-data:/data \
  -v $(pwd):/backup \
  alpine tar czf /backup/agent-kernel-backup.tar.gz -C /data .

# 传输备份文件到目标主机
scp agent-kernel-backup.tar.gz user@new-host:/tmp/

# 目标主机：导入数据
docker run --rm \
  -v agent-kernel-data:/data \
  -v /tmp:/backup \
  alpine tar xzf /backup/agent-kernel-backup.tar.gz -C /data

# 启动容器
./scripts/start.sh
```

---

## 🤝 贡献

如有问题或改进建议，请提交 Issue 或 PR。

---

## 📄 License

MIT License
