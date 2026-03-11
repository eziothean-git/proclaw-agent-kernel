#!/bin/bash
# Gateway + Request Manager + Python Kernel 集成测试脚本
# 完整服务链测试：Gateway → Request Manager (gRPC) → Python Kernel

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color
BOLD='\033[1m'

# 配置
GATEWAY_PORT=3000
KERNEL_PORT=8000
REQUEST_MANAGER_PORT=50052
GATEWAY_URL="http://localhost:$GATEWAY_PORT"
KERNEL_URL="http://localhost:$KERNEL_PORT"

# 使用项目根目录下的 data 目录
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DATA_PATH="${PROJECT_ROOT}/data"
KERNEL_DATA_PATH="${PROJECT_ROOT}/apps/python-kernel/data"
STORAGE_PATH="${DATA_PATH}/gateway"

print_header() {
    echo -e "${CYAN}${BOLD}$1${NC}"
    echo -e "${CYAN}$(printf '=%.0s' $(seq 1 ${#1}))${NC}"
}

print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[✓]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

print_error() {
    echo -e "${RED}[✗]${NC} $1"
}

echo ""
print_header "Gateway + Request Manager + Python Kernel 集成测试"
echo ""
print_info "项目根目录: $PROJECT_ROOT"
print_info "数据目录: $DATA_PATH"
echo ""

# PID 文件
REQUEST_MANAGER_PID_FILE="/tmp/request-manager-integration.pid"
GATEWAY_PID_FILE="/tmp/gateway-integration.pid"
KERNEL_PID_FILE="/tmp/kernel-integration.pid"

# 清理函数
cleanup() {
    echo ""
    print_warning "清理进程中..."
    
    # 停止 Gateway
    if [ -f "$GATEWAY_PID_FILE" ]; then
        GATEWAY_PID=$(cat "$GATEWAY_PID_FILE")
        kill $GATEWAY_PID 2>/dev/null || true
        rm -f "$GATEWAY_PID_FILE"
        print_info "Gateway 已停止"
    fi
    
    # 停止 Python Kernel
    if [ -f "$KERNEL_PID_FILE" ]; then
        KERNEL_PID=$(cat "$KERNEL_PID_FILE")
        kill $KERNEL_PID 2>/dev/null || true
        rm -f "$KERNEL_PID_FILE"
        print_info "Python Kernel 已停止"
    fi
    
    # 停止 Request Manager
    if [ -f "$REQUEST_MANAGER_PID_FILE" ]; then
        REQUEST_MANAGER_PID=$(cat "$REQUEST_MANAGER_PID_FILE")
        kill $REQUEST_MANAGER_PID 2>/dev/null || true
        rm -f "$REQUEST_MANAGER_PID_FILE"
        print_info "Request Manager 已停止"
    fi
    
    # 强制释放端口
    for port in $GATEWAY_PORT $KERNEL_PORT $REQUEST_MANAGER_PORT; do
        pid=$(lsof -Pi :$port -sTCP:LISTEN -t 2>/dev/null)
        if [ -n "$pid" ]; then
            kill -9 $pid 2>/dev/null || true
        fi
    done
    
    print_success "清理完成"
}

trap cleanup EXIT

# 检查依赖
check_dependencies() {
    print_header "[1/10] 检查依赖"
    
    if ! command -v node &> /dev/null; then
        print_error "Node.js 未安装"
        exit 1
    fi
    
    if ! command -v python3 &> /dev/null; then
        print_error "Python3 未安装"
        exit 1
    fi
    
    if ! command -v curl &> /dev/null; then
        print_error "curl 未安装"
        exit 1
    fi
    
    print_success "Node.js: $(node --version)"
    print_success "Python3: $(python3 --version)"
    print_success "curl: 已安装"
}

