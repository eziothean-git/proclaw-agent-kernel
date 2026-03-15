use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::RwLock;

use crate::agent_thread::models::{Event, EventType};
use crate::scheduler::time_budget_monitor::TimeBudgetConfig;

/// 任务执行快照
#[derive(Debug, Clone)]
pub struct TaskSnapshot {
    pub task_id: String,
    pub process_name: String,
    pub status: TaskSnapshotStatus,
    pub completed_steps: usize,
    pub total_steps_estimate: Option<usize>,
    pub recent_observations: Vec<ObservationRecord>,
    pub partial_result: Option<String>,
    pub artifacts_collected: Vec<String>,
    pub execution_time_ms: u64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TaskSnapshotStatus {
    Completed,
    InProgress,
    PartiallyDone,
    Timeout,
}

#[derive(Debug, Clone)]
pub struct ObservationRecord {
    pub step_number: usize,
    pub timestamp: chrono::DateTime<chrono::Utc>,
    pub observation_type: String,
    pub brief_summary: String,
    pub key_findings: Vec<String>,
}

/// 任务快照收集器
pub struct TaskSnapshotCollector {
    config: TimeBudgetConfig,
    snapshots: Arc<RwLock<HashMap<String, TaskSnapshot>>>,
}

impl TaskSnapshotCollector {
    pub fn new(config: TimeBudgetConfig) -> Self {
        Self {
            config,
            snapshots: Arc::new(RwLock::new(HashMap::new())),
        }
    }

    /// 从事件历史中提取观察记录
    pub fn extract_observations(
        &self,
        event_history: &[Event],
        n: usize,
    ) -> Vec<ObservationRecord> {
        event_history
            .iter()
            .rev()
            .filter(|e| self.is_significant_event(e))
            .take(n * 2)
            .map(|e| self.event_to_observation(e))
            .collect()
    }

    fn is_significant_event(&self,
        event: &Event,
    ) -> bool {
        matches!(
            event.event_type,
            EventType::ToolResult | EventType::PhaseChange
        )
    }

    fn event_to_observation(
        &self,
        event: &Event,
    ) -> ObservationRecord {
        let summary = match event.event_type {
            EventType::ToolResult => {
                "Tool execution completed".to_string()
            }
            EventType::PhaseChange => {
                "Phase transition occurred".to_string()
            }
            _ => format!("Event: {:?}", event.event_type),
        };

        ObservationRecord {
            step_number: event.step_number as usize,
            timestamp: event.timestamp,
            observation_type: format!("{:?}", event.event_type),
            brief_summary: summary,
            key_findings: vec![],
        }
    }

    /// 创建任务快照
    pub async fn create_snapshot(
        &self,
        task_id: String,
        process_name: String,
        status: TaskSnapshotStatus,
        completed_steps: usize,
        event_history: &[Event],
        execution_time_ms: u64,
    ) -> TaskSnapshot {
        let recent_obs = self.extract_observations(
            event_history,
            self.config.recent_rounds_to_keep,
        );

        TaskSnapshot {
            task_id,
            process_name,
            status,
            completed_steps,
            total_steps_estimate: None,
            recent_observations: recent_obs,
            partial_result: None,
            artifacts_collected: vec![],
            execution_time_ms,
        }
    }

    /// 存储快照
    pub async fn store_snapshot(
        &self,
        snapshot: TaskSnapshot,
    ) {
        let mut snapshots = self.snapshots.write().await;
        snapshots.insert(snapshot.task_id.clone(), snapshot);
    }

    /// 获取所有快照
    pub async fn get_all_snapshots(&self,
    ) -> Vec<TaskSnapshot> {
        let snapshots = self.snapshots.read().await;
        snapshots.values().cloned().collect()
    }

    /// 获取特定任务快照
    pub async fn get_snapshot(
        &self,
        task_id: &str,
    ) -> Option<TaskSnapshot> {
        let snapshots = self.snapshots.read().await;
        snapshots.get(task_id).cloned()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_snapshot_collector_new() {
        let config = TimeBudgetConfig::default();
        let collector = TaskSnapshotCollector::new(config);
        // Should create successfully
    }

    #[tokio::test]
    async fn test_store_and_get_snapshot() {
        let config = TimeBudgetConfig::default();
        let collector = TaskSnapshotCollector::new(config);

        let snapshot = TaskSnapshot {
            task_id: "task_001".to_string(),
            process_name: "Test Process".to_string(),
            status: TaskSnapshotStatus::InProgress,
            completed_steps: 5,
            total_steps_estimate: Some(10),
            recent_observations: vec![],
            partial_result: Some("Partial result".to_string()),
            artifacts_collected: vec!["artifact_1".to_string()],
            execution_time_ms: 5000,
        };

        collector.store_snapshot(snapshot.clone()).await;

        let retrieved = collector.get_snapshot("task_001").await;
        assert!(retrieved.is_some());
        assert_eq!(retrieved.unwrap().task_id, "task_001");
    }
}
