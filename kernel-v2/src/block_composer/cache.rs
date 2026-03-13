//! Multi-layer cache system for BlockComposer
//!
//! L1: In-memory LRU cache for hot blocks
//! L2: File-system based persistent cache (JSON Lines format)

use crate::config::{CacheConfig, L2CacheConfig, TtlConfig};
use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};
use sha2::{Sha256, Digest};
use std::collections::HashMap;
use std::path::{Path, PathBuf};
use tokio::fs;
use tokio::io::AsyncWriteExt;
use tokio::sync::Mutex;
use tracing::{debug, info, warn};

/// Cache key for block lookup
#[derive(Debug, Clone, Hash, Eq, PartialEq, Serialize, Deserialize)]
pub struct CacheKey {
    pub profile: String,
    pub block_types_hash: String,
    pub context_hash: String,
}

impl CacheKey {
    pub fn new(profile: &str, block_types: &[i32], context: &HashMap<String, String>) -> Self {
        // Compute block_types_hash from block types
        let mut block_types_hasher = Sha256::new();
        for bt in block_types {
            block_types_hasher.update(bt.to_le_bytes());
        }
        let block_types_hash = hex::encode(block_types_hasher.finalize())[..16].to_string();
        
        // Compute context_hash from sorted context keys and values
        let mut context_hasher = Sha256::new();
        let mut sorted_keys: Vec<_> = context.keys().collect();
        sorted_keys.sort();
        for key in sorted_keys {
            context_hasher.update(key.as_bytes());
            context_hasher.update(context[key].as_bytes());
        }
        let context_hash = hex::encode(context_hasher.finalize())[..16].to_string();
        
        Self {
            profile: profile.to_string(),
            block_types_hash,
            context_hash,
        }
    }

    pub fn to_string(&self) -> String {
        format!("{}:{}:{}", self.profile, self.block_types_hash, self.context_hash)
    }
}

/// Cached composition result
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CachedComposition {
    pub text: String,
    pub block_ids: Vec<String>,
    pub total_tokens: u32,
    pub cached_at: DateTime<Utc>,
    pub expires_at: DateTime<Utc>,
}

impl CachedComposition {
    pub fn is_expired(&self) -> bool {
        Utc::now() > self.expires_at
    }
}

/// L1 Cache (in-memory)
pub struct L1Cache {
    cache: Mutex<HashMap<String, CachedComposition>>,
}

impl L1Cache {
    pub fn new(max_entries: usize, _ttl_config: TtlConfig) -> Self {
        Self {
            cache: Mutex::new(HashMap::with_capacity(max_entries)),
        }
    }

    pub async fn get(&self, key: &CacheKey) -> Option<CachedComposition> {
        let key_str = key.to_string();
        let cache = self.cache.lock().await;
        cache.get(&key_str).cloned()
    }

    pub async fn put(&self, key: &CacheKey, composition: CachedComposition) {
        let key_str = key.to_string();
        let mut cache = self.cache.lock().await;
        cache.insert(key_str, composition);
        debug!("L1 cache put");
    }

    pub async fn stats(&self) -> L1Stats {
        let cache = self.cache.lock().await;
        L1Stats {
            len: cache.len(),
            capacity: 1000,
        }
    }
}

#[derive(Debug)]
pub struct L1Stats {
    pub len: usize,
    pub capacity: usize,
}

/// L2 Cache Entry for file storage
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct L2CacheEntry {
    pub key: CacheKey,
    pub value: CachedComposition,
    pub created_at: DateTime<Utc>,
    pub thread_id: String,
}

/// L2 Cache (File-system based)
pub struct L2Cache {
    base_path: PathBuf,
    index_file: PathBuf,
    index: Mutex<HashMap<String, PathBuf>>, // key -> file path mapping
}

impl L2Cache {
    /// Create new L2 cache with file system storage
    pub async fn new(config: &L2CacheConfig) -> anyhow::Result<Self> {
        let base_path = config.path.clone();
        let index_file = base_path.join("index.jsonl");
        
        // Create base directory
        fs::create_dir_all(&base_path).await?;
        
        // Load or create index
        let index = if index_file.exists() {
            Self::load_index(&index_file).await?
        } else {
            HashMap::new()
        };
        
        info!("L2 cache initialized at: {:?}", base_path);
        
        Ok(Self {
            base_path,
            index_file,
            index: Mutex::new(index),
        })
    }
    
