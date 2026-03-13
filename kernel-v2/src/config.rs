//! Configuration management for BlockComposer

use serde::{Deserialize, Serialize};
use std::path::PathBuf;

/// Main configuration structure
#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct ComposerConfig {
    pub server: ServerConfig,
    pub cache: CacheConfig,
    pub providers: ProvidersConfig,
    pub permissions: PermissionsConfig,
    pub gateway: GatewayConfig,
    pub observability: ObservabilityConfig,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct ServerConfig {
    pub socket_path: PathBuf,
    pub workers: usize,
    pub max_concurrent_requests: usize,
    pub request_timeout_seconds: u64,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct CacheConfig {
    pub l1: L1CacheConfig,
    pub l2: L2CacheConfig,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct L1CacheConfig {
    pub max_entries: usize,
    pub default_ttl_seconds: TtlConfig,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct TtlConfig {
    pub prime: u64,
    pub session: u64,
    pub task: u64,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct L2CacheConfig {
    pub path: PathBuf,
    pub max_size_mb: u64,
    pub compression: String,
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
            cache: CacheConfig {
                l1: L1CacheConfig {
                    max_entries: 1000,
                    default_ttl_seconds: TtlConfig {
                        prime: 300,
                        session: 120,
                        task: 30,
                    },
                },
                l2: L2CacheConfig {
                    path: PathBuf::from("/var/lib/proclaw/cache.db"),
                    max_size_mb: 512,
                    compression: "zstd".to_string(),
                },
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
        }
    }
}
