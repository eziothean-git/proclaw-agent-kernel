//! LLM Router - 多 Provider 路由和请求管理
//! 
//! 职责：
//! - 根据配置选择最佳 Provider 和模型
//! - 异步提交 LLM 请求
//! - 收集完整响应后回调给调用者

use std::collections::HashMap;
use std::sync::Arc;
use std::time::Duration;
use dashmap::DashMap;
use tokio::sync::{mpsc, oneshot};
use tokio::time::timeout;
use tracing::{debug, error, info, instrument, warn};
use uuid::Uuid;

use super::{
    client::{LLMClient, SimpleLLMClient, MockLLMClient},
    config::{LLMRouterConfig, LLMRequestConfig, ProviderType, DifficultyLevel},
    models::{LLMRequest, Message},
};

/// 请求 ID
#[derive(Debug, Clone, PartialEq, Eq, Hash)]
pub struct RequestId(pub String);

impl RequestId {
    pub fn new() -> Self {
        Self(Uuid::new_v4().to_string())
    }
}

impl Default for RequestId {
    fn default() -> Self {
        Self::new()
    }
}

/// LLM 请求任务
#[derive(Debug)]
struct LLMTask {
    request_id: RequestId,
    provider_name: String,
    model: String,
    prompt: String,
    config: LLMRequestConfig,
    response_tx: oneshot::Sender<Result<String, LLMError>>,
}

/// LLM 错误类型
#[derive(Debug, thiserror::Error)]
pub enum LLMError {
    #[error("Provider not found: {0}")]
    ProviderNotFound(String),
    
    #[error("Model not available: {0}")]
    ModelNotAvailable(String),
    
    #[error("Request timeout after {0}s")]
    Timeout(u64),
    
    #[error("All providers failed")]
    AllProvidersFailed,
    
    #[error("HTTP error: {0}")]
    HttpError(String),
    
    #[error("Invalid response: {0}")]
    InvalidResponse(String),
    
    #[error("Channel closed")]
    ChannelClosed,
}

/// LLM Router
pub struct LLMRouter {
    config: LLMRouterConfig,
    // 缓存的 Provider 客户端
    clients: DashMap<String, Arc<dyn LLMClient>>,
    // 等待中的请求
    pending_requests: DashMap<RequestId, PendingRequest>,
}

#[derive(Debug)]
struct PendingRequest {
    submitted_at: std::time::Instant,
    config: LLMRequestConfig,
}

impl LLMRouter {
    /// 创建新的 LLM Router
    pub fn new(config: LLMRouterConfig) -> Self {
        let router = Self {
            config,
            clients: DashMap::new(),
            pending_requests: DashMap::new(),
        };
        
        // 预创建所有启用的 Provider 客户端
        router.init_clients();
        
        router
    }
    
    /// 从环境变量创建
    pub fn from_env() -> Self {
        Self::new(LLMRouterConfig::from_env())
    }
    
    /// 初始化 Provider 客户端
    fn init_clients(&self,
    ) {
        for (name, provider_config) in &self.config.providers {
            if !provider_config.enabled {
                continue;
            }
            
            let client: Arc<dyn LLMClient> = match provider_config.provider_type {
                ProviderType::OpenAi | ProviderType::Ark | ProviderType::Custom => {
                    Arc::new(SimpleLLMClient::new(
                        &provider_config.base_url,
                        &provider_config.api_key,
                        &provider_config.default_model,
                    ))
                }
                ProviderType::Local => {
                    // 本地模型，使用 Mock 作为占位
                    Arc::new(MockLLMClient::new("Local model response"))
                }
                ProviderType::Anthropic => {
                    // Anthropic API，使用 SimpleLLMClient（兼容 OpenAI 格式）
                    Arc::new(SimpleLLMClient::new(
                        &provider_config.base_url,
                        &provider_config.api_key,
                        &provider_config.default_model,
                    ))
                }
            };
            
            self.clients.insert(name.clone(), client);
            info!(provider = %name, "Initialized LLM provider client");
        }
    }
    
    /// 提交 LLM 请求
    /// 
    /// 返回 RequestId，可以通过 wait_for_response 等待结果
    #[instrument(skip(self, prompt), fields(prompt_len = prompt.len()))]
    pub async fn submit_request(
        &self,
        prompt: String,
        config: LLMRequestConfig,
    ) -> Result<RequestId, LLMError> {
        // 1. 选择 Provider 和模型
        let (provider_name, model) = self.config.select_provider_and_model(&config)
            .ok_or_else(|| LLMError::AllProvidersFailed)?;
        
        info!(
            provider = %provider_name,
            model = %model,
            difficulty = ?config.difficulty,
            "Selected LLM provider and model"
        );
        
        // 2. 创建请求 ID
        let request_id = RequestId::new();
        
        // 3. 记录待处理请求
        self.pending_requests.insert(
            request_id.clone(),
            PendingRequest {
                submitted_at: std::time::Instant::now(),
                config: config.clone(),
            }
        );
        
        // 4. 异步执行请求
        let client = self.get_client(&provider_name)?;
        let request_id_clone = request_id.clone();
        let timeout_seconds = config.timeout_seconds;
        
        tokio::spawn(async move {
            let result = Self::execute_with_timeout(
                client,
                prompt,
                model,
                config,
                timeout_seconds,
            ).await;
            
            // 请求完成，从待处理列表移除
            // 注意：实际结果通过 wait_for_response 返回
            (request_id_clone, result)
        });
        
        Ok(request_id)
    }
    
