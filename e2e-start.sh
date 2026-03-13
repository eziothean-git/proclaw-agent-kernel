#!/bin/bash
# ProClaw E2E 测试快速启动脚本
# 一键启动完整系统进行端到端测试

set -e

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo -e "${BLUE}"
echo "╔════════════════════════════════════════════════════════════╗"
echo "║     ProClaw E2E 测试环境 - Rust Kernel v2                 ║"
echo "╚════════════════════════════════════════════════════════════╝"
echo -e "${NC}"

# 检查环境
echo "📋 环境检查..."

# 检查 Rust 二进制
RUST_BINARY="/home/eziothean/ProClaw/kernel-v2/target/release/proclaw-composer"
if [ ! -f "$RUST_BINARY" ]; then
    echo -e "${RED}❌ Rust Kernel 未编译${NC}"
    echo "请先运行: cd /home/eziothean/ProClaw/kernel-v2 && cargo build --release --features control-plane"
    exit 1
fi
echo -e "${GREEN}✓${NC} Rust Kernel 已编译"

# 检查 Node.js
if ! command -v node &> /dev/null; then
    echo -e "${RED}❌ Node.js 未安装${NC}"
    exit 1
fi
echo -e "${GREEN}✓${NC} Node.js 版本: $(node --version)"

# 检查端口占用
echo ""
echo "🔍 检查端口占用..."
for port in 3000 50051 50052 9090; do
    if lsof -Pi :$port -sTCP:LISTEN >/dev/null 2>&1; then
        echo -e "${YELLOW}⚠️ 端口 $port 已被占用${NC}"
        read -p "是否强制关闭占用进程? [y/N]: " confirm
        if [[ "$confirm" =~ ^[Yy]$ ]]; then
            pid=$(lsof -Pi :$port -sTCP:LISTEN -t 2>/dev/null || true)
            [ -n "$pid" ] && kill -9 $pid 2>/dev/null || true
        fi
    fi
done

# 启动服务
echo ""
echo "🚀 启动服务..."
bash /home/eziothean/ProClaw/launcher.sh

echo ""
echo "========================================"
echo -e "${GREEN}E2E 测试环境准备完成!${NC}"
echo "========================================"
echo ""
echo "测试端点:"
echo "  1. Gateway API:      http://localhost:3000/api/v1/chat"
echo "  2. Gateway Health:   http://localhost:3000/api/v1/health"
echo "  3. Prime gRPC:       localhost:50051"
echo "  4. Req Manager gRPC: localhost:50052"
echo "  5. Metrics:          http://localhost:9090/metrics"
echo ""
echo "快速测试:"
echo "  curl -X POST http://localhost:3000/api/v1/chat \\"
echo "    -H 'Content-Type: application/json' \\"
echo "    -d '{\"message\": \"你好\"}'"
echo ""
echo "查看日志:"
echo "  tail -f /tmp/proclaw-rust-kernel.log"
echo ""
echo "关闭服务:"
echo "  bash /home/eziothean/ProClaw/stop-all.sh"
