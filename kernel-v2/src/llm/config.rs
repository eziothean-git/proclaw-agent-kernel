//! LLM Provider 配置和路由
//! 
//! 支持多 Provider 配置，根据任务难度自动选择模型

use std::collections::HashMap;
use serde::{Deserialize, Serialize};

/// Provider 类型
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ProviderType {
    OpenAi,
    Ark,        // 字节跳动方舟
    Anthropic,
    Local,      // 本地模型
    Custom,     // 自定义
}

impl Default for ProviderType {
    fn default() -> Self {
        ProviderType::OpenAi
    }
}

/// LLM Provider 配置
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProviderConfig {
    pub provider_type: ProviderType,
    pub name: String,              // 显示名称
    pub base_url: String,
    pub api_key: String,
    pub default_model: String,
    pub models: Vec<ModelConfig>,  // 该 Provider 支持的模型
    pub priority: i32,             // 优先级（数值越小优先级越高）
    pub enabled: bool,
}

impl ProviderConfig {
    /// 创建 OpenAI 配置
    pub fn openai(api_key: impl Into<String>) -> Self {
        Self {
            provider_type: ProviderType::OpenAi,
            name: "OpenAI".to_string(),
            base_url: "https://api.openai.com/v1".to_string(),
            api_key: api_key.into(),
            default_model: "gpt-4".to_string(),
            models: vec![
                ModelConfig {
                    name: "gpt-4".to_string(),
                    display_name: "GPT-4".to_string(),
                    max_tokens: 8192,
                    cost_per_1k_input: 0.03,
                    cost_per_1k_output: 0.06,
                    capabilities: vec!["complex_reasoning".to_string(), "code".to_string()],
                    difficulty_level: DifficultyLevel::Hard,
                },
                ModelConfig {
                    name: "gpt-4-turbo".to_string(),
                    display_name: "GPT-4 Turbo".to_string(),
                    max_tokens: 128000,
                    cost_per_1k_input: 0.01,
                    cost_per_1k_output: 0.03,
                    capabilities: vec!["complex_reasoning".to_string(), "code".to_string(), "long_context".to_string()],
                    difficulty_level: DifficultyLevel::Hard,
                },
                ModelConfig {
                    name: "gpt-3.5-turbo".to_string(),
                    display_name: "GPT-3.5".to_string(),
                    max_tokens: 4096,
                    cost_per_1k_input: 0.0015,
                    cost_per_1k_output: 0.002,
                    capabilities: vec!["simple_tasks".to_string()],
                    difficulty_level: DifficultyLevel::Easy,
                },
            ],
            priority: 1,
            enabled: true,
        }
    }
    
    /// 创建 Ark 配置（字节跳动）
    pub fn ark(api_key: impl Into<String>) -> Self {
        Self {
            provider_type: ProviderType::Ark,
            name: "Ark".to_string(),
            base_url: "https://ark.cn-beijing.volces.com/api/v3".to_string(),
            api_key: api_key.into(),
            default_model: "glm-4".to_string(),
            models: vec![
                ModelConfig {
                    name: "glm-4".to_string(),
                    display_name: "GLM-4".to_string(),
                    max_tokens: 8192,
                    cost_per_1k_input: 0.01,
                    cost_per_1k_output: 0.02,
                    capabilities: vec!["complex_reasoning".to_string(), "code".to_string()],
                    difficulty_level: DifficultyLevel::Hard,
                },
            ],
            priority: 2,
            enabled: true,
        }
    }
    
    /// 获取指定难度级别的模型
    pub fn get_model_for_difficulty(&self, level: DifficultyLevel) -> Option<&ModelConfig> {
        self.models.iter()
            .filter(|m| m.difficulty_level == level || m.difficulty_level <= level)
            .min_by_key(|m| m.difficulty_level as i32)
    }
}

/// 模型配置
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ModelConfig {
    pub name: String,
    pub display_name: String,
    pub max_tokens: usize,
    pub cost_per_1k_input: f64,
    pub cost_per_1k_output: f64,
    pub capabilities: Vec<String>,
    pub difficulty_level: DifficultyLevel,
}

