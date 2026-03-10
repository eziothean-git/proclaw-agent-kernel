#!/bin/bash
# ProClaw 统一启动脚本 - 干净版本
set -e

# 颜色
GREEN='\033[0;32m'
RED='\033[0;31m'
NC='\033[0m'

# 项目根目录
ROOT="/home/eziothean/ProClaw/agent-kernel"
DATA_ROOT="$ROOT/data"

# 环境变量 - 统一配置
export GATEWAY_STORAGE_PATH="$DATA_ROOT/gateway"
export GATEWAY_INBOX_PATH="$DATA_ROOT/gateway/inbox"
export GATEWAY_URL="http://localhost:3000"
export PYTHON_KERNEL_URL="http://localhost:8000"
export DATA_PATH="$DATA_ROOT"
export ARK_API_KEY="ca199063-af7d-4d99-9613-40bdc4c82831"
export ARK_MODEL="doubao-seed-1-6-250615"
export LLM_PROVIDER="ark"
export LLM_TEMPERATURE="0.7"
export LLM_MAX_TOKENS="4000"

echo "🧹 清理所有现有服务..."
killall -9 node python 2>/dev/null || true
sleep 2

echo ""
echo "🚀 按顺序启动服务..."
echo ""

# 1. Request Manager
echo "1️⃣  启动 Request Manager (gRPC:50052)..."
cd "$ROOT/apps/request-manager"
nohup node dist/main.js > /tmp/request-manager.log 2>&1 &
sleep 3
if ! lsof -Pi :50052 -sTCP:LISTEN >/dev/null 2>&1; then
    echo -e "${RED}❌ Request Manager 启动失败${NC}"
    tail -10 /tmp/request-manager.log
    exit 1
fi
echo -e "${GREEN}✅ Request Manager 已启动${NC}"

# 2. Python Kernel
echo ""
echo "2️⃣  启动 Python Kernel (HTTP:8000)..."
cd "$ROOT/apps/python-kernel"
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
PYTHONPATH="$ROOT/apps/python-kernel" nohup python main.py > /tmp/proclaw-kernel.log 2>&1 &
sleep 5
if ! curl -s http://localhost:8000/health >/dev/null 2>&1; then
    echo -e "${RED}❌ Python Kernel 启动失败${NC}"
    tail -10 /tmp/proclaw-kernel.log
    exit 1
fi
echo -e "${GREEN}✅ Python Kernel 已启动${NC}"

# 3. Gateway
echo ""
echo "3️⃣  启动 Gateway (HTTP:3000)..."
cd "$ROOT/apps/gateway"
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
echo "测试命令:"
echo "  python3 /home/eziothean/ProClaw/proclaw-cli.py \"你好\""
echo ""
echo "查看日志:"
echo "  tail -f /tmp/proclaw-kernel.log"
