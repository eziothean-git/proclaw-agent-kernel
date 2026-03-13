//! Block composer engine

pub mod cache;

use crate::config::ComposerConfig;
use crate::server::proto::{Block, ComposeResponse, Profile};
use cache::{CacheKey, CacheManager, CachedComposition};
use chrono::Utc;
use std::collections::HashMap;
use std::sync::Arc;
use std::time::Instant;
use tokio::sync::RwLock;
use tracing::{debug, info, instrument};

/// Block metadata
#[derive(Debug, Clone)]
pub struct BlockMetadata {
    pub block_type: i32,
    pub priority: u32,
    pub token_count: u32,
}

/// Block store for managing blocks
pub struct BlockStore {
    blocks: RwLock<HashMap<String, Block>>,
    metadata: RwLock<HashMap<String, BlockMetadata>>,
}

impl BlockStore {
    /// Create new block store
    pub fn new() -> Self {
        Self {
            blocks: RwLock::new(HashMap::new()),
            metadata: RwLock::new(HashMap::new()),
        }
    }
    
    /// Store a block
    pub async fn store(&self, block: Block, metadata: BlockMetadata) {
        let mut blocks = self.blocks.write().await;
        let mut meta = self.metadata.write().await;
        
        let block_id = block.block_id.clone();
        blocks.insert(block_id.clone(), block);
        meta.insert(block_id, metadata);
    }
    
    /// Get a block by ID
    pub async fn get(&self, block_id: &str) -> Option<Block> {
        let blocks = self.blocks.read().await;
        blocks.get(block_id).cloned()
    }
    
    /// Get block metadata
    pub async fn get_metadata(&self, block_id: &str) -> Option<BlockMetadata> {
        let meta = self.metadata.read().await;
        meta.get(block_id).cloned()
    }
    
    /// Get all blocks
    pub async fn get_all(&self) -> Vec<Block> {
        let blocks = self.blocks.read().await;
        blocks.values().cloned().collect()
    }
    
    /// Get blocks by type
    pub async fn get_by_type(&self, block_type: i32) -> Vec<Block> {
        let blocks = self.blocks.read().await;
        blocks
            .values()
            .filter(|b| b.block_type == block_type)
            .cloned()
            .collect()
    }
    
    /// Remove a block
    pub async fn remove(&self, block_id: &str) {
        let mut blocks = self.blocks.write().await;
        let mut meta = self.metadata.write().await;
        
        blocks.remove(block_id);
        meta.remove(block_id);
    }
}

/// Composition configuration for different profiles
#[derive(Debug, Clone)]
pub struct CompositionProfile {
    pub token_budget: u32,
    pub block_type_order: Vec<i32>,
}

impl CompositionProfile {
    /// Get profile for a given profile type
    pub fn for_profile(profile: Profile) -> Self {
        match profile {
            Profile::Prime => Self {
                token_budget: 2000,
                block_type_order: vec![
                    1,  // SYSTEM_IDENTITY
                    3,  // INTENT_ANALYSIS
                    2,  // GLOBAL_MEMORY
                ],
            },
            Profile::Session => Self {
                token_budget: 3000,
                block_type_order: vec![
                    4,  // SESSION_CONTEXT
                    5,  // ACTIVE_TASKS
                    6,  // CONVERSATION_HISTORY
                ],
            },
            Profile::Task => Self {
                token_budget: 4000,
                block_type_order: vec![
                    7,  // TASK_GOAL
                    8,  // WORKING_MEMORY
                    9,  // AVAILABLE_TOOLS
                    10, // RECENT_OBSERVATIONS
                ],
            },
            _ => Self::for_profile(Profile::Task),
        }
    }
}

/// Core block composition engine
pub struct BlockComposerEngine {
    cache: Arc<CacheManager>,
    block_store: Arc<BlockStore>,
    profiles: HashMap<i32, CompositionProfile>,
}

impl BlockComposerEngine {
    /// Create new composer engine
    pub async fn new(config: &ComposerConfig) -> anyhow::Result<Self> {
        info!("Initializing BlockComposer engine");
        
        let cache = Arc::new(CacheManager::new(&config.cache).await?);
        let block_store = Arc::new(BlockStore::new());
        
        let mut profiles = HashMap::new();
        profiles.insert(Profile::Prime as i32, CompositionProfile::for_profile(Profile::Prime));
        profiles.insert(Profile::Session as i32, CompositionProfile::for_profile(Profile::Session));
        profiles.insert(Profile::Task as i32, CompositionProfile::for_profile(Profile::Task));
        
        info!("BlockComposer engine initialized with {} profiles", profiles.len());
        
        Ok(Self {
            cache,
            block_store,
            profiles,
        })
    }
    
