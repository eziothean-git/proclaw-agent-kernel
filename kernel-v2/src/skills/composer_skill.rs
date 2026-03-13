//! Composer Skill - 统一的上下文管理和执行接口
//!
//! 这是新架构的核心接口，前端通过此 Skill 完成：
//! 1. 动态管理 Context Blocks
//! 2. 触发 Composition
//! 3. 调用 LLM Generation
//! 4. 执行 Actions（带目录锁）

use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::Arc;

use crate::block_composer::{BlockComposerEngine, BlockMetadata};
use crate::coordinator::{ExecutionCoordinator, models::SkillRequest, models::SkillContext};
use crate::llm::{LLMRouter, config::DifficultyLevel};
use crate::scheduler::{ContextBuilder, OutputParser};
use crate::server::proto::{Block, Profile};
use crate::agent_thread::models::{SessionId, ExecutorId};
use crate::auth::CapabilityLevel;

/// Composer Skill - 统一的上下文管理和执行接口
pub struct ComposerSkill {
    composer: Arc<BlockComposerEngine>,
    coordinator: Arc<ExecutionCoordinator>,
    llm_router: Arc<LLMRouter>,
    context_builder: Arc<ContextBuilder>,
    output_parser: Arc<OutputParser>,
    data_path: PathBuf,
}

/// Block 操作结果
#[derive(Debug, Clone)]
pub struct BlockOperationResult {
    pub success: bool,
    pub block_id: String,
    pub message: String,
}

/// Generation 响应
#[derive(Debug, Clone)]
pub struct GenerationResponse {
    pub composed_text: String,
    pub llm_output: String,
    pub parsed_intent: Option<String>,
    pub total_tokens: u32,
    pub latency_ms: u64,
}

/// Action 请求
#[derive(Debug, Clone)]
pub struct ActionRequest {
    pub action_type: String,
    pub parameters: serde_json::Value,
    pub working_dir: Option<PathBuf>,
}

/// Action 结果
#[derive(Debug, Clone)]
pub struct ActionResult {
    pub success: bool,
    pub result: serde_json::Value,
    pub error: Option<String>,
    pub execution_time_ms: u64,
}

impl ComposerSkill {
    /// 创建新的 ComposerSkill
    pub fn new(
        composer: Arc<BlockComposerEngine>,
        coordinator: Arc<ExecutionCoordinator>,
        llm_router: Arc<LLMRouter>,
        context_builder: Arc<ContextBuilder>,
        output_parser: Arc<OutputParser>,
        data_path: PathBuf,
    ) -> Self {
        Self {
            composer,
            coordinator,
            llm_router,
            context_builder,
            output_parser,
            data_path,
        }
    }

    // ==================== Block 管理 ====================

    /// 添加或更新 Block
    pub async fn upsert_block(
        &self,
        block_id: impl Into<String>,
        block_type: impl Into<i32>,
        content: impl Into<String>,
        priority: u32,
    ) -> BlockOperationResult {
        use sha2::{Sha256, Digest};
        
        let block_id = block_id.into();
        let block_type = block_type.into();
        let content = content.into();
        
        let mut hasher = Sha256::new();
        hasher.update(&content);
        let hash = format!("{:x}", hasher.finalize());

        let block = Block {
            block_id: block_id.clone(),
            block_type,
            content: content.clone(),
            metadata: Vec::new(),
            priority,
            token_count: (content.len() / 4) as u32,
            dependencies: Vec::new(),
            content_hash: hash,
            created_at: Some(prost_types::Timestamp {
                seconds: chrono::Utc::now().timestamp(),
                nanos: 0,
            }),
        };

        let metadata = BlockMetadata {
            block_type,
            priority,
            token_count: (content.len() / 4) as u32,
        };

        self.composer.upsert_block(block, metadata).await;

        BlockOperationResult {
            success: true,
            block_id,
            message: "Block upserted successfully".to_string(),
        }
    }

    /// 删除 Block
    pub async fn remove_block(
        &self,
        block_id: impl AsRef<str>,
    ) -> BlockOperationResult {
        let block_id = block_id.as_ref();
        let removed = self.composer.remove_block(block_id).await;

        BlockOperationResult {
            success: removed,
            block_id: block_id.to_string(),
            message: if removed {
                "Block removed successfully".to_string()
            } else {
                "Block not found".to_string()
            },
        }
    }

    /// 获取指定 Block
    pub async fn get_block(
        &self,
        block_id: impl AsRef<str>,
    ) -> Option<Block> {
        self.composer.get_block(block_id.as_ref()).await
    }

