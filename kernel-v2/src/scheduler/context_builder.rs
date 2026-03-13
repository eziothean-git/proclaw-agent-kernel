//! Context Builder Adapter
//! 
//! 将 Agent Thread 的历史转换为 Block，通过 BlockComposer 合成 Working Set
//! 这是最低级别的 Context Compiler（规则驱动，非智能）

use std::collections::HashMap;
use std::sync::Arc;

use crate::agent_thread::{
    models::{ArtifactSlot, Event, ExecutionPhase, ImmutableInput, ThreadMeta},
    storage::ThreadStorage,
};
use crate::block_composer::BlockComposerEngine;
use crate::server::proto::Profile;
use crate::server::proto::Block;

/// Context Builder - 规则驱动的 Working Set 构造器
pub struct ContextBuilder {
    composer: Arc<BlockComposerEngine>,
}

impl ContextBuilder {
    pub fn new(composer: Arc<BlockComposerEngine>) -> Self {
        Self { composer }
    }
    
    /// 从 Agent Thread 历史构建 Working Set
    pub async fn build(
        &self,
        storage: &ThreadStorage,
        step_number: usize,
    ) -> anyhow::Result<WorkingSet> {
        // 读取 Thread 元数据
        let meta = storage.read_meta().await?;
        let immutable_input = storage.read_immutable_input().await?;
        let recent_events = storage.read_recent_events(10).await?;
        let artifacts = storage.list_artifacts().await?;
        
        // 根据 Phase 构建 Block
        let blocks = self.build_blocks(
            &meta,
            &immutable_input,
            &recent_events,
            &artifacts,
            step_number,
        )?;
        
        // 调用 BlockComposer 合成
        let response = self.composer.compose(
            &meta.session_id.0,
            &meta.thread_id.0,
            self.profile_for_phase(meta.current_phase),
            blocks,
            HashMap::new(),
        ).await?;
        
        Ok(WorkingSet {
            task_id: meta.thread_id.0.clone(),
            task_goal: immutable_input.task_goal.clone(),
            current_phase: meta.current_phase,
            step_number,
            composed_text: response.composed_text,
            token_estimate: response.total_tokens as usize,
        })
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
            let events_text = events.iter()
                .map(|e| format!("[{:?}] Step {}: {}", 
                    e.event_type, 
                    e.step_number,
                    serde_json::to_string(&e.content).unwrap_or_default()
                ))
                .collect::<Vec<_>>()
                .join("\n");
            
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

/// Working Set - 合成的上下文
#[derive(Debug, Clone)]
pub struct WorkingSet {
    pub task_id: String,
    pub task_goal: String,
    pub current_phase: ExecutionPhase,
    pub step_number: usize,
    pub composed_text: String,
    pub token_estimate: usize,
}

impl WorkingSet {
    /// 转换为 Prompt 文本
    pub fn to_prompt(&self,
    ) -> String {
        format!(
            r#"{}

=== CONTEXT ===
Task: {}
Phase: {:?}
Step: {}
Token Estimate: {}
"#,
            self.composed_text,
            self.task_goal,
            self.current_phase,
            self.step_number,
            self.token_estimate
        )
    }
}
