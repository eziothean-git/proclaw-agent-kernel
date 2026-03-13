//! Thread Manager - 管理所有运行中的 ThreadExecutor
//! 
//! 职责：
//! - 启动、暂停、恢复、取消 Thread
//! - 维护 Thread 状态
//! - 提供 Thread 查询接口

use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::Arc;
use dashmap::DashMap;
use tokio::sync::{mpsc, Mutex, RwLock};
use tracing::{debug, error, info, instrument, warn};

use crate::agent_thread::{
    models::{ExecutionPhase, ThreadId, ThreadStatus, SessionId, ImmutableInput},
    storage::ThreadStorage,
};
use crate::coordinator::ExecutionCoordinator;
use crate::llm::LLMRouter;
use crate::scheduler::{
    context_builder::ContextBuilder,
    output_parser::OutputParser,
    thread_executor::{ThreadExecutor, ExecutorState, ExecutorEvent, CompletionReason},
};

/// Thread 运行时信息
#[derive(Debug, Clone)]
pub struct ThreadInfo {
    pub thread_id: ThreadId,
    pub session_id: SessionId,
    pub status: ThreadStatus,
    pub current_phase: ExecutionPhase,
    pub step_count: usize,
    pub started_at: Option<chrono::DateTime<chrono::Utc>>,
    pub updated_at: Option<chrono::DateTime<chrono::Utc>>,
    pub executor_id: Option<String>,
}

/// Thread 管理器
/// 
/// SAFETY: ThreadManager is Send + Sync because all its fields are Send + Sync
pub struct ThreadManager {
    // Thread 存储根目录
    base_path: PathBuf,
    
    // 基础设施
    coordinator: Arc<ExecutionCoordinator>,
    llm_router: Arc<LLMRouter>,
    context_builder: Arc<ContextBuilder>,
    output_parser: Arc<OutputParser>,
    
    // 运行中的 Executor
    // thread_id -> (executor_state, event_sender, abort_handle)
    executors: Arc<DashMap<ThreadId, ExecutorHandle>>,
    
    // Thread 历史记录
    thread_history: Arc<RwLock<HashMap<ThreadId, ThreadHistory>>>,
}

/// Executor 句柄
#[derive(Debug)]
struct ExecutorHandle {
    state: Arc<RwLock<ExecutorState>>,
    event_tx: mpsc::Sender<ExecutorEvent>,
    join_handle: Arc<Mutex<tokio::task::JoinHandle<()>>>,
}

/// Thread 历史记录
#[derive(Debug, Clone)]
pub struct ThreadHistory {
    pub thread_id: ThreadId,
    pub session_id: SessionId,
    pub events: Vec<HistoryEvent>,
    pub created_at: chrono::DateTime<chrono::Utc>,
    pub completed_at: Option<chrono::DateTime<chrono::Utc>>,
    pub final_status: Option<ThreadStatus>,
}

/// 历史事件
#[derive(Debug, Clone)]
pub struct HistoryEvent {
    pub timestamp: chrono::DateTime<chrono::Utc>,
    pub event_type: String,
    pub details: serde_json::Value,
}

