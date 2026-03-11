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
use tracing::{debug, info, instrument, warn};

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
