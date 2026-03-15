# 批处理多任务并行执行方案

## 问题分析

用户提出两个关键需求：
1. **批处理汇总**：所有子任务完成后统一丢到下一轮 context
2. **防堵塞机制**：防止子任务循环造成堵塞

## 架构设计：Map-Reduce + 批处理汇总

### 核心流程

```
Prime/Host
    │
    ▼ 发起批处理请求
BatchTaskExecutor
    │
    ├─► 子任务1 ──┐
    ├─► 子任务2 ──┤ 并行执行（带超时/深度限制）
    ├─► 子任务3 ──┤
    └─► 子任务4 ──┘
    │
    ▼ 等待全部完成
结果汇总器
    │
    ▼ 生成 AggregatedContext
下一轮 Prime/Host
```

### 关键特性

| 特性 | 说明 |
|------|------|
| **并行执行** | 使用信号量限制并发数（默认5个） |
| **超时控制** | 每个子任务独立超时（默认120秒） |
| **深度限制** | 防止递归循环（默认最大深度3） |
| **步数限制** | 单任务最大步数（默认50步） |
| **结果汇总** | 多模式汇总：简单列表/结构化报告/智能摘要 |

---

## 组件设计

### 1. BatchTaskExecutor（批处理执行器）

**职责**：协调多个子任务的并行执行并汇总结果

```rust
pub struct BatchTaskExecutor {
    coordinator: Arc<ExecutionCoordinator>,
    llm_router: Arc<LLMRouter>,
    // ... 其他依赖
}

impl BatchTaskExecutor {
    /// 执行一批子任务
    pub async fn execute_batch(
        &self,
        parent_session_id: String,
        sub_tasks: Vec<SubTaskRequest>,
        config: BatchConfig,
    ) -> Result<BatchExecutionResult> {
        // 1. 验证子任务（深度检查）
        // 2. 使用信号量限制并发
        // 3. 并行执行所有子任务
        // 4. 等待全部完成（带全局超时）
        // 5. 汇总结果
        // 6. 生成 XML 报告
    }
}
```

**配置选项**：

```rust
pub struct BatchConfig {
    pub max_parallel_tasks: usize,      // 最大并行数（默认5）
    pub task_timeout_seconds: u64,      // 单任务超时（默认120s）
    pub max_steps_per_task: usize,      // 单任务最大步数（默认50）
    pub max_depth: u32,                 // 最大递归深度（默认3）
    pub require_all_success: bool,      // 是否要求全部成功
    pub aggregation_mode: AggregationMode, // 汇总模式
}
```

### 2. SubTaskExecutor（子任务执行器）

**职责**：执行单个独立的子任务

**防堵塞机制**：
1. **超时控制**：使用 `tokio::time::timeout`
2. **深度限制**：检查 `sub_task.depth > config.max_depth`
3. **步数限制**：在 ThreadExecutor 中限制 `max_steps`
4. **循环检测**：通过 `parent_task_id` 链追踪依赖

### 3. 结果汇总器

**汇总模式**：

| 模式 | 适用场景 | 输出格式 |
|------|----------|----------|
| `SimpleList` | 快速预览 | 简单列表 |
| `StructuredReport` | 标准场景 | 结构化报告 |
| `MergeArtifacts` | 需要合并 artifacts | 合并后的 artifacts |
| `SmartSummary` | 复杂场景 | LLM 生成的智能摘要 |

**AggregatedContext 结构**：

```rust
pub struct AggregatedContext {
    pub overview: TaskOverview,              // 执行概览
    pub successful_results: Vec<SubTaskSummary>,  // 成功任务
    pub failed_results: Vec<SubTaskSummary>,      // 失败任务
    pub key_findings: Vec<String>,          // 关键发现
    pub merged_artifacts: Vec<ArtifactSummary>,   // 合并的 artifacts
    pub recommended_next_steps: Vec<String>, // 推荐下一步
}

pub struct TaskOverview {
    pub total_tasks: usize,
    pub successful_count: usize,
    pub failed_count: usize,
    pub timeout_count: usize,
    pub total_execution_time_ms: u64,
    pub parallel_efficiency: f32,  // 并行效率指标
}
```

---

## 防堵塞机制详解

### 1. 超时控制（多层）

```rust
// 全局超时：所有任务必须在 N 秒内完成
let global_timeout = config.task_timeout_seconds * sub_tasks.len();

let results = match timeout(
    Duration::from_secs(global_timeout),
    futures::future::join_all(handles),
).await {
    Ok(results) => results,
    Err(_) => {
        warn!("Batch execution timeout");
        // 取消还在运行的任务
        // 返回部分结果
    }
};
```

