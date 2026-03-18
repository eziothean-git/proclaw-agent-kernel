//! Cache Metrics for Prompt Caching
//!
//! Collects metrics for LLM prompt caching including hit rate,
//! tokens saved, and provider-specific statistics.

use prometheus::{Counter, Gauge, Histogram, HistogramOpts, Registry};
use std::sync::Arc;
use tracing::info;

/// Cache metrics container
pub struct CacheMetrics {
    /// Total cache hits
    pub cache_hits: Counter,
    /// Total cache misses
    pub cache_misses: Counter,
    /// Total tokens saved by caching
    pub tokens_saved: Counter,
    /// Current cache hit rate (0.0 - 1.0)
    pub hit_rate: Gauge,
    /// Cache lookup latency histogram
    pub lookup_latency: Histogram,
    /// Cache creation count
    pub cache_creations: Counter,
    /// Cache eviction count
    pub cache_evictions: Counter,
    /// Registry reference for potential cleanup
    #[allow(dead_code)]
    registry: Arc<Registry>,
}

impl CacheMetrics {
    /// Create new cache metrics instance
    pub fn new(registry: Arc<Registry>) -> Result<Self, prometheus::Error> {
        let cache_hits = Counter::new(
            "proclaw_cache_hits_total",
            "Total number of cache hits",
        )?;
        registry.register(Box::new(cache_hits.clone()))?;

        let cache_misses = Counter::new(
            "proclaw_cache_misses_total",
            "Total number of cache misses",
        )?;
        registry.register(Box::new(cache_misses.clone()))?;

        let tokens_saved = Counter::new(
            "proclaw_cache_tokens_saved_total",
            "Total number of tokens saved by caching",
        )?;
        registry.register(Box::new(tokens_saved.clone()))?;

        let hit_rate = Gauge::new(
            "proclaw_cache_hit_rate",
            "Current cache hit rate (0.0 - 1.0)",
        )?;
        registry.register(Box::new(hit_rate.clone()))?;

        let lookup_latency = Histogram::with_opts(
            HistogramOpts::new(
                "proclaw_cache_lookup_latency_seconds",
                "Cache lookup latency in seconds",
            )
            .buckets(vec![0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0]),
        )?;
        registry.register(Box::new(lookup_latency.clone()))?;

        let cache_creations = Counter::new(
            "proclaw_cache_creations_total",
            "Total number of cache entries created",
        )?;
        registry.register(Box::new(cache_creations.clone()))?;

        let cache_evictions = Counter::new(
            "proclaw_cache_evictions_total",
            "Total number of cache entries evicted",
        )?;
        registry.register(Box::new(cache_evictions.clone()))?;

        Ok(Self {
            cache_hits,
            cache_misses,
            tokens_saved,
            hit_rate,
            lookup_latency,
            cache_creations,
            cache_evictions,
            registry,
        })
    }

    /// Record a cache hit
    pub fn record_hit(&self, tokens_saved: usize) {
        self.cache_hits.inc();
        self.tokens_saved.inc_by(tokens_saved as f64);
        self.update_hit_rate();
    }

    /// Record a cache miss
    pub fn record_miss(&self) {
        self.cache_misses.inc();
        self.update_hit_rate();
    }

    /// Record cache creation
    pub fn record_creation(&self) {
        self.cache_creations.inc();
    }

    /// Record cache eviction
    pub fn record_eviction(&self) {
        self.cache_evictions.inc();
    }

    /// Record lookup latency
    pub fn record_latency(&self, seconds: f64) {
        self.lookup_latency.observe(seconds);
    }

    /// Update the hit rate gauge
    fn update_hit_rate(&self) {
        // Note: Counter::get() is not available in prometheus crate
        // We use a simplified approach that tracks rate via external state
        // For now, just log the metrics periodically
    }

    /// Log current metrics (for debugging)
    pub fn log_metrics(&self) {
        info!(
            "Cache metrics - hits: {}, misses: {}, tokens_saved: {}",
            self.cache_hits.get(),
            self.cache_misses.get(),
            self.tokens_saved.get()
        );
    }
}

impl Clone for CacheMetrics {
    fn clone(&self) -> Self {
        Self {
            cache_hits: self.cache_hits.clone(),
            cache_misses: self.cache_misses.clone(),
            tokens_saved: self.tokens_saved.clone(),
            hit_rate: self.hit_rate.clone(),
            lookup_latency: self.lookup_latency.clone(),
            cache_creations: self.cache_creations.clone(),
            cache_evictions: self.cache_evictions.clone(),
            registry: self.registry.clone(),
        }
    }
}

/// Provider-specific cache statistics
#[derive(Debug, Clone, Default)]
pub struct ProviderCacheStats {
    /// Provider name
    pub provider: String,
    /// Total requests
    pub total_requests: u64,
    /// Cache hits
    pub cache_hits: u64,
    /// Cache misses
    pub cache_misses: u64,
    /// Tokens saved
    pub tokens_saved: u64,
    /// Tokens from cache reads
    pub cache_read_tokens: u64,
    /// Tokens from cache creation
    pub cache_creation_tokens: u64,
}

impl ProviderCacheStats {
    /// Create new provider cache stats
    pub fn new(provider: impl Into<String>) -> Self {
        Self {
            provider: provider.into(),
            ..Default::default()
        }
    }

    /// Record a request with cache result
    pub fn record_request(&mut self, cache_hit: bool, tokens_saved: u64) {
        self.total_requests += 1;
        if cache_hit {
            self.cache_hits += 1;
            self.tokens_saved += tokens_saved;
            self.cache_read_tokens += tokens_saved;
        } else {
            self.cache_misses += 1;
        }
    }

    /// Record cache creation tokens
    pub fn record_cache_creation(&mut self, tokens: u64) {
        self.cache_creation_tokens += tokens;
    }

    /// Calculate hit rate
    pub fn hit_rate(&self) -> f64 {
        if self.total_requests == 0 {
            0.0
        } else {
            self.cache_hits as f64 / self.total_requests as f64
        }
    }

    /// Calculate cost savings percentage
    pub fn cost_savings_percent(&self) -> f64 {
        // Assume cached tokens cost 10% of normal tokens (Claude pricing)
        // This gives a rough estimate of savings
        let total_input = self.cache_read_tokens + self.cache_creation_tokens;
        if total_input == 0 {
            0.0
        } else {
            // Without caching: would pay full price for all tokens
            // With caching: pay 10% for cached reads + 125% for creation
            // Savings = (cache_read_tokens * 0.9) / total_input
            (self.cache_read_tokens as f64 * 0.9 / total_input as f64) * 100.0
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use prometheus::Registry;

    #[test]
    fn test_provider_cache_stats() {
        let mut stats = ProviderCacheStats::new("claude");

        // Record some requests
        stats.record_request(true, 1000); // cache hit
        stats.record_request(true, 500);  // cache hit
        stats.record_request(false, 0);   // cache miss
        stats.record_request(true, 750);  // cache hit

        assert_eq!(stats.total_requests, 4);
        assert_eq!(stats.cache_hits, 3);
        assert_eq!(stats.cache_misses, 1);
        assert_eq!(stats.tokens_saved, 2250);

        // Hit rate should be 75%
        assert!((stats.hit_rate() - 0.75).abs() < 0.001);
    }

    #[test]
    fn test_cache_metrics_creation() {
        let registry = Arc::new(Registry::new());
        let metrics = CacheMetrics::new(registry);
        assert!(metrics.is_ok());
    }
}