    /// Compose blocks into final context
    #[instrument(skip(self, blocks, context))]
    pub async fn compose(
        &self,
        session_id: &str,
        task_id: &str,
        profile: Profile,
        blocks: Vec<Block>,
        context: HashMap<String, String>,
    ) -> anyhow::Result<ComposeResponse> {
        let start = Instant::now();
        
        // Convert profile to i32 for lookup
        let profile_i32 = profile as i32;
        let profile_name = format!("{:?}", profile).to_lowercase();
        
        // Get composition profile config
        let profile_config = self.profiles
            .get(&profile_i32)
            .cloned()
            .unwrap_or_else(|| CompositionProfile::for_profile(profile));
        
        // Generate cache key
        let cache_key = CacheKey::new(
            &profile_name,
            &blocks.iter().map(|b| b.block_type).collect::<Vec<_>>(),
            &context,
        );
        
        // Try to get from cache
        if let Some(cached) = self.cache.get(&cache_key).await? {
            debug!("Cache hit for {}:{}", session_id, task_id);
            
            return Ok(ComposeResponse {
                composed_text: cached.text,
                block_ids_used: cached.block_ids,
                total_tokens: cached.total_tokens,
                cache_hit: true,
                trace_id: format!("trace_{}_{}", session_id, task_id),
                latency: Some(prost_types::Duration {
                    seconds: start.elapsed().as_secs() as i64,
                    nanos: start.elapsed().subsec_nanos() as i32,
                }),
            });
        }
        
        // Store blocks
        for block in &blocks {
            let metadata = BlockMetadata {
                block_type: block.block_type,
                priority: block.priority,
                token_count: block.token_count,
            };
            self.block_store.store(block.clone(), metadata).await;
        }
        
        // Compose blocks according to profile
        let composed = self.compose_blocks(&profile_config,&blocks, profile_config.token_budget).await?;
        
        // Calculate total tokens
        let total_tokens = composed.iter().map(|b| b.token_count).sum();
        
        // Build composed text
        let mut composed_text = String::new();
        let mut block_ids_used = Vec::new();
        
        for block in &composed {
            block_ids_used.push(block.block_id.clone());
            composed_text.push_str(&format!("\n### {}\n{}\n", block.block_id, block.content));
        }
        
        // Cache the result
        let ttl_seconds = match profile {
            Profile::Prime => 300,
            Profile::Session => 120,
            Profile::Task => 30,
            _ => 30,
        };
        
        let cached = CachedComposition {
            text: composed_text.clone(),
            block_ids: block_ids_used.clone(),
            total_tokens,
            cached_at: Utc::now(),
            expires_at: Utc::now() + chrono::Duration::seconds(ttl_seconds as i64),
        };
        
        self.cache.put(&cache_key, cached).await?;
        
        let elapsed = start.elapsed();
        info!(
            "Composed {} blocks for {}:{} in {:?} (cache miss)",
            composed.len(),
            session_id,
            task_id,
            elapsed
        );
        
        Ok(ComposeResponse {
            composed_text,
            block_ids_used,
            total_tokens,
            cache_hit: false,
            trace_id: format!("trace_{}_{}", session_id, task_id),
            latency: Some(prost_types::Duration {
                seconds: elapsed.as_secs() as i64,
                nanos: elapsed.subsec_nanos() as i32,
            }),
        })
    }
    
