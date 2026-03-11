//! Authentication and permission management with JWT

pub mod capability;

pub use capability::CapabilityLevel;

use crate::providers::bash::ExecutionMode;
use chrono::{DateTime, Duration, Utc};
use jsonwebtoken::{decode, encode, Algorithm, DecodingKey, EncodingKey, Header, Validation};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::Arc;
use tokio::sync::Mutex;
use tracing::{debug, error, info, warn};

/// Permission levels
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum PermissionLevel {
    System,
    Session,
    Thread,
}

impl std::fmt::Display for PermissionLevel {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            PermissionLevel::System => write!(f, "system"),
            PermissionLevel::Session => write!(f, "session"),
            PermissionLevel::Thread => write!(f, "thread"),
        }
    }
}

impl std::str::FromStr for PermissionLevel {
    type Err = String;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        match s {
            "system" => Ok(PermissionLevel::System),
            "session" => Ok(PermissionLevel::Session),
            "thread" => Ok(PermissionLevel::Thread),
            _ => Err(format!("Unknown permission level: {}", s)),
        }
    }
}

/// Scope of operations allowed by token
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub enum Scope {
    FileMode,
    SearchMode,
    SystemMode,
    Custom(Vec<String>),
}

impl Scope {
    /// Check if scope allows a specific execution mode
    pub fn allows_mode(&self, mode: &ExecutionMode) -> bool {
        match (self, mode) {
            (Scope::FileMode, ExecutionMode::FileMode) => true,
            (Scope::SearchMode, ExecutionMode::SearchMode) => true,
            (Scope::SystemMode, ExecutionMode::SystemMode) => true,
            (Scope::Custom(patterns), ExecutionMode::Custom) => !patterns.is_empty(),
            _ => false,
        }
    }
}

/// JWT Claims for capability token
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CapabilityClaims {
    /// Subject (entity this token is for)
    pub sub: String,
    /// Issuer (who granted this token)
    pub iss: String,
    /// Issued at (Unix timestamp)
    pub iat: i64,
    /// Expiration time (Unix timestamp)
    pub exp: i64,
    /// Permission level
    pub level: PermissionLevel,
    /// Allowed scopes (execution modes)
    pub scopes: Vec<Scope>,
    /// Maximum calls allowed (0 = unlimited)
    #[serde(default)]
    pub max_calls: u32,
}

/// Token with usage tracking
pub struct TrackedToken {
    pub claims: CapabilityClaims,
    pub call_count: std::sync::atomic::AtomicU32,
}

impl TrackedToken {
    /// Check if token is still valid (not expired, not exceeded call limit)
    pub fn is_valid(&self) -> bool {
        let now = Utc::now().timestamp();

        // Check expiration
        if now > self.claims.exp {
            return false;
        }

        // Check call limit
        if self.claims.max_calls > 0 {
            let current = self.call_count.load(std::sync::atomic::Ordering::SeqCst);
            if current >= self.claims.max_calls {
                return false;
            }
        }

        true
    }

    /// Record a call, returns false if limit exceeded
    pub fn record_call(&self) -> bool {
        if self.claims.max_calls > 0 {
            let current = self.call_count.fetch_add(1, std::sync::atomic::Ordering::SeqCst);
            if current >= self.claims.max_calls {
                return false;
            }
        } else {
            self.call_count.fetch_add(1, std::sync::atomic::Ordering::SeqCst);
        }
        true
    }

    /// Get remaining calls (returns u32::MAX if unlimited)
    pub fn remaining_calls(&self) -> u32 {
        if self.claims.max_calls == 0 {
            u32::MAX
        } else {
            let current = self.call_count.load(std::sync::atomic::Ordering::SeqCst);
            self.claims.max_calls.saturating_sub(current)
        }
    }

    /// Get time until expiration
    pub fn time_until_expiry(&self) -> Duration {
        let now = Utc::now().timestamp();
        let remaining = self.claims.exp.saturating_sub(now);
        Duration::seconds(remaining)
    }
}

/// Auth configuration
#[derive(Debug, Clone)]
pub struct AuthConfig {
    pub secret_key: String,
    pub default_ttl_seconds: u64,
    pub default_max_calls: u32,
}

/// Token manager with JWT support
pub struct AuthManager {
    config: AuthConfig,
    encoding_key: EncodingKey,
    decoding_key: DecodingKey,
    tokens: Mutex<HashMap<String, Arc<TrackedToken>>>,
}

