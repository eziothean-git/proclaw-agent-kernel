use serde::{Deserialize, Serialize};
use std::collections::HashMap;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct IntermediateRepresentation {
    pub request_id: String,
    pub intent: String,
    pub goals: Vec<String>,
    pub processes: Vec<ProcessDefinition>,
    pub context_hints: HashMap<String, serde_json::Value>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProcessDefinition {
    pub name: String,
    pub goal: String,
    pub capabilities: Vec<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub forbidden_capabilities: Option<Vec<String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub constraints: Option<Vec<String>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub security_level: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub dependencies: Option<Vec<String>>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InputMessage {
    pub header: InputHeader,
    pub body: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub metadata: Option<InputMetadata>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub context: Option<ConversationContext>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ConversationContext {
    pub session_id: String,
    pub conversation_history: Vec<ConversationTurn>,
    pub window_size: usize,
    pub full_context_path: String,
    pub total_turns: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ConversationTurn {
    pub turn_id: String,
    pub timestamp: String,
    pub role: String,
    pub content: String,
    pub platform_message_id: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InputHeader {
    pub timestamp: String,
    pub platform: String,
    pub device_id: String,
    pub user_id: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub session_id: Option<String>,
    pub request_id: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub source_ip: Option<String>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub client_version: Option<String>,
    pub priority: i32,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InputMetadata {
    #[serde(skip_serializing_if = "Option::is_none")]
    pub attachments: Option<Vec<AttachmentMetadata>>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub tags: Option<Vec<String>>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AttachmentMetadata {
    pub index: i32,
    pub original_name: String,
    pub mime_type: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub local_path: Option<String>,
}
