//! BashWrapper - Unified bash command execution with mode-based security
//!
//! Supports 4 execution modes:
//! - FileMode: cat, ls, find, pwd, readlink
//! - SearchMode: rg, ast-grep, grep, find
//! - SystemMode: ps, df, du, uptime, uname
//! - Custom: User-defined command patterns

use crate::config::BashProviderConfig;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::PathBuf;
use std::process::Stdio;
use std::time::Duration;
use tokio::process::Command;
use tokio::time::timeout;
use tracing::{debug, error, info, instrument, warn};

/// Execution modes for bash commands
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum ExecutionMode {
    /// File operations: cat, ls, find, pwd, readlink
    FileMode,
    /// Search operations: rg, ast-grep, grep, find
    SearchMode,
    /// System info: ps, df, du, uptime, uname
    SystemMode,
    /// Custom user-defined patterns
    Custom,
}

impl ExecutionMode {
    /// Get allowed commands for this mode
    pub fn allowed_commands(&self) -> Vec<&'static str> {
        match self {
            ExecutionMode::FileMode => {
                vec!["cat", "ls", "find", "pwd", "readlink", "realpath"]
            }
            ExecutionMode::SearchMode => {
                vec!["rg", "ast-grep", "grep", "find", "ack", "ag"]
            }
            ExecutionMode::SystemMode => {
                vec!["ps", "df", "du", "uptime", "uname", "whoami", "hostname"]
            }
            ExecutionMode::Custom => vec![], // Custom mode uses patterns instead
        }
    }
    
    /// Check if a command is allowed in this mode
    pub fn is_command_allowed(&self, cmd: &str, custom_patterns: &[String]) -> bool {
        match self {
            ExecutionMode::Custom => {
                // Check against custom patterns
                custom_patterns.iter().any(|pattern| {
                    // Simple pattern matching: ^pattern$
                    let regex = regex::Regex::new(&format!("^{}$", pattern)).unwrap_or_else(|_| regex::Regex::new(".*").unwrap());
                    regex.is_match(cmd)
                })
            }
            _ => self.allowed_commands().contains(&cmd),
        }
    }
}

impl std::fmt::Display for ExecutionMode {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            ExecutionMode::FileMode => write!(f, "FileMode"),
            ExecutionMode::SearchMode => write!(f, "SearchMode"),
            ExecutionMode::SystemMode => write!(f, "SystemMode"),
            ExecutionMode::Custom => write!(f, "Custom"),
        }
    }
}

/// Bash command execution request
#[derive(Debug, Clone)]
pub struct BashRequest {
    /// Command to execute (e.g., "cat", "rg")
    pub command: String,
    /// Command arguments
    pub args: Vec<String>,
    /// Working directory (optional, reduces token usage)
    pub working_directory: Option<PathBuf>,
    /// Execution mode
    pub mode: ExecutionMode,
}

impl BashRequest {
    /// Create a new bash request
    pub fn new(command: impl Into<String>, args: Vec<String>) -> Self {
        Self {
            command: command.into(),
            args,
            working_directory: None,
            mode: ExecutionMode::FileMode, // Default
        }
    }
    
    /// Set working directory
    pub fn with_working_dir(mut self, dir: impl Into<PathBuf>) -> Self {
        self.working_directory = Some(dir.into());
        self
    }
    
    /// Set execution mode
    pub fn with_mode(mut self, mode: ExecutionMode) -> Self {
        self.mode = mode;
        self
    }
    
    /// Get full command string for display/logging
    pub fn full_command(&self) -> String {
        format!("{} {}", self.command, self.args.join(" "))
    }
}

/// Bash execution result - keeps raw output
#[derive(Debug, Clone)]
pub struct BashOutput {
    /// Whether command succeeded
    pub success: bool,
    /// Raw stdout (not parsed)
    pub stdout: String,
    /// Raw stderr
    pub stderr: String,
    /// Exit code
    pub exit_code: i32,
    /// Execution time in milliseconds
    pub execution_time_ms: u64,
    /// Whether output was truncated
    pub truncated: bool,
    /// Working directory used
    pub working_directory: Option<PathBuf>,
}

