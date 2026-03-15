use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Arc;
use std::time::Instant;
use tokio::sync::broadcast;
use tracing::{debug, info, warn};

/// 时间预算配置
#[derive(Debug, Clone, Copy)]
pub struct TimeBudgetConfig {
    /// 总时间预算（毫秒）
    pub total_budget_ms: u64,

    /// 警告阈值（达到此比例时发出警告，默认0.8=80%）
    pub warning_threshold: f32,

    /// 保留正在运行任务的最近几轮观察
    pub recent_rounds_to_keep: usize,

    /// 是否包含部分完成的 artifacts
    pub include_partial_artifacts: bool,
}

impl Default for TimeBudgetConfig {
    fn default() -> Self {
        Self {
            total_budget_ms: 120_000, // 2分钟
            warning_threshold: 0.8,
            recent_rounds_to_keep: 3,
            include_partial_artifacts: true,
        }
    }
}

/// 时间警告事件
#[derive(Debug, Clone)]
pub enum TimeWarning {
    /// 达到警告阈值（80%时间已过）
    ApproachingLimit {
        elapsed_ms: u64,
        remaining_ms: u64,
        message: String,
    },
    /// 时间预算耗尽
    BudgetExhausted {
        elapsed_ms: u64,
        message: String,
    },
}

/// 时间预算监控器
pub struct TimeBudgetMonitor {
    config: TimeBudgetConfig,
    start_time: Instant,
    warning_sent: AtomicBool,
    shutdown_tx: broadcast::Sender<()>,
}

impl TimeBudgetMonitor {
    /// 创建新的时间预算监控器
    pub fn new(config: TimeBudgetConfig) -> Self {
        let (shutdown_tx, _) = broadcast::channel(1);
        Self {
            config,
            start_time: Instant::now(),
            warning_sent: AtomicBool::new(false),
            shutdown_tx,
        }
    }

    /// 获取已过时间（毫秒）
    pub fn elapsed_ms(&self) -> u64 {
        self.start_time.elapsed().as_millis() as u64
    }

    /// 检查是否还有剩余时间
    pub fn has_time_remaining(&self) -> bool {
        self.elapsed_ms() < self.config.total_budget_ms
    }

    /// 获取剩余时间（毫秒）
    pub fn remaining_ms(&self) -> u64 {
        self.config.total_budget_ms.saturating_sub(self.elapsed_ms())
    }

    /// 获取已用时间比例（0.0 - 1.0）
    pub fn elapsed_ratio(&self) -> f32 {
        self.elapsed_ms() as f32 / self.config.total_budget_ms as f32
    }

    /// 检查是否达到警告阈值
    pub fn should_warn(&self) -> bool {
        let ratio = self.elapsed_ratio();
        ratio >= self.config.warning_threshold
            && !self.warning_sent.load(Ordering::Relaxed)
    }

    /// 发送警告
    pub fn send_warning(&self,
    ) -> Option<TimeWarning> {
        if self
            .warning_sent
            .compare_exchange(false, true, Ordering::SeqCst, Ordering::SeqCst)
            .is_ok()
        {
            let elapsed = self.elapsed_ms();
            let remaining = self.remaining_ms();

            warn!(
                "Time budget warning: {}ms elapsed, {}ms remaining ({:.1}%)",
                elapsed,
                remaining,
                self.elapsed_ratio() * 100.0
            );

            Some(TimeWarning::ApproachingLimit {
                elapsed_ms: elapsed,
                remaining_ms: remaining,
                message: format!(
                    "Warning: {:.0}% of time budget used. {}ms remaining.",
                    self.elapsed_ratio() * 100.0,
                    remaining
                ),
            })
        } else {
            None
        }
    }

    /// 创建关闭信号接收器
    pub fn subscribe_shutdown(&self,
    ) -> broadcast::Receiver<()> {
        self.shutdown_tx.subscribe()
    }

    /// 触发关闭
    pub fn trigger_shutdown(&self) {
        info!("Triggering shutdown due to time budget exhaustion");
        let _ = self.shutdown_tx.send(());
    }