    /// Compose blocks according to profile rules
    async fn compose_blocks(
        &self,
        profile: &CompositionProfile,
        blocks: &[Block],
        token_budget: u32,
    ) -> anyhow::Result<Vec<Block>> {
        let mut result = Vec::new();
        let mut remaining_budget = token_budget;
        
        // Sort blocks by profile order, then by priority
        let mut sorted_blocks: Vec<_> = blocks.iter().collect();
        sorted_blocks.sort_by(|a, b| {
            let a_order = profile.block_type_order.iter()
                .position(|&t| t == a.block_type)
                .unwrap_or(usize::MAX);
            let b_order = profile.block_type_order.iter()
                .position(|&t| t == b.block_type)
                .unwrap_or(usize::MAX);
            
            if a_order != b_order {
                a_order.cmp(&b_order)
            } else {
                b.priority.cmp(&a.priority)
            }
        });
        
        // Add blocks until budget is exhausted
        for block in sorted_blocks {
            if block.token_count <= remaining_budget {
                result.push(block.clone());
                remaining_budget -= block.token_count;
            } else if remaining_budget > 100 {
                // Partial inclusion: truncate block content
                let mut truncated = block.clone();
                let truncate_at = (remaining_budget * 4) as usize; // rough estimate: 4 chars per token
                truncated.content = format!("{}... (truncated)", &block.content[..truncate_at.min(block.content.len())]);
                truncated.token_count = remaining_budget;
                result.push(truncated);
                break;
            } else {
                break;
            }
        }
        
        Ok(result)
    }
    
    /// Get cache statistics
    pub async fn get_cache_stats(&self) -> anyhow::Result<cache::CacheStats> {
        self.cache.stats().await
    }
    
    /// Invalidate cache for a specific key
    pub async fn invalidate_cache(&self, key: &CacheKey) -> anyhow::Result<()> {
        self.cache.invalidate(key).await
    }

    // ===== 动态 Block 管理方法 (Phase 1 新增) =====

    /// 添加或更新 Block
    pub async fn upsert_block(&self, block: Block, metadata: BlockMetadata) {
        self.block_store.store(block, metadata).await;
    }

    /// 删除 Block
    pub async fn remove_block(&self, block_id: &str) -> bool {
        self.block_store.remove(block_id).await;
        true
    }

    /// 获取指定 Block
    pub async fn get_block(&self, block_id: &str) -> Option<Block> {
        self.block_store.get(block_id).await
    }

    /// 获取 Block 元数据
    pub async fn get_block_metadata(&self, block_id: &str) -> Option<BlockMetadata> {
        self.block_store.get_metadata(block_id).await
    }

    /// 列出所有 Blocks
    pub async fn list_all_blocks(&self) -> Vec<Block> {
        self.block_store.get_all().await
    }

    /// 按类型列出 Blocks
    pub async fn list_blocks_by_type(&self, block_type: i32) -> Vec<Block> {
        self.block_store.get_by_type(block_type).await
    }

    /// 清空所有 Blocks
    pub async fn clear_all_blocks(&self) {
        let mut blocks = self.block_store.blocks.write().await;
        let mut meta = self.block_store.metadata.write().await;
        blocks.clear();
        meta.clear();
    }
}

/// Placeholder module for observability
pub mod observability {
    use crate::config::{MetricsConfig, TracesConfig};
    
    pub struct MetricsCollector;
    
    impl MetricsCollector {
        pub fn new(_config: &MetricsConfig) -> Self {
            Self
        }
    }
    
    pub struct TraceCollector;
    
    impl TraceCollector {
        pub async fn new(_config: &TracesConfig) -> anyhow::Result<Self> {
            Ok(Self)
        }
    }
}

pub use observability::*;

#[cfg(test)]
mod tests {
    use super::*;

    fn create_test_block(id: &str, content: &str, block_type: i32) -> Block {
        Block {
            block_id: id.to_string(),
            block_type,
            content: content.to_string(),
            metadata: Vec::new(),
            priority: 50,
            token_count: (content.len() / 4) as u32,
            dependencies: Vec::new(),
            content_hash: format!("hash_{}", id),
            created_at: Some(prost_types::Timestamp {
                seconds: chrono::Utc::now().timestamp(),
                nanos: 0,
            }),
        }
    }

    fn create_test_metadata(block_type: i32) -> BlockMetadata {
        BlockMetadata {
            block_type,
            priority: 50,
            token_count: 10,
        }
    }

    #[tokio::test]
    async fn test_block_store_operations() {
        let store = BlockStore::new();

        let block = create_test_block("test1", "Test content", 1);
        let metadata = create_test_metadata(1);
        store.store(block.clone(), metadata).await;

        let retrieved = store.get("test1").await;
        assert!(retrieved.is_some());
        assert_eq!(retrieved.unwrap().content, "Test content");

        let block2 = create_test_block("test2", "Content 2", 2);
        let metadata2 = create_test_metadata(2);
        store.store(block2, metadata2).await;

        let all_blocks = store.get_all().await;
        assert_eq!(all_blocks.len(), 2);

        let type1_blocks = store.get_by_type(1).await;
        assert_eq!(type1_blocks.len(), 1);

        store.remove("test1").await;
        assert!(store.get("test1").await.is_none());
    }

