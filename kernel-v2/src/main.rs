//! ProClaw Agent Kernel - Main Entry Point
//!
//! 完整的 Agent Kernel v2，替代原有的 Python Kernel
//! 提供服务：
//! - BlockComposer: 上下文编译服务（gRPC）
//! - AgentKernel: Agent 执行引擎（gRPC）

use clap::Parser;
use std::path::PathBuf;
use std::sync::Arc;
use tokio::net::UnixListener;
use tokio_stream::wrappers::UnixListenerStream;
use tonic::transport::Server;
use tracing::{info, warn};

mod agent_thread;
mod block_composer;
mod config;
mod coordinator;
mod llm;
mod observability;
mod providers;
mod auth;
mod scheduler;
mod server;
mod session;
mod skills;

use config::ComposerConfig;
use server::{ComposerServer, agent_kernel::{AgentKernelService, AgentKernelConfig}};
use server::agent_kernel::proto::agent_kernel_server::AgentKernelServer;
use server::proto::block_composer_server::BlockComposerServer;

/// ProClaw Agent Kernel v2
#[derive(Parser, Debug)]
#[command(name = "proclaw-agent-kernel")]
#[command(about = "Agent Kernel v2 - Rust implementation replacing Python Kernel")]
#[command(version)]
struct Args {
    /// Path to configuration file
    #[arg(short, long, default_value = "/etc/proclaw/composer.yaml")]
    config: PathBuf,

    /// Run as daemon
    #[arg(short, long)]
    daemon: bool,

    /// Socket path (overrides config)
    #[arg(short, long)]
    socket: Option<PathBuf>,

    /// Data directory (overrides config)
    #[arg(short, long)]
    data_dir: Option<PathBuf>,

    /// LLM API Key (or set OPENAI_API_KEY env var)
    #[arg(long, env = "OPENAI_API_KEY")]
    llm_api_key: Option<String>,

    /// LLM Model
    #[arg(long, default_value = "gpt-4")]
    llm_model: String,

    /// LLM Base URL
    #[arg(long, default_value = "https://api.openai.com/v1")]
    llm_base_url: String,
}

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    // Parse command line arguments
    let args = Args::parse();

    // Initialize tracing
    tracing_subscriber::fmt()
        .with_env_filter(tracing_subscriber::EnvFilter::from_default_env())
        .with_target(true)
        .with_thread_ids(true)
        .with_line_number(true)
        .init();

    info!("Starting ProClaw Agent Kernel v{}", env!("CARGO_PKG_VERSION"));

    // Load configuration
    let mut config = ComposerConfig::load(&args.config).await?;
    
    // Apply command line overrides
    if let Some(socket) = args.socket {
        config.server.socket_path = socket;
    }
    // Create data directory
    let data_path = args.data_dir.clone().unwrap_or_else(|| PathBuf::from("./data"));
    
    if let Some(data_dir) = args.data_dir {
        config.cache.l2.path = data_dir.join("cache.db");
        config.observability.traces.base_path = data_dir.join("traces");
    }

    info!("Configuration loaded from: {}", args.config.display());
    info!("Socket path: {}", config.server.socket_path.display());
    info!("Workers: {}", config.server.workers);
    tokio::fs::create_dir_all(&data_path).await?;

    // Create BlockComposer service
    let composer_server = ComposerServer::new(config.clone()).await?;
    let block_composer = composer_server.composer.clone();

    // Create AgentKernel service
    let agent_kernel_config = AgentKernelConfig {
        data_path: data_path.clone(),
        llm_base_url: args.llm_base_url,
        llm_api_key: args.llm_api_key.unwrap_or_default(),
        llm_model: args.llm_model,
    };

    let agent_kernel_service = AgentKernelService::new(
        agent_kernel_config,
        block_composer,
    ).await?;

    // Start background tasks
    agent_kernel_service.start_background_tasks().await;

    // Notify systemd if available (optional)
    #[cfg(feature = "systemd")]
    {
        if let Err(e) = sd_notify::notify(true, &[sd_notify::NotifyState::Ready]) {
            warn!("Failed to notify systemd: {}", e);
        }
    }

    // Setup Unix socket
    let socket_path = &config.server.socket_path;
    if let Some(parent) = socket_path.parent() {
        tokio::fs::create_dir_all(parent).await?;
    }
    if socket_path.exists() {
        tokio::fs::remove_file(socket_path).await?;
    }

    info!("Starting gRPC server on: {}", socket_path.display());

    // Create Unix listener
    let listener = UnixListener::bind(socket_path)?;
    let stream = UnixListenerStream::new(listener);

    // Build and serve both services
    info!("Agent Kernel ready - serving BlockComposer and AgentKernel");
    
    Server::builder()
        .add_service(BlockComposerServer::new(composer_server))
        .add_service(AgentKernelServer::new(agent_kernel_service))
        .serve_with_incoming(stream)
        .await?;

    Ok(())
}