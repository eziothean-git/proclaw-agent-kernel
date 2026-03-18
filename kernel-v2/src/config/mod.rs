//! Configuration module

pub mod app;
pub mod dynamic;
pub mod prompt_loader;
pub mod prompt_composer;

// Re-export from app.rs for backward compatibility
pub use app::{
    AuditConfig, BashProviderConfig, CodeIndexConfig, CodeProviderConfig, ComposerConfig,
    GatewayConfig, LoggingConfig, MemoryProviderConfig,
    MetricsConfig, ObservabilityConfig, PermissionsConfig, PrimeProviderConfig, PromptsConfig,
    ProvidersConfig, ServerConfig, ThreadPromptConfig, TracesConfig,
    PromptComposition, PromptSection,
    // Context slot types
    ContextSlot, ContextSlotPreset, SlotSource, SlotSourceType, SlotPosition, OutputStructure,
};

pub use dynamic::{
    ConfigManager, DebugConfig, DynamicConfig, ExecutorConfig, FeatureFlags, OutputFormat,
    PrimeConfig, XmlConfig, get_global_config, init_global_config,
};

pub use dynamic::ComposerConfig as DynamicComposerConfig;

pub use prompt_loader::PromptLoader;
pub use prompt_composer::{PromptComposer, ExecutionContext, ComposedPrompt, CacheHint, CachedPrompt};
