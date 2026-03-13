#!/bin/bash
# ProClaw System Manager
# Manages Gateway, Request Manager, and Prime Personality services

set -e

# Base directory
BASE_DIR="/home/eziothean/ProClaw"
cd "$BASE_DIR"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
export GATEWAY_STORAGE_PATH="${BASE_DIR}/agent-kernel/apps/gateway/data/storage"
export GATEWAY_SCHEMAS_PATH="${BASE_DIR}/agent-kernel/apps/gateway/data/schemas"
export RUST_LOG="info"

log() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')] $1${NC}"
}

error() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')] ERROR: $1${NC}"
}

warn() {
    echo -e "${YELLOW}[$(date '+%Y-%m-%d %H:%M:%S')] WARNING: $1${NC}"
}

# Check if service is running
check_service() {
    local port=$1
    local name=$2
    if ss -tlnp | grep -q ":$port "; then
        echo "✅ $name (port $port)"
        return 0
    else
        echo "❌ $name (port $port)"
        return 1
    fi
}

# Stop all services
stop_all() {
    log "Stopping all services..."
    
    # Stop Gateway
    pkill -f "node dist/main" 2>/dev/null || true
    sleep 1
    
    # Stop Request Manager
    pkill -f "request-manager.*start" 2>/dev/null || true
    sleep 1
    
    # Stop Prime Personality
    pkill -f "proclaw-composer" 2>/dev/null || true
    sleep 2
    
    log "All services stopped"
}

# Start Prime Personality
start_prime() {
    log "Starting Prime Personality..."
    
    if check_service 50051 "Prime Personality" > /dev/null; then
        warn "Prime Personality already running"
        return 0
    fi
    
    cd "${BASE_DIR}/kernel-v2"
    nohup ./target/release/proclaw-composer \
        --config ./config/composer.yaml \
        --data-dir ./data \
        --llm-api-key "62663763-1f8a-4c10-862e-b5d760b19fba" \
        --llm-base-url "https://ark.cn-beijing.volces.com/api/v3" \
        --llm-model "glm-4-7-251222" \
        > /tmp/prime.log 2>&1 &
    
    # Wait for startup
    for i in {1..30}; do
        if check_service 50051 "Prime Personality" > /dev/null; then
            log "Prime Personality started successfully"
            return 0
        fi
        sleep 1
    done
    
    error "Prime Personality failed to start"
    return 1
}

# Start Gateway
start_gateway() {
    log "Starting Gateway..."
    
    if check_service 3000 "Gateway" > /dev/null; then
        warn "Gateway already running"
        return 0
    fi
    
    mkdir -p "$GATEWAY_STORAGE_PATH" "$GATEWAY_SCHEMAS_PATH"
    
    cd "${BASE_DIR}/agent-kernel/apps/gateway"
    nohup node dist/main > /tmp/gateway.log 2>&1 &
    
    # Wait for startup
    for i in {1..30}; do
        if check_service 3000 "Gateway" > /dev/null; then
            log "Gateway started successfully"
            return 0
        fi
        sleep 1
    done
    
    error "Gateway failed to start"
    return 1
}

# Start Request Manager
start_request_manager() {
    log "Starting Request Manager..."
    
    if check_service 50052 "Request Manager" > /dev/null; then
        warn "Request Manager already running"
        return 0
    fi
    
    cd "${BASE_DIR}/agent-kernel/apps/request-manager"
    nohup npm run start > /tmp/request-manager.log 2>&1 &
    
    # Wait for startup
    for i in {1..30}; do
        if check_service 50052 "Request Manager" > /dev/null; then
            log "Request Manager started successfully"
            return 0
        fi
        sleep 1
    done
    
    error "Request Manager failed to start"
    return 1
}

# Start all services
start_all() {
    log "Starting ProClaw system..."
    
    # Start in reverse order (Prime -> Gateway -> Request Manager)
    start_prime || exit 1
    sleep 2
    
    start_gateway || exit 1
    sleep 2
    
    start_request_manager || exit 1
    sleep 2
    
    log "All services started successfully!"
    echo ""
    status
}

# Show status
status() {
    echo ""
    echo "=== ProClaw System Status ==="
    echo ""
    check_service 50051 "Prime Personality (Rust)"
    check_service 3000 "Gateway (TypeScript)"
    check_service 50052 "Request Manager (TypeScript)"
    echo ""
}