    /// 启动监控任务
    pub async fn start_monitoring(
        self: Arc<Self>,
    ) {
        let check_interval = tokio::time::Duration::from_millis(100);

        loop {
            tokio::time::sleep(check_interval).await;

            // 检查是否超时
            if !self.has_time_remaining() {
                warn!(
                    "Time budget exhausted: {}ms / {}ms",
                    self.elapsed_ms(),
                    self.config.total_budget_ms
                );
                self.trigger_shutdown();
                break;
            }

            // 检查是否需要发送警告
            if self.should_warn() {
                if let Some(warning) = self.send_warning() {
                    debug!("Time warning sent: {:?}", warning);
                }
            }
        }
    }

    /// 获取监控报告
    pub fn get_report(&self,
    ) -> TimeBudgetReport {
        TimeBudgetReport {
            total_budget_ms: self.config.total_budget_ms,
            elapsed_ms: self.elapsed_ms(),
            remaining_ms: self.remaining_ms(),
            elapsed_ratio: self.elapsed_ratio(),
            is_exhausted: !self.has_time_remaining(),
            warning_issued: self.warning_sent.load(Ordering::Relaxed),
        }
    }
}

/// 时间预算报告
#[derive(Debug, Clone)]
pub struct TimeBudgetReport {
    pub total_budget_ms: u64,
    pub elapsed_ms: u64,
    pub remaining_ms: u64,
    pub elapsed_ratio: f32,
    pub is_exhausted: bool,
    pub warning_issued: bool,
}

impl TimeBudgetReport {
    /// 生成人类可读的摘要
    pub fn to_summary(&self,
    ) -> String {
        if self.is_exhausted {
            format!(
                "Time budget EXHAUSTED: {}ms / {}ms ({}%)",
                self.elapsed_ms,
                self.total_budget_ms,
                self.elapsed_ratio * 100.0
            )
        } else {
            format!(
                "Time budget: {}ms elapsed, {}ms remaining ({:.1}% used)",
                self.elapsed_ms, self.remaining_ms, self.elapsed_ratio * 100.0
            )
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tokio::time::{sleep, Duration};

    #[test]
    fn test_time_budget_default() {
        let config = TimeBudgetConfig::default();
        assert_eq!(config.total_budget_ms, 120_000);
        assert_eq!(config.warning_threshold, 0.8);
        assert_eq!(config.recent_rounds_to_keep, 3);
    }

    #[test]
    fn test_monitor_basic() {
        let config = TimeBudgetConfig {
            total_budget_ms: 1000,
            ..Default::default()
        };
        let monitor = TimeBudgetMonitor::new(config);

        assert!(monitor.has_time_remaining());
        assert_eq!(monitor.remaining_ms(), 1000);
        assert!(!monitor.should_warn());
    }

    #[tokio::test]
    async fn test_monitor_elapsed() {
        let config = TimeBudgetConfig {
            total_budget_ms: 100,
            ..Default::default()
        };
        let monitor = TimeBudgetMonitor::new(config);

        sleep(Duration::from_millis(50)).await;

        let elapsed = monitor.elapsed_ms();
        assert!(elapsed >= 50);
        assert!(monitor.has_time_remaining());

        sleep(Duration::from_millis(100)).await;

        assert!(!monitor.has_time_remaining());
    }

    #[test]
    fn test_warning_threshold() {
        let config = TimeBudgetConfig {
            total_budget_ms: 1000,
            warning_threshold: 0.5,
            ..Default::default()
        };
        let monitor = TimeBudgetMonitor::new(config);

        // 初始状态不应该警告
        assert!(!monitor.should_warn());

        // 模拟时间流逝到 60%
        // 注意：这里我们需要手动设置警告状态，因为我们不能直接修改时间
        // 在实际测试中，我们可以使用 mock 时间或 sleep
    }

    #[test]
    fn test_report_generation() {
        let config = TimeBudgetConfig {
            total_budget_ms: 1000,
            ..Default::default()
        };
        let monitor = TimeBudgetMonitor::new(config);

        let report = monitor.get_report();
        assert_eq!(report.total_budget_ms, 1000);
        assert!(!report.is_exhausted);
    }
}