# 构建 Request Manager
build_request_manager() {
    print_header "[2/10] 构建 Request Manager"
    cd "${PROJECT_ROOT}/apps/request-manager"
    
    if [ ! -d "node_modules" ]; then
        print_info "安装依赖..."
        npm install 2>&1 | tail -5
    fi
    
    print_info "编译 TypeScript..."
    npm run build 2>&1 | tail -5
    
    print_success "Request Manager 构建完成"
}

# 构建 Gateway
build_gateway() {
    print_header "[3/10] 构建 Gateway"
    cd "${PROJECT_ROOT}/apps/gateway"
    
    if [ ! -d "node_modules" ]; then
        print_info "安装依赖..."
        npm install 2>&1 | tail -5
    fi
    
    print_info "编译 TypeScript..."
    npm run build 2>&1 | tail -5
    
    print_success "Gateway 构建完成"
}

# 安装 Python Kernel 依赖
install_kernel_deps() {
    print_header "[4/10] 安装 Python Kernel 依赖"
    cd "${PROJECT_ROOT}/apps/python-kernel"
    
    # 检查是否已安装
    if python3 -c "import pydantic" 2>/dev/null; then
        print_success "Python 依赖已安装"
    else
        print_info "安装 Python 依赖..."
        pip3 install -e "." 2>&1 | tail -5
    fi
    
    print_success "Python Kernel 依赖就绪"
}

# 清理测试数据
clean_test_data() {
    print_header "[5/10] 清理测试数据"
    rm -rf "$STORAGE_PATH" "$KERNEL_DATA_PATH"
    mkdir -p "$STORAGE_PATH"/{inbox,outbox,pending,attachments,sessions,errors,logs,request-manager}
    print_success "已清理: $STORAGE_PATH"
    print_success "已清理: $KERNEL_DATA_PATH"
}

# 启动 Request Manager
start_request_manager() {
    print_header "[6/10] 启动 Request Manager (gRPC:50052)"
    cd "${PROJECT_ROOT}/apps/request-manager"
    
    export GATEWAY_STORAGE_PATH="$STORAGE_PATH"
    export REQUEST_MANAGER_GRPC_PORT="$REQUEST_MANAGER_PORT"
    
    node dist/main.js > /tmp/request-manager-integration.log 2>&1 &
    REQUEST_MANAGER_PID=$!
    echo $REQUEST_MANAGER_PID > "$REQUEST_MANAGER_PID_FILE"
    
    # 等待 Request Manager 启动
    print_info "等待 Request Manager 启动..."
    for i in {1..30}; do
        if lsof -Pi :$REQUEST_MANAGER_PORT -sTCP:LISTEN >/dev/null 2>&1; then
            print_success "Request Manager 已启动 (PID: $REQUEST_MANAGER_PID, Port: $REQUEST_MANAGER_PORT)"
            return 0
        fi
        sleep 1
    done
    
    print_error "Request Manager 启动失败"
    tail -20 /tmp/request-manager-integration.log
    exit 1
}

# 启动 Python Kernel
start_kernel() {
    print_header "[7/10] 启动 Python Kernel (HTTP:8000)"
    cd "${PROJECT_ROOT}/apps/python-kernel"
    
    export PORT="$KERNEL_PORT"
    export HOST="0.0.0.0"
    export KERNEL_RUN_MODE="mock"
    export DATA_PATH="$KERNEL_DATA_PATH"
    export GATEWAY_INBOX_PATH="$STORAGE_PATH/inbox"
    export GATEWAY_URL="$GATEWAY_URL"
    export INBOX_POLL_INTERVAL="0.5"
    
    PYTHONPATH="${PROJECT_ROOT}/apps/python-kernel" python3 main.py > /tmp/kernel-integration.log 2>&1 &
    KERNEL_PID=$!
    echo $KERNEL_PID > "$KERNEL_PID_FILE"
    
    # 等待 Kernel 启动
    print_info "等待 Python Kernel 启动..."
    for i in {1..30}; do
        if curl -s "$KERNEL_URL/health" > /dev/null 2>&1; then
            print_success "Python Kernel 已启动 (PID: $KERNEL_PID, Port: $KERNEL_PORT)"
            return 0
        fi
        sleep 1
    done
    
    print_error "Python Kernel 启动失败"
    tail -20 /tmp/kernel-integration.log
    exit 1
}

