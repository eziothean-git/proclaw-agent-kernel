//! IR Process Executor - 执行 Prime 生成的 IR Processes
//!
//! 职责：
//! 1. 解析 IR.processes
//! 2. 调用 SessionHostSkills 创建 Process 和 Thread
//! 3. 启动 Thread Executor
//! 4. 收集执行结果
//! 5. 向 Prime 汇报

use std::path::PathBuf;
use std::sync::Arc;
use tokio::sync::mpsc;
use tracing::{info, warn, error};

use crate::personality::models::{IntermediateRepresentation, ProcessDefinition};
use crate::session::{
    process::{ProcessId},
    skills::SessionHostSkills,
};
use crate::agent_thread::models::{ThreadId};
use crate::scheduler::{
    thread_executor::{ExecutorEvent, CompletionReason},
};
use crate::llm::config::DifficultyLevel;
use crate::coordinator::ExecutionCoordinator;
use crate::block_composer::BlockComposerEngine;
use crate::llm::LLMRouter;

/// 执行结果
#[derive(Debug, Clone)]
pub struct ProcessExecutionResult {
    pub process_id: String,
    pub process_name: String,
    pub success: bool,
    pub execution_log: Vec<ExecutionStep>,
    pub final_answer: Option<String>,
    pub artifacts: Vec<ArtifactInfo>,
    pub error_message: Option<String>,
}

/// 执行步骤记录
#[derive(Debug, Clone)]
pub struct ExecutionStep {
    pub step_number: usize,
    pub phase: String,
    pub action: String,
    pub result: String,
    pub timestamp: chrono::DateTime<chrono::Utc>,
}

/// 产物信息
#[derive(Debug, Clone)]
pub struct ArtifactInfo {
    pub artifact_id: String,
    pub artifact_type: String,
    pub content_preview: String,
}

/// IR Process Executor
pub struct IRProcessExecutor {
    data_path: PathBuf,
    session_host_skills: Arc<SessionHostSkills>,
}

impl IRProcessExecutor {
    /// 创建新的 IR Process Executor
    pub async fn new(
        data_path: PathBuf,
        coordinator: Arc<ExecutionCoordinator>,
        block_composer: Arc<BlockComposerEngine>,
        llm_router: Arc<LLMRouter>,
    ) -> anyhow::Result<Self> {
        let session_host_skills = Arc::new(
            SessionHostSkills::new(
                data_path.clone(),
                coordinator,
                block_composer,
                llm_router,
            ).await?
        );

        Ok(Self {
            data_path,
            session_host_skills,
        })
    }
    
    /// 执行 IR 中的所有 processes
    pub async fn execute_ir(
        &self,
        ir: &IntermediateRepresentation,
        session_id: &str,
    ) -> anyhow::Result<Vec<ProcessExecutionResult>> {
        info!(
            request_id = %ir.request_id,
            process_count = ir.processes.len(),
            "Starting IR execution"
        );
        
        let mut results = Vec::new();
        
        for (idx, process_def) in ir.processes.iter().enumerate() {
            info!(
                process_idx = idx,
                process_name = %process_def.name,
                "Executing process"
            );
            
            match self.execute_process(process_def, session_id, idx).await {
                Ok(result) => {
                    info!(
                        process_name = %process_def.name,
                        success = result.success,
                        "Process completed"
                    );
                    results.push(result);
                }
                Err(e) => {
                    error!(
                        process_name = %process_def.name,
                        error = %e,
                        "Process execution failed"
                    );
                    results.push(ProcessExecutionResult {
                        process_id: format!("failed_{}", idx),
                        process_name: process_def.name.clone(),
                        success: false,
                        execution_log: vec![],
                        final_answer: None,
                        artifacts: vec![],
                        error_message: Some(e.to_string()),
                    });
                }
            }
        }
        
        info!(
            request_id = %ir.request_id,
            completed_count = results.len(),
            "IR execution completed"
        );
        
        Ok(results)
    }
    
