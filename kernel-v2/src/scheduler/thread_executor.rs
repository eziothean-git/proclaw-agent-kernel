//! Thread Executor - 执行 SEE-ACT-UPDATE 循环的程序
//! 
//! 职责：
//! 1. 从 Agent Thread 文件加载历史
//! 2. 执行 SEE-ACT-UPDATE 循环
//! 3. 更新 Agent Thread 文件
//! 4. 向 Session Host 报告事件

use std::path::PathBuf;
use std::sync::Arc;
use tokio::sync::mpsc;
use tracing::{error, info, instrument};

use crate::agent_thread::{
    models::*,
    storage::ThreadStorage,
};
use crate::coordinator::{
    ExecutionCoordinator,
    models::{SkillContext, SkillRequest},
};
use crate::auth::CapabilityLevel;
use crate::llm::{LLMRouter, config::DifficultyLevel};
use crate::scheduler::context_builder::{ContextBuilder, WorkingSet};
use crate::scheduler::output_parser::OutputParser;

/// Thread Executor 状态
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ExecutorState {
    Initializing,
    Running,
    Paused,
    Completed,
    Error,
}

/// Thread Executor - 执行程序
pub struct ThreadExecutor {
    executor_id: ExecutorId,
    storage: ThreadStorage,
    
    // 基础设施
    coordinator: Arc<ExecutionCoordinator>,
    llm_router: Arc<LLMRouter>,  // 使用 LLM Router 替代直接 Client
    context_builder: Arc<ContextBuilder>,
    output_parser: Arc<OutputParser>,
    
    // 状态
    state: ExecutorState,
    current_step: usize,
    max_steps: usize,
    
    // 事件通道（向 Session Host 报告）
    event_tx: mpsc::Sender<ExecutorEvent>,
}

/// Executor 事件
#[derive(Debug, Clone)]
pub enum ExecutorEvent {
    StepStarted {
        step_number: usize,
        phase: ExecutionPhase,
    },
    ContextBuilt {
        token_estimate: usize,
    },
    LLMRequested,
    LLMResponded {
        content_length: usize,
    },
    IntentParsed {
        intent_type: String,
    },
    SkillExecuting {
        skill_name: String,
        tool_name: String,
    },
    SkillCompleted {
        success: bool,
        execution_time_ms: u64,
    },
    StepCompleted {
        step_number: usize,
    },
    PhaseChanged {
        from: ExecutionPhase,
        to: ExecutionPhase,
    },
    Completed {
        reason: CompletionReason,
    },
    Error {
        message: String,
    },
    BatchExecutionStarted {
        task_count: usize,
    },
    BatchExecutionCompleted {
        completed: usize,
        interrupted: usize,
    },
}

#[derive(Debug, Clone)]
pub enum CompletionReason {
    FinalAnswer,
    MaxStepsReached,
    Error,
    Cancelled,
}

impl ThreadExecutor {
    /// 创建新的 Executor
    pub async fn new(
        base_path: PathBuf,
        thread_id: ThreadId,
        coordinator: Arc<ExecutionCoordinator>,
        llm_router: Arc<LLMRouter>,
        context_builder: Arc<ContextBuilder>,
        output_parser: Arc<OutputParser>,
        event_tx: mpsc::Sender<ExecutorEvent>,
    ) -> anyhow::Result<Self> {
        let storage = ThreadStorage::load(base_path, &thread_id).await?;
        
        let executor_id = ExecutorId::new();
        
        info!(
            executor_id = %executor_id.0,
            thread_id = %thread_id.0,
            "Created ThreadExecutor"
        );
        
        Ok(Self {
            executor_id,
            storage,
            coordinator,
            llm_router,
            context_builder,
            output_parser,
            state: ExecutorState::Initializing,
            current_step: 0,
            max_steps: 100,
            event_tx,
        })
    }

    /// 获取 Executor ID
    pub fn executor_id(&self) -> &ExecutorId {
        &self.executor_id
    }

