//! Agent Kernel gRPC Service Implementation
//! 
//! 提供 Thread 管理、执行协调、系统管理等功能

use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::Arc;
use std::time::{Duration, Instant};
use tokio::sync::{mpsc, RwLock};
use tokio_stream::wrappers::ReceiverStream;
use tonic::{Request, Response, Status};
use tracing::{debug, error, info, instrument, warn};

use crate::agent_thread::{
    models::{ThreadId, ThreadMeta, ThreadStatus, SessionId, ImmutableInput, Event as ModelsEvent, ExecutorId},
    storage::ThreadStorage,
};
use crate::block_composer::BlockComposerEngine;
use crate::coordinator::{
    ExecutionCoordinator, CoordinatorStats,
    lock_manager::DirectoryLockManager,
    skill_registry::SkillRegistry,
    ticket::TicketTracker,
};
use crate::skills::BashSkill;
use crate::llm::{LLMRouter, config::LLMRouterConfig};
use crate::scheduler::{
    ContextBuilder, OutputParser, ThreadExecutor, ExecutorState, ExecutorEvent as SchedulerExecutorEvent,
};

// Include generated proto code
pub mod proto {
    tonic::include_proto!("proclaw.agent.v1");
}

use proto::agent_kernel_server::AgentKernel;
// Use specific proto types with prefix to avoid ambiguity
use proto::{
    CreateThreadRequest, CreateThreadResponse,
    GetThreadStatusRequest, GetThreadStatusResponse,
    GetThreadHistoryRequest, GetThreadHistoryResponse,
    ControlExecutorRequest, ControlExecutorResponse,
    KillExecutorRequest, KillExecutorResponse,
    SpawnExecutorRequest, SpawnExecutorResponse,
    StreamExecutorEventsRequest,
    ExecuteSkillRequest, ExecuteSkillResponse,
    GetResourceStatusRequest, GetResourceStatusResponse,
    GetTicketStatusRequest, GetTicketStatusResponse,
    HealthCheckResponse,
    SystemStatusResponse,
    ShutdownRequest, ShutdownResponse,
    ThreadMeta as ProtoThreadMeta,
    Event as ProtoEvent,
    ExecutorEvent,
    ExecutorStatus,
    Artifact,
};

/// Agent Kernel 服务实现
pub struct AgentKernelService {
    // 配置
    config: AgentKernelConfig,
    
    // 基础设施
    coordinator: Arc<ExecutionCoordinator>,
    lock_manager: Arc<DirectoryLockManager>,
    block_composer: Arc<BlockComposerEngine>,
    llm_router: Arc<LLMRouter>,
    
    // 组件
    context_builder: Arc<ContextBuilder>,
    output_parser: Arc<OutputParser>,
    
    // 运行时状态
    threads: Arc<RwLock<HashMap<String, ThreadHandle>>>,
    executors: Arc<RwLock<HashMap<String, ExecutorHandle>>>,
    
    // 启动时间
    start_time: Instant,
}

/// Agent Kernel 配置
#[derive(Debug, Clone)]
pub struct AgentKernelConfig {
    pub data_path: PathBuf,
    pub llm_base_url: String,
    pub llm_api_key: String,
    pub llm_model: String,
}

impl Default for AgentKernelConfig {
    fn default() -> Self {
        Self {
            data_path: PathBuf::from("./data"),
            llm_base_url: "https://api.openai.com/v1".to_string(),
            llm_api_key: std::env::var("OPENAI_API_KEY").unwrap_or_default(),
            llm_model: "gpt-4".to_string(),
        }
    }
}

/// Thread 句柄
#[derive(Debug)]
struct ThreadHandle {
    storage: ThreadStorage,
    created_at: std::time::Instant,
}

/// Executor 句柄
#[derive(Debug)]
struct ExecutorHandle {
    executor_id: String,
    thread_id: String,
    state: ExecutorState,
    event_tx: mpsc::Sender<SchedulerExecutorEvent>,
    task_handle: Option<tokio::task::JoinHandle<()>>,
}

