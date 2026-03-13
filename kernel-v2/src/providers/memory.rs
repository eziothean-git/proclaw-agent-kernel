//! Memory provider - long-term memory access (simplified)

use crate::config::MemoryProviderConfig;
use std::collections::HashMap;
use tokio::sync::Mutex;
use tracing::{debug, info};

/// Memory fact entry
#[derive(Debug, Clone)]
pub struct MemoryFact {
    pub id: String,
    pub content: String,
    pub category: String,
    pub importance: u8,
}

/// Memory query request
#[derive(Debug, Clone)]
pub struct MemoryQuery {
    pub query_text: String,
    pub categories: Vec<String>,
    pub limit: usize,
}

/// Memory provider (simplified in-memory version)
pub struct MemoryProvider {
    data: Mutex<HashMap<String, MemoryFact>>,
    max_facts_per_query: usize,
}

impl MemoryProvider {
    /// Create new memory provider
    pub async fn new(config: &MemoryProviderConfig) -> anyhow::Result<Self> {
        info!("MemoryProvider initialized (simplified)");
        
        Ok(Self {
            data: Mutex::new(HashMap::new()),
            max_facts_per_query: config.max_facts_per_query,
        })
    }
    
    /// Query memory facts
    pub async fn query(
        &self,
        query: MemoryQuery,
    ) -> anyhow::Result<Vec<MemoryFact>> {
        let data = self.data.lock().await;
        
        let mut results: Vec<MemoryFact> = data
            .values()
            .filter(|fact| {
                // Filter by categories
                if !query.categories.is_empty() && !query.categories.contains(&fact.category) {
                    return false;
                }
                
                // Simple text search
                if !query.query_text.is_empty() {
                    fact.content.to_lowercase().contains(&query.query_text.to_lowercase())
                } else {
                    true
                }
            })
            .cloned()
            .collect();
        
        // Sort by importance
        results.sort_by(|a, b| b.importance.cmp(&a.importance));
        
        // Limit results
        let limit = query.limit.min(self.max_facts_per_query);
        results.truncate(limit);
        
        debug!("Found {} memory facts", results.len());
        
        Ok(results)
    }
    
    /// Add a new memory fact
    pub async fn add_fact(
        &self,
        content: &str,
        category: &str,
        importance: u8,
    ) -> anyhow::Result<String> {
        let id = format!("mem_{}", uuid::Uuid::new_v4().to_string()[..8].to_string());
        
        let fact = MemoryFact {
            id: id.clone(),
            content: content.to_string(),
            category: category.to_string(),
            importance,
        };
        
        let mut data = self.data.lock().await;
        data.insert(id.clone(), fact);
        
        info!("Added memory fact: {}", id);
        
        Ok(id)
    }
    
    /// Delete a memory fact
    pub async fn delete_fact(
        &self,
        fact_id: &str,
    ) -> anyhow::Result<bool> {
        let mut data = self.data.lock().await;
        Ok(data.remove(fact_id).is_some())
    }
    
    /// Get memory statistics
    pub async fn get_stats(&self,
    ) -> anyhow::Result<MemoryStats> {
        let data = self.data.lock().await;
        
        let mut category_counts: HashMap<String, i64> = HashMap::new();
        for fact in data.values() {
            *category_counts.entry(fact.category.clone()).or_insert(0) += 1;
        }
        
        Ok(MemoryStats {
            total_count: data.len(),
            category_counts: category_counts.into_iter().collect(),
        })
    }
}

/// Memory statistics
#[derive(Debug)]
pub struct MemoryStats {
    pub total_count: usize,
    pub category_counts: Vec<(String, i64)>,
}

use uuid;
