//! LLM Client 实现

use async_trait::async_trait;
use serde_json::json;

use super::models::*;

/// LLM Client trait
#[async_trait]
pub trait LLMClient: Send + Sync {
    /// 生成文本
    async fn generate(
        &self,
        prompt: String,
    ) -> anyhow::Result<String>;
    
    /// 生成（带消息列表）
    async fn generate_messages(
        &self,
        messages: Vec<Message>,
    ) -> anyhow::Result<String>;
}

/// 简单的 HTTP LLM Client（OpenAI 兼容 API）
pub struct SimpleLLMClient {
    base_url: String,
    api_key: String,
    model: String,
    temperature: f32,
    max_tokens: Option<usize>,
    client: reqwest::Client,
}

impl SimpleLLMClient {
    pub fn new(
        base_url: impl Into<String>,
        api_key: impl Into<String>,
        model: impl Into<String>,
    ) -> Self {
        Self {
            base_url: base_url.into(),
            api_key: api_key.into(),
            model: model.into(),
            temperature: 0.7,
            max_tokens: Some(4000),
            client: reqwest::Client::new(),
        }
    }
    
    pub fn with_temperature(mut self, temperature: f32) -> Self {
        self.temperature = temperature;
        self
    }
    
    pub fn with_max_tokens(mut self, max_tokens: usize) -> Self {
        self.max_tokens = Some(max_tokens);
        self
    }
}

#[async_trait]
impl LLMClient for SimpleLLMClient {
    async fn generate(
        &self,
        prompt: String,
    ) -> anyhow::Result<String> {
        let messages = vec![
            Message {
                role: "system".to_string(),
                content: "You are an Agent Thread in an Agent Kernel system.".to_string(),
            },
            Message {
                role: "user".to_string(),
                content: prompt,
            },
        ];
        
        self.generate_messages(messages).await
    }
    
    async fn generate_messages(
        &self,
        messages: Vec<Message>,
    ) -> anyhow::Result<String> {
        let request = LLMRequest {
            model: self.model.clone(),
            messages,
            temperature: self.temperature,
            max_tokens: self.max_tokens,
        };
        
        let response = self.client
            .post(format!("{}/v1/chat/completions", self.base_url))
            .header("Authorization", format!("Bearer {}", self.api_key))
            .header("Content-Type", "application/json")
            .json(&request)
            .send()
            .await?;
        
        if !response.status().is_success() {
            let error_text = response.text().await?;
            return Err(anyhow::anyhow!("LLM API error: {}", error_text));
        }
        
        let llm_response: LLMResponse = response.json().await?;
        
        Ok(llm_response.content)
    }
}

/// Mock LLM Client（用于测试）
pub struct MockLLMClient {
    response: String,
}

impl MockLLMClient {
    pub fn new(response: impl Into<String>) -> Self {
        Self {
            response: response.into(),
        }
    }
}

#[async_trait]
impl LLMClient for MockLLMClient {
    async fn generate(
        &self,
        _prompt: String,
    ) -> anyhow::Result<String> {
        Ok(self.response.clone())
    }
    
    async fn generate_messages(
        &self,
        _messages: Vec<Message>,
    ) -> anyhow::Result<String> {
        Ok(self.response.clone())
    }
}