    /// 主执行循环
    #[instrument(skip(self), fields(executor_id = %self.executor_id.0))]
    pub async fn run(
        mut self,
    ) -> anyhow::Result<ExecutionSummary> {
        info!("Starting execution loop");
        self.state = ExecutorState::Running;
        
        loop {
            if self.current_step >= self.max_steps {
                info!("Max steps reached, stopping");
                let _ = self.event_tx.send(ExecutorEvent::Completed {
                    reason: CompletionReason::MaxStepsReached,
                }).await;
                break;
            }
            
            self.current_step += 1;
            
            // 执行一个步骤
            match self.execute_step().await {
                Ok(should_continue) => {
                    if !should_continue {
                        break;
                    }
                }
                Err(e) => {
                    error!(error = %e, "Step execution failed");
                    let _ = self.event_tx.send(ExecutorEvent::Error {
                        message: e.to_string(),
                    }).await;
                    break;
                }
            }
        }
        
        // 生成执行摘要
        let summary = self.generate_summary().await?;
        
        info!(
            executor_id = %self.executor_id.0,
            steps_executed = summary.steps_executed,
            "Execution completed"
        );
        
        Ok(summary)
    }
    
    /// 执行一个步骤（SEE-ACT-UPDATE）
    #[instrument(skip(self), fields(step = self.current_step))]
    async fn execute_step(&mut self,
    ) -> anyhow::Result<bool> {
        // 1. SEE: 加载历史并构建上下文
        let _ = self.event_tx.send(ExecutorEvent::StepStarted {
            step_number: self.current_step,
            phase: self.get_current_phase().await?,
        }).await;
        
        let working_set = self.build_working_set().await?;
        let _ = self.event_tx.send(ExecutorEvent::ContextBuilt {
            token_estimate: working_set.token_estimate,
        }).await;
        
        // 2. ACT: 调用 LLM（通过 Router，根据难度选择模型）
        let _ = self.event_tx.send(ExecutorEvent::LLMRequested).await;
        
        let difficulty = self.select_difficulty().await;
        let llm_output = self.llm_router.generate(working_set.to_prompt(), difficulty).await
            .map_err(|e| anyhow::anyhow!("LLM generation failed: {}", e))?;
        let _ = self.event_tx.send(ExecutorEvent::LLMResponded {
            content_length: llm_output.len(),
        }).await;
        
        // 3. 解析输出
        let intent = self.parse_intent(&llm_output).await?;
        let _ = self.event_tx.send(ExecutorEvent::IntentParsed {
            intent_type: format!("{:?}", intent.intent_type),
        }).await;
        
        // 4. UPDATE: 执行并更新状态
        match intent.intent_type {
            IntentType::ToolCall => {
                if intent.tool_calls.is_empty() {
                    tracing::warn!(
                        step = self.current_step,
                        "ToolCall intent with empty tool_calls, treating as FinalAnswer"
                    );
                    let _ = self.event_tx.send(ExecutorEvent::Completed {
                        reason: CompletionReason::FinalAnswer,
                    }).await;
                    return Ok(false);
                }
                
                for tool_call in intent.tool_calls {
                    let skill_name = tool_call.skill_name.clone();
                    let tool_name = tool_call.tool_name.clone();
                    let parameters = tool_call.parameters.clone();

                    let _ = self.event_tx.send(ExecutorEvent::SkillExecuting {
                        skill_name: skill_name.clone(),
                        tool_name: tool_name.clone(),
                    }).await;

                    let tool_call_event = Event::new(
                        EventType::ToolCall,
                        self.current_step,
                        self.get_current_phase().await?,
                        serde_json::json!({
                            "skill": &skill_name,
                            "tool": &tool_name,
                            "parameters": &parameters,
                        }),
                    );
                    self.storage.append_event(&tool_call_event).await?;

                    let result = self.execute_skill(tool_call).await?;

                    let _ = self.event_tx.send(ExecutorEvent::SkillCompleted {
                        success: result.success,
                        execution_time_ms: result.execution_time_ms,
                    }).await;

                    let tool_result_event = Event::new(
                        EventType::ToolResult,
                        self.current_step,
                        self.get_current_phase().await?,
                        serde_json::json!({
                            "skill": &skill_name,
                            "tool": &tool_name,
                            "success": result.success,
                            "result": &result.result,
                            "error": &result.error,
                        }),
                    );
                    self.storage.append_event(&tool_result_event).await?;

                    let artifact_content = serde_json::json!({
                        "skill": &skill_name,
                        "tool": &tool_name,
                        "parameters": &parameters,
                        "success": result.success,
                        "result": &result.result,
                        "error": &result.error,
                        "execution_time_ms": result.execution_time_ms,
                    });

                    let artifact = crate::agent_thread::models::ArtifactSlot::new(
                        crate::agent_thread::models::ArtifactType::Custom(
                            format!("{}_{}", skill_name, tool_name)
                        ),
                        artifact_content,
                        5,
                        self.current_step,
                    );
                    self.storage.save_artifact(&artifact).await?;
                }
            }
            IntentType::PhaseTransition => {
                if let Some(transition) = intent.phase_transition {
                    let old_phase = self.get_current_phase().await?;
                    self.update_phase(transition.to_phase).await?;
                    
                    let _ = self.event_tx.send(ExecutorEvent::PhaseChanged {
                        from: old_phase,
                        to: transition.to_phase,
                    }).await;
                    
                    let event = Event::new(
                        EventType::PhaseChange,
                        self.current_step,
                        old_phase,
                        serde_json::json!({
                            "from_phase": old_phase,
                            "to_phase": transition.to_phase,
                            "reason": transition.reason,
                        }),
                    );
                    self.storage.append_event(&event).await?;
                }
            }
            IntentType::FinalAnswer => {
                let _ = self.event_tx.send(ExecutorEvent::Completed {
                    reason: CompletionReason::FinalAnswer,
                }).await;
                return Ok(false);
            }
            IntentType::Clarification => {
                // 暂停等待澄清
                self.state = ExecutorState::Paused;
                return Ok(false);
            }
            IntentType::BatchExecution => {
                if let Some(tasks) = intent.batch_tasks {
                    let _ = self.event_tx.send(ExecutorEvent::BatchExecutionStarted {
                        task_count: tasks.len(),
                    }).await;
                    
                    let batch_executor = crate::scheduler::batch_task_executor::BatchTaskExecutor::new();
                    let config = crate::scheduler::time_budget_monitor::TimeBudgetConfig::default();
                    
                    let sub_tasks: Vec<_> = tasks.into_iter().enumerate().map(|(i, process)| {
                        crate::scheduler::batch_task_executor::SubTaskRequest {
                            task_id: format!("batch_task_{}", i),
                            process,
                            depth: 0,
                        }
                    }).collect();
                    
                    let meta = self.storage.read_meta().await?;
                    match batch_executor.execute_with_budget(
                        meta.session_id.0.clone(),
                        sub_tasks,
                        config,
                    ).await {
                        Ok(result) => {
                            let _ = self.event_tx.send(ExecutorEvent::BatchExecutionCompleted {
                                completed: result.completed_tasks.len(),
                                interrupted: result.interrupted_tasks.len(),
                            }).await;
                            
                            let artifact = crate::agent_thread::models::ArtifactSlot::new(
                                crate::agent_thread::models::ArtifactType::Custom("BatchResult".to_string()),
                                serde_json::json!({
                                    "system_notice": result.system_notice,
                                    "summary": result.summary,
                                    "time_budget_exceeded": result.time_budget_exceeded,
                                }),
                                10,
                                self.current_step,
                            );
                            self.storage.save_artifact(&artifact).await?;
                        }
                        Err(e) => {
                            error!("Batch execution failed: {}", e);
                        }
                    }
                }
            }
            IntentType::Error => {
                return Err(anyhow::anyhow!("Agent error: {:?}", intent.error_message));
            }
        }
        
        let _ = self.event_tx.send(ExecutorEvent::StepCompleted {
            step_number: self.current_step,
        }).await;
        
        Ok(true)
    }
    
