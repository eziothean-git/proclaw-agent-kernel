//! Output Parser - JSON优先格式解析器
//!
//! 优先解析JSON格式输出，fallback到XML格式

use tracing::{debug, warn};

use crate::agent_thread::models::ExecutionPhase;
use crate::scheduler::thread_executor::{IntentType, ParsedIntent, ToolCallIntent, PhaseTransitionIntent};
use crate::scheduler::xml_parser::XmlOutputParser;

/// Output Parser - JSON优先，XML fallback
pub struct OutputParser;

impl OutputParser {
    pub fn new() -> Self {
        Self
    }

    /// 解析 LLM 输出（优先JSON，fallback XML）
    pub fn parse(
        &self,
        output: &str,
        _current_phase: ExecutionPhase,
    ) -> anyhow::Result<ParsedIntent> {
        debug!("Parsing LLM output (len={}) - trying JSON first", output.len());

        // 首先尝试JSON解析
        if let Some(json_str) = self.extract_json(output) {
            debug!("Extracted JSON candidate (len={})", json_str.len());
            if let Ok(value) = serde_json::from_str::<serde_json::Value>(&json_str) {
                match self.parse_json_response(&value, output) {
                    Ok(intent) => {
                        debug!("Successfully parsed JSON response");
                        return Ok(intent);
                    }
                    Err(e) => {
                        warn!(error = %e, "JSON detected but parsing failed, trying XML fallback");
                    }
                }
            } else {
                debug!("Failed to parse extracted content as JSON");
            }
        } else {
            debug!("No JSON found in output");
        }

        // Fallback: 尝试XML解析
        debug!("Trying XML parser as fallback");
        let xml_parser = XmlOutputParser::new();
        match xml_parser.parse(output) {
            Ok(response) => {
                debug!("Successfully parsed XML response (fallback)");
                return xml_parser.to_parsed_intent(&response, output);
            }
            Err(e) => {
                warn!(error = %e, "Failed to parse XML, using fallback intent");
            }
        }

        // 最终fallback: 返回错误状态
        Ok(self.create_error_intent(output, "Failed to parse LLM output as JSON or XML"))
    }

    /// Extract JSON from response (handles markdown code blocks)
    fn extract_json(&self, output: &str) -> Option<String> {
        let trimmed = output.trim();

        // Try to find JSON in markdown code block
        if let Some(start) = trimmed.find("```json") {
            let content_start = start + 7;
            if let Some(end) = trimmed[content_start..].find("```") {
                return Some(trimmed[content_start..content_start + end].trim().to_string());
            }
        }

        // Try to find plain code block with JSON
        if let Some(start) = trimmed.find("```") {
            let content_start = start + 3;
            // Skip language identifier if present
            let content_start = if let Some(newline_pos) = trimmed[content_start..].find('\n') {
                content_start + newline_pos + 1
            } else {
                content_start
            };
            if let Some(end) = trimmed[content_start..].find("```") {
                let content = trimmed[content_start..content_start + end].trim();
                if content.starts_with('{') && content.ends_with('}') {
                    return Some(content.to_string());
                }
            }
        }

        // Try to find raw JSON object
        if let Some(start) = trimmed.find('{') {
            if let Some(end) = trimmed.rfind('}') {
                if start < end {
                    return Some(trimmed[start..=end].to_string());
                }
            }
        }

        None
    }

    /// Parse JSON format response (new primary format)
    fn parse_json_response(
        &self,
        value: &serde_json::Value,
        raw_output: &str,
    ) -> anyhow::Result<ParsedIntent> {
        let mut tool_calls = Vec::new();
        let mut phase_transition = None;

        // Extract actions
        if let Some(actions) = value.get("actions").and_then(|v| v.as_array()) {
            for action in actions {
                let action_type = action.get("type")
                    .and_then(|v| v.as_str())
                    .unwrap_or("tool_call");

                if action_type == "tool_call" {
                    if let (Some(skill), Some(tool)) = (
                        action.get("skill").and_then(|v| v.as_str()),
                        action.get("tool").and_then(|v| v.as_str()),
                    ) {
                        let params = action.get("parameters")
                            .and_then(|v| v.as_object())
                            .map(|obj| {
                                obj.iter()
                                    .map(|(k, v)| {
                                        let val = v.as_str()
                                            .map(String::from)
                                            .unwrap_or_else(|| v.to_string());
                                        (k.clone(), serde_json::Value::String(val))
                                    })
                                    .collect()
                            })
                            .unwrap_or_default();

                        let reasoning = action.get("metadata")
                            .and_then(|m| m.get("reasoning"))
                            .and_then(|v| v.as_str())
                            .unwrap_or_default()
                            .to_string();

                        tool_calls.push(ToolCallIntent {
                            skill_name: skill.to_string(),
                            tool_name: tool.to_string(),
                            parameters: serde_json::Value::Object(params),
                            reasoning,
                        });
                    }
                }
            }
        }

        // Extract state_update for phase transition
        if let Some(state_update) = value.get("state_update") {
            if let Some(phase_str) = state_update.get("phase").and_then(|v| v.as_str()) {
                let to_phase = self.parse_phase(phase_str)?;
                phase_transition = Some(PhaseTransitionIntent {
                    from_phase: ExecutionPhase::Execute,
                    to_phase,
                    reason: String::new(),
                    artifacts_to_finalize: vec![],
                });
            }
        }

        // Determine intent type
        // Priority: ToolCall > FinalAnswer > PhaseTransition
        let intent_type = if !tool_calls.is_empty() {
            IntentType::ToolCall
        } else if value.get("explanation").is_some() {
            // Has explanation and no tool calls = final answer
            IntentType::FinalAnswer
        } else if phase_transition.is_some() {
            IntentType::PhaseTransition
        } else {
            IntentType::FinalAnswer
        };

        // Extract explanation
        let explanation = value.get("explanation")
            .and_then(|v| v.as_str())
            .map(String::from);

        Ok(ParsedIntent {
            intent_type,
            confidence: 1.0,
            raw_content: raw_output.to_string(),
            structured_data: value.clone(),
            tool_calls,
            phase_transition,
            final_answer: explanation,
            clarification_request: None,
            error_message: None,
            batch_tasks: None,
        })
    }

