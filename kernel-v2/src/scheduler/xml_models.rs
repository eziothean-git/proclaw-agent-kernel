//! XML Output Models - SEE-ACT-UPDATE 结构的 XML 输出模型
//!
//! 定义 Agent 响应的 XML Schema，支持三个核心部分：
//! 1. reasoning: 观察、思考、计划
//! 2. explanation: 给用户的解释
//! 3. actions: 执行的动作（工具调用）

use serde::{Deserialize, Serialize};

/// Agent 响应根结构
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename = "agent-response")]
pub struct AgentResponse {
    #[serde(rename = "@version", default = "default_version")]
    pub version: String,

    #[serde(rename = "@xmlns", default = "default_namespace")]
    pub namespace: String,

    #[serde(rename = "reasoning")]
    pub reasoning: Reasoning,

    #[serde(rename = "explanation")]
    pub explanation: String,

    #[serde(rename = "actions")]
    pub actions: Actions,

    #[serde(rename = "state-update", skip_serializing_if = "Option::is_none")]
    pub state_update: Option<StateUpdate>,
}

impl AgentResponse {
    pub fn new(reasoning: Reasoning, explanation: String, actions: Actions) -> Self {
        Self {
            version: default_version(),
            namespace: default_namespace(),
            reasoning,
            explanation,
            actions,
            state_update: None,
        }
    }

    pub fn with_state_update(mut self, state_update: StateUpdate) -> Self {
        self.state_update = Some(state_update);
        self
    }

    pub fn with_time_budget_notice(self, _notice: SystemNotice) -> Self {
        self
    }
}

fn default_version() -> String {
    "1.0".to_string()
}

fn default_namespace() -> String {
    "http://proclaw.ai/response".to_string()
}

/// 推理部分 - SEE 阶段的内容
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Reasoning {
    #[serde(rename = "observation")]
    pub observation: String,

    #[serde(rename = "thought")]
    pub thought: String,

    #[serde(rename = "plan")]
    pub plan: Plan,
}

impl Reasoning {
    pub fn new(observation: impl Into<String>, thought: impl Into<String>, plan: Plan) -> Self {
        Self {
            observation: observation.into(),
            thought: thought.into(),
            plan,
        }
    }
}

/// 执行计划
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Plan {
    #[serde(rename = "step")]
    pub steps: Vec<PlanStep>,
}

impl Plan {
    pub fn new(steps: Vec<PlanStep>) -> Self {
        Self { steps }
    }

    pub fn single(description: impl Into<String>) -> Self {
        Self {
            steps: vec![PlanStep::new(1, description)],
        }
    }
}

/// 计划步骤
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct PlanStep {
    #[serde(rename = "@order")]
    pub order: u32,

    #[serde(rename = "$text")]
    pub description: String,
}

impl PlanStep {
    pub fn new(order: u32, description: impl Into<String>) -> Self {
        Self {
            order,
            description: description.into(),
        }
    }
}

/// 动作集合
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Actions {
    #[serde(rename = "action")]
    pub actions: Vec<Action>,
}

impl Actions {
    pub fn new(actions: Vec<Action>) -> Self {
        Self { actions }
    }

    pub fn empty() -> Self {
        Self { actions: vec![] }
    }

    pub fn single(action: Action) -> Self {
        Self { actions: vec![action] }
    }
}

/// 单个动作
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(tag = "@type")]
pub enum Action {
    #[serde(rename = "tool_call")]
    ToolCall {
        #[serde(rename = "@id")]
        id: String,

        #[serde(rename = "skill")]
        skill: SkillRef,

        #[serde(rename = "tool")]
        tool: ToolRef,

        #[serde(rename = "parameters")]
        parameters: Parameters,

        #[serde(rename = "metadata", skip_serializing_if = "Option::is_none")]
        metadata: Option<ActionMetadata>,
    },

    #[serde(rename = "phase_transition")]
    PhaseTransition {
        #[serde(rename = "@id")]
        id: String,

        #[serde(rename = "from")]
        from_phase: String,

        #[serde(rename = "to")]
        to_phase: String,

        #[serde(rename = "reason", skip_serializing_if = "Option::is_none")]
        reason: Option<String>,
    },
}

impl Action {
    pub fn tool_call(
        id: impl Into<String>,
        skill_name: impl Into<String>,
        tool_name: impl Into<String>,
        parameters: Parameters,
    ) -> Self {
        Self::ToolCall {
            id: id.into(),
            skill: SkillRef::new(skill_name),
            tool: ToolRef::new(tool_name),
            parameters,
            metadata: None,
        }
    }