# 启动 Gateway
start_gateway() {
    print_header "[8/10] 启动 Gateway (HTTP:3000)"
    cd "${PROJECT_ROOT}/apps/gateway"
    
    export GATEWAY_STORAGE_PATH="$STORAGE_PATH"
    export NODE_ENV="test"
    export PORT="$GATEWAY_PORT"
    export PYTHON_KERNEL_URL="$KERNEL_URL"
    
    node dist/main > /tmp/gateway-integration.log 2>&1 &
    GATEWAY_PID=$!
    echo $GATEWAY_PID > "$GATEWAY_PID_FILE"
    
    # 等待 Gateway 启动
    print_info "等待 Gateway 启动..."
    for i in {1..30}; do
        if curl -s "$GATEWAY_URL/api/v1/health" > /dev/null 2>&1; then
            print_success "Gateway 已启动 (PID: $GATEWAY_PID, Port: $GATEWAY_PORT)"
            return 0
        fi
        sleep 1
    done
    
    print_error "Gateway 启动失败"
    tail -20 /tmp/gateway-integration.log
    exit 1
}

# 发送测试请求
send_test_request() {
    print_header "[9/10] 发送测试请求"
    
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
        print_error "发送请求失败"
        echo "响应: $RESPONSE"
        exit 1
    fi
    
    print_success "请求已接受"
    print_info "Request ID: $REQUEST_ID"
}

# 验证请求流程
verify_request_flow() {
    print_header "[10/10] 验证请求流程"
    
    # 检查 inbox
    sleep 1
    INBOX_COUNT=$(find "$STORAGE_PATH/inbox" -name "*.json" 2>/dev/null | wc -l)
    if [ "$INBOX_COUNT" -eq 0 ]; then
        print_error "inbox 为空"
        exit 1
    fi
    print_success "inbox 中有 $INBOX_COUNT 个请求文件"
    
    # 等待响应
    print_info "等待响应..."
    ATTEMPTS=0
    MAX_ATTEMPTS=30
    
    while [ $ATTEMPTS -lt $MAX_ATTEMPTS ]; do
        sleep 1
        ATTEMPTS=$((ATTEMPTS + 1))
        
        # 检查 outbox
        OUTBOX_COUNT=$(find "$STORAGE_PATH/outbox" -name "*.json" 2>/dev/null | wc -l)
        
        if [ "$OUTBOX_COUNT" -gt 0 ]; then
            print_success "响应已生成 ($OUTBOX_COUNT 个文件)"
            break
        fi
        
        echo "  等待中... ($ATTEMPTS/$MAX_ATTEMPTS)"
    done
    
    if [ $ATTEMPTS -eq $MAX_ATTEMPTS ]; then
        print_error "超时，未收到响应"
        exit 1
    fi
}

# 打印测试总结
print_summary() {
    echo ""
    print_header "集成测试完成"
    echo ""
    print_info "文件系统状态:"
    echo "  Inbox:  $(find "$STORAGE_PATH/inbox" -name '*.json' 2>/dev/null | wc -l) 个文件"
    echo "  Outbox: $(find "$STORAGE_PATH/outbox" -name '*.json' 2>/dev/null | wc -l) 个文件"
    echo "  Pending: $(find "$STORAGE_PATH/pending" -name '*.json' 2>/dev/null | wc -l) 个文件"
    echo ""
    print_info "数据目录:"
    echo "  Gateway: $STORAGE_PATH"
    echo "  Kernel:  $KERNEL_DATA_PATH"
    echo ""
    print_success "所有测试通过"
}

# 主流程
main() {
    check_dependencies
    build_request_manager
    build_gateway
    install_kernel_deps
    clean_test_data
    start_request_manager
    start_kernel
    start_gateway
    send_test_request
    verify_request_flow
    print_summary
}

# 运行主流程
main
