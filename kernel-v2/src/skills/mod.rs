//! Skills 模块 - 将内部组件封装为可调用 Skill
//! 
//! 提供：
//! - BashSkill: 本地命令执行
//! 
//! 控制面技能默认不编入当前 binary，避免把未接线实现混入活跃运行链。
//! - SchedulerSkill: Thread 调度管理（Host/Prime）
//! - OSInterfaceSkill: 系统接口（Prime only）

pub mod bash_skill;
pub mod composer_skill;
#[cfg(feature = "control-plane")]
pub mod scheduler_skill;
#[cfg(feature = "control-plane")]
pub mod os_interface_skill;

pub use bash_skill::{BashSkill, ToolDefinition};
pub use composer_skill::ComposerSkill;
#[cfg(feature = "control-plane")]
pub use scheduler_skill::SchedulerSkill;
#[cfg(feature = "control-plane")]
pub use os_interface_skill::OSInterfaceSkill;
