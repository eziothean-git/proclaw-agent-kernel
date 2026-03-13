#!/bin/bash
# ProClaw 统一启动脚本 - Rust Kernel v2 版本
set -e

# 颜色
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

# 项目根目录
ROOT="/home/eziothean/ProClaw"
AGENT_KERNEL_ROOT="$ROOT/agent-kernel"
KERNEL_V2_ROOT="$ROOT/kernel-v2"
DATA_ROOT="$AGENT_KERNEL_ROOT/data"

# 环境变量 - 统一配置
export GATEWAY_STORAGE_PATH="$DATA_ROOT/gateway"
export GATEWAY_INBOX_PATH="$DATA_ROOT/gateway/inbox"
export GATEWAY_URL="http://localhost:3000"
export DATA_PATH="$DATA_ROOT"

# LLM 配置
export ARK_API_KEY="${ARK_API_KEY:-ca199063-af7d-4d99-9613-40bdc4c82831}"
export ARK_MODEL="${ARK_MODEL:-doubao-seed-1-6-250615}"
export OPENAI_API_KEY="${OPENAI_API_KEY:-}"
export LLM_PROVIDER="${LLM_PROVIDER:-ark}"
export LLM_TEMPERATURE="${LLM_TEMPERATURE:-0.7}"
export LLM_MAX_TOKENS="${LLM_MAX_TOKENS:-4000}"

# Rust Kernel 配置
export RUST_LOG="${RUST_LOG:-info}"
export RUST_BACKTRACE="${RUST_BACKTRACE:-1}"

# 创建数据目录
mkdir -p "$DATA_ROOT"
mkdir -p /tmp/proclaw-test

echo "🧹 清理所有现有服务..."
killall -9 node proclaw-composer 2>/dev/null || true
pkill -f "python main.py" 2>/dev/null || true
sleep 2

echo ""
echo "🚀 按顺序启动服务..."
echo ""

# 1. Rust Kernel v2 (Prime Personality + AgentKernel + BlockComposer)
echo "1️⃣  启动 Rust Kernel v2 (gRPC:50051, Unix Socket)..."

# 创建测试配置
cat > /tmp/proclaw-test/composer.yaml << 'EOF'
server:
  socket_path: "/tmp/proclaw-test/composer.sock"
  workers: 2
  max_concurrent_requests: 10
  request_timeout_seconds: 60

cache:
  l1:
    max_entries: 100
    default_ttl_seconds:
      prime: 300
      session: 120
      task: 30
  l2:
    path: "/tmp/proclaw-test/cache.db"
    max_size_mb: 50
    compression: "zstd"

providers:
  bash:
    timeout_seconds: 30
    max_output_size: 10000
    blocked_commands:
      - "rm -rf /"
      - "mkfs"
    patterns_file: "/tmp/proclaw-test/bash_patterns.yaml"
  
  code:
    index:
      database_path: "/tmp/proclaw-test/code_index.db"
      update_interval_seconds: 300
      paths: []
  
  memory:
    database_path: "/tmp/proclaw-test/memory.db"
    max_facts_per_query: 50
    default_categories:
      - "general"

permissions:
  default_token_ttl_seconds: 3600
  default_max_calls: 100
  policy_file: "/tmp/proclaw-test/policies.yaml"

observability:
  metrics:
    enabled: true
    port: 9090
    path: "/metrics"
  traces:
    base_path: "/tmp/proclaw-test/traces"
    retention_days: 7
    compress_after_hours: 24
    compression_algorithm: "zstd"
    compression_level: 3
  audit:
    path: "/tmp/proclaw-test/audit.log"
    level: "info"
  logging:
    level: "info"
    format: "text"
    output: "stdout"
EOF

# 检查 Rust Kernel 二进制是否存在
RUST_BINARY="$KERNEL_V2_ROOT/target/release/proclaw-composer"
if [ ! -f "$RUST_BINARY" ]; then
    echo -e "${YELLOW}⚠️  Rust Kernel 二进制不存在，尝试编译...${NC}"
    cd "$KERNEL_V2_ROOT"
    cargo build --release --features control-plane 2>&1 | tail -20
    if [ ! -f "$RUST_BINARY" ]; then
        echo -e "${RED}❌ Rust Kernel 编译失败${NC}"
        exit 1
    fi
fi

# 启动 Rust Kernel
cd "$KERNEL_V2_ROOT"
nohup "$RUST_BINARY" \
    --config /tmp/proclaw-test/composer.yaml \
    --llm-api-key "$ARK_API_KEY" \
    --llm-model "$ARK_MODEL" \
    > /tmp/proclaw-rust-kernel.log 2>&1 &

sleep 5

# 检查 Prime Personality (端口 50051)
if ! lsof -Pi :50051 -sTCP:LISTEN >/dev/null 2>&1; then
    echo -e "${RED}❌ Rust Kernel (Prime Personality) 启动失败${NC}"
    tail -20 /tmp/proclaw-rust-kernel.log
    exit 1
fi

# 检查 Unix socket
if [ ! -S "/tmp/proclaw-test/composer.sock" ]; then
    echo -e "${YELLOW}⚠️  Unix socket 未创建，可能仍在初始化中...${NC}"
fi

echo -e "${GREEN}✅ Rust Kernel v2 已启动${NC}"
echo "   - Prime Personality: localhost:50051"
echo "   - BlockComposer Socket: /tmp/proclaw-test/composer.sock"
echo "   - Metrics: http://localhost:9090/metrics"

# 2. Request Manager
echo ""
echo "2️⃣  启动 Request Manager (gRPC:50052)..."
cd "$AGENT_KERNEL_ROOT/apps/request-manager"
nohup node dist/main.js > /tmp/request-manager.log 2>&1 &
sleep 3
if ! lsof -Pi :50052 -sTCP:LISTEN >/dev/null 2>&1; then
    echo -e "${RED}❌ Request Manager 启动失败${NC}"
    tail -10 /tmp/request-manager.log
    exit 1
fi
echo -e "${GREEN}✅ Request Manager 已启动${NC}"

# 3. Gateway
echo ""
echo "3️⃣  启动 Gateway (HTTP:3000)..."
cd "$AGENT_KERNEL_ROOT/apps/gateway"
nohup npm run start:prod > /tmp/proclaw-gateway.log 2>&1 &
sleep 5
if ! curl -s http://localhost:3000/api/v1/health >/dev/null 2>&1; then
    echo -e "${RED}❌ Gateway 启动失败${NC}"
    tail -10 /tmp/proclaw-gateway.log
    exit 1
fi
echo -e "${GREEN}✅ Gateway 已启动${NC}"

echo ""
echo "========================================"
echo "✅ 所有服务已启动!"
echo "========================================"
echo ""
echo "服务列表:"
echo "  1. Rust Kernel v2    : localhost:50051 (gRPC)"
echo "  2. Request Manager   : localhost:50052 (gRPC)"
echo "  3. Gateway          : localhost:3000  (HTTP)"
echo ""
echo "测试命令:"
echo "  python3 /home/eziothean/ProClaw/proclaw-cli.py \"你好\""
echo ""
echo "查看日志:"
echo "  Rust Kernel: tail -f /tmp/proclaw-rust-kernel.log"
echo "  Req Manager: tail -f /tmp/request-manager.log"
echo "  Gateway:     tail -f /tmp/proclaw-gateway.log"
