//! Prime Personality gRPC Service
//!
//! 接收 Gateway 请求，执行完整链路：
//! 1. gRPC 接收 ProcessRequest
//! 2. Prime Personality 生成 IR
//! 3. IR Process Executor 执行 IR.processes
//! 4. Prime 读取执行结果生成最终响应
//! 5. 通过 Gateway Skill 发送结果

use std::path::PathBuf;
use std::sync::Arc;
use tonic::{Request, Response, Status};
use tracing::{info, warn};

use crate::personality::{PrimePersonality as PrimePersonalityCore, InputMessage, IntermediateRepresentation};
use crate::coordinator::skill_registry::SkillRegistry;
use crate::coordinator::ExecutionCoordinator;
use crate::block_composer::BlockComposerEngine;
use crate::config::PromptLoader;
use crate::executor::IRProcessExecutor;
use crate::llm::LLMRouter;
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
    Content as ProtoContent, Attachment as ProtoAttachment, ResourceReference as ProtoResourceRef,
};

pub struct PrimePersonalityService {
    personality: Arc<PrimePersonalityCore>,
    skill_registry: Arc<SkillRegistry>,
    ir_executor: Arc<IRProcessExecutor>,
    data_path: PathBuf,
}

impl PrimePersonalityService {
    pub async fn new(
        personality: Arc<PrimePersonalityCore>,
        skill_registry: Arc<SkillRegistry>,
        coordinator: Arc<ExecutionCoordinator>,
        block_composer: Arc<BlockComposerEngine>,
        llm_router: Arc<LLMRouter>,
        data_path: PathBuf,
        prompt_loader: Arc<PromptLoader>,
    ) -> anyhow::Result<Self> {
        let ir_executor = Arc::new(
            IRProcessExecutor::new(
                data_path.clone(),
                coordinator,
                block_composer,
                llm_router,
                prompt_loader,
            ).await?
        );

        Ok(Self {
            personality,
            skill_registry,
            ir_executor,
            data_path,
        })
    }