    fn parse_phase(&self, phase_str: &str) -> anyhow::Result<ExecutionPhase> {
        match phase_str.to_lowercase().as_str() {
            "explore" => Ok(ExecutionPhase::Explore),
            "execute" => Ok(ExecutionPhase::Execute),
            "complete" | "completed" => Ok(ExecutionPhase::Complete),
            _ => Err(anyhow::anyhow!("Unknown phase: {}", phase_str)),
        }
    }

    fn create_error_intent(&self, raw_output: &str, error_msg: &str) -> ParsedIntent {
        ParsedIntent {
            intent_type: IntentType::Error,
            confidence: 0.0,
            raw_content: raw_output.to_string(),
            structured_data: serde_json::json!({}),
            tool_calls: vec![],
            phase_transition: None,
            final_answer: None,
            clarification_request: None,
            error_message: Some(error_msg.to_string()),
            batch_tasks: None,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_json_response() {
        let json = r#"{
  "reasoning": {
    "observation": "User wants to read file",
    "thought": "I should use bash skill",
    "plan": ["Read the file"]
  },
  "explanation": "I'll read that file for you",
  "actions": [
    {
      "type": "tool_call",
      "id": "act_001",
      "skill": "bash",
      "tool": "execute",
      "parameters": {
        "command": "cat /etc/hosts"
      }
    }
  ],
  "state_update": {
    "phase": "Execute",
    "artifacts": []
  }
}"#;

        let parser = OutputParser::new();
        let intent = parser.parse(json, ExecutionPhase::Execute).unwrap();

        assert_eq!(intent.intent_type, IntentType::ToolCall);
        assert_eq!(intent.tool_calls.len(), 1);
        assert_eq!(intent.tool_calls[0].skill_name, "bash");
        assert_eq!(intent.tool_calls[0].tool_name, "execute");
        assert_eq!(
            intent.tool_calls[0].parameters.get("command").and_then(|v| v.as_str()),
            Some("cat /etc/hosts")
        );
    }

    #[test]
    fn test_parse_json_multiple_actions() {
        let json = r#"{
  "reasoning": {
    "observation": "Need to list and read",
    "thought": "Two steps needed",
    "plan": ["List files", "Read content"]
  },
  "explanation": "I'll list and read for you",
  "actions": [
    {
      "type": "tool_call",
      "id": "act_001",
      "skill": "bash",
      "tool": "execute",
      "parameters": {
        "command": "ls -la"
      }
    },
    {
      "type": "tool_call",
      "id": "act_002",
      "skill": "bash",
      "tool": "execute",
      "parameters": {
        "command": "cat file.txt"
      }
    }
  ],
  "state_update": {
    "phase": "Execute",
    "artifacts": []
  }
}"#;

        let parser = OutputParser::new();
        let intent = parser.parse(json, ExecutionPhase::Execute).unwrap();

        assert_eq!(intent.intent_type, IntentType::ToolCall);
        assert_eq!(intent.tool_calls.len(), 2);
        assert_eq!(
            intent.tool_calls[0].parameters.get("command").and_then(|v| v.as_str()),
            Some("ls -la")
        );
        assert_eq!(
            intent.tool_calls[1].parameters.get("command").and_then(|v| v.as_str()),
            Some("cat file.txt")
        );
    }

    #[test]
    fn test_parse_json_final_answer() {
        let json = r#"{
  "reasoning": {
    "observation": "Task complete",
    "thought": "No more actions needed",
    "plan": []
  },
  "explanation": "This is the final answer",
  "actions": [],
  "state_update": {
    "phase": "Complete",
    "artifacts": []
  }
}"#;

        let parser = OutputParser::new();
        let intent = parser.parse(json, ExecutionPhase::Complete).unwrap();

        assert_eq!(intent.intent_type, IntentType::FinalAnswer);
        assert_eq!(intent.final_answer.unwrap(), "This is the final answer");
    }

    #[test]
    fn test_parse_xml_fallback() {
        // XML fallback is deprecated - JSON is the primary format
        // This test verifies that invalid/unparseable content returns an error intent
        let invalid = "This is not valid JSON or XML";

        let parser = OutputParser::new();
        let intent = parser.parse(invalid, ExecutionPhase::Execute).unwrap();

        // Should return error intent when neither JSON nor XML can be parsed
        assert_eq!(intent.intent_type, IntentType::Error);
    }
}
