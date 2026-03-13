//! gRPC server implementation (simplified for Phase 2)

use crate::{
    auth::{AuthConfig, AuthManager},
    block_composer::{BlockComposerEngine, MetricsCollector},
    config::ComposerConfig,
    observability::{TraceCollector, TraceRecord},
    providers::bash::{BashWrapper, BashRequest, BashWrapperConfig, ExecutionMode},
};
use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::Arc;
use tokio::net::UnixListener;
use tokio::sync::mpsc;
use tokio_stream::wrappers::{ReceiverStream, UnixListenerStream};
use tonic::{transport::Server, Request, Response, Status};
use tracing::info;


// Use the proto module from server
use crate::server::proto;
use proto::block_composer_server::{BlockComposer, BlockComposerServer};
use proto::*;

/// Composer server implementation
pub struct ComposerServer {
    config: ComposerConfig,
    pub(crate) composer: Arc<BlockComposerEngine>,
    bash_wrapper: Arc<BashWrapper>,
    auth_manager: Arc<AuthManager>,
    _metrics: Arc<MetricsCollector>,
    tracer: Arc<TraceCollector>,
}

impl ComposerServer {
    /// Create new server instance
    pub async fn new(config: ComposerConfig) -> anyhow::Result<Self> {
        // Initialize auth manager
        let secret_key = std::env::var("COMPOSER_SECRET_KEY")
            .unwrap_or_else(|_| "default-secret-key-change-in-production".to_string());
        
        let auth_config = AuthConfig {
            secret_key,
            default_ttl_seconds: config.permissions.default_token_ttl_seconds,
            default_max_calls: config.permissions.default_max_calls,
        };
        
        let auth_manager = Arc::new(AuthManager::new(auth_config)?);
        
        // Initialize providers
        let bash_config: BashWrapperConfig = config.providers.bash.clone().into();
        let bash_wrapper = Arc::new(BashWrapper::new(bash_config));
        
        // Initialize composer
        let composer = Arc::new(BlockComposerEngine::new(&config).await?);
        
        // Initialize observability
        let metrics = Arc::new(MetricsCollector::new(&config.observability.metrics));
        let tracer = Arc::new(TraceCollector::new(&config.observability.traces).await?);
        
        info!("ComposerServer initialized");
        
        Ok(Self {
            config,
            composer,
            bash_wrapper,
            auth_manager,
            _metrics: metrics,
            tracer,
        })
    }

    pub fn composer(&self) -> Arc<BlockComposerEngine> {
        self.composer.clone()
    }

    /// Run the server
    pub async fn run(self) -> anyhow::Result<()> {
        let socket_path = &self.config.server.socket_path;

        // Ensure parent directory exists
        if let Some(parent) = socket_path.parent() {
            tokio::fs::create_dir_all(parent).await?;
        }

        // Remove old socket if exists
        if socket_path.exists() {
            tokio::fs::remove_file(socket_path).await?;
        }

        info!("Starting gRPC server on: {}", socket_path.display());

        // Create Unix listener
        let listener = UnixListener::bind(socket_path)?;
        let stream = UnixListenerStream::new(listener);

        // Build and serve
        Server::builder()
            .add_service(BlockComposerServer::new(self))
            .serve_with_incoming(stream)
            .await?;

        Ok(())
    }
}

#[tonic::async_trait]
impl BlockComposer for ComposerServer {
    type SubscribeTracesStream = ReceiverStream<Result<TraceEvent, Status>>;

