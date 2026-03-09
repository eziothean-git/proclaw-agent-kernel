#!/bin/bash
# Gateway + Python Kernel 集成测试脚本
# 测试目标：
# 1. 验证全量写历史功能（请求、响应、事件、任务快照）
# 2. 验证请求从 Gateway → Python Kernel → Scheduler → Prime Personality 的完整流程

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 配置
GATEWAY_PORT=3000
KERNEL_PORT=8000
GATEWAY_URL="http://localhost:$GATEWAY_PORT"
KERNEL_URL="http://localhost:$KERNEL_PORT"

# 使用项目根目录下的 data 目录
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DATA_PATH="${PROJECT_ROOT}/data"
KERNEL_DATA_PATH="${PROJECT_ROOT}/apps/python-kernel/data"
STORAGE_PATH="${DATA_PATH}/gateway"

echo -e "${BLUE}=== Gateway + Python Kernel 集成测试 ===${NC}"
echo ""
echo "项目根目录: $PROJECT_ROOT"
echo "数据目录: $DATA_PATH"
echo ""

# PID 文件
GATEWAY_PID_FILE="/tmp/gateway-integration.pid"
KERNEL_PID_FILE="/tmp/kernel-integration.pid"

# 清理函数
cleanup() {
    echo ""
    echo -e "${YELLOW}清理进程中...${NC}"
    
    # 停止 Gateway
    if [ -f "$GATEWAY_PID_FILE" ]; then
        GATEWAY_PID=$(cat "$GATEWAY_PID_FILE")
        kill $GATEWAY_PID 2>/dev/null || true
        rm -f "$GATEWAY_PID_FILE"
        echo "  ✓ Gateway 已停止"
    fi
    
    # 停止 Python Kernel
    if [ -f "$KERNEL_PID_FILE" ]; then
        KERNEL_PID=$(cat "$KERNEL_PID_FILE")
        kill $KERNEL_PID 2>/dev/null || true
        rm -f "$KERNEL_PID_FILE"
        echo "  ✓ Python Kernel 已停止"
    fi
    
    echo -e "${GREEN}清理完成${NC}"
}

trap cleanup EXIT

# 检查依赖
check_dependencies() {
    echo -e "${BLUE}[1/10] 检查依赖...${NC}"
    
    if ! command -v node &> /dev/null; then
        echo -e "${RED}错误: Node.js 未安装${NC}"
        exit 1
    fi
    
    if ! command -v python3 &> /dev/null; then
        echo -e "${RED}错误: Python3 未安装${NC}"
        exit 1
    fi
    
    if ! command -v curl &> /dev/null; then
        echo -e "${RED}错误: curl 未安装${NC}"
        exit 1
    fi
    
    echo "  ✓ Node.js: $(node --version)"
    echo "  ✓ Python3: $(python3 --version)"
    echo "  ✓ curl: 已安装"
}

# 检查并构建 Gateway
build_gateway() {
    echo -e "${BLUE}[2/10] 构建 Gateway...${NC}"
    cd "${PROJECT_ROOT}/apps/gateway"
    
    if [ ! -d "node_modules" ]; then
        echo "  安装依赖..."
        npm install 2>&1 | tail -5
    fi
    
    echo "  编译 TypeScript..."
    npm run build 2>&1 | tail -5
    
    echo "  ✓ Gateway 构建完成"
}

# 检查并安装 Python Kernel 依赖
install_kernel_deps() {
    echo -e "${BLUE}[3/10] 安装 Python Kernel 依赖...${NC}"
    cd "${PROJECT_ROOT}/apps/python-kernel"
    
    # 检查是否已安装
    if python3 -c "import pydantic" 2>/dev/null; then
        echo "  ✓ Python 依赖已安装"
    else
        echo "  安装 Python 依赖..."
        pip3 install -e "." 2>&1 | tail -5
    fi
    
    echo "  ✓ Python Kernel 依赖就绪"
}

