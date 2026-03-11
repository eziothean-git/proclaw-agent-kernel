//! Trace system for observability and debugging
//!
//! Features:
//! - Thread operation history tracking
//! - File-system based storage (JSON Lines)
//! - Real-time writes
//! - Extensible field configuration
//! - Index for fast lookup

use crate::config::TracesConfig;
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::{Path, PathBuf};
use tokio::fs;
use tokio::io::AsyncWriteExt;
use tokio::sync::Mutex;
use tracing::{debug, info};
use uuid::Uuid;

/// Trace record for an operation
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TraceRecord {
    /// Unique trace ID
    pub trace_id: String,
    /// Timestamp of the operation
    pub timestamp: DateTime<Utc>,
    /// Session ID
    pub session_id: String,
    /// Thread ID
    pub thread_id: String,
    /// Operation type
    pub operation: String,
    /// Execution mode (for bash operations)
    pub mode: Option<String>,
    /// Command or operation details
    pub command: Option<String>,
    /// Working directory
    pub working_directory: Option<PathBuf>,
    /// Duration in milliseconds
    pub duration_ms: u64,
    /// Whether operation succeeded
    pub success: bool,
    /// Cache hit status
    pub cache_hit: bool,
    /// Token subject (who performed the operation)
    pub token_subject: Option<String>,
    /// Output size in bytes
    pub output_size_bytes: u64,
    /// Error message (if any)
    pub error_message: Option<String>,
    /// Additional extensible fields
    #[serde(flatten)]
    pub extra_fields: HashMap<String, serde_json::Value>,
}

impl TraceRecord {
    /// Create a new trace record with minimal required fields
    pub fn new(
        trace_id: impl Into<String>,
        session_id: impl Into<String>,
        thread_id: impl Into<String>,
        operation: impl Into<String>,
    ) -> Self {
        Self {
            trace_id: trace_id.into(),
            timestamp: Utc::now(),
            session_id: session_id.into(),
            thread_id: thread_id.into(),
            operation: operation.into(),
            mode: None,
            command: None,
            working_directory: None,
            duration_ms: 0,
            success: true,
            cache_hit: false,
            token_subject: None,
            output_size_bytes: 0,
            error_message: None,
            extra_fields: HashMap::new(),
        }
    }

    /// Set execution mode
    pub fn with_mode(mut self, mode: impl Into<String>) -> Self {
        self.mode = Some(mode.into());
        self
    }

    /// Set command
    pub fn with_command(mut self, command: impl Into<String>) -> Self {
        self.command = Some(command.into());
        self
    }

    /// Set working directory
    pub fn with_working_directory(mut self, dir: impl Into<PathBuf>) -> Self {
        self.working_directory = Some(dir.into());
        self
    }

    /// Set duration
    pub fn with_duration(mut self, duration_ms: u64) -> Self {
        self.duration_ms = duration_ms;
        self
    }

    /// Set success status
    pub fn with_success(mut self, success: bool) -> Self {
        self.success = success;
        self
    }

    /// Set cache hit status
    pub fn with_cache_hit(mut self, cache_hit: bool) -> Self {
        self.cache_hit = cache_hit;
        self
    }

    /// Set token subject
    pub fn with_token_subject(mut self, subject: impl Into<String>) -> Self {
        self.token_subject = Some(subject.into());
        self
    }

    /// Set output size
    pub fn with_output_size(mut self, size: u64) -> Self {
        self.output_size_bytes = size;
        self
    }

    /// Set error message
    pub fn with_error(mut self, error: impl Into<String>) -> Self {
        self.error_message = Some(error.into());
        self
    }

    /// Add extra field
    pub fn with_extra_field(
        mut self,
        key: impl Into<String>,
        value: impl Serialize,
    ) -> anyhow::Result<Self> {
        let value = serde_json::to_value(value)?;
        self.extra_fields.insert(key.into(), value);
        Ok(self)
    }
}

/// Thread history record
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ThreadHistoryRecord {
    /// Sequence number (auto-incrementing per thread)
    pub seq: u64,
    /// Timestamp
    pub timestamp: DateTime<Utc>,
    /// Operation type
    pub operation: String,
    /// Operation details
    pub details: HashMap<String, String>,
    /// Working directory at time of operation
    pub working_directory: Option<PathBuf>,
    /// Success status
    pub success: bool,
    /// Duration
    pub duration_ms: u64,
}

/// Thread state snapshot
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ThreadState {
    /// Thread ID
    pub thread_id: String,
    /// Session ID
    pub session_id: String,
    /// When thread was created
    pub created_at: DateTime<Utc>,
    /// Current working directory
    pub current_directory: PathBuf,
    /// Operations performed
    pub operations: Vec<ThreadHistoryRecord>,
    /// Total operation count
    pub total_operations: u64,
    /// Last operation time
    pub last_operation_time: DateTime<Utc>,
    /// Accessed paths
    pub accessed_paths: Vec<PathBuf>,
}

