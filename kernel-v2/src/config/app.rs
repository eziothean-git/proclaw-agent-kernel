//! Configuration management for BlockComposer

use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::PathBuf;

/// Main configuration structure
#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct ComposerConfig {
    pub server: ServerConfig,
    pub prompts: PromptsConfig,
    pub providers: ProvidersConfig,
    pub permissions: PermissionsConfig,
    pub gateway: GatewayConfig,
    pub observability: ObservabilityConfig,
    #[serde(default)]
    pub prime: PrimeProviderConfig,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct ServerConfig {
    pub socket_path: PathBuf,
    pub workers: usize,
    pub max_concurrent_requests: usize,
    pub request_timeout_seconds: u64,
}

/// Prompt configuration for different prompt types
#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct PromptsConfig {
    pub thread: ThreadPromptConfig,
    /// Asset-based prompt composition settings
    #[serde(default)]
    pub assets_dir: Option<PathBuf>,
    #[serde(default)]
    pub compositions_dir: Option<PathBuf>,
}

/// A single section in a prompt composition
#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct PromptSection {
    /// Unique identifier for this section
    pub id: String,
    /// Path to the asset file (relative to assets_dir)
    #[serde(default)]
    pub asset: Option<PathBuf>,
    /// Inline template content (alternative to asset)
    #[serde(default)]
    pub template: Option<String>,
    /// Whether this section is required
    #[serde(default = "default_required")]
    pub required: bool,
}

fn default_required() -> bool {
    true
}

/// 预设槽位类型 - 常用的上下文内容类型
#[derive(Debug, Clone, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ContextSlotPreset {
    /// 当前执行状态（phase, step）
    CurrentState,
    /// 执行历史和工具调用
    ExecutionHistory,
    /// 任务目标和约束
    TaskGoal,
    /// 已产生的 artifacts
    Artifacts,
    /// 对话历史
    ConversationHistory,
    /// 最近工具调用结果
    ToolResults,
    /// 错误和异常信息
    ErrorContext,
}

impl std::fmt::Display for ContextSlotPreset {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            ContextSlotPreset::CurrentState => write!(f, "current_state"),
            ContextSlotPreset::ExecutionHistory => write!(f, "execution_history"),
            ContextSlotPreset::TaskGoal => write!(f, "task_goal"),
            ContextSlotPreset::Artifacts => write!(f, "artifacts"),
            ContextSlotPreset::ConversationHistory => write!(f, "conversation_history"),
            ContextSlotPreset::ToolResults => write!(f, "tool_results"),
            ContextSlotPreset::ErrorContext => write!(f, "error_context"),
        }
    }
}

/// 槽位内容来源类型
#[derive(Debug, Clone, Deserialize, Serialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum SlotSourceType {
    /// 内联模板
    Template,
    /// Rust 函数
    Function,
    /// 外部文件
    File,
}

/// 槽位内容来源
#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct SlotSource {
    /// 来源类型
    #[serde(rename = "type")]
    pub source_type: SlotSourceType,
    /// 模板内容（type=template 时使用）
    #[serde(default)]
    pub template: Option<String>,
    /// 函数名称（type=function 时使用）
    #[serde(default)]
    pub function: Option<String>,
    /// 文件路径（type=file 时使用）
    #[serde(default)]
    pub file: Option<PathBuf>,
    /// 变量映射
    #[serde(default)]
    pub variables: HashMap<String, String>,
}

/// 槽位位置
#[derive(Debug, Clone, Deserialize, Serialize, Default, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum SlotPosition {
    /// 在静态部分之后（默认）
    #[default]
    AfterStatic,
    /// 在静态部分之前
    BeforeStatic,
    /// 替换 {{MARKER_NAME}} 占位符
    AtMarker(String),
}

