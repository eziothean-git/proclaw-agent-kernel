# Work Plan: Complete Request Manager → Prime → Gateway Flow

## Overview

Implement the missing Gateway Skill (SendReply) to complete the end-to-end information flow from Request Manager through Prime Personality back to Gateway via HTTP webhook.

**Current State:** Components implemented but Gateway Skill missing  
**Target State:** Complete flow with Prime calling Gateway Skill to submit IR via HTTP

## Architecture

```
Request Manager (TypeScript)
    ↓ gRPC ProcessRequest
Prime Personality Service (Rust)
    ↓ Internal call
Prime Personality Core (Rust)
    ↓ BlockComposer → LLM
IR Generated
    ↓ Skill call: gateway.send_ir_result
Gateway Skill (Rust)
    ↓ HTTP POST
Gateway Webhook (TypeScript)
    ↓ Compile IR
User receives response
```

## Task Breakdown

### Wave 1: Gateway Skill Implementation

#### Task 1.1: Create Gateway Skill Module
**File:** `kernel-v2/src/skills/gateway_skill.rs` (new)

**Implementation:**
```rust
//! Gateway Skill - Send IR back to Gateway via HTTP webhook
//! 
//! Permission: Prime only
//! 
//! Tools:
//! - send_ir_result: Submit IR to Gateway webhook

use std::sync::Arc;
use serde_json::json;
use tracing::{info, instrument};
use reqwest::Client;

use crate::auth::CapabilityLevel;
use crate::coordinator::models::{SkillContext, SkillResult};

pub struct GatewaySkill {
    client: Client,
    gateway_url: String,
    auth_token: String,
}

pub struct ToolDefinition {
    pub name: String,
    pub description: String,
    pub parameters: serde_json::Value,
}

impl GatewaySkill {
    pub fn new(gateway_url: String, auth_token: String) -> Self {
        Self {
            client: Client::new(),
            gateway_url,
            auth_token,
        }
    }
    
    pub fn name(&self) -> &str {
        "gateway"
    }
    
    pub fn list_tools(&self) -> Vec<ToolDefinition> {
        vec![
            ToolDefinition {
                name: "send_ir_result".to_string(),
                description: "Send Intermediate Representation result back to Gateway".to_string(),
                parameters: json!({
                    "type": "object",
                    "properties": {
                        "ir": {
                            "type": "object",
                            "description": "Intermediate Representation with header and body"
                        },
                        "request_id": {
                            "type": "string",
                            "description": "Original request ID"
                        }
                    },
                    "required": ["ir", "request_id"]
                }),
            },
        ]
    }
    
    /// Check permission - Gateway Skill requires Prime level
    fn check_permission(&self, context: &SkillContext) -> Option<SkillResult> {
        if context.capability_level < CapabilityLevel::Prime {
            return Some(SkillResult {
                request_id: context.thread_id.clone(),
                success: false,
                result: None,
                error: Some("Permission denied: Gateway skill requires Prime level".to_string()),
                execution_time_ms: 0,
            });
        }
        None
    }
    
    /// Execute tool
    #[instrument(skip(self, params, context), fields(tool = %tool_name))]
    pub async fn execute(
        &self,
        tool_name: &str,
        params: serde_json::Value,
        context: SkillContext,
    ) -> anyhow::Result<SkillResult> {
        // Check permission
        if let Some(result) = self.check_permission(&context) {
            return Ok(result);
        }
        
        let start = std::time::Instant::now();
        
        let result = match tool_name {
            "send_ir_result" => self.send_ir_result(params).await,
            _ => {
                return Ok(SkillResult {
                    request_id: context.thread_id.clone(),
                    success: false,
                    result: None,
                    error: Some(format!("Unknown tool: {}", tool_name)),
                    execution_time_ms: start.elapsed().as_millis() as u64,
                });
            }
        };
        
        match result {
            Ok(result_json) => Ok(SkillResult {
                request_id: context.thread_id.clone(),
                success: true,
                result: Some(result_json),
                error: None,
                execution_time_ms: start.elapsed().as_millis() as u64,
            }),
            Err(e) => Ok(SkillResult {
                request_id: context.thread_id.clone(),
                success: false,
                result: None,
                error: Some(e.to_string()),
                execution_time_ms: start.elapsed().as_millis() as u64,
            }),
        }
    }
    
    /// Send IR result to Gateway webhook
    async fn send_ir_result(&self, params: serde_json::Value) -> anyhow::Result<serde_json::Value> {
        let ir = params.get("ir")
            .ok_or_else(|| anyhow::anyhow!("Missing 'ir' parameter"))?;
        let request_id = params.get("request_id")
            .and_then(|v| v.as_str())
            .ok_or_else(|| anyhow::anyhow!("Missing 'request_id' parameter"))?;
        
        let webhook_url = format!("{}/gateway/webhook/kernel-response", self.gateway_url);
        
        info!(
            request_id = %request_id,
            url = %webhook_url,
            "Sending IR to Gateway webhook"
        );
        
        let response = self.client
            .post(&webhook_url)
            .header("Authorization", format!("Bearer {}", self.auth_token))
            .header("Content-Type", "application/json")
            .json(&json!({
                "request_id": request_id,
                "ir": ir,
                "timestamp": chrono::Utc::now().to_rfc3339(),
            }))
            .send()
            .await?;
        
        let status = response.status();
        let body = response.text().await?;
        
        if status.is_success() {
            info!(
                request_id = %request_id,
                status = %status,
                "Successfully sent IR to Gateway"
            );
            Ok(json!({
                "success": true,
                "gateway_status": status.as_u16(),
                "gateway_response": body,
            }))
        } else {
            Err(anyhow::anyhow!(
                "Gateway webhook failed: {} - {}",
                status,
                body
            ))
        }
    }
}
```

