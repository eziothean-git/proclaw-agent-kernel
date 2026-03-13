//! Executor 模块 - 执行 Prime 生成的 IR
//!
//! 提供完整的 IR 执行链路，包括：
//! - IR Process 解析和执行
//! - 执行结果收集
//! - 向 Prime 汇报

pub mod ir_executor;

pub use ir_executor::{
    IRProcessExecutor,
    ProcessExecutionResult,
    ExecutionStep,
    ArtifactInfo,
    SessionExecutionLog,
    ProcessExecutionLog,
    ExecutionReport,
};
