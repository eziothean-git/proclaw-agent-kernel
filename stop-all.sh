#!/bin/bash
# 完全清理所有服务进程

echo "🧹 清理所有服务进程..."

# 停止 Gateway (端口3000)
echo "  - 停止 Gateway (端口3000)..."
pkill -f "node.*gateway.*dist/main" 2>/dev/null || true
pkill -f "npm.*start:prod" 2>/dev/null || true

# 停止 Request Manager (端口50052)
echo "  - 停止 Request Manager (端口50052)..."
pkill -f "request-manager" 2>/dev/null || true
pkill -9 -f "node dist/main.js" 2>/dev/null || true

# 停止 Python Kernel (端口8000)
echo "  - 停止 Python Kernel (端口8000)..."
pkill -f "python main.py" 2>/dev/null || true

# 等待进程完全停止
sleep 2

# 强制释放端口
echo "  - 强制释放端口..."
for port in 3000 50052 8000; do
    pid=$(lsof -Pi :$port -sTCP:LISTEN -t 2>/dev/null)
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
