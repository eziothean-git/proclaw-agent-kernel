//! Process 管理模块
//! 
//! Process 是 Thread 的容器，包含：
//! - Process 元信息
//! - 所有 Thread 的全量历史快照
//! - 提供快速查找和管理功能
//! 
//! 持久化结构：
//! /data/processes/{process_id}/
//!   ├── meta.json          # Process 元信息
//!   ├── threads/           # 所有 Thread 的索引
//!   │   ├── {thread_id}.json
//!   │   └── ...
//!   └── snapshots/         # Process 级别快照（可选）

use std::collections::HashMap;
use std::path::{Path, PathBuf};
use tokio::fs;
use tokio::io::AsyncWriteExt;
use chrono::{DateTime, Utc};
use tracing::{debug, info, warn};

use crate::agent_thread::{
    models::{ThreadId, ThreadMeta, ThreadStatus, SessionId, ImmutableInput},
    storage::ThreadStorage,
};

/// Process ID
#[derive(Debug, Clone, PartialEq, Eq, Hash, serde::Serialize, serde::Deserialize)]
pub struct ProcessId(pub String);

impl ProcessId {
    pub fn new() -> Self {
        Self(uuid::Uuid::new_v4().to_string())
    }
}

impl Default for ProcessId {
    fn default() -> Self {
        Self::new()
    }
}

/// Process 元信息
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct ProcessMeta {
    pub process_id: ProcessId,
    pub session_id: SessionId,
    pub process_goal: String,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
    pub thread_count: usize,
    pub status: ProcessStatus,
    pub tags: Vec<String>,
    pub metadata: HashMap<String, serde_json::Value>,
}

/// Process 状态
#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Serialize, serde::Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ProcessStatus {
    Created,      // 已创建
    Active,       // 有活跃 Thread
    Paused,       // 所有 Thread 暂停
    Completed,    // 所有 Thread 完成
    Error,        // 出错
}

/// Thread 摘要信息（用于快速查找，不包含完整历史）
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
pub struct ThreadSummary {
    pub thread_id: ThreadId,
    pub created_at: DateTime<Utc>,
    pub status: ThreadStatus,
    pub current_phase: String,
    pub step_count: usize,
    pub task_goal: String,
}

/// Process - Thread 容器
pub struct Process {
    process_id: ProcessId,
    base_path: PathBuf,
    meta: ProcessMeta,
    thread_summaries: HashMap<String, ThreadSummary>,
}

/// Process 存储路径
const PROCESSES_DIR: &str = "processes";
const META_FILE: &str = "meta.json";
const THREADS_DIR: &str = "threads";
const SNAPSHOTS_DIR: &str = "snapshots";

impl Process {
    /// 创建新的 Process
    pub async fn create(
        base_path: impl AsRef<Path>,
        session_id: SessionId,
        process_goal: impl Into<String>,
        tags: Vec<String>,
    ) -> anyhow::Result<Self> {
        let base_path = base_path.as_ref().to_path_buf();
        let process_id = ProcessId::new();
        let process_path = Self::process_path(&base_path, &process_id);
        
        // 创建目录结构
        fs::create_dir_all(&process_path).await?;
        fs::create_dir_all(process_path.join(THREADS_DIR)).await?;
        fs::create_dir_all(process_path.join(SNAPSHOTS_DIR)).await?;
        
        // 创建 meta.json
        let meta = ProcessMeta {
            process_id: process_id.clone(),
            session_id,
            process_goal: process_goal.into(),
            created_at: Utc::now(),
            updated_at: Utc::now(),
            thread_count: 0,
            status: ProcessStatus::Created,
            tags,
            metadata: HashMap::new(),
        };
        
        let meta_json = serde_json::to_string_pretty(&meta)?;
        fs::write(process_path.join(META_FILE), meta_json).await?;
        
        info!(
            process_id = %process_id.0,
            path = %process_path.display(),
            "Created new process"
        );
        
        Ok(Self {
            process_id,
            base_path,
            meta,
            thread_summaries: HashMap::new(),
        })
    }
    
