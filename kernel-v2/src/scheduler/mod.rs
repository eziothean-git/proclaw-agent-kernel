//! Thread Scheduler - Thread Executor 管理
//! 
//! 通过 gRPC 接口接受 Session Host 的管理请求：
//! - spawn_executor: 创建并启动 Thread Executor
//! - pause_executor: 暂停执行
//! - resume_thread: 从存储恢复 Thread 并创建新 Executor
//! - kill_executor: 销毁 Executor（保留 Thread）
//! - query_status: 查询状态

pub mod context_builder;
pub mod output_parser;
pub mod scheduler;
pub mod thread_executor;
#[cfg(feature = "control-plane")]
pub mod thread_manager;

pub use context_builder::{ContextBuilder, WorkingSet};
pub use output_parser::OutputParser;
pub use scheduler::ThreadScheduler;
pub use thread_executor::{
    ThreadExecutor, ExecutorState, ExecutorEvent, CompletionReason,
    ParsedIntent, IntentType, ToolCallIntent, PhaseTransitionIntent,
};
