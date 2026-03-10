#!/bin/bash
# OpenClaw TUI startup script

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Default configuration
GATEWAY_URL="${GATEWAY_URL:-http://localhost:3000}"
USER_ID="${USER_ID:-openclaw-user}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TUI_DIR="${SCRIPT_DIR}/.."

echo -e "${GREEN}🧠 OpenClaw Terminal UI${NC}"
echo "======================="
echo ""

# Check if we're in the right directory
if [ ! -f "${TUI_DIR}/pyproject.toml" ]; then
    echo -e "${RED}Error: pyproject.toml not found${NC}"
    echo "Please run this script from the clients/tui/scripts directory"
    exit 1
fi

# Check Python version
echo -n "Checking Python version... "
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
REQUIRED_VERSION="3.9"

if [ "$(printf '%s\n' "$REQUIRED_VERSION" "$PYTHON_VERSION" | sort -V | head -n1)" != "$REQUIRED_VERSION" ]; then
    echo -e "${RED}FAILED${NC}"
    echo -e "${RED}Python 3.9+ required, found $PYTHON_VERSION${NC}"
    exit 1
fi
echo -e "${GREEN}OK${NC} ($PYTHON_VERSION)"

# Check Gateway connectivity
echo -n "Checking Gateway connectivity ($GATEWAY_URL)... "
if curl -s -o /dev/null -w "%{http_code}" "${GATEWAY_URL}/api/v1/health" | grep -q "200"; then
    echo -e "${GREEN}OK${NC}"
else
    echo -e "${YELLOW}WARN${NC}"
    echo -e "${YELLOW}Warning: Gateway at $GATEWAY_URL is not responding${NC}"
    echo -e "${YELLOW}Make sure the Gateway is running before sending messages${NC}"
fi

# Install if needed
echo ""
echo "Installing dependencies (if needed)..."
cd "$TUI_DIR"
pip install -q -e . 2>/dev/null || pip install -e .

# Run TUI
echo ""
echo -e "${GREEN}Starting OpenClaw TUI...${NC}"
echo "Gateway: $GATEWAY_URL"
echo "User: $USER_ID"
echo ""

exec python -m openclaw_tui.main --url "$GATEWAY_URL" --user "$USER_ID" "$@"
