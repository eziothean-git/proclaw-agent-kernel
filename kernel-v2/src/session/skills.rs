//! Session Host SKILL 接口
//! 
//! 为主人格（Prime Personality）和 Session Host 提供管理 Process 和 Thread 的 SKILL
//! 
//! 职责：
//! - 创建/管理 Process
//! - 在 Process 中创建/管理 Thread
//! - 启动/停止 Thread Executor
//! - 查询 Process/Thread 状态

use std::path::PathBuf;
use std::sync::Arc;
use tokio::sync::RwLock;
use tracing::{info, warn};

use crate::agent_thread::{
    models::{SessionId, ThreadId, ImmutableInput},
    storage::ThreadStorage,
};
use crate::block_composer::BlockComposerEngine;
use crate::coordinator::ExecutionCoordinator;
use crate::llm::{
    LLMRouter,
    config::DifficultyLevel,
};
use crate::scheduler::{
    ContextBuilder, OutputParser, ThreadExecutor, ExecutorEvent,
};
use crate::session::process::{ProcessId, ProcessManager};

/// Session Host SKILL 集合
pub struct SessionHostSkills {
    data_path: PathBuf,
    process_manager: Arc<RwLock<ProcessManager>>,
    coordinator: Arc<ExecutionCoordinator>,
    llm_router: Arc<LLMRouter>,
    context_builder: Arc<ContextBuilder>,
    output_parser: Arc<OutputParser>,
    block_composer: Arc<BlockComposerEngine>,
    executors: Arc<RwLock<std::collections::HashMap<String, ExecutorHandle>>>,
}

#[derive(Debug)]
struct ExecutorHandle {
    executor_id: String,
    thread_id: String,
    process_id: String,
    event_tx: tokio::sync::mpsc::Sender<ExecutorEvent>,
    task_handle: Option<tokio::task::JoinHandle<()>>,
}

impl SessionHostSkills {
    /// 创建新的 Session Host Skills
    pub async fn new(
        data_path: PathBuf,
        coordinator: Arc<ExecutionCoordinator>,
        block_composer: Arc<BlockComposerEngine>,
        llm_router: Arc<LLMRouter>,
    ) -> anyhow::Result<Self> {
        // 创建 Process Manager
        let process_manager = Arc::new(RwLock::new(
            ProcessManager::new(&data_path).await?
        ));
        
        // 创建 Context Builder
        let context_builder = Arc::new(ContextBuilder::new(block_composer.clone()));
        
        // 创建 Output Parser
        let output_parser = Arc::new(OutputParser::new());
        
        Ok(Self {
            data_path,
            process_manager,
            coordinator,
            llm_router,
            context_builder,
            output_parser,
            block_composer,
            executors: Arc::new(RwLock::new(std::collections::HashMap::new())),
        })
    }
    
    // ==================== Process 管理 SKILL ====================
    
    /// SKILL: 创建新 Process
    /// 
    /// 参数：
    /// - session_id: Session ID
    /// - process_goal: Process 目标
    /// - tags: 标签列表
    /// 
    /// 返回：Process ID
    pub async fn create_process(
        &self,
        session_id: impl Into<String>,
        process_goal: impl Into<String>,
        tags: Vec<String>,
    ) -> anyhow::Result<ProcessId> {
        let session_id = SessionId(session_id.into());
        let process_goal = process_goal.into();
        
        info!(
            session_id = %session_id.0,
            goal = %process_goal,
            "Creating process via SessionHost skill"
        );
        
        let mut manager = self.process_manager.write().await;
        let process_id = manager.create_process(
            session_id,
            process_goal,
            tags,
        ).await?;
        
        Ok(process_id)
    }
    
    /// SKILL: 列出 Session 下的所有 Process
    pub async fn list_session_processes(
        &self,
        session_id: impl Into<String>,
    ) -> Vec<ProcessSummary> {
        let session_id = SessionId(session_id.into());
        
        let manager = self.process_manager.read().await;
        manager.list_processes_by_session(&session_id)
            .into_iter()
            .map(|p| ProcessSummary {
                process_id: p.process_id().0.clone(),
                goal: p.meta().process_goal.clone(),
                status: format!("{:?}", p.meta().status),
                thread_count: p.meta().thread_count,
                created_at: p.meta().created_at.to_rfc3339(),
                has_active_threads: p.has_active_threads(),
            })
            .collect()
    }
    
    /// SKILL: 获取 Process 详情
    pub async fn get_process_info(
        &self,
        process_id: &ProcessId,
    ) -> Option<ProcessDetail> {
        let manager = self.process_manager.read().await;
        manager.get_process(process_id).map(|p| ProcessDetail {
            process_id: p.process_id().0.clone(),
            session_id: p.meta().session_id.0.clone(),
            goal: p.meta().process_goal.clone(),
            status: format!("{:?}", p.meta().status),
            thread_count: p.meta().thread_count,
            created_at: p.meta().created_at.to_rfc3339(),
            updated_at: p.meta().updated_at.to_rfc3339(),
            tags: p.meta().tags.clone(),
            threads: p.list_threads().into_iter().map(|t| ThreadBrief {
                thread_id: t.thread_id.0.clone(),
                goal: t.task_goal.clone(),
                status: format!("{:?}", t.status),
                step_count: t.step_count,
            }).collect(),
        })
    }
    