/// 上下文槽位定义
#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct ContextSlot {
    /// 槽位唯一标识（自定义时必填）
    #[serde(default)]
    pub id: Option<String>,
    /// 预设模板名称（使用预设时必填）
    #[serde(default)]
    pub preset: Option<ContextSlotPreset>,
    /// 描述
    #[serde(default)]
    pub description: String,
    /// 位置
    #[serde(default)]
    pub position: SlotPosition,
    /// 是否必须
    #[serde(default = "default_required")]
    pub required: bool,
    /// 内容来源（自定义时使用）
    #[serde(default)]
    pub source: Option<SlotSource>,
    /// 配置选项
    #[serde(default)]
    pub config: HashMap<String, serde_json::Value>,
}

impl ContextSlot {
    /// 获取槽位标识（优先使用 id，其次使用 preset 名称）
    pub fn slot_id(&self) -> String {
        self.id.clone()
            .or_else(|| self.preset.as_ref().map(|p| p.to_string()))
            .unwrap_or_else(|| "unknown".to_string())
    }
}

/// 输出结构配置
#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct OutputStructure {
    /// 输出格式
    pub format: String,
    /// 分隔符
    #[serde(default = "default_separator")]
    pub separator: String,
    /// 是否在静态和动态部分之间添加边界标记
    #[serde(default)]
    pub context_boundary: bool,
}

fn default_separator() -> String {
    "\n\n---\n\n".to_string()
}

/// Defines how to compose a complete prompt from assets
#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct PromptComposition {
    /// Name of the composition
    pub name: String,
    /// Description of what this prompt is for
    pub description: String,
    /// Version of this composition
    pub version: String,
    /// 静态部分（可缓存）- 新格式
    #[serde(default)]
    pub static_sections: Vec<PromptSection>,
    /// 兼容旧格式
    #[serde(default)]
    pub sections: Vec<PromptSection>,
    /// 上下文槽位定义
    #[serde(default)]
    pub context_slots: Vec<ContextSlot>,
    /// 输出结构配置
    #[serde(default)]
    pub output_structure: Option<OutputStructure>,
}

impl PromptComposition {
    /// 检查是否使用新格式（static_sections + context_slots）
    pub fn uses_new_format(&self) -> bool {
        !self.static_sections.is_empty() || !self.context_slots.is_empty()
    }

    /// 获取静态部分（优先使用 static_sections，否则回退到 sections）
    pub fn get_static_sections(&self) -> &Vec<PromptSection> {
        if !self.static_sections.is_empty() {
            &self.static_sections
        } else {
            &self.sections
        }
    }
}

