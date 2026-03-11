//! 权限系统 - Capability Token 层级管理

use serde::{Deserialize, Serialize};

/// Capability 层级
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum CapabilityLevel {
    /// 底层 Agent - 只能访问普通 Skills
    Agent = 0,
    /// Session Host - 可以访问 Scheduler Skill
    Host = 1,
    /// 主人格 - 可以访问所有 Skills（包括 OS Interface）
    Prime = 2,
}

impl Default for CapabilityLevel {
    fn default() -> Self {
        CapabilityLevel::Agent
    }
}

impl CapabilityLevel {
    /// 检查是否有权限访问指定 Skill
    pub fn can_access(&self, required: CapabilityLevel) -> bool {
        *self >= required
    }
    
    /// 获取层级名称
    pub fn name(&self) -> &'static str {
        match self {
            CapabilityLevel::Agent => "agent",
            CapabilityLevel::Host => "host",
            CapabilityLevel::Prime => "prime",
        }
    }
}