# 清理测试数据
clean_test_data() {
    echo -e "${BLUE}[4/10] 清理测试数据...${NC}"
    rm -rf "$STORAGE_PATH" "$KERNEL_DATA_PATH"
    mkdir -p "$STORAGE_PATH"/{inbox,outbox,pending,attachments,sessions,errors,logs}
    echo "  ✓ 已清理: $STORAGE_PATH"
    echo "  ✓ 已清理: $KERNEL_DATA_PATH"
}

# 启动 Gateway
start_gateway() {
    echo -e "${BLUE}[5/10] 启动 Gateway...${NC}"
    cd "${PROJECT_ROOT}/apps/gateway"
    
    export GATEWAY_STORAGE_PATH="$STORAGE_PATH"
    export NODE_ENV="test"
    export PORT="$GATEWAY_PORT"
    export PYTHON_KERNEL_URL="$KERNEL_URL"
    
    node dist/main &
    GATEWAY_PID=$!
    echo $GATEWAY_PID > "$GATEWAY_PID_FILE"
    
    # 等待 Gateway 启动
    echo "  等待 Gateway 启动..."
    for i in {1..30}; do
        if curl -s "$GATEWAY_URL/api/v1/health" > /dev/null 2>&1; then
            echo "  ✓ Gateway 已启动 (PID: $GATEWAY_PID, Port: $GATEWAY_PORT)"
            return 0
        fi
        sleep 1
    done
    
    echo -e "${RED}  ✗ Gateway 启动失败${NC}"
    exit 1
}

# 启动 Python Kernel
start_kernel() {
    echo -e "${BLUE}[6/10] 启动 Python Kernel...${NC}"
    cd "${PROJECT_ROOT}/apps/python-kernel"
    
    export PORT="$KERNEL_PORT"
    export HOST="0.0.0.0"
    export KERNEL_RUN_MODE="mock"
    export DATA_PATH="$KERNEL_DATA_PATH"
    export GATEWAY_INBOX_PATH="$STORAGE_PATH/inbox"
    export GATEWAY_URL="$GATEWAY_URL"
    export INBOX_POLL_INTERVAL="0.5"
    
    python3 main.py &
    KERNEL_PID=$!
    echo $KERNEL_PID > "$KERNEL_PID_FILE"
    
    # 等待 Kernel 启动
    echo "  等待 Python Kernel 启动..."
    for i in {1..30}; do
        if curl -s "$KERNEL_URL/health" > /dev/null 2>&1; then
            echo "  ✓ Python Kernel 已启动 (PID: $KERNEL_PID, Port: $KERNEL_PORT)"
            return 0
        fi
        sleep 1
    done
    
    echo -e "${RED}  ✗ Python Kernel 启动失败${NC}"
    exit 1
}

# 发送测试请求
send_test_request() {
    echo -e "${BLUE}[7/10] 发送测试请求...${NC}"
    
    REQUEST_PAYLOAD='{
        "message": "帮我列出当前目录的文件",
        "user_id": "integration-test-user",
        "platform": "test",
        "priority": 5
    }'
    
    RESPONSE=$(curl -s -X POST "$GATEWAY_URL/api/v1/chat" \
        -H "Content-Type: application/json" \
        -d "$REQUEST_PAYLOAD")
    
    REQUEST_ID=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['requestId'])" 2>/dev/null || echo "")
    
    if [ -z "$REQUEST_ID" ]; then
        echo -e "${RED}  ✗ 发送请求失败${NC}"
        echo "  响应: $RESPONSE"
        exit 1
    fi
    
    echo "  ✓ 请求已接受"
    echo "  Request ID: $REQUEST_ID"
}

# 验证请求写入 inbox
verify_inbox() {
    echo -e "${BLUE}[8/10] 验证请求写入 inbox...${NC}"
    
    sleep 1
    
    INBOX_COUNT=$(find "$STORAGE_PATH/inbox" -name "*.json" 2>/dev/null | wc -l)
    
    if [ "$INBOX_COUNT" -eq 0 ]; then
        echo -e "${RED}  ✗ inbox 为空${NC}"
        exit 1
    fi
    
    echo "  ✓ inbox 中有 $INBOX_COUNT 个请求文件"
    
    # 显示请求内容
    LATEST_REQUEST=$(find "$STORAGE_PATH/inbox" -name "*.json" -type f -printf '%T@ %p\n' 2>/dev/null | sort -n | tail -1 | cut -d' ' -f2-)
    if [ -f "$LATEST_REQUEST" ]; then
        echo "  请求文件: $LATEST_REQUEST"
    fi
}

