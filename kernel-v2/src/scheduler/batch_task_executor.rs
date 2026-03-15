use std::sync::Arc;
use tokio::sync::Semaphore;
use tokio::time::{timeout, Duration};
use tracing::{info, warn};

use crate::personality::models::ProcessDefinition;
use crate::scheduler::{
    snapshot_collector::{TaskSnapshot, TaskSnapshotStatus},
    time_budget_monitor::{TimeBudgetConfig, TimeBudgetMonitor},
    xml_models::{
        CompletedTaskReport, InterruptedTaskReport, SystemNotice,
        TaskStatusReport,
    },
};

/// Sub task request
#[derive(Debug, Clone)]
pub struct SubTaskRequest {
    pub task_id: String,
    pub process: ProcessDefinition,
    pub depth: u32,
}

/// Batch execution result
#[derive(Debug, Clone)]
pub struct BatchExecutionResult {
    pub batch_id: String,
    pub completed_tasks: Vec<TaskSnapshot>,
    pub interrupted_tasks: Vec<TaskSnapshot>,
    pub time_budget_exceeded: bool,
    pub system_notice: SystemNotice,
    pub task_status_report: TaskStatusReport,
    pub summary: String,
}

/// Batch task executor with time budget support
pub struct BatchTaskExecutor;

impl BatchTaskExecutor {
    pub fn new() -> Self {
        Self
    }

    /// Execute batch with time budget
    pub async fn execute_with_budget(
        &self,
        _parent_session_id: String,
        sub_tasks: Vec<SubTaskRequest>,
        config: TimeBudgetConfig,
    ) -> anyhow::Result<BatchExecutionResult> {
        let batch_id = format!("batch_{}", uuid::Uuid::new_v4());
        info!(
            batch_id = %batch_id,
            task_count = sub_tasks.len(),
            budget_ms = config.total_budget_ms,
            "Starting batch execution with time budget"
        );

        let monitor = Arc::new(TimeBudgetMonitor::new(config));
        let semaphore = Arc::new(Semaphore::new(5)); // Max 5 concurrent

        let mut handles = Vec::new();

        for sub_task in sub_tasks.clone() {
            let semaphore = semaphore.clone();
            let monitor = monitor.clone();
            let task_id = sub_task.task_id.clone();

            let handle = tokio::spawn(async move {
                let _permit = semaphore.acquire().await.unwrap();

                if !monitor.has_time_remaining() {
                    return None;
                }

                Self::execute_single_task(sub_task, monitor).await
            });

            handles.push((task_id, handle));
        }

        let budget_duration = Duration::from_millis(config.total_budget_ms);
        let results = match timeout(
            budget_duration,
            Self::collect_results(handles),
        )
        .await
        {
            Ok(results) => {
                info!("All tasks completed within time budget");
                results
            }
            Err(_) => {
                warn!("Time budget exceeded, collecting partial results");
                vec![]
            }
        };

        let (completed, interrupted) = Self::categorize_results(results, &sub_tasks);

        let time_budget_exceeded = monitor.elapsed_ms() >= config.total_budget_ms;

        let system_notice = SystemNotice::time_budget_exceeded(
            config.total_budget_ms,
            monitor.elapsed_ms(),
            completed.len(),
            interrupted.len(),
        );

        let task_status_report = Self::build_status_report(&completed, &interrupted);

        let summary = Self::generate_summary(
            &completed,
            &interrupted,
            time_budget_exceeded,
        );

        Ok(BatchExecutionResult {
            batch_id,
            completed_tasks: completed,
            interrupted_tasks: interrupted,
            time_budget_exceeded,
            system_notice,
            task_status_report,
            summary,
        })
    }

    async fn execute_single_task(
        _sub_task: SubTaskRequest,
        monitor: Arc<TimeBudgetMonitor>,
    ) -> Option<TaskSnapshot> {
        let start = std::time::Instant::now();

        while monitor.has_time_remaining() {
            tokio::time::sleep(Duration::from_millis(10)).await;
        }

        Some(TaskSnapshot {
            task_id: _sub_task.task_id,
            process_name: _sub_task.process.name,
            status: TaskSnapshotStatus::Completed,
            completed_steps: 1,
            total_steps_estimate: None,
            recent_observations: vec![],
            partial_result: None,
            artifacts_collected: vec![],
            execution_time_ms: start.elapsed().as_millis() as u64,
        })
    }

