//! Output Parser - 解析 LLM 输出为结构化意图
//! 
//! 支持：
//! - JSON 格式解析
//! - YAML 格式解析  
//! - 启发式解析（fallback）

use tracing::{debug, warn};

use crate::agent_thread::models::ExecutionPhase;
use crate::scheduler::thread_executor::{IntentType, ParsedIntent, PhaseTransitionIntent, ToolCallIntent};

/// Output Parser
pub struct OutputParser;

impl OutputParser {
    pub fn new() -> Self {
        Self
    }
    
    /// 解析 LLM 输出
    pub fn parse(
        &self,
        output: &str,
        current_phase: ExecutionPhase,
    ) -> anyhow::Result<ParsedIntent> {
        // 1. 尝试 JSON 解析
        if let Ok(intent) = self.parse_json(output, current_phase) {
            debug!("Parsed as JSON");
            return Ok(intent);
        }
        
        // 2. 尝试 YAML 解析
        if let Ok(intent) = self.parse_yaml(output, current_phase) {
            debug!("Parsed as YAML");
            return Ok(intent);
        }
        
        // 3. 启发式解析
        warn!("Falling back to heuristic parsing");
        self.parse_heuristic(output, current_phase)
    }
    
    /// JSON 解析
    fn parse_json(
        &self,
        output: &str,
        _current_phase: ExecutionPhase,
    ) -> anyhow::Result<ParsedIntent> {
        // 提取 JSON 代码块
        let json_str = self.extract_code_block(output, "json")
            .unwrap_or_else(|| output.to_string());
        
        let json_value: serde_json::Value = serde_json::from_str(&json_str)?;
        
        // 解析 intent 字段
        let intent_type = json_value.get("intent")
            .and_then(|v| v.as_str())
            .unwrap_or("tool_call");
        
        match intent_type {
            "tool_call" | "tool_calls" => {
                let tool_calls = self.parse_tool_calls_json(&json_value)?;
                Ok(ParsedIntent {
                    intent_type: IntentType::ToolCall,
                    confidence: 1.0,
                    raw_content: output.to_string(),
                    structured_data: json_value.clone(),
                    tool_calls,
                    phase_transition: None,
                    final_answer: None,
                    clarification_request: None,
                    error_message: None,
                })
            }
            "phase_transition" => {
                let transition = self.parse_phase_transition_json(&json_value)?;
                Ok(ParsedIntent {
                    intent_type: IntentType::PhaseTransition,
                    confidence: 1.0,
                    raw_content: output.to_string(),
                    structured_data: json_value.clone(),
                    tool_calls: vec![],
                    phase_transition: Some(transition),
                    final_answer: None,
                    clarification_request: None,
                    error_message: None,
                })
            }
            "final_answer" | "answer" => {
                let answer = json_value.get("answer")
                    .and_then(|v| v.as_str())
                    .map(|s| s.to_string())
                    .unwrap_or_default();
                Ok(ParsedIntent {
                    intent_type: IntentType::FinalAnswer,
                    confidence: 1.0,
                    raw_content: output.to_string(),
                    structured_data: json_value.clone(),
                    tool_calls: vec![],
                    phase_transition: None,
                    final_answer: Some(answer),
                    clarification_request: None,
                    error_message: None,
                })
            }
            "clarification" => {
                let question = json_value.get("question")
                    .and_then(|v| v.as_str())
                    .map(|s| s.to_string())
                    .unwrap_or_default();
                Ok(ParsedIntent {
                    intent_type: IntentType::Clarification,
                    confidence: 1.0,
                    raw_content: output.to_string(),
                    structured_data: json_value.clone(),
                    tool_calls: vec![],
                    phase_transition: None,
                    final_answer: None,
                    clarification_request: Some(question),
                    error_message: None,
                })
            }
            _ => Err(anyhow::anyhow!("Unknown intent type: {}", intent_type)),
        }
    }
    
    /// YAML 解析
    fn parse_yaml(
        &self,
        output: &str,
        current_phase: ExecutionPhase,
    ) -> anyhow::Result<ParsedIntent> {
        // 提取 YAML 代码块
        let yaml_str = self.extract_code_block(output, "yaml")
            .or_else(|| self.extract_code_block(output, "yml"))
            .unwrap_or_else(|| output.to_string());
        
        // 转换为 JSON 然后解析
        let yaml_value: serde_yaml::Value = serde_yaml::from_str(&yaml_str)?;
        let json_value = serde_json::to_value(yaml_value)?;
        
        // 复用 JSON 解析逻辑
        self.parse_json(&json_value.to_string(), current_phase)
    }
    
