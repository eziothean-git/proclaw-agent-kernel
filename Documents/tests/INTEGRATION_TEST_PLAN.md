# Atomic Agent + Ark LLM 集成测试计划

## 测试目标

验证 Atomic Agent Thread + Ark (火山方舟) LLM 的完整集成链路，确保：
1. ✅ Ark LLM API 连接正常
2. ✅ Atomic Agent Thread 能正确调用 LLM
3. ✅ SEE-ACT-UPDATE 循环工作正常
4. ✅ Event Log + Working Set 架构正确
5. ✅ 工具执行流程完整
6. ✅ 阶段转换 (Explore → Execute → Complete) 正确

## 环境配置

### 1. 环境变量

```bash
# Ark API 配置
export ARK_API_KEY="your-ark-api-key"
export ARK_MODEL="glm-4-7-251222"  # 或 doubao-1-5-pro-32k-250115
export ARK_BASE_URL="https://ark.cn-beijing.volces.com/api/v3"

# Kernel 配置
export KERNEL_RUN_MODE="real"
export LLM_PROVIDER="ark"
```

### 2. 依赖安装

```bash
cd agent-kernel/apps/python-kernel
pip install -e ".[dev]"
```

## 测试步骤

### 阶段 1: 基础设施测试

#### 1.1 LLM 连接测试

```bash
cd agent-kernel/apps/python-kernel
PYTHONPATH=/home/eziothean/ProClaw/agent-kernel/apps/python-kernel \
  python tests/test_ark_llm.py
```

**预期结果:**
- ✅ LLM client 初始化成功
- ✅ 简单生成测试通过
- ✅ 代码任务解析测试通过

#### 1.2 Atomic Agent 单元测试

```bash
cd agent-kernel/apps/python-kernel
PYTHONPATH=/home/eziothean/ProClaw/agent-kernel/apps/python-kernel \
  python tests/integration_test.py
```

**预期结果:**
- ✅ 50/50 测试通过
- ✅ Working Set Builder 测试通过
- ✅ Event Log 测试通过
- ✅ Agent Output Parser 测试通过
- ✅ Agent Thread 测试通过

#### 1.3 Mock E2E 测试

```bash
cd agent-kernel/apps/python-kernel
PYTHONPATH=/home/eziothean/ProClaw/agent-kernel/apps/python-kernel \
  python tests/mock_e2e_test.py
```

**预期结果:**
- ✅ Kernel 初始化成功
- ✅ 完整任务执行流程通过
- ✅ 工具执行成功
- ✅ Event Log 正确记录

### 阶段 2: 完整 E2E 测试 (使用真实 LLM)

#### 2.1 运行完整测试

```bash
cd agent-kernel/apps/python-kernel
export ARK_API_KEY="your-ark-api-key"
export ARK_MODEL="glm-4-7-251222"
export KERNEL_RUN_MODE="real"
export LLM_PROVIDER="ark"

PYTHONPATH=/home/eziothean/ProClaw/agent-kernel/apps/python-kernel \
  python tests/e2e_test.py
```

**预期结果:**
- ✅ 所有测试通过
- ✅ 任务成功完成
- ✅ Event Log 包含多个事件
- ✅ 工具执行成功
- ✅ 阶段转换正确

### 阶段 3: Gateway + Python Kernel 集成测试

#### 3.1 启动 Gateway

```bash
cd agent-kernel/apps/gateway
npm run start:dev
```

验证: `curl http://localhost:3000/health` 返回 healthy

#### 3.2 启动 Python Kernel

```bash
cd agent-kernel/apps/python-kernel
export ARK_API_KEY="your-ark-api-key"
export ARK_MODEL="glm-4-7-251222"
export KERNEL_RUN_MODE="real"
export LLM_PROVIDER="ark"
python main.py
```

验证: `curl http://localhost:8000/health` 返回 healthy

#### 3.3 运行集成测试

```bash
cd agent-kernel
npm run test:integration:manual
```

**预期结果:**
- ✅ Gateway 接收请求
- ✅ 写入 inbox
- ✅ Python Kernel 处理请求
- ✅ 回调返回结果
- ✅ 历史记录保存

## 验证清单

### 核心功能验证