impl AgentKernelService {
    /// 创建新的服务实例
    pub async fn new(
        config: AgentKernelConfig,
        block_composer: Arc<BlockComposerEngine>,
    ) -> anyhow::Result<Self> {
        info!("Initializing AgentKernel service");
        
        // 创建数据目录
        let threads_path = config.data_path.join("threads");
        tokio::fs::create_dir_all(&threads_path).await?;
        
        // 初始化 LLM Router
        let llm_config = LLMRouterConfig::from_env();
        let llm_router = Arc::new(LLMRouter::new(llm_config));
        info!("LLM Router initialized with multiple providers");
        
        // 初始化 Coordinator
        let lock_manager = Arc::new(
            DirectoryLockManager::new(config.data_path.join("locks.db"))?
        );
        
        // 创建 Bash Skill
        let bash_config = crate::providers::bash::BashWrapperConfig {
            timeout_seconds: 60,
            max_output_size: 10 * 1024 * 1024,  // 10MB
            blocked_commands: vec!["rm -rf /".to_string(), ":(){ :|:& };:".to_string()],
            custom_patterns: vec![],
        };
        let bash_skill = Arc::new(BashSkill::new(
            std::sync::Arc::new(crate::providers::bash::BashWrapper::new(bash_config))
        ));
        
        // 创建 Skill Registry
        let skill_registry = Arc::new(SkillRegistry::new(bash_skill));
        let ticket_tracker = Arc::new(TicketTracker::new());
        
        let coordinator = Arc::new(ExecutionCoordinator::new(
            lock_manager.clone(),
            skill_registry,
            ticket_tracker,
        ));
        
        // 初始化 Context Builder
        let context_builder = Arc::new(ContextBuilder::new(block_composer.clone()));
        
        // 初始化 Output Parser
        let output_parser = Arc::new(OutputParser::new());
        
        info!("AgentKernel service initialized");
        
        Ok(Self {
            config,
            coordinator,
            lock_manager,
            block_composer,
            llm_router,
            context_builder,
            output_parser,
            threads: Arc::new(RwLock::new(HashMap::new())),
            executors: Arc::new(RwLock::new(HashMap::new())),
            start_time: Instant::now(),
        })
    }
    
    /// 启动后台任务（锁清理等）
    pub async fn start_background_tasks(&self,
    ) {
        let lock_manager = self.lock_manager.clone();
        
        // 启动锁清理任务
        tokio::spawn(async move {
            let mut interval = tokio::time::interval(Duration::from_secs(30));
            loop {
                interval.tick().await;
                if let Err(e) = lock_manager.cleanup_expired().await {
                    warn!("Lock cleanup failed: {}", e);
                }
            }
        });
        
        info!("Background tasks started");
    }
}

#[tonic::async_trait]
impl AgentKernel for AgentKernelService {
    // ==================== Thread 管理 ====================
    
    #[instrument(skip(self, request))]
    async fn create_thread(
        &self,
        request: Request<CreateThreadRequest>,
    ) -> Result<Response<CreateThreadResponse>, Status> {
        let req = request.into_inner();
        
        info!(
            session_id = %req.session_id,
            task_goal = %req.task_goal,
            "Creating new thread"
        );
        
        let thread_id = ThreadId::new();
        let session_id = SessionId(req.session_id);
        
        let immutable_input = ImmutableInput {
            task_goal: req.task_goal,
            constraints: req.constraints,
            allowed_capabilities: req.allowed_capabilities,
            forbidden_capabilities: vec![],
            session_context: req.session_context.into_iter()
                .map(|(k, v)| (k, serde_json::Value::String(v)))
                .collect(),
            compiled_at: chrono::Utc::now(),
        };
        
        match ThreadStorage::create(
            &self.config.data_path,
            thread_id.clone(),
            session_id,
            immutable_input,
        ).await {
            Ok(storage) => {
                let thread_id_str = thread_id.0.clone();
                
                let handle = ThreadHandle {
                    storage,
                    created_at: Instant::now(),
                };
                
                self.threads.write().await.insert(thread_id_str.clone(), handle);
                
                info!(thread_id = %thread_id_str, "Thread created successfully");
                
                Ok(Response::new(CreateThreadResponse {
                    thread_id: thread_id_str,
                    success: true,
                    error_message: String::new(),
                }))
            }
            Err(e) => {
                error!(error = %e, "Failed to create thread");
                Ok(Response::new(CreateThreadResponse {
                    thread_id: String::new(),
                    success: false,
                    error_message: e.to_string(),
                }))
            }
        }
    }
    
