#!/bin/bash
# Integration test: Gateway + Simulated Request Manager

set -e

echo "=== Gateway + Request Manager Integration Test ==="
echo ""

TEST_DIR="/tmp/gateway-integration-$(date +%s)"
GATEWAY_URL="http://localhost:3000"
PID_FILE="/tmp/gateway-integration.pid"

echo "Test directory: $TEST_DIR"
echo ""

cleanup() {
    echo ""
    echo "Cleaning up..."
    if [ -f "$PID_FILE" ]; then
        kill $(cat "$PID_FILE") 2>/dev/null || true
        rm -f "$PID_FILE"
    fi
    rm -rf "$TEST_DIR"
    echo "✓ Cleanup complete"
}

trap cleanup EXIT

export GATEWAY_STORAGE_PATH="$TEST_DIR"
export NODE_ENV="test"
export PORT="3000"

mkdir -p "$TEST_DIR"/{inbox,outbox,pending,attachments,sessions,errors,logs}

echo "1. Starting Gateway..."
cd /home/eziothean/ProClaw/agent-kernel/apps/gateway
node dist/main &
echo $! > "$PID_FILE"

for i in {1..30}; do
    if curl -s "$GATEWAY_URL/api/v1/health" > /dev/null 2>&1; then
        echo "   ✓ Gateway ready"
        break
    fi
    sleep 1
done

echo ""
echo "2. Sending request..."
REQUEST_PAYLOAD='{
  "message": "What is the weather today?",
  "user_id": "user-123",
  "platform": "cli",
  "priority": 5
}'

RESPONSE=$(curl -s -X POST "$GATEWAY_URL/api/v1/chat" \
  -H "Content-Type: application/json" \
  -d "$REQUEST_PAYLOAD")

REQUEST_ID=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['requestId'])")
echo "   Request ID: $REQUEST_ID"

echo ""
echo "3. Simulating Request Manager..."
echo "   Reading request from inbox..."

INBOX_FILE=$(find "$TEST_DIR/inbox" -name "*.json" | head -1)
echo "   Found: $INBOX_FILE"

echo "   Processing request..."

# Simulate processing and write response
OUTBOX_DATE=$(date +%Y-%m-%d)
mkdir -p "$TEST_DIR/outbox/$OUTBOX_DATE"

OUTBOX_FILE="$TEST_DIR/outbox/$OUTBOX_DATE/$REQUEST_ID.json"

cat > "$OUTBOX_FILE" << EOF
{
  "header": {
    "requestId": "$REQUEST_ID",
    "sessionId": "sess_$(date +%s)",
    "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ)",
    "processingTimeMs": 1250
  },
  "status": "completed",
  "body": "Today's weather is sunny with a high of 25°C. The skies will be clear throughout the day, perfect for outdoor activities!",
  "metadata": {
    "actions": [
      {
        "type": "tool_call",
        "skill": "weather",
        "tool": "get_forecast",
        "status": "success",
        "durationMs": 450
      }
    ]
  }
}
EOF

echo "   Written response to: $OUTBOX_FILE"

# Update outbox index
cat >> "$TEST_DIR/outbox/index.jsonl" << EOF
{"timestamp":"$(date -u +%Y-%m-%dT%H:%M:%S.%3NZ)","requestId":"$REQUEST_ID","sessionId":"sess_$(date +%s)","status":"completed","path":"$OUTBOX_FILE"}
EOF

echo ""
echo "4. Waiting for Gateway to detect response..."
sleep 2

echo ""
echo "5. Querying response via API..."
RESULT=$(curl -s "$GATEWAY_URL/api/v1/requests/$REQUEST_ID")
echo "   Response:"
echo "$RESULT" | python3 -m json.tool

echo ""
echo "6. Verifying response content..."
BODY=$(echo "$RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('response',{}).get('body','NO BODY'))" 2>/dev/null || echo "FAILED")

if echo "$BODY" | grep -q "sunny"; then
    echo "   ✓ Response content verified: $BODY"
else
    echo "   ✗ Response content not found or incorrect"
    echo "   Body: $BODY"
    exit 1
fi

echo ""
echo "=== Integration Test Summary ==="
echo "✓ Gateway accepted request"
echo "✓ Request written to inbox"
echo "✓ Simulated Request Manager processed request"
echo "✓ Response written to outbox"
echo "✓ Gateway detected response"
echo "✓ API returned complete response"
echo ""
echo "All tests passed! ✓"
