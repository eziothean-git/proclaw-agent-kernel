//! Scheduler Skill - Thread 调度管理 Skill
//! 
//! 权限：Host/Prime
//! 
//! 提供工具：
//! - spawn_thread: 启动 Thread
//! - pause_thread: 暂停 Thread
//! - resume_thread: 恢复 Thread
//! - cancel_thread: 取消 Thread
//! - list_threads: 列出所有 Threads
//! - get_thread_log: 获取 Thread 日志

use std::sync::Arc;
use serde_json::json;
use tracing::{info, instrument, warn};

use crate::auth::CapabilityLevel;
use crate::coordinator::models::{SkillContext, SkillResult};
use crate::agent_thread::models::{ThreadId, ImmutableInput, SessionId};
use crate::scheduler::thread_manager::{ThreadManager, ThreadHistory};

/// Scheduler Skill
pub struct SchedulerSkill {
    thread_manager: Arc<ThreadManager>,
}

impl SchedulerSkill {
    pub fn new(thread_manager: Arc<ThreadManager>) -> Self {
        Self { thread_manager }
    }
    
    /// 获取 Skill 名称
    pub fn name(&self) -> &str {
        "scheduler"
    }
    
    /// 列出可用 Tools
    pub fn list_tools(&self) -> Vec<ToolDefinition> {
        vec![
            ToolDefinition {
                name: "create_thread".to_string(),
                description: "Create a new thread for task execution".to_string(),
                parameters: json!({
                    "type": "object",
                    "properties": {
                        "session_id": {
                            "type": "string",
                            "description": "Session ID for the thread"
                        },
                        "task_goal": {
                            "type": "string",
                            "description": "The task goal"
                        },
                        "constraints": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of constraints"
                        }
                    },
                    "required": ["session_id", "task_goal"]
                }),
            },
            ToolDefinition {
                name: "spawn_thread".to_string(),
                description: "Start executing a thread".to_string(),
                parameters: json!({
                    "type": "object",
                    "properties": {
                        "thread_id": {
                            "type": "string",
                            "description": "Thread ID to start"
                        }
                    },
                    "required": ["thread_id"]
                }),
            },
            ToolDefinition {
                name: "pause_thread".to_string(),
                description: "Pause a running thread".to_string(),
                parameters: json!({
                    "type": "object",
                    "properties": {
                        "thread_id": {
                            "type": "string",
                            "description": "Thread ID to pause"
                        }
                    },
                    "required": ["thread_id"]
                }),
            },
            ToolDefinition {
                name: "resume_thread".to_string(),
                description: "Resume a paused thread".to_string(),
                parameters: json!({
                    "type": "object",
                    "properties": {
                        "thread_id": {
                            "type": "string",
                            "description": "Thread ID to resume"
                        }
                    },
                    "required": ["thread_id"]
                }),
            },
            ToolDefinition {
                name: "cancel_thread".to_string(),
                description: "Cancel a running thread".to_string(),
                parameters: json!({
                    "type": "object",
                    "properties": {
                        "thread_id": {
                            "type": "string",
                            "description": "Thread ID to cancel"
                        }
                    },
                    "required": ["thread_id"]
                }),
            },
            ToolDefinition {
                name: "list_threads".to_string(),
                description: "List all threads (running or historical)".to_string(),
                parameters: json!({
                    "type": "object",
                    "properties": {
                        "status_filter": {
                            "type": "string",
                            "enum": ["all", "running", "paused", "completed", "error"],
                            "description": "Filter by status"
                        }
                    }
                }),
            },
            ToolDefinition {
                name: "get_thread_info".to_string(),
                description: "Get information about a specific thread".to_string(),
                parameters: json!({
                    "type": "object",
                    "properties": {
                        "thread_id": {
                            "type": "string",
                            "description": "Thread ID"
                        }
                    },
                    "required": ["thread_id"]
                }),
            },
            ToolDefinition {
                name: "get_thread_log".to_string(),
                description: "Get execution log for a thread".to_string(),
                parameters: json!({
                    "type": "object",
                    "properties": {
                        "thread_id": {
                            "type": "string",
                            "description": "Thread ID"
                        }
                    },
                    "required": ["thread_id"]
                }),
            },
        ]
    }
    
    /// 检查权限
    fn check_permission(&self,
        context: &SkillContext,
    ) -> Option<SkillResult> {
        // Scheduler 需要 Host 或 Prime 权限
        if context.capability_level < CapabilityLevel::Host {
            return Some(SkillResult {
                request_id: context.thread_id.clone(),
                success: false,
                result: None,
                error: Some("Permission denied: scheduler skill requires Host or Prime level".to_string()),
                execution_time_ms: 0,
            });
        }
        None
    }
    
    /// 执行 Tool
    #[instrument(skip(self, params, context), fields(tool = %tool_name))]
    pub async fn execute(
        &self,
        tool_name: &str,
        params: serde_json::Value,
        context: SkillContext,
    ) -> anyhow::Result<SkillResult> {
        // 检查权限
        if let Some(result) = self.check_permission(&context) {
            return Ok(result);
        }
        
        let start = std::time::Instant::now();
        
        let result = match tool_name {
            "create_thread" => self.create_thread(params, &context).await,
            "spawn_thread" => self.spawn_thread(params).await,
            "pause_thread" => self.pause_thread(params).await,
            "resume_thread" => self.resume_thread(params).await,
            "cancel_thread" => self.cancel_thread(params).await,
            "list_threads" => self.list_threads(params).await,
            "get_thread_info" => self.get_thread_info(params).await,
            "get_thread_log" => self.get_thread_log(params).await,
            _ => {
                return Ok(SkillResult {
                    request_id: context.thread_id.clone(),
                    success: false,
                    result: None,
                    error: Some(format!("Unknown tool: {}", tool_name)),
                    execution_time_ms: start.elapsed().as_millis() as u64,
                });
            }
        };
        
        match result {
            Ok(result_json) => Ok(SkillResult {
                request_id: context.thread_id.clone(),
                success: true,
                result: Some(result_json),
                error: None,
                execution_time_ms: start.elapsed().as_millis() as u64,
            }),
            Err(e) => Ok(SkillResult {
                request_id: context.thread_id.clone(),
                success: false,
                result: None,
                error: Some(e.to_string()),
                execution_time_ms: start.elapsed().as_millis() as u64,
            }),
        }
    }
    
    /// 创建 Thread
    async fn create_thread(
        &self,
        params: serde_json::Value,
        context: &SkillContext,
    ) -> anyhow::Result<serde_json::Value> {
        let session_id = SessionId(params.get("session_id")
            .and_then(|v| v.as_str())
            .ok_or_else(|| anyhow::anyhow!("Missing session_id"))?
            .to_string());
        
        let task_goal = params.get("task_goal")
            .and_then(|v| v.as_str())
            .ok_or_else(|| anyhow::anyhow!("Missing task_goal"))?
            .to_string();
        
        let constraints: Vec<String> = params.get("constraints")
            .and_then(|v| v.as_array())
            .map(|arr| arr.iter()
                .filter_map(|v| v.as_str().map(|s| s.to_string()))
                .collect())
            .unwrap_or_default();
        
        let immutable_input = ImmutableInput {
            task_goal,
            constraints,
            allowed_capabilities: vec![],
            forbidden_capabilities: vec![],
            session_context: std::collections::HashMap::new(),
            compiled_at: chrono::Utc::now(),
        };
        
        let thread_id = self.thread_manager.create_thread(session_id, immutable_input).await?;
        
        info!(thread_id = %thread_id.0, "Created thread");
        
        Ok(json!({
            "thread_id": thread_id.0,
            "status": "created"
        }))
    }
    
    /// 启动 Thread
    async fn spawn_thread(
        &self,
        params: serde_json::Value,
    ) -> anyhow::Result<serde_json::Value> {
        let thread_id = ThreadId(params.get("thread_id")
            .and_then(|v| v.as_str())
            .ok_or_else(|| anyhow::anyhow!("Missing thread_id"))?
            .to_string());
        
        let executor_id = self.thread_manager.spawn_thread(thread_id.clone()).await?;
        
        info!(thread_id = %thread_id.0, executor_id = %executor_id, "Spawned thread");
        
        Ok(json!({
            "thread_id": thread_id.0,
            "executor_id": executor_id,
            "status": "running"
        }))
    }
    
    /// 暂停 Thread
    async fn pause_thread(
        &self,
        params: serde_json::Value,
    ) -> anyhow::Result<serde_json::Value> {
        let thread_id = ThreadId(params.get("thread_id")
            .and_then(|v| v.as_str())
            .ok_or_else(|| anyhow::anyhow!("Missing thread_id"))?
            .to_string());
        
        self.thread_manager.pause_thread(&thread_id).await?;
        
        info!(thread_id = %thread_id.0, "Paused thread");
        
        Ok(json!({
            "thread_id": thread_id.0,
            "status": "paused"
        }))
    }
    
    /// 恢复 Thread
    async fn resume_thread(
        &self,
        params: serde_json::Value,
    ) -> anyhow::Result<serde_json::Value> {
        let thread_id = ThreadId(params.get("thread_id")
            .and_then(|v| v.as_str())
            .ok_or_else(|| anyhow::anyhow!("Missing thread_id"))?
            .to_string());
        
        self.thread_manager.resume_thread(&thread_id).await?;
        
        info!(thread_id = %thread_id.0, "Resumed thread");
        
        Ok(json!({
            "thread_id": thread_id.0,
            "status": "running"
        }))
    }
    
    /// 取消 Thread
    async fn cancel_thread(
        &self,
        params: serde_json::Value,
    ) -> anyhow::Result<serde_json::Value> {
        let thread_id = ThreadId(params.get("thread_id")
            .and_then(|v| v.as_str())
            .ok_or_else(|| anyhow::anyhow!("Missing thread_id"))?
            .to_string());
        
        self.thread_manager.cancel_thread(&thread_id).await?;
        
        info!(thread_id = %thread_id.0, "Cancelled thread");
        
        Ok(json!({
            "thread_id": thread_id.0,
            "status": "cancelled"
        }))
    }
    
    /// 列出 Threads
    async fn list_threads(
        &self,
        params: serde_json::Value,
    ) -> anyhow::Result<serde_json::Value> {
        let status_filter = params.get("status_filter")
            .and_then(|v| v.as_str())
            .unwrap_or("all");
        
        // 获取运行中的 threads
        let running_threads = self.thread_manager.list_running_threads().await;
        
        // 获取历史记录
        let history = self.thread_manager.get_all_history().await;
        
        // 合并信息
        let mut threads_json = Vec::new();
        
        for info in running_threads {
            let status_str = format!("{:?}", info.status).to_lowercase();
            
            if status_filter == "all" || status_str == status_filter {
                threads_json.push(json!({
                    "thread_id": info.thread_id.0,
                    "session_id": info.session_id.0,
                    "status": status_str,
                    "current_phase": format!("{:?}", info.current_phase).to_lowercase(),
                    "step_count": info.step_count,
                    "started_at": info.started_at,
                    "updated_at": info.updated_at,
                }));
            }
        }
        
        // 添加历史中的已完成 threads
        for h in history {
            if let Some(status) = h.final_status {
                let status_str = format!("{:?}", status).to_lowercase();
                
                if status_filter == "all" || status_filter == "completed" && status_str == "completed" {
                    // 检查是否已经在运行列表中
                    if !threads_json.iter().any(|t| t.get("thread_id").and_then(|v| v.as_str()) == Some(&h.thread_id.0)) {
                        threads_json.push(json!({
                            "thread_id": h.thread_id.0,
                            "session_id": h.session_id.0,
                            "status": status_str,
                            "created_at": h.created_at,
                            "completed_at": h.completed_at,
                        }));
                    }
                }
            }
        }
        
        Ok(json!({
            "threads": threads_json,
            "total_count": threads_json.len()
        }))
    }
    
    /// 获取 Thread 信息
    async fn get_thread_info(
        &self,
        params: serde_json::Value,
    ) -> anyhow::Result<serde_json::Value> {
        let thread_id = ThreadId(params.get("thread_id")
            .and_then(|v| v.as_str())
            .ok_or_else(|| anyhow::anyhow!("Missing thread_id"))?
            .to_string());
        
        let info = self.thread_manager.get_thread_info(&thread_id).await?;
        
        Ok(json!({
            "thread_id": info.thread_id.0,
            "session_id": info.session_id.0,
            "status": format!("{:?}", info.status).to_lowercase(),
            "current_phase": format!("{:?}", info.current_phase).to_lowercase(),
            "step_count": info.step_count,
            "started_at": info.started_at,
            "updated_at": info.updated_at,
        }))
    }
    
    /// 获取 Thread 日志
    async fn get_thread_log(
        &self,
        params: serde_json::Value,
    ) -> anyhow::Result<serde_json::Value> {
        let thread_id = ThreadId(params.get("thread_id")
            .and_then(|v| v.as_str())
            .ok_or_else(|| anyhow::anyhow!("Missing thread_id"))?
            .to_string());
        
        let history: ThreadHistory = self.thread_manager.get_thread_log(&thread_id).await?;
        
        let events_json: Vec<serde_json::Value> = history.events.iter().map(|e| {
            json!({
                "timestamp": e.timestamp,
                "event_type": e.event_type,
                "details": e.details,
            })
        }).collect();
        
        Ok(json!({
            "thread_id": history.thread_id.0,
            "session_id": history.session_id.0,
            "created_at": history.created_at,
            "completed_at": history.completed_at,
            "final_status": history.final_status.map(|s| format!("{:?}", s).to_lowercase()),
            "events": events_json,
            "event_count": events_json.len(),
        }))
    }
}

/// Tool 定义
#[derive(Debug, Clone)]
pub struct ToolDefinition {
    pub name: String,
    pub description: String,
    pub parameters: serde_json::Value, // JSON Schema
}