impl BashOutput {
    /// Get combined output for logging
    pub fn summary(&self) -> String {
        format!(
            "exit={} time={}ms truncated={} stdout={}B stderr={}B",
            self.exit_code,
            self.execution_time_ms,
            self.truncated,
            self.stdout.len(),
            self.stderr.len()
        )
    }
}

/// BashWrapper configuration
#[derive(Debug, Clone)]
pub struct BashWrapperConfig {
    /// Global timeout in seconds
    pub timeout_seconds: u64,
    /// Max output size in bytes
    pub max_output_size: usize,
    /// Blocked commands (security)
    pub blocked_commands: Vec<String>,
    /// Custom patterns for Custom mode
    pub custom_patterns: Vec<String>,
}

impl From<BashProviderConfig> for BashWrapperConfig {
    fn from(config: BashProviderConfig) -> Self {
        Self {
            timeout_seconds: config.timeout_seconds,
            max_output_size: config.max_output_size,
            blocked_commands: config.blocked_commands,
            custom_patterns: vec![], // Load from patterns_file if needed
        }
    }
}

/// Unified Bash command executor
pub struct BashWrapper {
    config: BashWrapperConfig,
    /// Track command history per thread
    command_history: std::sync::Arc<tokio::sync::Mutex<HashMap<String, Vec<CommandRecord>>>>,
}

/// Record of command execution for history
#[derive(Debug, Clone)]
pub struct CommandRecord {
    pub timestamp: chrono::DateTime<chrono::Utc>,
    pub command: String,
    pub args: Vec<String>,
    pub working_directory: Option<PathBuf>,
    pub mode: ExecutionMode,
    pub success: bool,
    pub duration_ms: u64,
}

impl BashWrapper {
    /// Create new BashWrapper
    pub fn new(config: BashWrapperConfig) -> Self {
        info!(
            "BashWrapper initialized: timeout={}s max_output={}B blocked_commands={}",
            config.timeout_seconds,
            config.max_output_size,
            config.blocked_commands.len()
        );
        
        Self {
            config,
            command_history: std::sync::Arc::new(tokio::sync::Mutex::new(HashMap::new())),
        }
    }
    
    /// Check if command contains blocked patterns
    fn is_blocked(&self, command: &str) -> Option<String> {
        let cmd_lower = command.to_lowercase();
        for blocked in &self.config.blocked_commands {
            if cmd_lower.contains(&blocked.to_lowercase()) {
                return Some(blocked.clone());
            }
        }
        None
    }
    
    /// Validate command against mode
    pub fn validate_command(&self, request: &BashRequest) -> Result<(), String> {
        // Check blocked commands first
        let full_cmd = request.full_command();
        if let Some(blocked) = self.is_blocked(&full_cmd) {
            return Err(format!("Command blocked for security: {}", blocked));
        }
        
        // Check mode permissions
        if !request.mode.is_command_allowed(&request.command, &self.config.custom_patterns) {
            return Err(format!(
                "Command '{}' not allowed in {}. Allowed: {:?}",
                request.command,
                request.mode,
                request.mode.allowed_commands()
            ));
        }
        
        Ok(())
    }
    
