#!/bin/bash
#
# Agent Kernel Build Script
# Builds Docker image locally with optimizations
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
IMAGE_NAME="agent-kernel"
IMAGE_TAG="${1:-latest}"
DOCKERFILE="docker/Dockerfile"
BUILD_CONTEXT="."

# Functions
print_header() {
    echo -e "${BLUE}"
    echo "╔════════════════════════════════════════════════════════════╗"
    echo "║         Agent Kernel - Local Build                         ║"
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

# Check dependencies
check_deps() {
    if ! command -v docker &>/dev/null; then
        print_error "Docker is not installed."
        exit 1
    fi
    
    # Check if Docker daemon is running
    if ! docker info >/dev/null 2>&1; then
        print_error "Docker daemon is not running."
        exit 1
    fi
    
    print_success "Docker is available"
}

# Check if config exists
check_config() {
    local config_file="${HOME}/.agent-kernel/config/.env"
    if [ ! -f "$config_file" ]; then
        print_warning "Configuration file not found: $config_file"
        print_info "Please run: ./scripts/setup.sh"
        exit 1
    fi
    print_success "Configuration found"
}

# Check buildx availability
setup_buildx() {
    if docker buildx version >/dev/null 2>&1; then
        print_success "Docker Buildx is available"
        
        # Create builder if it doesn't exist
        if ! docker buildx inspect agent-kernel-builder >/dev/null 2>&1; then
            print_info "Creating buildx builder..."
            docker buildx create --name agent-kernel-builder --use
        fi
        
        USE_BUILDX=true
    else
        print_warning "Docker Buildx not available, using standard build"
        USE_BUILDX=false
    fi
}

# Calculate cache settings
get_cache_opts() {
    local cache_opts=""
    
    # Check if cache should be used
    if [ "${NO_CACHE:-false}" = "true" ]; then
        cache_opts="--no-cache"
        print_info "Building without cache"
    else
        # Use BuildKit cache if available
        if [ "$USE_BUILDX" = true ]; then
            cache_opts="--cache-from type=local,src=/tmp/.buildx-cache \
                       --cache-to type=local,dest=/tmp/.buildx-cache-new,mode=max"
        fi
    fi
    
    echo "$cache_opts"
}

# Build image
build_image() {
    echo ""
    print_info "Building image: ${IMAGE_NAME}:${IMAGE_TAG}"
    echo "  - Platform: linux/amd64"
    echo "  - Dockerfile: ${DOCKERFILE}"
    echo "  - Context: ${BUILD_CONTEXT}"
    echo ""
    
    local cache_opts=$(get_cache_opts)
    
    # Export DOCKER_BUILDKIT for standard build
    export DOCKER_BUILDKIT=1
    
    if [ "$USE_BUILDX" = true ]; then
        print_info "Using Buildx for optimized build..."
        
        # Ensure cache directory exists
        mkdir -p /tmp/.buildx-cache
        
        docker buildx build \
            --platform linux/amd64 \
            --tag "${IMAGE_NAME}:${IMAGE_TAG}" \
            --file "${DOCKERFILE}" \
            --build-arg BUILDKIT_INLINE_CACHE=1 \
            $cache_opts \
            --load \
            "${BUILD_CONTEXT}"
        
        # Update cache
        if [ -d /tmp/.buildx-cache-new ]; then
            rm -rf /tmp/.buildx-cache
            mv /tmp/.buildx-cache-new /tmp/.buildx-cache
        fi
    else
        print_info "Using standard Docker build..."
        
        docker build \
            --tag "${IMAGE_NAME}:${IMAGE_TAG}" \
            --file "${DOCKERFILE}" \
            --build-arg BUILDKIT_INLINE_CACHE=1 \
            $cache_opts \
            "${BUILD_CONTEXT}"
    fi
}

# Show build result
show_result() {
    echo ""
    print_success "Build completed successfully!"
    echo ""
    
    # Get image size
    local size=$(docker images "${IMAGE_NAME}:${IMAGE_TAG}" --format "{{.Size}}")
    print_info "Image: ${IMAGE_NAME}:${IMAGE_TAG}"
    print_info "Size: $size"
    echo ""
    
    # Show available commands
    echo "Available commands:"
    echo "  Start service:  ./scripts/start.sh"
    echo "  View logs:      docker logs -f agent-kernel"
    echo "  Shell access:   docker exec -it agent-kernel /bin/sh"
    echo ""
}

# Parse arguments
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --no-cache)
                NO_CACHE=true
                shift
                ;;
            --tag|-t)
                IMAGE_TAG="$2"
                shift 2
                ;;
            --help|-h)
                echo "Usage: $0 [OPTIONS]"
                echo ""
                echo "Options:"
                echo "  -t, --tag TAG     Set image tag (default: latest)"
                echo "  --no-cache        Build without cache"
                echo "  -h, --help        Show this help"
                exit 0
                ;;
            *)
                print_error "Unknown option: $1"
                exit 1
                ;;
        esac
    done
}

# Main
main() {
    print_header
    
    parse_args "$@"
    
    # Change to project root
    cd "$(dirname "$0")/.."
    
    check_deps
    check_config
    setup_buildx
    build_image
    show_result
}

# Run
main "$@"
