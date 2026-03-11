//! Skills 模块 - 将内部组件封装为可调用 Skill
//! 
//! 提供：
//! - BashSkill: 本地命令执行
//! - SchedulerSkill: Thread 调度管理（Host/Prime）
//! - OSInterfaceSkill: 系统接口（Prime only）

pub mod bash_skill;
pub mod scheduler_skill;
pub mod os_interface_skill;

pub use bash_skill::{BashSkill, ToolDefinition};
pub use scheduler_skill::SchedulerSkill;
pub use os_interface_skill::OSInterfaceSkill;