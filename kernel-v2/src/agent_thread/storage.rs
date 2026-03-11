//! Agent Thread 文件存储实现

use std::collections::HashMap;
use std::path::{Path, PathBuf};
use tokio::fs;
use tokio::io::AsyncWriteExt;
use chrono::Utc;
use tracing::{info, debug, warn};

use super::{
    models::*,
    error::{Result, ThreadError},
};

/// Thread 文件存储路径结构
/// 
/// ```
/// /data/threads/{thread_id}/
/// ├── meta.json              # Thread 元数据
/// ├── immutable_input.json   # 不可变输入
/// ├── event_log.jsonl        # JSON Lines 格式的事件日志
/// ├── artifacts/             # 结构化产物
/// │   ├── module_map.json
/// │   ├── patch_plan.json
/// │   └── ...
/// ├── snapshots/             # 执行快照
/// │   └── {timestamp}.json
/// └── index/                 # 索引（可选）
///     └── event_index.json
/// ```
const THREADS_DIR: &str = "threads";
const META_FILE: &str = "meta.json";
const IMMUTABLE_INPUT_FILE: &str = "immutable_input.json";
const EVENT_LOG_FILE: &str = "event_log.jsonl";
const ARTIFACTS_DIR: &str = "artifacts";
const SNAPSHOTS_DIR: &str = "snapshots";
const INDEX_DIR: &str = "index";

#[derive(Debug)]
pub struct ThreadStorage {
    base_path: PathBuf,
    thread_id: ThreadId,
}

impl ThreadStorage {
    /// 创建新的 Thread 存储
    pub async fn create(
        base_path: impl AsRef<Path>,
        thread_id: ThreadId,
        session_id: SessionId,
        immutable_input: ImmutableInput,
    ) -> Result<Self> {
        let base_path = base_path.as_ref().to_path_buf();
        let thread_path = Self::thread_path_for_id(&base_path, &thread_id);
        
        // 检查是否已存在
        if thread_path.exists() {
            return Err(ThreadError::AlreadyExists(thread_id.0.clone()));
        }
        
        // 创建目录结构
        fs::create_dir_all(&thread_path).await?;
        fs::create_dir_all(thread_path.join(ARTIFACTS_DIR)).await?;
        fs::create_dir_all(thread_path.join(SNAPSHOTS_DIR)).await?;
        fs::create_dir_all(thread_path.join(INDEX_DIR)).await?;
        
        // 创建 meta.json
        let meta = ThreadMeta::new(thread_id.clone(), session_id);
        let meta_json = serde_json::to_string_pretty(&meta)?;
        fs::write(thread_path.join(META_FILE), meta_json).await?;
        
        // 创建 immutable_input.json
        let input_json = serde_json::to_string_pretty(&immutable_input)?;
        fs::write(thread_path.join(IMMUTABLE_INPUT_FILE), input_json).await?;
        
        // 创建空的 event_log.jsonl
        fs::write(thread_path.join(EVENT_LOG_FILE), "").await?;
        
        info!(
            thread_id = %thread_id.0,
            path = %thread_path.display(),
            "Created new thread storage"
        );
        
        Ok(Self {
            base_path,
            thread_id,
        })
    }
    
    /// 加载现有的 Thread 存储
    pub async fn load(
        base_path: impl AsRef<Path>,
        thread_id: &ThreadId,
    ) -> Result<Self> {
        let base_path = base_path.as_ref().to_path_buf();
        let thread_path = Self::thread_path_for_id(&base_path, thread_id);
        
        if !thread_path.exists() {
            return Err(ThreadError::NotFound(thread_id.0.clone()));
        }
        
        debug!(
            thread_id = %thread_id.0,
            path = %thread_path.display(),
            "Loaded thread storage"
        );
        
        Ok(Self {
            base_path,
            thread_id: thread_id.clone(),
        })
    }
    
    /// 检查 Thread 是否存在
    pub async fn exists(
        base_path: impl AsRef<Path>,
        thread_id: &ThreadId,
    ) -> bool {
        let thread_path = Self::thread_path_for_id(base_path.as_ref(), thread_id);
        thread_path.exists()
    }
    
    /// 追加事件到 Event Log（原子写入）
    pub async fn append_event(&self,
        event: &Event,
    ) -> Result<()> {
        let event_log_path = self.event_log_path();
        let line = event.to_json_line()?;
        
        // 原子写入：先写入临时文件，再追加
        let mut file = fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(&event_log_path)
            .await?;
        
        file.write_all(line.as_bytes()).await?;
        file.write_all(b"\n").await?;
        file.sync_all().await?;
        
        debug!(
            thread_id = %self.thread_id.0,
            event_id = %event.event_id,
            event_type = ?event.event_type,
            "Appended event to log"
        );
        
        Ok(())
    }
    