    /// 执行单个 process
    async fn execute_process(
        &self,
        process_def: &ProcessDefinition,
        session_id: &str,
        _process_idx: usize,
    ) -> anyhow::Result<ProcessExecutionResult> {
        // 1. 创建 Process
        let process_id = self.session_host_skills.create_process(
            session_id,
            &process_def.goal,
            vec![process_def.name.clone()],
        ).await?;
        
        info!(
            process_id = %process_id.0,
            "Created process"
        );
        
        // 2. 创建 Thread
        let thread_id = self.session_host_skills.create_thread_in_process(
            &process_id,
            &process_def.goal,
            process_def.constraints.clone().unwrap_or_default(),
            process_def.capabilities.clone(),
        ).await?;
        
        info!(
            process_id = %process_id.0,
            thread_id = %thread_id.0,
            "Created thread in process"
        );
        
        // 3. 启动 Executor 并等待完成
        let difficulty = self.select_difficulty(process_def);
        
        // 创建事件通道来监控执行
        let (event_tx, mut event_rx) = mpsc::channel::<ExecutorEvent>(100);
        let (completion_tx, completion_rx) = tokio::sync::oneshot::channel::<CompletionReason>();
        
        // 启动事件收集任务
        let mut execution_log = Vec::new();
        let mut step_count = 0;
        let mut current_phase = "Explore".to_string();
        let event_collector = tokio::spawn(async move {
            while let Some(event) = event_rx.recv().await {
                match &event {
                    ExecutorEvent::StepStarted { step_number, phase } => {
                        step_count = *step_number;
                        current_phase = format!("{:?}", phase);
                    }
                    ExecutorEvent::SkillExecuting { skill_name, tool_name } => {
                        execution_log.push(ExecutionStep {
                            step_number: step_count,
                            phase: current_phase.clone(),
                            action: format!("{}:{}", skill_name, tool_name),
                            result: "Executing...".to_string(),
                            timestamp: chrono::Utc::now(),
                        });
                    }
                    ExecutorEvent::SkillCompleted { success, .. } => {
                        if let Some(last) = execution_log.last_mut() {
                            last.result = if *success { "Success".to_string() } else { "Failed".to_string() };
                        }
                    }
                    ExecutorEvent::Completed { reason } => {
                        let _ = completion_tx.send(reason.clone());
                        break;
                    }
                    _ => {}
                }
            }
            execution_log
        });
        
        // 启动 Executor（传递外部事件通道）
        let executor_id = self.session_host_skills.spawn_executor_in_process_with_events(
            &process_id,
            &thread_id,
            difficulty,
            Some(event_tx),
        ).await?;
        
        info!(
            executor_id = %executor_id,
            "Spawned executor"
        );
        
        // 等待执行完成（带超时）
        let timeout_duration = tokio::time::Duration::from_secs(300); // 5分钟超时
        let execution_result = tokio::time::timeout(
            timeout_duration,
            completion_rx
        ).await;
        
        // 收集执行日志
        let execution_log = match event_collector.await {
            Ok(log) => log,
            Err(_) => vec![],
        };

        // 4. 获取 Process 的最终状态
        let _process_info = self.session_host_skills.get_process_info(&process_id).await;
        let _thread_status = self.session_host_skills.get_thread_in_process_status(&process_id, &thread_id).await;
        
        // 5. 从 Thread Storage 读取执行结果
        let (final_answer, artifacts) = self.collect_thread_results(&thread_id).await?;
        
        let success = match execution_result {
            Ok(Ok(CompletionReason::FinalAnswer)) => true,
            Ok(Ok(_)) => true, // MaxStepsReached 也算成功
            Ok(Err(_)) => false,
            Err(_) => {
                warn!("Execution timeout");
                false
            }
        };
        
        Ok(ProcessExecutionResult {
            process_id: process_id.0,
            process_name: process_def.name.clone(),
            success,
            execution_log,
            final_answer,
            artifacts,
            error_message: if success { None } else { Some("Execution failed or timed out".to_string()) },
        })
    }
    
