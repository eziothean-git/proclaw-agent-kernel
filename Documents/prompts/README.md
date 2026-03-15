# XML/Markdown 双格式提示词资产管理方案

## 目录结构

```
data/prompts/
├── xml/           # 纯 XML 格式提示词（结构化最强）
├── md/            # 纯 Markdown 格式提示词（可读性最强）
├── hybrid/        # 混合格式（推荐）
└── config.yaml    # 格式配置文件
```

## 三种格式对比

| 维度 | XML | Markdown | Hybrid (推荐) |
|------|-----|----------|---------------|
| **Claude 亲和力** | ⭐⭐⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| **人类可读性** | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| **结构清晰度** | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐⭐ |
| **编辑便利性** | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| **向后兼容** | ❌ | ✅ | ✅ |

## 配置文件

```yaml
# data/prompts/config.yaml
composer:
  # 可选: markdown | xml | xml_hybrid
  output_format: xml_hybrid
  
  xml_config:
    use_cdata: true
    include_attributes: true
    root_tag: context
    namespace: http://proclaw.ai/context
  
  # 资产路径配置
  assets:
    base_path: ./data/prompts
    default_format: hybrid
    fallback_format: md

# 提示词映射
prompts:
  prime_system:
    file: prime-system-prompt
    formats: [hybrid, md, xml]
    default: hybrid
  
  task_execution:
    file: task-execution-guide
    formats: [xml, hybrid]
    default: xml
```

## 迁移步骤

### Phase 1: 代码修改（已完成 ✅）

1. **添加 OutputFormat 枚举** (`src/config/dynamic.rs`)
   - `Markdown` - 现有格式，向后兼容
   - `Xml` - 纯 XML 结构化
   - `XmlHybrid` - XML + CDATA 包裹 Markdown

2. **修改 BlockComposerEngine** (`src/block_composer/mod.rs`)
   - 添加 `output_format` 字段
   - 添加 `compose_markdown()` 方法
   - 添加 `compose_xml()` 方法
   - 添加 `compose_xml_hybrid()` 方法
   - 添加 `set_output_format()` 方法

3. **导出配置类型** (`src/config/mod.rs`)
   - 导出 `OutputFormat`, `XmlConfig`, `DynamicComposerConfig`

### Phase 2: 资产创建（已完成 ✅）

创建三种格式的示例提示词：
- `data/prompts/xml/prime-system-prompt.xml`
- `data/prompts/md/prime-system-prompt.md`
- `data/prompts/hybrid/prime-system-prompt.md.xml`

### Phase 3: 初始化配置

在主程序中初始化配置：

```rust
// src/main.rs
use proclaw_block_composer::config::{init_global_config, OutputFormat};
use std::path::PathBuf;

#[tokio::main]
async fn main() -> anyhow::Result<()> {
    // 初始化动态配置
    let config_path = PathBuf::from("./data/config/dynamic.yaml");
    init_global_config(config_path).await?;
    
    // 启动服务...
}
```

### Phase 4: 运行时切换

通过动态配置热切换格式：

```rust
// 在 Prime Personality 或其他组件中
use proclaw_block_composer::config::get_global_config;

async fn update_composer_format() {
    if let Some(config_manager) = get_global_config() {
        let config = config_manager.get_config().await;
        let format = config.composer.output_format;
        
        // 应用到 BlockComposerEngine
        composer_engine.set_output_format(format);
    }
}
```

## 使用建议

### 场景 1: 存量系统迁移
```yaml
composer:
  output_format: markdown  # 保持现有行为
```

### 场景 2: 新系统启用 XML
```yaml
composer:
  output_format: xml_hybrid  # 推荐
```

### 场景 3: A/B 测试
```yaml
composer:
  ab_test:
    enabled: true
    control_group:
      output_format: markdown
    treatment_group:
      output_format: xml_hybrid
```

## 输出示例对比

### Markdown 格式
```
### system_identity
You are the Prime Personality...

### task_goal
实现用户认证功能

### observations
## Recent Actions
[Step 1] bash.execute: ls -la
```

### XML Hybrid 格式
```xml
<?xml version="1.0" encoding="UTF-8"?>
<context profile="prime">
  <block id="system_identity" type="1" priority="100">
    <![CDATA[You are the Prime Personality...]]>
  </block>
  <block id="task_goal" type="7" priority="100">
    <![CDATA[实现用户认证功能]]>
  </block>
  <block id="observations" type="10" priority="80">
    <![CDATA[## Recent Actions
[Step 1] bash.execute: ls -la]]>
  </block>
</context>
```

## 下一步

1. ✅ 代码修改完成
2. ✅ 资产创建完成
3. ⏳ 集成到 main.rs 初始化配置
4. ⏳ 在 Prime Personality 中使用配置
5. ⏳ 添加配置热重载支持
6. ⏳ A/B 测试验证效果

## 验证命令

```bash
# 构建项目
cd kernel-v2
cargo build --release --features control-plane

# 运行测试
cargo test

# 检查配置加载
./target/release/proclaw-composer --config ./config/composer.yaml
```
