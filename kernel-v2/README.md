# ProClaw BlockComposer

高性能上下文合成服务，为 Agent Kernel 提供文本块组装能力。

## 架构

- **L1 Cache**: 内存 LRU 缓存 (1000 entries)
- **L2 Cache**: SQLite 持久化缓存
- **Providers**: Bash、Code、Memory、File 数据提供者
- **权限**: Capability Token + Policy Engine
- **可观测性**: Prometheus 指标、Trace、审计日志

## 快速开始

### 1. 安装依赖

```bash
# Ubuntu/Debian
sudo apt-get install -y ripgrep ast-grep tree-sitter-cli

# Arch
sudo pacman -S ripgrep ast-grep tree-sitter
```

### 2. 创建用户和目录

```bash
sudo useradd -r -s /bin/false proclaw
sudo mkdir -p /var/lib/proclaw /var/log/proclaw /run/proclaw /etc/proclaw
sudo chown -R proclaw:proclaw /var/lib/proclaw /var/log/proclaw /run/proclaw
```

### 3. 安装二进制

```bash
sudo cp target/release/proclaw-composer /usr/local/bin/
sudo cp target/release/proclaw-indexer /usr/local/bin/
```

### 4. 配置

```bash
sudo cp config/composer.yaml.example /etc/proclaw/composer.yaml
# 编辑配置文件
sudo nano /etc/proclaw/composer.yaml
```

### 5. 启动服务

```bash
# 使用 systemd
sudo cp config/proclaw-composer.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable proclaw-composer
sudo systemctl start proclaw-composer

# 或手动启动（开发模式）
RUST_LOG=debug ./target/debug/proclaw-composer --config ./config/composer.yaml
```

## 开发

### 构建

```bash
cd kernel-v2

# Debug build
cargo build

# Release build
cargo build --release

# Run tests
cargo test

# Run benchmarks
cargo bench
```

### 生成 gRPC 代码

```bash
# Install protoc and tonic
sudo apt-get install -y protobuf-compiler
cargo install tonic-build

# Generate code (automatic in build.rs)
cargo build
```

### 项目结构

```
kernel-v2/
├── Cargo.toml           # Rust project config
├── proto/               # Protocol Buffers
│   └── block_composer.proto
├── src/
│   ├── main.rs          # Entry point
│   ├── server.rs        # gRPC server
│   ├── config.rs        # Configuration
│   ├── block_composer/  # Core composition engine
│   ├── providers/       # Data providers
│   │   ├── bash.rs
│   │   ├── code.rs
│   │   ├── memory.rs
│   │   └── file.rs
│   ├── auth/            # Authentication & permissions
│   └── observability/   # Metrics & tracing
├── config/              # Configuration templates
└── tests/               # Integration tests
```

## API

### gRPC 服务

服务通过 Unix socket 暴露：`/run/proclaw/composer.sock`

主要方法：

- `Compose`: 组装 blocks 为最终上下文
- `QueryBlocks`: 查询 blocks（Session Host）
- `ExecuteBash`: 执行授权的 bash 命令（Thread）
- `QueryCode`: 代码查询（Thread）
- `GetMetrics`: 获取 Prometheus 指标

### 示例客户端

```python
import grpc
from proclaw.block_composer.v1 import block_composer_pb2, block_composer_pb2_grpc

channel = grpc.insecure_channel("unix:///run/proclaw/composer.sock")
stub = block_composer_pb2_grpc.BlockComposerStub(channel)

request = block_composer_pb2.ComposeRequest(
    session_id="sess_123",
    task_id="task_456",
    profile=block_composer_pb2.SESSION,
    block_types=[block_composer_pb2.SESSION_CONTEXT]
)

response = stub.Compose(request)
print(f"Composed: {response.composed_text}")
```

## 配置

### 环境变量

- `RUST_LOG`: 日志级别 (debug, info, warn, error)
- `COMPOSER_SOCKET_PATH`: Socket 路径
- `COMPOSER_DATA_DIR`: 数据目录
- `COMPOSER_SECRET_KEY`: Token 签名密钥

### 权限

BlockComposer 使用三层权限模型：

- **System**: 完全访问
- **Session**: 读文件、查询 memory、组装 blocks
- **Thread**: 受限 bash、代码查询（需授权 Token）

Token 通过 Capability Token（JWT-like）传递，包含 scope、过期时间、调用次数限制。

## 监控

### Prometheus 指标

访问 `http://localhost:9090/metrics`：

```
block_composer_cache_hits_total{profile="prime"} 15234
block_composer_latency_seconds_bucket{le="0.01"} 12000
```

### 日志

- 应用日志: `journalctl -u proclaw-composer`
- 审计日志: `/var/log/proclaw/audit.log`

### Trace

Trace 文件保存在 `/var/lib/proclaw/traces/`，格式为 JSON Lines。

## 性能

目标指标：

- Block composition latency: <10ms
- Cache hit rate: >90%
- Memory usage per session: <50MB

## 许可证

MIT OR Apache-2.0