- [ ] Ark LLM API 连接成功
- [ ] LLM 生成正确的 YAML 格式输出
- [ ] Agent Output Parser 正确解析意图
- [ ] Tool Call 正确识别和执行
- [ ] Event Log 正确记录所有事件
- [ ] Working Set 构建正确
- [ ] 阶段转换正常 (Explore → Execute → Complete)
- [ ] 上层干预 API 可用

### 性能指标

- [ ] 单次 LLM 调用 < 15s
- [ ] 完整任务执行 < 120s
- [ ] Event Log 记录延迟 < 10ms
- [ ] Working Set 构建 < 100ms

### 错误处理

- [ ] LLM 调用失败时有降级策略
- [ ] 工具执行失败时正确记录错误
- [ ] 超时处理正确
- [ ] 网络错误恢复正确

## 故障排查

### 问题 1: LLM 连接失败

**症状:** `Failed to initialize LLM client`

**解决:**
```bash
# 检查 API Key
echo $ARK_API_KEY

# 检查网络
curl https://ark.cn-beijing.volces.com/api/v3/models \
  -H "Authorization: Bearer $ARK_API_KEY"
```

### 问题 2: Parser 无法识别意图

**症状:** `Unknown intent, continuing`

**解决:**
- 检查 LLM 输出格式是否为正确的 YAML
- 确认 LLM 理解 system prompt 中的格式要求
- 查看日志中的 raw_output 内容

### 问题 3: 工具执行失败

**症状:** `Tool execution failed`

**解决:**
- 检查 skill 是否正确注册
- 查看 Event Log 中的工具调用参数
- 确认工具存在且参数正确

## 测试报告模板

```markdown
## 测试执行报告

**日期:** YYYY-MM-DD
**测试者:** 
**Ark 模型:** glm-4-7-251222
**API Key:** ✅ 已配置

### 测试结果

| 测试项目 | 状态 | 耗时 | 备注 |
|---------|------|------|------|
| LLM 连接测试 | ✅/❌ | Xs | |
| 单元测试 | ✅/❌ | Xs | 50/50 |
| Mock E2E | ✅/❌ | Xs | |
| 真实 LLM E2E | ✅/❌ | Xs | |
| Gateway 集成 | ✅/❌ | Xs | |

### Event Log 分析

- 总事件数: X
- 工具调用: X
- 阶段转换: X
- 错误事件: X

### 发现的问题

1. 
2. 

### 建议

1. 
2. 
```

## 自动化测试脚本

创建 `run_integration_tests.sh`:

```bash
#!/bin/bash
set -e

echo "=== Atomic Agent + Ark LLM 集成测试 ==="
echo ""

# 检查环境变量
if [ -z "$ARK_API_KEY" ]; then
    echo "❌ ARK_API_KEY 未设置"
    exit 1
fi

echo "✓ ARK_API_KEY 已配置"
echo "✓ 使用模型: ${ARK_MODEL:-glm-4-7-251222}"
echo ""

cd /home/eziothean/ProClaw/agent-kernel/apps/python-kernel

# 测试 1: LLM 连接
echo "测试 1: LLM 连接测试..."
PYTHONPATH=/home/eziothean/ProClaw/agent-kernel/apps/python-kernel \
    python tests/test_ark_llm.py
echo ""

# 测试 2: 单元测试
echo "测试 2: Atomic Agent 单元测试..."
PYTHONPATH=/home/eziothean/ProClaw/agent-kernel/apps/python-kernel \
    python tests/integration_test.py
echo ""

# 测试 3: Mock E2E
echo "测试 3: Mock E2E 测试..."
PYTHONPATH=/home/eziothean/ProClaw/agent-kernel/apps/python-kernel \
    python tests/mock_e2e_test.py
echo ""

# 测试 4: 真实 LLM E2E
echo "测试 4: 真实 LLM E2E 测试..."
export KERNEL_RUN_MODE=real
export LLM_PROVIDER=ark
PYTHONPATH=/home/eziothean/ProClaw/agent-kernel/apps/python-kernel \
    python tests/e2e_test.py
echo ""

echo "=== 所有测试通过! ==="
```

赋予执行权限:
```bash
chmod +x run_integration_tests.sh
```

## 下一步

1. ✅ 基础测试完成
2. ⏳ 性能优化（减少 LLM 调用次数）
3. ⏳ 错误恢复机制增强
4. ⏳ 与 Prime Personality 集成测试
5. ⏳ 多会话并发测试
