#!/bin/bash
#
# Agent Kernel Release Script
# Builds and publishes Docker image to GitHub Container Registry
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
DOCKERFILE="docker/Dockerfile"
BUILD_CONTEXT="."

# GitHub configuration
GITHUB_REPO="${GITHUB_REPO:-$(git remote get-url origin 2>/dev/null | sed 's/.*github.com[:/]\(.*\)\.git$/\1/')}"
GHCR_REGISTRY="ghcr.io"
GHCR_IMAGE="${GHCR_REGISTRY}/${GITHUB_REPO}/${IMAGE_NAME}"

# Functions
print_header() {
    echo -e "${BLUE}"
    echo "╔════════════════════════════════════════════════════════════╗"
    echo "║         Agent Kernel - GitHub Release                      ║"
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
    print_info "Checking dependencies..."
    
    # Check Docker
    if ! command -v docker &>/dev/null; then
        print_error "Docker is not installed"
        exit 1
    fi
    
    # Check if logged in to GitHub Container Registry
    if ! docker info 2>/dev/null | grep -q "Username"; then
        print_warning "Not logged in to Docker registry"
        print_info "Please run: docker login ${GHCR_REGISTRY}"
        print_info "Use your GitHub Personal Access Token as password"
        exit 1
    fi
    
    # Check Git
    if ! git rev-parse --git-dir > /dev/null 2>&1; then
        print_error "Not a git repository"
        exit 1
    fi
    
    # Check GitHub CLI (optional)
    if command -v gh &>/dev/null; then
        print_success "GitHub CLI (gh) is available"
        HAS_GH=true
    else
        print_warning "GitHub CLI (gh) not found. Release will be created manually."
        HAS_GH=false
    fi
    
    print_success "All checks passed"
}