    /// 启发式解析（fallback）
    fn parse_heuristic(
        &self,
        output: &str,
        _current_phase: ExecutionPhase,
    ) -> anyhow::Result<ParsedIntent> {
        let output_lower = output.to_lowercase();
        
        // 检测最终答案
        if output_lower.contains("final answer:") 
            || output_lower.contains("final_answer:")
            || output_lower.contains("answer:") {
            return Ok(ParsedIntent {
                intent_type: IntentType::FinalAnswer,
                confidence: 0.7,
                raw_content: output.to_string(),
                structured_data: serde_json::json!({}),
                tool_calls: vec![],
                phase_transition: None,
                final_answer: Some(output.to_string()),
                clarification_request: None,
                error_message: None,
            });
        }
        
        // 检测澄清请求
        if output_lower.contains("clarification:")
            || output_lower.contains("i need more information")
            || output_lower.contains("please clarify") {
            return Ok(ParsedIntent {
                intent_type: IntentType::Clarification,
                confidence: 0.7,
                raw_content: output.to_string(),
                structured_data: serde_json::json!({}),
                tool_calls: vec![],
                phase_transition: None,
                final_answer: None,
                clarification_request: Some(output.to_string()),
                error_message: None,
            });
        }
        
        // 默认假设是工具调用
        Ok(ParsedIntent {
            intent_type: IntentType::ToolCall,
            confidence: 0.5,
            raw_content: output.to_string(),
            structured_data: serde_json::json!({}),
            tool_calls: vec![],  // 启发式解析无法提取具体工具调用
            phase_transition: None,
            final_answer: None,
            clarification_request: None,
            error_message: None,
        })
    }
    
    /// 提取代码块
    fn extract_code_block(
        &self,
        output: &str,
        language: &str,
    ) -> Option<String> {
        let pattern = format!("```{}\n", language);
        if let Some(start) = output.find(&pattern) {
            let content_start = start + pattern.len();
            if let Some(end) = output[content_start..].find("```") {
                return Some(output[content_start..content_start + end].to_string());
            }
        }
        None
    }
    
    /// 解析工具调用（JSON）
    fn parse_tool_calls_json(
        &self,
        json: &serde_json::Value,
    ) -> anyhow::Result<Vec<ToolCallIntent>> {
        let mut tool_calls = Vec::new();
        
        // 支持两种格式：
        // 1. { "tool_calls": [...] }
        // 2. { "tools": [...] }
        // 3. { "skill": "...", "tool": "...", "parameters": {...} }
        
        if let Some(calls) = json.get("tool_calls").and_then(|v| v.as_array()) {
            for call in calls {
                tool_calls.push(self.parse_single_tool_call(call)?);
            }
        } else if let Some(calls) = json.get("tools").and_then(|v| v.as_array()) {
            for call in calls {
                tool_calls.push(self.parse_single_tool_call(call)?);
            }
        } else if json.get("skill").is_some() {
            // 单个工具调用
            tool_calls.push(self.parse_single_tool_call(json)?);
        }
        
        Ok(tool_calls)
    }
    
    /// 解析单个工具调用
    fn parse_single_tool_call(
        &self,
        json: &serde_json::Value,
    ) -> anyhow::Result<ToolCallIntent> {
        let skill_name = json.get("skill")
            .or_else(|| json.get("skill_name"))
            .and_then(|v| v.as_str())
            .ok_or_else(|| anyhow::anyhow!("Missing skill name"))?
            .to_string();
        
        let tool_name = json.get("tool")
            .or_else(|| json.get("tool_name"))
            .or_else(|| json.get("action"))
            .and_then(|v| v.as_str())
            .unwrap_or("execute")
            .to_string();
        
        let parameters = json.get("parameters")
            .or_else(|| json.get("params"))
            .or_else(|| json.get("args"))
            .cloned()
            .unwrap_or(serde_json::json!({}));
        
        let reasoning = json.get("reasoning")
            .or_else(|| json.get("reason"))
            .or_else(|| json.get("thought"))
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string();
        
        Ok(ToolCallIntent {
            skill_name,
            tool_name,
            parameters,
            reasoning,
        })
    }
    
    /// 解析 Phase 转换（JSON）
    fn parse_phase_transition_json(
        &self,
        json: &serde_json::Value,
    ) -> anyhow::Result<PhaseTransitionIntent> {
        let from_phase_str = json.get("from_phase")
            .and_then(|v| v.as_str())
            .ok_or_else(|| anyhow::anyhow!("Missing from_phase"))?;
        
        let to_phase_str = json.get("to_phase")
            .and_then(|v| v.as_str())
            .ok_or_else(|| anyhow::anyhow!("Missing to_phase"))?;
        
        let from_phase = self.parse_phase(from_phase_str)?;
        let to_phase = self.parse_phase(to_phase_str)?;
        
        let reason = json.get("reason")
            .and_then(|v| v.as_str())
            .unwrap_or("")
            .to_string();
        
        let artifacts_to_finalize = json.get("artifacts_to_finalize")
            .and_then(|v| v.as_array())
            .map(|arr| {
                arr.iter()
                    .filter_map(|v| v.as_str().map(|s| s.to_string()))
                    .collect()
            })
            .unwrap_or_default();
        
        Ok(PhaseTransitionIntent {
            from_phase,
            to_phase,
            reason,
            artifacts_to_finalize,
        })
    }
    
    /// 解析 Phase 字符串
    fn parse_phase(&self, phase_str: &str) -> anyhow::Result<ExecutionPhase> {
        match phase_str.to_lowercase().as_str() {
            "explore" => Ok(ExecutionPhase::Explore),
            "execute" => Ok(ExecutionPhase::Execute),
            "complete" | "completed" => Ok(ExecutionPhase::Complete),
            _ => Err(anyhow::anyhow!("Unknown phase: {}", phase_str)),
        }
    }
}