    async fn compose(
        &self,
        request: Request<ComposeRequest>,
    ) -> Result<Response<ComposeResponse>, Status> {
        let req = request.into_inner();
        let start = std::time::Instant::now();
        
        info!("Compose request: session={}", req.session_id);

        // Convert blocks
        let blocks: Vec<proto::Block> = req.block_types.iter().map(|bt| proto::Block {
            block_id: format!("block_{}_{}", req.session_id, bt),
            block_type: *bt,
            content: format!("Content for block type {:?}", bt),
            metadata: vec![],
            priority: 5,
            token_count: 100,
            dependencies: vec![],
            content_hash: String::new(),
            created_at: Some(prost_types::Timestamp::from(std::time::SystemTime::now())),
        }).collect();

        // Call composer
        let result = match self.composer.compose(
            &req.session_id,
            &req.task_id,
            req.profile(),
            blocks,
            req.context,
        ).await {
            Ok(response) => {
                // Record successful compose trace
                let trace = TraceRecord::new(
                    format!("trace_{}", uuid::Uuid::new_v4().to_string()[..8].to_string()),
                    req.session_id.clone(),
                    self.tracer.thread_id(),
                    "compose",
                )
                .with_duration(start.elapsed().as_millis() as u64)
                .with_success(true)
                .with_extra_field("block_count", req.block_types.len())
                .unwrap_or_else(|_| TraceRecord::new(
                    format!("trace_{}", uuid::Uuid::new_v4().to_string()[..8].to_string()),
                    req.session_id.clone(),
                    self.tracer.thread_id(),
                    "compose",
                ));
                
                let _ = self.tracer.record(trace).await;
                Ok(Response::new(response))
            }
            Err(e) => {
                // Record failed compose trace
                let trace = TraceRecord::new(
                    format!("trace_{}", uuid::Uuid::new_v4().to_string()[..8].to_string()),
                    req.session_id.clone(),
                    self.tracer.thread_id(),
                    "compose",
                )
                .with_duration(start.elapsed().as_millis() as u64)
                .with_success(false)
                .with_error(e.to_string());
                
                let _ = self.tracer.record(trace).await;
                Err(Status::internal(format!("Composition failed: {}", e)))
            }
        };
        
        result
    }

    async fn query_blocks(
        &self,
        _request: Request<QueryBlocksRequest>,
    ) -> Result<Response<QueryBlocksResponse>, Status> {
        Err(Status::unimplemented("Not yet implemented"))
    }

    async fn execute_bash(
        &self,
        request: Request<ExecuteBashRequest>,
    ) -> Result<Response<ExecuteBashResponse>, Status> {
        let req = request.into_inner();
        let start = std::time::Instant::now();

        // Verify token
        let token = match self.auth_manager.verify_token(&req.capability_token).await {
            Ok(t) => t,
            Err(e) => return Err(Status::permission_denied(format!("Invalid token: {}", e))),
        };

        let remaining = token.remaining_calls();

        // Determine execution mode from command
        let mode = Self::detect_execution_mode(&req.command);

        // Parse arguments from the command
        let args = Self::parse_arguments(&req.command);
        let cmd = args.first().cloned().unwrap_or_default();
        let cmd_args = if args.len() > 1 {
            args[1..].to_vec()
        } else {
            vec![]
        };

        // Build bash request
        let working_dir = if req.working_directory.is_empty() {
            None
        } else {
            Some(PathBuf::from(&req.working_directory))
        };

        let bash_req = BashRequest::new(&cmd, cmd_args)
            .with_mode(mode)
            .with_working_dir(working_dir.clone().unwrap_or_else(|| PathBuf::from(".")));

        // Execute
        let result = match self.bash_wrapper.execute(bash_req).await {
            Ok(result) => {
                let error_message = if result.success {
                    String::new()
                } else {
                    result.stderr.clone()
                };
                
                // Record trace
                let trace = TraceRecord::new(
                    format!("trace_{}", uuid::Uuid::new_v4().to_string()[..8].to_string()),
                    req.session_id.clone(),
                    self.tracer.thread_id(),
                    "bash_execute",
                )
                .with_mode(format!("{:?}", mode))
                .with_command(req.command.clone())
                .with_working_directory(working_dir.unwrap_or_else(|| PathBuf::from(".")))
                .with_duration(start.elapsed().as_millis() as u64)
                .with_success(result.success)
                .with_output_size(result.stdout.len() as u64)
                .with_token_subject(token.claims.sub.clone());
                
                let _ = self.tracer.record(trace).await;
                
                Ok(Response::new(ExecuteBashResponse {
                    success: result.success,
                    stdout: result.stdout,
                    stderr: result.stderr,
                    exit_code: result.exit_code,
                    execution_time_ms: result.execution_time_ms as i64,
                    error_message,
                    remaining_calls: remaining.saturating_sub(1),
                }))
            }
            Err(e) => {
                // Record failed trace
                let trace = TraceRecord::new(
                    format!("trace_{}", uuid::Uuid::new_v4().to_string()[..8].to_string()),
                    req.session_id,
                    self.tracer.thread_id(),
                    "bash_execute",
                )
                .with_mode(format!("{:?}", mode))
                .with_command(req.command)
                .with_duration(start.elapsed().as_millis() as u64)
                .with_success(false)
                .with_error(e.to_string())
                .with_token_subject(token.claims.sub.clone());
                
                let _ = self.tracer.record(trace).await;
                
                Err(Status::internal(format!("Execution failed: {}", e)))
            }
        };
        
        result
    }