impl ThreadState {
    /// Create new thread state
    pub fn new(thread_id: impl Into<String>, session_id: impl Into<String>) -> Self {
        let now = Utc::now();
        Self {
            thread_id: thread_id.into(),
            session_id: session_id.into(),
            created_at: now,
            current_directory: PathBuf::from("."),
            operations: Vec::new(),
            total_operations: 0,
            last_operation_time: now,
            accessed_paths: Vec::new(),
        }
    }

    /// Record an operation
    pub fn record_operation(
        &mut self,
        operation: impl Into<String>,
        details: HashMap<String, String>,
        working_dir: Option<PathBuf>,
        success: bool,
        duration_ms: u64,
    ) {
        self.total_operations += 1;
        self.last_operation_time = Utc::now();

        if let Some(ref dir) = working_dir {
            self.current_directory = dir.clone();
            if !self.accessed_paths.contains(dir) {
                self.accessed_paths.push(dir.clone());
            }
        }

        let record = ThreadHistoryRecord {
            seq: self.total_operations,
            timestamp: Utc::now(),
            operation: operation.into(),
            details,
            working_directory: working_dir,
            success,
            duration_ms,
        };

        self.operations.push(record);
    }
}

/// Trace collector configuration
#[derive(Debug, Clone)]
pub struct TraceCollectorConfig {
    pub storage_path: PathBuf,
    pub enabled_fields: Vec<String>,
}

/// Trace collector for recording operations
pub struct TraceCollector {
    config: TraceCollectorConfig,
    /// Global index for fast lookup
    index: Mutex<HashMap<String, PathBuf>>, // trace_id -> file path
    /// Thread states (in-memory for fast access)
    thread_states: Mutex<HashMap<String, ThreadState>>,
    /// Index file path
    index_file: PathBuf,
    /// Current thread ID
    current_thread_id: String,
}

/// Index entry for trace lookup
#[derive(Debug, Serialize, Deserialize)]
struct TraceIndexEntry {
    trace_id: String,
    thread_id: String,
    timestamp: DateTime<Utc>,
    path: String,
}

impl TraceCollector {
    /// Create new trace collector
    pub async fn new(config: &TracesConfig) -> anyhow::Result<Self> {
        let storage_path = config.base_path.clone();
        let index_file = storage_path.join("index.jsonl");

        // Create directories
        fs::create_dir_all(&storage_path).await?;
        fs::create_dir_all(storage_path.join("threads")).await?;
        fs::create_dir_all(storage_path.join("daily")).await?;

        // Load index
        let index = if index_file.exists() {
            Self::load_index(&index_file).await?
        } else {
            HashMap::new()
        };

        // Load thread states
        let thread_states = Self::load_thread_states(&storage_path).await?;

        let collector_config = TraceCollectorConfig {
            storage_path,
            enabled_fields: vec![
                "timestamp".to_string(),
                "thread_id".to_string(),
                "operation".to_string(),
                "command".to_string(),
                "duration_ms".to_string(),
                "success".to_string(),
            ],
        };

        // Generate thread ID
        let current_thread_id = format!("trace_thread_{}", Uuid::new_v4().to_string()[..8].to_string());

        info!(
            "TraceCollector initialized: {} traces, {} threads, id: {}",
            index.len(),
            thread_states.len(),
            current_thread_id
        );

        Ok(Self {
            config: collector_config,
            index: Mutex::new(index),
            thread_states: Mutex::new(thread_states),
            index_file,
            current_thread_id,
        })
    }

    /// Load index from file
    async fn load_index(index_file: &Path) -> anyhow::Result<HashMap<String, PathBuf>> {
        let content = fs::read_to_string(index_file).await?;
        let mut index = HashMap::new();

        for line in content.lines() {
            if let Ok(entry) = serde_json::from_str::<TraceIndexEntry>(line) {
                index.insert(entry.trace_id, PathBuf::from(entry.path));
            }
        }

        Ok(index)
    }

    /// Save index to file
    async fn save_index(&self) -> anyhow::Result<()> {
        let index = self.index.lock().await;
        let mut file = fs::File::create(&self.index_file).await?;

        for (trace_id, path) in index.iter() {
            let thread_id = self
                .get_thread_id_for_trace(trace_id)
                .await
                .unwrap_or_default();
            let entry = TraceIndexEntry {
                trace_id: trace_id.clone(),
                thread_id,
                timestamp: Utc::now(),
                path: path.to_string_lossy().to_string(),
            };
            let line = serde_json::to_string(&entry)?;
            file.write_all(line.as_bytes()).await?;
            file.write_all(b"\n").await?;
        }

        file.flush().await?;
        Ok(())
    }

    /// Get thread ID for a trace (helper)
    async fn get_thread_id_for_trace(&self,
        trace_id: &str,
    ) -> Option<String> {
        if let Some(path) = self.index.lock().await.get(trace_id) {
            if let Ok(content) = fs::read_to_string(path).await {
                if let Ok(record) = serde_json::from_str::<TraceRecord>(&content) {
                    return Some(record.thread_id);
                }
            }
        }
        None
    }