/// 任务难度级别
#[derive(Debug, Clone, Copy, PartialEq, Eq, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum DifficultyLevel {
    Trivial = 0,    // 非常简单的任务
    Easy = 1,       // 简单任务
    Medium = 2,     // 中等复杂度
    Hard = 3,       // 复杂任务
    Expert = 4,     // 专家级任务
}

impl Default for DifficultyLevel {
    fn default() -> Self {
        DifficultyLevel::Medium
    }
}

/// LLM 请求配置
#[derive(Debug, Clone)]
pub struct LLMRequestConfig {
    pub provider: Option<String>,        // 指定 Provider 名称（可选）
    pub model: Option<String>,           // 指定模型（可选）
    pub difficulty: DifficultyLevel,     // 任务难度（用于自动选择）
    pub temperature: f32,
    pub max_tokens: Option<usize>,
    pub timeout_seconds: u64,
}

impl Default for LLMRequestConfig {
    fn default() -> Self {
        Self {
            provider: None,
            model: None,
            difficulty: DifficultyLevel::Medium,
            temperature: 0.7,
            max_tokens: None,
            timeout_seconds: 60,
        }
    }
}

/// LLM 路由配置
#[derive(Debug, Clone, Default, Serialize, Deserialize)]
pub struct LLMRouterConfig {
    pub providers: HashMap<String, ProviderConfig>,
    pub default_provider: String,
    pub default_difficulty: DifficultyLevel,
    pub enable_fallback: bool,  // 是否允许 Provider 失败时回退
}

impl LLMRouterConfig {
    /// 从环境变量加载配置
    pub fn from_env() -> Self {
        let mut providers = HashMap::new();
        
        // OpenAI
        if let Ok(api_key) = std::env::var("OPENAI_API_KEY") {
            providers.insert("openai".to_string(), ProviderConfig::openai(api_key));
        }
        
        // Ark
        if let Ok(api_key) = std::env::var("ARK_API_KEY") {
            providers.insert("ark".to_string(), ProviderConfig::ark(api_key));
        }
        
        Self {
            providers,
            default_provider: "openai".to_string(),
            default_difficulty: DifficultyLevel::Medium,
            enable_fallback: true,
        }
    }
    
    /// 添加 Provider
    pub fn add_provider(&mut self, name: impl Into<String>, config: ProviderConfig) {
        self.providers.insert(name.into(), config);
    }
    
    /// 获取 Provider
    pub fn get_provider(&self, name: &str) -> Option<&ProviderConfig> {
        self.providers.get(name)
    }
    
    /// 选择最佳 Provider 和模型
    pub fn select_provider_and_model(
        &self,
        config: &LLMRequestConfig,
    ) -> Option<(String, String)> {
        // 1. 如果指定了 Provider 和模型，直接使用
        if let (Some(provider_name), Some(model_name)) = (&config.provider, &config.model) {
            if let Some(provider) = self.providers.get(provider_name) {
                if provider.enabled && provider.models.iter().any(|m| m.name == *model_name) {
                    return Some((provider_name.clone(), model_name.clone()));
                }
            }
        }
        
        // 2. 如果只指定了 Provider，使用该 Provider 的默认模型
        if let Some(provider_name) = &config.provider {
            if let Some(provider) = self.providers.get(provider_name) {
                if provider.enabled {
                    return Some((provider_name.clone(), provider.default_model.clone()));
                }
            }
        }
        
        // 3. 根据难度自动选择
        let difficulty = config.difficulty;
        let mut candidates: Vec<_> = self.providers.iter()
            .filter(|(_, p)| p.enabled)
            .filter_map(|(name, provider)| {
                provider.get_model_for_difficulty(difficulty)
                    .map(|model| (name.clone(), model, provider.priority))
            })
            .collect();
        
        // 按优先级排序
        candidates.sort_by_key(|(_, _, priority)| *priority);
        
        candidates.into_iter()
            .next()
            .map(|(name, model, _)| (name, model.name.clone()))
    }
}