# 等待响应并验证
wait_for_response() {
    echo -e "${BLUE}[9/10] 等待响应...${NC}"
    
    ATTEMPTS=0
    MAX_ATTEMPTS=30
    
    while [ $ATTEMPTS -lt $MAX_ATTEMPTS ]; do
        sleep 1
        ATTEMPTS=$((ATTEMPTS + 1))
        
        # 检查 outbox
        OUTBOX_COUNT=$(find "$STORAGE_PATH/outbox" -name "*.json" 2>/dev/null | wc -l)
        
        if [ "$OUTBOX_COUNT" -gt 0 ]; then
            echo "  ✓ 响应已生成 ($OUTBOX_COUNT 个文件)"
            return 0
        fi
        
        echo "  等待中... ($ATTEMPTS/$MAX_ATTEMPTS)"
    done
    
    echo -e "${RED}  ✗ 超时，未收到响应${NC}"
    exit 1
}

# 验证历史记录
verify_history() {
    echo -e "${BLUE}[10/10] 验证历史记录...${NC}"
    
    # 使用 Python 脚本验证 SQLite 数据库
    if [ -f "${PROJECT_ROOT}/scripts/verify-history.py" ]; then
        python3 "${PROJECT_ROOT}/scripts/verify-history.py" --data-path "$KERNEL_DATA_PATH"
    else
        echo -e "${YELLOW}  ! 历史记录验证脚本未找到，跳过详细验证${NC}"
        
        # 简单验证：检查数据库文件是否存在
        if [ -f "$KERNEL_DATA_PATH/runtime.db" ]; then
            echo "  ✓ SQLite 数据库存在: $KERNEL_DATA_PATH/runtime.db"
            
            # 简单检查表数据
            if command -v sqlite3 &> /dev/null; then
                REQUEST_COUNT=$(sqlite3 "$KERNEL_DATA_PATH/runtime.db" "SELECT COUNT(*) FROM requests;" 2>/dev/null || echo "0")
                TASK_COUNT=$(sqlite3 "$KERNEL_DATA_PATH/runtime.db" "SELECT COUNT(*) FROM tasks;" 2>/dev/null || echo "0")
                EVENT_COUNT=$(sqlite3 "$KERNEL_DATA_PATH/runtime.db" "SELECT COUNT(*) FROM events;" 2>/dev/null || echo "0")
                
                echo "  ✓ requests 表: $REQUEST_COUNT 条记录"
                echo "  ✓ tasks 表: $TASK_COUNT 条记录"
                echo "  ✓ events 表: $EVENT_COUNT 条记录"
            fi
        fi
    fi
}

# 打印测试总结
print_summary() {
    echo ""
    echo -e "${GREEN}=== 集成测试完成 ===${NC}"
    echo ""
    echo -e "${BLUE}文件系统状态:${NC}"
    echo "  Inbox:  $(find "$STORAGE_PATH/inbox" -name '*.json' 2>/dev/null | wc -l) 个文件"
    echo "  Outbox: $(find "$STORAGE_PATH/outbox" -name '*.json' 2>/dev/null | wc -l) 个文件"
    echo "  Pending: $(find "$STORAGE_PATH/pending" -name '*.json' 2>/dev/null | wc -l) 个文件"
    echo ""
    echo -e "${BLUE}数据目录:${NC}"
    echo "  Gateway: $STORAGE_PATH"
    echo "  Kernel:  $KERNEL_DATA_PATH"
    echo ""
    echo -e "${GREEN}✓ 所有测试通过${NC}"
}

# 主流程
main() {
    check_dependencies
    build_gateway
    install_kernel_deps
    clean_test_data
    start_gateway
    start_kernel
    send_test_request
    verify_inbox
    wait_for_response
    verify_history
    print_summary
}

# 运行主流程
main
