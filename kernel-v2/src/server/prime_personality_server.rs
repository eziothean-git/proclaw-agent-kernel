//! Prime Personality gRPC Service
//!
//! 接收 Gateway 请求，内部作为 Agent 执行：
//! 1. gRPC 接收 ProcessRequest
//! 2. 调用 PrimePersonality 生成 IR
//! 3. 通过 AgenticOSInterface Skill 或 SendReply Skill 发送结果

use std::sync::Arc;
use tonic::{Request, Response, Status};
use tracing::{info, instrument, warn};

use crate::personality::{PrimePersonality as PrimePersonalityCore, InputMessage, IntermediateRepresentation};
use crate::coordinator::skill_registry::SkillRegistry;
use crate::auth::CapabilityLevel;

pub mod proto {
    tonic::include_proto!("primepersonality");
}

use proto::{
    prime_personality_server::PrimePersonality,
    ProcessRequestRequest, ProcessRequestResponse,
    HealthCheckRequest, HealthCheckResponse,
    ProcessingStatus, InputMessage as ProtoInputMessage,
    IntermediateRepresentation as ProtoIr, ProcessDefinition as ProtoProcessDef,
};

pub struct PrimePersonalityService {
    personality: Arc<PrimePersonalityCore>,
    skill_registry: Arc<SkillRegistry>,
}

impl PrimePersonalityService {
    pub fn new(
        personality: Arc<PrimePersonalityCore>,
        skill_registry: Arc<SkillRegistry>,
    ) -> Self {
        Self {
            personality,
            skill_registry,
        }
    }

    /// 发送 IR 结果回 Gateway
    async fn send_ir_to_gateway(
        &self,
        ir: IntermediateRepresentation,
    ) -> anyhow::Result<()> {
        // 通过 AgenticOSInterface Skill 提交 IR
        let skill_request = crate::coordinator::models::SkillRequest {
            request_id: ir.request_id.clone(),
            skill_name: "os_interface".to_string(),
            tool_name: "submit_ir_result".to_string(),
            parameters: serde_json::json!({
                "ir": ir,
            }),
            context: crate::coordinator::models::SkillContext {
                thread_id: format!("prime_{}", ir.request_id),
                session_id: ir.request_id.clone(),
                executor_id: "prime_personality".to_string(),
                capability_level: CapabilityLevel::Prime,
                working_dirs: vec![],
            },
        };

        let result = self.skill_registry
            .execute_control(skill_request, CapabilityLevel::Prime)
            .await?;

        if result.success {
            Ok(())
        } else {
            Err(anyhow::anyhow!(
                "Failed to submit IR: {}",
                result.error.unwrap_or_default()
            ))
        }
    }
}

#[tonic::async_trait]
impl PrimePersonality for PrimePersonalityService {
    async fn process_request(
        &self,
        request: Request<ProcessRequestRequest>,
    ) -> Result<Response<ProcessRequestResponse>, Status> {
        let req = request.into_inner();

        // 转换 Proto 消息到内部类型
        let input = match req.input_message {
            Some(proto_input) => convert_proto_to_input(proto_input),
            None => {
                return Err(Status::invalid_argument("Missing input_message"));
            }
        };

        let request_id = input.header.request_id.clone();

        info!(
            request_id = %request_id,
            "Prime Personality received request"
        );

        // 调用 Prime Personality 生成 IR（Agent 执行流程）
        let ir = match self.personality.process_request(input, None).await {
            Ok(ir) => ir,
            Err(e) => {
                warn!(error = %e, "Prime Personality processing failed");
                return Ok(Response::new(ProcessRequestResponse {
                    request_id,
                    status: ProcessingStatus::Failed as i32,
                    ir: None,
                    error_message: e.to_string(),
                }));
            }
        };

        // 通过 Skill 发送结果回 Gateway
        if let Err(e) = self.send_ir_to_gateway(ir.clone()).await {
            warn!(error = %e, "Failed to send IR to gateway");
        }

        // 返回 IR 给调用方（Gateway）
        let proto_ir = convert_ir_to_proto(ir);

        Ok(Response::new(ProcessRequestResponse {
            request_id,
            status: ProcessingStatus::Completed as i32,
            ir: Some(proto_ir),
            error_message: String::new(),
        }))
    }

    async fn health_check(
        &self,
        _request: Request<HealthCheckRequest>,
    ) -> Result<Response<HealthCheckResponse>, Status> {
        Ok(Response::new(HealthCheckResponse {
            healthy: true,
            version: env!("CARGO_PKG_VERSION").to_string(),
            timestamp: Some(prost_types::Timestamp {
                seconds: chrono::Utc::now().timestamp(),
                nanos: 0,
            }),
        }))
    }
}

/// 转换 Proto InputMessage 到内部类型
fn convert_proto_to_input(proto: ProtoInputMessage) -> InputMessage {
    use crate::personality::{InputHeader, InputMetadata, AttachmentMetadata, ConversationContext, ConversationTurn};

    let header = proto.header.map(|h| InputHeader {
        timestamp: h.timestamp,
        platform: h.platform,
        device_id: h.device_id,
        user_id: h.user_id,
        session_id: if h.session_id.is_empty() { None } else { Some(h.session_id) },
        request_id: h.request_id,
        source_ip: if h.source_ip.is_empty() { None } else { Some(h.source_ip) },
        client_version: if h.client_version.is_empty() { None } else { Some(h.client_version) },
        priority: h.priority,
    }).unwrap_or_else(|| InputHeader {
        timestamp: chrono::Utc::now().to_rfc3339(),
        platform: "unknown".to_string(),
        device_id: "unknown".to_string(),
        user_id: "unknown".to_string(),
        session_id: None,
        request_id: "unknown".to_string(),
        source_ip: None,
        client_version: None,
        priority: 0,
    });

    let context = proto.context.map(|c| ConversationContext {
        session_id: c.session_id,
        conversation_history: c.conversation_history.into_iter().map(|t| ConversationTurn {
            turn_id: t.turn_id,
            timestamp: t.timestamp,
            role: t.role,
            content: t.content,
            platform_message_id: if t.platform_message_id.is_empty() { None } else { Some(t.platform_message_id) },
        }).collect(),
        window_size: c.window_size as usize,
        full_context_path: c.full_context_path,
        total_turns: c.total_turns as usize,
    });

    InputMessage {
        header,
        body: proto.body,
        metadata: None, // 简化处理
        context,
    }
}

/// 转换内部 IR 到 Proto 类型
fn convert_ir_to_proto(ir: IntermediateRepresentation) -> ProtoIr {
    ProtoIr {
        request_id: ir.request_id,
        intent: ir.intent,
        goals: ir.goals,
        processes: ir.processes.into_iter().map(|p| ProtoProcessDef {
            name: p.name,
            goal: p.goal,
            capabilities: p.capabilities,
            forbidden_capabilities: p.forbidden_capabilities.unwrap_or_default(),
            constraints: p.constraints.unwrap_or_default(),
            security_level: p.security_level.unwrap_or_default(),
            dependencies: p.dependencies.unwrap_or_default(),
        }).collect(),
        context_hints: ir.context_hints.into_iter().map(|(k, v)| {
            (k, v.to_string())
        }).collect(),
    }
}