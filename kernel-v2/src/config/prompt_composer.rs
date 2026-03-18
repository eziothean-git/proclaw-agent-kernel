//! Prompt Composer Service
//!
//! Composes complete prompts from modular assets defined in YAML compositions.
//! Supports hot-reloading and caching of composed prompts.
//!
//! # SEE-ACT-UPDATE Context Injection
//!
//! The composer now supports separating static and dynamic content:
//! - **Static sections**: Cached by LLM providers (prefix caching)
//! - **Context slots**: Dynamic content injected at specified positions
//!
//! ## Usage
//!
//! ```yaml
//! static_sections:
//!   - id: identity
//!     asset: "identity/thread_identity.md"
//!     required: true
//!
//! context_slots:
//!   - preset: current_state
//!     position: after_static
//!   - preset: execution_history
//!     config:
//!       max_events: 10
//! ```

use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::Arc;
use tokio::sync::RwLock;
use tracing::{debug, info, warn};

use super::app::{PromptComposition, ContextSlotPreset, SlotSourceType};

/// 执行上下文 - 传递给 PromptComposer 用于构建动态内容
#[derive(Debug, Clone, Default)]
pub struct ExecutionContext {
    /// 任务目标
    pub task_goal: String,
    /// 约束条件
    pub constraints: Vec<String>,
    /// 当前执行阶段
    pub current_phase: String,
    /// 当前步骤号
    pub step_number: usize,
    /// 执行历史事件（格式化后的文本）
    pub events_text: String,
    /// 已产生的 artifacts（格式化后的文本）
    pub artifacts_text: String,
    /// Token 预算
    pub token_budget: usize,
    /// 最近工具调用结果
    pub tool_results_text: String,
    /// 错误信息
    pub error_text: String,
}

/// 组装结果 - 包含静态和动态部分
#[derive(Debug, Clone)]
pub struct ComposedPrompt {
    /// 静态部分（可被 LLM 缓存）
    pub static_part: String,
    /// 动态部分（按槽位 ID 组织）
    pub dynamic_parts: Vec<(String, String)>,
    /// 分隔符
    pub separator: String,
    /// 缓存提示
    pub cache_hint: CacheHint,
}

impl ComposedPrompt {
    /// 生成最终 prompt 文本
    pub fn to_full_prompt(&self) -> String {
        let mut result = self.static_part.clone();
        for (_, content) in &self.dynamic_parts {
            if !content.is_empty() {
                result.push_str(&self.separator);
                result.push_str(content);
            }
        }
        result
    }

    /// 生成带缓存标记的 prompt（用于支持 prompt caching 的 API）
    pub fn to_cached_prompt(&self) -> CachedPrompt {
        let dynamic_content: String = self.dynamic_parts.iter()
            .filter(|(_, c)| !c.is_empty())
            .map(|(_, c)| c.as_str())
            .collect::<Vec<_>>()
            .join(&self.separator);

        CachedPrompt {
            cached_content: self.static_part.clone(),
            dynamic_content,
        }
    }
}

/// 缓存提示
#[derive(Debug, Clone)]
pub struct CacheHint {
    /// 静态部分的 token 数量
    pub static_token_count: usize,
    /// 是否可缓存
    pub cacheable: bool,
}

/// 带缓存标记的 prompt
#[derive(Debug, Clone)]
pub struct CachedPrompt {
    /// 可缓存的内容（静态部分）
    pub cached_content: String,
    /// 动态内容
    pub dynamic_content: String,
}

impl CachedPrompt {
    /// 生成完整 prompt
    pub fn to_full_prompt(&self) -> String {
        if self.dynamic_content.is_empty() {
            self.cached_content.clone()
        } else {
            format!("{}\n\n---\n\n{}", self.cached_content, self.dynamic_content)
        }
    }
}