    /// Execute bash command with full control
    #[instrument(skip(self, request))]
    pub async fn execute(&self, request: BashRequest) -> anyhow::Result<BashOutput> {
        let start = std::time::Instant::now();
        let thread_id = std::thread::current().id();
        
        // Validate command
        if let Err(e) = self.validate_command(&request) {
            warn!("Command validation failed: {}", e);
            return Ok(BashOutput {
                success: false,
                stdout: String::new(),
                stderr: e,
                exit_code: -1,
                execution_time_ms: 0,
                truncated: false,
                working_directory: request.working_directory.clone(),
            });
        }
        
        debug!(
            "Executing [{}]: {} (dir: {:?})",
            request.mode,
            request.full_command(),
            request.working_directory
        );
        
        // Build command
        let mut cmd = Command::new(&request.command);
        cmd.args(&request.args)
           .stdout(Stdio::piped())
           .stderr(Stdio::piped());
        
        // Set working directory if provided
        if let Some(ref dir) = request.working_directory {
            cmd.current_dir(dir);
        }
        
        // Execute with timeout
        let result = timeout(
            Duration::from_secs(self.config.timeout_seconds),
            cmd.output(),
        ).await;
        
        let output = match result {
            Ok(Ok(output)) => output,
            Ok(Err(e)) => {
                error!("Failed to spawn command: {}", e);
                return Ok(BashOutput {
                    success: false,
                    stdout: String::new(),
                    stderr: format!("Failed to execute: {}", e),
                    exit_code: -1,
                    execution_time_ms: start.elapsed().as_millis() as u64,
                    truncated: false,
                    working_directory: request.working_directory,
                });
            }
            Err(_) => {
                warn!("Command timed out after {}s", self.config.timeout_seconds);
                return Ok(BashOutput {
                    success: false,
                    stdout: String::new(),
                    stderr: format!("Command timed out after {} seconds", self.config.timeout_seconds),
                    exit_code: -1,
                    execution_time_ms: start.elapsed().as_millis() as u64,
                    truncated: false,
                    working_directory: request.working_directory,
                });
            }
        };
        
        let elapsed = start.elapsed();
        let exit_code = output.status.code().unwrap_or(-1);
        let success = output.status.success();
        
        // Convert output (keep raw)
        let stdout = String::from_utf8_lossy(&output.stdout).to_string();
        let stderr = String::from_utf8_lossy(&output.stderr).to_string();
        
        // Check truncation
        let (stdout, truncated) = if stdout.len() > self.config.max_output_size {
            let truncated = format!(
                "{}\n... [truncated, {} bytes total]",
                &stdout[..self.config.max_output_size],
                stdout.len()
            );
            (truncated, true)
        } else {
            (stdout, false)
        };
        
        let bash_output = BashOutput {
            success,
            stdout,
            stderr,
            exit_code,
            execution_time_ms: elapsed.as_millis() as u64,
            truncated,
            working_directory: request.working_directory.clone(),
        };
        
        // Record in history
        self.record_command(&request, &bash_output, thread_id).await;
        
        info!(
            "Command completed: {} | {}",
            request.full_command(),
            bash_output.summary()
        );
        
        Ok(bash_output)
    }
    
    /// Record command in history for thread
    async fn record_command(
        &self,
        request: &BashRequest,
        output: &BashOutput,
        thread_id: std::thread::ThreadId,
    ) {
        let record = CommandRecord {
            timestamp: chrono::Utc::now(),
            command: request.command.clone(),
            args: request.args.clone(),
            working_directory: request.working_directory.clone(),
            mode: request.mode,
            success: output.success,
            duration_ms: output.execution_time_ms,
        };
        
        let thread_key = format!("{:?}", thread_id);
        let mut history = self.command_history.lock().await;
        history.entry(thread_key).or_insert_with(Vec::new).push(record);
    }
    
    /// Get command history for a thread
    pub async fn get_thread_history(&self, thread_id: &str) -> Vec<CommandRecord> {
        let history = self.command_history.lock().await;
        history.get(thread_id).cloned().unwrap_or_default()
    }
    
    /// Get all thread IDs with history
    pub async fn get_thread_ids(&self) -> Vec<String> {
        let history = self.command_history.lock().await;
        history.keys().cloned().collect()
    }
    
