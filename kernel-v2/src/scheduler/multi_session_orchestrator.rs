//! Multi-Session Orchestrator - 多 Session 并行执行协调器
//!
//! 当 Prime 返回多个独立的 processes 时，创建多个 Thread 并行执行

use std::path::PathBuf;
use std::sync::Arc;
use tokio::sync::{mpsc, Mutex};
use tracing::{info};

use crate::agent_thread::{
    models::{ArtifactSlot, ImmutableInput, ThreadId, ThreadMeta},
    storage::ThreadStorage,
};
use crate::coordinator::ExecutionCoordinator;
use crate::llm::LLMRouter;
use crate::personality::models::ProcessDefinition;
use crate::scheduler::{
    context_builder::ContextBuilder,
    output_parser::OutputParser,
    thread_executor::{CompletionReason, ExecutorEvent, ThreadExecutor},
};

/// 子任务定义
#[derive(Debug, Clone)]
pub struct SubTask {
    pub process: ProcessDefinition,
    pub task_id: String,
    pub priority: u32,
}

/// 并行执行配置
#[derive(Debug, Clone)]
pub struct ParallelConfig {
    /// 最大并行线程数
    pub max_concurrent_threads: usize,
    /// 是否等待所有任务完成
    pub wait_for_all: bool,
    /// 是否合并结果
    pub merge_results: bool,
}

impl Default for ParallelConfig {
    fn default() -> Self {
        Self {
            max_concurrent_threads: 3,
            wait_for_all: true,
            merge_results: true,
        }
    }
}

/// 多 Session 执行结果
#[derive(Debug, Clone)]
pub struct MultiSessionResult {
    pub task_id: String,
    pub process_name: String,
    pub success: bool,
    pub artifacts: Vec<ArtifactSlot>,
    pub final_answer: Option<String>,
    pub error: Option<String>,
    pub execution_time_ms: u64,
}

/// 多 Session 协调器
pub struct MultiSessionOrchestrator {
    base_path: PathBuf,
    coordinator: Arc<ExecutionCoordinator>,
    llm_router: Arc<LLMRouter>,
    context_builder: Arc<ContextBuilder>,
    output_parser: Arc<OutputParser>,
}

impl MultiSessionOrchestrator {
    pub fn new(
        base_path: PathBuf,
        coordinator: Arc<ExecutionCoordinator>,
        llm_router: Arc<LLMRouter>,
        context_builder: Arc<ContextBuilder>,
        output_parser: Arc<OutputParser>,
    ) -> Self {
        Self {
            base_path,
            coordinator,
            llm_router,
            context_builder,
            output_parser,
        }
    }

    /// 并行执行多个子任务
    pub async fn execute_parallel(
        &self,
        parent_session_id: String,
        sub_tasks: Vec<SubTask>,
        config: ParallelConfig,
    ) -> anyhow::Result<Vec<MultiSessionResult>> {
        info!(
            "Starting parallel execution of {} sub-tasks",
            sub_tasks.len()
        );

        let start_time = std::time::Instant::now();
        let mut handles = Vec::new();

        // 使用信号量限制并发数
        let semaphore = Arc::new(tokio::sync::Semaphore::new(config.max_concurrent_threads));

        for sub_task in sub_tasks {
            let semaphore = semaphore.clone();
            let base_path = self.base_path.clone();
            let coordinator = self.coordinator.clone();
            let llm_router = self.llm_router.clone();
            let context_builder = self.context_builder.clone();
            let output_parser = self.output_parser.clone();
            let parent_session_id = parent_session_id.clone();

            let handle = tokio::spawn(async move {
                // 获取信号量许可
                let _permit = semaphore.acquire().await.unwrap();

                info!("Starting sub-task: {}", sub_task.process.name);

                let task_start = std::time::Instant::now();

                // 创建独立的 Thread
                let thread_id = ThreadId::new();
                let result = Self::execute_single_thread(
                    base_path,
                    thread_id.clone(),
                    parent_session_id,
                    sub_task.clone(),
                    coordinator,
                    llm_router,
                    context_builder,
                    output_parser,
                )
                .await;

                let execution_time_ms = task_start.elapsed().as_millis() as u64;

                match result {
                    Ok((artifacts, final_answer)) => MultiSessionResult {
                        task_id: sub_task.task_id,
                        process_name: sub_task.process.name.clone(),
                        success: true,
                        artifacts,
                        final_answer,
                        error: None,
                        execution_time_ms,
                    },
                    Err(e) => MultiSessionResult {
                        task_id: sub_task.task_id,
                        process_name: sub_task.process.name.clone(),
                        success: false,
                        artifacts: vec![],
                        final_answer: None,
                        error: Some(e.to_string()),
                        execution_time_ms,
                    },
                }
            });

            handles.push(handle);
        }

        // 等待所有任务完成
        let results = if config.wait_for_all {
            futures::future::join_all(handles)
                .await
                .into_iter()
                .filter_map(|r| r.ok())
                .collect()
        } else {
            // 只等待第一个成功的任务
            let mut results = Vec::new();
            for handle in handles {
                if let Ok(result) = handle.await {
                    results.push(result);
                }
            }
            results
        };

        let total_time_ms = start_time.elapsed().as_millis() as u64;
        info!(
            "Parallel execution completed: {} tasks in {}ms",
            results.len(),
            total_time_ms
        );

        Ok(results)
    }