    /// 加载现有 Process
    pub async fn load(
        base_path: impl AsRef<Path>,
        process_id: &ProcessId,
    ) -> anyhow::Result<Self> {
        let base_path = base_path.as_ref().to_path_buf();
        let process_path = Self::process_path(&base_path, process_id);
        
        if !process_path.exists() {
            return Err(anyhow::anyhow!("Process not found: {}", process_id.0));
        }
        
        // 加载 meta
        let meta_json = fs::read_to_string(process_path.join(META_FILE)).await?;
        let meta: ProcessMeta = serde_json::from_str(&meta_json)?;
        
        // 加载 Thread 摘要
        let mut thread_summaries = HashMap::new();
        let threads_dir = process_path.join(THREADS_DIR);
        
        if threads_dir.exists() {
            let mut entries = fs::read_dir(&threads_dir).await?;
            while let Some(entry) = entries.next_entry().await? {
                let path = entry.path();
                if path.extension().map_or(false, |e| e == "json") {
                    if let Ok(content) = fs::read_to_string(&path).await {
                        if let Ok(summary) = serde_json::from_str::<ThreadSummary>(&content) {
                            thread_summaries.insert(summary.thread_id.0.clone(), summary);
                        }
                    }
                }
            }
        }
        
        debug!(
            process_id = %process_id.0,
            thread_count = thread_summaries.len(),
            "Loaded process"
        );
        
        Ok(Self {
            process_id: process_id.clone(),
            base_path,
            meta,
            thread_summaries,
        })
    }
    
    /// 添加 Thread 到 Process
    pub async fn add_thread(
        &mut self,
        thread_storage: &ThreadStorage,
    ) -> anyhow::Result<()> {
        // 读取 Thread 元信息
        let thread_meta = thread_storage.read_meta().await?;
        let immutable_input = thread_storage.read_immutable_input().await?;
        
        // 创建 Thread 摘要
        let summary = ThreadSummary {
            thread_id: thread_storage.thread_id().clone(),
            created_at: thread_meta.created_at,
            status: thread_meta.status,
            current_phase: format!("{:?}", thread_meta.current_phase),
            step_count: thread_meta.step_count,
            task_goal: immutable_input.task_goal.clone(),
        };
        
        // 保存摘要
        let summary_path = self.threads_dir().join(format!("{}.json", summary.thread_id.0));
        let summary_json = serde_json::to_string_pretty(&summary)?;
        fs::write(&summary_path, summary_json).await?;
        
        // 更新内存索引
        self.thread_summaries.insert(summary.thread_id.0.clone(), summary);
        
        // 更新 Process meta
        self.meta.thread_count = self.thread_summaries.len();
        self.meta.updated_at = Utc::now();
        self.save_meta().await?;
        
        info!(
            process_id = %self.process_id.0,
            thread_id = %thread_storage.thread_id().0,
            "Added thread to process"
        );
        
        Ok(())
    }
    
    /// 更新 Thread 状态
    pub async fn update_thread_status(
        &mut self,
        thread_id: &ThreadId,
        thread_storage: &ThreadStorage,
    ) -> anyhow::Result<()> {
        let thread_id_str = thread_id.0.clone();
        
        // 先读取元数据
        let meta = thread_storage.read_meta().await?;
        let summary_path = self.threads_dir().join(format!("{}.json", thread_id_str));
        
        if let Some(summary) = self.thread_summaries.get_mut(&thread_id_str) {
            summary.status = meta.status;
            summary.current_phase = format!("{:?}", meta.current_phase);
            summary.step_count = meta.step_count;
            
            // 保存更新后的摘要
            let summary_json = serde_json::to_string_pretty(&summary)?;
            fs::write(&summary_path, summary_json).await?;
            
            // 更新 Process 状态
            self.update_process_status().await?;
        }
        
        Ok(())
    }
    
    /// 获取 Process 中的所有 Thread
    pub fn list_threads(&self,
    ) -> Vec<&ThreadSummary> {
        self.thread_summaries.values().collect()
    }
    
    /// 根据状态过滤 Thread
    pub fn list_threads_by_status(
        &self,
        status: ThreadStatus,
    ) -> Vec<&ThreadSummary> {
        self.thread_summaries.values()
            .filter(|s| s.status == status)
            .collect()
    }
    
    /// 获取活跃的 Thread（有 Executor 在运行）
    pub fn get_active_threads(&self,
    ) -> Vec<&ThreadSummary> {
        self.thread_summaries.values()
            .filter(|s| s.status == ThreadStatus::Active)
            .collect()
    }
    
    /// 检查 Process 是否有活跃 Thread
    pub fn has_active_threads(&self,
    ) -> bool {
        self.thread_summaries.values()
            .any(|s| s.status == ThreadStatus::Active)
    }
    