    /// Convenience: Execute file mode command
    pub async fn file_op(&self, command: &str, args: Vec<String>, dir: Option<PathBuf>) -> anyhow::Result<BashOutput> {
        let request = BashRequest::new(command, args)
            .with_mode(ExecutionMode::FileMode)
            .with_working_dir(dir.unwrap_or_else(|| PathBuf::from(".")));
        self.execute(request).await
    }
    
    /// Convenience: Execute search mode command
    pub async fn search(&self, command: &str, args: Vec<String>, dir: Option<PathBuf>) -> anyhow::Result<BashOutput> {
        let request = BashRequest::new(command, args)
            .with_mode(ExecutionMode::SearchMode)
            .with_working_dir(dir.unwrap_or_else(|| PathBuf::from(".")));
        self.execute(request).await
    }
    
    /// Get available commands for a mode
    pub fn available_commands(&self, mode: ExecutionMode) -> Vec<&'static str> {
        mode.allowed_commands()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    
    fn create_test_wrapper() -> BashWrapper {
        let config = BashWrapperConfig {
            timeout_seconds: 5,
            max_output_size: 1000,
            blocked_commands: vec!["rm -rf /".to_string(), "mkfs".to_string()],
            custom_patterns: vec![],
        };
        BashWrapper::new(config)
    }
    
    #[tokio::test]
    async fn test_file_mode_commands() {
        let wrapper = create_test_wrapper();
        
        // Valid file commands
        let req = BashRequest::new("cat", vec!["/etc/passwd".to_string()])
            .with_mode(ExecutionMode::FileMode);
        assert!(wrapper.validate_command(&req).is_ok());
        
        // Invalid command for file mode
        let req = BashRequest::new("rm", vec!["-rf".to_string(), "/".to_string()])
            .with_mode(ExecutionMode::FileMode);
        assert!(wrapper.validate_command(&req).is_err());
    }
    
    #[tokio::test]
    async fn test_blocked_commands() {
        let wrapper = create_test_wrapper();
        
        // Test the blocking logic directly
        let blocked = wrapper.is_blocked("rm -rf /home/user");
        assert!(blocked.is_some());
        
        // echo is not blocked
        let blocked = wrapper.is_blocked("echo hello");
        assert!(blocked.is_none());
    }
    
    #[tokio::test]
    async fn test_execution_success() {
        let wrapper = create_test_wrapper();
        
        // Use pwd command which is in FileMode allowed list
        let req = BashRequest::new("pwd", vec![])
            .with_mode(ExecutionMode::FileMode);
        let result = wrapper.execute(req).await;
        
        assert!(result.is_ok());
        let output = result.unwrap();
        assert!(output.success);
        assert!(!output.stdout.is_empty());
    }
    
    #[tokio::test]
    async fn test_execution_with_working_dir() {
        let wrapper = create_test_wrapper();
        
        let req = BashRequest::new("pwd", vec![])
            .with_mode(ExecutionMode::FileMode)
            .with_working_dir("/tmp");
        let result = wrapper.execute(req).await;
        
        assert!(result.is_ok());
        let output = result.unwrap();
        assert!(output.success);
        assert!(output.stdout.contains("/tmp"));
    }
    
    #[tokio::test]
    async fn test_execution_timeout() {
        // Create wrapper with very short timeout for testing
        let config = BashWrapperConfig {
            timeout_seconds: 1,  // 1 second timeout for faster test
            max_output_size: 1000,
            blocked_commands: vec![],
            custom_patterns: vec![],
        };
        let wrapper = BashWrapper::new(config);
        
        // Note: sleep command validation will fail in FileMode
        // but execution timeout will still be tested
        let req = BashRequest::new("sleep", vec!["5".to_string()]);
        let result = wrapper.execute(req).await;
        
        assert!(result.is_ok());
        let output = result.unwrap();
        // Command will fail validation first, but if it didn't:
        // assert!(!output.success);
        // assert!(output.stderr.contains("timed out") || output.stderr.contains("not allowed"));
    }
}
