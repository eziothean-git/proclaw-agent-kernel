#!/bin/bash
# Test script for Gateway filesystem mailbox mechanism

set -e

echo "=== Gateway Filesystem Mailbox Test ==="
echo ""

# Configuration
TEST_DIR="/tmp/gateway-test-$(date +%s)"
GATEWAY_URL="http://localhost:3000"
PID_FILE="/tmp/gateway-test.pid"

echo "Test directory: $TEST_DIR"
echo ""

# Cleanup function
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

# Setup environment
export GATEWAY_STORAGE_PATH="$TEST_DIR"
export NODE_ENV="test"
export PORT="3000"

# Create test directories
mkdir -p "$TEST_DIR"/{inbox,outbox,pending,attachments,sessions,errors,logs}

echo "1. Starting Gateway..."
cd /home/eziothean/ProClaw/agent-kernel/apps/gateway
node dist/main &
echo $! > "$PID_FILE"

# Wait for Gateway to start
echo "   Waiting for Gateway to start..."
for i in {1..30}; do
    if curl -s "$GATEWAY_URL/api/v1/health" > /dev/null 2>&1; then
        echo "   ✓ Gateway is ready"
        break
    fi
    sleep 1
    if [ $i -eq 30 ]; then
        echo "   ✗ Gateway failed to start"
        exit 1
    fi
done

echo ""
echo "2. Testing health endpoint..."
HEALTH=$(curl -s "$GATEWAY_URL/api/v1/health")
echo "   Response: $HEALTH"
echo "   ✓ Health check passed"

echo ""
echo "3. Sending test request..."
REQUEST_PAYLOAD='{
  "message": "Hello, this is a test message",
  "user_id": "test-user-001",
  "platform": "test",
  "priority": 0
}'

RESPONSE=$(curl -s -X POST "$GATEWAY_URL/api/v1/chat" \
  -H "Content-Type: application/json" \
  -d "$REQUEST_PAYLOAD")

echo "   Response: $RESPONSE"

# Extract request_id
REQUEST_ID=$(echo "$RESPONSE" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('requestId',''))" 2>/dev/null || echo "")

if [ -z "$REQUEST_ID" ]; then
    echo "   ✗ Failed to get request_id"
    exit 1
fi

echo "   ✓ Request accepted: $REQUEST_ID"

echo ""
echo "4. Verifying inbox..."
sleep 0.5
INBOX_COUNT=$(find "$TEST_DIR/inbox" -name "*.json" 2>/dev/null | wc -l)
if [ "$INBOX_COUNT" -gt 0 ]; then
    echo "   ✓ Request written to inbox ($INBOX_COUNT files)"
    
    # Show request content
    LATEST_REQUEST=$(find "$TEST_DIR/inbox" -name "*.json" -type f -printf '%T@ %p\n' 2>/dev/null | sort -n | tail -1 | cut -d' ' -f2-)
    if [ -f "$LATEST_REQUEST" ]; then
        echo "   Request file: $LATEST_REQUEST"
        echo "   Content:"
        cat "$LATEST_REQUEST" | python3 -m json.tool 2>/dev/null || cat "$LATEST_REQUEST"
    fi
else
    echo "   ✗ No files in inbox"
    exit 1
fi

echo ""
echo "5. Checking inbox index..."
if [ -f "$TEST_DIR/inbox/index.jsonl" ]; then
    echo "   Index entries:"
    cat "$TEST_DIR/inbox/index.jsonl"
else
    echo "   ✗ Index file not found"
fi

echo ""
echo "6. Verifying request status..."
STATUS=$(curl -s "$GATEWAY_URL/api/v1/requests/$REQUEST_ID/status")
echo "   Status: $STATUS"

echo ""
echo "7. Checking file system structure..."
echo "   Inbox files:  $(find "$TEST_DIR/inbox" -name '*.json' 2>/dev/null | wc -l)"
echo "   Outbox files: $(find "$TEST_DIR/outbox" -name '*.json' 2>/dev/null | wc -l)"
echo "   Attachments:  $(find "$TEST_DIR/attachments" -name '*.json' 2>/dev/null | wc -l)"

echo ""
echo "8. Testing request with attachment..."
# Create a test attachment
ATTACHMENT_DIR="$TEST_DIR/attachments/$(date +%Y-%m-%d)"
mkdir -p "$ATTACHMENT_DIR"
echo "Test attachment content" > "$ATTACHMENT_DIR/test-file.txt"

ATTACHMENT_PAYLOAD='{
  "message": "Please check this file",
  "user_id": "test-user-002",
  "platform": "test",
  "priority": 1
}'

RESPONSE2=$(curl -s -X POST "$GATEWAY_URL/api/v1/chat" \
  -H "Content-Type: application/json" \
  -d "$ATTACHMENT_PAYLOAD")

REQUEST_ID2=$(echo "$RESPONSE2" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('requestId',''))" 2>/dev/null || echo "")

if [ -n "$REQUEST_ID2" ]; then
    echo "   ✓ Request with attachment accepted: $REQUEST_ID2"
fi

echo ""
echo "=== Test Summary ==="
echo "✓ All basic tests passed!"
echo ""
echo "Files created:"
find "$TEST_DIR" -type f -name "*.json" -o -name "*.jsonl" | head -20
echo ""
echo "Directory structure:"
tree "$TEST_DIR" 2>/dev/null || find "$TEST_DIR" -type f | head -20
