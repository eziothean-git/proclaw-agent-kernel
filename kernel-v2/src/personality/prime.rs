use std::sync::Arc;
use std::collections::HashMap;
use anyhow::{Result, anyhow};
use tracing::{info, warn};
use sha2::{Sha256, Digest};

use crate::block_composer::BlockComposerEngine;
use crate::llm::{LLMRouter, config::DifficultyLevel};
use crate::server::proto::{Block, Profile};

use super::{IntermediateRepresentation, ProcessDefinition, InputMessage, PrimePersonalityConfig, ConversationContext, ConversationTurn, Content, Attachment, ResourceReference};

pub struct PrimePersonality {
    config: PrimePersonalityConfig,
    llm_router: Arc<LLMRouter>,
    composer: Arc<BlockComposerEngine>,
}

impl PrimePersonality {
    pub fn new(
        config: PrimePersonalityConfig,
        llm_router: Arc<LLMRouter>,
        composer: Arc<BlockComposerEngine>,
    ) -> Self {
        Self {
            config,
            llm_router,
            composer,
        }
    }

    pub async fn process_request(
        &self,
        input: InputMessage,
        _session_context: Option<serde_json::Value>,
    ) -> Result<IntermediateRepresentation> {
        info!(
            request_id = %input.header.request_id,
            platform = %input.header.platform,
            user_id = %input.header.user_id,
            "Processing request with Prime Personality"
        );

        let prompt = self.build_prompt(&input).await?;
        
        // 打印 prompt 用于调试
        tracing::debug!("Prime prompt:\n{}", prompt);

        let response = self.llm_router.generate(
            prompt,
            DifficultyLevel::Hard,
        ).await?;
        
        // 打印 response 用于调试
        tracing::debug!("Prime response:\n{}", response);

        let ir = self.parse_ir(&response, &input.header.request_id)?;

        info!(
            request_id = %ir.request_id,
            intent = %ir.intent,
            process_count = ir.processes.len(),
            "Generated intermediate representation"
        );

        Ok(ir)
    }

    async fn build_prompt(
        &self,
        input: &InputMessage,
    ) -> Result<String> {
        let mut blocks: Vec<Block> = Vec::new();

        let enhanced_system_prompt = if let Some(ref ctx) = input.context {
            format!(
                "{}\n\n## Context Reference\n\nThis conversation has {} total turns. \
You have access to the last {} turns in the conversation history below. \
For full conversation history and session state, access: {}\n\n## Memory Access Rules\n\n- You are STATELESS in terms of direct memory, but the system provides you \
with recent conversation history through the [CONVERSATION_HISTORY] block\n- \
If you need information beyond the provided window, you can access the full \
context at the path provided above\n- Use context_hints in your response to \
indicate if you need additional context from memory\n",
                self.config.system_prompt,
                ctx.total_turns,
                ctx.conversation_history.len(),
                ctx.full_context_path
            )
        } else {
            self.config.system_prompt.clone()
        };

        let system_prompt_len = enhanced_system_prompt.len();
        let system_prompt_hash = {
            let mut hasher = Sha256::new();
            hasher.update(&enhanced_system_prompt);
            format!("{:x}", hasher.finalize())
        };
        
        let system_block = Block {
            block_id: "system_identity".to_string(),
            block_type: 1,
            content: enhanced_system_prompt,
            metadata: vec![],
            priority: 100,
            token_count: (system_prompt_len / 4) as u32,
            dependencies: vec![],
            content_hash: system_prompt_hash,
            created_at: Some(prost_types::Timestamp {
                seconds: chrono::Utc::now().timestamp(),
                nanos: 0,
            }),
        };
        blocks.push(system_block);

        if let Some(ref ctx) = input.context {
            if !ctx.conversation_history.is_empty() {
                let history_content = self.format_conversation_history(&ctx.conversation_history);
                let history_block = Block {
                    block_id: "conversation_history".to_string(),
                    block_type: 8,
                    content: history_content,
                    metadata: vec![],
                    priority: 80,
                    token_count: (ctx.conversation_history.len() * 100) as u32,
                    dependencies: vec![],
                    content_hash: {
                        let mut hasher = Sha256::new();
                        hasher.update(ctx.session_id.as_bytes());
                        format!("{:x}", hasher.finalize())
                    },
                    created_at: Some(prost_types::Timestamp {
                        seconds: chrono::Utc::now().timestamp(),
                        nanos: 0,
                    }),
                };
                blocks.push(history_block);
            }
        }

        let user_message = format!(
            "Platform: {}\nUser: {}\nSession: {}\nPriority: {}\n\nCurrent Message: {}",
            input.header.platform,
            input.header.user_id,
            input.header.session_id.as_deref().unwrap_or("none"),
            input.header.priority,
            input.body
        );

        let user_block = Block {
            block_id: "user_request".to_string(),
            block_type: 7,
            content: user_message,
            metadata: vec![],
            priority: 90,
            token_count: (input.body.len() / 4) as u32,
            dependencies: vec![],
            content_hash: {
                let mut hasher = Sha256::new();
                hasher.update(&input.body);
                format!("{:x}", hasher.finalize())
            },
            created_at: Some(prost_types::Timestamp {
                seconds: chrono::Utc::now().timestamp(),
                nanos: 0,
            }),
        };
        blocks.push(user_block);

        let context = HashMap::new();

        let compose_result = self.composer.compose(
            &input.header.request_id,
            &input.header.request_id,
            Profile::Prime,
            blocks,
            context,
        ).await?;

        Ok(compose_result.composed_text)
    }

