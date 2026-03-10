#!/bin/bash
# 完整服务启动脚本

set -e

echo "========================================"
echo "🚀 ProClaw 完整服务启动"
echo "========================================"

# 环境变量
export ARK_API_KEY="${ARK_API_KEY:-62663763-1f8a-4c10-862e-b5d760b19fba}"
export LLM_PROVIDER="ark"
export ARK_MODEL="glm-4-7-251222"
export DATA_PATH="/home/eziothean/ProClaw/agent-kernel/data"
export GATEWAY_STORAGE_PATH="/home/eziothean/ProClaw/agent-kernel/data/gateway"
export GATEWAY_URL="http://localhost:3000"
export PYTHON_KERNEL_URL="http://localhost:8000"

# 项目路径
PROJECT_ROOT="/home/eziothean/ProClaw/agent-kernel"

echo ""
echo "1️⃣  停止现有服务..."
pkill -f "node dist/main" 2>/dev/null || true
pkill -f "request-manager" 2>/dev/null || true
pkill -f "python main.py" 2>/dev/null || true
sleep 3
echo "   ✅ 已清理"

# 等待端口释放
sleep 2

echo ""
echo "2️⃣  启动 Request Manager (gRPC:50052)..."
cd "${PROJECT_ROOT}/apps/request-manager"
nohup npm start > /tmp/request-manager.log 2>&1 &
sleep 4
if lsof -Pi :50052 -sTCP:LISTEN >/dev/null 2>&1; then
    echo "   ✅ Request Manager 已启动"
else
    echo "   ❌ Request Manager 启动失败"
    tail -20 /tmp/request-manager.log
    exit 1
fi

echo ""
echo "3️⃣  启动 Python Kernel (HTTP:8000)..."
cd "${PROJECT_ROOT}/apps/python-kernel"
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
PYTHONPATH="${PROJECT_ROOT}/apps/python-kernel" nohup python main.py > /tmp/proclaw-kernel.log 2>&1 &
sleep 6
if curl -s http://localhost:8000/health >/dev/null 2>&1; then
    echo "   ✅ Python Kernel 已启动"
else
    echo "   ❌ Python Kernel 启动失败"
    tail -20 /tmp/proclaw-kernel.log
    exit 1
fi

echo ""
echo "4️⃣  启动 Gateway (HTTP:3000)..."
cd "${PROJECT_ROOT}/apps/gateway"
nohup npm run start:prod > /tmp/proclaw-gateway.log 2>&1 &
sleep 6
if curl -s http://localhost:3000/api/v1/health >/dev/null 2>&1; then
    echo "   ✅ Gateway 已启动"
else
    echo "   ❌ Gateway 启动失败"
    tail -20 /tmp/proclaw-gateway.log
    exit 1
fi

echo ""
echo "========================================"
echo "✅ 所有服务已启动！"
echo "========================================"
echo ""
echo "服务地址:"
echo "  Gateway:       http://localhost:3000"
echo "  Request Manager: gRPC://localhost:50052"
echo "  Python Kernel: http://localhost:8000"
echo ""
echo "现在可以使用:"
echo "  proclaw"
echo ""
echo "或手动测试:"
echo "  curl -X POST http://localhost:3000/api/v1/chat \\"
echo "    -H \"Content-Type: application/json\" \\"
echo "    -d '{\"message\": \"你好\", \"user_id\": \"test\"}'"
echo ""
