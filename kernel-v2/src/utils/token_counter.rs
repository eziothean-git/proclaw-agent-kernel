//! Token Counter - Precise token counting using tiktoken
//!
//! Provides accurate token counting for LLM prompts using the cl100k_base
//! encoding (used by GPT-4, GPT-3.5-turbo, and most modern LLMs).

use std::sync::OnceLock;
use tiktoken_rs::CoreBPE;

/// Global token counter instance
static TOKEN_COUNTER: OnceLock<TokenCounter> = OnceLock::new();

/// Token counter using tiktoken cl100k_base encoding
#[derive(Debug, Clone)]
pub struct TokenCounter {
    encoder: CoreBPE,
}

impl TokenCounter {
    /// Create a new token counter
    pub fn new() -> Self {
        Self {
            encoder: tiktoken_rs::cl100k_base().expect("Failed to initialize tiktoken encoder"),
        }
    }

    /// Get the global token counter instance
    pub fn global() -> &'static Self {
        TOKEN_COUNTER.get_or_init(Self::new)
    }

    /// Count tokens in a text string
    pub fn count_tokens(&self, text: &str) -> usize {
        if text.is_empty() {
            return 0;
        }
        self.encoder.encode_with_special_tokens(text).len()
    }

    /// Count tokens in multiple texts
    pub fn count_tokens_batch(&self, texts: &[&str]) -> usize {
        texts.iter().map(|t| self.count_tokens(t)).sum()
    }

    /// Estimate the maximum text length for a given token budget
    pub fn max_text_length(&self, token_budget: usize) -> usize {
        // Average of 4 characters per token for most text
        // Use a conservative estimate
        token_budget * 3
    }

    /// Truncate text to fit within a token budget
    pub fn truncate_to_tokens(&self, text: &str, max_tokens: usize) -> String {
        if text.is_empty() || max_tokens == 0 {
            return String::new();
        }

        let tokens = self.encoder.encode_with_special_tokens(text);
        if tokens.len() <= max_tokens {
            return text.to_string();
        }

        // Take the first max_tokens tokens
        let truncated_tokens: Vec<usize> = tokens
            .into_iter()
            .take(max_tokens)
            .collect();

        // Try to decode, falling back to string truncation if needed
        self.encoder
            .decode(truncated_tokens)
            .unwrap_or_else(|_| {
                // Fallback: approximate truncation
                let char_count = (max_tokens as f64 * 3.5) as usize;
                text.chars().take(char_count).collect()
            })
    }

    /// Split text into chunks that fit within a token limit
    pub fn chunk_text(&self, text: &str, max_tokens_per_chunk: usize) -> Vec<String> {
        if text.is_empty() {
            return vec![];
        }

        let tokens = self.encoder.encode_with_special_tokens(text);
        if tokens.len() <= max_tokens_per_chunk {
            return vec![text.to_string()];
        }

        let mut chunks = Vec::new();
        let mut current_chunk = Vec::new();

        for token in tokens {
            current_chunk.push(token);
            if current_chunk.len() >= max_tokens_per_chunk {
                if let Ok(chunk_text) = self.encoder.decode(current_chunk.clone()) {
                    chunks.push(chunk_text);
                }
                current_chunk.clear();
            }
        }

        // Handle remaining tokens
        if !current_chunk.is_empty() {
            if let Ok(chunk_text) = self.encoder.decode(current_chunk) {
                chunks.push(chunk_text);
            }
        }

        chunks
    }
}

impl Default for TokenCounter {
    fn default() -> Self {
        Self::new()
    }
}

/// Fast token estimation without tiktoken (fallback)
///
/// This is a simple heuristic: approximately 4 characters per token
/// for English text, or 2 characters per token for Chinese/other languages.
pub fn estimate_tokens_fallback(text: &str) -> usize {
    if text.is_empty() {
        return 0;
    }

    // Count ASCII vs non-ASCII characters
    let ascii_count = text.chars().filter(|c| c.is_ascii()).count();
    let non_ascii_count = text.len().saturating_sub(ascii_count);

    // ASCII: ~4 chars per token
    // Non-ASCII: ~2 chars per token
    (ascii_count / 4) + (non_ascii_count / 2)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_count_tokens_basic() {
        let counter = TokenCounter::new();

        // Basic English text
        let text = "Hello, world!";
        let count = counter.count_tokens(text);
        assert!(count > 0);
        assert!(count < 10);
    }

    #[test]
    fn test_count_tokens_empty() {
        let counter = TokenCounter::new();
        assert_eq!(counter.count_tokens(""), 0);
    }

    #[test]
    fn test_count_tokens_batch() {
        let counter = TokenCounter::new();
        let texts = vec!["Hello", "World", "Test"];
        let batch_count = counter.count_tokens_batch(&texts);

        let individual_sum: usize = texts.iter().map(|t| counter.count_tokens(t)).sum();
        assert_eq!(batch_count, individual_sum);
    }

    #[test]
    fn test_truncate_to_tokens() {
        let counter = TokenCounter::new();

        let long_text = "This is a very long text that should be truncated to fit within a small token budget.";
        let truncated = counter.truncate_to_tokens(long_text, 5);

        // Truncated text should have fewer tokens
        assert!(counter.count_tokens(&truncated) <= 5);
    }

    #[test]
    fn test_estimate_tokens_fallback() {
        // English text
        let english = "Hello world this is a test";
        let est = estimate_tokens_fallback(english);
        assert!(est > 0);

        // Empty text
        assert_eq!(estimate_tokens_fallback(""), 0);

        // Mixed text
        let mixed = "Hello 世界";
        let est_mixed = estimate_tokens_fallback(mixed);
        assert!(est_mixed > 0);
    }

    #[test]
    fn test_global_instance() {
        let counter1 = TokenCounter::global();
        let counter2 = TokenCounter::global();

        // Should be the same instance
        assert!(std::ptr::eq(counter1, counter2));
    }
}