    /// Load index from file
    async fn load_index(index_file: &Path) -> anyhow::Result<HashMap<String, PathBuf>> {
        let content = fs::read_to_string(index_file).await?;
        let mut index = HashMap::new();
        
        for line in content.lines() {
            if let Ok(entry) = serde_json::from_str::<IndexEntry>(line) {
                index.insert(entry.key, PathBuf::from(entry.path));
            }
        }
        
        info!("Loaded {} entries from L2 cache index", index.len());
        Ok(index)
    }
    
    /// Save index to file
    async fn save_index(&self) -> anyhow::Result<()> {
        let index = self.index.lock().await;
        let mut file = fs::File::create(&self.index_file).await?;
        
        for (key, path) in index.iter() {
            let entry = IndexEntry {
                key: key.clone(),
                path: path.to_string_lossy().to_string(),
            };
            let line = serde_json::to_string(&entry)?;
            file.write_all(line.as_bytes()).await?;
            file.write_all(b"\n").await?;
        }
        
        file.flush().await?;
        Ok(())
    }
    
    /// Generate filename for cache entry
    fn generate_filename(key: &CacheKey, thread_id: &str) -> String {
        let date = Utc::now().format("%Y-%m-%d").to_string();
        let cmd = &key.profile; // Using profile as command identifier
        let simplified_args = Self::simplify_args(&key.block_types_hash);
        let hash = Self::compute_hash(key);
        
        format!("{}_{}_{}_{}_{}.jsonl", date, thread_id, cmd, simplified_args, &hash[..8])
    }
    
    /// Simplify arguments for filename (first few chars)
    fn simplify_args(args: &str) -> String {
        if args.len() <= 10 {
            args.to_string()
        } else {
            format!("{}..", &args[..10])
        }
    }
    
    /// Compute hash for cache key
    fn compute_hash(key: &CacheKey) -> String {
        let mut hasher = Sha256::new();
        hasher.update(key.to_string().as_bytes());
        hex::encode(hasher.finalize())
    }
    
    /// Get cached composition
    pub async fn get(&self, key: &CacheKey) -> anyhow::Result<Option<CachedComposition>> {
        let key_str = key.to_string();
        let index = self.index.lock().await;
        
        if let Some(path) = index.get(&key_str) {
            if path.exists() {
                let content = fs::read_to_string(path).await?;
                if let Ok(entry) = serde_json::from_str::<L2CacheEntry>(&content) {
                    debug!("L2 cache hit: {}", key_str);
                    return Ok(Some(entry.value));
                }
            }
        }
        
        Ok(None)
    }
    
    /// Put composition in cache
    pub async fn put(
        &self,
        key: &CacheKey,
        composition: &CachedComposition,
        thread_id: &str,
    ) -> anyhow::Result<()> {
        let key_str = key.to_string();
        
        // Generate filename
        let filename = Self::generate_filename(key, thread_id);
        let date_dir = Utc::now().format("%Y-%m-%d").to_string();
        let dir_path = self.base_path.join(&date_dir);
        
        // Create date directory
        fs::create_dir_all(&dir_path).await?;
        
        let file_path = dir_path.join(&filename);
        
        // Create entry
        let entry = L2CacheEntry {
            key: key.clone(),
            value: composition.clone(),
            created_at: Utc::now(),
            thread_id: thread_id.to_string(),
        };
        
        // Write to file
        let content = serde_json::to_string(&entry)?;
        fs::write(&file_path, content).await?;
        
        // Update index
        {
            let mut index = self.index.lock().await;
            index.insert(key_str, file_path.clone());
        }
        
        // Save index (async in background would be better, but for now sync)
        self.save_index().await?;
        
        debug!("L2 cache put: {:?}", file_path);
        Ok(())
    }
    
