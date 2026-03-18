//! Thread Scheduler - Thread Executor 管理
//! 
//! 通过 gRPC 接口接受 Session Host 的管理请求：
//! - spawn_executor: 创建并启动 Thread Executor
//! - pause_executor: 暂停执行
//! - resume_thread: 从存储恢复 Thread 并创建新 Executor
//! - kill_executor: 销毁 Executor（保留 Thread）
//! - query_status: 查询状态

pub mod batch_task_executor;
pub mod context_builder;
pub mod multi_session_orchestrator;
pub mod output_parser;
pub mod parallel_executor;
pub mod scheduler;
pub mod snapshot_collector;
pub mod thread_executor;
pub mod time_budget_monitor;
pub mod xml_models;
pub mod xml_parser;

#[cfg(feature = "control-plane")]
pub mod thread_manager;

pub use context_builder::ContextBuilder;
pub use thread_executor::WorkingSet;
pub use multi_session_orchestrator::{
    MultiSessionOrchestrator, ParallelConfig, MultiSessionResult, SubTask,
    convert_processes_to_sub_tasks,
};
pub use output_parser::OutputParser;
pub use parallel_executor::{ParallelActionExecutor, ExecutionMode, DependencyAnalyzer};
pub use scheduler::ThreadScheduler;
pub use snapshot_collector::{TaskSnapshotCollector, TaskSnapshot, TaskSnapshotStatus, ObservationRecord};
pub use thread_executor::{
    ThreadExecutor, ExecutorState, ExecutorEvent, CompletionReason,
    ParsedIntent, IntentType, ToolCallIntent, PhaseTransitionIntent,
};
pub use time_budget_monitor::{TimeBudgetMonitor, TimeBudgetConfig, TimeBudgetReport, TimeWarning};
pub use xml_models::{
    AgentResponse, SystemNotice, NoticeMetadata, 
    TaskStatusReport, CompletedTaskReport, InterruptedTaskReport
};
pub use xml_parser::XmlOutputParser;
