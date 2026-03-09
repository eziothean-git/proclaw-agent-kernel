#!/bin/bash
# Gateway + Request Manager 集成测试脚本

set -e

echo "=== Gateway + Request Manager 集成测试 ==="
echo ""

# 配置
GATEWAY_URL="http://localhost:3000"
STORAGE_PATH="${GATEWAY_STORAGE_PATH:-/tmp/gateway-test}"

# 清理之前的测试数据
echo "1. 清理测试数据..."
rm -rf "$STORAGE_PATH"
mkdir -p "$STORAGE_PATH"/{inbox,outbox,pending,attachments}
echo "   ✓ 已清理: $STORAGE_PATH"

# 检查 Gateway 是否运行
echo ""
echo "2. 检查 Gateway 服务..."
if curl -s "$GATEWAY_URL/api/v1/health" > /dev/null 2>&1; then
    echo "   ✓ Gateway 正在运行"
else
    echo "   ✗ Gateway 未启动"
    echo "   请先运行: cd apps/gateway && npm run start:dev"
    exit 1
fi

# 发送测试请求
echo ""
echo "3. 发送测试请求..."

REQUEST_PAYLOAD='{
  "message": "你好，这是一个测试消息",
  "user_id": "test-user-001",
  "platform": "cli",
  "priority": 0
}'

RESPONSE=$(curl -s -X POST "$GATEWAY_URL/api/v1/chat" \
  -H "Content-Type: application/json" \
  -d "$REQUEST_PAYLOAD")

REQUEST_ID=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['requestId'])" 2>/dev/null || echo "")

if [ -z "$REQUEST_ID" ]; then
    echo "   ✗ 发送失败"
    echo "   响应: $RESPONSE"
    exit 1
fi

echo "   ✓ 请求已发送"
echo "   Request ID: $REQUEST_ID"

# 检查 inbox
echo ""
echo "4. 检查 inbox..."
sleep 0.5
INBOX_FILES=$(find "$STORAGE_PATH/inbox" -name "*.json" 2>/dev/null | wc -l)
if [ "$INBOX_FILES" -gt 0 ]; then
    echo "   ✓ 请求已写入 inbox ($INBOX_FILES 个文件)"
    
    # 显示请求内容
    LATEST_REQUEST=$(find "$STORAGE_PATH/inbox" -name "*.json" -type f -printf '%T@ %p\n' | sort -n | tail -1 | cut -d' ' -f2-)
    if [ -f "$LATEST_REQUEST" ]; then
        echo "   请求文件: $LATEST_REQUEST"
        echo "   内容预览:"
        cat "$LATEST_REQUEST" | python3 -m json.tool 2>/dev/null | head -20 || cat "$LATEST_REQUEST"
    fi
else
    echo "   ✗ inbox 为空"
fi

# 启动 Request Manager（如果在独立终端运行）
echo ""
echo "5. Request Manager 检查..."
echo "   请确保 Request Manager 正在运行:"
echo "   cd apps/request-manager && python3 request_manager.py"
echo ""
echo "   或者在另一个终端手动启动，然后按 Enter 继续..."
read -r

# 等待响应
echo ""
echo "6. 等待响应（最多 10 秒）..."
ATTEMPTS=0
MAX_ATTEMPTS=20

while [ $ATTEMPTS -lt $MAX_ATTEMPTS ]; do
    sleep 0.5
    ATTEMPTS=$((ATTEMPTS + 1))
    
    # 检查 outbox
    OUTBOX_FILES=$(find "$STORAGE_PATH/outbox" -name "*.json" 2>/dev/null | wc -l)
    
    if [ "$OUTBOX_FILES" -gt 0 ]; then
        echo "   ✓ 响应已生成 ($OUTBOX_FILES 个文件)"
        break
    fi
    
    echo "   等待中... ($ATTEMPTS/$MAX_ATTEMPTS)"
done

if [ $ATTEMPTS -eq $MAX_ATTEMPTS ]; then
    echo "   ✗ 超时，未收到响应"
    echo "   请检查 Request Manager 日志"
    exit 1
fi

# 查询响应
echo ""
echo "7. 查询响应..."
RESPONSE_DATA=$(curl -s "$GATEWAY_URL/api/v1/requests/$REQUEST_ID")

echo "   响应数据:"
echo "$RESPONSE_DATA" | python3 -m json.tool 2>/dev/null || echo "$RESPONSE_DATA"

# 检查响应文件
echo ""
echo "8. 检查响应文件..."
OUTBOX_FILE=$(find "$STORAGE_PATH/outbox" -name "*.json" -type f -printf '%T@ %p\n' | sort -n | tail -1 | cut -d' ' -f2-)
if [ -f "$OUTBOX_FILE" ]; then
    echo "   响应文件: $OUTBOX_FILE"
    echo "   内容:"
    cat "$OUTBOX_FILE" | python3 -m json.tool 2>/dev/null | head -30 || cat "$OUTBOX_FILE"
fi

# 测试完成
echo ""
echo "=== 测试完成 ==="
echo ""
echo "文件系统状态:"
echo "  Inbox:  $(find "$STORAGE_PATH/inbox" -name '*.json' 2>/dev/null | wc -l) 个文件"
echo "  Outbox: $(find "$STORAGE_PATH/outbox" -name '*.json' 2>/dev/null | wc -l) 个文件"
echo ""
echo "查看详细日志:"
echo "  tail -f $STORAGE_PATH/logs/gateway.log"
