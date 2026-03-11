//! Agent Thread 文件存储系统
//! 
//! 遵循"一切皆文件"哲学，提供：
//! - 历史快照存储（Event Log + Artifacts）
//! - 原子写入保证
//! - 并发安全（文件锁）
//! - 查询优化（索引）

pub mod models;
pub mod storage;
pub mod error;

pub use models::*;
pub use storage::ThreadStorage;
pub use error::ThreadError;