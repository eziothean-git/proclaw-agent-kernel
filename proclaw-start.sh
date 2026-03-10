#!/bin/bash
# ProClaw - 一键启动脚本
# 自动停止现有服务、启动Gateway和Python Kernel、进入TUI

set -e

# 颜色配置
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color
BOLD='\033[1m'

# 项目路径
PROJECT_ROOT="/home/eziothean/ProClaw/agent-kernel"
GATEWAY_DIR="${PROJECT_ROOT}/apps/gateway"
KERNEL_DIR="${PROJECT_ROOT}/apps/python-kernel"
TUI_DIR="${GATEWAY_DIR}/clients/tui"

# 服务端口
GATEWAY_PORT=3000
KERNEL_PORT=8000

# 日志文件
GATEWAY_LOG="/tmp/proclaw-gateway.log"
KERNEL_LOG="/tmp/proclaw-kernel.log"

# 环境变量
export ARK_API_KEY="${ARK_API_KEY:-62663763-1f8a-4c10-862e-b5d760b19fba}"
export LLM_PROVIDER="${LLM_PROVIDER:-ark}"
export ARK_MODEL="${ARK_MODEL:-glm-4-7-251222}"
export GATEWAY_STORAGE_PATH="${PROJECT_ROOT}/data/gateway"
export DATA_PATH="${PROJECT_ROOT}/data"
export GATEWAY_URL="http://localhost:${GATEWAY_PORT}"

# 打印带颜色的信息
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

print_header() {
    echo -e "\n${CYAN}${BOLD}$1${NC}"
    echo -e "${CYAN}$(printf '=%.0s' $(seq 1 ${#1}))${NC}\n"
}

