# Work Plan: Gateway-to-Prime Information Flow Verification

## Current Status
- ✅ Rust backend builds successfully (release binary)
- ✅ Prime Personality gRPC service implemented
- ❌ Service cannot start due to incomplete config file
- ⏳ End-to-end integration not yet tested

## Blocker Identified

The `config/composer.yaml.example` file is **incomplete**. It only contains:
- `server` section (partial)
- `cache` section (partial)
- `observability.metrics` section (partial)

**Missing required sections:**
- `providers.bash` - Bash provider configuration
- `providers.code` - Code index configuration  
- `providers.memory` - Memory provider configuration
- `permissions` - Token and policy configuration
- `observability.traces` - Trace retention and compression settings
- `observability.audit` - Audit log configuration
- `observability.logging` - Logging configuration

## Tasks to Complete

### Task 1: Create Valid Configuration File
**Location:** `kernel-v2/config/composer.yaml`

**Required content structure:**
```yaml
server:
  socket_path: "./data/composer.sock"
  workers: 2
  max_concurrent_requests: 50
  request_timeout_seconds: 30

cache:
  l1:
    max_entries: 100
    default_ttl_seconds:
      prime: 300
      session: 120
      task: 30
  l2:
    path: "./data/cache.db"
    max_size_mb: 100
    compression: "zstd"

providers:
  bash:
    timeout_seconds: 30
    max_output_size: 100000
    blocked_commands:
      - "rm -rf /"
      - "mkfs"
      - "dd if=/dev/zero"
    patterns_file: "./data/bash_patterns.yaml"
  
  code:
    index:
      database_path: "./data/code_index.db"
      update_interval_seconds: 300
      paths: []
  
  memory:
    database_path: "./data/memory.db"
    max_facts_per_query: 50
    default_categories:
      - "general"

permissions:
  default_token_ttl_seconds: 3600
  default_max_calls: 100
  policy_file: "./data/policies.yaml"

observability:
  metrics:
    enabled: true
    port: 9090
    path: "/metrics"
  
  traces:
    base_path: "./data/traces"
    retention_days: 30
    compress_after_hours: 24
    compression_algorithm: "zstd"
    compression_level: 3
  
  audit:
    path: "./data/audit.log"
    level: "info"
  
  logging:
    level: "info"
    format: "json"
    output: "stdout"
```

### Task 2: Start Prime Personality Service
**Command:**
```bash
cd kernel-v2
./target/release/proclaw-composer \
  --config ./config/composer.yaml \
  --data-dir ./data \
  --llm-api-key "${OPENAI_API_KEY:-sk-test-dummy}"
```

**Verify:**
- Service starts without errors
- gRPC server binds to port 50051
- Unix socket created at `./data/composer.sock`

### Task 3: Test gRPC Endpoint
**Tool:** grpcurl or similar

**Test command:**
```bash
# Check if service is listening
ss -tlnp | grep 50051

# Test with grpcurl (if available)
grpcurl -plaintext localhost:50051 list

# Or test with netcat/telnet
nc -zv localhost 50051
```

### Task 4: End-to-End Integration Test
**Components to verify:**
1. TypeScript Request Manager connects to Rust Prime Personality
2. ProcessRequest message is sent successfully
3. Prime Personality processes the request (BlockComposer → LLM → IR)
4. IR result is sent back via Skill call (os_interface.submit_ir_result)
5. Result reaches Gateway

**Test scenario:**
```typescript
// From TypeScript request-manager
const response = await primeClient.processRequest({
  request_id: "test-001",
  user_id: "user-001", 
  input_message: {
    header: {
      message_id: "msg-001",
      timestamp: Date.now(),
      source: "test"
    },
    content: {
      text: "Hello, this is a test message"
    }
  },
  process_definition: {
    goal: "Test end-to-end flow",
    scope: "test"
  }
});
```

### Task 5: Verify IR Result Flow
**Check:**
- Prime Personality generates IR via BlockComposer
- IR is sent via `os_interface.submit_ir_result` Skill call
- Skill registry routes the call correctly
- Result is returned to Gateway

**Verification points:**
1. PrimePersonalityService receives ProcessRequest
2. Calls PrimePersonalityCore.process_request()
3. BlockComposer assembles context
4. LLM generates IR
5. Service calls send_ir_to_gateway()
6. SkillRegistry executes os_interface.submit_ir_result
7. OSInterfaceSkill handles the call

## Information Flow Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         Gateway (TypeScript)                      │
│                         Port: 3000 (HTTP)                         │
└───────────────────────────────┬───────────────────────────────────┘
                                │ HTTP / gRPC
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│                   Request Manager (TypeScript)                    │
│                   Port: 50051 (gRPC client)                       │
└───────────────────────────────┬───────────────────────────────────┘
                                │ gRPC ProcessRequest
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│              Prime Personality Service (Rust)                     │
│              Port: 50051 (gRPC server)                            │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ PrimePersonalityService (gRPC wrapper)                  │   │
│  │ - Receives ProcessRequest                               │   │
│  │ - Converts proto → internal types                       │   │
│  │ - Calls PrimePersonalityCore                            │   │
│  │ - Sends result via Skill call                           │   │
│  └─────────────────────────┬───────────────────────────────┘   │
│                            │                                    │
│                            ▼                                    │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │ PrimePersonalityCore (Agent logic)                      │   │
│  │ - Uses BlockComposer for context                        │   │
│  │ - Calls LLM via LLMRouter                               │   │
│  │ - Generates IntermediateRepresentation                  │   │
│  └─────────────────────────┬───────────────────────────────┘   │
│                            │                                    │
└────────────────────────────┼────────────────────────────────────┘
                             │ Skill call
                             ▼
┌─────────────────────────────────────────────────────────────────┐
│              OS Interface Skill (Rust)                            │
│              via SkillRegistry                                    │
│                                                                 │
│  - Receives submit_ir_result call                                 │
│  - Returns result to Gateway                                      │
└─────────────────────────────────────────────────────────────────┘
```

## Success Criteria

- [ ] Config file created and service starts successfully
- [ ] Prime Personality gRPC server binds to port 50051
- [ ] TypeScript client can connect and send ProcessRequest
- [ ] Request is processed through BlockComposer → LLM → IR
- [ ] IR result is sent back via Skill call
- [ ] End-to-end latency < 5 seconds (excluding LLM call)

## Commands for Execution

```bash
# 1. Create config file (manual step - cannot be automated by Prometheus)
cat > kernel-v2/config/composer.yaml << 'EOF'
[config content from Task 1]
EOF

# 2. Start service
cd kernel-v2
RUST_LOG=info ./target/release/proclaw-composer \
  --config ./config/composer.yaml \
  --data-dir ./data \
  --llm-api-key "$OPENAI_API_KEY"

# 3. Verify port binding (in another terminal)
ss -tlnp | grep 50051

# 4. Test with grpcurl
grpcurl -plaintext localhost:50051 list
grpcurl -plaintext localhost:50051 describe prime_personality.PrimePersonality
```

## Next Steps

1. **Immediate**: Create the config file with all required sections
2. **Start service**: Run the binary with proper config
3. **Verify binding**: Check port 50051 is listening
4. **Integration test**: Connect TypeScript frontend
5. **Flow verification**: Trace a request end-to-end

Run `/start-work` to execute this plan with Sisyphus.
