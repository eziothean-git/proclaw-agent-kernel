//! Gateway Skill - Send IR back to Gateway via HTTP webhook
//! 
//! Permission: Prime only
//! 
//! Tools:
//! - send_ir_result: Submit IR to Gateway webhook

use tracing::{info, instrument, warn};

use crate::auth::CapabilityLevel;
use crate::coordinator::models::{SkillContext, SkillResult};

/// Tool definition for schema
pub struct ToolDefinition {
    pub name: String,
    pub description: String,
    pub parameters: serde_json::Value,
}

/// Gateway Skill - submits IR to Gateway via HTTP webhook
pub struct GatewaySkill {
    client: reqwest::Client,
    gateway_url: String,
    auth_token: String,
}

impl GatewaySkill {
    /// Create new Gateway Skill instance
    pub fn new(gateway_url: String, auth_token: String) -> Self {
        Self {
            client: reqwest::Client::new(),
            gateway_url,
            auth_token,
        }
    }
    
    /// Get Skill name
    pub fn name(&self) -> &str {
        "gateway"
    }
    
    /// List available tools
    pub fn list_tools(&self) -> Vec<ToolDefinition> {
        vec![
            ToolDefinition {
                name: "send_ir_result".to_string(),
                description: "Send Intermediate Representation result back to Gateway".to_string(),
                parameters: serde_json::json!({
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
        
        let session_id = ir.get("request_id")
            .and_then(|v| v.as_str())
            .unwrap_or(request_id);
        
        let content_text = ir.get("content")
            .and_then(|c| c.get("text"))
            .and_then(|v| v.as_str())
            .unwrap_or("");
        
        let status = "completed";
        
        let webhook_url = format!("{}/gateway/webhook/kernel-response", self.gateway_url);
        
        info!(
            request_id = %request_id,
            url = %webhook_url,
            "Sending IR to Gateway webhook"
        );
        
        let result = tokio::time::timeout(
            std::time::Duration::from_secs(5),
            self.client
                .post(&webhook_url)
                .header("Authorization", format!("Bearer {}", self.auth_token))
                .header("Content-Type", "application/json")
                .json(&serde_json::json!({
                    "request_id": request_id,
                    "session_id": session_id,
                    "status": status,
                    "header": {
                        "timestamp": chrono::Utc::now().to_rfc3339(),
                    },
                    "body": content_text,
                    "metadata": {
                        "ir": ir,
                    },
                }))
                .send()
        ).await;
        
        match result {
            Ok(Ok(response)) => {
                let status = response.status();
                let body = response.text().await.unwrap_or_default();
                
                if status.is_success() {
                    info!(
                        request_id = %request_id,
                        status = %status,
                        "Successfully sent IR to Gateway"
                    );
                    Ok(serde_json::json!({
                        "success": true,
                        "gateway_status": status.as_u16(),
                        "gateway_response": body,
                    }))
                } else {
                    warn!(
                        request_id = %request_id,
                        status = %status,
                        response = %body,
                        "Gateway webhook returned error status"
                    );
                    Err(anyhow::anyhow!(
                        "Gateway webhook failed: {} - {}",
                        status,
                        body
                    ))
                }
            }
            Ok(Err(e)) => {
                warn!(
                    request_id = %request_id,
                    error = %e,
                    "Failed to connect to Gateway webhook"
                );
                Err(anyhow::anyhow!(
                    "Gateway connection failed: {}. Note: Gateway may not be running.",
                    e
                ))
            }
            Err(_) => {
                warn!(
                    request_id = %request_id,
                    "Gateway webhook timeout after 5s"
                );
                Err(anyhow::anyhow!("Gateway webhook timeout"))
            }
        }
    }
}
