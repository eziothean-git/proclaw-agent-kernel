//! Execution Coordinator 核心实现
//! 
//! 系统级资源协调层，跨线程、跨进程、跨 Session

use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::Arc;
use dashmap::DashMap;
use tokio::sync::RwLock;
use tracing::{debug, error, info, instrument, warn};

use super::{
    lock_manager::{DirectoryLock, DirectoryLockManager, LockLevel},
    models::*,
    skill_registry::SkillRegistry,
    ticket::TicketTracker,
};

/// Execution Coordinator - 跨 Session 共享的系统级资源协调器
pub struct ExecutionCoordinator {
    // 目录锁管理器
    lock_manager: Arc<DirectoryLockManager>,
    
    // Skill 注册表（替代 router）
    skill_registry: Arc<SkillRegistry>,
    
    // Ticket 追踪
    ticket_tracker: Arc<TicketTracker>,
    
    // 执行统计
    stats: Arc<RwLock<CoordinatorStats>>,
}

/// 协调器统计
#[derive(Debug, Default, Clone)]
pub struct CoordinatorStats {
    pub total_executions: u64,
    pub successful_executions: u64,
    pub failed_executions: u64,
    pub total_wait_time_ms: u64,
}

impl ExecutionCoordinator {
    /// 创建新的 Coordinator
    pub fn new(
        lock_manager: Arc<DirectoryLockManager>,
        skill_registry: Arc<SkillRegistry>,
        ticket_tracker: Arc<TicketTracker>,
    ) -> Self {
        Self {
            lock_manager,
            skill_registry,
            ticket_tracker,
            stats: Arc::new(RwLock::new(CoordinatorStats::default())),
        }
    }
    
    /// 执行 Skill（带资源锁定）
    #[instrument(skip(self, request), fields(executor_id = %request.context.executor_id, skill = %request.skill_name))]
    pub async fn execute_skill(
        &self,
        request: SkillRequest,
    ) -> anyhow::Result<SkillResult> {
        let start_time = std::time::Instant::now();

        // 1. 提取需要锁定的目录
        let directories = self.extract_directories(&request);

        info!(
            executor_id = %request.context.executor_id,
            skill = %request.skill_name,
            tool = %request.tool_name,
            directories = ?directories.iter().map(|p| p.display().to_string()).collect::<Vec<_>>(),
            "Executing skill"
        );

        // 2. 获取目录锁（带 FIFO 队列）
        let locks = if !directories.is_empty() {
            self.acquire_directory_locks(
                &directories,
                &request.context.executor_id,
                &request.context.session_id,
            ).await?
        } else {
            Vec::new()
        };
        
        let wait_time = start_time.elapsed();
        
        // 3. 通过 SkillRegistry 执行 Skill
        debug!(skill = %request.skill_name, "Executing via skill registry");
        let result = self.skill_registry.execute(request.clone()).await;
        
        // 4. 释放锁
        for lock in locks {
            if let Err(e) = self.lock_manager.release_lock(lock).await {
                warn!(error = %e, "Failed to release lock");
            }
        }
        
        // 5. 更新统计
        let execution_time = start_time.elapsed();
        {
            let mut stats = self.stats.write().await;
            stats.total_executions += 1;
            stats.total_wait_time_ms += wait_time.as_millis() as u64;
            match &result {
                Ok(r) if r.success => stats.successful_executions += 1,
                _ => stats.failed_executions += 1,
            }
        }
        
        let result = result.map_err(|e| {
            error!(error = %e, "Skill execution failed");
            e
        })?;
        
        info!(
            executor_id = %request.context.executor_id,
            skill = %request.skill_name,
            success = result.success,
            wait_ms = wait_time.as_millis(),
            execution_ms = execution_time.as_millis(),
            "Skill execution completed"
        );
        
        Ok(result)
    }
    
    /// 提取需要锁定的目录
    fn extract_directories(&self,
        request: &SkillRequest,
    ) -> Vec<PathBuf> {
        // 从参数中提取 working_dir 等路径
        let mut directories = Vec::new();
        
        // 检查常见的路径参数
        for key in ["working_dir", "path", "directory", "target_path"] {
            if let Some(path_str) = request.parameters.get(key).and_then(|v| v.as_str()) {
                if let Ok(path) = PathBuf::from(path_str).canonicalize() {
                    if path.is_dir() {
                        directories.push(path);
                    }
                }
            }
        }
        
        // 去重并排序（避免死锁）
        directories.sort();
        directories.dedup();
        
        directories
    }
    
    /// 获取多个目录锁（避免死锁）
    async fn acquire_directory_locks(
        &self,
        directories: &[PathBuf],
        executor_id: &str,
        session_id: &str,
    ) -> anyhow::Result<Vec<DirectoryLock>> {
        let mut locks = Vec::new();

        // 按顺序获取，避免死锁
        for directory in directories {
            let lock = self.lock_manager.acquire_lock(
                directory.clone(),
                crate::agent_thread::ExecutorId(executor_id.to_string()),
                crate::agent_thread::SessionId(session_id.to_string()),
                LockLevel::Write,  // Skill 执行需要写锁
                300,  // 5 分钟超时
            ).await?;

            locks.push(lock);
        }

        Ok(locks)
    }
    
    /// 获取统计信息
    pub async fn get_stats(&self,
    ) -> CoordinatorStats {
        self.stats.read().await.clone()
    }
}

/// 路由决策（保留供将来使用）
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RouteDecision {
    Local,
    Remote,
}