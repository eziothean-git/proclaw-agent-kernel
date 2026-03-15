//! 动态配置管理器
//!
//! 支持从文件加载配置，便于调试和运行时调整

use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::Arc;
use tokio::sync::RwLock;
use serde::{Deserialize, Serialize};
use tracing::{info, warn};

/// 输出格式枚举
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum OutputFormat {
    /// Markdown 格式（默认，向后兼容）
    Markdown,
    /// XML 结构化格式
    Xml,
    /// 混合格式：XML 结构 + CDATA 包裹 Markdown
    XmlHybrid,
}

impl Default for OutputFormat {
    fn default() -> Self {
        OutputFormat::Markdown
    }
}

/// Composer 配置
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ComposerConfig {
    /// 默认输出格式
    pub output_format: OutputFormat,
    
    /// XML 配置
    pub xml_config: XmlConfig,
    
    /// 提示词资产目录
    pub assets_path: PathBuf,
}

impl Default for ComposerConfig {
    fn default() -> Self {
        Self {
            output_format: OutputFormat::Markdown,
            xml_config: XmlConfig::default(),
            assets_path: PathBuf::from("./data/prompts"),
        }
    }
}

/// XML 输出配置
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct XmlConfig {
    /// 是否使用 CDATA 包裹内容
    pub use_cdata: bool,
    /// 是否包含元数据属性
    pub include_attributes: bool,
    /// 根标签名称
    pub root_tag: String,
    /// XML 命名空间
    pub namespace: Option<String>,
}

impl Default for XmlConfig {
    fn default() -> Self {
        Self {
            use_cdata: true,
            include_attributes: true,
            root_tag: "context".to_string(),
            namespace: Some("http://proclaw.ai/context".to_string()),
        }
    }
}

/// 动态配置结构
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DynamicConfig {
    /// Prime Personality 配置
    pub prime: PrimeConfig,
    
    /// Composer 配置
    pub composer: ComposerConfig,
    
    /// 执行器配置
    pub executor: ExecutorConfig,
    
    /// 调试配置
    pub debug: DebugConfig,
    
    /// 功能开关
    pub features: FeatureFlags,
}

impl Default for DynamicConfig {
    fn default() -> Self {
        Self {
            prime: PrimeConfig::default(),
            composer: ComposerConfig::default(),
            executor: ExecutorConfig::default(),
            debug: DebugConfig::default(),
            features: FeatureFlags::default(),
        }
    }
}

/// Prime Personality 动态配置
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PrimeConfig {
    /// 是否启用意图强制修正
    pub enable_intent_override: bool,
    
    /// 意图关键词映射
    pub intent_keywords: HashMap<String, Vec<String>>,
    
    /// 系统提示词附加内容
    pub system_prompt_appendix: String,
    
    /// 温度参数覆盖
    pub temperature_override: Option<f32>,
}

impl Default for PrimeConfig {
    fn default() -> Self {
        let mut intent_keywords = HashMap::new();
        
        // 文件操作关键词
        intent_keywords.insert(
            "file_operation".to_string(),
            vec![
                "读取文件".to_string(),
                "read file".to_string(),
                "查看文件".to_string(),
                "文件内容".to_string(),
                "/home/".to_string(),
                "/data/".to_string(),
                ".md".to_string(),
                ".txt".to_string(),
                "cat ".to_string(),
                "list".to_string(),
                "ls ".to_string(),
            ],
        );
        
        // Shell 执行关键词
        intent_keywords.insert(
            "shell_execution".to_string(),
            vec![
                "执行命令".to_string(),
                "execute".to_string(),
                "run command".to_string(),
                "bash".to_string(),
                "sh ".to_string(),
            ],
        );
        
        Self {
            enable_intent_override: true,
            intent_keywords,
            system_prompt_appendix: String::new(),
            temperature_override: None,
        }
    }
}

/// 执行器配置
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ExecutorConfig {
    /// 默认超时时间（秒）
    pub default_timeout_seconds: u64,
    
    /// 最大执行步数
    pub max_steps: usize,
    
    /// 是否启用详细日志
    pub verbose_logging: bool,
}