    async fn collect_results(
        handles: Vec<(String, tokio::task::JoinHandle<Option<TaskSnapshot>>)>,
    ) -> Vec<TaskSnapshot> {
        let mut results = Vec::new();

        for (_task_id, handle) in handles {
            if let Ok(Some(snapshot)) = handle.await {
                results.push(snapshot);
            }
        }

        results
    }

    fn categorize_results(
        results: Vec<TaskSnapshot>,
        _sub_tasks: &[SubTaskRequest],
    ) -> (Vec<TaskSnapshot>, Vec<TaskSnapshot>) {
        let mut completed = Vec::new();
        let mut interrupted = Vec::new();

        for result in results {
            match result.status {
                TaskSnapshotStatus::Completed => completed.push(result),
                _ => interrupted.push(result),
            }
        }

        (completed, interrupted)
    }

    fn build_status_report(
        completed: &[TaskSnapshot],
        interrupted: &[TaskSnapshot],
    ) -> TaskStatusReport {
        let completed_reports = completed
            .iter()
            .map(|t| CompletedTaskReport {
                id: t.task_id.clone(),
                name: t.process_name.clone(),
                duration_ms: t.execution_time_ms,
                result: t.partial_result.clone().unwrap_or_default(),
                artifacts: vec![],
            })
            .collect();

        let interrupted_reports = interrupted
            .iter()
            .map(|t| InterruptedTaskReport {
                id: t.task_id.clone(),
                name: t.process_name.clone(),
                progress: format!("{}/{:?}", t.completed_steps, t.total_steps_estimate),
                duration_ms: t.execution_time_ms,
                last_observation: "Task interrupted".to_string(),
                recent_findings: t
                    .recent_observations
                    .iter()
                    .map(|o| o.brief_summary.clone())
                    .collect(),
                partial_result: t.partial_result.clone(),
            })
            .collect();

        TaskStatusReport {
            completed: crate::scheduler::xml_models::CompletedTasks {
                tasks: completed_reports,
            },
            interrupted: crate::scheduler::xml_models::InterruptedTasks {
                tasks: interrupted_reports,
            },
        }
    }

    fn generate_summary(
        completed: &[TaskSnapshot],
        interrupted: &[TaskSnapshot],
        time_exceeded: bool,
    ) -> String {
        let mut summary = String::new();

        if time_exceeded {
            summary.push_str("## ⚠️ Time Budget Exceeded\n\n");
        } else {
            summary.push_str("## ✅ Batch Execution Complete\n\n");
        }

        summary.push_str(&format!(
            "Completed: {} tasks\n",
            completed.len()
        ));
        summary.push_str(&format!(
            "Interrupted: {} tasks\n",
            interrupted.len()
        ));

        if !completed.is_empty() {
            summary.push_str("\n### Completed Tasks\n");
            for task in completed {
                summary.push_str(&format!("- {}\n", task.process_name));
            }
        }

        if !interrupted.is_empty() {
            summary.push_str("\n### Interrupted Tasks\n");
            for task in interrupted {
                summary.push_str(&format!(
                    "- {} (progress: {}/{:?})\n",
                    task.process_name,
                    task.completed_steps,
                    task.total_steps_estimate
                ));
            }
        }

        summary
    }
}

impl Default for BatchTaskExecutor {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_batch_executor_new() {
        let executor = BatchTaskExecutor::new();
    }

    #[tokio::test]
    async fn test_execute_with_short_budget() {
        let executor = BatchTaskExecutor::new();
        let config = TimeBudgetConfig {
            total_budget_ms: 50, // Very short budget
            ..Default::default()
        };

        let sub_tasks = vec![SubTaskRequest {
            task_id: "task_1".to_string(),
            process: ProcessDefinition {
                name: "Test Process".to_string(),
                goal: "Test".to_string(),
                capabilities: vec![],
                forbidden_capabilities: None,
                constraints: None,
                security_level: None,
                dependencies: None,
            },
            depth: 0,
        }];

        let result = executor
            .execute_with_budget("session_1".to_string(), sub_tasks, config)
            .await;

        assert!(result.is_ok());
        let batch_result = result.unwrap();
        assert!(batch_result.time_budget_exceeded);
    }
}