/// Prompt Composer that assembles prompts from assets
pub struct PromptComposer {
    /// Directory containing asset files
    assets_dir: PathBuf,
    /// Directory containing composition YAML files
    compositions_dir: PathBuf,
    /// In-memory cache of composed prompts
    cache: Arc<RwLock<HashMap<String, String>>>,
    /// In-memory cache of loaded compositions
    compositions: Arc<RwLock<HashMap<String, PromptComposition>>>,
}

impl PromptComposer {
    /// Create a new PromptComposer
    pub fn new(assets_dir: PathBuf, compositions_dir: PathBuf) -> Self {
        Self {
            assets_dir,
            compositions_dir,
            cache: Arc::new(RwLock::new(HashMap::new())),
            compositions: Arc::new(RwLock::new(HashMap::new())),
        }
    }

    /// Load all compositions from the compositions directory
    pub async fn load_all(&self) -> anyhow::Result<()> {
        info!("Loading prompt compositions from: {:?}", self.compositions_dir);

        if !self.compositions_dir.exists() {
            warn!("Compositions directory does not exist: {:?}", self.compositions_dir);
            return Ok(());
        }

        let mut compositions = self.compositions.write().await;
        let mut count = 0;

        let mut entries = tokio::fs::read_dir(&self.compositions_dir).await?;
        while let Some(entry) = entries.next_entry().await? {
            let path = entry.path();
            if path.extension().map(|e| e == "yaml").unwrap_or(false) {
                match self.load_composition_file(&path).await {
                    Ok(composition) => {
                        let name = composition.name.clone();
                        info!("Loaded composition: {} (v{})", name, composition.version);
                        compositions.insert(name, composition);
                        count += 1;
                    }
                    Err(e) => {
                        warn!("Failed to load composition {:?}: {}", path, e);
                    }
                }
            }
        }

        info!("Loaded {} prompt compositions", count);
        Ok(())
    }

    /// Load a composition from a YAML file
    async fn load_composition_file(&self, path: &PathBuf) -> anyhow::Result<PromptComposition> {
        let content = tokio::fs::read_to_string(path).await?;
        let composition: PromptComposition = serde_yaml::from_str(&content)?;
        Ok(composition)
    }

    /// Load a specific composition by name
    pub async fn load_composition(&self, name: &str) -> anyhow::Result<PromptComposition> {
        // Check cache first
        {
            let compositions = self.compositions.read().await;
            if let Some(composition) = compositions.get(name) {
                return Ok(composition.clone());
            }
        }

        // Try to load from file
        let composition_path = self.compositions_dir.join(format!("{}.yaml", name));
        if composition_path.exists() {
            let composition = self.load_composition_file(&composition_path).await?;
            let mut compositions = self.compositions.write().await;
            compositions.insert(name.to_string(), composition.clone());
            return Ok(composition);
        }

        Err(anyhow::anyhow!("Composition not found: {}", name))
    }

    /// Compose a complete prompt from a composition
    pub async fn compose(&self, name: &str) -> anyhow::Result<String> {
        // Check cache first
        {
            let cache = self.cache.read().await;
            if let Some(prompt) = cache.get(name) {
                debug!("Returning cached prompt: {}", name);
                return Ok(prompt.clone());
            }
        }

        // Load composition
        let composition = self.load_composition(name).await?;

        // Compose prompt from sections
        let mut parts = Vec::new();

        for section in composition.get_static_sections() {
            let content = if let Some(asset) = &section.asset {
                // Load from asset file
                let asset_path = self.assets_dir.join(asset);
                match tokio::fs::read_to_string(&asset_path).await {
                    Ok(content) => content,
                    Err(e) => {
                        if section.required {
                            return Err(anyhow::anyhow!(
                                "Failed to load required asset {:?}: {}",
                                asset_path,
                                e
                            ));
                        } else {
                            debug!("Skipping optional asset {:?}: {}", asset_path, e);
                            continue;
                        }
                    }
                }
            } else if let Some(template) = &section.template {
                // Use inline template
                template.clone()
            } else {
                if section.required {
                    return Err(anyhow::anyhow!(
                        "Section '{}' has neither asset nor template",
                        section.id
                    ));
                }
                continue;
            };

            parts.push(content);
        }

        let prompt = parts.join("\n\n");

        // Cache the result
        {
            let mut cache = self.cache.write().await;
            cache.insert(name.to_string(), prompt.clone());
        }

        info!("Composed prompt '{}' with {} sections", name, composition.get_static_sections().len());
        Ok(prompt)
    }