    /// 执行单个 Thread
    async fn execute_single_thread(
        base_path: PathBuf,
        thread_id: ThreadId,
        parent_session_id: String,
        sub_task: SubTask,
        coordinator: Arc<ExecutionCoordinator>,
        llm_router: Arc<LLMRouter>,
        context_builder: Arc<ContextBuilder>,
        output_parser: Arc<OutputParser>,
    ) -> anyhow::Result<(Vec<ArtifactSlot>, Option<String>)> {
        // 创建 ThreadStorage
        let immutable_input = ImmutableInput {
            task_goal: sub_task.process.goal.clone(),
            constraints: sub_task.process.constraints.clone().unwrap_or_default(),
            allowed_capabilities: sub_task.process.capabilities.clone(),
            forbidden_capabilities: vec![],
            session_context: std::collections::HashMap::new(),
            compiled_at: chrono::Utc::now(),
        };

        let storage = ThreadStorage::create(
            &base_path,
            thread_id.clone(),
            crate::agent_thread::models::SessionId(parent_session_id),
            immutable_input,
        )
        .await?;

        // 设置初始元数据
        let meta = ThreadMeta::new(
            thread_id.clone(),
            crate::agent_thread::models::SessionId("sub_session".to_string()),
        );
        storage.update_meta(&meta).await?;

        // 创建事件通道
        let (event_tx, mut event_rx) = mpsc::channel(100);

        // 创建 ThreadExecutor
        let executor = ThreadExecutor::new(
            base_path.clone(),
            thread_id.clone(),
            coordinator,
            llm_router,
            context_builder,
            output_parser,
            event_tx,
        )
        .await?;

        // 启动事件监听器（用于收集 artifacts）
        let artifacts = Arc::new(Mutex::new(Vec::<ArtifactSlot>::new()));
        let _artifacts_clone = artifacts.clone();

        let event_listener = tokio::spawn(async move {
            while let Some(event) = event_rx.recv().await {
                match event {
                    ExecutorEvent::Completed { reason } => {
                        if matches!(reason, CompletionReason::FinalAnswer) {
                            break;
                        }
                    }
                    _ => {}
                }
            }
        });

        // 执行
        executor.run().await?;

        // 等待事件监听器完成
        let _ = tokio::time::timeout(std::time::Duration::from_secs(5), event_listener).await;

        // 读取所有 artifacts (reload storage to get latest state)
        let storage = ThreadStorage::load(
            &base_path,
            &thread_id
        ).await?;
        let final_artifacts = storage.list_artifacts().await?;

        // TODO: 提取 final_answer
        let final_answer = None;

        Ok((final_artifacts, final_answer))
    }

    /// 合并多个子任务的结果
    pub fn merge_results(
        &self,
        results: &[MultiSessionResult],
    ) -> anyhow::Result<String> {
        let mut summary = String::from("## 并行任务执行结果\n\n");

        for result in results {
            summary.push_str(&format!(
                "### {}\n",
                result.process_name
            ));

            if result.success {
                summary.push_str("✅ **成功**\n");
                if let Some(answer) = &result.final_answer {
                    summary.push_str(&format!("\n{}\n", answer));
                }
                summary.push_str(&format!(
                    "\n- 执行时间: {}ms\n",
                    result.execution_time_ms
                ));
            } else {
                summary.push_str("❌ **失败**\n");
                if let Some(error) = &result.error {
                    summary.push_str(&format!("\n错误: {}\n", error));
                }
            }

            summary.push('\n');
        }

        Ok(summary)
    }
}

/// Process 到 SubTask 的转换
trait ProcessConverter {
    fn to_sub_task(self, index: usize) -> SubTask;
}

impl ProcessConverter for ProcessDefinition {
    fn to_sub_task(self, index: usize) -> SubTask {
        SubTask {
            process: self,
            task_id: format!("sub_task_{}", index),
            priority: 50,
        }
    }
}

pub fn convert_processes_to_sub_tasks(
    processes: Vec<ProcessDefinition>
) -> Vec<SubTask> {
    processes
        .into_iter()
        .enumerate()
        .map(|(i, p)| p.to_sub_task(i))
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parallel_config_default() {
        let config = ParallelConfig::default();
        assert_eq!(config.max_concurrent_threads, 3);
        assert!(config.wait_for_all);
        assert!(config.merge_results);
    }

    #[test]
    fn test_merge_results() {
        // TODO: 添加结果合并测试
    }
}
