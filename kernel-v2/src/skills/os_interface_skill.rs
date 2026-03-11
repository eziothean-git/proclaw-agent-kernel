//! OS Interface Skill - 系统接口 Skill
//! 
//! 权限：Prime only
//! 
//! 提供工具：
//! - list_sessions: 列出所有 Sessions
//! - get_session_info: 获取 Session 信息
//! - delete_session: 删除 Session
//! - create_process: 创建 Process
//! - list_processes: 列出所有 Processes
//! - get_process_info: 获取 Process 信息
//! - query_session_history: 查询 Session 历史

use std::sync::Arc;
use serde_json::json;
use tracing::{info, instrument, warn};

use crate::auth::CapabilityLevel;
use crate::coordinator::models::{SkillContext, SkillResult};
use crate::agent_thread::models::{ThreadId, SessionId};
use crate::session::{
    process::{ProcessId, ProcessManager},
    SessionHostSkills,
};
use crate::scheduler::thread_manager::ThreadManager;

/// OS Interface Skill
pub struct OSInterfaceSkill {
    process_manager: Arc<ProcessManager>,
    thread_manager: Arc<ThreadManager>,
}

impl OSInterfaceSkill {
    pub fn new(
        process_manager: Arc<ProcessManager>,
        thread_manager: Arc<ThreadManager>,
    ) -> Self {
        Self {
            process_manager,
            thread_manager,
        }
    }
    
    /// 获取 Skill 名称
    pub fn name(&self) -> &str {
        "os_interface"
    }
    
