//! Execution Coordinator - 系统级资源协调层
//! 
//! 跨线程、跨进程、跨 Session 的资源协调
//! - 目录锁定（FIFO 队列）
//! - Skill 路由（Local/Remote）
//! - Ticket 追踪

pub mod coordinator_impl;
pub mod lock_manager;
pub mod models;
pub mod router;
pub mod skill_registry;
pub mod ticket;

pub use coordinator_impl::{ExecutionCoordinator, CoordinatorStats, RouteDecision};
pub use lock_manager::{DirectoryLockManager, DirectoryLock, LockLevel};
pub use models::*;
pub use skill_registry::SkillRegistry;