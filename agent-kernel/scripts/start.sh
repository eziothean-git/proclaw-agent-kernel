#!/bin/bash

# Agent Kernel 快速启动脚本

set -e

echo "🚀 Agent Kernel 启动脚本"
echo "=========================="

# 检查环境
if [ ! -f .env ]; then
    echo "⚠️  未找到 .env 文件，使用 .env.example 创建"
    cp .env.example .env
    echo "请编辑 .env 文件配置API密钥等参数"
fi

# 创建数据目录
mkdir -p data/{sessions,tasks,snapshots,queue,scheduler}

echo ""
echo "启动选项:"
echo "1. 启动完整系统（Gateway + Python Kernel）"
echo "2. 仅启动 Python Kernel"
echo "3. 仅启动 Gateway"
echo "4. 运行存储工具演示"
echo "5. 退出"
echo ""
read -p "请选择 [1-5]: " choice

case $choice in
    1)
        echo "🚀 启动完整系统..."
        
        # 安装依赖
        echo "📦 安装依赖..."
        cd apps/python-kernel
        pip install -q -r requirements.txt
        cd ../..
        
        cd apps/gateway
        npm install
        cd ../..
        
        # 启动Python Kernel（后台）
        echo "🐍 启动 Python Kernel..."
        cd apps/python-kernel
        python main.py &
        PYTHON_PID=$!
        cd ../..
        
        # 等待Python Kernel启动
        sleep 2
        
        # 启动Gateway
        echo "🌐 启动 Gateway..."
        cd apps/gateway
        npm run start:dev &
        GATEWAY_PID=$!
        cd ../..
        
        echo ""
        echo "✅ 系统已启动!"
        echo "   Gateway: http://localhost:3000"
        echo "   Python Kernel: http://localhost:8000"
        echo ""
        echo "按 Ctrl+C 停止服务"
        
        # 等待中断
        wait
        ;;
        
    2)
        echo "🐍 启动 Python Kernel..."
        cd apps/python-kernel
        pip install -q -r requirements.txt
        python main.py
        ;;
        
    3)
        echo "🌐 启动 Gateway..."
        cd apps/gateway
        npm install
        npm run start:dev
        ;;
        
    4)
        echo "🎮 运行存储工具演示..."
        cd apps/python-kernel
        pip install -q -r requirements.txt
        python examples/storage_demo.py
        ;;
        
    5)
        echo "👋 再见!"
        exit 0
        ;;
        
    *)
        echo "❌ 无效选择"
        exit 1
        ;;
esac