    fn format_conversation_history(&self, history: &[ConversationTurn]) -> String {
        let mut formatted = String::from("## Recent Conversation History (Sliding Window)\n\n");

        for (idx, turn) in history.iter().enumerate() {
            formatted.push_str(&format!(
                "[Turn {} - {}] {}: {}\n\n",
                idx + 1,
                turn.timestamp,
                turn.role.to_uppercase(),
                turn.content
            ));
        }

        formatted.push_str(&format!(
            "\n--- End of History (showing last {} turns) ---\n",
            history.len()
        ));

        formatted
    }

    fn parse_ir(
        &self,
        response: &str,
        request_id: &str,
    ) -> Result<IntermediateRepresentation> {
        let json_str = self.extract_json(response)?;
        
        let value: serde_json::Value = match serde_json::from_str(&json_str) {
            Ok(v) => v,
            Err(e) => {
                warn!(error = %e, "Failed to parse JSON, using fallback");
                return Ok(self.create_fallback_ir(request_id, response));
            }
        };
        
        let ir = IntermediateRepresentation {
            request_id: request_id.to_string(),
            intent: value.get("intent")
                .and_then(|v| v.as_str())
                .unwrap_or("conversation")
                .to_string(),
            goals: value.get("goals")
                .and_then(|v| v.as_array())
                .map(|arr| arr.iter()
                    .filter_map(|v| v.as_str().map(String::from))
                    .collect())
                .unwrap_or_else(|| vec!["Process user request".to_string()]),
            processes: self.extract_processes(&value),
            context_hints: value.get("context_hints")
                .and_then(|v| v.as_object())
                .map(|obj| obj.iter()
                    .map(|(k, v)| (k.clone(), v.clone()))
                    .collect())
                .unwrap_or_default(),
            content: self.extract_content(&value).ok(),
        };
        
        Ok(ir)
    }
    