    async fn validate_token(
        &self,
        request: Request<ValidateTokenRequest>,
    ) -> Result<Response<ValidateTokenResponse>, Status> {
        let req = request.into_inner();
        
        match self.auth_manager.verify_token(&req.token).await {
            Ok(tracked) => {
                let expires_at = if tracked.is_valid() {
                    Some(prost_types::Timestamp::from(std::time::SystemTime::from(
                        chrono::DateTime::from_timestamp(tracked.claims.exp, 0)
                            .unwrap_or_else(|| chrono::Utc::now())
                    )))
                } else {
                    None
                };
                
                Ok(Response::new(ValidateTokenResponse {
                    valid: tracked.is_valid(),
                    subject: tracked.claims.sub.clone(),
                    level: tracked.claims.level.to_string(),
                    scopes: tracked.claims.scopes.iter().map(|s| format!("{:?}", s)).collect(),
                    remaining_calls: tracked.remaining_calls(),
                    expires_at,
                }))
            }
            Err(_) => {
                Ok(Response::new(ValidateTokenResponse {
                    valid: false,
                    subject: String::new(),
                    level: String::new(),
                    scopes: vec![],
                    remaining_calls: 0,
                    expires_at: None,
                }))
            }
        }
    }

    async fn revoke_token(
        &self,
        request: Request<RevokeTokenRequest>,
    ) -> Result<Response<RevokeTokenResponse>, Status> {
        let req = request.into_inner();
        
        let subject = req.token.trim_start_matches("token_");
        let success = self.auth_manager.revoke_token(subject).await
            .unwrap_or(false);
        
        Ok(Response::new(RevokeTokenResponse { success }))
    }

    async fn get_trace(
        &self,
        _request: Request<GetTraceRequest>,
    ) -> Result<Response<TraceResponse>, Status> {
        Err(Status::unimplemented("Not yet implemented"))
    }

    async fn list_traces(
        &self,
        _request: Request<ListTracesRequest>,
    ) -> Result<Response<ListTracesResponse>, Status> {
        Err(Status::unimplemented("Not yet implemented"))
    }

    async fn replay_trace(
        &self,
        _request: Request<ReplayTraceRequest>,
    ) -> Result<Response<ReplayTraceResponse>, Status> {
        Err(Status::unimplemented("Not yet implemented"))
    }

    async fn get_metrics(
        &self,
        _request: Request<GetMetricsRequest>,
    ) -> Result<Response<MetricsResponse>, Status> {
        match self.composer.get_cache_stats().await {
            Ok(stats) => {
                let mut gauges = HashMap::new();
                gauges.insert("l1_cache_size".to_string(), stats.l1.len as f64);
                gauges.insert("l2_cache_size_mb".to_string(), stats.l2.size_mb);
                
                Ok(Response::new(MetricsResponse {
                    counters: HashMap::new(),
                    gauges,
                    histograms: HashMap::new(),
                }))
            }
            Err(e) => {
                Err(Status::internal(format!("Failed to get metrics: {}", e)))
            }
        }
    }

    async fn subscribe_traces(
        &self,
        _request: Request<SubscribeTracesRequest>,
    ) -> Result<Response<Self::SubscribeTracesStream>, Status> {
        let (_tx, rx) = mpsc::channel(100);
        Ok(Response::new(ReceiverStream::new(rx)))
    }
}

// Helper methods for ComposerServer (not part of the trait)
impl ComposerServer {
    /// Detect execution mode from command string
    fn detect_execution_mode(command: &str) -> ExecutionMode {
        let cmd_lower = command.to_lowercase();
        let first_word = cmd_lower.split_whitespace().next().unwrap_or("");

        match first_word {
            "cat" | "ls" | "find" | "pwd" | "readlink" | "realpath" => ExecutionMode::FileMode,
            "rg" | "ast-grep" | "grep" | "ack" | "ag" => ExecutionMode::SearchMode,
            "ps" | "df" | "du" | "uptime" | "uname" | "whoami" | "hostname" => ExecutionMode::SystemMode,
            _ => ExecutionMode::FileMode, // Default to file mode
        }
    }

    /// Parse command string into arguments
    fn parse_arguments(command: &str) -> Vec<String> {
        command
            .split_whitespace()
            .map(|s| s.to_string())
            .collect()
    }
}