    /// 从 Thread 收集执行结果
    async fn collect_thread_results(
        &self,
        thread_id: &ThreadId,
    ) -> anyhow::Result<(Option<String>, Vec<ArtifactInfo>)> {
        use crate::agent_thread::storage::ThreadStorage;
        use crate::agent_thread::models::EventType;
        
        let storage = ThreadStorage::load(&self.data_path, thread_id).await?;
        
        // 读取所有 events
        let events = storage.read_event_log().await?;
        
        // 从 ToolResult 事件提取结果
        let mut final_answer = None;
        let mut artifacts = Vec::new();
        
        for event in events {
            if event.event_type == EventType::ToolResult {
                // 提取工具执行结果
                if let Some(result) = event.content.get("result") {
                    let result_str = result.to_string();
                    if !result_str.is_empty() && result_str != "null" {
                        final_answer = Some(result_str);
                    }
                }
                
                // 提取成功执行的 artifacts
                if let Some(success) = event.content.get("success").and_then(|v| v.as_bool()) {
                    if success {
                        if let (Some(skill), Some(tool)) = (
                            event.content.get("skill").and_then(|v| v.as_str()),
                            event.content.get("tool").and_then(|v| v.as_str())
                        ) {
                            artifacts.push(ArtifactInfo {
                                artifact_id: format!("{}_{}_{}", skill, tool, event.step_number),
                                artifact_type: format!("{}:{}", skill, tool),
                                content_preview: event.content.get("result")
                                    .map(|r| r.to_string())
                                    .unwrap_or_default()
                                    .chars()
                                    .take(200)
                                    .collect(),
                            });
                        }
                    }
                }
            }
        }
        
        Ok((final_answer, artifacts))
    }
    
    /// 根据 process 定义选择难度
    fn select_difficulty(&self, process_def: &ProcessDefinition) -> DifficultyLevel {
        // 根据 security_level 和 constraints 选择难度
        if let Some(security) = &process_def.security_level {
            match security.as_str() {
                "high" => DifficultyLevel::Expert,
                "medium" => DifficultyLevel::Hard,
                _ => DifficultyLevel::Medium,
            }
        } else {
            DifficultyLevel::Medium
        }
    }
    
    /// 获取 Session 的全量执行日志
    pub async fn get_session_full_log(
        &self,
        session_id: &str,
    ) -> anyhow::Result<SessionExecutionLog> {
        let processes = self.session_host_skills.list_session_processes(session_id).await;
        
        let mut process_logs = Vec::new();
        
        for process_summary in processes {
            if let Some(process_detail) = self.session_host_skills
                .get_process_info(&ProcessId(process_summary.process_id.clone()))
                .await 
            {
                process_logs.push(ProcessExecutionLog {
                    process_id: process_detail.process_id,
                    goal: process_detail.goal,
                    status: process_detail.status,
                    threads: process_detail.threads,
                });
            }
        }
        
        Ok(SessionExecutionLog {
            session_id: session_id.to_string(),
            processes: process_logs,
        })
    }
}

/// Session 执行日志
#[derive(Debug, Clone)]
pub struct SessionExecutionLog {
    pub session_id: String,
    pub processes: Vec<ProcessExecutionLog>,
}

/// Process 执行日志
#[derive(Debug, Clone)]
pub struct ProcessExecutionLog {
    pub process_id: String,
    pub goal: String,
    pub status: String,
    pub threads: Vec<crate::session::skills::ThreadBrief>,
}

/// 执行报告 - 用于向 Prime 汇报
#[derive(Debug, Clone)]
pub struct ExecutionReport {
    pub original_ir: IntermediateRepresentation,
    pub execution_results: Vec<ProcessExecutionResult>,
    pub session_log: SessionExecutionLog,
    pub summary: String,
}

impl ExecutionReport {
    /// 生成给 Prime 的上下文摘要
    pub fn to_prime_context(&self) -> String {
        let mut context = format!(
            "## 执行报告\n\n原始请求: {}\nIntent: {}\n执行结果:\n\n",
            self.original_ir.goals.join(", "),
            self.original_ir.intent
        );

        for (idx, result) in self.execution_results.iter().enumerate() {
            context.push_str(&format!(
                "### Process {}: {}\n- 状态: {}\n- 执行步骤: {}\n",
                idx + 1,
                result.process_name,
                if result.success { "✅ 成功" } else { "❌ 失败" },
                result.execution_log.len()
            ));
            
            if let Some(answer) = &result.final_answer {
                context.push_str(&format!("- 结果: {}\n", answer));
            }
            
            if let Some(error) = &result.error_message {
                context.push_str(&format!("- 错误: {}\n", error));
            }
            
            context.push('\n');
        }
        
        context.push_str(&format!("\n## 总结\n{}\n", self.summary));
        
        context
    }
}