### 2. 深度限制

```rust
fn validate_sub_tasks(&self, sub_tasks: &[SubTaskRequest]) -> Result<()> {
    for task in sub_tasks {
        if task.depth > config.max_depth {
            return Err(format!(
                "Task {} exceeds max depth: {} > {}",
                task.task_id, task.depth, config.max_depth
            ));
        }
    }
}
```

### 3. 循环检测

```rust
// 通过 parent_task_id 链追踪
fn detect_cycle(task: &SubTaskRequest, all_tasks: &[SubTaskRequest]) -> bool {
    let mut current = task.parent_task_id.clone();
    let mut visited = HashSet::new();
    
    while let Some(parent_id) = current {
        if !visited.insert(parent_id.clone()) {
            return true; // 发现循环
        }
        current = all_tasks
            .iter()
            .find(|t| t.task_id == parent_id)
            .and_then(|t| t.parent_task_id.clone());
    }
    false
}
```

---

## 与现有系统集成

### 1. 在 ThreadExecutor 中使用

```rust
// scheduler/thread_executor.rs

async fn execute_step(&mut self) -> Result<bool> {
    // ... 现有代码 ...
    
    // 检测是否需要批处理（通过特殊 intent 或配置）
    if intent.intent_type == IntentType::BatchExecution {
        let batch_executor = BatchTaskExecutor::new(
            self.coordinator.clone(),
            self.llm_router.clone(),
            // ...
        );
        
        let sub_tasks = convert_processes_to_sub_tasks(intent.processes);
        
        let batch_result = batch_executor.execute_batch(
            self.session_id.clone(),
            sub_tasks,
            BatchConfig::default(),
        ).await?;
        
        // 将汇总结果存入 context，供下一轮使用
        self.storage.save_artifact(&ArtifactSlot::new(
            ArtifactType::BatchResult,
            serde_json::json!({
                "aggregated_context": batch_result.aggregated_context,
                "xml_report": batch_result.xml_report,
            }),
            10,
            self.current_step,
        )).await?;
        
        // 不立即返回结果，而是继续执行（结果在下一轮可用）
        return Ok(true);
    }
    
    // ... 现有代码 ...
}
```

### 2. Prime/Host 如何使用

**Prime 发起批处理**：

```json
{
  "intent": "batch_execution",
  "goals": ["并行分析多个模块"],
  "processes": [
    {"name": "analyze_module_a", "goal": "分析模块A"},
    {"name": "analyze_module_b", "goal": "分析模块B"},
    {"name": "analyze_module_c", "goal": "分析模块C"}
  ],
  "content": {
    "text": "我将并行分析三个模块..."
  }
}
```

**下一轮 Prime 接收汇总结果**：

```xml
<context>
  <batch_result batch_id="batch_abc123">
    <overview>
      <total_tasks>3</total_tasks>
      <successful>3</successful>
      <failed>0</failed>
      <parallel_efficiency>2.8x</parallel_efficiency>
    </overview>
    <successful_results>
      <task name="analyze_module_a">
        <finding>模块A存在循环依赖</finding>
      </task>
      <task name="analyze_module_b">
        <finding>模块B代码覆盖率90%</finding>
      </task>
      <task name="analyze_module_c">
        <finding>模块C需要重构</finding>
      </task>
    </successful_results>
    <recommended_next_steps>
      <step>1. 修复模块A的循环依赖</step>
      <step>2. 为模块C制定重构计划</step>
    </recommended_next_steps>
  </batch_result>
</context>
```

---

## XML 结构扩展

为支持批处理，扩展 XML Schema：

```xml
<agent-response>
  <reasoning>
    <observation>需要并行分析3个模块</observation>
    <thought>这些模块相互独立，可以并行执行</thought>
    <plan>
      <step order="1">启动批处理执行</step>
    </plan>
  </reasoning>
  
  <explanation>我将并行分析三个模块...</explanation>
  
  <actions>
    <!-- 特殊的批处理动作 -->
    <action type="batch_execute" id="batch_001">
      <config>
        <max_parallel>3</max_parallel>
        <timeout>120</timeout>
      </config>
      <sub_tasks>
        <task id="task_001" process="analyze_module_a"/>
        <task id="task_002" process="analyze_module_b"/>
        <task id="task_003" process="analyze_module_c"/>
      </sub_tasks>
    </action>
  </actions>
</agent-response>
```

---

## 实施步骤

### Phase 1: 基础批处理执行器

1. **创建文件** `scheduler/batch_task_executor.rs`
   - [ ] `BatchTaskExecutor` 结构
   - [ ] `BatchConfig` 配置
   - [ ] `execute_batch()` 方法
   - [ ] 基础结果汇总

