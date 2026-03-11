//! LLM Client - 基础设施层
//! 
//! 提供 LLM 调用服务，可被多个 Thread Executor 共享

pub mod client;
pub mod config;
pub mod models;
pub mod router;

pub use client::{LLMClient, SimpleLLMClient, MockLLMClient};
pub use config::{ProviderConfig, ProviderType, DifficultyLevel, LLMRouterConfig, LLMRequestConfig};
pub use models::*;
pub use router::{LLMRouter, RequestId};