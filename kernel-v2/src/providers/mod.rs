//! Providers for data sources
//!
//! BashWrapper: Unified command execution with mode-based security
//! MemoryProvider: Long-term memory storage

pub mod bash;
pub mod memory;

// Re-export main types
pub use bash::{BashWrapper, BashRequest, BashOutput, ExecutionMode, BashWrapperConfig};
pub use memory::{MemoryProvider, MemoryFact, MemoryQuery};
