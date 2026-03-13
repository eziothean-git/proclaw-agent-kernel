//! Bash Skill - 本地命令执行
//! 
//! 通过 BashWrapper 执行系统命令

use serde_json::json;
use tracing::{debug, error, info, instrument};

use crate::auth::CapabilityLevel;
use crate::coordinator::models::{SkillContext, SkillResult};
use crate::providers::bash::{BashWrapper, BashRequest, ExecutionMode};

/// Bash Skill
pub struct BashSkill {
    bash_wrapper: std::sync::Arc<BashWrapper>,
}

impl BashSkill {
    pub fn new(bash_wrapper: std::sync::Arc<BashWrapper>) -> Self {
        Self { bash_wrapper }
    }
    
    /// 获取 Skill 名称
    pub fn name(&self) -> &str {
        "bash"
    }
    
    /// 列出可用 Tools
    pub fn list_tools(&self) -> Vec<ToolDefinition> {
        vec![
            ToolDefinition {
                name: "execute".to_string(),
                description: "Execute a bash command".to_string(),
                parameters: json!({
                    "type": "object",
                    "properties": {
                        "command": {
                            "type": "string",
                            "description": "The bash command to execute"
                        },
                        "working_dir": {
                            "type": "string",
                            "description": "Working directory for the command"
                        }
                    },
                    "required": ["command"]
                }),
            },
        ]
    }
    
    /// 执行 Tool
    #[instrument(skip(self, params, context), fields(tool = %tool_name))]
    pub async fn execute(
        &self,
        tool_name: &str,
        params: serde_json::Value,
        context: SkillContext,
    ) -> anyhow::Result<SkillResult> {
        // 检查权限 - 所有 Agent 都可以使用 bash
        if context.capability_level < CapabilityLevel::Agent {
            return Ok(SkillResult {
                request_id: context.thread_id,
                success: false,
                result: None,
                error: Some("Permission denied: bash skill requires Agent level".to_string()),
                execution_time_ms: 0,
            });
        }
        
        match tool_name {
            "execute" => {
                let command = params.get("command")
                    .and_then(|v| v.as_str())
                    .ok_or_else(|| anyhow::anyhow!("Missing command parameter"))?;
                
                let working_dir = params.get("working_dir")
                    .and_then(|v| v.as_str());
                
                info!(
                    command = %command,
                    working_dir = ?working_dir,
                    "Executing bash command"
                );
                
                // 检测执行模式
                let mode = detect_execution_mode(command);
                
                // 创建请求
                let mut request = BashRequest::new("execute", vec![command.to_string()]);
                request.mode = mode;
                
                if let Some(dir) = working_dir {
                    request.working_directory = Some(std::path::PathBuf::from(dir));
                }
                
                // 执行命令
                let start = std::time::Instant::now();
                match self.bash_wrapper.execute(request).await {
                    Ok(output) => {
                        let elapsed = start.elapsed().as_millis() as u64;
                        
                        debug!(
                            success = output.success,
                            stdout_len = output.stdout.len(),
                            stderr_len = output.stderr.len(),
                            "Bash command completed"
                        );
                        
                        Ok(SkillResult {
                            request_id: context.thread_id,
                            success: output.success,
                            result: Some(json!({
                                "stdout": output.stdout,
                                "stderr": output.stderr,
                                "exit_code": output.exit_code,
                            })),
                            error: if output.success { None } else { Some(output.stderr) },
                            execution_time_ms: elapsed,
                        })
                    }
                    Err(e) => {
                        error!(error = %e, "Bash command failed");
                        Ok(SkillResult {
                            request_id: context.thread_id,
                            success: false,
                            result: None,
                            error: Some(format!("Bash execution error: {}", e)),
                            execution_time_ms: start.elapsed().as_millis() as u64,
                        })
                    }
                }
            }
            _ => {
                Ok(SkillResult {
                    request_id: context.thread_id,
                    success: false,
                    result: None,
                    error: Some(format!("Unknown tool: {}", tool_name)),
                    execution_time_ms: 0,
                })
            }
        }
    }
}

/// Tool 定义
#[derive(Debug, Clone)]
pub struct ToolDefinition {
    pub name: String,
    pub description: String,
    pub parameters: serde_json::Value, // JSON Schema
}

/// 检测命令的执行模式
fn detect_execution_mode(command: &str) -> ExecutionMode {
    let cmd_lower = command.to_lowercase();
    let first_word = cmd_lower.split_whitespace().next().unwrap_or("");

    match first_word {
        "cat" | "ls" | "find" | "pwd" | "readlink" | "realpath" | "head" | "tail" => {
            ExecutionMode::FileMode
        }
        "grep" | "rg" | "ack" | "ag" => ExecutionMode::SearchMode,
        _ => ExecutionMode::SystemMode,
    }
}