# 检查端口是否被占用
check_port() {
    local port=$1
    if lsof -Pi :${port} -sTCP:LISTEN -t >/dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

# 获取占用端口的进程PID
get_port_pid() {
    local port=$1
    lsof -Pi :${port} -sTCP:LISTEN -t 2>/dev/null
}

# 停止指定端口的服务
stop_service_on_port() {
    local port=$1
    local name=$2
    
    if check_port ${port}; then
        local pid=$(get_port_pid ${port})
        print_warning "发现 ${name} 正在端口 ${port} 运行 (PID: ${pid})"
        print_info "正在停止 ${name}..."
        
        # 先尝试优雅停止
        kill ${pid} 2>/dev/null || true
        sleep 2
        
        # 如果还在运行，强制停止
        if check_port ${port}; then
            print_warning "${name} 未响应，强制停止..."
            kill -9 ${pid} 2>/dev/null || true
            sleep 1
        fi
        
        if check_port ${port}; then
            print_error "无法停止 ${name}"
            return 1
        else
            print_success "${name} 已停止"
        fi
    else
        print_info "${name} 未在运行"
    fi
}

# 检查并停止现有服务
stop_existing_services() {
    print_header "🛑 停止现有服务"
    
    # 停止 Gateway
    stop_service_on_port ${GATEWAY_PORT} "Gateway"
    
    # 停止 Python Kernel
    stop_service_on_port ${KERNEL_PORT} "Python Kernel"
    
    # 清理可能残留的Python缓存
    find ${KERNEL_DIR} -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
    find ${KERNEL_DIR} -type f -name "*.pyc" -delete 2>/dev/null || true
    
    print_success "服务清理完成"
    sleep 1
}

# 等待服务启动
wait_for_service() {
    local url=$1
    local name=$2
    local max_attempts=30
    local attempt=1
    
    print_info "等待 ${name} 启动..."
    
    while [ ${attempt} -le ${max_attempts} ]; do
        if curl -s ${url} >/dev/null 2>&1; then
            print_success "${name} 已就绪"
            return 0
        fi
        
        echo -n "."
        sleep 1
        attempt=$((attempt + 1))
    done
    
    echo ""
    print_error "${name} 启动超时"
    return 1
}

# 启动 Gateway
start_gateway() {
    print_header "🚀 启动 Gateway"
    
    cd ${GATEWAY_DIR}
    
    # 检查是否需要构建
    if [ ! -d "dist" ] || [ ! -f "dist/main.js" ]; then
        print_info "检测到需要构建 Gateway..."
        npm run build
        print_success "Gateway 构建完成"
    fi
    
    # 启动服务
    print_info "正在启动 Gateway (端口: ${GATEWAY_PORT})..."
    nohup npm run start:prod > ${GATEWAY_LOG} 2>&1 &
    
    # 等待服务就绪
    if wait_for_service "http://localhost:${GATEWAY_PORT}/api/v1/health" "Gateway"; then
        local version=$(curl -s http://localhost:${GATEWAY_PORT}/api/v1/health | grep -o '"version":"[^"]*"' | cut -d'"' -f4)
        print_success "Gateway 启动成功 (版本: ${version})"
        return 0
    else
        print_error "Gateway 启动失败"
        print_info "查看日志: tail -f ${GATEWAY_LOG}"
        return 1
    fi
}

# 启动 Python Kernel
start_kernel() {
    print_header "🐍 启动 Python Kernel"
    
    cd ${KERNEL_DIR}
    
    # 启动服务
    print_info "正在启动 Python Kernel (端口: ${KERNEL_PORT})..."
    PYTHONPATH=${KERNEL_DIR} nohup python main.py > ${KERNEL_LOG} 2>&1 &
    
    # 等待服务就绪
    if wait_for_service "http://localhost:${KERNEL_PORT}/health" "Python Kernel"; then
        local version=$(curl -s http://localhost:${KERNEL_PORT}/health | grep -o '"version":"[^"]*"' | cut -d'"' -f4)
        print_success "Python Kernel 启动成功 (版本: ${version})"
        return 0
    else
        print_error "Python Kernel 启动失败"
        print_info "查看日志: tail -f ${KERNEL_LOG}"
        return 1
    fi
}

# 显示服务状态
show_status() {
    print_header "📊 服务状态"
    
    echo -e "${BOLD}Gateway:${NC}"
    if check_port ${GATEWAY_PORT}; then
        local health=$(curl -s http://localhost:${GATEWAY_PORT}/api/v1/health 2>/dev/null)
        echo "  状态: ${GREEN}运行中${NC}"
        echo "  端口: ${GATEWAY_PORT}"
        echo "  版本: $(echo ${health} | grep -o '"version":"[^"]*"' | cut -d'"' -f4)"
    else
        echo "  状态: ${RED}未运行${NC}"
    fi
    
    echo ""
    echo -e "${BOLD}Python Kernel:${NC}"
    if check_port ${KERNEL_PORT}; then
        local health=$(curl -s http://localhost:${KERNEL_PORT}/health 2>/dev/null)
        echo "  状态: ${GREEN}运行中${NC}"
        echo "  端口: ${KERNEL_PORT}"
        echo "  版本: $(echo ${health} | grep -o '"version":"[^"]*"' | cut -d'"' -f4)"
    else
        echo "  状态: ${RED}未运行${NC}"
    fi
    
    echo ""
    echo -e "${BOLD}日志文件:${NC}"
    echo "  Gateway: ${GATEWAY_LOG}"
    echo "  Kernel:  ${KERNEL_LOG}"
}

# 启动 TUI
start_tui() {
    print_header "🖥️  启动 ProClaw TUI"
    
    cd ${TUI_DIR}
    
    # 确保 TUI 已安装
    if ! command -v proclaw &> /dev/null; then
        print_info "安装 ProClaw TUI..."
        pip install -e . -q
        print_success "安装完成"
    fi
    
    print_info "正在启动 TUI 客户端..."
    print_info "提示: 首次 LLM 响应可能需要 10-30 秒"
    echo ""
    sleep 2
    
    # 启动 TUI
    exec proclaw --url "http://localhost:${GATEWAY_PORT}" --user "proclaw-user"
}

# 清理函数
cleanup() {
    echo ""
    print_warning "收到中断信号"
    print_info "服务仍在后台运行"
    print_info "使用以下命令停止服务:"
    echo "  kill $(lsof -Pi :${GATEWAY_PORT} -sTCP:LISTEN -t 2>/dev/null) 2>/dev/null || true"
    echo "  kill $(lsof -Pi :${KERNEL_PORT} -sTCP:LISTEN -t 2>/dev/null) 2>/dev/null || true"
    exit 0
}

# 设置信号处理
trap cleanup INT TERM

# 主函数
main() {
    # 显示欢迎信息
    clear
    echo -e "${CYAN}"
    cat << "EOF"
    ____             __            __
   / __ \_________  / /____  _____/ /_
  / /_/ / ___/ _ \/ __/ _ \/ ___/ __/
 / ____/ /  /  __/ /_/  __/ /__/ /_
/_/   /_/   \___/\__/\___/\___/\__/

EOF
    echo -e "${NC}"
    
    print_header "🎮 ProClaw 一键启动脚本"
    
    # 检查依赖
    print_info "检查依赖..."
    
    if ! command -v node &> /dev/null; then
        print_error "未找到 Node.js"
        exit 1
    fi
    
    if ! command -v python3 &> /dev/null; then
        print_error "未找到 Python3"
        exit 1
    fi
    
    if ! command -v pip &> /dev/null; then
        print_error "未找到 pip"
        exit 1
    fi
    
    print_success "依赖检查通过"
    
    # 停止现有服务
    stop_existing_services
    
    # 启动 Gateway
    if ! start_gateway; then
        exit 1
    fi
    
    # 启动 Python Kernel
    if ! start_kernel; then
        exit 1
    fi
    
    # 显示状态
    show_status
    
    # 启动 TUI
    start_tui
}

# 处理命令行参数
case "${1:-}" in
    --status|-s)
        show_status
        exit 0
        ;;
    --stop)
        stop_existing_services
        print_success "所有服务已停止"
        exit 0
        ;;
    --logs|-l)
        print_header "📋 实时日志"
        echo "按 Ctrl+C 退出日志查看"
        tail -f ${GATEWAY_LOG} ${KERNEL_LOG} 2>/dev/null
        exit 0
        ;;
    --help|-h)
        echo "ProClaw 一键启动脚本"
        echo ""
        echo "用法: $0 [选项]"
        echo ""
        echo "选项:"
        echo "  --status, -s    显示服务状态"
        echo "  --stop          停止所有服务"
        echo "  --logs, -l      查看实时日志"
        echo "  --help, -h      显示此帮助"
        echo ""
        echo "示例:"
        echo "  $0              # 启动所有服务并进入TUI"
        echo "  $0 --status     # 查看服务状态"
        echo "  $0 --stop       # 停止所有服务"
        exit 0
        ;;
    *)
        main
        ;;
esac