    /// 组装静态部分（可缓存）
    pub async fn compose_static(&self, name: &str) -> anyhow::Result<String> {
        // 静态部分可以永久缓存，因为不依赖运行时上下文
        let cache_key = format!("{}:static", name);

        {
            let cache = self.cache.read().await;
            if let Some(prompt) = cache.get(&cache_key) {
                debug!("Returning cached static prompt: {}", name);
                return Ok(prompt.clone());
            }
        }

        let composition = self.load_composition(name).await?;
        let static_part = self.compose_static_from(&composition).await?;

        // 缓存静态部分
        {
            let mut cache = self.cache.write().await;
            cache.insert(cache_key, static_part.clone());
        }

        Ok(static_part)
    }

    /// 从 composition 组装静态部分
    async fn compose_static_from(&self, composition: &PromptComposition) -> anyhow::Result<String> {
        let mut parts = Vec::new();

        for section in composition.get_static_sections() {
            let content = self.load_section_content(section).await?;
            parts.push(content);
        }

        Ok(parts.join("\n\n"))
    }

    /// 加载单个 section 的内容
    async fn load_section_content(
        &self,
        section: &super::app::PromptSection,
    ) -> anyhow::Result<String> {
        if let Some(asset) = &section.asset {
            let asset_path = self.assets_dir.join(asset);
            match tokio::fs::read_to_string(&asset_path).await {
                Ok(content) => Ok(content),
                Err(e) => {
                    if section.required {
                        Err(anyhow::anyhow!(
                            "Failed to load required asset {:?}: {}",
                            asset_path,
                            e
                        ))
                    } else {
                        debug!("Skipping optional asset {:?}: {}", asset_path, e);
                        Ok(String::new())
                    }
                }
            }
        } else if let Some(template) = &section.template {
            Ok(template.clone())
        } else {
            if section.required {
                Err(anyhow::anyhow!(
                    "Section '{}' has neither asset nor template",
                    section.id
                ))
            } else {
                Ok(String::new())
            }
        }
    }

    /// 组装完整 prompt（静态 + 动态上下文）
    pub async fn compose_with_context(
        &self,
        name: &str,
        context: &ExecutionContext,
    ) -> anyhow::Result<ComposedPrompt> {
        let composition = self.load_composition(name).await?;

        // 1. 组装静态部分
        let static_part = self.compose_static_from(&composition).await?;

        // 2. 根据槽位定义组装动态部分
        let mut dynamic_parts = Vec::new();
        for slot in &composition.context_slots {
            let content = self.build_slot_content(slot, context).await?;
            if !content.is_empty() {
                let slot_id = slot.slot_id();
                dynamic_parts.push((slot_id, content));
            }
        }

        // 3. 组合最终输出
        let separator = composition.output_structure
            .as_ref()
            .map(|o| o.separator.clone())
            .unwrap_or_else(|| "\n\n---\n\n".to_string());

        let static_token_count = estimate_tokens(&static_part);

        Ok(ComposedPrompt {
            static_part,
            dynamic_parts,
            separator,
            cache_hint: CacheHint {
                static_token_count,
                cacheable: true,
            },
        })
    }

    /// 构建单个槽位内容
    async fn build_slot_content(
        &self,
        slot: &super::app::ContextSlot,
        context: &ExecutionContext,
    ) -> anyhow::Result<String> {
        // 1. 如果使用预设，获取预设内容
        if let Some(preset) = &slot.preset {
            return self.build_preset_content(preset, &slot.config, context).await;
        }

        // 2. 自定义槽位：根据 source 类型处理
        if let Some(source) = &slot.source {
            match source.source_type {
                SlotSourceType::Template => {
                    self.build_template_content(source, context).await
                }
                SlotSourceType::Function => {
                    // 函数调用暂不实现，返回空
                    warn!("Function-based slot sources not yet implemented: {:?}", source.function);
                    Ok(String::new())
                }
                SlotSourceType::File => {
                    self.build_file_content(source).await
                }
            }
        } else {
            Ok(String::new())
        }
    }