impl ThreadManager {
    /// 创建新的 ThreadManager
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
            executors: Arc::new(DashMap::new()),
            thread_history: Arc::new(RwLock::new(HashMap::new())),
        }
    }
    
    /// 创建新 Thread
    #[instrument(skip(self, immutable_input), fields(session_id = %session_id.0))]
    pub async fn create_thread(
        &self,
        session_id: SessionId,
        immutable_input: ImmutableInput,
    ) -> anyhow::Result<ThreadId> {
        let thread_id = ThreadId::new();
        
        // 创建 Thread 存储
        ThreadStorage::create(
            &self.base_path,
            thread_id.clone(),
            session_id.clone(),
            immutable_input,
        ).await?;
        
        info!(
            thread_id = %thread_id.0,
            session_id = %session_id.0,
            "Created new thread"
        );
        
        // 初始化历史记录
        {
            let mut history = self.thread_history.write().await;
            history.insert(thread_id.clone(), ThreadHistory {
                thread_id: thread_id.clone(),
                session_id: session_id.clone(),
                events: Vec::new(),
                created_at: chrono::Utc::now(),
                completed_at: None,
                final_status: None,
            });
        }
        
        Ok(thread_id)
    }
    
    /// 启动 Thread（创建并运行 Executor）
    #[instrument(skip(self), fields(thread_id = %thread_id.0))]
    pub async fn spawn_thread(
        &self,
        thread_id: ThreadId,
    ) -> anyhow::Result<String> {
        // 检查 Thread 是否已存在
        if self.executors.contains_key(&thread_id) {
            return Err(anyhow::anyhow!("Thread {} is already running", thread_id.0));
        }
        
        // 检查 Thread 存储是否存在
        if !ThreadStorage::exists(&self.base_path, &thread_id).await {
            return Err(anyhow::anyhow!("Thread {} not found", thread_id.0));
        }
        
        // 创建事件通道
        let (event_tx, mut event_rx) = mpsc::channel::<ExecutorEvent>(100);
        
        // 创建 Executor
        let executor = ThreadExecutor::new(
            self.base_path.clone(),
            thread_id.clone(),
            self.coordinator.clone(),
            self.llm_router.clone(),
            self.context_builder.clone(),
            self.output_parser.clone(),
            event_tx.clone(),
        ).await?;
        
        let executor_id = executor.executor_id().clone();
        
        // 启动 Executor 任务
        let thread_id_clone = thread_id.clone();
        let history = self.thread_history.clone();
        let executors = self.executors.clone();
        
        let handle = tokio::spawn(async move {
            // 运行 Executor
            let result = executor.run().await;
            
            // 记录完成状态
            if let Ok(summary) = result {
                let mut history_guard = history.write().await;
                if let Some(h) = history_guard.get_mut(&thread_id_clone) {
                    h.completed_at = Some(chrono::Utc::now());
                    h.final_status = Some(summary.final_status);
                }
            }
            
            // 从运行列表中移除
            executors.remove(&thread_id_clone);
            
            info!(thread_id = %thread_id_clone.0, "Thread executor completed");
        });
        
        // 启动事件收集任务
        let history = self.thread_history.clone();
        let thread_id_for_events = thread_id.clone();
        tokio::spawn(async move {
            while let Some(event) = event_rx.recv().await {
                let event_record = HistoryEvent {
                    timestamp: chrono::Utc::now(),
                    event_type: format!("{:?}", std::mem::discriminant(&event)),
                    details: serde_json::json!({
                        "event": format!("{:?}", event),
                    }),
                };
                
                let mut history_guard = history.write().await;
                if let Some(h) = history_guard.get_mut(&thread_id_for_events) {
                    h.events.push(event_record);
                }
            }
        });
        
        // Log before moving thread_id
        let thread_id_str = thread_id.0.clone();
        let executor_id_str = executor_id.0.clone();
        
        // 保存到运行列表
        self.executors.insert(thread_id, ExecutorHandle {
            state: Arc::new(RwLock::new(crate::scheduler::thread_executor::ExecutorState::Running)),
            event_tx,
            join_handle: Arc::new(Mutex::new(handle)),
        });
        
        info!(
            thread_id = %thread_id_str,
            executor_id = %executor_id_str,
            "Spawned thread executor"
        );
        
        Ok(executor_id.0)
    }
    
    /// 暂停 Thread
    #[instrument(skip(self), fields(thread_id = %thread_id.0))]
    pub async fn pause_thread(
        &self,
        thread_id: &ThreadId,
    ) -> anyhow::Result<()> {
        if let Some(handle) = self.executors.get(thread_id).map(|entry| entry.state.clone()) {
            // 发送暂停信号（通过事件通道）
            // 注意：实际暂停逻辑在 Executor 内部处理
            // 这里只是记录状态
            let mut state = handle.write().await;
            *state = crate::scheduler::thread_executor::ExecutorState::Paused;
            
            info!(thread_id = %thread_id.0, "Paused thread");
            Ok(())
        } else {
            Err(anyhow::anyhow!("Thread {} is not running", thread_id.0))
        }
    }
    
    /// 恢复 Thread
    #[instrument(skip(self), fields(thread_id = %thread_id.0))]
    pub async fn resume_thread(
        &self,
        thread_id: &ThreadId,
    ) -> anyhow::Result<()> {
        if let Some(handle) = self.executors.get(thread_id).map(|entry| entry.state.clone()) {
            let mut state = handle.write().await;
            *state = crate::scheduler::thread_executor::ExecutorState::Running;
            
            info!(thread_id = %thread_id.0, "Resumed thread");
            Ok(())
        } else {
            Err(anyhow::anyhow!("Thread {} is not running", thread_id.0))
        }
    }
    
    /// 取消 Thread
    #[instrument(skip(self), fields(thread_id = %thread_id.0))]
    pub async fn cancel_thread(
        &self,
        thread_id: &ThreadId,
    ) -> anyhow::Result<()> {
        if let Some((_, handle)) = self.executors.remove(thread_id) {
            // 取消任务
            let join_handle = handle.join_handle.lock().await;
            join_handle.abort();
            
            info!(thread_id = %thread_id.0, "Cancelled thread");
            Ok(())
        } else {
            Err(anyhow::anyhow!("Thread {} is not running", thread_id.0))
        }
    }
    
    /// 列出所有运行中的 Threads
    pub async fn list_running_threads(&self) -> Vec<ThreadInfo> {
        let mut threads = Vec::new();

        let executor_snapshots: Vec<(ThreadId, Arc<RwLock<ExecutorState>>)> = self.executors
            .iter()
            .map(|entry| (entry.key().clone(), entry.value().state.clone()))
            .collect();

        for (thread_id, state_handle) in executor_snapshots {
            // 尝试从存储读取最新状态
            if let Ok(storage) = ThreadStorage::load(&self.base_path, &thread_id).await {
                if let Ok(meta) = storage.read_meta().await {
                    let state = state_handle.read().await;
                    let status = match *state {
                        crate::scheduler::thread_executor::ExecutorState::Paused => ThreadStatus::Paused,
                        crate::scheduler::thread_executor::ExecutorState::Running => ThreadStatus::Active,
                        crate::scheduler::thread_executor::ExecutorState::Completed => ThreadStatus::Completed,
                        crate::scheduler::thread_executor::ExecutorState::Error => ThreadStatus::Error,
                        _ => meta.status,
                    };
                    
                    threads.push(ThreadInfo {
                        thread_id,
                        session_id: meta.session_id.clone(),
                        status,
                        current_phase: meta.current_phase,
                        step_count: meta.step_count,
                        started_at: Some(meta.created_at),
                        updated_at: Some(meta.updated_at),
                        executor_id: None, // TODO: track executor_id
                    });
                }
            }
        }
        
        threads
    }
    
    /// 获取 Thread 信息
    pub async fn get_thread_info(&self, thread_id: &ThreadId) -> anyhow::Result<ThreadInfo> {
        let storage = ThreadStorage::load(&self.base_path, thread_id).await?;
        let meta = storage.read_meta().await?;
        
        // 检查是否正在运行
        let state_handle = self.executors.get(thread_id).map(|entry| entry.state.clone());
        let status = if let Some(state_handle) = state_handle {
            let state = state_handle.read().await;
            match *state {
                crate::scheduler::thread_executor::ExecutorState::Paused => ThreadStatus::Paused,
                crate::scheduler::thread_executor::ExecutorState::Running => ThreadStatus::Active,
                crate::scheduler::thread_executor::ExecutorState::Completed => ThreadStatus::Completed,
                crate::scheduler::thread_executor::ExecutorState::Error => ThreadStatus::Error,
                _ => meta.status,
            }
        } else {
            meta.status
        };
        
        Ok(ThreadInfo {
            thread_id: thread_id.clone(),
            session_id: meta.session_id.clone(),
            status,
            current_phase: meta.current_phase,
            step_count: meta.step_count,
            started_at: Some(meta.created_at),
            updated_at: Some(meta.updated_at),
            executor_id: None,
        })
    }
    
    /// 获取 Thread 日志
    pub async fn get_thread_log(&self, thread_id: &ThreadId) -> anyhow::Result<ThreadHistory> {
        let history = self.thread_history.read().await;
        history.get(thread_id)
            .cloned()
            .ok_or_else(|| anyhow::anyhow!("Thread {} not found in history", thread_id.0))
    }
    
    /// 获取所有 Thread 历史（用于查询）
    pub async fn get_all_history(&self) -> Vec<ThreadHistory> {
        let history = self.thread_history.read().await;
        history.values().cloned().collect()
    }
}

// Compile-time assertions for Send + Sync
#[cfg(test)]
mod tests {
    use super::*;
    use crate::scheduler::thread_executor::ThreadExecutor;
    
    fn assert_send<T: Send>() {}
    fn assert_sync<T: Sync>() {}
    
    #[test]
    fn test_thread_manager_is_send_sync() {
        assert_send::<ThreadManager>();
        assert_sync::<ThreadManager>();
    }
    
    #[test]
    fn test_executor_handle_is_send_sync() {
        assert_send::<ExecutorHandle>();
        assert_sync::<ExecutorHandle>();
    }
    
    #[test]
    fn test_thread_executor_is_send_sync() {
        assert_send::<ThreadExecutor>();
        assert_sync::<ThreadExecutor>();
    }
}
