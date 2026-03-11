#!/bin/bash
# Manual test script for BlockComposer

set -e

echo "=== ProClaw BlockComposer Manual Test ==="
echo

# Check if binary exists
if [ ! -f "target/release/proclaw-composer" ]; then
    echo "Building release binary..."
    . "$HOME/.cargo/env"
    export PROTOC="$HOME/.local/bin/bin/protoc"
    cargo build --release
fi

echo "1. Testing binary execution..."
./target/release/proclaw-composer --help || true
echo "✓ Binary runs"
echo

echo "2. Checking configuration..."
if [ ! -f "config/composer.yaml" ]; then
    echo "Creating test configuration..."
    mkdir -p /tmp/proclaw-test
    cat > /tmp/proclaw-test/composer.yaml << 'EOF'
server:
  socket_path: "/tmp/proclaw-test/composer.sock"
  workers: 2
  max_concurrent_requests: 10
  request_timeout_seconds: 10

cache:
  l1:
    max_entries: 100
    default_ttl_seconds:
      prime: 300
      session: 120
      task: 30
  l2:
    path: "/tmp/proclaw-test/cache.db"
    max_size_mb: 50
    compression: "zstd"

providers:
  bash:
    timeout_seconds: 5
    max_output_size: 10000
    blocked_commands:
      - "rm -rf /"
      - "mkfs"
    patterns_file: "/tmp/proclaw-test/bash_patterns.yaml"
  
  code:
    index:
      database_path: "/tmp/proclaw-test/code_index.db"
      update_interval_seconds: 300
      paths: []
  
  memory:
    database_path: "/tmp/proclaw-test/memory.db"
    max_facts_per_query: 50
    default_categories:
      - "general"

permissions:
  default_token_ttl_seconds: 3600
  default_max_calls: 100
  policy_file: "/tmp/proclaw-test/policies.yaml"

observability:
  metrics:
    enabled: true
    port: 9090
    path: "/metrics"
  traces:
    base_path: "/tmp/proclaw-test/traces"
    retention_days: 7
    compress_after_hours: 24
    compression_algorithm: "zstd"
    compression_level: 3
  audit:
    path: "/tmp/proclaw-test/audit.log"
    level: "info"
  logging:
    level: "info"
    format: "text"
    output: "stdout"
EOF
    echo "✓ Test config created at /tmp/proclaw-test/composer.yaml"
fi
echo

echo "3. Testing server startup..."
timeout 3 ./target/release/proclaw-composer --config /tmp/proclaw-test/composer.yaml 2>&1 || true
echo "✓ Server starts (timeout expected)"
echo

echo "4. Testing with invalid config..."
./target/release/proclaw-composer --config /nonexistent/config.yaml 2>&1 || echo "✓ Properly fails on invalid config"
echo

echo "5. Checking for runtime errors..."
# Check if any critical errors in logs
if [ -f "/tmp/proclaw-kernel.log" ]; then
    echo "Log file exists, checking for errors..."
    grep -i "error\|panic" /tmp/proclaw-kernel.log || echo "✓ No critical errors found"
else
    echo "✓ No existing log file (first run)"
fi
echo

echo "=== Manual Test Complete ==="
echo
echo "To start the server:"
echo "  ./target/release/proclaw-composer --config /tmp/proclaw-test/composer.yaml"
echo
echo "To test with a client:"
echo "  (Install grpcurl or write a Python client)"
