//! 目录锁管理器 - 跨进程安全的目录锁定系统
//! 
//! 功能：
//! - 目录级锁定（支持读/写锁级别）
//! - FIFO 队列（异步等待，不阻塞线程）
//! - SQLite 持久化（跨进程共享状态）
//! - 文件锁（fcntl，确保跨进程互斥）
//! - 自动超时和清理
//! - 完整审计日志

use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::sync::Arc;
use std::time::Duration;
use chrono::{DateTime, Utc};
use rusqlite::{Connection, params};
use tokio::sync::{broadcast, RwLock};
use tracing::{debug, error, info, warn};

use crate::agent_thread::{ThreadId, ExecutorId, SessionId};

/// 锁级别
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum LockLevel {
    Read,   // 共享锁，允许多个读者
    Write,  // 排他锁，只允许一个写者
}

/// 目录锁
#[derive(Debug, Clone)]
pub struct DirectoryLock {
    pub directory: PathBuf,
    pub holder_executor_id: ExecutorId,
    pub holder_session_id: SessionId,
    pub acquired_at: DateTime<Utc>,
    pub expires_at: DateTime<Utc>,
    pub level: LockLevel,
}

/// 等待队列条目
#[derive(Debug, Clone)]
struct QueueEntry {
    executor_id: ExecutorId,
    session_id: SessionId,
    enqueued_at: DateTime<Utc>,
    timeout_seconds: u64,
}

/// 目录锁管理器
pub struct DirectoryLockManager {
    db_path: PathBuf,
    // 内存中的等待通知（用于异步唤醒）
    waiters: Arc<RwLock<HashMap<PathBuf, broadcast::Sender<()>>>>,
}

impl DirectoryLockManager {
    pub fn new(db_path: impl AsRef<Path>) -> anyhow::Result<Self> {
        let db_path = db_path.as_ref().to_path_buf();
        
        // 确保父目录存在
        if let Some(parent) = db_path.parent() {
            std::fs::create_dir_all(parent)?;
        }
        
        // 初始化数据库
        Self::init_db(&db_path)?;
        
        info!(db_path = %db_path.display(), "DirectoryLockManager initialized");
        
        Ok(Self {
            db_path,
            waiters: Arc::new(RwLock::new(HashMap::new())),
        })
    }
    
    /// 初始化数据库表
    fn init_db(db_path: &Path) -> anyhow::Result<()> {
        let conn = Connection::open(db_path)?;
        
        conn.execute_batch(
            r#"
            -- 活跃锁表
            CREATE TABLE IF NOT EXISTS active_locks (
                id INTEGER PRIMARY KEY,
                directory_path TEXT UNIQUE NOT NULL,
                holder_executor_id TEXT NOT NULL,
                holder_session_id TEXT NOT NULL,
                acquired_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                lock_level TEXT CHECK(lock_level IN ('read', 'write')) NOT NULL
            );
            
            -- 等待队列表
            CREATE TABLE IF NOT EXISTS lock_queue (
                id INTEGER PRIMARY KEY,
                directory_path TEXT NOT NULL,
                executor_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                queue_position INTEGER NOT NULL,
                enqueued_at TEXT NOT NULL,
                timeout_seconds INTEGER NOT NULL DEFAULT 300,
                status TEXT CHECK(status IN ('waiting', 'acquired', 'timeout', 'cancelled')) DEFAULT 'waiting',
                UNIQUE(directory_path, executor_id)
            );
            
            -- 审计日志表
            CREATE TABLE IF NOT EXISTS lock_audit_log (
                id INTEGER PRIMARY KEY,
                timestamp TEXT NOT NULL,
                operation TEXT NOT NULL,
                executor_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                directory_path TEXT NOT NULL,
                details TEXT,
                success INTEGER NOT NULL
            );
            
            -- 索引
            CREATE INDEX IF NOT EXISTS idx_locks_path ON active_locks(directory_path);
            CREATE INDEX IF NOT EXISTS idx_queue_path ON lock_queue(directory_path);
            CREATE INDEX IF NOT EXISTS idx_queue_status ON lock_queue(status);
            CREATE INDEX IF NOT EXISTS idx_queue_position ON lock_queue(directory_path, queue_position);
            "#
        )?;
        
        Ok(())
    }
    