    #[instrument(skip(self, request))]
    async fn spawn_executor(
        &self,
        request: Request<SpawnExecutorRequest>,
    ) -> Result<Response<SpawnExecutorResponse>, Status> {
        let req = request.into_inner();
        let thread_id = ThreadId(req.thread_id.clone());
        
        info!(thread_id = %req.thread_id, "Spawning executor");
        
        // 检查 Thread 是否存在
        let storage = match ThreadStorage::load(&self.config.data_path, &thread_id).await {
            Ok(s) => s,
            Err(e) => {
                return Ok(Response::new(SpawnExecutorResponse {
                    executor_id: String::new(),
                    success: false,
                    error_message: format!("Thread not found: {}", e),
                }));
            }
        };
        
        // 检查是否已有活跃的 Executor
        let executors = self.executors.read().await;
        for (id, handle) in executors.iter() {
            if handle.thread_id == req.thread_id && handle.state == ExecutorState::Running {
                return Ok(Response::new(SpawnExecutorResponse {
                    executor_id: id.clone(),
                    success: false,
                    error_message: "Thread already has an active executor".to_string(),
                }));
            }
        }
        drop(executors);
        
        // 创建 Executor
        let executor_id = ExecutorId::new();
        let executor_id_str = executor_id.0.clone();
        let (event_tx, mut event_rx) = mpsc::channel(100);
        let event_tx_clone = event_tx.clone();
        
        let executor = match ThreadExecutor::new(
            self.config.data_path.clone(),
            thread_id,
            self.coordinator.clone(),
            self.llm_router.clone(),
            self.context_builder.clone(),
            self.output_parser.clone(),
            event_tx,
        ).await {
            Ok(e) => e,
            Err(e) => {
                return Ok(Response::new(SpawnExecutorResponse {
                    executor_id: String::new(),
                    success: false,
                    error_message: format!("Failed to create executor: {}", e),
                }));
            }
        };
        
        // 启动执行
        let max_steps = if req.max_steps > 0 { req.max_steps as usize } else { 100 };
        let executor_id_str_clone = executor_id_str.clone();
        let task_handle = tokio::spawn(async move {
            match executor.run().await {
                Ok(summary) => {
                    info!(
                        executor_id = %executor_id_str_clone,
                        steps = summary.steps_executed,
                        "Executor completed successfully"
                    );
                }
                Err(e) => {
                    error!(
                        executor_id = %executor_id_str_clone,
                        error = %e,
                        "Executor failed"
                    );
                }
            }
        });
        
        // 存储 Executor 句柄
        let handle = ExecutorHandle {
            executor_id: executor_id_str.clone(),
            thread_id: req.thread_id.clone(),
            state: ExecutorState::Running,
            event_tx: event_tx_clone,
            task_handle: Some(task_handle),
        };
        
        self.executors.write().await.insert(executor_id_str.clone(), handle);
        
        // 更新 Thread 状态
        if let Some(thread_handle) = self.threads.write().await.get_mut(&req.thread_id) {
            let mut meta = thread_handle.storage.read_meta().await
                .map_err(|e| Status::internal(e.to_string()))?;
            meta.status = ThreadStatus::Active;
            thread_handle.storage.update_meta(&meta).await
                .map_err(|e| Status::internal(e.to_string()))?;
        }
        
        info!(executor_id = %executor_id_str, "Executor spawned successfully");
        
        Ok(Response::new(SpawnExecutorResponse {
            executor_id: executor_id_str,
            success: true,
            error_message: String::new(),
        }))
    }
    
    #[instrument(skip(self, request))]
    async fn control_executor(
        &self,
        request: Request<ControlExecutorRequest>,
    ) -> Result<Response<ControlExecutorResponse>, Status> {
        let req = request.into_inner();
        
        info!(
            executor_id = %req.executor_id,
            action = ?req.action(),
            "Controlling executor"
        );
        
        let mut executors = self.executors.write().await;
        
        match executors.get_mut(&req.executor_id) {
            Some(handle) => {
                let new_status = match req.action() {
                    proto::control_executor_request::ControlAction::ControlPause => {
                        handle.state = ExecutorState::Paused;
                        proto::ExecutorStatus::ExecutorPaused
                    }
                    proto::control_executor_request::ControlAction::ControlResume => {
                        handle.state = ExecutorState::Running;
                        proto::ExecutorStatus::ExecutorRunning
                    }
                    proto::control_executor_request::ControlAction::ControlCancel => {
                        handle.state = ExecutorState::Error;
                        proto::ExecutorStatus::ExecutorError
                    }
                };
                
                Ok(Response::new(ControlExecutorResponse {
                    success: true,
                    error_message: String::new(),
                    new_status: new_status as i32,
                }))
            }
            None => Ok(Response::new(ControlExecutorResponse {
                success: false,
                error_message: "Executor not found".to_string(),
                new_status: ExecutorStatus::ExecutorError as i32,
            })),
        }
    }
    