    /// 构建 Working Set
    async fn build_working_set(&self,
    ) -> anyhow::Result<WorkingSet> {
        // 使用 ContextBuilder 构建
        self.context_builder.build(&self.storage, self.current_step).await
    }
    
    /// 解析 LLM 输出
    async fn parse_intent(
        &self,
        output: &str,
    ) -> anyhow::Result<ParsedIntent> {
        let phase = self.get_current_phase().await?;
        self.output_parser.parse(output, phase)
    }
    
    /// 执行 Skill（通过 Coordinator）
    async fn execute_skill(
        &self,
        tool_call: ToolCallIntent,
    ) -> anyhow::Result<crate::coordinator::models::SkillResult> {
        let meta = self.storage.read_meta().await?;
        
        let request = SkillRequest {
            request_id: uuid::Uuid::new_v4().to_string(),
            skill_name: tool_call.skill_name,
            tool_name: tool_call.tool_name,
            parameters: tool_call.parameters,
            context: SkillContext {
                thread_id: self.storage.thread_id().0.clone(),
                session_id: meta.session_id.0.clone(),
                executor_id: self.executor_id.0.clone(),
                capability_level: CapabilityLevel::Agent,
                working_dirs: Vec::new(),
            },
        };
        
        self.coordinator.execute_skill(request).await
    }
    