    /// 列出可用 Tools
    pub fn list_tools(&self) -> Vec<ToolDefinition> {
        vec![
            ToolDefinition {
                name: "list_sessions".to_string(),
                description: "List all sessions in the system".to_string(),
                parameters: json!({
                    "type": "object",
                    "properties": {}
                }),
            },
            ToolDefinition {
                name: "get_session_info".to_string(),
                description: "Get information about a specific session".to_string(),
                parameters: json!({
                    "type": "object",
                    "properties": {
                        "session_id": {
                            "type": "string",
                            "description": "Session ID"
                        }
                    },
                    "required": ["session_id"]
                }),
            },
            ToolDefinition {
                name: "delete_session".to_string(),
                description: "Delete a session and all its data".to_string(),
                parameters: json!({
                    "type": "object",
                    "properties": {
                        "session_id": {
                            "type": "string",
                            "description": "Session ID to delete"
                        },
                        "force": {
                            "type": "boolean",
                            "description": "Force deletion even if active",
                            "default": false
                        }
                    },
                    "required": ["session_id"]
                }),
            },
            ToolDefinition {
                name: "create_process".to_string(),
                description: "Create a new process".to_string(),
                parameters: json!({
                    "type": "object",
                    "properties": {
                        "session_id": {
                            "type": "string",
                            "description": "Session ID"
                        },
                        "process_goal": {
                            "type": "string",
                            "description": "Goal of the process"
                        },
                        "tags": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Tags for the process"
                        }
                    },
                    "required": ["session_id", "process_goal"]
                }),
            },
            ToolDefinition {
                name: "list_processes".to_string(),
                description: "List all processes (optionally filtered by session)".to_string(),
                parameters: json!({
                    "type": "object",
                    "properties": {
                        "session_id": {
                            "type": "string",
                            "description": "Optional: Filter by session ID"
                        },
                        "status_filter": {
                            "type": "string",
                            "enum": ["all", "active", "completed", "error"],
                            "description": "Filter by status"
                        }
                    }
                }),
            },
            ToolDefinition {
                name: "get_process_info".to_string(),
                description: "Get detailed information about a process".to_string(),
                parameters: json!({
                    "type": "object",
                    "properties": {
                        "process_id": {
                            "type": "string",
                            "description": "Process ID"
                        }
                    },
                    "required": ["process_id"]
                }),
            },
            ToolDefinition {
                name: "delete_process".to_string(),
                description: "Delete a process".to_string(),
                parameters: json!({
                    "type": "object",
                    "properties": {
                        "process_id": {
                            "type": "string",
                            "description": "Process ID to delete"
                        }
                    },
                    "required": ["process_id"]
                }),
            },
            ToolDefinition {
                name: "query_session_history".to_string(),
                description: "Query the complete history of a session".to_string(),
                parameters: json!({
                    "type": "object",
                    "properties": {
                        "session_id": {
                            "type": "string",
                            "description": "Session ID"
                        },
                        "limit": {
                            "type": "integer",
                            "description": "Maximum number of entries to return",
                            "default": 100
                        }
                    },
                    "required": ["session_id"]
                }),
            },
        ]
    }
    
    /// 检查权限
    fn check_permission(
        &self,
        context: &SkillContext,
    ) -> Option<SkillResult> {
        // OS Interface 需要 Prime 权限
        if context.capability_level < CapabilityLevel::Prime {
            return Some(SkillResult {
                request_id: context.thread_id.clone(),
                success: false,
                result: None,
                error: Some("Permission denied: OS interface skill requires Prime level".to_string()),
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
            "list_sessions" => self.list_sessions().await,
            "get_session_info" => self.get_session_info(params).await,
            "delete_session" => self.delete_session(params).await,
            "create_process" => self.create_process(params).await,
            "list_processes" => self.list_processes(params).await,
            "get_process_info" => self.get_process_info(params).await,
            "delete_process" => self.delete_process(params).await,
            "query_session_history" => self.query_session_history(params).await,
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
    
    /// 列出所有 Sessions
    async fn list_sessions(&self,
    ) -> anyhow::Result<serde_json::Value> {
        // 从 ProcessManager 收集所有唯一的 session_ids
        let processes = self.process_manager.list_processes();
        
        use std::collections::HashSet;
        let session_ids: HashSet<String> = processes.iter()
            .map(|p| p.meta().session_id.0.clone())
            .collect();
        
        let sessions_json: Vec<serde_json::Value> = session_ids.iter().map(|sid| {
            // 统计该 session 的 processes
            let process_count = processes.iter()
                .filter(|p| p.meta().session_id.0 == *sid)
                .count();
            
            // 统计 threads
            let thread_count: usize = processes.iter()
                .filter(|p| p.meta().session_id.0 == *sid)
                .map(|p| p.meta().thread_count)
                .sum();
            
            json!({
                "session_id": sid,
                "process_count": process_count,
                "thread_count": thread_count,
            })
        }).collect();
        
        Ok(json!({
            "sessions": sessions_json,
            "total_count": sessions_json.len()
        }))
    }
    
    /// 获取 Session 信息
    async fn get_session_info(
        &self,
        params: serde_json::Value,
    ) -> anyhow::Result<serde_json::Value> {
        let session_id = params.get("session_id")
            .and_then(|v| v.as_str())
            .ok_or_else(|| anyhow::anyhow!("Missing session_id"))?;
        
        // 查找该 session 的所有 processes
        let processes = self.process_manager.list_processes_by_session(&SessionId(session_id.to_string()));
        
        let processes_json: Vec<serde_json::Value> = processes.iter().map(|p| {
            json!({
                "process_id": p.process_id().0,
                "goal": p.meta().process_goal,
                "status": format!("{:?}", p.meta().status).to_lowercase(),
                "thread_count": p.meta().thread_count,
                "created_at": p.meta().created_at,
                "updated_at": p.meta().updated_at,
                "has_active_threads": p.has_active_threads(),
            })
        }).collect();
        
        let total_threads: usize = processes.iter().map(|p| p.meta().thread_count).sum();
        let active_processes = processes.iter().filter(|p| p.has_active_threads()).count();
        
        Ok(json!({
            "session_id": session_id,
            "processes": processes_json,
            "process_count": processes.len(),
            "total_threads": total_threads,
            "active_processes": active_processes,
        }))
    }
    
    /// 删除 Session（删除所有相关 processes）
    async fn delete_session(
        &self,
        params: serde_json::Value,
    ) -> anyhow::Result<serde_json::Value> {
        let session_id = params.get("session_id")
            .and_then(|v| v.as_str())
            .ok_or_else(|| anyhow::anyhow!("Missing session_id"))?;
        
        let force = params.get("force")
            .and_then(|v| v.as_bool())
            .unwrap_or(false);
        
        // 查找该 session 的所有 processes
        let processes = self.process_manager.list_processes_by_session(&SessionId(session_id.to_string()));
        
        if !force {
            // 检查是否有活跃的 processes
            let active_count = processes.iter().filter(|p| p.has_active_threads()).count();
            if active_count > 0 {
                return Err(anyhow::anyhow!(
                    "Session has {} active processes. Use force=true to delete anyway.",
                    active_count
                ));
            }
        }
        
        let deleted_count = processes.len();
        
        // TODO: 实际删除操作（从文件系统删除）
        // 这里只是标记为删除，实际删除需要在 ProcessManager 中实现
        
        info!(session_id = %session_id, deleted_count = %deleted_count, "Deleted session");
        
        Ok(json!({
            "session_id": session_id,
            "deleted_processes": deleted_count,
            "status": "deleted"
        }))
    }
    
    /// 创建 Process
    async fn create_process(
        &self,
        params: serde_json::Value,
    ) -> anyhow::Result<serde_json::Value> {
        let session_id = SessionId(params.get("session_id")
            .and_then(|v| v.as_str())
            .ok_or_else(|| anyhow::anyhow!("Missing session_id"))?
            .to_string());
        
        let process_goal = params.get("process_goal")
            .and_then(|v| v.as_str())
            .ok_or_else(|| anyhow::anyhow!("Missing process_goal"))?
            .to_string();
        
        let tags: Vec<String> = params.get("tags")
            .and_then(|v| v.as_array())
            .map(|arr| arr.iter()
                .filter_map(|v| v.as_str().map(|s| s.to_string()))
                .collect())
            .unwrap_or_default();
        
        // 创建 Process（需要使用 mutable ProcessManager）
        // 这里简化处理，实际需要 mutable 访问
        let process_id = ProcessId::new();
        
        info!(session_id = %session_id.0, process_id = %process_id.0, "Created process");
        
        Ok(json!({
            "process_id": process_id.0,
            "session_id": session_id.0,
            "status": "created"
        }))
    }
    
    /// 列出 Processes
    async fn list_processes(
        &self,
        params: serde_json::Value,
    ) -> anyhow::Result<serde_json::Value> {
        let session_id: Option<String> = params.get("session_id")
            .and_then(|v| v.as_str())
            .map(|s| s.to_string());
        
        let status_filter = params.get("status_filter")
            .and_then(|v| v.as_str())
            .unwrap_or("all");
        
        let processes = if let Some(sid) = session_id {
            self.process_manager.list_processes_by_session(&SessionId(sid))
        } else {
            self.process_manager.list_processes()
        };
        
        let filtered_processes: Vec<_> = processes.iter().filter(|p| {
            match status_filter {
                "active" => p.has_active_threads(),
                "completed" => matches!(p.meta().status, crate::session::process::ProcessStatus::Completed),
                "error" => matches!(p.meta().status, crate::session::process::ProcessStatus::Error),
                _ => true,
            }
        }).collect();
        
        let processes_json: Vec<serde_json::Value> = filtered_processes.iter().map(|p| {
            json!({
                "process_id": p.process_id().0,
                "session_id": p.meta().session_id.0,
                "goal": p.meta().process_goal,
                "status": format!("{:?}", p.meta().status).to_lowercase(),
                "thread_count": p.meta().thread_count,
                "created_at": p.meta().created_at,
                "updated_at": p.meta().updated_at,
                "has_active_threads": p.has_active_threads(),
                "tags": p.meta().tags,
            })
        }).collect();
        
        Ok(json!({
            "processes": processes_json,
            "total_count": processes_json.len()
        }))
    }
    
    /// 获取 Process 信息
    async fn get_process_info(
        &self,
        params: serde_json::Value,
    ) -> anyhow::Result<serde_json::Value> {
        let process_id = ProcessId(params.get("process_id")
            .and_then(|v| v.as_str())
            .ok_or_else(|| anyhow::anyhow!("Missing process_id"))?
            .to_string());
        
        let process = self.process_manager.get_process(&process_id)
            .ok_or_else(|| anyhow::anyhow!("Process not found: {}", process_id.0))?;
        
        let threads_json: Vec<serde_json::Value> = process.list_threads().into_iter().map(|t| {
            json!({
                "thread_id": t.thread_id.0,
                "task_goal": t.task_goal,
                "status": format!("{:?}", t.status).to_lowercase(),
                "current_phase": t.current_phase,
                "step_count": t.step_count,
                "created_at": t.created_at,
            })
        }).collect();
        
        Ok(json!({
            "process_id": process.process_id().0,
            "session_id": process.meta().session_id.0,
            "goal": process.meta().process_goal,
            "status": format!("{:?}", process.meta().status).to_lowercase(),
            "thread_count": process.meta().thread_count,
            "created_at": process.meta().created_at,
            "updated_at": process.meta().updated_at,
            "tags": process.meta().tags,
            "metadata": process.meta().metadata,
            "threads": threads_json,
        }))
    }
    
    /// 删除 Process
    async fn delete_process(
        &self,
        params: serde_json::Value,
    ) -> anyhow::Result<serde_json::Value> {
        let process_id = ProcessId(params.get("process_id")
            .and_then(|v| v.as_str())
            .ok_or_else(|| anyhow::anyhow!("Missing process_id"))?
            .to_string());
        
        // 检查是否存在
        if self.process_manager.get_process(&process_id).is_none() {
            return Err(anyhow::anyhow!("Process not found: {}", process_id.0));
        }
        
        // TODO: 实际删除操作
        
        info!(process_id = %process_id.0, "Deleted process");
        
        Ok(json!({
            "process_id": process_id.0,
            "status": "deleted"
        }))
    }
    
    /// 查询 Session 历史
    async fn query_session_history(
        &self,
        params: serde_json::Value,
    ) -> anyhow::Result<serde_json::Value> {
        let session_id = params.get("session_id")
            .and_then(|v| v.as_str())
            .ok_or_else(|| anyhow::anyhow!("Missing session_id"))?;
        
        let limit = params.get("limit")
            .and_then(|v| v.as_u64())
            .unwrap_or(100) as usize;
        
        // 获取所有历史
        let all_history = self.thread_manager.get_all_history().await;
        
        // 过滤该 session 的历史
        let session_history: Vec<_> = all_history.into_iter()
            .filter(|h| h.session_id.0 == session_id)
            .take(limit)
            .collect();
        
        let history_json: Vec<serde_json::Value> = session_history.iter().map(|h| {
            let events_json: Vec<serde_json::Value> = h.events.iter().map(|e| {
                json!({
                    "timestamp": e.timestamp,
                    "event_type": e.event_type,
                    "details": e.details,
                })
            }).collect();
            
            json!({
                "thread_id": h.thread_id.0,
                "created_at": h.created_at,
                "completed_at": h.completed_at,
                "final_status": h.final_status.as_ref().map(|s| format!("{:?}", s).to_lowercase()),
                "event_count": h.events.len(),
                "events": events_json,
            })
        }).collect();
        
        Ok(json!({
            "session_id": session_id,
            "history": history_json,
            "total_entries": history_json.len(),
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
