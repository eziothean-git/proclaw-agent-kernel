# Prompt 缓存优化方案

## 概述

ProClaw 的上下文系统实现了静态/动态分离的 prompt 组装，通过针对不同 LLM 提供商的缓存优化策略，实现：

- **最大化缓存命中率** - 通过优化 prompt 结构布局
- **支持多模型适配** - DeepSeek, Kimi, GLM, MiniMax, Claude
- **降低 token 成本** - 预计减少 40-60% 的 token 开销

## 架构设计

### 静态/动态分离

```
┌─────────────────────────────────────────────────────────────────┐
│  SYSTEM MESSAGE (可缓存 - ~2000 tokens, 70-80%)                 │
├─────────────────────────────────────────────────────────────────┤
│  Tier 1: 核心身份 (~300 tokens)                                 │
│  - identity/thread_identity.md                                  │
│  - 稳定性: 永不变化                                              │
│  - 缓存命中率: 95%+                                              │
├─────────────────────────────────────────────────────────────────┤
│  Tier 2: 能力定义 (~400 tokens)                                 │
│  - capabilities/available_tools.md                              │
│  - 稳定性: 仅系统更新时变化                                       │
│  - 缓存命中率: 90%                                               │
├─────────────────────────────────────────────────────────────────┤
│  Tier 3: 输出规范 (~500 tokens)                                 │
│  - schemas/thread_schema.md                                     │
│  - rules/json_only.md                                           │
│  - 稳定性: 跨版本稳定                                            │
│  - 缓存命中率: 80%                                               │
├─────────────────────────────────────────────────────────────────┤
│  Tier 4: 行为规则 (~300 tokens)                                 │
│  - rules/common_mistakes.md                                     │
│  - 稳定性: 可调优                                                │
│  - 缓存命中率: 60%                                               │
├─────────────────────────────────────────────────────────────────┤
│  Tier 5: Few-shot 示例 (~500 tokens)                            │
│  - examples/thread_examples.md                                  │
│  - 稳定性: 可 A/B 测试                                           │
│  - 缓存命中率: 40%                                               │
├─────────────────────────────────────────────────────────────────┤
│  USER MESSAGE (不缓存)                                          │
│  - current_state (phase, step)                                  │
│  - task_goal (用户请求)                                          │
│  - execution_history (事件历史)                                  │
│  - artifacts (已产生工件)                                        │
│  - tool_results (工具结果)                                       │
│  - error_context (错误信息)                                      │
│  缓存命中率: 0%                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Provider 特定缓存策略

### 1. Claude (Anthropic)

Claude 支持 `cache_control` 参数来标记缓存边界：

```rust
// Claude 格式消息
pub fn to_claude_messages(&self) -> Vec<CacheAwareMessage> {
    vec![
        // 静态部分作为第一个 user message，标记为持久缓存
        CacheAwareMessage::user(&self.static_part)
            .with_cache_control(CacheControl::Persistent),
        // 助手确认消息
        CacheAwareMessage::assistant("Understood. I'm ready to help."),
        // 动态部分作为后续 user message，标记为短期缓存
        CacheAwareMessage::user(&self.to_dynamic_content())
            .with_cache_control(CacheControl::Ephemeral),
    ]
}
```

**API 请求格式：**
```json
{
  "messages": [
    {
      "role": "user",
      "content": [
        {"type": "text", "text": "<static_content>"},
        {"type": "text", "text": "<dynamic_content>", "cache_control": {"type": "ephemeral"}}
      ]
    }
  ]
}
```

**特点：**
- TTL: 5 分钟 (persistent) 或 1 小时 (ephemeral)
- 成本折扣: 90% (cached tokens)

### 2. OpenAI 兼容 API (DeepSeek, Kimi, GLM, MiniMax)

这些 provider 通常会自动缓存 system message 前缀：

```rust
// OpenAI 兼容格式消息
pub fn to_openai_messages(&self) -> Vec<CacheAwareMessage> {
    vec![
        // 静态部分作为 system message（自动被 provider 缓存）
        CacheAwareMessage::system(&self.static_part),
        // 动态部分作为 user message
        CacheAwareMessage::user(&self.to_dynamic_content()),
    ]
}
```

**API 请求格式：**
```json
{
  "messages": [
    {
      "role": "system",
      "content": "<static_content>"
    },
    {
      "role": "user",
      "content": "<dynamic_content>"
    }
  ]
}
```

**特点：**
- 无需显式 cache_control
- System message 自动作为缓存前缀
- 成本折扣: ~50-70%

## 数据模型

### CacheControl

```rust
/// 缓存控制类型
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum CacheControl {
    /// 短期缓存（约1小时，Claude ephemeral）
    Ephemeral,
    /// 长期缓存（约5分钟，但更可靠，Claude persistent）
    Persistent,
}
```

### CacheAwareMessage

```rust
/// 带缓存控制的消息
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CacheAwareMessage {
    /// 角色：system, user, assistant
    pub role: String,
    /// 消息内容
    pub content: String,
    /// 缓存控制（仅 Claude API 使用）
    #[serde(skip_serializing_if = "Option::is_none")]
    pub cache_control: Option<CacheControl>,
}
```

### CacheAwareResponse

```rust
/// 带缓存统计的 LLM 响应
#[derive(Debug, Clone, Deserialize)]
pub struct CacheAwareResponse {
    pub choices: Vec<Choice>,
    pub usage: Option<Usage>,
    /// 从缓存读取的输入 token 数
    #[serde(default)]
    pub cache_read_input_tokens: Option<usize>,
    /// 创建缓存时的输入 token 数
    #[serde(default)]
    pub cache_creation_input_tokens: Option<usize>,
}
```

### LLMProvider

```rust
/// LLM 提供商类型
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum LLMProvider {
    Claude,
    DeepSeek,
    Kimi,
    GLM,
    MiniMax,
    OpenAI,
    Unknown,
}

