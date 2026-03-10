#!/bin/bash
#
# Agent Kernel Setup Script
# Interactive configuration for LLM API settings
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Configuration directory
CONFIG_DIR="${HOME}/.agent-kernel"
ENV_FILE="${CONFIG_DIR}/config/.env"

# Print functions
print_header() {
    echo -e "${BLUE}"
    echo "╔════════════════════════════════════════════════════════════╗"
    echo "║         Agent Kernel - Configuration Setup                 ║"
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

# Check if config exists
check_existing_config() {
    if [ -f "$ENV_FILE" ]; then
        echo ""
        print_warning "Existing configuration found!"
        echo ""
        echo "Current configuration:"
        echo "----------------------------------------"
        grep -E "^(LLM_PROVIDER|ARK_MODEL|OPENAI_MODEL)=" "$ENV_FILE" 2>/dev/null || echo "(minimal config)"
        echo "----------------------------------------"
        echo ""
        read -p "Do you want to overwrite the existing configuration? [y/N]: " overwrite
        if [[ ! "$overwrite" =~ ^[Yy]$ ]]; then
            print_info "Keeping existing configuration."
            exit 0
        fi
        echo ""
    fi
}

# Create config directory
setup_config_dir() {
    mkdir -p "${CONFIG_DIR}/config"
    mkdir -p "${CONFIG_DIR}/backups"
    print_success "Created configuration directory: ${CONFIG_DIR}"
}

# Configure LLM provider
configure_provider() {
    echo ""
    echo "Select your LLM provider:"
    echo ""
    echo "  1) Volcengine Ark (推荐，国内可用)"
    echo "  2) OpenAI (GPT-4/GPT-3.5)"
    echo "  3) Custom/OpenAI-compatible API"
    echo ""
    
    while true; do
        read -p "Enter your choice (1-3): " provider_choice
        case $provider_choice in
            1)
                LLM_PROVIDER="ark"
                print_success "Selected: Volcengine Ark"
                break
                ;;
            2)
                LLM_PROVIDER="openai"
                print_success "Selected: OpenAI"
                break
                ;;
            3)
                LLM_PROVIDER="custom"
                print_success "Selected: Custom API"
                break
                ;;
            *)
                print_error "Invalid choice. Please enter 1, 2, or 3."
                ;;
        esac
    done
}

# Configure Ark settings
configure_ark() {
    echo ""
    echo "Volcengine Ark Configuration"
    echo "----------------------------------------"
    echo ""
    echo "Don't have an API key?"
    echo "  1. Visit: https://console.volcengine.com/ark/"
    echo "  2. Create an account and generate an API key"
    echo ""
    
    while true; do
        read -s -p "Enter your Ark API key: " ark_key
        echo ""
        if [ -z "$ark_key" ]; then
            print_error "API key cannot be empty."
        else
            ARK_API_KEY="$ark_key"
            break
        fi
    done
    
    echo ""
    echo "Select model:"
    echo "  1) GLM-4-7 (默认，推荐)"
    echo "  2) GLM-4-9B"
    echo "  3) DeepSeek-R1"
    echo "  4) 其他 (手动输入)"
    echo ""
    
    read -p "Enter your choice (1-4) [1]: " model_choice
    model_choice=${model_choice:-1}
    
    case $model_choice in
        1) ARK_MODEL="glm-4-7-251222" ;;
        2) ARK_MODEL="glm-4-9b-chat" ;;
        3) ARK_MODEL="deepseek-r1-250120" ;;
        4)
            read -p "Enter model name: " ARK_MODEL
            ;;
        *) ARK_MODEL="glm-4-7-251222" ;;
    esac
    
    print_success "Selected model: $ARK_MODEL"
    
    # Optional: Custom base URL
    echo ""
    read -p "Use custom base URL? [y/N]: " custom_url
    if [[ "$custom_url" =~ ^[Yy]$ ]]; then
        read -p "Enter base URL: " ARK_BASE_URL
    else
        ARK_BASE_URL="https://ark.cn-beijing.volces.com/api/v3"
    fi
}