2. **创建文件** `scheduler/sub_task_executor.rs`
   - [ ] `SubTaskExecutor` 结构
   - [ ] 单任务执行逻辑
   - [ ] 超时控制

### Phase 2: 防堵塞机制

3. **实现验证逻辑**
   - [ ] 深度限制检查
   - [ ] 循环依赖检测
   - [ ] 步数限制

4. **完善超时机制**
   - [ ] 单任务超时
   - [ ] 全局批处理超时
   - [ ] 优雅取消

### Phase 3: 结果汇总

5. **实现汇总器**
   - [ ] `SimpleList` 模式
   - [ ] `StructuredReport` 模式
   - [ ] XML 报告生成

6. **Context 转换**
   - [ ] `IntoNextRoundContext` trait
   - [ ] Prime/Host 可读格式

### Phase 4: 集成

7. **修改 ThreadExecutor**
   - [ ] 检测 `BatchExecution` intent
   - [ ] 调用 `BatchTaskExecutor`
   - [ ] 存储结果到 artifact

8. **系统提示词更新**
   - [ ] 添加批处理使用说明
   - [ ] 示例：何时使用批处理

---

## 使用示例

### 场景：并行代码分析

**Round 1 - Prime 发起批处理**：

```xml
<agent-response>
  <reasoning>
    <observation>用户要求分析大型项目的三个核心模块</observation>
    <thought>三个模块相互独立，适合并行分析以提高效率</thought>
    <plan>
      <step order="1">并行分析模块A、B、C</step>
      <step order="2">汇总分析结果</step>
      <step order="3">提供综合建议</step>
    </plan>
  </reasoning>
  
  <explanation>我将同时分析三个模块，这样更快...</explanation>
  
  <actions>
    <action type="batch_execute" id="batch_analysis">
      <config max_parallel="3" timeout="60"/>
      <sub_tasks>
        <task id="analyze_a" goal="分析模块A的代码质量和依赖"/>
        <task id="analyze_b" goal="分析模块B的测试覆盖"/>
        <task id="analyze_c" goal="分析模块C的性能瓶颈"/>
      </sub_tasks>
    </action>
  </actions>
</agent-response>
```

**Round 2 - Prime 接收汇总结果并决策**：

```xml
<context>
  <previous_batch_result>
    <overview parallel_efficiency="2.9x" total_time="65s"/>
    <results>
      <success task="analyze_a">发现3个循环依赖</success>
      <success task="analyze_b">测试覆盖率85%</success>
      <success task="analyze_c">发现2个性能瓶颈</success>
    </results>
  </previous_batch_result>
</context>

<agent-response>
  <reasoning>
    <observation>批处理完成，三个模块分析结果已汇总</observation>
    <thought>基于分析结果，我应该优先处理循环依赖...</thought>
  </reasoning>
  
  <explanation>分析完成！发现以下问题：
  1. 模块A有循环依赖需要修复
  2. 模块B测试覆盖率良好
  3. 模块C需要性能优化
  
  建议先修复模块A的依赖问题...</explanation>
  
  <actions>
    <action type="tool_call" id="fix_deps">
      <skill name="code"/>
      <tool name="refactor"/>
      <parameters>
        <param name="target">module_a</param>
        <param name="issue">circular_dependency</param>
      </parameters>
    </action>
  </actions>
</agent-response>
```

---

## 优势总结

| 优势 | 说明 |
|------|------|
| **效率提升** | 并行执行减少总耗时（parallel_efficiency 指标） |
| **资源控制** | 信号量限制并发，防止资源耗尽 |
| **防堵塞** | 多层超时+深度限制，保证系统稳定 |
| **结果复用** | 汇总后的 Context 可被 Prime/Host 复用 |
| **可追溯** | 完整的执行记录和 XML 报告 |
| **灵活配置** | 多种汇总模式适应不同场景 |

---

## 文件清单

需要创建/修改的文件：

```
kernel-v2/src/scheduler/
├── batch_task_executor.rs      # 批处理执行器（新增）
├── sub_task_executor.rs        # 子任务执行器（新增）
├── mod.rs                      # 导出新模块（修改）
└── thread_executor.rs          # 集成批处理（修改）

data/prompts/xml/
└── batch-execution-guide.md    # 批处理使用指南（新增）
```

---

这个方案解决了：
1. ✅ **批处理汇总**：所有子任务完成后统一生成 AggregatedContext
2. ✅ **复用性**：汇总结果可直接用于下一轮 Prime/Host
3. ✅ **防堵塞**：超时+深度限制+步数限制三层防护
4. ✅ **并行效率**：信号量控制并发，提供效率指标

是否开始实施？