    /// 列出所有 Blocks
    pub async fn list_all_blocks(&self) -> Vec<Block> {
        self.composer.list_all_blocks().await
    }

    /// 按类型列出 Blocks
    pub async fn list_blocks_by_type(
        &self,
        block_type: i32,
    ) -> Vec<Block> {
        self.composer.list_blocks_by_type(block_type).await
    }

    /// 清空所有 Blocks
    pub async fn clear_all_blocks(&self) {
        self.composer.clear_all_blocks().await;
    }

    // ==================== Composition ====================

    /// 合成上下文（不调用 LLM）
    pub async fn compose(
        &self,
        session_id: impl AsRef<str>,
        task_id: impl AsRef<str>,
        profile: Profile,
    ) -> anyhow::Result<crate::server::proto::ComposeResponse> {
        let blocks = self.composer.list_all_blocks().await;
        let context = HashMap::new();

        self.composer.compose(
            session_id.as_ref(),
            task_id.as_ref(),
            profile,
            blocks,
            context,
        ).await
    }

    /// 合成并生成（Act）
    pub async fn compose_and_generate(
        &self,
        session_id: impl AsRef<str>,
        task_id: impl AsRef<str>,
        profile: Profile,
        difficulty: DifficultyLevel,
    ) -> anyhow::Result<GenerationResponse> {
        let start = std::time::Instant::now();

        // 1. Compose
        let compose_response = self.compose(
            session_id.as_ref(),
            task_id.as_ref(),
            profile,
        ).await?;

        // 2. Generate with LLM
        let prompt = compose_response.composed_text.clone();
        let llm_output = self.llm_router.generate(prompt, difficulty).await?;

        // 3. Parse output (optional)
        let parsed_intent = None; // Can be implemented based on needs

        let latency_ms = start.elapsed().as_millis() as u64;

        Ok(GenerationResponse {
            composed_text: compose_response.composed_text,
            llm_output,
            parsed_intent,
            total_tokens: compose_response.total_tokens,
            latency_ms,
        })
    }

    // ==================== 执行（带目录锁） ====================

    /// 执行 Action（目录锁 + FIFO）
    pub async fn execute_with_lock(
        &self,
        directory: PathBuf,
        action: ActionRequest,
        session_id: impl AsRef<str>,
        executor_id: impl AsRef<str>,
        timeout_secs: u64,
    ) -> anyhow::Result<ActionResult> {
        use crate::coordinator::lock_manager::LockLevel;

        let session_id = SessionId(session_id.as_ref().to_string());
        let executor_id = ExecutorId(executor_id.as_ref().to_string());

        // 1. 获取目录锁（FIFO队列）
        let lock_manager = self.coordinator.lock_manager();
        let _lock = lock_manager
            .acquire_lock(
                directory.clone(),
                executor_id.clone(),
                session_id.clone(),
                LockLevel::Write,
                timeout_secs,
            )
            .await?;

        let start = std::time::Instant::now();

        // 2. 执行 Action
        let result = self.execute_action_internal(action, session_id).await;

        let execution_time_ms = start.elapsed().as_millis() as u64;

        // 3. 锁在 _lock 离开作用域时自动释放

        match result {
            Ok(output) => Ok(ActionResult {
                success: true,
                result: output,
                error: None,
                execution_time_ms,
            }),
            Err(e) => Ok(ActionResult {
                success: false,
                result: serde_json::json!({}),
                error: Some(e.to_string()),
                execution_time_ms,
            }),
        }
    }

    /// 内部执行 Action
    async fn execute_action_internal(
        &self,
        action: ActionRequest,
        session_id: SessionId,
    ) -> anyhow::Result<serde_json::Value> {
        // 构造 Skill 请求
        let request = SkillRequest {
            request_id: uuid::Uuid::new_v4().to_string(),
            skill_name: action.action_type.clone(),
            tool_name: "execute".to_string(),
            parameters: action.parameters.clone(),
            context: SkillContext {
                thread_id: format!("composer_{}", session_id.0),
                session_id: session_id.0.clone(),
                executor_id: "composer_skill".to_string(),
                capability_level: CapabilityLevel::Agent,
                working_dirs: action.working_dir.map(|p| vec![p.display().to_string()]).unwrap_or_default(),
            },
        };

        // 通过 Coordinator 执行
        let skill_result = self.coordinator.execute_skill(request).await?;

        Ok(serde_json::json!({
            "success": skill_result.success,
            "result": skill_result.result,
            "error": skill_result.error,
        }))
    }
}