    /// 批量追加事件
    pub async fn append_events(&self,
        events: &[Event],
    ) -> Result<()> {
        let event_log_path = self.event_log_path();
        
        let mut lines = Vec::new();
        for event in events {
            lines.push(event.to_json_line()?);
        }
        
        let content = lines.join("\n");
        let content = format!("{}\n", content);
        
        let mut file = fs::OpenOptions::new()
            .create(true)
            .append(true)
            .open(&event_log_path)
            .await?;
        
        file.write_all(content.as_bytes()).await?;
        file.sync_all().await?;
        
        debug!(
            thread_id = %self.thread_id.0,
            count = events.len(),
            "Appended batch events to log"
        );
        
        Ok(())
    }
    
    /// 读取 Event Log
    pub async fn read_event_log(&self,
    ) -> Result<Vec<Event>> {
        let event_log_path = self.event_log_path();
        
        if !event_log_path.exists() {
            return Ok(Vec::new());
        }
        
        let content = fs::read_to_string(&event_log_path).await?;
        let mut events = Vec::new();
        
        for line in content.lines() {
            if line.trim().is_empty() {
                continue;
            }
            match Event::from_json_line(line) {
                Ok(event) => events.push(event),
                Err(e) => {
                    warn!(
                        thread_id = %self.thread_id.0,
                        error = %e,
                        line = %line,
                        "Failed to parse event line"
                    );
                }
            }
        }
        
        Ok(events)
    }
    
    /// 读取最近 N 条事件
    pub async fn read_recent_events(
&self,
        n: usize,
    ) -> Result<Vec<Event>> {
        let events = self.read_event_log().await?;
        let start = events.len().saturating_sub(n);
        Ok(events[start..].to_vec())
    }
    
    /// 保存 Artifact
    pub async fn save_artifact(
&self,
        artifact: &ArtifactSlot,
    ) -> Result<()> {
        let artifact_path = self.artifact_path(&artifact.artifact_type);
        let content = serde_json::to_string_pretty(artifact)?;
        
        // 原子写入
        let temp_path = format!("{}.tmp", artifact_path.display());
        fs::write(&temp_path, content).await?;
        fs::rename(&temp_path, &artifact_path).await?;
        
        debug!(
            thread_id = %self.thread_id.0,
            slot_id = %artifact.slot_id,
            artifact_type = ?artifact.artifact_type,
            "Saved artifact"
        );
        
        Ok(())
    }
    
    /// 加载 Artifact
    pub async fn load_artifact(
&self,
        artifact_type: &ArtifactType,
    ) -> Result<Option<ArtifactSlot>> {
        let artifact_path = self.artifact_path(artifact_type);
        
        if !artifact_path.exists() {
            return Ok(None);
        }
        
        let content = fs::read_to_string(&artifact_path).await?;
        let artifact: ArtifactSlot = serde_json::from_str(&content)?;
        
        Ok(Some(artifact))
    }
    
    /// 列出所有 Artifacts
    pub async fn list_artifacts(
&self,
    ) -> Result<Vec<ArtifactSlot>> {
        let artifacts_dir = self.artifacts_dir();
        let mut artifacts = Vec::new();
        
        if artifacts_dir.exists() {
            let mut entries = fs::read_dir(&artifacts_dir).await?;
            while let Some(entry) = entries.next_entry().await? {
                let path = entry.path();
                if path.extension().map_or(false, |e| e == "json") {
                    match fs::read_to_string(&path).await {
                        Ok(content) => {
                            match serde_json::from_str::<ArtifactSlot>(&content) {
                                Ok(artifact) => artifacts.push(artifact),
                                Err(e) => warn!("Failed to parse artifact: {}", e),
                            }
                        }
                        Err(e) => warn!("Failed to read artifact: {}", e),
                    }
                }
            }
        }
        
        Ok(artifacts)
    }
    
    /// 读取 Meta
    pub async fn read_meta(
&self,
    ) -> Result<ThreadMeta> {
        let meta_path = self.thread_path().join(META_FILE);
        let content = fs::read_to_string(&meta_path).await?;
        let meta: ThreadMeta = serde_json::from_str(&content)?;
        Ok(meta)
    }
    
    /// 更新 Meta
    pub async fn update_meta(
&self,
        meta: &ThreadMeta,
    ) -> Result<()> {
        let meta_path = self.thread_path().join(META_FILE);
        let content = serde_json::to_string_pretty(meta)?;
        
        // 原子写入
        let temp_path = format!("{}.tmp", meta_path.display());
        fs::write(&temp_path, content).await?;
        fs::rename(&temp_path, &meta_path).await?;
        
        Ok(())
    }
    
    /// 读取 Immutable Input
    pub async fn read_immutable_input(
&self,
    ) -> Result<ImmutableInput> {
        let input_path = self.thread_path().join(IMMUTABLE_INPUT_FILE);
        let content = fs::read_to_string(&input_path).await?;
        let input: ImmutableInput = serde_json::from_str(&content)?;
        Ok(input)
    }
    