    #[instrument(skip(self, request))]
    async fn kill_executor(
        &self,
        request: Request<KillExecutorRequest>,
    ) -> Result<Response<KillExecutorResponse>, Status> {
        let req = request.into_inner();
        
        info!(executor_id = %req.executor_id, "Killing executor");
        
        let mut executors = self.executors.write().await;
        
        match executors.remove(&req.executor_id) {
            Some(handle) => {
                // 取消任务
                if let Some(task) = handle.task_handle {
                    task.abort();
                }
                
                // 更新 Thread 状态
                if let Some(thread_handle) = self.threads.write().await.get_mut(&handle.thread_id) {
                    if let Ok(mut meta) = thread_handle.storage.read_meta().await {
                        meta.status = ThreadStatus::Paused;
                        let _ = thread_handle.storage.update_meta(&meta).await;
                    }
                }
                
                Ok(Response::new(KillExecutorResponse {
                    success: true,
                    thread_id: handle.thread_id,
                }))
            }
            None => Ok(Response::new(KillExecutorResponse {
                success: false,
                thread_id: String::new(),
            })),
        }
    }
    
    type StreamExecutorEventsStream = ReceiverStream<Result<ExecutorEvent, Status>>;
    
    #[instrument(skip(self, request))]
    async fn stream_executor_events(
        &self,
        request: Request<StreamExecutorEventsRequest>,
    ) -> Result<Response<Self::StreamExecutorEventsStream>, Status> {
        let req = request.into_inner();
        
        let (tx, rx) = mpsc::channel(100);
        
        // 这里应该连接到实际的 Executor 事件流
        // 简化实现：发送一个启动事件
        let _ = tx.send(Ok(proto::ExecutorEvent {
            timestamp: Some(prost_types::Timestamp::from(std::time::SystemTime::now())),
            event_type: proto::executor_event::EventType::StepStarted as i32,
            executor_id: req.executor_id.clone(),
            thread_id: String::new(),
            step_number: 1,
            message: "Event streaming started".to_string(),
            payload: HashMap::new(),
        })).await;
        
        Ok(Response::new(ReceiverStream::new(rx)))
    }
    
    #[instrument(skip(self, request))]
    async fn get_thread_history(
        &self,
        request: Request<GetThreadHistoryRequest>,
    ) -> Result<Response<GetThreadHistoryResponse>, Status> {
        let req = request.into_inner();
        let thread_id = ThreadId(req.thread_id.clone());
        
        let storage = match ThreadStorage::load(&self.config.data_path, &thread_id).await {
            Ok(s) => s,
            Err(_) => {
                return Ok(Response::new(GetThreadHistoryResponse {
                    thread_id: req.thread_id,
                    meta: None,
                    events: vec![],
                    artifacts: vec![],
                }));
            }
        };
        
        let meta = storage.read_meta().await.ok();
        let events = if req.include_events {
            storage.read_event_log().await
                .unwrap_or_default()
                .into_iter()
                .map(|e| ProtoEvent {
                    event_id: e.event_id,
                    timestamp: Some(prost_types::Timestamp {
                        seconds: e.timestamp.timestamp(),
                        nanos: e.timestamp.timestamp_subsec_nanos() as i32,
                    }),
                    event_type: format!("{:?}", e.event_type),
                    step_number: e.step_number as i32,
                    phase: format!("{:?}", e.phase),
                    content_json: serde_json::to_string(&e.content).unwrap_or_default(),
                })
                .collect()
        } else {
            vec![]
        };
        
        let artifacts = if req.include_artifacts {
            storage.list_artifacts().await
                .unwrap_or_default()
                .into_iter()
                .map(|a| Artifact {
                    slot_id: a.slot_id,
                    artifact_type: format!("{:?}", a.artifact_type),
                    content_json: serde_json::to_string(&a.content).unwrap_or_default(),
                    priority: a.priority,
                    created_at: Some(prost_types::Timestamp {
                        seconds: a.created_at.timestamp(),
                        nanos: a.created_at.timestamp_subsec_nanos() as i32,
                    }),
                })
                .collect()
        } else {
            vec![]
        };
        
        let proto_meta = meta.map(|m| ProtoThreadMeta {
            thread_id: m.thread_id.0,
            session_id: m.session_id.0,
            created_at: Some(prost_types::Timestamp {
                seconds: m.created_at.timestamp(),
                nanos: m.created_at.timestamp_subsec_nanos() as i32,
            }),
            updated_at: Some(prost_types::Timestamp {
                seconds: m.updated_at.timestamp(),
                nanos: m.updated_at.timestamp_subsec_nanos() as i32,
            }),
            current_phase: format!("{:?}", m.current_phase),
            step_count: m.step_count as i32,
            status: match m.status {
                ThreadStatus::Created => proto::ThreadStatus::Created as i32,
                ThreadStatus::Active => proto::ThreadStatus::Active as i32,
                ThreadStatus::Paused => proto::ThreadStatus::Paused as i32,
                ThreadStatus::Completed => proto::ThreadStatus::Completed as i32,
                ThreadStatus::Error => proto::ThreadStatus::Error as i32,
            },
        });
        
        Ok(Response::new(GetThreadHistoryResponse {
            thread_id: req.thread_id,
            meta: proto_meta,
            events,
            artifacts,
        }))
    }
    
