//! Parallel Action Executor - 支持并行执行多个 Actions
//!
//! 提供两种执行模式：
//! 1. Sequential - 串行执行（默认，保持向后兼容）
//! 2. Parallel - 并行执行（通过配置启用）

use std::sync::Arc;
use tokio::sync::Mutex;
use tracing::{info};

use crate::agent_thread::models::{Event, EventType, ExecutionPhase};
use crate::agent_thread::storage::ThreadStorage;
use crate::coordinator::{
    ExecutionCoordinator,
    models::{SkillContext, SkillRequest, SkillResult},
};
use crate::auth::CapabilityLevel;
use crate::scheduler::thread_executor::{ExecutorEvent, ToolCallIntent};

/// 执行模式
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ExecutionMode {
    /// 串行执行
    Sequential,
    /// 并行执行
    Parallel,
}

impl Default for ExecutionMode {
    fn default() -> Self {
        ExecutionMode::Sequential
    }
}

/// Action 执行结果
#[derive(Debug)]
pub struct ActionResult {
    pub tool_call: ToolCallIntent,
    pub result: anyhow::Result<SkillResult>,
    pub execution_time_ms: u64,
}

/// Parallel Action Executor
pub struct ParallelActionExecutor {
    coordinator: Arc<ExecutionCoordinator>,
    storage: Arc<Mutex<ThreadStorage>>,
    executor_id: String,
    session_id: String,
    current_step: usize,
    current_phase: ExecutionPhase,
    event_tx: tokio::sync::mpsc::Sender<ExecutorEvent>,
}

impl ParallelActionExecutor {
    pub fn new(
        coordinator: Arc<ExecutionCoordinator>,
        storage: ThreadStorage,
        executor_id: String,
        session_id: String,
        current_step: usize,
        current_phase: ExecutionPhase,
        event_tx: tokio::sync::mpsc::Sender<ExecutorEvent>,
    ) -> Self {
        Self {
            coordinator,
            storage: Arc::new(Mutex::new(storage)),
            executor_id,
            session_id,
            current_step,
            current_phase,
            event_tx,
        }
    }

    /// 执行多个 actions
    pub async fn execute_actions(
        &self,
        tool_calls: Vec<ToolCallIntent>,
        mode: ExecutionMode,
    ) -> anyhow::Result<Vec<ActionResult>> {
        match mode {
            ExecutionMode::Sequential => {
                info!("Executing {} actions sequentially", tool_calls.len());
                self.execute_sequential(tool_calls).await
            }
            ExecutionMode::Parallel => {
                info!("Executing {} actions in parallel", tool_calls.len());
                self.execute_parallel(tool_calls).await
            }
        }
    }

    /// 串行执行
    async fn execute_sequential(
        &self,
        tool_calls: Vec<ToolCallIntent>,
    ) -> anyhow::Result<Vec<ActionResult>> {
        let mut results = Vec::new();

        for tool_call in tool_calls {
            let result = self.execute_single_action(&tool_call).await;
            results.push(ActionResult {
                tool_call: tool_call.clone(),
                result: result.map_err(|e| e),
                execution_time_ms: 0, // TODO: 记录实际时间
            });

            // 记录事件
            self.record_action_events(&tool_call, results.last().unwrap())
                .await?;
        }

        Ok(results)
    }

    /// 并行执行
    async fn execute_parallel(
        &self,
        tool_calls: Vec<ToolCallIntent>,
    ) -> anyhow::Result<Vec<ActionResult>> {
        // 创建并发的执行 futures
        let mut futures = Vec::new();

        for tool_call in tool_calls.clone() {
            let coordinator = self.coordinator.clone();
            let _storage = self.storage.clone();
            let executor_id = self.executor_id.clone();
            let session_id = self.session_id.clone();
            let event_tx = self.event_tx.clone();

            let future = async move {
                let start = std::time::Instant::now();

                // 发送开始执行事件
                let _ = event_tx
                    .send(ExecutorEvent::SkillExecuting {
                        skill_name: tool_call.skill_name.clone(),
                        tool_name: tool_call.tool_name.clone(),
                    })
                    .await;

                // 构建请求
                let request = SkillRequest {
                    request_id: uuid::Uuid::new_v4().to_string(),
                    skill_name: tool_call.skill_name.clone(),
                    tool_name: tool_call.tool_name.clone(),
                    parameters: tool_call.parameters.clone(),
                    context: SkillContext {
                        thread_id: format!("thread_{}", executor_id),
                        session_id: session_id.clone(),
                        executor_id: executor_id.clone(),
                        capability_level: CapabilityLevel::Agent,
                        working_dirs: Vec::new(),
                    },
                };

                // 执行
                let result = coordinator.execute_skill(request).await;

                let execution_time_ms = start.elapsed().as_millis() as u64;

                // 发送完成事件
                let _ = event_tx
                    .send(ExecutorEvent::SkillCompleted {
                        success: result.as_ref().map(|r| r.success).unwrap_or(false),
                        execution_time_ms,
                    })
                    .await;

                ActionResult {
                    tool_call: tool_call.clone(),
                    result,
                    execution_time_ms,
                }
            };

            futures.push(future);
        }

        // 并行执行所有 futures
        let results = futures::future::join_all(futures).await;

        // 记录所有事件（串行记录以避免存储竞争）
        for (tool_call, result) in tool_calls.iter().zip(results.iter()) {
            self.record_action_events(tool_call, result).await?;
        }

        Ok(results)
    }