    /// 创建执行快照
    pub async fn create_snapshot(
&self,
        executor_id: &ExecutorId,
        events: &[Event],
        artifacts: &[ArtifactSlot],
    ) -> Result<PathBuf> {
        let timestamp = Utc::now().timestamp_millis();
        let snapshot_path = self.snapshots_dir().join(format!("{}_{}.json", executor_id.0, timestamp));
        
        let snapshot = serde_json::json!({
            "executor_id": executor_id,
            "timestamp": timestamp,
            "events": events,
            "artifacts": artifacts,
        });
        
        let content = serde_json::to_string_pretty(&snapshot)?;
        fs::write(&snapshot_path, content).await?;
        
        info!(
            thread_id = %self.thread_id.0,
            executor_id = %executor_id.0,
            path = %snapshot_path.display(),
            "Created snapshot"
        );
        
        Ok(snapshot_path)
    }
    
    /// 获取 Thread 路径
    fn thread_path(&self) -> PathBuf {
        Self::thread_path_for_id(&self.base_path, &self.thread_id)
    }

    fn thread_path_for_id(base: &Path, thread_id: &ThreadId) -> PathBuf {
        base.join(THREADS_DIR).join(&thread_id.0)
    }
    
    fn event_log_path(&self,
    ) -> PathBuf {
        self.thread_path().join(EVENT_LOG_FILE)
    }
    
    fn artifacts_dir(&self,
    ) -> PathBuf {
        self.thread_path().join(ARTIFACTS_DIR)
    }
    
    fn artifact_path(&self, artifact_type: &ArtifactType) -> PathBuf {
        let filename = format!("{:?}.json", artifact_type).to_lowercase();
        self.artifacts_dir().join(filename)
    }
    
    fn snapshots_dir(&self,
    ) -> PathBuf {
        self.thread_path().join(SNAPSHOTS_DIR)
    }
    
    /// 获取 Thread ID
    pub fn thread_id(&self) -> &ThreadId {
        &self.thread_id
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;
    
    #[tokio::test]
    async fn test_create_and_load_thread() {
        let temp_dir = TempDir::new().unwrap();
        let thread_id = ThreadId::new();
        let session_id = SessionId("test_session".to_string());
        let immutable_input = ImmutableInput {
            task_goal: "Test task".to_string(),
            constraints: vec![],
            allowed_capabilities: vec![],
            forbidden_capabilities: vec![],
            session_context: HashMap::new(),
            compiled_at: Utc::now(),
        };
        
        // 创建 Thread
        let storage = ThreadStorage::create(
            temp_dir.path(),
            thread_id.clone(),
            session_id.clone(),
            immutable_input.clone(),
        ).await.unwrap();
        
        // 验证目录结构
        assert!(storage.thread_path().exists());
        assert!(storage.artifacts_dir().exists());
        assert!(storage.snapshots_dir().exists());
        
        // 加载并验证
        let loaded_storage = ThreadStorage::load(temp_dir.path(), &thread_id).await.unwrap();
        let meta = loaded_storage.read_meta().await.unwrap();
        assert_eq!(meta.thread_id.0, thread_id.0);
        
        let input = loaded_storage.read_immutable_input().await.unwrap();
        assert_eq!(input.task_goal, "Test task");
    }
    
    #[tokio::test]
    async fn test_append_and_read_events() {
        let temp_dir = TempDir::new().unwrap();
        let thread_id = ThreadId::new();
        let session_id = SessionId("test_session".to_string());
        let immutable_input = ImmutableInput {
            task_goal: "Test task".to_string(),
            constraints: vec![],
            allowed_capabilities: vec![],
            forbidden_capabilities: vec![],
            session_context: HashMap::new(),
            compiled_at: Utc::now(),
        };
        
        let storage = ThreadStorage::create(
            temp_dir.path(),
            thread_id,
            session_id,
            immutable_input,
        ).await.unwrap();
        
        // 追加事件
        let event1 = Event::new(
            EventType::StepStart,
            1,
            ExecutionPhase::Explore,
            serde_json::json!({"message": "Step 1"}),
        );
        
        let event2 = Event::new(
            EventType::ToolCall,
            1,
            ExecutionPhase::Explore,
            serde_json::json!({"tool": "bash", "command": "ls"}),
        );
        
        storage.append_event(&event1).await.unwrap();
        storage.append_event(&event2).await.unwrap();
        
        // 读取并验证
        let events = storage.read_event_log().await.unwrap();
        assert_eq!(events.len(), 2);
        assert_eq!(events[0].event_type, EventType::StepStart);
        assert_eq!(events[1].event_type, EventType::ToolCall);
    }
}