# Configure OpenAI settings
configure_openai() {
    echo ""
    echo "OpenAI Configuration"
    echo "----------------------------------------"
    echo ""
    echo "Don't have an API key?"
    echo "  1. Visit: https://platform.openai.com/api-keys"
    echo "  2. Create an account and generate an API key"
    echo ""
    
    while true; do
        read -s -p "Enter your OpenAI API key: " openai_key
        echo ""
        if [ -z "$openai_key" ]; then
            print_error "API key cannot be empty."
        else
            OPENAI_API_KEY="$openai_key"
            break
        fi
    done
    
    echo ""
    echo "Select model:"
    echo "  1) GPT-4 (推荐)"
    echo "  2) GPT-4 Turbo"
    echo "  3) GPT-3.5 Turbo"
    echo "  4) 其他 (手动输入)"
    echo ""
    
    read -p "Enter your choice (1-4) [1]: " model_choice
    model_choice=${model_choice:-1}
    
    case $model_choice in
        1) OPENAI_MODEL="gpt-4" ;;
        2) OPENAI_MODEL="gpt-4-turbo-preview" ;;
        3) OPENAI_MODEL="gpt-3.5-turbo" ;;
        4)
            read -p "Enter model name: " OPENAI_MODEL
            ;;
        *) OPENAI_MODEL="gpt-4" ;;
    esac
    
    print_success "Selected model: $OPENAI_MODEL"
    
    # Optional: Custom base URL (for Azure or proxies)
    echo ""
    read -p "Use custom base URL (for Azure/proxy)? [y/N]: " custom_url
    if [[ "$custom_url" =~ ^[Yy]$ ]]; then
        read -p "Enter base URL: " OPENAI_BASE_URL
    fi
}

# Configure Custom API
configure_custom() {
    echo ""
    echo "Custom API Configuration"
    echo "----------------------------------------"
    echo ""
    
    read -p "Enter API base URL: " OPENAI_BASE_URL
    read -s -p "Enter API key: " OPENAI_API_KEY
    echo ""
    read -p "Enter model name: " OPENAI_MODEL
    
    print_success "Custom API configured"
}

# Configure advanced settings
configure_advanced() {
    echo ""
    read -p "Configure advanced settings? [y/N]: " advanced
    
    if [[ "$advanced" =~ ^[Yy]$ ]]; then
        echo ""
        echo "Advanced Settings"
        echo "----------------------------------------"
        
        # Temperature
        echo ""
        echo "Temperature (控制创造性):"
        echo "  0.0 - 更确定、保守的回答"
        echo "  0.7 - 平衡 (默认)"
        echo "  1.0+ - 更有创造性"
        read -p "Enter temperature [0.7]: " temp
        LLM_TEMPERATURE=${temp:-0.7}
        
        # Max tokens
        echo ""
        echo "Max tokens (最大生成长度):"
        read -p "Enter max tokens [4000]: " tokens
        LLM_MAX_TOKENS=${tokens:-4000}
        
        # Run mode
        echo ""
        echo "Run mode:"
        echo "  1) real - 调用真实 LLM API (默认)"
        echo "  2) mock - 返回模拟响应 (测试用)"
        read -p "Enter choice (1-2) [1]: " run_mode
        case $run_mode in
            2) KERNEL_RUN_MODE="mock" ;;
            *) KERNEL_RUN_MODE="real" ;;
        esac
    else
        # Default values
        LLM_TEMPERATURE="0.7"
        LLM_MAX_TOKENS="4000"
        KERNEL_RUN_MODE="real"
    fi
}