impl LLMProvider {
    /// 从 base URL 推断提供商类型
    pub fn from_base_url(url: &str) -> Self;

    /// 是否支持 Claude 风格的 cache_control
    pub fn supports_cache_control(&self) -> bool;

    /// 是否支持 system message 缓存
    pub fn supports_system_prefix_cache(&self) -> bool;
}
```

## YAML Composition 配置

### thread.yaml 示例

```yaml
name: thread
description: "Agent Thread Executor System Prompt"
version: "3.0"

# 缓存配置
cache_config:
  default_strategy: auto  # auto | claude | openai | none
  providers:
    claude:
      strategy: persistent
      ttl_seconds: 300
    deepseek:
      strategy: system_prefix
    kimi:
      strategy: system_prefix
    glm:
      strategy: system_prefix
    minimax:
      strategy: system_prefix

# 静态部分（按缓存优先级排序）
static_sections:
  - id: identity
    asset: "identity/thread_identity.md"
    required: true
    cache_priority: 1

  - id: format
    asset: "rules/json_only.md"
    required: true
    cache_priority: 2

  - id: schema
    asset: "schemas/thread_schema.md"
    required: true
    cache_priority: 3

  - id: structure
    asset: "rules/thread_structure.md"
    required: true
    cache_priority: 3

  - id: examples
    asset: "examples/thread_examples.md"
    required: true
    cache_priority: 4

  - id: mistakes
    asset: "rules/common_mistakes.md"
    required: false
    cache_priority: 5

# 动态上下文槽位
context_slots:
  - preset: current_state
    position: after_static
  - preset: task_goal
    position: after_static
  - preset: execution_history
    position: after_static
    config:
      max_events: 10
  - preset: artifacts
    position: after_static
    config:
      max_tokens: 2000
  - preset: tool_results
    position: after_static
  - preset: error_context
    position: after_static
    required: false

output_structure:
  format: "markdown"
  separator: "\n\n---\n\n"
