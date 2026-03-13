#[cfg(test)]
mod tests {
    use std::sync::Arc;
    use tempfile::TempDir;

    use proclaw_block_composer::coordinator::{
        DirectoryLockManager, LockLevel,
    };
    use proclaw_block_composer::agent_thread::models::{ExecutorId, SessionId};

    #[tokio::test]
    async fn test_full_lock_workflow() {
        let temp_dir = TempDir::new().unwrap();
        let db_path = temp_dir.path().join("locks.db");
        let test_dir = temp_dir.path().join("test_workspace");
        tokio::fs::create_dir_all(&test_dir).await.unwrap();

        let lock_manager = Arc::new(DirectoryLockManager::new(db_path).unwrap());

        let status = lock_manager.query_lock_status(&test_dir
        ).await.unwrap().unwrap();
        assert!(!status.is_locked);
        assert_eq!(status.queue_length, 0);

        let lock = lock_manager.acquire_lock(
            test_dir.clone(),
            ExecutorId("exec_1".to_string()),
            SessionId("session_1".to_string()),
            LockLevel::Write,
            60,
        ).await.unwrap();

        let status = lock_manager.query_lock_status(&test_dir
        ).await.unwrap().unwrap();
        assert!(status.is_locked);
        assert_eq!(status.holder_executor_id, "exec_1");

        let locks = lock_manager.list_active_locks().await.unwrap();
        assert_eq!(locks.len(), 1);

        lock_manager.release_lock(lock).await.unwrap();

        let status = lock_manager.query_lock_status(&test_dir
        ).await.unwrap().unwrap();
        assert!(!status.is_locked);
    }

    #[tokio::test]
    async fn test_multiple_directories() {
        let temp_dir = TempDir::new().unwrap();
        let db_path = temp_dir.path().join("locks.db");
        let dir1 = temp_dir.path().join("dir1");
        let dir2 = temp_dir.path().join("dir2");
        tokio::fs::create_dir_all(&dir1).await.unwrap();
        tokio::fs::create_dir_all(&dir2).await.unwrap();

        let lock_manager = Arc::new(DirectoryLockManager::new(db_path).unwrap());

        let lock1 = lock_manager.acquire_lock(
            dir1.clone(),
            ExecutorId("exec_1".to_string()),
            SessionId("session_1".to_string()),
            LockLevel::Write,
            60,
        ).await.unwrap();

        let lock2 = lock_manager.acquire_lock(
            dir2.clone(),
            ExecutorId("exec_2".to_string()),
            SessionId("session_2".to_string()),
            LockLevel::Write,
            60,
        ).await.unwrap();

        let locks = lock_manager.list_active_locks().await.unwrap();
        assert_eq!(locks.len(), 2);

        lock_manager.release_lock(lock1).await.unwrap();
        lock_manager.release_lock(lock2).await.unwrap();
    }
}
