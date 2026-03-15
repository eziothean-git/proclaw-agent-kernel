# 批处理多任务执行方案 v2 - Time Budget + 优雅降级

## 核心设计变更

从"等待全部完成"改为 **"Time Budget + 部分结果返回"** 模式。

### 执行流程对比

**旧方案（阻塞式）**：
```
启动所有子任务 → 等待全部完成 → 汇总结果 → 返回
                    ↑
            如果有一个任务卡住，全部阻塞
```

**新方案（Time Budget）**：
```
启动所有子任务 + 启动计时器
    │
    ├─► 任务1完成 ────────┐
    ├─► 任务2完成 ────────┤  收集结果
    ├─► 任务3运行中 ──────┤  （保留最近N轮）
    │   [最近观察...]     │
    │                     │
    ▼                     │
时间预算到期！             │
    │                     │
    ▼                     │
生成部分结果报告 ◄─────────┘
    │
    ▼
添加系统提示："时间限制强制返回"
    │
    ▼
返回给 Prime
```

---

## Time Budget 机制

### 配置结构

```rust
pub struct TimeBudgetConfig {
    /// 总时间预算（毫秒）
    pub total_budget_ms: u64,
    
    /// 警告阈值（达到此比例时发出警告）
    pub warning_threshold: f32,  // 默认 0.8 (80%)
    
    /// 保留正在运行任务的最近几轮观察
    pub recent_rounds_to_keep: usize,  // 默认 3
    
    /// 是否包含部分完成的 artifacts
    pub include_partial_artifacts: bool,  // 默认 true
}

impl Default for TimeBudgetConfig {
    fn default() -> Self {
        Self {
            total_budget_ms: 120_000,  // 2分钟
            warning_threshold: 0.8,
            recent_rounds_to_keep: 3,
            include_partial_artifacts: true,
        }
    }
}
```

### 时间预算监控

```rust
pub struct TimeBudgetMonitor {
    config: TimeBudgetConfig,
    start_time: Instant,
    warning_sent: Arc<AtomicBool>,
}

impl TimeBudgetMonitor {
    pub fn new(config: TimeBudgetConfig) -> Self {
        Self {
            config,
            start_time: Instant::now(),
            warning_sent: Arc::new(AtomicBool::new(false)),
        }
    }
    
    /// 检查是否还有剩余时间
    pub fn has_time_remaining(&self) -> bool {
        self.elapsed_ms() < self.config.total_budget_ms
    }
    
    /// 获取剩余时间
    pub fn remaining_ms(&self) -> u64 {
        self.config.total_budget_ms.saturating_sub(self.elapsed_ms())
    }
    
    /// 检查是否达到警告阈值
    pub fn should_warn(&self) -> bool {
        let ratio = self.elapsed_ms() as f32 / self.config.total_budget_ms as f32;
        ratio >= self.config.warning_threshold && 
        !self.warning_sent.load(Ordering::Relaxed)
    }
    
    /// 发送警告（给正在运行的任务）
    pub async fn send_warning(&self) {
        if self.warning_sent.compare_exchange(
            false, 
            true, 
            Ordering::SeqCst, 
            Ordering::SeqCst
        ).is_ok() {
            // 向所有运行中的任务发送警告信号
            // 让它们知道时间即将耗尽，应该尽快完成当前步骤
        }
    }
}
```

---

## 部分结果收集

### 任务状态快照

```rust
/// 任务执行快照（用于时间预算到期时返回）
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
    Completed,      // 已完成
    InProgress,     // 进行中（时间到）
    PartiallyDone,  // 部分完成（被中断）
    Timeout,        // 超时
}

#[derive(Debug, Clone)]
pub struct ObservationRecord {
    pub step_number: usize,
    pub timestamp: DateTime<Utc>,
    pub observation_type: String,  // "tool_call", "tool_result", "phase_change"
    pub brief_summary: String,
    pub key_findings: Vec<String>,
}
```

### 快照收集器

