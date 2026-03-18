//! Context Builder Adapter
//!
//! 将 Agent Thread 的历史转换为 Block，通过 BlockComposer 合成 Working Set
//! 这是最低级别的 Context Compiler（规则驱动，非智能）
//!
//! # SEE-ACT-UPDATE Context Injection
//!
//! 构建 ExecutionContext，供 PromptComposer 使用（静态/动态分离）

use std::collections::HashMap;
use std::sync::Arc;

use crate::agent_thread::{
    models::{ArtifactSlot, Event, ExecutionPhase, ImmutableInput, ThreadMeta},
    storage::ThreadStorage,
};
use crate::block_composer::BlockComposerEngine;
use crate::config::PromptLoader;
use crate::config::ExecutionContext as ComposerExecutionContext;
use crate::server::proto::Profile;
use crate::server::proto::Block;

/// Context Builder - 规则驱动的 Working Set 构造器
pub struct ContextBuilder {
    composer: Arc<BlockComposerEngine>,
    prompt_loader: Arc<PromptLoader>,
}

impl ContextBuilder {
    pub fn new(composer: Arc<BlockComposerEngine>, prompt_loader: Arc<PromptLoader>) -> Self {
        Self { composer, prompt_loader }
    }

    /// 构建执行上下文（不直接组装 prompt）
    /// 供 PromptComposer 使用，支持静态/动态分离
    pub async fn build_context(
        &self,
        storage: &ThreadStorage,
        step_number: usize,
    ) -> anyhow::Result<ComposerExecutionContext> {
        // 读取 Thread 元数据
        let meta = storage.read_meta().await?;
        let immutable_input = storage.read_immutable_input().await?;
        let recent_events = storage.read_recent_events(10).await?;
        let artifacts = storage.list_artifacts().await?;

        // 格式化事件为文本
        let events_text = self.format_events_readable(&recent_events);

        // 格式化 artifacts 为文本
        let artifacts_text = self.format_artifacts_readable(&artifacts);

        // 提取工具调用结果
        let tool_results_text = self.extract_tool_results(&recent_events);

        // 提取错误信息
        let error_text = self.extract_errors(&recent_events);

        Ok(ComposerExecutionContext {
            task_goal: immutable_input.task_goal,
            constraints: immutable_input.constraints,
            current_phase: format!("{:?}", meta.current_phase),
            step_number,
            events_text,
            artifacts_text,
            token_budget: 4000,
            tool_results_text,
            error_text,
        })
    }

    /// 格式化 artifacts 为可读文本
    fn format_artifacts_readable(&self, artifacts: &[ArtifactSlot]) -> String {
        if artifacts.is_empty() {
            return String::new();
        }

        let mut formatted = String::new();
        for artifact in artifacts {
            formatted.push_str(&format!(
                "### {:?} (Priority: {})\n",
                artifact.artifact_type, artifact.priority
            ));
            formatted.push_str(&serde_json::to_string_pretty(&artifact.content).unwrap_or_default());
            formatted.push_str("\n\n");
        }
        formatted
    }

    /// 从事件中提取工具调用结果
    fn extract_tool_results(&self, events: &[Event]) -> String {
        use crate::agent_thread::models::EventType;

        let mut results = Vec::new();
        for event in events.iter().rev().take(5) {
            if event.event_type == EventType::ToolResult {
                if let (Some(skill), Some(tool)) = (
                    event.content.get("skill").and_then(|v| v.as_str()),
                    event.content.get("tool").and_then(|v| v.as_str())
                ) {
                    let success = event.content.get("success")
                        .and_then(|v| v.as_bool())
                        .unwrap_or(false);

                    if let Some(result) = event.content.get("result") {
                        results.push(format!(
                            "- {}.{}: {}\n  Result: {}",
                            skill, tool,
                            if success { "✓" } else { "✗" },
                            serde_json::to_string(result).unwrap_or_default()
                        ));
                    }
                }
            }
        }
        results.join("\n")
    }

    /// 从事件中提取错误信息
    fn extract_errors(&self, events: &[Event]) -> String {
        use crate::agent_thread::models::EventType;

        let mut errors = Vec::new();
        for event in events.iter().rev() {
            if event.event_type == EventType::ToolResult {
                if let Some(error) = event.content.get("error").and_then(|v| v.as_str()) {
                    if !error.is_empty() {
                        errors.push(error.to_string());
                    }
                }
            }
        }
        errors.join("\n")
    }
    