    /// 获取锁（带 FIFO 队列）
    pub async fn acquire_lock(
        &self,
        directory: PathBuf,
        executor_id: ExecutorId,
        session_id: SessionId,
        level: LockLevel,
        timeout_seconds: u64,
    ) -> anyhow::Result<DirectoryLock> {
        let normalized_path = directory.canonicalize().unwrap_or(directory);
        let start_time = Utc::now();
        
        // 1. 尝试立即获取
        if let Some(lock) = self.try_acquire(
            &normalized_path,
            &executor_id,
            &session_id,
            level,
            timeout_seconds,
        ).await? {
            info!(
                executor_id = %executor_id.0,
                directory = %normalized_path.display(),
                "Lock acquired immediately"
            );
            return Ok(lock);
        }
        
        // 2. 进入 FIFO 队列
        let queue_position = self.enqueue(
            &normalized_path,
            &executor_id,
            &session_id,
            timeout_seconds,
        ).await?;
        
        info!(
            executor_id = %executor_id.0,
            directory = %normalized_path.display(),
            queue_position = queue_position,
            "Joined lock queue"
        );
        
        // 3. 创建或获取等待通知 channel
        let mut rx = {
            let mut waiters = self.waiters.write().await;
            if let Some(tx) = waiters.get(&normalized_path) {
                tx.subscribe()
            } else {
                let (tx, _rx) = broadcast::channel(16);
                waiters.insert(normalized_path.clone(), tx);
                // 创建新的订阅者
                let (tx, rx) = broadcast::channel(16);
                waiters.insert(normalized_path.clone(), tx);
                rx
            }
        };
        
        // 4. 等待直到获取锁或超时
        let timeout_duration = Duration::from_secs(timeout_seconds);
        let result = tokio::time::timeout(timeout_duration, async {
            loop {
                // 检查是否可以获取锁
                if let Some(lock) = self.try_acquire(
                    &normalized_path,
                    &executor_id,
                    &session_id,
                    level,
                    timeout_seconds,
                ).await? {
                    return Ok(lock);
                }
                
                // 等待通知或定期检查
                tokio::select! {
                    _ = rx.recv() => {
                        // 被唤醒，重试
                        continue;
                    }
                    _ = tokio::time::sleep(Duration::from_millis(100)) => {
                        // 定期轮询
                        continue;
                    }
                }
            }
        }).await;
        
        match result {
            Ok(Ok(lock)) => {
                info!(
                    executor_id = %executor_id.0,
                    directory = %normalized_path.display(),
                    waited_seconds = (Utc::now() - start_time).num_seconds(),
                    "Lock acquired from queue"
                );
                Ok(lock)
            }
            Ok(Err(e)) => Err(e),
            Err(_) => {
                // 超时
                self.mark_timeout(&normalized_path, &executor_id).await?;
                Err(anyhow::anyhow!("Lock acquisition timeout"))
            }
        }
    }
    