    /// 执行单个 action
    async fn execute_single_action(
        &self,
        tool_call: &ToolCallIntent,
    ) -> anyhow::Result<SkillResult> {
        let _ = self
            .event_tx
            .send(ExecutorEvent::SkillExecuting {
                skill_name: tool_call.skill_name.clone(),
                tool_name: tool_call.tool_name.clone(),
            })
            .await;

        let request = SkillRequest {
            request_id: uuid::Uuid::new_v4().to_string(),
            skill_name: tool_call.skill_name.clone(),
            tool_name: tool_call.tool_name.clone(),
            parameters: tool_call.parameters.clone(),
            context: SkillContext {
                thread_id: format!("thread_{}", self.executor_id),
                session_id: self.session_id.clone(),
                executor_id: self.executor_id.clone(),
                capability_level: CapabilityLevel::Agent,
                working_dirs: Vec::new(),
            },
        };

        let result = self.coordinator.execute_skill(request).await;

        let _ = self
            .event_tx
            .send(ExecutorEvent::SkillCompleted {
                success: result.as_ref().map(|r| r.success).unwrap_or(false),
                execution_time_ms: 0,
            })
            .await;

        result
    }

    /// 记录 action 事件到 storage
    async fn record_action_events(
        &self,
        tool_call: &ToolCallIntent,
        action_result: &ActionResult,
    ) -> anyhow::Result<()> {
        let storage = self.storage.lock().await;

        // 记录 ToolCall 事件
        let tool_call_event = Event::new(
            EventType::ToolCall,
            self.current_step,
            self.current_phase,
            serde_json::json!({
                "skill": &tool_call.skill_name,
                "tool": &tool_call.tool_name,
                "parameters": &tool_call.parameters,
            }),
        );
        storage.append_event(&tool_call_event).await?;

        // 记录 ToolResult 事件
        let result = match &action_result.result {
            Ok(r) => serde_json::json!({
                "skill": &tool_call.skill_name,
                "tool": &tool_call.tool_name,
                "success": r.success,
                "result": &r.result,
                "error": &r.error,
            }),
            Err(e) => serde_json::json!({
                "skill": &tool_call.skill_name,
                "tool": &tool_call.tool_name,
                "success": false,
                "error": e.to_string(),
            }),
        };

        let tool_result_event = Event::new(
            EventType::ToolResult,
            self.current_step,
            self.current_phase,
            result,
        );
        storage.append_event(&tool_result_event).await?;

        // 保存 artifact
        let artifact_content = serde_json::json!({
            "skill": &tool_call.skill_name,
            "tool": &tool_call.tool_name,
            "parameters": &tool_call.parameters,
            "success": action_result.result.as_ref().map(|r| r.success).unwrap_or(false),
            "result": action_result.result.as_ref().ok().and_then(|r| r.result.as_ref()).unwrap_or(&serde_json::json!({})),
            "error": action_result.result.as_ref().err().map(|e| e.to_string()).or_else(|| action_result.result.as_ref().ok().and_then(|r| r.error.clone())),
            "execution_time_ms": action_result.execution_time_ms,
        });

        let artifact = crate::agent_thread::models::ArtifactSlot::new(
            crate::agent_thread::models::ArtifactType::Custom(format!(
                "{}_{}",
                tool_call.skill_name, tool_call.tool_name
            )),
            artifact_content,
            5,
            self.current_step,
        );
        storage.save_artifact(&artifact).await?;

        Ok(())
    }
}

/// 依赖关系分析器
pub struct DependencyAnalyzer;

impl DependencyAnalyzer {
    /// 分析 actions 之间的依赖关系
    /// 返回可以并行执行的 action 组
    pub fn analyze_dependencies(
        tool_calls: &[ToolCallIntent],
    ) -> Vec<Vec<usize>> {
        // TODO: 实现依赖分析逻辑
        // 目前简单返回所有 actions 作为一个组（全部并行）
        vec![(0..tool_calls.len()).collect()]
    }

    /// 检查两个 actions 是否有依赖关系
    fn has_dependency(
        _action1: &ToolCallIntent,
        _action2: &ToolCallIntent,
    ) -> bool {
        // TODO: 实现依赖检测逻辑
        // 例如：检查是否操作同一个文件、是否有读写依赖等
        false
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::scheduler::thread_executor::ToolCallIntent;

    #[test]
    fn test_execution_mode_default() {
        let mode = ExecutionMode::default();
        assert_eq!(mode, ExecutionMode::Sequential);
    }

    #[tokio::test]
    async fn test_parallel_execution_mock() {
        // TODO: 添加 mock 测试
        // 需要 mock ExecutionCoordinator
    }
}
