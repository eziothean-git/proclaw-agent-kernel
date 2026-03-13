//! Execution Coordinator 数据模型

use crate::auth::CapabilityLevel;
use serde::{Deserialize, Serialize};

/// Skill 请求
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SkillRequest {
    pub request_id: String,
    pub skill_name: String,
    pub tool_name: String,
    pub parameters: serde_json::Value,
    pub context: SkillContext,
}

/// Skill 执行上下文
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SkillContext {
    pub thread_id: String,
    pub session_id: String,
    pub executor_id: String,
    pub capability_level: CapabilityLevel,  // 权限层级
    pub working_dirs: Vec<String>,  // 需要锁定的目录
}

/// Skill 执行结果
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SkillResult {
    pub request_id: String,
    pub success: bool,
    pub result: Option<serde_json::Value>,
    pub error: Option<String>,
    pub execution_time_ms: u64,
}
