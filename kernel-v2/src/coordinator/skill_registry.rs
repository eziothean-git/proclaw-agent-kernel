//! Skill Registry - Skill 注册和路由中心
//! 
//! 管理所有可用的 Skills，提供统一的执行接口
//! 
//! 权限层级：
//! - Prime (P0): 可以访问所有 Skills（包括 OS Interface）
//! - Host (P1): 可以访问 Scheduler 及以下
//! - Agent (P3): 只能访问基础 Skills（Bash 等）

use std::sync::Arc;
use tracing::{info, instrument, warn};

use crate::auth::CapabilityLevel;
use crate::coordinator::models::{SkillRequest, SkillResult};
use crate::skills::BashSkill;
#[cfg(feature = "control-plane")]
use crate::skills::{OSInterfaceSkill, SchedulerSkill};

use tokio::sync::RwLock;

/// Skill 注册表
pub struct SkillRegistry {
    // 本地 Skills
    bash_skill: Arc<BashSkill>,
    #[cfg(feature = "control-plane")]
    scheduler_skill: RwLock<Option<Arc<SchedulerSkill>>>,
    #[cfg(feature = "control-plane")]
    os_interface_skill: RwLock<Option<Arc<OSInterfaceSkill>>>,
}

impl SkillRegistry {
    /// 创建新的 Skill 注册表（基础 Skills）
    pub fn new(bash_skill: Arc<BashSkill>) -> Self {
        Self {
            bash_skill,
            #[cfg(feature = "control-plane")]
            scheduler_skill: RwLock::new(None),
            #[cfg(feature = "control-plane")]
            os_interface_skill: RwLock::new(None),
        }
    }

    /// 注册 Scheduler Skill（延迟注册，解决循环依赖）
    #[cfg(feature = "control-plane")]
    pub async fn register_scheduler_skill(&self, skill: Arc<SchedulerSkill>) {
        let mut guard = self.scheduler_skill.write().await;
        *guard = Some(skill);
    }

    /// 注册 OS Interface Skill（延迟注册，解决循环依赖）
    #[cfg(feature = "control-plane")]
    pub async fn register_os_interface_skill(&self, skill: Arc<OSInterfaceSkill>) {
        let mut guard = self.os_interface_skill.write().await;
        *guard = Some(skill);
    }
    
    /// 执行 Agent 可直接调用的 Skill
    #[instrument(skip(self, request), fields(skill = %request.skill_name, tool = %request.tool_name))]
    pub async fn execute_agent(
        &self,
        request: SkillRequest,
    ) -> anyhow::Result<SkillResult> {
        info!(
            skill = %request.skill_name,
            tool = %request.tool_name,
            "Executing skill"
        );
        
        match request.skill_name.as_str() {
            "bash" => {
                self.bash_skill.execute(
                    &request.tool_name,
                    request.parameters,
                    request.context,
                ).await
            }
            _ => Ok(SkillResult {
                request_id: request.request_id,
                success: false,
                result: None,
                error: Some(format!("Unknown skill: {}", request.skill_name)),
                execution_time_ms: 0,
            }),
        }
    }

    /// 执行 Host/Prime 控制面 Skill（带权限检查）
    #[cfg(feature = "control-plane")]
    #[instrument(skip(self, request), fields(skill = %request.skill_name, tool = %request.tool_name))]
    pub async fn execute_control(
        &self,
        request: SkillRequest,
        caller_level: CapabilityLevel,
    ) -> anyhow::Result<SkillResult> {
        info!(
            skill = %request.skill_name,
            tool = %request.tool_name,
            caller = %caller_level.name(),
            "Executing control skill"
        );

        match request.skill_name.as_str() {
            "bash" => {
                self.bash_skill.execute(
                    &request.tool_name,
                    request.parameters,
                    request.context,
                ).await
            }
            "scheduler" => {
                if !caller_level.can_access(CapabilityLevel::Host) {
                    warn!(
                        caller = %caller_level.name(),
                        skill = "scheduler",
                        "Permission denied: Host level required"
                    );
                    return Ok(SkillResult {
                        request_id: request.request_id,
                        success: false,
                        result: None,
                        error: Some("Permission denied: Host level required for scheduler skill".to_string()),
                        execution_time_ms: 0,
                    });
                }
                
                let guard = self.scheduler_skill.read().await;
                if let Some(ref skill) = *guard {
                    skill.execute(
                        &request.tool_name,
                        request.parameters,
                        request.context,
                    ).await
                } else {
                    Ok(SkillResult {
                        request_id: request.request_id,
                        success: false,
                        result: None,
                        error: Some("Scheduler skill not registered".to_string()),
                        execution_time_ms: 0,
                    })
                }
            }
            "os_interface" => {
                if !caller_level.can_access(CapabilityLevel::Prime) {
                    warn!(
                        caller = %caller_level.name(),
                        skill = "os_interface",
                        "Permission denied: Prime level required"
                    );
                    return Ok(SkillResult {
                        request_id: request.request_id,
                        success: false,
                        result: None,
                        error: Some("Permission denied: Prime level required for OS interface skill".to_string()),
                        execution_time_ms: 0,
                    });
                }
                
                let guard = self.os_interface_skill.read().await;
                if let Some(ref skill) = *guard {
                    skill.execute(
                        &request.tool_name,
                        request.parameters,
                        request.context,
                    ).await
                } else {
                    Ok(SkillResult {
                        request_id: request.request_id,
                        success: false,
                        result: None,
                        error: Some("OS interface skill not registered".to_string()),
                        execution_time_ms: 0,
                    })
                }
            }
            _ => Ok(SkillResult {
                request_id: request.request_id,
                success: false,
                result: None,
                error: Some(format!("Unknown skill: {}", request.skill_name)),
                execution_time_ms: 0,
            }),
        }
    }
    
    /// 列出所有可用的 Skills
    pub async fn list_skills(&self) -> Vec<&str> {
        #[cfg(not(feature = "control-plane"))]
        {
            return vec!["bash"];
        }

        #[cfg(feature = "control-plane")]
        {
        let mut skills = vec!["bash"];

        let scheduler_guard = self.scheduler_skill.read().await;
        if scheduler_guard.is_some() {
            skills.push("scheduler");
        }

        let os_guard = self.os_interface_skill.read().await;
        if os_guard.is_some() {
            skills.push("os_interface");
        }

        skills
        }
    }

    pub async fn list_tools(&self, skill_name: &str) -> Option<Vec<serde_json::Value>> {
        match skill_name {
            "bash" => {
                Some(self.bash_skill.list_tools().into_iter()
                    .map(|t| serde_json::json!({
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.parameters,
                    }))
                    .collect())
            }
            #[cfg(feature = "control-plane")]
            "scheduler" => {
                let guard = self.scheduler_skill.read().await;
                guard.as_ref().map(|skill| {
                    skill.list_tools().into_iter()
                        .map(|t| serde_json::json!({
                            "name": t.name,
                            "description": t.description,
                            "parameters": t.parameters,
                        }))
                        .collect()
                })
            }
            #[cfg(feature = "control-plane")]
            "os_interface" => {
                let guard = self.os_interface_skill.read().await;
                guard.as_ref().map(|skill| {
                    skill.list_tools().into_iter()
                        .map(|t| serde_json::json!({
                            "name": t.name,
                            "description": t.description,
                            "parameters": t.parameters,
                        }))
                        .collect()
                })
            }
            _ => None,
        }
    }
}
