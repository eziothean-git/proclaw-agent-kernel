#!/bin/bash
# ProClaw 优雅关闭脚本
# 使用HTTP shutdown端点确保服务完全关闭

set -e

echo "🛑 优雅关闭所有服务..."

# 停止顺序：Gateway -> Request Manager -> Python Kernel
# 给每个服务10秒完成当前请求

TIMEOUT=10

# 1. 停止 Gateway (端口3000)
echo "  - 通知 Gateway 关闭 (${TIMEOUT}s 超时)..."
if curl -s -X POST http://localhost:3000/v1/shutdown 2>/dev/null; then
    echo "    ✓ Gateway 已接受关闭请求"
else
    echo "    ⚠️ Gateway 未响应，强制关闭"
fi
sleep 1

# 2. 停止 Request Manager (端口50052)
echo "  - 通知 Request Manager 关闭 (${TIMEOUT}s 超时)..."
# Request Manager 通过 gRPC shutdown 方法
# 暂时使用 kill，后续可以添加 HTTP 端点
pkill -f "request-manager" 2>/dev/null || true
sleep 1

# 3. 停止 Python Kernel (端口8000)
echo "  - 通知 Python Kernel 关闭 (${TIMEOUT}s 超时)..."
if curl -s -X POST http://localhost:8000/v1/shutdown 2>/dev/null; then
    echo "    ✓ Python Kernel 已接受关闭请求"
else
    echo "    ⚠️ Python Kernel 未响应，强制关闭"
fi

# 等待服务自行关闭
echo ""
echo "⏳ 等待 ${TIMEOUT} 秒让服务完成当前请求..."
sleep ${TIMEOUT}

# 强制释放端口（确保完全关闭）
echo "  - 强制释放端口..."
for port in 3000 50052 8000; do
    pid=$(lsof -Pi :$port -sTCP:LISTEN -t 2>/dev/null || true)
    if [ -n "$pid" ]; then
        echo "    强制停止端口 $port (PID: $pid)"
        kill -9 $pid 2>/dev/null || true
    fi
done

sleep 1

echo "✅ 所有服务已停止"

# 显示剩余进程
echo ""
echo "📊 剩余进程检查:"
remaining=$(ps aux | grep -E "(node.*dist/main|python main.py)" | grep -v grep | wc -l)
if [ "$remaining" -eq 0 ]; then
    echo "   ✓ 没有残留进程"
else
    echo "   ⚠️ 发现 $remaining 个残留进程:"
    ps aux | grep -E "(node.*dist/main|python main.py)" | grep -v grep
fi