# Restart services
restart() {
    log "Restarting all services..."
    stop_all
    sleep 3
    start_all
}

# View logs
logs() {
    local service=$1
    case $service in
        prime)
            tail -f /tmp/prime.log
            ;;
        gateway)
            tail -f /tmp/gateway.log
            ;;
        request-manager|rm)
            tail -f /tmp/request-manager.log
            ;;
        *)
            echo "Usage: $0 logs [prime|gateway|request-manager]"
            exit 1
            ;;
    esac
}

# Test the system
test_system() {
    log "Testing system..."
    
    # Check all services are running
    if ! check_service 50051 "Prime Personality" > /dev/null; then
        error "Prime Personality not running"
        return 1
    fi
    
    if ! check_service 3000 "Gateway" > /dev/null; then
        error "Gateway not running"
        return 1
    fi
    
    if ! check_service 50052 "Request Manager" > /dev/null; then
        error "Request Manager not running"
        return 1
    fi
    
    # Send test request
    log "Sending test request..."
    response=$(curl -s -X POST http://localhost:3000/api/v1/chat \
        -H "Content-Type: application/json" \
        -d '{
            "message": "你好",
            "session_id": "test-session",
            "user_id": "test-user",
            "priority": 10
        }')
    
    if echo "$response" | grep -q "accepted"; then
        log "Test request accepted!"
        echo "Response: $response"
        return 0
    else
        error "Test request failed"
        echo "Response: $response"
        return 1
    fi
}

kill_all() {
    log "Force killing all services..."
    
    pkill -9 -f "proclaw-composer" 2>/dev/null || true
    pkill -9 -f "node dist/main" 2>/dev/null || true
    pkill -9 -f "request-manager" 2>/dev/null || true
    
    for port in 3000 50051 50052; do
        pid=$(lsof -Pi :$port -sTCP:LISTEN -t 2>/dev/null || true)
        if [ -n "$pid" ]; then
            log "Killing process on port $port (PID: $pid)"
            kill -9 $pid 2>/dev/null || true
        fi
    done
    
    sleep 1
    
    local remaining=0
    for port in 3000 50051 50052; do
        if lsof -Pi :$port -sTCP:LISTEN >/dev/null 2>&1; then
            remaining=$((remaining + 1))
        fi
    done
    
    if [ "$remaining" -eq 0 ]; then
        log "All services force killed successfully"
    else
        warn "$remaining service(s) still running"
    fi
}

clear_logs() {
    log "Clearing all logs..."
    
    local log_files=(
        "/tmp/prime.log"
        "/tmp/prime-live.log"
        "/tmp/gateway.log"
        "/tmp/proclaw-gateway.log"
        "/tmp/request-manager.log"
        "/tmp/proclaw-rust-kernel.log"
        "/tmp/proclaw-composer.log"
    )
    
    for log_file in "${log_files[@]}"; do
        if [ -f "$log_file" ]; then
            > "$log_file"
            log "Cleared: $log_file"
        fi
    done
    
    rm -f /tmp/prime-*.log 2>/dev/null || true
    
    log "All logs cleared"
}

case "${1:-}" in
    start)
        start_all
        ;;
    stop)
        stop_all
        ;;
    restart)
        restart
        ;;
    status)
        status
        ;;
    logs)
        logs "$2"
        ;;
    test)
        test_system
        ;;
    kill)
        kill_all
        ;;
    clear-logs)
        clear_logs
        ;;
    *)
        echo "ProClaw System Manager"
        echo ""
        echo "Usage: $0 {start|stop|restart|status|test|kill|clear-logs|logs}"
        echo ""
        echo "Commands:"
        echo "  start              Start all services"
        echo "  stop               Stop all services gracefully"
        echo "  kill               Force kill all services"
        echo "  restart            Restart all services"
        echo "  status             Show service status"
        echo "  test               Test system with a sample request"
        echo "  clear-logs         Clear all log files"
        echo "  logs <service>     View logs (prime|gateway|request-manager)"
        echo ""
        echo "Services:"
        echo "  - Prime Personality (Rust) on port 50051"
        echo "  - Gateway (TypeScript) on port 3000"
        echo "  - Request Manager (TypeScript) on port 50052"
        exit 1
        ;;
esac