    #[instrument(skip(self, request))]
    async fn get_thread_status(
        &self,
        request: Request<GetThreadStatusRequest>,
    ) -> Result<Response<GetThreadStatusResponse>, Status> {
        let req = request.into_inner();
        let thread_id = ThreadId(req.thread_id.clone());
        
        let storage = match ThreadStorage::load(&self.config.data_path, &thread_id).await {
            Ok(s) => s,
            Err(_) => {
                return Ok(Response::new(GetThreadStatusResponse {
                    thread_id: req.thread_id,
                    status: proto::ThreadStatus::Error as i32,
                    current_phase: String::new(),
                    step_count: 0,
                    has_active_executor: false,
                    active_executor_id: String::new(),
                }));
            }
        };
        
        let meta = storage.read_meta().await
            .map_err(|e| Status::internal(e.to_string()))?;
        
        // 查找活跃的 Executor
        let executors = self.executors.read().await;
        let active_executor = executors.values()
            .find(|e| e.thread_id == req.thread_id && e.state == ExecutorState::Running);
        
        Ok(Response::new(GetThreadStatusResponse {
            thread_id: req.thread_id,
            status: match meta.status {
                ThreadStatus::Created => proto::ThreadStatus::Created as i32,
                ThreadStatus::Active => proto::ThreadStatus::Active as i32,
                ThreadStatus::Paused => proto::ThreadStatus::Paused as i32,
                ThreadStatus::Completed => proto::ThreadStatus::Completed as i32,
                ThreadStatus::Error => proto::ThreadStatus::Error as i32,
            },
            current_phase: format!("{:?}", meta.current_phase),
            step_count: meta.step_count as i32,
            has_active_executor: active_executor.is_some(),
            active_executor_id: active_executor.map(|e| e.executor_id.clone()).unwrap_or_default(),
        }))
    }
    
    // ==================== 执行协调 ====================
    