```rust
pub struct TaskSnapshotCollector {
    config: TimeBudgetConfig,
    snapshots: Arc<RwLock<HashMap<String, TaskSnapshot>>>,
}

impl TaskSnapshotCollector {
    /// 从正在运行的任务中收集快照
    pub async fn collect_snapshots(
        &self,
        active_executors: &HashMap<String, ActiveExecutorHandle>,
    ) -> Vec<TaskSnapshot> {
        let mut snapshots = Vec::new();
        
        for (task_id, handle) in active_executors {
            // 获取任务的当前状态
            let state = handle.get_current_state().await;
            
            // 提取最近N轮观察
            let recent_obs = self.extract_recent_observations(
                &state.event_history,
                self.config.recent_rounds_to_keep
            );
            
            let snapshot = TaskSnapshot {
                task_id: task_id.clone(),
                process_name: handle.process_name.clone(),
                status: TaskSnapshotStatus::InProgress,
                completed_steps: state.current_step,
                total_steps_estimate: state.estimated_total_steps,
                recent_observations: recent_obs,
                partial_result: state.intermediate_result.clone(),
                artifacts_collected: state.artifacts.keys().cloned().collect(),
                execution_time_ms: state.start_time.elapsed().as_millis() as u64,
            };
            
            snapshots.push(snapshot);
        }
        
        snapshots
    }
    
    /// 提取最近N轮的关键观察
    fn extract_recent_observations(
        &self,
        event_history: &[Event],
        n: usize,
    ) -> Vec<ObservationRecord> {
        event_history
            .iter()
            .rev()  // 从最新开始
            .take(n * 2)  // 取最近N轮的 events（每轮可能有多个event）
            .filter(|e| self.is_significant_event(e))  // 只保留重要事件
            .map(|e| self.event_to_observation(e))
            .collect()
    }
    
    fn is_significant_event(&self, event: &Event) -> bool {
        matches!(event.event_type, 
            EventType::ToolResult | 
            EventType::PhaseChange |
            EventType::ArtifactCreated
        )
    }
}
```

---

## XML 结构扩展 - 系统提示块

### 强制返回标记

```xml
<?xml version="1.0" encoding="UTF-8"?>
<agent-response version="1.0" xmlns="http://proclaw.ai/response">
  
  <!-- 系统提示块：告诉 LLM 这是时间限制后强制返回的结果 -->
  <system-notice type="time_budget_exceeded" priority="critical">
    <message>
      警告：执行时间已达到预算限制（120秒）。
      以下结果是部分完成的，部分任务仍在运行中被中断。
    </message>
    <metadata>
      <time-budget-ms>120000</time-budget-ms>
      <elapsed-ms>120050</elapsed-ms>
      <completed-tasks>2</completed-tasks>
      <interrupted-tasks>2</interrupted-tasks>
    </metadata>
    <guidance>
      作为 LLM，你应该：
      1. 基于部分结果给出最佳-effort回答
      2. 明确告知用户哪些任务未完成
      3. 建议是否需要延长时间重新执行未完成的任务
      4. 不要假设未完成任务的最终结果
    </guidance>
  </system-notice>
  
  <reasoning>
    <observation>
      批处理任务执行达到时间限制。
      已完成任务：2/4
      进行中任务：2/4（被中断）
    </observation>
    <thought>
      虽然时间已到，但已完成2个任务，
      可以基于这些结果给出初步分析。
      对于未完成的任务，需要告知用户。
    </thought>
    <plan>
      <step order="1">总结已完成任务的结果</step>
      <step order="2">报告未完成任务的状态</step>
      <step order="3">给出建议（是否延长时间）</step>
    </plan>
  </reasoning>
  
  <explanation>
    我已分析了部分模块，但时间不足以完成全部4个任务。
    
    ✅ 已完成的任务：
    - 模块A分析：发现3个循环依赖
    - 模块B分析：测试覆盖率85%
    
    ⏳ 未完成的任务：
    - 模块C分析：正在检查性能瓶颈（已执行3/5步）
    - 模块D分析：正在统计代码行数（已执行2/4步）
    
    建议：如需完整分析，可以延长执行时间或分批处理。
  </explanation>
  
  <actions>
    <!-- 基于部分结果的最佳-effort行动 -->
    <action type="tool_call" id="partial_response">
      <skill name="response"/>
      <tool name="partial_summary"/>
      <parameters>
        <param name="completed">module_a,module_b</param>
        <param name="interrupted">module_c,module_d</param>
      </parameters>
    </action>
  </actions>
  
  <!-- 详细的任务状态（供 LLM 参考） -->
  <task-status-report>
    <completed-tasks>
      <task id="analyze_a" name="分析模块A" duration-ms="45000">
        <result>发现3个循环依赖，建议重构</result>
        <artifacts>
          <artifact id="dep_graph_a" type="dependency_graph"/>
        </artifacts>
      </task>
      <task id="analyze_b" name="分析模块B" duration-ms="38000">
        <result>测试覆盖率85%，达到标准</result>
        <artifacts>
          <artifact id="coverage_report_b" type="coverage_report"/>
        </artifacts>
      </task>
    </completed-tasks>
    
    <interrupted-tasks>
      <task id="analyze_c" name="分析模块C" progress="3/5" duration-ms="37000">
        <last-observation>正在分析第3个性能瓶颈点...</last-observation>
        <recent-findings>
          <finding>发现2个潜在的内存泄漏点</finding>
          <finding>数据库查询平均耗时&gt;500ms</finding>
        </recent-findings>
        <partial-artifacts>
          <artifact id="perf_partial_c" type="partial_performance_report"/>
        </partial-artifacts>
      </task>
      <task id="analyze_d" name="分析模块D" progress="2/4" duration-ms="12000">
        <last-observation>已统计src目录，正在统计tests...</last-observation>
        <partial-result>代码行数：src/ 约1500行</partial-result>
      </task>
    </interrupted-tasks>
  </task-status-report>
  
</agent-response>
```