# Get version from user
get_version() {
    # Get current version from git tags
    local current_version=$(git describe --tags --abbrev=0 2>/dev/null || echo "v0.0.0")
    
    echo ""
    echo "Current version: ${current_version}"
    echo ""
    
    if [ -n "$1" ]; then
        VERSION="$1"
        print_info "Using provided version: ${VERSION}"
    else
        read -p "Enter new version (e.g., v1.2.3): " VERSION
        if [ -z "$VERSION" ]; then
            print_error "Version cannot be empty"
            exit 1
        fi
    fi
    
    # Validate version format
    if [[ ! "$VERSION" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
        print_warning "Version should be in format 'vX.Y.Z' (e.g., v1.2.3)"
        read -p "Continue anyway? [y/N]: " confirm
        if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
    
    # Check if tag already exists
    if git rev-parse "${VERSION}" >/dev/null 2>&1; then
        print_error "Tag ${VERSION} already exists"
        exit 1
    fi
}

# Generate release notes
generate_release_notes() {
    local version="$1"
    local output_file="${2:-RELEASE_NOTES.md}"
    
    print_info "Generating release notes..."
    
    # Get commits since last tag
    local last_tag=$(git describe --tags --abbrev=0 2>/dev/null || echo "")
    local commit_range=""
    
    if [ -n "$last_tag" ]; then
        commit_range="${last_tag}..HEAD"
    fi
    
    cat > "$output_file" <<EOF
# Agent Kernel ${version}

## Docker Image
\`\`\`
docker pull ${GHCR_IMAGE}:${version}
docker pull ${GHCR_IMAGE}:latest
\`\`\`

## Quick Start
\`\`\`bash
# Pull and run
docker run -d \\
  --name agent-kernel \\
  -p 3000:3000 \\
  -p 8000:8000 \\
  -e LLM_PROVIDER=ark \\
  -e ARK_API_KEY=your-api-key \\
  ${GHCR_IMAGE}:${version}
\`\`\`

## Changes
EOF

    # Add recent commits
    if [ -n "$commit_range" ]; then
        echo "" >> "$output_file"
        git log "$commit_range" --pretty=format:"- %s (%h)" --no-merges >> "$output_file"
        echo "" >> "$output_file"
    else
        echo "" >> "$output_file"
        echo "_Initial release_" >> "$output_file"
        echo "" >> "$output_file"
    fi
    
    print_success "Release notes generated: ${output_file}"
}

# Build and push image
build_and_push() {
    local version="$1"
    
    print_info "Building image for version: ${version}"
    
    # Check if buildx is available
    if docker buildx version >/dev/null 2>&1; then
        print_success "Using Docker Buildx for multi-platform build"
        
        # Create builder if needed
        if ! docker buildx inspect agent-kernel-builder >/dev/null 2>&1; then
            docker buildx create --name agent-kernel-builder --use
        fi
        
        # Build and push
        docker buildx build \
            --platform linux/amd64 \
            --tag "${GHCR_IMAGE}:${version}" \
            --tag "${GHCR_IMAGE}:latest" \
            --file "${DOCKERFILE}" \
            --push \
            "${BUILD_CONTEXT}"
    else
        print_warning "Buildx not available, using standard build"
        
        # Build locally
        docker build \
            --tag "${GHCR_IMAGE}:${version}" \
            --tag "${GHCR_IMAGE}:latest" \
            --file "${DOCKERFILE}" \
            "${BUILD_CONTEXT}"
        
        # Push
        docker push "${GHCR_IMAGE}:${version}"
        docker push "${GHCR_IMAGE}:latest"
    fi
    
    print_success "Image pushed to: ${GHCR_IMAGE}:${version}"
}

# Create Git tag
create_git_tag() {
    local version="$1"
    
    print_info "Creating git tag: ${version}"
    
    # Check if working directory is clean
    if ! git diff-index --quiet HEAD --; then
        print_warning "Working directory is not clean"
        git status --short
        echo ""
        read -p "Continue anyway? [y/N]: " confirm
        if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi
    
    # Create annotated tag
    git tag -a "$version" -m "Release ${version}"
    
    print_success "Git tag created: ${version}"
    print_info "To push tag, run: git push origin ${version}"
    
    read -p "Push tag to remote now? [Y/n]: " push_now
    if [[ ! "$push_now" =~ ^[Nn]$ ]]; then
        git push origin "$version"
        print_success "Tag pushed to remote"
    fi
}

# Create GitHub release
create_github_release() {
    local version="$1"
    local notes_file="$2"
    
    if [ "$HAS_GH" = false ]; then
        print_warning "GitHub CLI not available, skipping automatic release creation"
        print_info "Please create release manually on GitHub:"
        print_info "  https://github.com/${GITHUB_REPO}/releases/new"
        return 0
    fi
    
    print_info "Creating GitHub release..."
    
    # Check if already authenticated
    if ! gh auth status >/dev/null 2>&1; then
        print_warning "Not authenticated with GitHub CLI"
        gh auth login
    fi
    
    # Create release
    gh release create "$version" \
        --title "Agent Kernel ${version}" \
        --notes-file "$notes_file" \
        --draft
    
    print_success "GitHub release created (draft)"
    print_info "Please review and publish at: https://github.com/${GITHUB_REPO}/releases"
}

# Verify release
verify_release() {
    local version="$1"
    
    print_info "Verifying release..."
    
    # Check image exists
    if ! docker manifest inspect "${GHCR_IMAGE}:${version}" >/dev/null 2>&1; then
        print_error "Image not found in registry: ${GHCR_IMAGE}:${version}"
        return 1
    fi
    
    print_success "Image verified: ${GHCR_IMAGE}:${version}"
    
    # Show image info
    echo ""
    print_info "Release Summary:"
    echo "  Version:      ${version}"
    echo "  Image:        ${GHCR_IMAGE}:${version}"
    echo "  Registry:     ${GHCR_REGISTRY}"
    echo "  Git Tag:      ${version}"
    echo ""
    echo "Pull command:"
    echo "  docker pull ${GHCR_IMAGE}:${version}"
    echo ""
}

# Show help
show_help() {
    echo "Agent Kernel Release Script"
    echo ""
    echo "Usage: $0 [OPTIONS] [VERSION]"
    echo ""
    echo "Options:"
    echo "  -d, --dry-run       Build without pushing"
    echo "  -s, --skip-build    Skip building, just create tag and release"
    echo "  -h, --help          Show this help"
    echo ""
    echo "Examples:"
    echo "  $0                  # Interactive mode"
    echo "  $0 v1.2.3          # Release specific version"
    echo "  $0 --dry-run       # Test build without pushing"
}

# Main
main() {
    print_header
    
    # Parse arguments
    local dry_run=false
    local skip_build=false
    
    while [[ $# -gt 0 ]]; do
        case $1 in
            -d|--dry-run)
                dry_run=true
                shift
                ;;
            -s|--skip-build)
                skip_build=true
                shift
                ;;
            -h|--help)
                show_help
                exit 0
                ;;
            -*)
                print_error "Unknown option: $1"
                show_help
                exit 1
                ;;
            *)
                break
                ;;
        esac
    done
    
    # Change to project root
    cd "$(dirname "$0")/.."
    
    # Check dependencies
    check_deps
    
    # Get version
    get_version "$1"
    
    # Generate release notes
    local notes_file="/tmp/agent-kernel-release-${VERSION}.md"
    generate_release_notes "$VERSION" "$notes_file"
    
    # Show summary
    echo ""
    echo "Release Summary:"
    echo "  Version:  ${VERSION}"
    echo "  Image:    ${GHCR_IMAGE}:${VERSION}"
    echo "  Dry Run:  ${dry_run}"
    echo ""
    
    read -p "Continue with release? [Y/n]: " confirm
    if [[ "$confirm" =~ ^[Nn]$ ]]; then
        print_info "Cancelled"
        exit 0
    fi
    
    # Build and push
    if [ "$skip_build" = false ]; then
        if [ "$dry_run" = true ]; then
            print_info "Dry run mode - building without pushing"
            docker build --tag "${IMAGE_NAME}:${VERSION}" --file "${DOCKERFILE}" "${BUILD_CONTEXT}"
            print_success "Build completed (dry run)"
            exit 0
        else
            build_and_push "$VERSION"
        fi
    fi
    
    # Create git tag
    create_git_tag "$VERSION"
    
    # Create GitHub release
    if [ "$dry_run" = false ]; then
        create_github_release "$VERSION" "$notes_file"
        verify_release "$VERSION"
    fi
    
    # Cleanup
    rm -f "$notes_file"
    
    echo ""
    print_success "Release ${VERSION} completed! 🎉"
    echo ""
    echo "Next steps:"
    echo "  1. Review the GitHub release (if created as draft)"
    echo "  2. Test the image: docker pull ${GHCR_IMAGE}:${VERSION}"
    echo "  3. Update documentation if needed"
}

# Run
main "$@"
