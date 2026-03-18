use serde::{Deserialize, Serialize};
use std::path::PathBuf;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PrimePersonalityConfig {
    pub model_name: String,
    pub temperature: f32,
    pub max_tokens: i32,
    pub system_prompt: String,
    pub prompt_file: Option<PathBuf>,
}

impl PrimePersonalityConfig {
    /// 从文件加载prompt
    pub async fn load_prompt_from_file(&mut self) -> anyhow::Result<()> {
        if let Some(ref path) = self.prompt_file {
            if path.exists() {
                let content = tokio::fs::read_to_string(path).await?;
                self.system_prompt = content;
                tracing::info!("Loaded Prime prompt from: {}", path.display());
            } else {
                tracing::error!("Prime prompt file not found: {}", path.display());
                return Err(anyhow::anyhow!(
                    "Prime prompt file not found: {}. ProClaw v2 requires JSON output format prompt files.",
                    path.display()
                ));
            }
        }
        Ok(())
    }

    /// 创建配置并从文件加载prompt
    pub async fn with_prompt_file(
        model_name: String,
        temperature: f32,
        max_tokens: i32,
        prompt_file: PathBuf,
    ) -> anyhow::Result<Self> {
        let content = if prompt_file.exists() {
            tokio::fs::read_to_string(&prompt_file).await?
        } else {
            return Err(anyhow::anyhow!(
                "Prime prompt file not found: {}. ProClaw v2 requires XML format prompt files.",
                prompt_file.display()
            ));
        };

        tracing::info!("Loaded Prime prompt from: {}", prompt_file.display());

        Ok(Self {
            model_name,
            temperature,
            max_tokens,
            system_prompt: content,
            prompt_file: Some(prompt_file),
        })
    }
}

impl Default for PrimePersonalityConfig {
    fn default() -> Self {
        panic!("Default is not supported in ProClaw v2. Please use with_prompt_file() to load JSON output format prompt.");
    }
}