    fn extract_processes(&self, value: &serde_json::Value) -> Vec<ProcessDefinition> {
        value.get("processes")
            .and_then(|v| v.as_array())
            .map(|arr| arr.iter()
                .filter_map(|p| {
                    Some(ProcessDefinition {
                        name: p.get("name")?.as_str()?.to_string(),
                        goal: p.get("goal")?.as_str()?.to_string(),
                        capabilities: p.get("capabilities")
                            .and_then(|v| v.as_array())
                            .map(|arr| arr.iter()
                                .filter_map(|v| v.as_str().map(String::from))
                                .collect())
                            .unwrap_or_default(),
                        forbidden_capabilities: p.get("forbidden_capabilities")
                            .and_then(|v| v.as_array())
                            .map(|arr| arr.iter()
                                .filter_map(|v| v.as_str().map(String::from))
                                .collect()),
                        constraints: p.get("constraints")
                            .and_then(|v| v.as_array())
                            .map(|arr| arr.iter()
                                .filter_map(|v| v.as_str().map(String::from))
                                .collect()),
                        security_level: p.get("security_level")
                            .and_then(|v| v.as_str())
                            .map(String::from),
                        dependencies: p.get("dependencies")
                            .and_then(|v| v.as_array())
                            .map(|arr| arr.iter()
                                .filter_map(|v| v.as_str().map(String::from))
                                .collect()),
                    })
                })
                .collect())
            .unwrap_or_else(|| vec![ProcessDefinition {
                name: "conversation".to_string(),
                goal: "Respond to user message".to_string(),
                capabilities: vec![],
                forbidden_capabilities: None,
                constraints: Some(vec!["max_steps: 5".to_string()]),
                security_level: Some("low".to_string()),
                dependencies: None,
            }])
    }
    
    fn extract_content(&self, value: &serde_json::Value) -> Result<Content> {
        if let Some(content_val) = value.get("content") {
            let text = content_val.get("text")
                .and_then(|t| t.as_str())
                .map(String::from);
            
            let attachments = content_val.get("attachments")
                .and_then(|v| v.as_array())
                .map(|arr| arr.iter()
                    .filter_map(|item| {
                        Some(Attachment {
                            id: item.get("id")?.as_str()?.to_string(),
                            name: item.get("name")?.as_str()?.to_string(),
                            mime_type: item.get("mime_type")?.as_str()?.to_string(),
                            local_path: item.get("local_path")
                                .and_then(|v| v.as_str())
                                .map(String::from),
                            content_url: item.get("content_url")
                                .and_then(|v| v.as_str())
                                .map(String::from),
                            size_bytes: item.get("size_bytes")
                                .and_then(|v| v.as_i64()),
                        })
                    })
                    .collect());
            
            let references = content_val.get("references")
                .and_then(|v| v.as_array())
                .map(|arr| arr.iter()
                    .filter_map(|item| {
                        Some(ResourceReference {
                            resource_id: item.get("resource_id")?.as_str()?.to_string(),
                            resource_type: item.get("resource_type")?.as_str()?.to_string(),
                            start_index: item.get("start_index")?.as_u64()? as usize,
                            end_index: item.get("end_index")?.as_u64()? as usize,
                            metadata: item.get("metadata")
                                .and_then(|m| m.as_object())
                                .map(|obj| obj.iter()
                                    .map(|(k, v)| (k.clone(), v.clone()))
                                    .collect()),
                        })
                    })
                    .collect());
            
            Ok(Content { text, attachments, references })
        } else {
            Ok(Content {
                text: Some("Processed successfully".to_string()),
                attachments: None,
                references: None,
            })
        }
    }

    fn extract_json(&self,
        response: &str,
    ) -> Result<String> {
        let trimmed = response.trim();

        if let Some(start) = trimmed.find('{') {
            if let Some(end) = trimmed.rfind('}') {
                if start < end {
                    return Ok(trimmed[start..=end].to_string());
                }
            }
        }

        Err(anyhow!("No JSON found in response"))
    }

    fn create_fallback_ir(
        &self,
        request_id: &str,
        response: &str,
    ) -> IntermediateRepresentation {
        IntermediateRepresentation {
            request_id: request_id.to_string(),
            intent: "conversation".to_string(),
            goals: vec!["Provide direct response".to_string()],
            processes: vec![ProcessDefinition {
                name: "fallback_response".to_string(),
                goal: response.chars().take(100).collect(),
                capabilities: vec![],
                forbidden_capabilities: None,
                constraints: Some(vec!["max_steps: 5".to_string()]),
                security_level: Some("low".to_string()),
                dependencies: None,
            }],
            context_hints: HashMap::new(),
            content: Some(Content {
                text: Some(response.to_string()),
                attachments: None,
                references: None,
            }),
        }
    }
}