impl Default for ExecutorConfig {
    fn default() -> Self {
        Self {
            default_timeout_seconds: 300,
            max_steps: 100,
            verbose_logging: true,
        }
    }
}

/// 调试配置
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DebugConfig {
    /// 是否打印 Prime 的 prompt
    pub print_prime_prompt: bool,
    
    /// 是否打印 Prime 的 response
    pub print_prime_response: bool,
    
    /// 是否保存所有 IR 到文件
    pub save_ir_to_file: bool,
    
    /// IR 保存路径
    pub ir_save_path: PathBuf,
}

impl Default for DebugConfig {
    fn default() -> Self {
        Self {
            print_prime_prompt: false,
            print_prime_response: false,
            save_ir_to_file: false,
            ir_save_path: PathBuf::from("./debug/ir"),
        }
    }
}

/// 功能开关
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FeatureFlags {
    /// 是否启用 IR Process Executor
    pub enable_ir_executor: bool,
    
    /// 是否启用 Phase 3（Prime 第二轮迭代）
    pub enable_phase_3: bool,
    
    /// 是否启用自动意图修正
    pub enable_auto_intent_fix: bool,
}

impl Default for FeatureFlags {
    fn default() -> Self {
        Self {
            enable_ir_executor: true,
            enable_phase_3: true,
            enable_auto_intent_fix: false,
        }
    }
}

/// 配置管理器
pub struct ConfigManager {
    config: Arc<RwLock<DynamicConfig>>,
    config_path: PathBuf,
}

impl ConfigManager {
    /// 创建新的配置管理器
    pub async fn new(config_path: PathBuf) -> anyhow::Result<Self> {
        let config = if config_path.exists() {
            info!("Loading dynamic config from: {}", config_path.display());
            let content = tokio::fs::read_to_string(&config_path).await?;
            serde_yaml::from_str(&content)?
        } else {
            info!("Creating default dynamic config at: {}", config_path.display());
            let config = DynamicConfig::default();
            // 创建目录
            if let Some(parent) = config_path.parent() {
                tokio::fs::create_dir_all(parent).await?;
            }
            // 保存默认配置
            let content = serde_yaml::to_string(&config)?;
            tokio::fs::write(&config_path, content).await?;
            config
        };
        
        Ok(Self {
            config: Arc::new(RwLock::new(config)),
            config_path,
        })
    }
    
    /// 获取配置（只读）
    pub async fn get_config(&self) -> DynamicConfig {
        self.config.read().await.clone()
    }
    
    /// 更新配置
    pub async fn update_config(
        &self,
        new_config: DynamicConfig,
    ) -> anyhow::Result<()> {
        // 保存到文件
        let content = serde_yaml::to_string(&new_config)?;
        tokio::fs::write(&self.config_path, content).await?;
        
        // 更新内存中的配置
        *self.config.write().await = new_config;
        
        info!("Dynamic config updated");
        Ok(())
    }
    
    /// 重新加载配置
    pub async fn reload(&self) -> anyhow::Result<()> {
        if !self.config_path.exists() {
            warn!("Config file not found: {}", self.config_path.display());
            return Ok(());
        }
        
        let content = tokio::fs::read_to_string(&self.config_path).await?;
        let new_config: DynamicConfig = serde_yaml::from_str(&content)?;
        
        *self.config.write().await = new_config;
        
        info!("Dynamic config reloaded from: {}", self.config_path.display());
        Ok(())
    }
    
    /// 获取配置路径
    pub fn config_path(&self) -> &PathBuf {
        &self.config_path
    }
}

// 全局配置访问点
lazy_static::lazy_static! {
    static ref GLOBAL_CONFIG: std::sync::Mutex<Option<Arc<ConfigManager>>> = 
        std::sync::Mutex::new(None);
}

/// 初始化全局配置
pub async fn init_global_config(config_path: PathBuf) -> anyhow::Result<()> {
    let manager = ConfigManager::new(config_path).await?;
    *GLOBAL_CONFIG.lock().unwrap() = Some(Arc::new(manager));
    Ok(())
}

/// 获取全局配置
pub fn get_global_config() -> Option<Arc<ConfigManager>> {
    GLOBAL_CONFIG.lock().unwrap().clone()
}