### 对应的 Rust 结构

```rust
/// 系统通知/提示块
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename = "system-notice")]
pub struct SystemNotice {
    #[serde(rename = "@type")]
    pub notice_type: String,  // "time_budget_exceeded"
    
    #[serde(rename = "@priority")]
    pub priority: String,  // "critical"
    
    #[serde(rename = "message")]
    pub message: String,
    
    #[serde(rename = "metadata")]
    pub metadata: NoticeMetadata,
    
    #[serde(rename = "guidance")]
    pub guidance: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct NoticeMetadata {
    #[serde(rename = "time-budget-ms")]
    pub time_budget_ms: u64,
    
    #[serde(rename = "elapsed-ms")]
    pub elapsed_ms: u64,
    
    #[serde(rename = "completed-tasks")]
    pub completed_tasks: usize,
    
    #[serde(rename = "interrupted-tasks")]
    pub interrupted_tasks: usize,
}

/// 任务状态报告
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename = "task-status-report")]
pub struct TaskStatusReport {
    #[serde(rename = "completed-tasks")]
    pub completed: CompletedTasks,
    
    #[serde(rename = "interrupted-tasks")]
    pub interrupted: InterruptedTasks,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CompletedTasks {
    #[serde(rename = "task")]
    pub tasks: Vec<CompletedTaskReport>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CompletedTaskReport {
    #[serde(rename = "@id")]
    pub id: String,
    
    #[serde(rename = "@name")]
    pub name: String,
    
    #[serde(rename = "@duration-ms")]
    pub duration_ms: u64,
    
    #[serde(rename = "result")]
    pub result: String,
    
    #[serde(rename = "artifacts")]
    pub artifacts: Vec<ArtifactRef>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InterruptedTasks {
    #[serde(rename = "task")]
    pub tasks: Vec<InterruptedTaskReport>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct InterruptedTaskReport {
    #[serde(rename = "@id")]
    pub id: String,
    
    #[serde(rename = "@name")]
    pub name: String,
    
    #[serde(rename = "@progress")]
    pub progress: String,  // "3/5"
    
    #[serde(rename = "@duration-ms")]
    pub duration_ms: u64,
    
    #[serde(rename = "last-observation")]
    pub last_observation: String,
    
    #[serde(rename = "recent-findings")]
    pub recent_findings: Vec<String>,
    
    #[serde(rename = "partial-result", skip_serializing_if = "Option::is_none")]
    pub partial_result: Option<String>,
}
```

---

## 对 Prime/Host 的指导

在系统提示中明确告知 LLM 如何处理部分结果：

```markdown
## 处理 Time Budget 强制返回的结果

当收到带有 `<system-notice type="time_budget_exceeded">` 的响应时：

### DO（应该做）：
1. ✅ 基于已完成任务给出准确的总结
2. ✅ 明确告知用户哪些任务未完成
3. ✅ 报告部分完成任务的当前进度和发现
4. ✅ 建议是否需要延长时间重新执行
5. ✅ 使用谨慎的语言（"初步分析显示..."）

### DON'T（不要做）：
1. ❌ 不要假设未完成任务的最终结果
2. ❌ 不要忽略 `<interrupted-tasks>` 中的部分发现
3. ❌ 不要表现得像所有任务都已完成
4. ❌ 不要在未完成任务上给出确定性的结论

### 建议模板：
"基于已完成的 X 个任务，我发现... 
对于未完成的 Y 个任务（已完成 Z%），初步观察显示...
建议：如需完整分析，可以[延长时间/分批处理/调整优先级]"
```

---

## 实施更新

### 文件更新

```
kernel-v2/src/scheduler/
├── batch_task_executor_v2.rs      # 更新：添加 Time Budget 机制
├── time_budget_monitor.rs          # 新增：时间预算监控器
├── snapshot_collector.rs           # 新增：任务快照收集器
├── xml_models.rs                   # 更新：添加 SystemNotice 等结构
└── ...
```

### 核心变更点

1. **BatchTaskExecutor.execute_batch()** - 添加超时控制
   - 使用 `tokio::select!` 或 `timeout` 组合
   - 时间到时触发 graceful shutdown

2. **新增 TimeBudgetMonitor** - 监控时间预算
   - 周期性检查剩余时间
   - 达到警告阈值时发送信号

3. **新增 TaskSnapshotCollector** - 收集部分结果
   - 从运行中的任务提取状态
   - 保留最近N轮观察

4. **更新 XML 结构** - 添加系统提示块
   - `SystemNotice` 结构
   - `TaskStatusReport` 结构

这个方案是否更符合你的需求？