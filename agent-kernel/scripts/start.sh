#!/bin/bash
#
# Agent Kernel Start Script
# Manages container lifecycle
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
CONTAINER_NAME="agent-kernel"
IMAGE_NAME="agent-kernel"
IMAGE_TAG="latest"
CONFIG_DIR="${HOME}/.agent-kernel"
ENV_FILE="${CONFIG_DIR}/config/.env"
COMPOSE_FILE="docker/docker-compose.yml"

# Functions
print_header() {
    echo -e "${BLUE}"
    echo "╔════════════════════════════════════════════════════════════╗"
    echo "║         Agent Kernel - Container Manager                   ║"
    echo "╚════════════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

# Check if container is running
is_running() {
    docker ps --filter "name=${CONTAINER_NAME}" --format "{{.Names}}" | grep -q "^${CONTAINER_NAME}$"
}

# Check if container exists
exists() {
    docker ps -a --filter "name=${CONTAINER_NAME}" --format "{{.Names}}" | grep -q "^${CONTAINER_NAME}$"
}

# Get container status
get_status() {
    docker inspect -f '{{.State.Status}}' "${CONTAINER_NAME}" 2>/dev/null || echo "not found"
}

# Start container
start_container() {
    if is_running; then
        print_warning "Container '${CONTAINER_NAME}' is already running"
        show_status
        return 0
    fi
    
    if exists; then
        print_info "Starting existing container..."
        docker start "${CONTAINER_NAME}"
    else
        print_info "Creating and starting new container..."
        
        # Check if image exists
        if ! docker images "${IMAGE_NAME}:${IMAGE_TAG}" --format "{{.Repository}}" | grep -q "^${IMAGE_NAME}$"; then
            print_error "Image '${IMAGE_NAME}:${IMAGE_TAG}' not found"
            print_info "Please build first: ./scripts/build.sh"
            exit 1
        fi
        
        # Check config
        if [ ! -f "$ENV_FILE" ]; then
            print_error "Configuration not found: $ENV_FILE"
            print_info "Please run: ./scripts/setup.sh"
            exit 1
        fi
        
        # Create and start container
        docker run -d \
            --name "${CONTAINER_NAME}" \
            --restart unless-stopped \
            -p 3000:3000 \
            -p 8000:8000 \
            --env-file "${ENV_FILE}" \
            -v agent-kernel-data:/app/data \
            -v agent-kernel-logs:/var/log/supervisor \
            -v /etc/localtime:/etc/localtime:ro \
            "${IMAGE_NAME}:${IMAGE_TAG}"
    fi
    
    print_success "Container started"
    show_status
    
    # Wait for health check
    print_info "Waiting for services to be ready..."
    sleep 5
    
    local retries=30
    while [ $retries -gt 0 ]; do
        if curl -s http://localhost:3000/health >/dev/null 2>&1; then
            print_success "Gateway is ready!"
            break
        fi
        sleep 2
        retries=$((retries - 1))
    done
    
    if [ $retries -eq 0 ]; then
        print_warning "Services may still be starting. Check logs with: docker logs -f ${CONTAINER_NAME}"
    fi
}

# Stop container
stop_container() {
    if ! exists; then
        print_warning "Container '${CONTAINER_NAME}' does not exist"
        return 0
    fi
    
    if ! is_running; then
        print_info "Container is already stopped"
        return 0
    fi
    
    print_info "Stopping container..."
    docker stop "${CONTAINER_NAME}"
    print_success "Container stopped"
}

# Restart container
restart_container() {
    stop_container
    start_container
}

# Remove container
remove_container() {
    if ! exists; then
        print_warning "Container '${CONTAINER_NAME}' does not exist"
        return 0
    fi
    
    stop_container
    
    read -p "Are you sure you want to remove the container? [y/N]: " confirm
    if [[ "$confirm" =~ ^[Yy]$ ]]; then
        docker rm "${CONTAINER_NAME}"
        print_success "Container removed"
    else
        print_info "Cancelled"
    fi
}

# Show logs
show_logs() {
    if ! exists; then
        print_error "Container '${CONTAINER_NAME}' does not exist"
        exit 1
    fi
    
    echo -e "${BLUE}Showing logs (press Ctrl+C to exit)...${NC}"
    docker logs -f "${CONTAINER_NAME}"
}

# Show status
show_status() {
    if ! exists; then
        echo "Status: ${YELLOW}Not created${NC}"
        return 0
    fi
    
    local status=$(get_status)
    local health="unknown"
    
    if is_running; then
        # Try to get health status
        health=$(docker inspect -f '{{.State.Health.Status}}' "${CONTAINER_NAME}" 2>/dev/null || echo "N/A")
    fi
    
    echo ""
    echo "Container Status:"
    echo "  Name:    ${CONTAINER_NAME}"
    echo "  Image:   ${IMAGE_NAME}:${IMAGE_TAG}"
    echo "  Status:  ${status}"
    
    if is_running; then
        echo "  Health:  ${health}"
        
        # Show ports
        local ports=$(docker port "${CONTAINER_NAME}" 2>/dev/null | head -2)
        if [ -n "$ports" ]; then
            echo "  Ports:"
            echo "$ports" | sed 's/^/    /'
        fi
        
        # Show uptime
        local started=$(docker inspect -f '{{.State.StartedAt}}' "${CONTAINER_NAME}")
        echo "  Started: ${started}"
    fi
    
    echo ""
}

# Shell access
shell_access() {
    if ! is_running; then
        print_error "Container is not running"
        exit 1
    fi
    
    print_info "Opening shell in container..."
    docker exec -it "${CONTAINER_NAME}" /bin/sh
}

# Backup data
backup_data() {
    if ! exists; then
        print_error "Container does not exist, nothing to backup"
        exit 1
    fi
    
    local backup_dir="${CONFIG_DIR}/backups"
    local timestamp=$(date +%Y%m%d_%H%M%S)
    local backup_file="${backup_dir}/agent-kernel-data-${timestamp}.tar.gz"
    
    mkdir -p "$backup_dir"
    
    print_info "Creating backup..."
    docker run --rm \
        -v agent-kernel-data:/data \
        -v "${backup_dir}:/backup" \
        alpine tar czf "/backup/agent-kernel-data-${timestamp}.tar.gz" -C /data .
    
    print_success "Backup created: ${backup_file}"
}

# Restore data
restore_data() {
    local backup_dir="${CONFIG_DIR}/backups"
    
    # List available backups
    echo "Available backups:"
    ls -1t "${backup_dir}"/*.tar.gz 2>/dev/null | head -5 | nl
    
    if [ ! -d "$backup_dir" ] || [ -z "$(ls -A "$backup_dir"/*.tar.gz 2>/dev/null)" ]; then
        print_error "No backups found in ${backup_dir}"
        exit 1
    fi
    
    read -p "Enter backup number to restore: " backup_num
    local backup_file=$(ls -1t "${backup_dir}"/*.tar.gz 2>/dev/null | sed -n "${backup_num}p")
    
    if [ -z "$backup_file" ]; then
        print_error "Invalid backup number"
        exit 1
    fi
    
    read -p "This will overwrite current data. Continue? [y/N]: " confirm
    if [[ "$confirm" =~ ^[Yy]$ ]]; then
        stop_container
        
        print_info "Restoring from backup..."
        docker run --rm \
            -v agent-kernel-data:/data \
            -v "${backup_dir}:/backup" \
            alpine tar xzf "/backup/$(basename "$backup_file")" -C /data
        
        print_success "Backup restored"
        start_container
    else
        print_info "Cancelled"
    fi
}

# Show help
show_help() {
    echo "Agent Kernel Container Manager"
    echo ""
    echo "Usage: $0 [COMMAND]"
    echo ""
    echo "Commands:"
    echo "  start       Start the container (create if not exists)"
    echo "  stop        Stop the container"
    echo "  restart     Restart the container"
    echo "  remove      Remove the container (keeps data)"
    echo "  status      Show container status"
    echo "  logs        Show container logs"
    echo "  shell       Open shell in running container"
    echo "  backup      Backup container data"
    echo "  restore     Restore container data from backup"
    echo "  help        Show this help message"
    echo ""
    echo "Examples:"
    echo "  $0 start           # Start the service"
    echo "  $0 logs            # View logs"
    echo "  $0 shell           # Access container shell"
}

# Main
main() {
    print_header
    
    # Change to project root
    cd "$(dirname "$0")/.."
    
    # Check Docker
    if ! command -v docker &>/dev/null; then
        print_error "Docker is not installed"
        exit 1
    fi
    
    # Parse command
    case "${1:-start}" in
        start)
            start_container
            ;;
        stop)
            stop_container
            ;;
        restart)
            restart_container
            ;;
        remove|rm)
            remove_container
            ;;
        status)
            show_status
            ;;
        logs)
            show_logs
            ;;
        shell|sh|bash)
            shell_access
            ;;
        backup)
            backup_data
            ;;
        restore)
            restore_data
            ;;
        help|-h|--help)
            show_help
            ;;
        *)
            print_error "Unknown command: $1"
            show_help
            exit 1
            ;;
    esac
}

# Run
main "$@"