    /// 根据 Phase 选择 Profile
    fn profile_for_phase(&self,
        _phase: ExecutionPhase,
    ) -> Profile {
        // 所有 Phase 都使用 Task Profile，但 block 顺序不同
        Profile::Task
    }
    
    /// 构建 Block 列表
    fn build_blocks(
        &self,
        meta: &ThreadMeta,
        immutable_input: &ImmutableInput,
        events: &[Event],
        artifacts: &[ArtifactSlot],
        step_number: usize,
    ) -> anyhow::Result<Vec<Block>> {
        use crate::server::proto::BlockType;

        let mut blocks = Vec::new();

        // 0. System Identity Block - 从配置文件加载
        // Note: This is sync because we're in a non-async context
        // The prompt should be pre-loaded via prompt_loader.load_all()
        let system_prompt = tokio::task::block_in_place(|| {
            tokio::runtime::Handle::current().block_on(async {
                self.prompt_loader.get_thread_prompt().await
            })
        });
        
        blocks.push(Block {
            block_id: format!("system_identity_{}", step_number),
            block_type: BlockType::SystemIdentity as i32,
            content: system_prompt.to_string(),
            metadata: vec![],
            priority: 100,
            token_count: (system_prompt.len() / 4) as u32,
            dependencies: vec![],
            content_hash: Self::compute_hash(&system_prompt),
            created_at: None,
        });
        
        // 1. Task Goal Block (优先级最高)
        blocks.push(Block {
            block_id: format!("task_goal_{}", step_number),
            block_type: BlockType::TaskGoal as i32,
            content: immutable_input.task_goal.clone(),
            metadata: serde_json::to_vec(&serde_json::json!({
                "constraints": immutable_input.constraints,
                "allowed_capabilities": immutable_input.allowed_capabilities,
            }))?,
            priority: 100,
            token_count: (immutable_input.task_goal.len() / 4) as u32,
            dependencies: vec![],
                content_hash: Self::compute_hash(&immutable_input.task_goal),
            created_at: Some(prost_types::Timestamp {
                seconds: immutable_input.compiled_at.timestamp(),
                nanos: immutable_input.compiled_at.timestamp_subsec_nanos() as i32,
            }),
        });
        
        // 2. Current Phase Block
        blocks.push(Block {
            block_id: format!("phase_{}", step_number),
            block_type: BlockType::SystemIdentity as i32,
            content: format!("Current Phase: {:?}", meta.current_phase),
            metadata: serde_json::to_vec(&serde_json::json!({
                "phase": format!("{:?}", meta.current_phase),
            }))?,
            priority: 90,
            token_count: 10,
            dependencies: vec![],
                content_hash: Self::compute_hash(&format!("{:?}", meta.current_phase)),
            created_at: None,
        });
        
        // 3. Recent Observations Block
        if !events.is_empty() {
            let events_text = self.format_events_readable(events);

            blocks.push(Block {
                block_id: format!("observations_{}", step_number),
                block_type: BlockType::RecentObservations as i32,
                content: events_text.clone(),
                metadata: serde_json::to_vec(&serde_json::json!({
                    "event_count": events.len(),
                }))?,
                priority: 80,
                token_count: (events_text.len() / 4) as u32,
                dependencies: vec![],
                content_hash: Self::compute_hash(&events_text),
                created_at: None,
            });
        }
        
        // 4. Artifact Blocks
        for artifact in artifacts {
            let content = format!("## {:?}\n{}", 
                artifact.artifact_type,
                serde_json::to_string_pretty(&artifact.content).unwrap_or_default()
            );
            
            blocks.push(Block {
                block_id: artifact.slot_id.clone(),
                block_type: self.artifact_type_to_block_type(&artifact.artifact_type
                ),
                content: content.clone(),
                metadata: serde_json::to_vec(&serde_json::json!({
                    "priority": artifact.priority,
                    "step_created": artifact.step_number,
                }))?,
                priority: artifact.priority as u32,
                token_count: (content.len() / 4) as u32,
                dependencies: vec![],
                content_hash: Self::compute_hash(&content),
                created_at: Some(prost_types::Timestamp {
                    seconds: artifact.created_at.timestamp(),
                    nanos: artifact.created_at.timestamp_subsec_nanos() as i32,
                }),
            });
        }
        
        // 5. Constraints Block
        if !immutable_input.constraints.is_empty() {
            let constraints_text = immutable_input.constraints.join("\n");
            blocks.push(Block {
                block_id: format!("constraints_{}", step_number),
            block_type: BlockType::WorkingMemory as i32,
            content: format!("## Constraints\n{}", constraints_text),
            metadata: serde_json::to_vec(&serde_json::json!({}))?,
            priority: 70,
                token_count: (constraints_text.len() / 4) as u32,
                dependencies: vec![],
                content_hash: Self::compute_hash(&constraints_text),
                created_at: None,
            });
        }
        
        Ok(blocks)
    }
    
