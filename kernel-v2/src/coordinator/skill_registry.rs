//! Skill Registry - Skill 注册和路由中心
//! 
//! 管理所有可用的 Skills，提供统一的执行接口

use std::sync::Arc;
use tracing::{debug, error, info, instrument};

use crate::coordinator::models::{SkillContext, SkillRequest, SkillResult};
use crate::skills::{
    BashSkill,
    SchedulerSkill,
    OSInterfaceSkill,
};

/// Skill 注册表
pub struct SkillRegistry {
    // 本地 Skills
    bash_skill: Arc<BashSkill>,
    scheduler_skill: Option<Arc<SchedulerSkill>>,
    os_interface_skill: Option<Arc<OSInterfaceSkill>>,
}

impl SkillRegistry {
    /// 创建新的 Skill 注册表（基础 Skills）
    pub fn new(bash_skill: Arc<BashSkill>) -> Self {
        Self {
            bash_skill,
            scheduler_skill: None,
            os_interface_skill: None,
        }
    }
    
    /// 注册 Scheduler Skill
    pub fn register_scheduler_skill(mut self, skill: Arc<SchedulerSkill>) -> Self {
        self.scheduler_skill = Some(skill);
        self
    }
    
    /// 注册 OS Interface Skill
    pub fn register_os_interface_skill(mut self, skill: Arc<OSInterfaceSkill>) -> Self {
        self.os_interface_skill = Some(skill);
        self
    }
    
    /// 执行 Skill
    #[instrument(skip(self, request), fields(skill = %request.skill_name, tool = %request.tool_name))]
    pub async fn execute(
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
            "scheduler" => {
                if let Some(ref skill) = self.scheduler_skill {
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
                if let Some(ref skill) = self.os_interface_skill {
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
            _ => {
                Ok(SkillResult {
                    request_id: request.request_id,
                    success: false,
                    result: None,
                    error: Some(format!("Unknown skill: {}", request.skill_name)),
                    execution_time_ms: 0,
                })
            }
        }
    }
    
    /// 列出所有可用的 Skills
    pub fn list_skills(&self) -> Vec<&str> {
        let mut skills = vec!["bash"];
        
        if self.scheduler_skill.is_some() {
            skills.push("scheduler");
        }
        
        if self.os_interface_skill.is_some() {
            skills.push("os_interface");
        }
        
        skills
    }
    
    /// 获取特定 Skill 的工具列表
    pub fn list_tools(&self, skill_name: &str) -> Option<Vec<serde_json::Value>> {
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
            "scheduler" => {
                self.scheduler_skill.as_ref().map(|skill| {
                    skill.list_tools().into_iter()
                        .map(|t| serde_json::json!({
                            "name": t.name,
                            "description": t.description,
                            "parameters": t.parameters,
                        }))
                        .collect()
                })
            }
            "os_interface" => {
                self.os_interface_skill.as_ref().map(|skill| {
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