/// Thread system prompt configuration
#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct ThreadPromptConfig {
    pub path: PathBuf,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct ProvidersConfig {
    pub bash: BashProviderConfig,
    pub code: CodeProviderConfig,
    pub memory: MemoryProviderConfig,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct BashProviderConfig {
    pub timeout_seconds: u64,
    pub max_output_size: usize,
    pub blocked_commands: Vec<String>,
    pub patterns_file: PathBuf,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct CodeProviderConfig {
    pub index: CodeIndexConfig,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct CodeIndexConfig {
    pub database_path: PathBuf,
    pub update_interval_seconds: u64,
    pub paths: Vec<IndexPathConfig>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct IndexPathConfig {
    pub path: PathBuf,
    pub languages: Vec<String>,
    pub include_patterns: Vec<String>,
    pub exclude_patterns: Vec<String>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct MemoryProviderConfig {
    pub database_path: PathBuf,
    pub max_facts_per_query: usize,
    pub default_categories: Vec<String>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct PermissionsConfig {
    pub default_token_ttl_seconds: u64,
    pub default_max_calls: u32,
    pub policy_file: PathBuf,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct GatewayConfig {
    pub url: String,
    pub auth_token: String,
    pub webhook_path: String,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct ObservabilityConfig {
    pub metrics: MetricsConfig,
    pub traces: TracesConfig,
    pub audit: AuditConfig,
    pub logging: LoggingConfig,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct MetricsConfig {
    pub enabled: bool,
    pub port: u16,
    pub path: String,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct TracesConfig {
    pub base_path: PathBuf,
    pub retention_days: u64,
    pub compress_after_hours: u64,
    pub compression_algorithm: String,
    pub compression_level: i32,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct AuditConfig {
    pub path: PathBuf,
    pub level: String,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct LoggingConfig {
    pub level: String,
    pub format: String,
    pub output: String,
}

/// Prime Personality Provider Configuration
#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct PrimeProviderConfig {
    /// Path to the prime personality prompt file
    #[serde(default = "default_prime_prompt_path")]
    pub prompt_path: PathBuf,
    /// LLM temperature for prime personality
    #[serde(default = "default_prime_temperature")]
    pub temperature: f32,
    /// Maximum tokens for prime personality
    #[serde(default = "default_prime_max_tokens")]
    pub max_tokens: i32,
    /// Model to use (overrides global setting)
    pub model: Option<String>,
}

fn default_prime_prompt_path() -> PathBuf {
    PathBuf::from("/etc/proclaw/prompts/prime.md")
}

fn default_prime_temperature() -> f32 {
    0.3
}

fn default_prime_max_tokens() -> i32 {
    4096
}

impl Default for PrimeProviderConfig {
    fn default() -> Self {
        Self {
            prompt_path: default_prime_prompt_path(),
            temperature: default_prime_temperature(),
            max_tokens: default_prime_max_tokens(),
            model: None,
        }
    }
}

impl ComposerConfig {
    /// Load configuration from file
    pub async fn load(path: &PathBuf) -> anyhow::Result<Self> {
        let content = tokio::fs::read_to_string(path).await?;
        let config: ComposerConfig = serde_yaml::from_str(&content)?;
        Ok(config)
    }

    /// Create default configuration
    pub fn default() -> Self {
        Self {
            server: ServerConfig {
                socket_path: PathBuf::from("/run/proclaw/composer.sock"),
                workers: 4,
                max_concurrent_requests: 100,
                request_timeout_seconds: 30,
            },
            prompts: PromptsConfig {
                thread: ThreadPromptConfig {
                    path: PathBuf::from("/etc/proclaw/prompts/thread.md"),
                },
                assets_dir: Some(PathBuf::from("/etc/proclaw/prompts/assets")),
                compositions_dir: Some(PathBuf::from("/etc/proclaw/prompts/compositions")),
            },
            providers: ProvidersConfig {
                bash: BashProviderConfig {
                    timeout_seconds: 30,
                    max_output_size: 100000,
                    blocked_commands: vec![
                        "rm -rf /".to_string(),
                        "mkfs".to_string(),
                        "dd if=/dev/zero".to_string(),
                    ],
                    patterns_file: PathBuf::from("/etc/proclaw/bash_patterns.yaml"),
                },
                code: CodeProviderConfig {
                    index: CodeIndexConfig {
                        database_path: PathBuf::from("/var/lib/proclaw/code_index.db"),
                        update_interval_seconds: 300,
                        paths: vec![],
                    },
                },
                memory: MemoryProviderConfig {
                    database_path: PathBuf::from("/var/lib/proclaw/memory.db"),
                    max_facts_per_query: 50,
                    default_categories: vec!["general".to_string()],
                },
            },
            permissions: PermissionsConfig {
                default_token_ttl_seconds: 3600,
                default_max_calls: 100,
                policy_file: PathBuf::from("/etc/proclaw/policies.yaml"),
            },
            gateway: GatewayConfig {
                url: "http://localhost:3000".to_string(),
                auth_token: "default-token-change-in-production".to_string(),
                webhook_path: "/gateway/webhook/kernel-response".to_string(),
            },
            observability: ObservabilityConfig {
                metrics: MetricsConfig {
                    enabled: true,
                    port: 9090,
                    path: "/metrics".to_string(),
                },
                traces: TracesConfig {
                    base_path: PathBuf::from("/var/lib/proclaw/traces"),
                    retention_days: 30,
                    compress_after_hours: 24,
                    compression_algorithm: "zstd".to_string(),
                    compression_level: 3,
                },
                audit: AuditConfig {
                    path: PathBuf::from("/var/log/proclaw/audit.log"),
                    level: "info".to_string(),
                },
                logging: LoggingConfig {
                    level: "info".to_string(),
                    format: "json".to_string(),
                    output: "stdout".to_string(),
                },
            },
            prime: PrimeProviderConfig::default(),
        }
    }
}
