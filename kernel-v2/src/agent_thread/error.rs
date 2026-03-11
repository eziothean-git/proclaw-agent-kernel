//! Agent Thread 存储错误类型

use thiserror::Error;

#[derive(Error, Debug)]
pub enum ThreadError {
    #[error("IO error: {0}")]
    Io(#[from] std::io::Error),
    
    #[error("JSON error: {0}")]
    Json(#[from] serde_json::Error),
    
    #[error("YAML error: {0}")]
    Yaml(#[from] serde_yaml::Error),
    
    #[error("Thread not found: {0}")]
    NotFound(String),
    
    #[error("Thread already exists: {0}")]
    AlreadyExists(String),
    
    #[error("Thread is locked by another executor: {0}")]
    Locked(String),
    
    #[error("Invalid thread state: {0}")]
    InvalidState(String),
    
    #[error("Storage error: {0}")]
    Storage(String),
    
    #[error("Lock error: {0}")]
    Lock(String),

    #[error("General error: {0}")]
    Anyhow(String),
}

impl From<anyhow::Error> for ThreadError {
    fn from(err: anyhow::Error) -> Self {
        ThreadError::Anyhow(err.to_string())
    }
}

pub type Result<T> = std::result::Result<T, ThreadError>;