    /// 获取 Process 路径
    fn process_path(base: &Path, process_id: &ProcessId) -> PathBuf {
        base.join(PROCESSES_DIR).join(&process_id.0)
    }
    
    fn threads_dir(&self,
    ) -> PathBuf {
        Self::process_path(&self.base_path, &self.process_id).join(THREADS_DIR)
    }
    
    /// 保存 meta
    async fn save_meta(&self,
    ) -> anyhow::Result<()> {
        let meta_path = Self::process_path(&self.base_path, &self.process_id).join(META_FILE);
        let meta_json = serde_json::to_string_pretty(&self.meta)?;
        fs::write(meta_path, meta_json).await?;
        Ok(())
    }
    
    /// 根据 Thread 状态更新 Process 状态
    async fn update_process_status(&mut self,
    ) -> anyhow::Result<()> {
        let has_active = self.has_active_threads();
        let all_completed = self.thread_summaries.values()
            .all(|s| s.status == ThreadStatus::Completed);
        let any_error = self.thread_summaries.values()
            .any(|s| s.status == ThreadStatus::Error);
        
        self.meta.status = if any_error {
            ProcessStatus::Error
        } else if all_completed && !self.thread_summaries.is_empty() {
            ProcessStatus::Completed
        } else if has_active {
            ProcessStatus::Active
        } else {
            ProcessStatus::Paused
        };
        
        self.meta.updated_at = Utc::now();
        self.save_meta().await?;
        
        Ok(())
    }
    
    /// 获取 Process ID
    pub fn process_id(&self) -> &ProcessId {
        &self.process_id
    }
    
    /// 获取 Process Meta
    pub fn meta(&self) -> &ProcessMeta {
        &self.meta
    }
}

/// Process 管理器（用于查找和管理所有 Process）
pub struct ProcessManager {
    base_path: PathBuf,
    processes: HashMap<String, Process>,
}

impl ProcessManager {
    pub async fn new(base_path: impl AsRef<Path>) -> anyhow::Result<Self> {
        let base_path = base_path.as_ref().to_path_buf();
        let processes_path = base_path.join(PROCESSES_DIR);
        
        // 确保目录存在
        fs::create_dir_all(&processes_path).await?;
        
        // 加载所有 Process
        let mut processes = HashMap::new();
        let mut entries = fs::read_dir(&processes_path).await?;
        
        while let Some(entry) = entries.next_entry().await? {
            let path = entry.path();
            if path.is_dir() {
                let process_id = ProcessId(path.file_name()
                    .and_then(|n| n.to_str())
                    .unwrap_or("")
                    .to_string());
                
                if let Ok(process) = Process::load(&base_path, &process_id).await {
                    processes.insert(process_id.0.clone(), process);
                }
            }
        }
        
        info!(process_count = processes.len(), "Loaded process manager");
        
        Ok(Self {
            base_path,
            processes,
        })
    }
    
    /// 创建新 Process
    pub async fn create_process(
        &mut self,
        session_id: SessionId,
        process_goal: impl Into<String>,
        tags: Vec<String>,
    ) -> anyhow::Result<ProcessId> {
        let process = Process::create(
            &self.base_path,
            session_id,
            process_goal,
            tags,
        ).await?;
        
        let process_id = process.process_id().clone();
        self.processes.insert(process_id.0.clone(), process);
        
        Ok(process_id)
    }
    
    /// 获取 Process
    pub fn get_process(&self,
        process_id: &ProcessId,
    ) -> Option<&Process> {
        self.processes.get(&process_id.0)
    }
    
    /// 获取 Process（可变）
    pub fn get_process_mut(
        &mut self,
        process_id: &ProcessId,
    ) -> Option<&mut Process> {
        self.processes.get_mut(&process_id.0)
    }
    
    /// 列出所有 Process
    pub fn list_processes(&self,
    ) -> Vec<&Process> {
        self.processes.values().collect()
    }
    
    /// 根据 Session 列出 Process
    pub fn list_processes_by_session(
        &self,
        session_id: &SessionId,
    ) -> Vec<&Process> {
        self.processes.values()
            .filter(|p| p.meta().session_id.0 == session_id.0)
            .collect()
    }
    
    /// 查找包含指定 Thread 的 Process
    pub fn find_process_by_thread(
        &self,
        thread_id: &ThreadId,
    ) -> Option<&Process> {
        self.processes.values()
            .find(|p| p.thread_summaries.contains_key(&thread_id.0))
    }
}