    // ==================== Thread 管理 SKILL ====================
    
    /// SKILL: 在 Process 中创建 Thread
    /// 
    /// 参数：
    /// - process_id: Process ID
    /// - task_goal: Thread 目标
    /// - constraints: 约束条件
    /// - allowed_capabilities: 允许的能力
    /// 
    /// 返回：Thread ID
    pub async fn create_thread_in_process(
        &self,
        process_id: &ProcessId,
        task_goal: impl Into<String>,
        constraints: Vec<String>,
        allowed_capabilities: Vec<String>,
    ) -> anyhow::Result<ThreadId> {
        let task_goal = task_goal.into();
        
        info!(
            process_id = %process_id.0,
            goal = %task_goal,
            "Creating thread in process via SessionHost skill"
        );
        
        // 1. 获取 Process
        let manager = self.process_manager.write().await;
        let process = manager.get_process(process_id)
            .ok_or_else(|| anyhow::anyhow!("Process not found"))?
            .meta()
            .clone();
        
        let session_id = process.session_id.clone();
        drop(manager);  // 释放锁
        
        // 2. 创建 Thread
        let thread_id = ThreadId::new();
        let immutable_input = ImmutableInput {
            task_goal: task_goal.clone(),
            constraints,
            allowed_capabilities,
            forbidden_capabilities: vec![],
            session_context: std::collections::HashMap::new(),
            compiled_at: chrono::Utc::now(),
        };
        
        let thread_storage = ThreadStorage::create(
            &self.data_path,
            thread_id.clone(),
            session_id,
            immutable_input,
        ).await?;
        
        // 3. 将 Thread 添加到 Process
        let mut manager = self.process_manager.write().await;
        if let Some(process) = manager.get_process_mut(process_id) {
            process.add_thread(&thread_storage).await?;
        }
        
        info!(
            process_id = %process_id.0,
            thread_id = %thread_id.0,
            "Thread created and added to process"
        );
        
        Ok(thread_id)
    }
    
    /// SKILL: 启动 Process 中的 Thread Executor
    /// 
    /// 参数：
    /// - process_id: Process ID
    /// - thread_id: Thread ID
    /// - difficulty: LLM 难度级别（用于选择模型）
    /// 
    /// 返回：Executor ID
    pub async fn spawn_executor_in_process(
        &self,
        process_id: &ProcessId,
        thread_id: &ThreadId,
        difficulty: DifficultyLevel,
    ) -> anyhow::Result<String> {
        self.spawn_executor_in_process_with_events(
            process_id,
            thread_id,
            difficulty,
            None,
        ).await
    }

    /// SKILL: 在 Process 中启动 Thread Executor（带外部事件通道）
    ///
    /// 参数：
    /// - process_id: Process ID
    /// - thread_id: Thread ID
    /// - difficulty: LLM 难度级别
    /// - external_event_tx: 可选的外部事件发送器
    ///
    /// 返回：Executor ID
    pub async fn spawn_executor_in_process_with_events(
        &self,
        process_id: &ProcessId,
        thread_id: &ThreadId,
        difficulty: DifficultyLevel,
        external_event_tx: Option<tokio::sync::mpsc::Sender<crate::scheduler::thread_executor::ExecutorEvent>>,
    ) -> anyhow::Result<String> {
        info!(
            process_id = %process_id.0,
            thread_id = %thread_id.0,
            difficulty = ?difficulty,
            "Spawning executor in process via SessionHost skill"
        );

        // 1. 验证 Process 存在
        let manager = self.process_manager.read().await;
        if manager.get_process(process_id).is_none() {
            return Err(anyhow::anyhow!("Process not found"));
        }
        drop(manager);

        // 2. 加载 Thread
        let thread_storage = ThreadStorage::load(&self.data_path, thread_id
        ).await?;

        // 3. 创建 Executor
        let executor_id = crate::agent_thread::models::ExecutorId::new();
        let executor_id_str = executor_id.0.clone();
        let (internal_event_tx, _event_rx) = tokio::sync::mpsc::channel(100);
        let event_tx = external_event_tx.unwrap_or(internal_event_tx);
        
        let executor = ThreadExecutor::new(
            self.data_path.clone(),
            thread_id.clone(),
            self.coordinator.clone(),
            self.llm_router.clone(),
            self.context_builder.clone(),
            self.output_parser.clone(),
            event_tx.clone(),
        ).await?;
        
        // 4. 启动执行
        let process_id_str = process_id.0.clone();
        let thread_id_str = thread_id.0.clone();
        let executors = self.executors.clone();
        let process_manager = self.process_manager.clone();
        let data_path = self.data_path.clone();
        
        // Clone before moving into async block
        let executor_id_str_clone = executor_id_str.clone();
        
        let task_handle = tokio::spawn(async move {
            match executor.run().await {
                Ok(summary) => {
                    info!(
                        executor_id = %executor_id_str_clone,
                        steps = summary.steps_executed,
                        "Executor completed"
                    );
                }
                Err(e) => {
                    warn!(
                        executor_id = %executor_id_str_clone,
                        error = %e,
                        "Executor failed"
                    );
                }
            }
            
            // 更新 Process 状态
            let mut manager = process_manager.write().await;
            if let Some(process) = manager.get_process_mut(&ProcessId(process_id_str)) {
                let thread_id_clone = thread_id_str.clone();
                if let Ok(storage) = ThreadStorage::load(&data_path, &ThreadId(thread_id_str)).await {
                    let _ = process.update_thread_status(
                        &ThreadId(thread_id_clone), &storage
                    ).await;
                }
            }
            
            // 从 executors 中移除
            executors.write().await.remove(&executor_id_str_clone);
        });
        
        // 5. 存储 Executor 句柄
        let handle = ExecutorHandle {
            executor_id: executor_id_str.clone(),
            thread_id: thread_id.0.clone(),
            process_id: process_id.0.clone(),
            event_tx,
            task_handle: Some(task_handle),
        };
        
        self.executors.write().await.insert(executor_id_str.clone(), handle);
        
        // 6. 更新 Process 中的 Thread 状态
        let mut manager = self.process_manager.write().await;
        if let Some(process) = manager.get_process_mut(process_id) {
            process.update_thread_status(thread_id, &thread_storage).await?;
        }
        
        info!(
            executor_id = %executor_id_str,
            "Executor spawned successfully"
        );
        
        Ok(executor_id_str)
    }
    
