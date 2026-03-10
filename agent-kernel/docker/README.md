# Agent Kernel Docker Deployment

Agent Kernel 的 Docker 打包和部署方案。

## 📦 打包组件

```
agent-kernel/
├── docker/
│   ├── Dockerfile              # 多阶段构建文件
│   ├── docker-compose.yml      # Docker Compose 编排
│   ├── supervisord.conf        # 进程管理配置
│   └── .dockerignore           # 构建忽略文件
├── scripts/
│   ├── setup.sh                # LLM API 配置引导脚本
│   ├── build.sh                # 本地构建脚本
│   └── start.sh                # 容器管理脚本
├── release/
│   └── publish.sh              # GitHub 发布脚本
└── docs/
    └── DEPLOYMENT.md           # 完整部署文档
```

## 🚀 快速开始

### 1. 配置 LLM API

```bash
./scripts/setup.sh
```

交互式配置支持：
- Volcengine Ark (推荐，国内可用)
- OpenAI (GPT-4/GPT-3.5)
- Custom API (OpenAI-compatible)

### 2. 构建镜像

```bash
./scripts/build.sh
```

### 3. 启动服务

```bash
./scripts/start.sh
```

服务将在后台启动：
- Gateway: http://localhost:3000
- Python Kernel: http://localhost:8000

## 📋 命令速查

```bash
# 容器管理
./scripts/start.sh start        # 启动服务
./scripts/start.sh stop         # 停止服务
./scripts/start.sh restart      # 重启服务
./scripts/start.sh status       # 查看状态
./scripts/start.sh logs         # 查看日志
./scripts/start.sh shell        # 进入容器

# 数据管理
./scripts/start.sh backup       # 备份数据
./scripts/start.sh restore      # 恢复数据

# 构建
./scripts/build.sh --tag v1.0.0 # 指定版本构建
./scripts/build.sh --no-cache   # 不使用缓存

# 发布
./release/publish.sh v1.0.0     # 发布到 GitHub
```

## 🔧 技术架构

### 容器设计

- **单容器模式**: Gateway + Python Kernel 合并在一个容器内
- **进程管理**: 使用 supervisord 管理两个服务
- **数据持久化**: Docker 命名卷，数据完全隔离
- **时区同步**: 自动挂载宿主机时区

### 镜像特点

- **多阶段构建**: 构建和运行分离，减小镜像体积
- **非 root 运行**: 使用 UID 1000 运行，增强安全性
- **健康检查**: 自动检测服务状态
- **日志轮转**: 自动清理日志文件

### 端口映射

| 端口 | 服务 | 说明 |
|------|------|------|
| 3000 | Gateway | 主 API 入口 |
| 8000 | Python Kernel | 调试/内部 API |

## 📁 数据存储

数据保存在 Docker 命名卷中：

```
agent-kernel-data/
├── gateway/              # Gateway mailbox
│   ├── inbox/
│   ├── outbox/
│   └── pending/
└── python-kernel/        # 内核数据
    ├── sessions/
    ├── tasks/
    ├── events/
    └── long_term_memory/
```

配置文件保存在宿主机：
```
~/.agent-kernel/
├── config/
│   └── .env              # LLM 配置
└── backups/              # 数据备份
```

## 🌐 发布到 GitHub

### 准备工作

1. 登录 GitHub Container Registry：
```bash
docker login ghcr.io -u USERNAME
# 使用 GitHub Personal Access Token 作为密码
```

2. 确保代码已推送到 GitHub

### 发布流程

```bash
./release/publish.sh v1.0.0
```

自动完成：
- 构建 Docker 镜像
- 推送到 ghcr.io
- 创建 Git 标签
- 创建 GitHub Release

### 使用已发布镜像

```bash
# 拉取镜像
docker pull ghcr.io/username/agent-kernel:v1.0.0

# 运行
docker run -d \
  --name agent-kernel \
  -p 3000:3000 \
  -p 8000:8000 \
  --env-file ~/.agent-kernel/config/.env \
  ghcr.io/username/agent-kernel:v1.0.0
```

## 🐛 故障排除

### 查看日志

```bash
# 容器日志
docker logs agent-kernel

# 服务日志
docker exec agent-kernel tail -f /var/log/supervisor/gateway.log
docker exec agent-kernel tail -f /var/log/supervisor/python-kernel.log
```

### 检查状态

```bash
# 容器状态
./scripts/start.sh status

# 健康检查
curl http://localhost:3000/health

# 进程状态
docker exec agent-kernel supervisorctl status
```

### 常见问题

**端口被占用**:
```bash
lsof -i :3000
# 或使用不同端口启动
```

**权限问题**:
```bash
# 检查卷权限
docker volume inspect agent-kernel-data
```

**服务未启动**:
```bash
# 检查配置
cat ~/.agent-kernel/config/.env

# 检查资源
docker stats agent-kernel
```

## 📚 详细文档

完整部署指南请查看：
- [DEPLOYMENT.md](docs/DEPLOYMENT.md) - 详细部署文档
- [INTEGRATION_TEST.md](docs/INTEGRATION_TEST.md) - 集成测试指南

## 🔒 安全说明

1. **API 密钥**: 保存在 `~/.agent-kernel/config/.env`，权限设置为 600
2. **容器运行**: 使用非 root 用户 (UID 1000)
3. **数据隔离**: 使用 Docker 命名卷，与宿主机隔离
4. **网络**: 默认只暴露必要端口

## 📝 License

MIT License