# Save configuration
save_config() {
    echo ""
    echo "Saving configuration..."
    
    # Backup existing config if present
    if [ -f "$ENV_FILE" ]; then
        backup_file="${CONFIG_DIR}/backups/.env.$(date +%Y%m%d_%H%M%S)"
        cp "$ENV_FILE" "$backup_file"
        print_info "Backed up existing config to: $backup_file"
    fi
    
    # Write new config
    cat > "$ENV_FILE" <<EOF
# Agent Kernel Configuration
# Generated on $(date)

# LLM Provider
LLM_PROVIDER=${LLM_PROVIDER}

EOF

    # Add provider-specific settings
    case $LLM_PROVIDER in
        ark)
            cat >> "$ENV_FILE" <<EOF
# Volcengine Ark Settings
ARK_API_KEY=${ARK_API_KEY}
ARK_BASE_URL=${ARK_BASE_URL:-https://ark.cn-beijing.volces.com/api/v3}
ARK_MODEL=${ARK_MODEL:-glm-4-7-251222}

EOF
            ;;
        openai|custom)
            cat >> "$ENV_FILE" <<EOF
# OpenAI Settings
OPENAI_API_KEY=${OPENAI_API_KEY}
OPENAI_MODEL=${OPENAI_MODEL}
EOF
            if [ -n "$OPENAI_BASE_URL" ]; then
                echo "OPENAI_BASE_URL=${OPENAI_BASE_URL}" >> "$ENV_FILE"
            fi
            echo "" >> "$ENV_FILE"
            ;;
    esac
    
    # Add common settings
    cat >> "$ENV_FILE" <<EOF
# LLM Settings
LLM_TEMPERATURE=${LLM_TEMPERATURE:-0.7}
LLM_MAX_TOKENS=${LLM_MAX_TOKENS:-4000}

# Run Mode
KERNEL_RUN_MODE=${KERNEL_RUN_MODE:-real}

# Optional: Gateway Settings (uncomment to customize)
# GATEWAY_PORT=3000
# PYTHON_KERNEL_PORT=8000
# LOG_LEVEL=INFO
EOF

    chmod 600 "$ENV_FILE"
    print_success "Configuration saved to: $ENV_FILE"
}

# Verify configuration
verify_config() {
    echo ""
    echo "Configuration Summary"
    echo "----------------------------------------"
    echo "Provider:    $LLM_PROVIDER"
    
    case $LLM_PROVIDER in
        ark)
            echo "Model:       $ARK_MODEL"
            echo "Base URL:    $ARK_BASE_URL"
            ;;
        openai|custom)
            echo "Model:       $OPENAI_MODEL"
            [ -n "$OPENAI_BASE_URL" ] && echo "Base URL:    $OPENAI_BASE_URL"
            ;;
    esac
    
    echo "Temperature: $LLM_TEMPERATURE"
    echo "Max Tokens:  $LLM_MAX_TOKENS"
    echo "Run Mode:    $KERNEL_RUN_MODE"
    echo ""
    
    read -p "Is this correct? [Y/n]: " confirm
    if [[ "$confirm" =~ ^[Nn]$ ]]; then
        print_warning "Setup cancelled. Please run the script again."
        exit 1
    fi
}

# Main function
main() {
    print_header
    
    # Check if running in Docker
    if [ -f /.dockerenv ]; then
        print_error "This script should be run on the host, not inside Docker."
        exit 1
    fi
    
    # Check dependencies
    if ! command -v docker &>/dev/null; then
        print_error "Docker is not installed. Please install Docker first."
        exit 1
    fi
    
    check_existing_config
    setup_config_dir
    configure_provider
    
    # Configure based on provider
    case $LLM_PROVIDER in
        ark) configure_ark ;;
        openai) configure_openai ;;
        custom) configure_custom ;;
    esac
    
    configure_advanced
    verify_config
    save_config
    
    echo ""
    print_success "Setup complete! 🎉"
    echo ""
    echo "Next steps:"
    echo "  1. Build the image:   ./scripts/build.sh"
    echo "  2. Start the service: ./scripts/start.sh"
    echo ""
    echo "Configuration file: $ENV_FILE"
    echo ""
    print_info "To modify settings later, run: ./scripts/setup.sh"
}

# Run main function
main "$@"