    /// 构建预设槽位内容
    async fn build_preset_content(
        &self,
        preset: &ContextSlotPreset,
        config: &HashMap<String, serde_json::Value>,
        context: &ExecutionContext,
    ) -> anyhow::Result<String> {
        match preset {
            ContextSlotPreset::CurrentState => {
                self.build_current_state(config, context).await
            }
            ContextSlotPreset::ExecutionHistory => {
                let max_events = config.get("max_events")
                    .and_then(|v| v.as_u64())
                    .unwrap_or(10) as usize;
                self.build_execution_history(context, max_events).await
            }
            ContextSlotPreset::TaskGoal => {
                self.build_task_goal(config, context).await
            }
            ContextSlotPreset::Artifacts => {
                let max_tokens = config.get("max_tokens")
                    .and_then(|v| v.as_u64())
                    .unwrap_or(2000) as usize;
                self.build_artifacts(context, max_tokens).await
            }
            ContextSlotPreset::ConversationHistory => {
                let max_turns = config.get("max_turns")
                    .and_then(|v| v.as_u64())
                    .unwrap_or(5) as usize;
                self.build_conversation_history(context, max_turns).await
            }
            ContextSlotPreset::ToolResults => {
                let include_errors = config.get("include_errors")
                    .and_then(|v| v.as_bool())
                    .unwrap_or(true);
                self.build_tool_results(context, include_errors).await
            }
            ContextSlotPreset::ErrorContext => {
                let include_stack_trace = config.get("include_stack_trace")
                    .and_then(|v| v.as_bool())
                    .unwrap_or(false);
                self.build_error_context(context, include_stack_trace).await
            }
        }
    }

    /// 构建模板内容
    async fn build_template_content(
        &self,
        source: &super::app::SlotSource,
        context: &ExecutionContext,
    ) -> anyhow::Result<String> {
        if let Some(template) = &source.template {
            let mut result = template.clone();

            // 替换变量
            for (key, path) in &source.variables {
                let value = self.resolve_variable(path, context);
                result = result.replace(&format!("{{{{{}}}}}", key), &value);
            }

            // 替换内置变量
            result = result
                .replace("{{step_number}}", &context.step_number.to_string())
                .replace("{{current_phase}}", &context.current_phase)
                .replace("{{task_goal}}", &context.task_goal)
                .replace("{{token_estimate}}", &context.token_budget.to_string());

            Ok(result)
        } else {
            Ok(String::new())
        }
    }

    /// 构建文件内容
    async fn build_file_content(
        &self,
        source: &super::app::SlotSource,
    ) -> anyhow::Result<String> {
        if let Some(file) = &source.file {
            let path = self.assets_dir.join(file);
            match tokio::fs::read_to_string(&path).await {
                Ok(content) => Ok(content),
                Err(e) => {
                    warn!("Failed to load slot file {:?}: {}", path, e);
                    Ok(String::new())
                }
            }
        } else {
            Ok(String::new())
        }
    }

    /// 解析变量路径
    fn resolve_variable(&self, path: &str, context: &ExecutionContext) -> String {
        match path {
            "context.step_number" => context.step_number.to_string(),
            "context.current_phase" => context.current_phase.clone(),
            "context.task_goal" => context.task_goal.clone(),
            "context.token_budget" => context.token_budget.to_string(),
            _ => String::new(),
        }
    }

    // ===== 预设内容构建器 =====