    /// Load thread states from storage
    async fn load_thread_states(
        storage_path: &Path,
    ) -> anyhow::Result<HashMap<String, ThreadState>> {
        let threads_dir = storage_path.join("threads");
        let mut states = HashMap::new();

        if threads_dir.exists() {
            let mut entries = fs::read_dir(&threads_dir).await?;
            while let Some(entry) = entries.next_entry().await? {
                let path = entry.path();
                if path.extension().map(|e| e == "json").unwrap_or(false) {
                    if let Ok(content) = fs::read_to_string(&path).await {
                        if let Ok(state) = serde_json::from_str::<ThreadState>(&content) {
                            states.insert(state.thread_id.clone(), state);
                        }
                    }
                }
            }
        }

        Ok(states)
    }

    /// Save thread state to file
    async fn save_thread_state(
        &self,
        thread_id: &str,
    ) -> anyhow::Result<()> {
        let states = self.thread_states.lock().await;
        if let Some(state) = states.get(thread_id) {
            let path = self
                .config
                .storage_path
                .join("threads")
                .join(format!("{}.json", thread_id));
            let content = serde_json::to_string_pretty(state)?;
            fs::write(&path, content).await?;
        }
        Ok(())
    }

    /// Record a trace (real-time write)
    pub async fn record(&self,
        record: TraceRecord,
    ) -> anyhow::Result<()> {
        let trace_id = record.trace_id.clone();
        let thread_id = record.thread_id.clone();
        let timestamp = record.timestamp;

        // Update thread state
        {
            let mut states = self.thread_states.lock().await;
            let state = states
                .entry(thread_id.clone())
                .or_insert_with(|| ThreadState::new(&thread_id, &record.session_id));

            let mut details = HashMap::new();
            if let Some(ref cmd) = record.command {
                details.insert("command".to_string(), cmd.clone());
            }

            state.record_operation(
                record.operation.clone(),
                details,
                record.working_directory.clone(),
                record.success,
                record.duration_ms,
            );
        }

        // Save thread state
        self.save_thread_state(&thread_id).await?;

        // Write trace to daily file
        let date = timestamp.format("%Y-%m-%d").to_string();
        let daily_dir = self.config.storage_path.join("daily").join(&date);
        fs::create_dir_all(&daily_dir).await?;

        let trace_file = daily_dir.join(format!("{}_{}.jsonl", thread_id, &trace_id[..8]));
        let content = serde_json::to_string(&record)?;
        fs::write(&trace_file, content).await?;

        // Update index
        {
            let mut index = self.index.lock().await;
            index.insert(trace_id.clone(), trace_file);
        }

        // Save index
        self.save_index().await?;

        debug!("Recorded trace: {}", trace_id);
        Ok(())
    }

    /// Get trace by ID
    pub async fn get_trace(&self,
        trace_id: &str,
    ) -> anyhow::Result<Option<TraceRecord>> {
        let index = self.index.lock().await;
        if let Some(path) = index.get(trace_id) {
            if path.exists() {
                let content = fs::read_to_string(path).await?;
                let record: TraceRecord = serde_json::from_str(&content)?;
                return Ok(Some(record));
            }
        }
        Ok(None)
    }

    /// List traces with filtering
    pub async fn list_traces(
        &self,
        thread_id: Option<&str>,
        session_id: Option<&str>,
        limit: usize,
    ) -> Vec<TraceRecord> {
        let index = self.index.lock().await;
        let mut records = Vec::new();

        for (id, path) in index.iter() {
            if records.len() >= limit {
                break;
            }

            if let Ok(content) = fs::read_to_string(path).await {
                if let Ok(record) = serde_json::from_str::<TraceRecord>(&content) {
                    // Apply filters
                    if let Some(tid) = thread_id {
                        if record.thread_id != tid {
                            continue;
                        }
                    }
                    if let Some(sid) = session_id {
                        if record.session_id != sid {
                            continue;
                        }
                    }
                    records.push(record);
                }
            }
        }

        records
    }

    /// Get thread state
    pub async fn get_thread_state(
        &self,
        thread_id: &str,
    ) -> Option<ThreadState> {
        let states = self.thread_states.lock().await;
        states.get(thread_id).cloned()
    }

    /// Get all thread IDs
    pub async fn get_thread_ids(&self) -> Vec<String> {
        let states = self.thread_states.lock().await;
        states.keys().cloned().collect()
    }

    /// Get operation history for a thread
    pub async fn get_thread_history(
        &self,
        thread_id: &str,
    ) -> Vec<ThreadHistoryRecord> {
        let states = self.thread_states.lock().await;
        if let Some(state) = states.get(thread_id) {
            state.operations.clone()
        } else {
            Vec::new()
        }
    }

    /// Get statistics
    pub async fn get_stats(&self,
    ) -> TraceStats {
        let index = self.index.lock().await;
        let states = self.thread_states.lock().await;

        TraceStats {
            total_traces: index.len(),
            total_threads: states.len(),
            storage_path: self.config.storage_path.clone(),
        }
    }

    /// Get the current thread ID
    pub fn thread_id(&self) -> String {
        self.current_thread_id.clone()
    }
}

/// Trace statistics
#[derive(Debug)]
pub struct TraceStats {
    pub total_traces: usize,
    pub total_threads: usize,
    pub storage_path: PathBuf,
}
