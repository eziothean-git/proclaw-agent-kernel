//! Prompt Loader Service
//!
//! Loads prompt files from disk and caches them in memory.
//! Supports hot-reloading by re-reading files on demand.

use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::Arc;
use tokio::sync::RwLock;
use tracing::{debug, info, warn};

use super::app::PromptsConfig;

/// Fallback thread prompt used when file cannot be loaded
const FALLBACK_THREAD_PROMPT: &str = r#"You are an AI agent. You MUST output JSON format ONLY.

REQUIRED JSON Structure:
{
  "reasoning": {
    "observation": "What you see in the context",
    "thought": "Your internal thinking process",
    "plan": ["Step 1", "Step 2"]
  },
  "explanation": "What you tell the user (this is user-visible)",
  "actions": [
    {
      "type": "tool_call",
      "id": "act_001",
      "skill": "bash",
      "tool": "execute",
      "parameters": {
        "command": "ls -la"
      }
    }
  ],
  "state_update": {
    "phase": "Execute"
  }
}

CRITICAL RULES:
- Output ONLY raw JSON, NO markdown code blocks, NO conversation text
- Use tool_call actions to execute commands
- When task is complete, set phase to "Complete" and omit actions array
- The explanation field is the ONLY text visible to the user
- Each action MUST have: type, id, skill, tool, parameters"#;

/// Prompt loader service that loads and caches prompts from disk
pub struct PromptLoader {
    /// In-memory cache of loaded prompts
    prompts: Arc<RwLock<HashMap<String, String>>>,
    /// Configuration for prompt paths
    config: PromptsConfig,
}

impl PromptLoader {
    /// Create a new PromptLoader with the given configuration
    pub fn new(config: PromptsConfig) -> Self {
        Self {
            prompts: Arc::new(RwLock::new(HashMap::new())),
            config,
        }
    }

    /// Load all prompts from disk into memory
    pub async fn load_all(&self) -> anyhow::Result<()> {
        info!("Loading all prompts from disk");

        // Load thread prompt
        let thread_prompt = self.load_file(&self.config.thread.path).await?;
        let mut prompts = self.prompts.write().await;
        prompts.insert("thread".to_string(), thread_prompt);

        info!("Loaded {} prompts", prompts.len());
        Ok(())
    }

    /// Get a prompt by name
    /// Returns the cached prompt if available, otherwise loads from disk
    pub async fn get(&self, name: &str) -> Option<String> {
        // First check cache
        {
            let prompts = self.prompts.read().await;
            if let Some(prompt) = prompts.get(name) {
                return Some(prompt.clone());
            }
        }

        // If not in cache, try to load based on name
        let path = match name {
            "thread" => self.config.thread.path.clone(),
            _ => return None,
        };

        // Try to load from disk
        match self.load_file(&path).await {
            Ok(content) => {
                let mut prompts = self.prompts.write().await;
                prompts.insert(name.to_string(), content.clone());
                Some(content)
            }
            Err(e) => {
                warn!("Failed to load prompt '{}': {}", name, e);
                None
            }
        }
    }

    /// Get thread prompt with fallback
    pub async fn get_thread_prompt(&self) -> String {
        self.get("thread")
            .await
            .unwrap_or_else(|| FALLBACK_THREAD_PROMPT.to_string())
    }

    /// Force reload a prompt from disk
    pub async fn reload(&self, name: &str) -> anyhow::Result<()> {
        let path = match name {
            "thread" => self.config.thread.path.clone(),
            _ => return Err(anyhow::anyhow!("Unknown prompt: {}", name)),
        };

        let content = self.load_file(&path).await?;
        let mut prompts = self.prompts.write().await;
        prompts.insert(name.to_string(), content);

        debug!("Reloaded prompt: {}", name);
        Ok(())
    }

    /// Clear the in-memory cache
    pub async fn clear_cache(&self) {
        let mut prompts = self.prompts.write().await;
        prompts.clear();
        debug!("Prompt cache cleared");
    }

    /// Load a file from disk
    async fn load_file(&self, path: &PathBuf) -> anyhow::Result<String> {
        debug!("Loading prompt from: {:?}", path);
        let content = tokio::fs::read_to_string(path).await?;
        Ok(content)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use super::super::app::ThreadPromptConfig;
    use std::path::PathBuf;

    #[tokio::test]
    async fn test_fallback_prompt() {
        let config = PromptsConfig {
            thread: ThreadPromptConfig {
                path: PathBuf::from("/nonexistent/path/thread.md"),
            },
            assets_dir: None,
            compositions_dir: None,
        };

        let loader = PromptLoader::new(config);
        let prompt = loader.get_thread_prompt().await;

        assert!(prompt.contains("You are an AI agent"));
        assert!(prompt.contains("JSON format ONLY"));
    }
}
