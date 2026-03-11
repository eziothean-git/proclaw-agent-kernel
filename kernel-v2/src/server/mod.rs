//! gRPC Server Module
//! 
//! 提供两种服务：
//! 1. BlockComposer - 上下文编译服务（原有）
//! 2. AgentKernel - Agent 执行引擎（新增）

pub mod agent_kernel;
pub mod composer_server;

pub use agent_kernel::{
    AgentKernelService, AgentKernelConfig, proto as agent_proto,
};

// Include generated proto code
pub mod proto {
    tonic::include_proto!("proclaw.block_composer.v1");
}

pub use composer_server::ComposerServer;