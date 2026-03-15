//! Configuration module

pub mod app;
pub mod dynamic;

// Re-export from app.rs for backward compatibility
pub use app::{
    BashProviderConfig, CacheConfig, CodeIndexConfig, CodeProviderConfig, ComposerConfig,
    GatewayConfig, L1CacheConfig, L2CacheConfig, LoggingConfig, MemoryProviderConfig,
    MetricsConfig, ObservabilityConfig, PermissionsConfig, ProvidersConfig, ServerConfig,
    TracesConfig, TtlConfig,
};

pub use dynamic::{
    ConfigManager, DebugConfig, DynamicConfig, ExecutorConfig, FeatureFlags, OutputFormat,
    PrimeConfig, XmlConfig, get_global_config, init_global_config,
};

pub use dynamic::ComposerConfig as DynamicComposerConfig;