    async fn build_current_state(
        &self,
        config: &HashMap<String, serde_json::Value>,
        context: &ExecutionContext,
    ) -> anyhow::Result<String> {
        let include_artifacts = config.get("include_artifacts_summary")
            .and_then(|v| v.as_bool())
            .unwrap_or(true);

        let mut content = format!(
            "## Current State\n\n**Phase:** {}\n**Step:** {}\n",
            context.current_phase, context.step_number
        );

        if include_artifacts && !context.artifacts_text.is_empty() {
            content.push_str(&format!("\n**Artifacts Available:** Yes\n"));
        }

        Ok(content)
    }

    async fn build_execution_history(
        &self,
        context: &ExecutionContext,
        _max_events: usize,
    ) -> anyhow::Result<String> {
        if context.events_text.is_empty() {
            return Ok(String::new());
        }

        Ok(format!("## Execution History\n\n{}", context.events_text))
    }

    async fn build_task_goal(
        &self,
        config: &HashMap<String, serde_json::Value>,
        context: &ExecutionContext,
    ) -> anyhow::Result<String> {
        let include_constraints = config.get("include_constraints")
            .and_then(|v| v.as_bool())
            .unwrap_or(true);

        let mut content = format!("## Task Goal\n\n{}\n", context.task_goal);

        if include_constraints && !context.constraints.is_empty() {
            content.push_str("\n### Constraints\n");
            for c in &context.constraints {
                content.push_str(&format!("- {}\n", c));
            }
        }

        Ok(content)
    }

    async fn build_artifacts(
        &self,
        context: &ExecutionContext,
        max_tokens: usize,
    ) -> anyhow::Result<String> {
        if context.artifacts_text.is_empty() {
            return Ok(String::new());
        }

        // 简单截断到 max_tokens
        let content = if estimate_tokens(&context.artifacts_text) > max_tokens {
            // 按 token 估算截断（每 4 字符约 1 token）
            let char_limit = max_tokens * 4;
            format!("{}\n\n... [truncated]", &context.artifacts_text[..char_limit.min(context.artifacts_text.len())])
        } else {
            context.artifacts_text.clone()
        };

        Ok(format!("## Artifacts\n\n{}", content))
    }

    async fn build_conversation_history(
        &self,
        _context: &ExecutionContext,
        _max_turns: usize,
    ) -> anyhow::Result<String> {
        // TODO: 实现对话历史
        Ok(String::new())
    }

    async fn build_tool_results(
        &self,
        context: &ExecutionContext,
        _include_errors: bool,
    ) -> anyhow::Result<String> {
        if context.tool_results_text.is_empty() {
            return Ok(String::new());
        }

        Ok(format!("## Tool Results\n\n{}", context.tool_results_text))
    }

    async fn build_error_context(
        &self,
        context: &ExecutionContext,
        _include_stack_trace: bool,
    ) -> anyhow::Result<String> {
        if context.error_text.is_empty() {
            return Ok(String::new());
        }

        Ok(format!("## Error Context\n\n{}", context.error_text))
    }

    /// Force reload a composition and re-compose the prompt
    pub async fn reload(&self, name: &str) -> anyhow::Result<()> {
        // Remove from compositions cache
        {
            let mut compositions = self.compositions.write().await;
            compositions.remove(name);
        }

        // Remove from prompt cache
        {
            let mut cache = self.cache.write().await;
            cache.remove(name);
        }

        // Re-load and compose
        self.load_composition(name).await?;
        self.compose(name).await?;

        info!("Reloaded prompt composition: {}", name);
        Ok(())
    }

    /// Clear all caches
    pub async fn clear_cache(&self) {
        let mut cache = self.cache.write().await;
        cache.clear();

        let mut compositions = self.compositions.write().await;
        compositions.clear();

        debug!("Prompt composer cache cleared");
    }

    /// List all available compositions
    pub async fn list_compositions(&self) -> Vec<String> {
        let compositions = self.compositions.read().await;
        compositions.keys().cloned().collect()
    }