    /// 获取当前 Phase
    async fn get_current_phase(&self,
    ) -> anyhow::Result<ExecutionPhase> {
        let meta = self.storage.read_meta().await?;
        Ok(meta.current_phase)
    }
    
    /// 更新 Phase
    async fn update_phase(&mut self,
        phase: ExecutionPhase,
    ) -> anyhow::Result<()> {
        let mut meta = self.storage.read_meta().await?;
        meta.current_phase = phase;
        meta.updated_at = chrono::Utc::now();
        self.storage.update_meta(&meta).await.map_err(|e| anyhow::anyhow!("Failed to update meta: {}", e))
    }
    
    /// 根据当前状态选择 LLM 难度级别
    async fn select_difficulty(&self) -> DifficultyLevel {
        let meta = match self.storage.read_meta().await {
            Ok(m) => m,
            Err(_) => return DifficultyLevel::Medium,
        };
        
        // 根据 Phase 和 step 数选择难度
        match meta.current_phase {
            ExecutionPhase::Explore => {
                // 探索阶段：前期简单，后期复杂
                if self.current_step < 5 {
                    DifficultyLevel::Easy
                } else {
                    DifficultyLevel::Medium
                }
            }
            ExecutionPhase::Execute => {
                // 执行阶段：根据复杂度
                if meta.step_count > 20 {
                    DifficultyLevel::Hard
                } else {
                    DifficultyLevel::Medium
                }
            }
            ExecutionPhase::Complete => {
                // 完成阶段：需要总结能力
                DifficultyLevel::Medium
            }
        }
    }
    
    /// 生成执行摘要
    async fn generate_summary(&self,
    ) -> anyhow::Result<ExecutionSummary> {
        let meta = self.storage.read_meta().await?;
        let artifacts = self.storage.list_artifacts().await?;
        
        Ok(ExecutionSummary {
            thread_id: self.storage.thread_id().clone(),
            executor_id: self.executor_id.clone(),
            steps_executed: self.current_step,
            final_phase: meta.current_phase,
            final_status: match self.state {
                ExecutorState::Completed => ThreadStatus::Completed,
                ExecutorState::Error => ThreadStatus::Error,
                ExecutorState::Paused => ThreadStatus::Paused,
                _ => ThreadStatus::Active,
            },
            artifacts_produced: artifacts.iter().map(|a| a.artifact_type.clone()).collect(),
            started_at: meta.created_at,  // TODO: 记录实际开始时间
            completed_at: chrono::Utc::now(),
        })
    }
}

/// 工具调用意图
#[derive(Debug, Clone)]
pub struct ToolCallIntent {
    pub skill_name: String,
    pub tool_name: String,
    pub parameters: serde_json::Value,
    pub reasoning: String,
}

/// 意图类型
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum IntentType {
    ToolCall,
    PhaseTransition,
    FinalAnswer,
    Clarification,
    BatchExecution,
    Error,
}

/// 解析后的意图
#[derive(Debug, Clone)]
pub struct ParsedIntent {
    pub intent_type: IntentType,
    pub confidence: f32,
    pub raw_content: String,
    pub structured_data: serde_json::Value,
    pub tool_calls: Vec<ToolCallIntent>,
    pub phase_transition: Option<PhaseTransitionIntent>,
    pub final_answer: Option<String>,
    pub clarification_request: Option<String>,
    pub error_message: Option<String>,
    pub batch_tasks: Option<Vec<crate::personality::models::ProcessDefinition>>,
}

/// Phase 转换意图
#[derive(Debug, Clone)]
pub struct PhaseTransitionIntent {
    pub from_phase: ExecutionPhase,
    pub to_phase: ExecutionPhase,
    pub reason: String,
    pub artifacts_to_finalize: Vec<String>,
}