```

## Token 计数

### Tiktoken 集成

```rust
use tiktoken_rs::cl100k_base;

pub struct TokenCounter {
    encoder: tiktoken_rs::CoreBPE,
}

impl TokenCounter {
    pub fn new() -> Self {
        Self {
            encoder: cl100k_base().unwrap(),
        }
    }

    pub fn count_tokens(&self, text: &str) -> usize {
        self.encoder.encode_with_special_tokens(text).len()
    }

    pub fn truncate_to_tokens(&self, text: &str, max_tokens: usize) -> String;

    pub fn chunk_text(&self, text: &str, max_tokens_per_chunk: usize) -> Vec<String>;
}
```

### 估算 vs 精确计数

- **估算**: `len() / 4` (4 字符 ≈ 1 token)
- **精确**: tiktoken cl100k_base 编码

## Prometheus 指标

### 缓存指标

```rust
pub struct CacheMetrics {
    /// 缓存命中次数
    pub cache_hits: Counter,
    /// 缓存未命中次数
    pub cache_misses: Counter,
    /// 节省的 token 数量
    pub tokens_saved: Counter,
    /// 缓存命中率
    pub hit_rate: Gauge,
    /// 缓存查找延迟
    pub lookup_latency: Histogram,
}
```

### 示例指标输出

```
# HELP proclaw_cache_hits_total Total cache hits
# TYPE proclaw_cache_hits_total counter
proclaw_cache_hits_total{provider="deepseek"} 1234
proclaw_cache_hits_total{provider="claude"} 567

# HELP proclaw_cache_tokens_saved_total Total tokens saved by caching
# TYPE proclaw_cache_tokens_saved_total counter
proclaw_cache_tokens_saved_total{provider="deepseek"} 45678

# HELP proclaw_cache_hit_rate Current cache hit rate
# TYPE proclaw_cache_hit_rate gauge
proclaw_cache_hit_rate{provider="deepseek"} 0.96
```

## 验证方案

### 单元测试

```bash
cd kernel-v2
cargo test --lib config::prompt_composer
cargo test --lib llm::models
cargo test --lib observability::cache_metrics
cargo test --lib utils::token_counter
```

### 集成测试

```bash
# 测试 Claude 格式消息生成
cargo test test_claude_messages

# 测试 OpenAI 格式消息生成
cargo test test_openai_messages
```

### 端到端验证

```bash
# 启动服务
./proclaw.sh start

# 发送测试请求
curl -s -X POST http://localhost:3000/api/v1/chat \
    -H "Content-Type: application/json" \
    -d '{"message": "测试", "session_id": "test", "user_id": "test"}'

# 检查缓存指标
curl http://localhost:9090/metrics | grep proclaw_cache
```

## 预期结果

| 指标 | 目标值 |
|------|--------|
| 缓存命中率 (相同 session) | >80% |
| Token 成本降低 | 40-60% |
| 响应延迟降低 (缓存命中) | 20-30% |
| 静态部分占比 | 70-80% |

## 文件清单

| 文件 | 说明 |
|------|------|
| `kernel-v2/src/llm/models.rs` | CacheControl, CacheAwareMessage, CacheAwareResponse, LLMProvider |
| `kernel-v2/src/config/prompt_composer.rs` | to_claude_messages(), to_openai_messages() |
| `kernel-v2/src/utils/token_counter.rs` | Tiktoken 精确计数 |
| `kernel-v2/src/observability/cache_metrics.rs` | Prometheus 指标 |
| `kernel-v2/prompts/compositions/thread.yaml` | Thread 缓存配置 |
| `kernel-v2/prompts/compositions/prime.yaml` | Prime 缓存配置 |

## 未来优化

1. **动态缓存 TTL** - 根据内容变化频率调整 TTL
2. **跨 Session 缓存共享** - 共享静态部分缓存
3. **智能截断** - 根据 token 预算动态调整动态部分
4. **A/B 测试** - 测试不同 prompt 结构的缓存效果