    /// List all asset files in the assets directory
    pub async fn list_assets(&self) -> anyhow::Result<Vec<String>> {
        let mut assets = Vec::new();

        if !self.assets_dir.exists() {
            return Ok(assets);
        }

        self.list_assets_recursive(&self.assets_dir, &mut assets).await?;
        Ok(assets)
    }

    /// Recursively list asset files
    async fn list_assets_recursive(&self, dir: &PathBuf, assets: &mut Vec<String>) -> anyhow::Result<()> {
        let mut entries = tokio::fs::read_dir(dir).await?;
        let base = &self.assets_dir;

        while let Some(entry) = entries.next_entry().await? {
            let path = entry.path();
            if path.is_dir() {
                Box::pin(self.list_assets_recursive(&path, assets)).await?;
            } else if path.extension().map(|e| e == "md").unwrap_or(false) {
                // Get relative path from assets_dir
                if let Ok(relative) = path.strip_prefix(base) {
                    assets.push(relative.to_string_lossy().to_string());
                }
            }
        }

        Ok(())
    }

    /// Get an asset's content by path
    pub async fn get_asset(&self, relative_path: &str) -> anyhow::Result<String> {
        let asset_path = self.assets_dir.join(relative_path);
        let content = tokio::fs::read_to_string(&asset_path).await?;
        Ok(content)
    }

    /// Validate a composition (check all required assets exist)
    pub async fn validate(&self, name: &str) -> anyhow::Result<Vec<String>> {
        let composition = self.load_composition(name).await?;
        let mut errors = Vec::new();

        for section in &composition.sections {
            if let Some(asset) = &section.asset {
                let asset_path = self.assets_dir.join(asset);
                if !asset_path.exists() {
                    errors.push(format!(
                        "Section '{}': asset not found: {:?}",
                        section.id, asset
                    ));
                }
            }
        }

        Ok(errors)
    }
}

/// 估算文本的 token 数量（简单实现：4 字符 ≈ 1 token）
fn estimate_tokens(text: &str) -> usize {
    text.len() / 4
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;
    use tokio::io::AsyncWriteExt;

    #[tokio::test]
    async fn test_compose_prompt() {
        let temp_dir = TempDir::new().unwrap();
        let assets_dir = temp_dir.path().join("assets");
        let compositions_dir = temp_dir.path().join("compositions");

        // Create directories
        tokio::fs::create_dir_all(&assets_dir).await.unwrap();
        tokio::fs::create_dir_all(&compositions_dir).await.unwrap();

        // Create asset file
        let identity_asset = assets_dir.join("identity/test_identity.md");
        tokio::fs::create_dir_all(identity_asset.parent().unwrap()).await.unwrap();
        let mut file = tokio::fs::File::create(&identity_asset).await.unwrap();
        file.write_all(b"# Test Identity\n\nYou are a test agent.").await.unwrap();

        // Create composition file
        let composition = PromptComposition {
            name: "test".to_string(),
            description: "Test composition".to_string(),
            version: "1.0".to_string(),
            static_sections: vec![],
            sections: vec![
                super::super::app::PromptSection {
                    id: "identity".to_string(),
                    asset: Some(PathBuf::from("identity/test_identity.md")),
                    template: None,
                    required: true,
                },
                super::super::app::PromptSection {
                    id: "reminder".to_string(),
                    asset: None,
                    template: Some("## Remember\n- Output JSON only".to_string()),
                    required: true,
                },
            ],
            context_slots: vec![],
            output_structure: None,
        };

        let composition_path = compositions_dir.join("test.yaml");
        let composition_yaml = serde_yaml::to_string(&composition).unwrap();
        let mut file = tokio::fs::File::create(&composition_path).await.unwrap();
        file.write_all(composition_yaml.as_bytes()).await.unwrap();

        // Create composer and load
        let composer = PromptComposer::new(assets_dir, compositions_dir);
        composer.load_all().await.unwrap();

        // Compose prompt
        let prompt = composer.compose("test").await.unwrap();

        assert!(prompt.contains("Test Identity"));
        assert!(prompt.contains("Output JSON only"));
    }
}