    async fn send_result_to_gateway(
        &self,
        ir: IntermediateRepresentation,
        execution_summary: String,
    ) -> anyhow::Result<()> {
        let skill_request = crate::coordinator::models::SkillRequest {
            request_id: ir.request_id.clone(),
            skill_name: "gateway".to_string(),
            tool_name: "send_ir_result".to_string(),
            parameters: serde_json::json!({
                "ir": ir,
                "request_id": ir.request_id,
                "execution_summary": execution_summary,
            }),
            context: crate::coordinator::models::SkillContext {
                thread_id: format!("prime_{}", ir.request_id),
                session_id: ir.request_id.clone(),
                executor_id: "prime_personality".to_string(),
                capability_level: CapabilityLevel::Prime,
                working_dirs: vec![],
            },
        };

        #[cfg(feature = "control-plane")]
        let result = self.skill_registry
            .execute_control(skill_request, CapabilityLevel::Prime)
            .await?;

        #[cfg(not(feature = "control-plane"))]
        let result = self.skill_registry
            .execute_agent(skill_request)
            .await?;

        if result.success {
            Ok(())
        } else {
            Err(anyhow::anyhow!(
                "Failed to submit result: {}",
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

        info!("Received ProcessRequest: input_message is {}", 
            if req.input_message.is_some() { "Some" } else { "None" });

        // 转换 Proto 消息到内部类型
        let input = match req.input_message {
            Some(proto_input) => convert_proto_to_input(proto_input),
            None => {
                return Err(Status::invalid_argument("Missing input_message"));
            }
        };

        let request_id = input.header.request_id.clone();
        let session_id = input.header.session_id.clone().unwrap_or_else(|| request_id.clone());

        info!(
            request_id = %request_id,
            session_id = %session_id,
            "Prime Personality received request"
        );

        // ========== 第一轮：Prime 生成 IR ==========
        info!("=== Phase 1: Prime generating IR ===");
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

        info!(
            intent = %ir.intent,
            process_count = ir.processes.len(),
            "IR generated"
        );

        // 如果没有 processes（简单对话），直接返回
        if ir.processes.is_empty() {
            info!("No processes to execute, returning IR directly");
            
            // 发送结果到 Gateway
            let summary = ir.content.as_ref()
                .and_then(|c| c.text.clone())
                .unwrap_or_default();
            let _ = self.send_result_to_gateway(ir.clone(), summary).await;
            
            let proto_ir = convert_ir_to_proto(ir);
            return Ok(Response::new(ProcessRequestResponse {
                request_id,
                status: ProcessingStatus::Completed as i32,
                ir: Some(proto_ir),
                error_message: String::new(),
            }));
        }

        // ========== 第二轮：执行 IR Processes ==========
        info!("=== Phase 2: Executing IR processes ===");
        let execution_results = match self.ir_executor.execute_ir(&ir, &session_id).await {
            Ok(results) => {
                info!(result_count = results.len(), "IR execution completed");
                results
            }
            Err(e) => {
                warn!(error = %e, "IR execution failed");
                // 即使执行失败，也继续生成响应
                vec![]
            }
        };

        // ========== 第三轮：Prime 生成最终响应 ==========
        info!("=== Phase 3: Prime generating final response ===");
        
        // 构建执行报告
        let execution_summary = self.build_execution_summary(&ir, &execution_results
        );
        
        // 获取 Session 全量日志
        let session_log = self.ir_executor.get_session_full_log(&session_id).await
            .map(|log| format!("{:?}", log))
            .unwrap_or_default();

        // 构建第二轮输入 - 使用原始 request_id，保持一来一回的设计
        let second_turn_input = InputMessage {
            header: crate::personality::models::InputHeader {
                timestamp: chrono::Utc::now().to_rfc3339(),
                platform: "internal".to_string(),
                device_id: "prime_executor".to_string(),
                user_id: "system".to_string(),
                session_id: Some(session_id.clone()),
                source_ip: None,
                client_version: None,
                priority: 1,
                request_id: request_id.clone(), // 使用原始 request_id，不加 _final 后缀
            },
            body: format!(
                "[任务执行完成报告]\n\n原始请求已完成执行。请根据以下执行结果生成最终响应：\n\n{}\n\nSession日志:\n{}",
                execution_summary,
                session_log
            ),
            metadata: None,
            context: Some(crate::personality::models::ConversationContext {
                session_id: session_id.clone(),
                conversation_history: vec![],
                window_size: 10,
                full_context_path: self.data_path.join("context").to_str().unwrap_or("").to_string(),
                total_turns: 2,
            }),
        };

        // Prime 生成最终响应
        let final_ir = match self.personality.process_request(second_turn_input, None).await {
            Ok(ir) => {
                info!("Final response generated");
                ir
            }
            Err(e) => {
                warn!(error = %e, "Failed to generate final response, using original IR");
                ir // 回退到原始 IR
            }
        };

        // 发送最终结果到 Gateway
        let summary = final_ir.content.as_ref()
            .and_then(|c| c.text.clone())
            .unwrap_or_else(|| execution_summary.clone());

        // 修正 IR：如果是任务执行后的最终响应，设置正确的 intent
        let mut result_ir = final_ir;
        if result_ir.intent == "conversation" && !execution_results.is_empty() {
            // 任务已执行完成，这是最终响应
            result_ir.intent = "task_completed".to_string();
            info!(intent = %result_ir.intent, "Adjusted final response intent");
        }

        if let Err(e) = self.send_result_to_gateway(result_ir.clone(), summary).await {
            warn!(error = %e, "Failed to send result to gateway");
        }

        // 返回最终 IR 给调用方
        let proto_ir = convert_ir_to_proto(result_ir);

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

impl PrimePersonalityService {
    /// 构建执行摘要
    fn build_execution_summary(
        &self,
        ir: &IntermediateRepresentation,
        results: &[crate::executor::ProcessExecutionResult],
    ) -> String {
        let mut summary = format!(
            "执行摘要：\n原始 Intent: {}\n原始 Goals: {:?}\nProcess 数量: {}\n\n执行结果:\n",
            ir.intent,
            ir.goals,
            results.len()
        );

        for (idx, result) in results.iter().enumerate() {
            summary.push_str(&format!(
                "\n[Process {}] {}\n  状态: {}\n  执行步骤: {}\n",
                idx + 1,
                result.process_name,
                if result.success { "成功" } else { "失败" },
                result.execution_log.len()
            ));

            if let Some(answer) = &result.final_answer {
                summary.push_str(&format!("  结果: {}\n", answer));
            }

            if let Some(error) = &result.error_message {
                summary.push_str(&format!("  错误: {}\n", error));
            }
        }

        summary
    }
}

/// 转换 Proto InputMessage 到内部类型
fn convert_proto_to_input(proto: ProtoInputMessage) -> InputMessage {
    use crate::personality::{InputHeader, ConversationContext, ConversationTurn};

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
        metadata: None,
        context,
    }
}

fn convert_ir_to_proto(ir: IntermediateRepresentation) -> ProtoIr {
    let content = ir.content.map(|c| {
        let attachments = c.attachments.map(|atts| {
            atts.into_iter().map(|a| ProtoAttachment {
                id: a.id,
                name: a.name,
                mime_type: a.mime_type,
                local_path: a.local_path.unwrap_or_default(),
                content_url: a.content_url.unwrap_or_default(),
                size_bytes: a.size_bytes.unwrap_or_default(),
            }).collect()
        }).unwrap_or_default();

        let references = c.references.map(|refs| {
            refs.into_iter().map(|r| ProtoResourceRef {
                resource_id: r.resource_id,
                resource_type: r.resource_type,
                start_index: r.start_index as i32,
                end_index: r.end_index as i32,
                metadata: r.metadata.map(|m| {
                    m.into_iter().map(|(k, v)| (k, v.to_string())).collect()
                }).unwrap_or_default(),
            }).collect()
        }).unwrap_or_default();

        let text = c.text.map(|t| {
            if let Ok(json_val) = serde_json::from_str::<serde_json::Value>(&t) {
                if let Some(nested_content) = json_val.get("content") {
                    if let Some(nested_text) = nested_content.get("text").and_then(|v| v.as_str()) {
                        return nested_text.to_string();
                    }
                }
            }
            t
        }).unwrap_or_default();

        ProtoContent {
            text,
            attachments,
            references,
        }
    });

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
        content,
    }
}
