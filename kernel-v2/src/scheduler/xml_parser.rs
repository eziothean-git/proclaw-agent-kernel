use crate::agent_thread::models::ExecutionPhase;
use crate::scheduler::thread_executor::{
    IntentType, ParsedIntent, PhaseTransitionIntent, ToolCallIntent,
};
use crate::scheduler::xml_models::{
    Action, AgentResponse, Parameters,
};
use tracing::{debug, error};

pub struct XmlOutputParser;

impl XmlOutputParser {
    pub fn new() -> Self {
        Self
    }

    pub fn parse(&self, output: &str) -> anyhow::Result<AgentResponse> {
        let clean_xml = self.extract_xml_block(output);

        match quick_xml::de::from_str::<AgentResponse>(&clean_xml) {
            Ok(response) => {
                debug!("Successfully parsed XML response");
                Ok(response)
            }
            Err(e) => {
                error!("Failed to parse XML: {}", e);
                Err(anyhow::anyhow!("XML parse error: {}", e))
            }
        }
    }

    pub fn to_parsed_intent(
        &self,
        response: &AgentResponse,
        raw_output: &str,
    ) -> anyhow::Result<ParsedIntent> {
        let mut tool_calls = Vec::new();
        let mut phase_transition = None;

        for action in &response.actions.actions {
            match action {
                Action::ToolCall {
                    id: _,
                    skill,
                    tool,
                    parameters,
                    metadata,
                } => {
                    let params = self.params_to_json(parameters);
                    let reasoning = metadata
                        .as_ref()
                        .map(|m| m.reasoning.clone())
                        .unwrap_or_default();

                    tool_calls.push(ToolCallIntent {
                        skill_name: skill.name.clone(),
                        tool_name: tool.name.clone(),
                        parameters: params,
                        reasoning,
                    });
                }
                Action::PhaseTransition {
                    id: _,
                    from_phase,
                    to_phase,
                    reason,
                } => {
                    let from = self.parse_phase(from_phase)?;
                    let to = self.parse_phase(to_phase)?;
                    phase_transition = Some(PhaseTransitionIntent {
                        from_phase: from,
                        to_phase: to,
                        reason: reason.clone().unwrap_or_default(),
                        artifacts_to_finalize: vec![],
                    });
                }
            }
        }

        let intent_type = if !tool_calls.is_empty() {
            IntentType::ToolCall
        } else if phase_transition.is_some() {
            IntentType::PhaseTransition
        } else if !response.explanation.is_empty() {
            IntentType::FinalAnswer
        } else {
            IntentType::Error
        };

        let structured_data = match serde_json::to_value(response) {
            Ok(v) => v,
            Err(_) => serde_json::json!({}),
        };

        Ok(ParsedIntent {
            intent_type,
            confidence: 1.0,
            raw_content: raw_output.to_string(),
            structured_data,
            tool_calls,
            phase_transition,
            final_answer: Some(response.explanation.clone()),
            clarification_request: None,
            error_message: None,
            batch_tasks: None,
        })
    }

    fn extract_xml_block(&self, output: &str) -> String {
        if let Some(start) = output.find("```xml") {
            let content_start = start + 6;
            if let Some(end) = output[content_start..].find("```") {
                return output[content_start..content_start + end].trim().to_string();
            }
        }

        if let Some(start) = output.find("```") {
            let content_start = start + 3;
            if let Some(end) = output[content_start..].find("```") {
                let content = output[content_start..content_start + end].trim();
                if content.starts_with("<?xml") || content.starts_with("<agent-response") {
                    return content.to_string();
                }
            }
        }

        output.trim().to_string()
    }

    fn params_to_json(&self, params: &Parameters) -> serde_json::Value {
        let mut map = serde_json::Map::new();
        for param in &params.params {
            map.insert(
                param.name.clone(),
                serde_json::Value::String(param.value.clone()),
            );
        }
        serde_json::Value::Object(map)
    }

    fn parse_phase(&self, phase_str: &str) -> anyhow::Result<ExecutionPhase> {
        match phase_str.to_lowercase().as_str() {
            "explore" => Ok(ExecutionPhase::Explore),
            "execute" => Ok(ExecutionPhase::Execute),
            "complete" | "completed" => Ok(ExecutionPhase::Complete),
            _ => Err(anyhow::anyhow!("Unknown phase: {}", phase_str)),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::scheduler::xml_models::{
        Action, Actions, Plan, PlanStep, Reasoning, SkillRef, ToolRef,
    };

    #[test]
    #[ignore = "deprecated: XML is no longer the primary format, use JSON instead"]
    fn test_parse_simple_response() {
        let xml = r#"<?xml version="1.0" encoding="UTF-8"?>
<agent-response version="1.0" xmlns="http://proclaw.ai/response">
  <reasoning>
    <observation>User wants to read file</observation>
    <thought>I should use bash</thought>
    <plan>
      <step order="1">Read file</step>
    </plan>
  </reasoning>
  <explanation>I'll read that file</explanation>
  <actions>
    <action type="tool_call" id="act_001">
      <skill name="bash"/>
      <tool name="execute"/>
      <parameters>
        <param name="command">cat /etc/hosts</param>
      </parameters>
    </action>
  </actions>
</agent-response>"#;

        let parser = XmlOutputParser::new();
        let response = parser.parse(xml).unwrap();

        assert_eq!(response.reasoning.observation, "User wants to read file");
        assert_eq!(response.explanation, "I'll read that file");
        assert_eq!(response.actions.actions.len(), 1);
    }

    #[test]
    #[ignore = "deprecated: XML is no longer the primary format, use JSON instead"]
    fn test_extract_from_markdown() {
        let markdown = r#"Here's my response:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<agent-response version="1.0" xmlns="http://proclaw.ai/response">
  <reasoning>
    <observation>Test</observation>
    <thought>Test thought</thought>
    <plan>
      <step order="1">Test step</step>
    </plan>
  </reasoning>
  <explanation>Test explanation</explanation>
  <actions></actions>
</agent-response>
```

Hope that helps!"#;

        let parser = XmlOutputParser::new();
        let response = parser.parse(markdown).unwrap();

        assert_eq!(response.explanation, "Test explanation");
    }

    #[test]
    fn test_to_parsed_intent() {
        let response = AgentResponse::new(
            Reasoning::new(
                "Test observation",
                "Test thought",
                Plan::single("Test step"),
            ),
            "Test explanation".to_string(),
            Actions::single(Action::tool_call(
                "act_001",
                "bash",
                "execute",
                Parameters::single("command", "ls"),
            )),
        );

        let parser = XmlOutputParser::new();
        let intent = parser.to_parsed_intent(&response, "test output").unwrap();

        assert_eq!(intent.intent_type, IntentType::ToolCall);
        assert_eq!(intent.tool_calls.len(), 1);
        assert_eq!(intent.tool_calls[0].skill_name, "bash");
    }
}