    /// Get cache stats
    pub async fn stats(&self) -> anyhow::Result<L2Stats> {
        let index = self.index.lock().await;
        
        // Calculate total size
        let mut total_size = 0u64;
        for path in index.values() {
            if let Ok(metadata) = fs::metadata(path).await {
                total_size += metadata.len();
            }
        }
        
        Ok(L2Stats {
            entry_count: index.len(),
            size_mb: total_size as f64 / (1024.0 * 1024.0),
            max_size_mb: 512, // Placeholder
        })
    }
    
    /// Invalidate cache entry
    pub async fn invalidate(&self, key: &CacheKey) -> anyhow::Result<()> {
        let key_str = key.to_string();
        let mut index = self.index.lock().await;
        
        if let Some(path) = index.remove(&key_str) {
            // Delete file
            if let Err(e) = fs::remove_file(&path).await {
                warn!("Failed to remove cache file {}: {}", path.display(), e);
            }
            debug!("L2 cache invalidated: {}", key_str);
        }
        
        // Update index
        drop(index);
        self.save_index().await?;
        
        Ok(())
    }
    
    /// List all cache entries for a thread
    pub async fn list_by_thread(&self, thread_id: &str) -> Vec<(CacheKey, CachedComposition)> {
        let index = self.index.lock().await;
        let mut results = Vec::new();
        
        for path in index.values() {
            if let Ok(content) = fs::read_to_string(path).await {
                if let Ok(entry) = serde_json::from_str::<L2CacheEntry>(&content) {
                    if entry.thread_id == thread_id {
                        results.push((entry.key, entry.value));
                    }
                }
            }
        }
        
        results
    }
}

/// Index entry for fast lookup
#[derive(Debug, Serialize, Deserialize)]
struct IndexEntry {
    key: String,
    path: String,
}

#[derive(Debug)]
pub struct L2Stats {
    pub entry_count: usize,
    pub size_mb: f64,
    pub max_size_mb: u64,
}

/// Multi-layer cache manager
pub struct CacheManager {
    l1: L1Cache,
    l2: L2Cache,
    current_thread_id: String,
}

impl CacheManager {
    pub async fn new(config: &CacheConfig) -> anyhow::Result<Self> {
        let l1 = L1Cache::new(config.l1.max_entries, config.l1.default_ttl_seconds.clone());
        let l2 = L2Cache::new(&config.l2).await?;
        
        // Generate thread ID for this instance
        let thread_id = format!("thread_{}", uuid::Uuid::new_v4().to_string()[..8].to_string());
        
        info!("Cache manager initialized for thread: {}", thread_id);
        
        Ok(Self {
            l1,
            l2,
            current_thread_id: thread_id,
        })
    }
    
    pub async fn get(&self, key: &CacheKey) -> anyhow::Result<Option<CachedComposition>> {
        // Try L1 first
        if let Some(composition) = self.l1.get(key).await {
            return Ok(Some(composition));
        }
        
        // Try L2
        if let Some(composition) = self.l2.get(key).await? {
            // Promote to L1
            self.l1.put(key, composition.clone()).await;
            return Ok(Some(composition));
        }
        
        Ok(None)
    }
    
    pub async fn put(&self, key: &CacheKey, composition: CachedComposition) -> anyhow::Result<()> {
        // Put in L1
        self.l1.put(key, composition.clone()).await;
        
        // Put in L2 with thread ID
        self.l2.put(key, &composition, &self.current_thread_id).await?;
        
        Ok(())
    }
    
    pub async fn stats(&self) -> anyhow::Result<CacheStats> {
        Ok(CacheStats {
            l1: self.l1.stats().await,
            l2: self.l2.stats().await?,
        })
    }
    
    pub async fn invalidate(&self, key: &CacheKey) -> anyhow::Result<()> {
        // Invalidate in both layers
        self.l2.invalidate(key).await?;
        // Note: L1 invalidation not implemented in simplified version
        Ok(())
    }
    
    /// Get current thread ID
    pub fn thread_id(&self) -> &str {
        &self.current_thread_id
    }
    
    /// List cache entries for current thread
    pub async fn list_thread_entries(&self) -> Vec<(CacheKey, CachedComposition)> {
        self.l2.list_by_thread(&self.current_thread_id).await
    }
}

#[derive(Debug)]
pub struct CacheStats {
    pub l1: L1Stats,
    pub l2: L2Stats,
}
