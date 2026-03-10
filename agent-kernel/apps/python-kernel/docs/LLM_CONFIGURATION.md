# LLM Configuration Guide

## 支持的 LLM 提供商

### 1. Kimi CodePlan (默认推荐)

**配置:**
```bash
export LLM_PROVIDER=kimi
export KIMI_API_KEY="sk-kimi-fiIa9rIPAEHxTVxaaW5Igg4wzoX6w3IAKchclTbD62mdbKxJ11BuR8sYSucPibdP"
export KIMI_MODEL="kimi-k2.5"  # 或其他可用模型
```

**在代码中配置:**
```python
from llm_client import configure_llm

client = configure_llm(
    provider="kimi",
    api_key="sk-kimi-fiIa9rIPAEHxTVxaaW5Igg4wzoX6w3IAKchclTbD62mdbKxJ11BuR8sYSucPibdP",
    model="kimi-k2.5",
)
```

---

### 2. OpenAI

**配置:**
```bash
export LLM_PROVIDER=openai
export OPENAI_API_KEY="sk-..."
export OPENAI_MODEL="gpt-4"  # 或 gpt-3.5-turbo
```

**可选自定义 Base URL (用于代理):**
```bash
export OPENAI_BASE_URL="https://your-proxy.com/v1"
```

---

### 3. 自定义 OpenAI 兼容 API

**配置:**
```bash
export LLM_PROVIDER=custom
export CUSTOM_API_KEY="your-key"
export CUSTOM_BASE_URL="https://api.example.com/v1"
export CUSTOM_MODEL="model-name"
```

---

## 快速开始

### 方法一：环境变量（推荐）

创建 `.env` 文件:
```bash
# 选择提供商: kimi, openai, custom
LLM_PROVIDER=kimi

# Kimi 配置
KIMI_API_KEY=sk-kimi-fiIa9rIPAEHxTVxaaW5Igg4wzoX6w3IAKchclTbD62mdbKxJ11BuR8sYSucPibdP
KIMI_MODEL=kimi-k2.5

# 可选参数
LLM_TEMPERATURE=0.7
LLM_MAX_TOKENS=4000
```

然后在 Python 中:
```python
from llm_client import get_llm_client

client = get_llm_client()
client.initialize(system_prompt="You are a helpful assistant.")

# 使用
result = await client.generate("Hello, world!")
```

---

### 方法二：显式配置

```python
from llm_client import configure_llm

# 配置 Kimi
client = configure_llm(
    provider="kimi",
    api_key="your-kimi-key",
    model="kimi-k2.5",
    temperature=0.7,
    max_tokens=4000,
)

# 初始化
client.initialize(system_prompt="Your system prompt here")

# 生成
result = await client.generate("Your prompt here")
```

---

## 在 Agent Thread 中使用

### 环境变量方式

```bash
export LLM_PROVIDER=kimi
export KIMI_API_KEY="your-key"
export KERNEL_RUN_MODE=real

python your_script.py
```

```python
from thread_runtime.agent_thread import AgentThread

# Agent Thread 会自动使用配置好的 LLM
agent = AgentThread(task=task, compiled_context=context)
result = await agent.run()  # 将使用 Kimi API
```

---

### 显式配置方式

```python
from llm_client import configure_llm
from thread_runtime.agent_thread import AgentThread

# 先配置 LLM
configure_llm(
    provider="kimi",
    api_key="your-key",
    model="kimi-k2.5",
)

# 设置运行模式
import os
os.environ["KERNEL_RUN_MODE"] = "real"

# 创建并运行 Agent
agent = AgentThread(task=task, compiled_context=context)
result = await agent.run()
```

---

## 测试 LLM 连接

运行测试脚本:
```bash
# 测试 Kimi
export LLM_PROVIDER=kimi
export KIMI_API_KEY="your-key"
python tests/test_llm.py

# 测试 OpenAI
export LLM_PROVIDER=openai
export OPENAI_API_KEY="your-key"
python tests/test_llm.py
```

---

## 故障排查

### 错误："No API key configured"
**解决:** 确保设置了对应的环境变量:
```bash
# Kimi
export KIMI_API_KEY="your-key"

# OpenAI
export OPENAI_API_KEY="your-key"
```

### 错误："Failed to initialize LLM client"
**解决:** 
1. 检查 API Key 是否正确
2. 检查网络连接
3. 查看日志获取详细信息

### 错误："Generation failed"
**解决:**
1. 检查模型名称是否正确
2. 检查 API Key 是否有足够额度
3. 尝试降低 max_tokens

---

## 模型推荐

### Kimi CodePlan
- **kimi-k2.5**: 推荐，性能均衡
- **kimi-k1.5**: 更快，适合简单任务

### OpenAI
- **gpt-4**: 最强性能
- **gpt-3.5-turbo**: 性价比高
- **gpt-4-turbo**: 最新版本

### 自定义
根据你的 API 提供商选择合适的模型名称。