impl AuthManager {
    /// Create new auth manager
    pub fn new(config: AuthConfig) -> anyhow::Result<Self> {
        let encoding_key = EncodingKey::from_secret(config.secret_key.as_bytes());
        let decoding_key = DecodingKey::from_secret(config.secret_key.as_bytes());

        info!("AuthManager initialized with JWT support");

        Ok(Self {
            config,
            encoding_key,
            decoding_key,
            tokens: Mutex::new(HashMap::new()),
        })
    }

    /// Issue a new JWT token
    pub async fn issue_token(
        &self,
        subject: String,
        issuer: String,
        level: PermissionLevel,
        scopes: Vec<Scope>,
        ttl_seconds: Option<u64>,
        max_calls: Option<u32>,
    ) -> anyhow::Result<String> {
        let now = Utc::now();
        let ttl = ttl_seconds.unwrap_or(self.config.default_ttl_seconds);
        let exp = now + Duration::seconds(ttl as i64);

        let claims = CapabilityClaims {
            sub: subject.clone(),
            iss: issuer,
            iat: now.timestamp(),
            exp: exp.timestamp(),
            level,
            scopes,
            max_calls: max_calls.unwrap_or(self.config.default_max_calls),
        };

        // Encode JWT
        let token = encode(&Header::new(Algorithm::HS256), &claims, &self.encoding_key)?;

        // Create tracked token
        let tracked = Arc::new(TrackedToken {
            claims: claims.clone(),
            call_count: std::sync::atomic::AtomicU32::new(0),
        });

        // Store in memory
        let mut tokens = self.tokens.lock().await;
        tokens.insert(subject, tracked);

        info!(
            "Issued JWT token for subject: {} (exp: {}s, max_calls: {})",
            claims.sub, ttl, claims.max_calls
        );

        Ok(token)
    }

    /// Verify and decode JWT token
    pub async fn verify_token(
        &self,
        token_string: &str,
    ) -> anyhow::Result<Arc<TrackedToken>> {
        // Decode and validate JWT
        let validation = Validation::new(Algorithm::HS256);
        let token_data = decode::<CapabilityClaims>(
            token_string,
            &self.decoding_key,
            &validation,
        )?;

        let claims = token_data.claims;
        let now = Utc::now().timestamp();

        // Check expiration
        if now > claims.exp {
            return Err(anyhow::anyhow!("Token expired"));
        }

        // Check if we have a tracked token for this subject
        let mut tokens = self.tokens.lock().await;
        if let Some(tracked) = tokens.get(&claims.sub) {
            // Verify claims match
            if tracked.claims.exp == claims.exp && tracked.claims.iat == claims.iat {
                return Ok(tracked.clone());
            }
        }

        // Create new tracked token from claims
        let tracked = Arc::new(TrackedToken {
            claims: claims.clone(),
            call_count: std::sync::atomic::AtomicU32::new(0),
        });

        tokens.insert(claims.sub.clone(), tracked.clone());

        debug!("Verified JWT token for subject: {}", claims.sub);

        Ok(tracked)
    }

    /// Revoke a token by subject
    pub async fn revoke_token(&self,
        subject: &str,
    ) -> anyhow::Result<bool> {
        let mut tokens = self.tokens.lock().await;
        let removed = tokens.remove(subject).is_some();

        if removed {
            info!("Revoked token for subject: {}", subject);
        }

        Ok(removed)
    }

    /// Check permission for an execution mode
    pub fn check_permission(
        &self,
        token: &TrackedToken,
        mode: &ExecutionMode,
    ) -> bool {
        // Check if token is valid (not expired, not exceeded limit)
        if !token.is_valid() {
            warn!(
                "Permission denied: token invalid or expired for subject {}",
                token.claims.sub
            );
            return false;
        }

        // Check if any scope allows this mode
        for scope in &token.claims.scopes {
            if scope.allows_mode(mode) {
                // Record the call after permission check passes
                if !token.record_call() {
                    warn!(
                        "Permission denied: call limit exceeded for subject {}",
                        token.claims.sub
                    );
                    return false;
                }

                debug!(
                    "Permission granted: subject {} can execute {:?}",
                    token.claims.sub, mode
                );
                return true;
            }
        }

        warn!(
            "Permission denied: subject {} cannot execute {:?}",
            token.claims.sub, mode
        );
        false
    }