    #[instrument(skip(self, request))]
    async fn execute_skill(
        &self,
        request: Request<ExecuteSkillRequest>,
    ) -> Result<Response<ExecuteSkillResponse>, Status> {
        let req = request.into_inner();
        
        debug!(
            request_id = %req.request_id,
            skill = %req.skill_name,
            tool = %req.tool_name,
            "Executing skill"
        );
        
        let parameters: serde_json::Value = match serde_json::from_str(&req.parameters_json) {
            Ok(v) => v,
            Err(e) => {
                return Ok(Response::new(ExecuteSkillResponse {
                    request_id: req.request_id,
                    success: false,
                    result_json: String::new(),
                    error_message: format!("Invalid parameters JSON: {}", e),
                    execution_time_ms: 0,
                }));
            }
        };
        
        let context = req.context.unwrap_or_default();
        
        let skill_request = crate::coordinator::models::SkillRequest {
            request_id: req.request_id.clone(),
            skill_name: req.skill_name,
            tool_name: req.tool_name,
            parameters,
            context: crate::coordinator::models::SkillContext {
                thread_id: context.thread_id,
                session_id: context.session_id,
                executor_id: context.executor_id,
                capability_level: crate::auth::CapabilityLevel::Agent,  // Default to Agent for now
                working_dirs: context.working_dirs,
            },
        };
        
        match self.coordinator.execute_skill(skill_request).await {
            Ok(result) => Ok(Response::new(ExecuteSkillResponse {
                request_id: result.request_id,
                success: result.success,
                result_json: result.result.map(|v| v.to_string()).unwrap_or_default(),
                error_message: result.error.unwrap_or_default(),
                execution_time_ms: result.execution_time_ms as i64,
            })),
            Err(e) => Ok(Response::new(ExecuteSkillResponse {
                request_id: req.request_id,
                success: false,
                result_json: String::new(),
                error_message: e.to_string(),
                execution_time_ms: 0,
            })),
        }
    }
    
    #[instrument(skip(self, request))]
    async fn get_resource_status(
        &self,
        request: Request<GetResourceStatusRequest>,
    ) -> Result<Response<GetResourceStatusResponse>, Status> {
        let req = request.into_inner();
        
        // 简化实现：返回所有请求的目录状态
        let locks: Vec<_> = req.directory_paths.into_iter()
            .map(|path| proto::get_resource_status_response::DirectoryLockStatus {
                directory_path: path,
                is_locked: false,  // TODO: 查询实际锁状态
                holder_executor_id: String::new(),
                queue_length: 0,
            })
            .collect();
        
        Ok(Response::new(GetResourceStatusResponse { locks }))
    }
    
    #[instrument(skip(self, request))]
    async fn get_ticket_status(
        &self,
        request: Request<GetTicketStatusRequest>,
    ) -> Result<Response<GetTicketStatusResponse>, Status> {
        let req = request.into_inner();
        
        // 简化实现：返回未知状态
        Ok(Response::new(GetTicketStatusResponse {
            ticket_id: req.ticket_id,
            status: proto::get_ticket_status_response::TicketStatus::TicketPending as i32,
            skill_name: String::new(),
            error_message: String::new(),
        }))
    }
    
    // ==================== 系统管理 ====================
    
    #[instrument(skip(self))]
    async fn health_check(
        &self,
        _request: Request<()>,
    ) -> Result<Response<HealthCheckResponse>, Status> {
        Ok(Response::new(HealthCheckResponse {
            healthy: true,
            version: env!("CARGO_PKG_VERSION").to_string(),
            uptime_seconds: self.start_time.elapsed().as_secs() as i64,
        }))
    }
    
    #[instrument(skip(self))]
    async fn get_system_status(
        &self,
        _request: Request<()>,
    ) -> Result<Response<SystemStatusResponse>, Status> {
        let threads = self.threads.read().await;
        let executors = self.executors.read().await;
        let stats = self.coordinator.get_stats().await;
        
        Ok(Response::new(SystemStatusResponse {
            active_threads: threads.len() as i32,
            active_executors: executors.len() as i32,
            pending_tickets: 0,  // TODO: 从 TicketTracker 获取
            total_executions: stats.total_executions as i64,
            total_wait_time_ms: stats.total_wait_time_ms as i64,
            skill_stats: HashMap::new(),  // TODO: 统计 Skill 使用情况
        }))
    }
    
    #[instrument(skip(self, request))]
    async fn shutdown(
        &self,
        request: Request<ShutdownRequest>,
    ) -> Result<Response<ShutdownResponse>, Status> {
        let req = request.into_inner();
        let timeout = if req.timeout_seconds > 0 {
            req.timeout_seconds
        } else {
            10
        };
        
        info!(timeout_seconds = timeout, "Shutting down AgentKernel");
        
        // 停止所有 Executor
        let mut executors = self.executors.write().await;
        for (id, handle) in executors.drain() {
            info!(executor_id = %id, "Stopping executor");
            if let Some(task) = handle.task_handle {
                task.abort();
            }
        }
        
        Ok(Response::new(ShutdownResponse {
            success: true,
            message: format!("AgentKernel shutdown completed (timeout: {}s)", timeout),
        }))
    }
}