    /// 计算内容的 SHA256 hash
    fn compute_hash(content: &str) -> String {
        use sha2::{Sha256, Digest};
        let mut hasher = Sha256::new();
        hasher.update(content.as_bytes());
        format!("{:x}", hasher.finalize())
    }

    fn format_events_readable(&self, events: &[Event]) -> String {
        use crate::agent_thread::models::EventType;

        let mut formatted = String::from("## Recent Actions and Observations\n\n");

        for event in events {
            match event.event_type {
                EventType::ToolCall => {
                    if let (Some(skill), Some(tool)) = (
                        event.content.get("skill").and_then(|v| v.as_str()),
                        event.content.get("tool").and_then(|v| v.as_str())
                    ) {
                        formatted.push_str(&format!(
                            "[Step {}] Called: {}.{}\n",
                            event.step_number, skill, tool
                        ));

                        if let Some(params) = event.content.get("parameters") {
                            formatted.push_str(&format!("  Parameters: {}\n",
                                serde_json::to_string(params).unwrap_or_default()
                            ));
                        }
                    }
                }
                EventType::ToolResult => {
                    if let (Some(skill), Some(tool)) = (
                        event.content.get("skill").and_then(|v| v.as_str()),
                        event.content.get("tool").and_then(|v| v.as_str())
                    ) {
                        let success = event.content.get("success")
                            .and_then(|v| v.as_bool())
                            .unwrap_or(false);

                        formatted.push_str(&format!(
                            "[Step {}] Result: {}.{} -> {}\n",
                            event.step_number, skill, tool,
                            if success { "SUCCESS" } else { "FAILED" }
                        ));

                        if let Some(result) = event.content.get("result") {
                            if let Some(stdout) = result.get("stdout").and_then(|v| v.as_str()) {
                                if !stdout.is_empty() {
                                    let truncated = if stdout.len() > 500 {
                                        format!("{}... [truncated]", &stdout[..500])
                                    } else {
                                        stdout.to_string()
                                    };
                                    formatted.push_str(&format!("  Output:\n{}\n", truncated));
                                }
                            }
                        }

                        if let Some(error) = event.content.get("error").and_then(|v| v.as_str()) {
                            if !error.is_empty() {
                                formatted.push_str(&format!("  Error: {}\n", error));
                            }
                        }
                    }
                }
                EventType::PhaseChange => {
                    if let (Some(from), Some(to)) = (
                        event.content.get("from_phase").and_then(|v| v.as_str()),
                        event.content.get("to_phase").and_then(|v| v.as_str())
                    ) {
                        formatted.push_str(&format!(
                            "[Step {}] Phase changed: {} -> {}\n",
                            event.step_number, from, to
                        ));
                    }
                }
                _ => {
                    formatted.push_str(&format!(
                        "[{:?}] Step {}: {}\n",
                        event.event_type,
                        event.step_number,
                        serde_json::to_string(&event.content).unwrap_or_default()
                    ));
                }
            }
            formatted.push('\n');
        }

        formatted
    }

    /// 将 ArtifactType 映射到 BlockType
    fn artifact_type_to_block_type(
        &self,
        artifact_type: &crate::agent_thread::models::ArtifactType,
    ) -> i32 {
        use crate::server::proto::BlockType;
        use crate::agent_thread::models::ArtifactType;
        
        match artifact_type {
            ArtifactType::ModuleMap => BlockType::CodeSearchResult as i32,
            ArtifactType::SymbolIndex => BlockType::SymbolDefinition as i32,
            ArtifactType::ContextReport => BlockType::WorkingMemory as i32,
            ArtifactType::FileTree => BlockType::FileContent as i32,
            ArtifactType::PatchPlan => BlockType::WorkingMemory as i32,
            ArtifactType::DependencySummary => BlockType::WorkingMemory as i32,
            ArtifactType::TestPlan => BlockType::WorkingMemory as i32,
            ArtifactType::VerificationResult => BlockType::BashOutput as i32,
            ArtifactType::FinalResult => BlockType::WorkingMemory as i32,
            ArtifactType::Summary => BlockType::WorkingMemory as i32,
            ArtifactType::NextSteps => BlockType::WorkingMemory as i32,
            ArtifactType::Custom(_) => BlockType::WorkingMemory as i32,
        }
    }
}
