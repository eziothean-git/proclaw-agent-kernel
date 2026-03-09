#!/bin/bash
# CLI 适配器演示脚本

# 设置环境变量启用 CLI 适配器
export ENABLE_CLI_ADAPTER=true
export GATEWAY_STORAGE_PATH=/tmp/gateway-test

echo "=== Gateway CLI Adapter Demo ==="
echo ""
echo "This script demonstrates how to use the CLI adapter."
echo "Expected input: JSON lines on stdin"
echo "Output: JSON responses on stdout"
echo ""
echo "Example usage:"
echo '  echo \'{"message": "Hello", "user_id": "user1"}\' | gateway-cli'
echo ""
echo "Input format:"
cat <<-'EOF'
{
  "message": "Your message here",
  "user_id": "unique-user-id",
  "session_id": "optional-session-id",
  "device_id": "optional-device-id",
  "tags": ["optional", "tags"]
}
EOF
echo ""
echo "Output format:"
cat <<-'EOF'
{
  "request_id": "uuid",
  "session_id": "uuid",
  "status": "completed",
  "response": "AI response text",
  "attachments": []
}
EOF