    pub fn with_metadata(mut self, reasoning: impl Into<String>) -> Self {
        if let Self::ToolCall { metadata, .. } = &mut self {
            *metadata = Some(ActionMetadata::new(reasoning));
        }
        self
    }
}

/// Skill 引用
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct SkillRef {
    #[serde(rename = "@name")]
    pub name: String,
}

impl SkillRef {
    pub fn new(name: impl Into<String>) -> Self {
        Self { name: name.into() }
    }
}

/// Tool 引用
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ToolRef {
    #[serde(rename = "@name")]
    pub name: String,
}

impl ToolRef {
    pub fn new(name: impl Into<String>) -> Self {
        Self { name: name.into() }
    }
}

/// 参数集合
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Parameters {
    #[serde(rename = "param")]
    pub params: Vec<Param>,
}

impl Parameters {
    pub fn new(params: Vec<Param>) -> Self {
        Self { params }
    }

    pub fn from_map(map: std::collections::HashMap<String, String>) -> Self {
        let params = map
            .into_iter()
            .map(|(name, value)| Param::new(name, value))
            .collect();
        Self { params }
    }

    pub fn single(name: impl Into<String>, value: impl Into<String>) -> Self {
        Self {
            params: vec![Param::new(name, value)],
        }
    }
}

/// 单个参数
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Param {
    #[serde(rename = "@name")]
    pub name: String,

    #[serde(rename = "$text")]
    pub value: String,
}

impl Param {
    pub fn new(name: impl Into<String>, value: impl Into<String>) -> Self {
        Self {
            name: name.into(),
            value: value.into(),
        }
    }
}

/// 动作元数据
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ActionMetadata {
    #[serde(rename = "reasoning")]
    pub reasoning: String,

    #[serde(rename = "expected_output", skip_serializing_if = "Option::is_none")]
    pub expected_output: Option<String>,
}

impl ActionMetadata {
    pub fn new(reasoning: impl Into<String>) -> Self {
        Self {
            reasoning: reasoning.into(),
            expected_output: None,
        }
    }

    pub fn with_expected_output(mut self, output: impl Into<String>) -> Self {
        self.expected_output = Some(output.into());
        self
    }
}

/// 状态更新（UPDATE 阶段）
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct StateUpdate {
    #[serde(rename = "phase", skip_serializing_if = "Option::is_none")]
    pub phase: Option<PhaseTransition>,

    #[serde(rename = "artifacts", skip_serializing_if = "Option::is_none")]
    pub artifacts: Option<Artifacts>,
}

impl StateUpdate {
    pub fn new() -> Self {
        Self {
            phase: None,
            artifacts: None,
        }
    }

    pub fn with_phase_transition(
        mut self,
        from: impl Into<String>,
        to: impl Into<String>,
    ) -> Self {
        self.phase = Some(PhaseTransition {
            from_phase: from.into(),
            to_phase: to.into(),
        });
        self
    }

    pub fn with_artifacts(mut self, artifacts: Artifacts) -> Self {
        self.artifacts = Some(artifacts);
        self
    }
}

/// Phase 转换
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct PhaseTransition {
    #[serde(rename = "@from")]
    pub from_phase: String,

    #[serde(rename = "@to")]
    pub to_phase: String,
}

/// Artifact 集合
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Artifacts {
    #[serde(rename = "artifact")]
    pub artifacts: Vec<ArtifactRef>,
}

impl Artifacts {
    pub fn new(artifacts: Vec<ArtifactRef>) -> Self {
        Self { artifacts }
    }

    pub fn single(artifact_type: impl Into<String>, id: impl Into<String>) -> Self {
        Self {
            artifacts: vec![ArtifactRef::new(artifact_type, id)],
        }
    }
}

/// Artifact 引用
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ArtifactRef {
    #[serde(rename = "@type")]
    pub artifact_type: String,

    #[serde(rename = "@id")]
    pub id: String,
}

impl ArtifactRef {
    pub fn new(artifact_type: impl Into<String>, id: impl Into<String>) -> Self {
        Self {
            artifact_type: artifact_type.into(),
            id: id.into(),
        }
    }
}

/// System notice for time budget exceeded
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename = "system-notice")]
pub struct SystemNotice {
    #[serde(rename = "@type")]
    pub notice_type: String,

    #[serde(rename = "@priority")]
    pub priority: String,

    #[serde(rename = "message")]
    pub message: String,

    #[serde(rename = "metadata")]
    pub metadata: NoticeMetadata,

    #[serde(rename = "guidance")]
    pub guidance: String,
}

