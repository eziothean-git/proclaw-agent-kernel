//! Prime Personality XML Response Parser
//!
//! Parses XML format IR from Prime (prime-response)

use serde::{Deserialize, Serialize};
use tracing::{debug, warn};

/// Prime Response root structure
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(rename = "prime-response")]
pub struct PrimeResponse {
    #[serde(rename = "@xmlns", default = "default_namespace")]
    pub namespace: String,

    #[serde(rename = "analysis")]
    pub analysis: Analysis,

    #[serde(rename = "reasoning", default)]
    pub reasoning: Option<Reasoning>,

    #[serde(rename = "plan", default)]
    pub plan: Option<Plan>,

    #[serde(rename = "processes", default)]
    pub processes: Option<Processes>,

    #[serde(rename = "explanation", default)]
    pub explanation: Option<String>,
}

impl PrimeResponse {
    pub fn extract_ir(&self, request_id: &str) -> super::IntermediateRepresentation {
        let processes = self.processes.as_ref()
            .map(|p| p.to_process_definitions())
            .unwrap_or_default();
        
        // Determine intent from processes or default to conversation
        let intent = if processes.is_empty() {
            "conversation".to_string()
        } else {
            self.analysis.intent.clone()
                .unwrap_or_else(|| "file_operation".to_string())
        };
        
        super::IntermediateRepresentation {
            request_id: request_id.to_string(),
            intent,
            goals: vec![format!("{}", self.analysis.observation)],
            processes,
            context_hints: std::collections::HashMap::new(),
            content: Some(super::Content {
                text: self.explanation.clone().or_else(|| Some("Processing...".to_string())),
                attachments: None,
                references: None,
            }),
        }
    }
}

fn default_namespace() -> String {
    "http://proclaw.ai/prime".to_string()
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Analysis {
    #[serde(rename = "observation")]
    pub observation: String,
    #[serde(rename = "intent", default)]
    pub intent: Option<String>,
    #[serde(rename = "complexity", default)]
    pub complexity: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct Reasoning {
    #[serde(rename = "think", default)]
    pub think: Option<String>,
    #[serde(rename = "approach", default)]
    pub approach: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, Default)]
pub struct Plan {
    #[serde(rename = "step", default)]
    pub steps: Vec<PlanStep>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PlanStep {
    #[serde(rename = "@order")]
    pub order: u32,
    #[serde(rename = "$text")]
    pub description: String,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Processes {
    #[serde(rename = "process", default)]
    pub processes: Vec<Process>,
}

impl Processes {
    pub fn to_process_definitions(&self) -> Vec<super::ProcessDefinition> {
        self.processes.iter().map(|p| p.to_definition()).collect()
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Process {
    #[serde(rename = "@id")]
    pub id: String,
    #[serde(rename = "name")]
    pub name: String,
    #[serde(rename = "goal")]
    pub goal: String,
    #[serde(rename = "capabilities")]
    pub capabilities: Capabilities,
    #[serde(rename = "constraints")]
    pub constraints: Option<Constraints>,
    #[serde(rename = "security_level")]
    pub security_level: Option<String>,
}

impl Process {
    pub fn to_definition(&self) -> super::ProcessDefinition {
        super::ProcessDefinition {
            name: self.name.clone(),
            goal: self.goal.clone(),
            capabilities: self.capabilities.to_vec(),
            forbidden_capabilities: None,
            constraints: self.constraints.as_ref().map(|c| c.to_vec()),
            security_level: self.security_level.clone(),
            dependencies: None,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Capabilities {
    #[serde(rename = "capability")]
    pub capabilities: Vec<String>,
}

impl Capabilities {
    pub fn to_vec(&self) -> Vec<String> {
        self.capabilities.clone()
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Constraints {
    #[serde(rename = "constraint")]
    pub constraints: Vec<String>,
}

impl Constraints {
    pub fn to_vec(&self) -> Vec<String> {
        self.constraints.clone()
    }
}

/// Prime XML Parser
pub struct PrimeXmlParser;

impl PrimeXmlParser {
    pub fn new() -> Self {
        Self
    }

    pub fn parse(&self, xml: &str) -> anyhow::Result<PrimeResponse> {
        let clean_xml = self.extract_xml_block(xml);

        match quick_xml::de::from_str::<PrimeResponse>(&clean_xml) {
            Ok(response) => {
                debug!("Successfully parsed Prime XML response");
                Ok(response)
            }
            Err(e) => {
                warn!("Failed to parse Prime XML: {}", e);
                Err(anyhow::anyhow!("Prime XML parse error: {}", e))
            }
        }
    }

    fn extract_xml_block(&self, output: &str) -> String {
        // Try to find XML in markdown code block
        if let Some(start) = output.find("```xml") {
            let content_start = start + 6;
            if let Some(end) = output[content_start..].find("```") {
                return output[content_start..content_start + end].trim().to_string();
            }
        }

        // Try to find ``` block containing XML
        if let Some(start) = output.find("```") {
            let content_start = start + 3;
            if let Some(end) = output[content_start..].find("```") {
                let content = output[content_start..content_start + end].trim();
                if content.starts_with("<?xml") || content.starts_with("<prime-response") {
                    return content.to_string();
                }
            }
        }

        // Return trimmed output as-is
        output.trim().to_string()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_parse_prime_response() {
        let xml = r#"<?xml version="1.0" encoding="UTF-8"?>
<prime-response xmlns="http://proclaw.ai/prime">
  <analysis>
    <observation>User wants to read file</observation>
    <intent>read_file</intent>
    <complexity>simple</complexity>
  </analysis>
  <reasoning>
    <think>Simple file read</think>
    <approach>Use bash skill</approach>
  </reasoning>
  <plan>
    <step order="1">Read file</step>
  </plan>
  <processes>
    <process id="p1">
      <name>read_file</name>
      <goal>Read /etc/hosts</goal>
      <capabilities>
        <capability>bash</capability>
      </capabilities>
      <constraints>
        <constraint>read_only</constraint>
      </constraints>
      <security_level>low</security_level>
    </process>
  </processes>
  <explanation>I'll read that file</explanation>
</prime-response>"#;

        let parser = PrimeXmlParser::new();
        let response = parser.parse(xml).unwrap();

        assert_eq!(response.analysis.intent, Some("read_file".to_string()));
        assert!(response.processes.is_some());
        let processes = response.processes.as_ref().unwrap();
        assert_eq!(processes.processes.len(), 1);
        assert_eq!(processes.processes[0].name, "read_file");
        assert_eq!(response.explanation, Some("I'll read that file".to_string()));
    }
}