**QA Scenarios:**
- Happy path: IR sent successfully, returns 200 OK
- Error case: Gateway returns 4xx/5xx, proper error handling
- Auth case: Invalid token, returns 401/403

#### Task 1.2: Update skills/mod.rs
**File:** `kernel-v2/src/skills/mod.rs`

Add GatewaySkill to module exports.

#### Task 1.3: Register Gateway Skill in SkillRegistry
**File:** `kernel-v2/src/coordinator/skill_registry.rs`

Add GatewaySkill registration method and execution routing.

### Wave 2: Configuration & Integration

#### Task 2.1: Add Gateway URL and Auth Token to Config
**File:** `kernel-v2/src/config.rs`

Add:
```rust
pub struct GatewayConfig {
    pub url: String,
    pub auth_token: String,
    pub webhook_path: String,
}
```

#### Task 2.2: Initialize Gateway Skill in main.rs
**File:** `kernel-v2/src/main.rs`

- Create GatewaySkill instance
- Register with SkillRegistry
- Pass to PrimePersonalityService

#### Task 2.3: Update PrimePersonalityService
**File:** `kernel-v2/src/server/prime_personality_server.rs`

Change `send_ir_to_gateway()` to use `gateway` skill instead of `os_interface`.

### Wave 3: TypeScript Integration (Optional for now)

#### Task 3.1: Update Worker Pool to use gRPC
**File:** `agent-kernel/apps/request-manager/src/services/worker-pool.service.ts`

Replace HTTP API call with gRPC call using PrimePersonalityClient.

**Alternative:** Keep HTTP API for now and create compatibility layer later.

### Wave 4: Testing

#### Task 4.1: Unit Tests
- Test GatewaySkill with mock HTTP server
- Test authentication validation
- Test error handling

#### Task 4.2: Integration Test
Start full flow:
1. Submit request to Request Manager
2. Verify Prime Personality receives it
3. Verify IR is generated
4. Verify Gateway Skill sends HTTP POST
5. Verify Gateway webhook receives IR

## Configuration Template

Create `kernel-v2/config/composer.yaml`:

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

gateway:
  url: "http://localhost:3000"
  auth_token: "${GATEWAY_AUTH_TOKEN:-default-token-change-in-production}"
  webhook_path: "/gateway/webhook/kernel-response"

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

## Environment Variables

```bash
# Required
export GATEWAY_AUTH_TOKEN="your-secret-token"
export OPENAI_API_KEY="sk-..."

# Optional
export GATEWAY_URL="http://localhost:3000"
export RUST_LOG="info"
```

## Commands

```bash
# Build
cd kernel-v2
cargo build --release --features control-plane

# Run
./target/release/proclaw-composer \
  --config ./config/composer.yaml \
  --data-dir ./data \
  --llm-api-key "$OPENAI_API_KEY"

# Test Gateway webhook (in another terminal)
curl -X POST http://localhost:3000/gateway/webhook/kernel-response \
  -H "Authorization: Bearer $GATEWAY_AUTH_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "request_id": "test-001",
    "ir": {"intent": "test", "body": "hello"},
    "timestamp": "2024-01-01T00:00:00Z"
  }'
```

## Success Criteria

- [ ] Gateway Skill created and registered
- [ ] Prime Personality can call `gateway.send_ir_result`
- [ ] HTTP POST sent to Gateway webhook with IR
- [ ] Authentication working (Bearer token)
- [ ] End-to-end flow completes successfully
- [ ] Error handling working (timeout, retry)

## Notes

1. **Single Prime assumption**: For now, assume only one Prime instance running. Request Manager serializes requests.

2. **HTTP vs gRPC**: For simplicity, use HTTP callback from Rust to TypeScript. This is acceptable since it's a single call at the end of processing.

3. **IR Format**: IR is JSON with header + body. Gateway Skill just passes it through without modification.

4. **Authentication**: Use Bearer token in Authorization header. Token configured in both Rust (GatewaySkill) and TypeScript (Gateway webhook).

5. **Error Handling**: If Gateway webhook fails, log error but don't block. Request Manager will handle retry at higher level.

Run `/start-work` to execute this plan.