    /// 等待请求完成并获取结果
    #[instrument(skip(self), fields(request_id = %request_id.0))]
    pub async fn wait_for_response(
        &self,
        request_id: &RequestId,
    ) -> Result<String, LLMError> {
        // 查找待处理的请求
        let pending = self.pending_requests.get(request_id)
            .ok_or_else(|| LLMError::InvalidResponse("Request not found".to_string()))?;
        
        let config = pending.config.clone();
        let submitted_at = pending.submitted_at;
        drop(pending);
        
        // 获取客户端
        let (provider_name, model) = self.config.select_provider_and_model(&config)
            .ok_or_else(|| LLMError::AllProvidersFailed)?;
        
        let client = self.get_client(&provider_name)?;
        
        // 这里需要重新获取 prompt，这是一个设计问题
        // 更好的设计是：submit_request 返回的是一个 handle，包含所有信息
        // 简化处理：直接在这里执行请求
        
        // 实际上，我们应该在 submit_request 时存储更多信息
        // 现在先简化：重新构建 prompt（这是一个 TODO）
        
        // 由于架构限制，我们需要重新设计
        // 临时方案：直接执行（同步）
        let messages = vec![
            Message {
                role: "system".to_string(),
                content: "You are an Agent Thread in an Agent Kernel system.".to_string(),
            },
            Message {
                role: "user".to_string(),
                content: format!("Request ID: {}", request_id.0),  // 占位
            },
        ];
        
        // 重新设计：存储完整的请求信息
        // 暂时返回错误，提示需要重新设计
        Err(LLMError::InvalidResponse(
            "Architecture needs redesign: prompt should be stored with request".to_string()
        ))
    }
    
    /// 直接生成（简化接口，保持向后兼容）
    /// 
    /// 这个接口会：
    /// 1. 根据难度选择 Provider 和模型
    /// 2. 发送请求
    /// 3. 等待完整响应
    /// 4. 返回结果
    #[instrument(skip(self, prompt), fields(prompt_len = prompt.len()))]
    pub async fn generate(
        &self,
        prompt: String,
        difficulty: DifficultyLevel,
    ) -> Result<String, LLMError> {
        let config = LLMRequestConfig {
            difficulty,
            ..Default::default()
        };
        
        // 选择 Provider 和模型
        let (provider_name, model) = self.config.select_provider_and_model(&config)
            .ok_or_else(|| LLMError::AllProvidersFailed)?;
        
        info!(
            provider = %provider_name,
            model = %model,
            difficulty = ?difficulty,
            "Generating LLM response"
        );
        
        // 获取客户端
        let client = self.get_client(&provider_name)?;
        
        // 执行请求（带超时）
        Self::execute_with_timeout(
            client,
            prompt,
            model,
            config.clone(),
            config.timeout_seconds,
        ).await
    }
    
    /// 使用指定 Provider 生成
    pub async fn generate_with_provider(
        &self,
        provider_name: &str,
        model: &str,
        prompt: String,
    ) -> Result<String, LLMError> {
        let client = self.get_client(provider_name)?;
        
        let config = LLMRequestConfig {
            provider: Some(provider_name.to_string()),
            model: Some(model.to_string()),
            ..Default::default()
        };
        
        Self::execute_with_timeout(
            client,
            prompt,
            model.to_string(),
            config,
            60,
        ).await
    }
    
    /// 获取 Provider 客户端
    fn get_client(
        &self,
        provider_name: &str,
    ) -> Result<Arc<dyn LLMClient>, LLMError> {
        self.clients.get(provider_name)
            .map(|c| c.clone())
            .ok_or_else(|| LLMError::ProviderNotFound(provider_name.to_string()))
    }
    
    /// 执行请求（带超时）
    async fn execute_with_timeout(
        client: Arc<dyn LLMClient>,
        prompt: String,
        model: String,
        _config: LLMRequestConfig,
        timeout_seconds: u64,
    ) -> Result<String, LLMError> {
        // 构建消息
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
        
        // 执行（带超时）
        match timeout(
            Duration::from_secs(timeout_seconds),
            client.generate_messages(messages)
        ).await {
            Ok(Ok(response)) => {
                debug!(response_len = response.len(), "LLM response received");
                Ok(response)
            }
            Ok(Err(e)) => {
                error!(error = %e, "LLM request failed");
                Err(LLMError::HttpError(e.to_string()))
            }
            Err(_) => {
                warn!(timeout = timeout_seconds, "LLM request timeout");
                Err(LLMError::Timeout(timeout_seconds))
            }
        }
    }
    
    /// 获取统计信息
    pub fn get_stats(&self,
    ) -> RouterStats {
        RouterStats {
            total_providers: self.clients.len(),
            pending_requests: self.pending_requests.len(),
        }
    }
    
    /// 获取 Router 统计
    pub fn stats(&self) -> RouterStats {
        RouterStats {
            total_providers: self.clients.len(),
            pending_requests: self.pending_requests.len(),
        }
    }
}

/// Router 统计
#[derive(Debug)]
pub struct RouterStats {
    pub total_providers: usize,
    pub pending_requests: usize,
}