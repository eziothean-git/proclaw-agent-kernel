//! Agent Thread 数据模型

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// Thread 唯一标识
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct ThreadId(pub String);

impl ThreadId {
    pub fn new() -> Self {
        Self(uuid::Uuid::new_v4().to_string())
    }
}

impl Default for ThreadId {
    fn default() -> Self {
        Self::new()
    }
}

/// Executor 唯一标识
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct ExecutorId(pub String);

impl ExecutorId {
    pub fn new() -> Self {
        Self(uuid::Uuid::new_v4().to_string())
    }
}

/// Session 标识
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub struct SessionId(pub String);

/// 执行阶段
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ExecutionPhase {
    Explore,   // 探索阶段：收集信息
    Execute,   // 执行阶段：执行动作
    Complete,  // 完成阶段：整理结果
}

impl Default for ExecutionPhase {
    fn default() -> Self {
        ExecutionPhase::Explore
    }
}

/// Thread 元数据
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ThreadMeta {
    pub thread_id: ThreadId,
    pub session_id: SessionId,
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
    pub current_phase: ExecutionPhase,
    pub step_count: usize,
    pub status: ThreadStatus,
}

impl ThreadMeta {
    pub fn new(thread_id: ThreadId, session_id: SessionId) -> Self {
        let now = Utc::now();
        Self {
            thread_id,
            session_id,
            created_at: now,
            updated_at: now,
            current_phase: ExecutionPhase::default(),
            step_count: 0,
            status: ThreadStatus::Created,
        }
    }
}

/// Thread 状态
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ThreadStatus {
    Created,     // 已创建
    Active,      // 有 Executor 在执行
    Paused,      // 已暂停
    Completed,   // 已完成
    Error,       // 出错
}

/// 不可变输入（来自 Context Compiler）
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ImmutableInput {
    pub task_goal: String,
    pub constraints: Vec<String>,
    pub allowed_capabilities: Vec<String>,
    pub forbidden_capabilities: Vec<String>,
    pub session_context: HashMap<String, serde_json::Value>,
    pub compiled_at: DateTime<Utc>,
}

/// Event 类型
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum EventType {
    StepStart,       // 步骤开始
    ToolCall,        // 工具调用
    ToolResult,      // 工具结果
    Observation,     // 观察
    PhaseChange,     // 阶段切换
    Error,           // 错误
    Completed,       // 完成
}

/// Event 记录（存储在 JSON Lines 中）
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Event {
    pub event_id: String,
    pub timestamp: DateTime<Utc>,
    pub event_type: EventType,
    pub step_number: usize,
    pub phase: ExecutionPhase,
    pub content: serde_json::Value,
    pub metadata: HashMap<String, serde_json::Value>,
}

impl Event {
    pub fn new(
        event_type: EventType,
        step_number: usize,
        phase: ExecutionPhase,
        content: serde_json::Value,
    ) -> Self {
        Self {
            event_id: uuid::Uuid::new_v4().to_string(),
            timestamp: Utc::now(),
            event_type,
            step_number,
            phase,
            content,
            metadata: HashMap::new(),
        }
    }
    
    /// 转换为单行 JSON（用于 JSON Lines）
    pub fn to_json_line(&self) -> anyhow::Result<String> {
        Ok(serde_json::to_string(self)?)
    }
    
    /// 从 JSON Line 解析
    pub fn from_json_line(line: &str) -> anyhow::Result<Self> {
        Ok(serde_json::from_str(line)?)
    }
}

/// Artifact 类型
#[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ArtifactType {
    ModuleMap,          // 模块映射
    SymbolIndex,        // 符号索引
    ContextReport,      // 上下文报告
    FileTree,           // 文件树
    PatchPlan,          // 补丁计划
    DependencySummary,  // 依赖摘要
    TestPlan,           // 测试计划
    VerificationResult, // 验证结果
    FinalResult,        // 最终结果
    Summary,            // 摘要
    NextSteps,          // 下一步
    Custom(String),     // 自定义类型
}

/// Artifact 槽位
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ArtifactSlot {
    pub slot_id: String,
    pub artifact_type: ArtifactType,
    pub content: serde_json::Value,
    pub priority: i32,  // 1-10，用于 Working Set Builder 选择
    pub created_at: DateTime<Utc>,
    pub updated_at: DateTime<Utc>,
    pub step_number: usize,  // 在哪个步骤创建的
}

impl ArtifactSlot {
    pub fn new(
        artifact_type: ArtifactType,
        content: serde_json::Value,
        priority: i32,
        step_number: usize,
    ) -> Self {
        let now = Utc::now();
        Self {
            slot_id: uuid::Uuid::new_v4().to_string(),
            artifact_type,
            content,
            priority,
            created_at: now,
            updated_at: now,
            step_number,
        }
    }
}

/// Thread 历史快照（用于 Context Builder）
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ThreadSnapshot {
    pub thread_id: ThreadId,
    pub meta: ThreadMeta,
    pub immutable_input: ImmutableInput,
    pub recent_events: Vec<Event>,  // 最近 N 条事件
    pub artifacts: Vec<ArtifactSlot>,
    pub confirmed_facts: Vec<String>,
    pub pending_decisions: Vec<String>,
}

/// 执行摘要（用于返回给 Session Host）
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExecutionSummary {
    pub thread_id: ThreadId,
    pub executor_id: ExecutorId,
    pub steps_executed: usize,
    pub final_phase: ExecutionPhase,
    pub final_status: ThreadStatus,
    pub artifacts_produced: Vec<ArtifactType>,
    pub started_at: DateTime<Utc>,
    pub completed_at: DateTime<Utc>,
}