//! LLM 模型

use serde::{Deserialize, Serialize};

/// LLM 请求
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LLMRequest {
    pub model: String,
    pub messages: Vec<Message>,
    pub temperature: f32,
    pub max_tokens: Option<usize>,
}

/// 消息
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Message {
    pub role: String,
    pub content: String,
}

#[derive(Debug, Clone, Deserialize)]
pub struct LLMResponse {
    pub choices: Vec<Choice>,
    pub usage: Option<Usage>,
}

impl LLMResponse {
    pub fn content(&self) -> String {
        self.choices
            .first()
            .map(|c| c.message.content.clone())
            .unwrap_or_default()
    }
}

#[derive(Debug, Clone, Deserialize)]
pub struct Choice {
    pub message: Message,
    pub finish_reason: Option<String>,
}

/// Token 使用量
#[derive(Debug, Clone, Deserialize)]
pub struct Usage {
    pub prompt_tokens: usize,
    pub completion_tokens: usize,
    pub total_tokens: usize,
}

// ===== 缓存控制相关类型 =====

/// 缓存控制类型
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum CacheControl {
    /// 短期缓存（约1小时，Claude ephemeral）
    Ephemeral,
    /// 长期缓存（约5分钟，但更可靠，Claude persistent）
    Persistent,
}

/// 带缓存控制的消息
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CacheAwareMessage {
    /// 角色：system, user, assistant
    pub role: String,
    /// 消息内容
    pub content: String,
    /// 缓存控制（仅 Claude API 使用）
    #[serde(skip_serializing_if = "Option::is_none")]
    pub cache_control: Option<CacheControl>,
}

impl CacheAwareMessage {
    /// 创建系统消息
    pub fn system(content: impl Into<String>) -> Self {
        Self {
            role: "system".to_string(),
            content: content.into(),
            cache_control: None,
        }
    }

    /// 创建用户消息
    pub fn user(content: impl Into<String>) -> Self {
        Self {
            role: "user".to_string(),
            content: content.into(),
            cache_control: None,
        }
    }

    /// 创建助手消息
    pub fn assistant(content: impl Into<String>) -> Self {
        Self {
            role: "assistant".to_string(),
            content: content.into(),
            cache_control: None,
        }
    }

    /// 设置缓存控制
    pub fn with_cache_control(mut self, control: CacheControl) -> Self {
        self.cache_control = Some(control);
        self
    }

    /// 转换为普通 Message（丢弃缓存控制）
    pub fn to_message(&self) -> Message {
        Message {
            role: self.role.clone(),
            content: self.content.clone(),
        }
    }
}

/// 带缓存统计的 LLM 响应
#[derive(Debug, Clone, Deserialize)]
pub struct CacheAwareResponse {
    /// 响应选项
    pub choices: Vec<Choice>,
    /// Token 使用量
    pub usage: Option<Usage>,
    /// 从缓存读取的输入 token 数
    #[serde(default)]
    pub cache_read_input_tokens: Option<usize>,
    /// 创建缓存时的输入 token 数
    #[serde(default)]
    pub cache_creation_input_tokens: Option<usize>,
}

impl CacheAwareResponse {
    /// 获取响应内容
    pub fn content(&self) -> String {
        self.choices
            .first()
            .map(|c| c.message.content.clone())
            .unwrap_or_default()
    }

    /// 是否有缓存命中
    pub fn cache_hit(&self) -> bool {
        self.cache_read_input_tokens.unwrap_or(0) > 0
    }

    /// 获取节省的 token 数量
    pub fn tokens_saved(&self) -> usize {
        self.cache_read_input_tokens.unwrap_or(0)
    }
}

/// LLM 提供商类型（用于选择缓存策略）
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum LLMProvider {
    /// Anthropic Claude（支持 cache_control）
    Claude,
    /// DeepSeek（OpenAI 兼容，system message 自动缓存）
    DeepSeek,
    /// Moonshot Kimi（OpenAI 兼容）
    Kimi,
    /// 智谱 GLM（OpenAI 兼容）
    GLM,
    /// MiniMax（OpenAI 兼容）
    MiniMax,
    /// 通用 OpenAI 兼容 API
    OpenAI,
    /// 未知提供商
    Unknown,
}

impl LLMProvider {
    /// 从 base URL 推断提供商类型
    pub fn from_base_url(url: &str) -> Self {
        let url_lower = url.to_lowercase();
        if url_lower.contains("anthropic.com") || url_lower.contains("claude") {
            Self::Claude
        } else if url_lower.contains("deepseek") {
            Self::DeepSeek
        } else if url_lower.contains("moonshot") || url_lower.contains("kimi") {
            Self::Kimi
        } else if url_lower.contains("zhipu") || url_lower.contains("glm") {
            Self::GLM
        } else if url_lower.contains("minimax") {
            Self::MiniMax
        } else if url_lower.contains("openai.com") {
            Self::OpenAI
        } else {
            Self::Unknown
        }
    }

    /// 是否支持 Claude 风格的 cache_control
    pub fn supports_cache_control(&self) -> bool {
        matches!(self, Self::Claude)
    }

    /// 是否支持 system message 缓存
    pub fn supports_system_prefix_cache(&self) -> bool {
        matches!(
            self,
            Self::DeepSeek | Self::Kimi | Self::GLM | Self::MiniMax | Self::OpenAI
        )
    }
}