    async fn create_test_engine() -> BlockComposerEngine {
        let temp_dir = std::env::temp_dir().join(format!("proclaw_test_{}", uuid::Uuid::new_v4()));
        tokio::fs::create_dir_all(&temp_dir).await.unwrap();
        
        let config = ComposerConfig {
            server: crate::config::ServerConfig {
                socket_path: temp_dir.join("test.sock"),
                workers: 1,
                max_concurrent_requests: 100,
                request_timeout_seconds: 30,
            },
            cache: crate::config::CacheConfig {
                l1: crate::config::L1CacheConfig {
                    max_entries: 100,
                    default_ttl_seconds: crate::config::TtlConfig {
                        prime: 300,
                        session: 120,
                        task: 30,
                    },
                },
                l2: crate::config::L2CacheConfig {
                    path: temp_dir.join("cache.db"),
                    max_size_mb: 10,
                    compression: "zstd".to_string(),
                },
            },
            providers: crate::config::ProvidersConfig {
                bash: crate::config::BashProviderConfig {
                    timeout_seconds: 30,
                    max_output_size: 1024,
                    blocked_commands: vec![],
                    patterns_file: temp_dir.join("patterns.yaml"),
                },
                code: crate::config::CodeProviderConfig {
                    index: crate::config::CodeIndexConfig {
                        database_path: temp_dir.join("code_index.db"),
                        update_interval_seconds: 300,
                        paths: vec![],
                    },
                },
                memory: crate::config::MemoryProviderConfig {
                    database_path: temp_dir.join("memory.db"),
                    max_facts_per_query: 10,
                    default_categories: vec![],
                },
            },
            permissions: crate::config::PermissionsConfig {
                default_token_ttl_seconds: 3600,
                default_max_calls: 100,
                policy_file: temp_dir.join("policies.yaml"),
            },
            observability: crate::config::ObservabilityConfig {
                metrics: crate::config::MetricsConfig {
                    enabled: false,
                    port: 9090,
                    path: "/metrics".to_string(),
                },
                traces: crate::config::TracesConfig {
                    base_path: temp_dir.join("traces"),
                    retention_days: 7,
                    compress_after_hours: 24,
                    compression_algorithm: "zstd".to_string(),
                    compression_level: 3,
                },
                audit: crate::config::AuditConfig {
                    path: temp_dir.join("audit.log"),
                    level: "info".to_string(),
                },
                logging: crate::config::LoggingConfig {
                    level: "info".to_string(),
                    format: "json".to_string(),
                    output: "stdout".to_string(),
                },
            },
        };
        
        BlockComposerEngine::new(&config).await.unwrap()
    }

    #[tokio::test]
    async fn test_engine_compose_integration() {
        let engine = create_test_engine().await;

        let block1 = create_test_block("task_goal", "Implement feature X", 7);
        let meta1 = create_test_metadata(7);
        engine.upsert_block(block1, meta1).await;

        let block2 = create_test_block("context", "Background information", 8);
        let meta2 = create_test_metadata(8);
        engine.upsert_block(block2, meta2).await;

        let blocks = engine.list_all_blocks().await;
        let context = std::collections::HashMap::new();

        let response = engine.compose("test_session", "test_task", Profile::Task, blocks, context).await;
        
        assert!(response.is_ok());
        let compose_response = response.unwrap();
        assert!(!compose_response.composed_text.is_empty());
        assert!(compose_response.total_tokens > 0);
    }

    #[tokio::test]
    async fn test_engine_dynamic_block_lifecycle() {
        let engine = create_test_engine().await;

        let block = create_test_block("dynamic1", "Dynamic content", 1);
        let metadata = create_test_metadata(1);
        engine.upsert_block(block, metadata).await;

        let retrieved = engine.get_block("dynamic1").await;
        assert!(retrieved.is_some());
        assert_eq!(retrieved.unwrap().content, "Dynamic content");

        let all_blocks = engine.list_all_blocks().await;
        assert_eq!(all_blocks.len(), 1);

        engine.remove_block("dynamic1").await;
        assert!(engine.get_block("dynamic1").await.is_none());

        engine.clear_all_blocks().await;
        assert!(engine.list_all_blocks().await.is_empty());
    }
}