impl SystemNotice {
    pub fn time_budget_exceeded(
        time_budget_ms: u64,
        elapsed_ms: u64,
        completed_tasks: usize,
        interrupted_tasks: usize,
    ) -> Self {
        Self {
            notice_type: "time_budget_exceeded".to_string(),
            priority: "critical".to_string(),
            message: format!(
                "Time budget exhausted: {}ms / {}ms. \
                 Results are partial, some tasks were interrupted.",
                elapsed_ms, time_budget_ms
            ),
            metadata: NoticeMetadata {
                time_budget_ms,
                elapsed_ms,
                completed_tasks,
                interrupted_tasks,
            },
            guidance: "Handle partial results carefully. \
                      Report completed tasks accurately. \
                      Suggest whether to extend time for incomplete tasks."
                .to_string(),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
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

/// Task status report for batch execution results
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename = "task-status-report")]
pub struct TaskStatusReport {
    #[serde(rename = "completed-tasks")]
    pub completed: CompletedTasks,

    #[serde(rename = "interrupted-tasks")]
    pub interrupted: InterruptedTasks,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct CompletedTasks {
    #[serde(rename = "task")]
    pub tasks: Vec<CompletedTaskReport>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
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

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct InterruptedTasks {
    #[serde(rename = "task")]
    pub tasks: Vec<InterruptedTaskReport>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct InterruptedTaskReport {
    #[serde(rename = "@id")]
    pub id: String,

    #[serde(rename = "@name")]
    pub name: String,

    #[serde(rename = "@progress")]
    pub progress: String,

    #[serde(rename = "@duration-ms")]
    pub duration_ms: u64,

    #[serde(rename = "last-observation")]
    pub last_observation: String,

    #[serde(rename = "recent-findings")]
    pub recent_findings: Vec<String>,

    #[serde(rename = "partial-result", skip_serializing_if = "Option::is_none")]
    pub partial_result: Option<String>,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_serialize_response() {
        let response = AgentResponse::new(
            Reasoning::new(
                "User asked to read file",
                "I should use bash skill",
                Plan::single("Read the file"),
            ),
            "I'll read that file for you".to_string(),
            Actions::single(Action::tool_call(
                "act_001",
                "bash",
                "execute",
                Parameters::single("command", "cat /etc/hosts"),
            )),
        );

        let xml = quick_xml::se::to_string(&response).unwrap();
        assert!(xml.contains("agent-response"));
        assert!(xml.contains("reasoning"));
        assert!(xml.contains("explanation"));
        assert!(xml.contains("actions"));
    }

    #[test]
    fn test_roundtrip() {
        let original = AgentResponse::new(
            Reasoning::new(
                "Test observation",
                "Test thought",
                Plan::new(vec![
                    PlanStep::new(1, "Step 1"),
                    PlanStep::new(2, "Step 2"),
                ]),
            ),
            "Test explanation".to_string(),
            Actions::empty(),
        );

        let xml = quick_xml::se::to_string(&original).unwrap();
        let parsed: AgentResponse = quick_xml::de::from_str(&xml).unwrap();

        assert_eq!(original.reasoning.observation, parsed.reasoning.observation);
        assert_eq!(original.explanation, parsed.explanation);
    }

    #[test]
    fn test_system_notice_serialization() {
        let notice = SystemNotice::time_budget_exceeded(
            120_000,
            120_050,
            2,
            2,
        );

        let xml = quick_xml::se::to_string(&notice).unwrap();
        assert!(xml.contains("system-notice"));
        assert!(xml.contains("time_budget_exceeded"));
        assert!(xml.contains("120000"));
        assert!(xml.contains("2"));
    }

    #[test]
    fn test_task_status_report() {
        let report = TaskStatusReport {
            completed: CompletedTasks {
                tasks: vec![CompletedTaskReport {
                    id: "task_1".to_string(),
                    name: "Test Task".to_string(),
                    duration_ms: 5000,
                    result: "Success".to_string(),
                    artifacts: vec![],
                }],
            },
            interrupted: InterruptedTasks {
                tasks: vec![InterruptedTaskReport {
                    id: "task_2".to_string(),
                    name: "Interrupted Task".to_string(),
                    progress: "3/5".to_string(),
                    duration_ms: 3000,
                    last_observation: "In progress".to_string(),
                    recent_findings: vec!["Finding 1".to_string()],
                    partial_result: Some("Partial".to_string()),
                }],
            },
        };

        let xml = quick_xml::se::to_string(&report).unwrap();
        assert!(xml.contains("task-status-report"));
        assert!(xml.contains("completed-tasks"));
        assert!(xml.contains("interrupted-tasks"));
    }
}
