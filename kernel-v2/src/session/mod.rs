//! Session 管理模块
//! 
//! 提供 Session Host 层和 Process 管理功能

pub mod process;
pub mod skills;

pub use process::{Process, ProcessId, ProcessManager, ProcessMeta, ProcessStatus, ThreadSummary};
pub use skills::{
    SessionHostSkills, ProcessSummary, ProcessDetail, ThreadBrief, ThreadStatusInProcess,
};