    /// SKILL: 列出 Process 中的所有 Thread
    pub async fn list_process_threads(
        &self,
        process_id: &ProcessId,
    ) -> Vec<ThreadBrief> {
        let manager = self.process_manager.read().await;
        
        manager.get_process(process_id)
            .map(|p| {
                p.list_threads().into_iter().map(|t| ThreadBrief {
                    thread_id: t.thread_id.0.clone(),
                    goal: t.task_goal.clone(),
                    status: format!("{:?}", t.status),
                    step_count: t.step_count,
                }).collect()
            })
            .unwrap_or_default()
    }
    
    /// SKILL: 获取 Thread 在 Process 中的状态
    pub async fn get_thread_in_process_status(
        &self,
        process_id: &ProcessId,
        thread_id: &ThreadId,
    ) -> Option<ThreadStatusInProcess> {
        let manager = self.process_manager.read().await;

        let thread_summary = manager.get_process(process_id).and_then(|p| {
            p.list_threads().into_iter().find(|t| t.thread_id.0 == thread_id.0).cloned()
        });

        if let Some(t) = thread_summary {
            let is_active = self.executors.read().await.values()
                .any(|e| e.thread_id == thread_id.0);

            Some(ThreadStatusInProcess {
                thread_id: t.thread_id.0.clone(),
                process_id: process_id.0.clone(),
                status: format!("{:?}", t.status),
                current_phase: t.current_phase.clone(),
                step_count: t.step_count,
                is_active,
            })
        } else {
            None
        }
    }
    
    // ==================== 查询 SKILL ====================
    
    /// SKILL: 查找包含指定 Thread 的 Process
    pub async fn find_process_by_thread(
        &self,
        thread_id: &ThreadId,
    ) -> Option<ProcessId> {
        let manager = self.process_manager.read().await;
        manager.find_process_by_thread(thread_id)
            .map(|p| p.process_id().clone())
    }
    
    /// SKILL: 获取活跃 Process 列表
    pub async fn list_active_processes(
        &self,
    ) -> Vec<ProcessSummary> {
        let manager = self.process_manager.read().await;
        
        manager.list_processes().into_iter()
            .filter(|p| p.has_active_threads())
            .map(|p| ProcessSummary {
                process_id: p.process_id().0.clone(),
                goal: p.meta().process_goal.clone(),
                status: format!("{:?}", p.meta().status),
                thread_count: p.meta().thread_count,
                created_at: p.meta().created_at.to_rfc3339(),
                has_active_threads: true,
            })
            .collect()
    }
}

/// Process 摘要
#[derive(Debug, Clone)]
pub struct ProcessSummary {
    pub process_id: String,
    pub goal: String,
    pub status: String,
    pub thread_count: usize,
    pub created_at: String,
    pub has_active_threads: bool,
}

/// Process 详情
#[derive(Debug, Clone)]
pub struct ProcessDetail {
    pub process_id: String,
    pub session_id: String,
    pub goal: String,
    pub status: String,
    pub thread_count: usize,
    pub created_at: String,
    pub updated_at: String,
    pub tags: Vec<String>,
    pub threads: Vec<ThreadBrief>,
}

/// Thread 简要信息
#[derive(Debug, Clone)]
pub struct ThreadBrief {
    pub thread_id: String,
    pub goal: String,
    pub status: String,
    pub step_count: usize,
}

/// Thread 在 Process 中的状态
#[derive(Debug, Clone)]
pub struct ThreadStatusInProcess {
    pub thread_id: String,
    pub process_id: String,
    pub status: String,
    pub current_phase: String,
    pub step_count: usize,
    pub is_active: bool,
}