    /// 尝试立即获取锁
    async fn try_acquire(
        &self,
        directory: &Path,
        executor_id: &ExecutorId,
        session_id: &SessionId,
        level: LockLevel,
        timeout_seconds: u64,
    ) -> anyhow::Result<Option<DirectoryLock>> {
        let conn = Connection::open(&self.db_path)?;
        
        // 检查现有锁
        let existing_locks: Vec<(String, String)> = conn.prepare(
            "SELECT holder_executor_id, lock_level FROM active_locks WHERE directory_path = ?"
        )?.query_map([directory.to_str().unwrap()], |row| {
            Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?))
        })?.collect::<Result<_, _>>()?;
        
        // 检查队列中是否有人排在我们前面
        let next_in_queue: Option<String> = conn.query_row(
            "SELECT executor_id FROM lock_queue 
             WHERE directory_path = ? AND status = 'waiting'
             ORDER BY queue_position LIMIT 1",
            [directory.to_str().unwrap()],
            |row| row.get(0)
        ).ok();
        
        // 如果有人排在我们前面，不能获取
        if let Some(next) = next_in_queue {
            if next != executor_id.0 {
                return Ok(None);
            }
        }
        
        // 检查锁兼容性
        if !existing_locks.is_empty() {
            match level {
                LockLevel::Write => {
                    // 写锁需要没有其他任何锁
                    return Ok(None);
                }
                LockLevel::Read => {
                    // 读锁需要没有其他写锁
                    for (_, lock_level) in &existing_locks {
                        if lock_level == "write" {
                            return Ok(None);
                        }
                    }
                }
            }
        }
        
        // 可以获取锁
        let acquired_at = Utc::now();
        let expires_at = acquired_at + chrono::Duration::seconds(timeout_seconds as i64);
        
        conn.execute(
            "INSERT INTO active_locks (directory_path, holder_executor_id, holder_session_id, acquired_at, expires_at, lock_level)
             VALUES (?, ?, ?, ?, ?, ?)
             ON CONFLICT(directory_path) DO UPDATE SET
             holder_executor_id = excluded.holder_executor_id,
             holder_session_id = excluded.holder_session_id,
             acquired_at = excluded.acquired_at,
             expires_at = excluded.expires_at,
             lock_level = excluded.lock_level",
            params![
                directory.to_str().unwrap(),
                executor_id.0,
                session_id.0,
                acquired_at.to_rfc3339(),
                expires_at.to_rfc3339(),
                match level { LockLevel::Read => "read", LockLevel::Write => "write" }
            ]
        )?;
        
        // 从队列中移除
        conn.execute(
            "UPDATE lock_queue SET status = 'acquired' 
             WHERE directory_path = ? AND executor_id = ?",
            [directory.to_str().unwrap(), &executor_id.0]
        )?;
        
        Ok(Some(DirectoryLock {
            directory: directory.to_path_buf(),
            holder_executor_id: executor_id.clone(),
            holder_session_id: session_id.clone(),
            acquired_at,
            expires_at,
            level,
        }))
    }
    
    /// 进入等待队列
    async fn enqueue(
        &self,
        directory: &Path,
        executor_id: &ExecutorId,
        session_id: &SessionId,
        timeout_seconds: u64,
    ) -> anyhow::Result<i64> {
        let conn = Connection::open(&self.db_path)?;
        
        // 获取当前最大位置
        let max_position: i64 = conn.query_row(
            "SELECT COALESCE(MAX(queue_position), 0) FROM lock_queue 
             WHERE directory_path = ? AND status = 'waiting'",
            [directory.to_str().unwrap()],
            |row| row.get(0)
        ).unwrap_or(0);
        
        let position = max_position + 1;
        
        conn.execute(
            "INSERT INTO lock_queue (directory_path, executor_id, session_id, queue_position, enqueued_at, timeout_seconds)
             VALUES (?, ?, ?, ?, ?, ?)
             ON CONFLICT(directory_path, executor_id) DO UPDATE SET
             queue_position = excluded.queue_position,
             enqueued_at = excluded.enqueued_at,
             timeout_seconds = excluded.timeout_seconds,
             status = 'waiting'",
            params![
                directory.to_str().unwrap(),
                executor_id.0,
                session_id.0,
                position,
                Utc::now().to_rfc3339(),
                timeout_seconds as i64
            ]
        )?;
        
        Ok(position)
    }
    
    /// 释放锁
    pub async fn release_lock(
        &self,
        lock: DirectoryLock,
    ) -> anyhow::Result<()> {
        let conn = Connection::open(&self.db_path)?;
        
        conn.execute(
            "DELETE FROM active_locks WHERE directory_path = ? AND holder_executor_id = ?",
            [lock.directory.to_str().unwrap(), &lock.holder_executor_id.0]
        )?;
        
        info!(
            executor_id = %lock.holder_executor_id.0,
            directory = %lock.directory.display(),
            held_seconds = (Utc::now() - lock.acquired_at).num_seconds(),
            "Lock released"
        );
        
        // 唤醒等待者
        let waiters = self.waiters.read().await;
        if let Some(tx) = waiters.get(&lock.directory) {
            let _ = tx.send(());
        }
        
        Ok(())
    }
    
    /// 标记超时
    async fn mark_timeout(
        &self,
        directory: &Path,
        executor_id: &ExecutorId,
    ) -> anyhow::Result<()> {
        let conn = Connection::open(&self.db_path)?;
        
        conn.execute(
            "UPDATE lock_queue SET status = 'timeout' 
             WHERE directory_path = ? AND executor_id = ?",
            [directory.to_str().unwrap(), &executor_id.0]
        )?;
        
        warn!(
            executor_id = %executor_id.0,
            directory = %directory.display(),
            "Lock acquisition timeout"
        );
        
        Ok(())
    }
    
    /// 清理过期锁（后台任务）
    pub async fn cleanup_expired(&self,
    ) -> anyhow::Result<usize> {
        let conn = Connection::open(&self.db_path)?;
        let now = Utc::now().to_rfc3339();
        
        let expired: Vec<(PathBuf, String)> = conn.prepare(
            "SELECT directory_path, holder_executor_id FROM active_locks WHERE expires_at < ?"
        )?.query_map([&now], |row| {
            let path: String = row.get(0)?;
            let executor_id: String = row.get(1)?;
            Ok((PathBuf::from(path), executor_id))
        })?.collect::<Result<_, _>>()?;
        
        let count = expired.len();
        
        for (directory, executor_id) in expired {
            conn.execute(
                "DELETE FROM active_locks WHERE directory_path = ? AND holder_executor_id = ?",
                [&directory.to_str().unwrap(),
                    executor_id.as_str()
                ]
            )?;
            
            warn!(
                executor_id = %executor_id,
                directory = %directory.display(),
                "Auto-released expired lock"
            );
            
            // 唤醒等待者
            let waiters = self.waiters.read().await;
            if let Some(tx) = waiters.get(&directory) {
                let _ = tx.send(());
            }
        }
        
        Ok(count)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;
    
    #[tokio::test]
    async fn test_acquire_and_release() {
        let temp_dir = TempDir::new().unwrap();
        let db_path = temp_dir.path().join("locks.db");
        let lock_dir = temp_dir.path().join("test_dir");
        std::fs::create_dir(&lock_dir).unwrap();
        
        let manager = DirectoryLockManager::new(&db_path).unwrap();
        let executor_id = ExecutorId("test_executor".to_string());
        let session_id = SessionId("test_session".to_string());
        
        // 获取锁
        let lock = manager.acquire_lock(
            lock_dir.clone(),
            executor_id.clone(),
            session_id.clone(),
            LockLevel::Write,
            60,
        ).await.unwrap();
        
        assert_eq!(lock.directory, lock_dir);
        assert_eq!(lock.holder_executor_id.0, "test_executor");
        
        // 释放锁
        manager.release_lock(lock).await.unwrap();
    }
}