    /// Get token info for introspection
    pub async fn get_token_info(&self,
        subject: &str,
    ) -> Option<TokenInfo> {
        let tokens = self.tokens.lock().await;
        tokens.get(subject).map(|t| TokenInfo {
            subject: t.claims.sub.clone(),
            issuer: t.claims.iss.clone(),
            level: t.claims.level.to_string(),
            scopes: t
                .claims
                .scopes
                .iter()
                .map(|s| format!("{:?}", s))
                .collect(),
            remaining_calls: t.remaining_calls(),
            expires_at: DateTime::from_timestamp(t.claims.exp, 0).unwrap_or_else(|| Utc::now()),
            is_valid: t.is_valid(),
        })
    }

    /// Cleanup expired tokens
    pub async fn cleanup_expired(&self,
    ) -> usize {
        let mut tokens = self.tokens.lock().await;
        let expired: Vec<String> = tokens
            .iter()
            .filter(|(_, t)| !t.is_valid())
            .map(|(k, _)| k.clone())
            .collect();

        let count = expired.len();
        for subject in expired {
            tokens.remove(&subject);
            debug!("Cleaned up expired token: {}", subject);
        }

        count
    }
}

/// Token information for introspection
#[derive(Debug)]
pub struct TokenInfo {
    pub subject: String,
    pub issuer: String,
    pub level: String,
    pub scopes: Vec<String>,
    pub remaining_calls: u32,
    pub expires_at: DateTime<Utc>,
    pub is_valid: bool,
}

#[cfg(test)]
mod tests {
    use super::*;

    fn create_test_auth_manager() -> AuthManager {
        let config = AuthConfig {
            secret_key: "test-secret-key-12345678901234".to_string(),
            default_ttl_seconds: 3600,
            default_max_calls: 10,
        };
        AuthManager::new(config).unwrap()
    }

    #[tokio::test]
    async fn test_issue_and_verify_token() {
        let auth = create_test_auth_manager();

        let token_string = auth
            .issue_token(
                "test_user".to_string(),
                "test_issuer".to_string(),
                PermissionLevel::Thread,
                vec![Scope::FileMode],
                None,
                None,
            )
            .await
            .unwrap();

        // Verify token
        let tracked = auth.verify_token(&token_string).await.unwrap();

        assert_eq!(tracked.claims.sub, "test_user");
        assert_eq!(tracked.claims.iss, "test_issuer");
        assert_eq!(tracked.claims.level, PermissionLevel::Thread);
        assert!(tracked.is_valid());
    }

    #[tokio::test]
    async fn test_token_expiration() {
        let auth = create_test_auth_manager();

        // Issue token with 1 second TTL
        let token_string = auth
            .issue_token(
                "expire_user".to_string(),
                "test".to_string(),
                PermissionLevel::Thread,
                vec![Scope::FileMode],
                Some(1), // 1 second
                None,
            )
            .await
            .unwrap();

        // Should be valid immediately
        let tracked = auth.verify_token(&token_string).await.unwrap();
        assert!(tracked.is_valid());

        // Wait for expiration
        tokio::time::sleep(tokio::time::Duration::from_secs(2)).await;

        // Should fail verification after expiration
        assert!(auth.verify_token(&token_string).await.is_err());
    }

    #[tokio::test]
    async fn test_permission_check() {
        let auth = create_test_auth_manager();

        let token_string = auth
            .issue_token(
                "perm_user".to_string(),
                "test".to_string(),
                PermissionLevel::Thread,
                vec![Scope::FileMode],
                None,
                Some(5), // max 5 calls
            )
            .await
            .unwrap();

        let tracked = auth.verify_token(&token_string).await.unwrap();

        // Should have permission for FileMode
        assert!(auth.check_permission(&tracked, &ExecutionMode::FileMode));

        // Should NOT have permission for SearchMode
        assert!(!auth.check_permission(&tracked, &ExecutionMode::SearchMode));

        // Check call limit
        assert_eq!(tracked.remaining_calls(), 4);
    }

    #[tokio::test]
    async fn test_call_limit() {
        let auth = create_test_auth_manager();

        let token_string = auth
            .issue_token(
                "limit_user".to_string(),
                "test".to_string(),
                PermissionLevel::Thread,
                vec![Scope::FileMode],
                None,
                Some(3), // max 3 calls
            )
            .await
            .unwrap();

        let tracked = auth.verify_token(&token_string).await.unwrap();

        // First 3 calls should succeed
        assert!(auth.check_permission(&tracked, &ExecutionMode::FileMode));
        assert!(auth.check_permission(&tracked, &ExecutionMode::FileMode));
        assert!(auth.check_permission(&tracked, &ExecutionMode::FileMode));

        // 4th call should fail (limit exceeded)
        assert!(!auth.check_permission(&tracked, &ExecutionMode::FileMode));
    }
}
