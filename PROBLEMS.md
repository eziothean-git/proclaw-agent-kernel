# ProClaw 系统问题跟踪

## 🔴 阻塞性问题（Critical）

### 1. Request Manager 时间戳解析错误
**状态**: 🔴 阻塞系统运行  
**影响**: 所有通过 Gateway 的请求都失败  
**错误信息**: `Invalid time value`  
**位置**: `apps/request-manager/src/services/priority-request-manager.service.ts`

**详细描述**:
- Gateway 成功接收请求并提交到 Request Manager
- Request Manager 将请求保存到 inbox 成功
- 处理请求时出现时间戳解析错误
- 错误发生在 `PriorityRequestManagerService`

**日志证据**:
```
[Nest] 310651 - [PriorityQueueService] Request queued at position 0
[Nest] 310651 - [RetryHandlerService] Request failed with non-recoverable error: Invalid time value
[Nest] 310651 - [PriorityRequestManagerService] Request failed: Invalid time value
```

**可能原因**:
1. 请求中的 `receivedAt` 时间戳格式问题
2. `new Date()` 在某些情况下返回无效日期
3. 时区或格式转换错误

**建议修复方案**:
1. 检查 `priority-request-manager.service.ts` 第 96、120、127 行的时间处理
2. 添加日期验证和错误处理
3. 统一使用 ISO 8601 格式时间戳

---

## 🟡 高优先级问题（High）

### 2. Prime Personality LLM 响应解析
**状态**: ✅ 已修复  
**问题**: LLM 返回 YAML/Markdown 格式，但代码期望纯 JSON  
**修复**: 添加了 `_extract_json_from_response()` 方法支持 YAML/JSON  
**文件**: `apps/python-kernel/personality/prime_personality.py`

### 3. 模型名称错误
**状态**: ✅ 已修复  
**问题**: 使用 `glm-4.7` 而不是正确的 `glm-4-7-251222`  
**修复**: 更新 `llm_client.py` 中的默认模型名称  
**文件**: `apps/python-kernel/llm_client.py`

### 4. Master Context Compiler asyncio 问题
**状态**: ✅ 已修复  
**问题**: 在异步上下文中调用 `asyncio.run()`  
**修复**: 添加了事件循环检测逻辑  
**文件**: `apps/python-kernel/context_compiler/master_compiler.py`

### 5. 项目名称冲突
**状态**: ✅ 已修复  
**问题**: `openclaw` 与原版 CLI 冲突  
**修复**: 重命名为 `proclaw`  
**文件**: 
- `apps/gateway/clients/tui/pyproject.toml`
- `apps/gateway/clients/tui/proclaw_tui/`

---

## 🟢 中优先级问题（Medium）

### 6. Prime Context Compiler Agent WorkingSet 验证错误
**状态**: 🟡 存在但非阻塞  
**问题**: Pydantic 验证错误 - `task_id`, `task_goal`, `recent_observations` 字段缺失  
**日志**:
```
3 validation errors for WorkingSet
task_id: Field required
task_goal: Field required  
recent_observations: Input should be a valid list
```

**建议**: 检查 `PrimeContextCompilerAgent` 的 WorkingSet 构建逻辑

### 7. Webhook Controller 时间戳错误
**状态**: 🟡 存在但非阻塞  
**问题**: `Cannot read properties of undefined (reading 'timestamp')`  
**位置**: `apps/gateway/src/gateway/webhook.controller.ts:34`

**建议**: 添加空值检查

### 8. Remote Executor 404 错误
**状态**: 🟡 存在但非阻塞  
**问题**: `Client error '404 Not Found' for url 'http://localhost:3000/api/v1/executor/execute'`  
**说明**: Executor 端点不存在，但这不影响核心流程

---

## 📋 服务启动配置

### 需要启动的服务（按顺序）

1. **Request Manager** (gRPC:50052)
   ```bash
   cd apps/request-manager
   npm start
   ```

2. **Python Kernel** (HTTP:8000)
   ```bash
   cd apps/python-kernel
   export ARK_API_KEY="62663763-1f8a-4c10-862e-b5d760b19fba"
   export LLM_PROVIDER="ark"
   export ARK_MODEL="glm-4-7-251222"
   export GATEWAY_URL="http://localhost:3000"
   export DATA_PATH="/home/eziothean/ProClaw/agent-kernel/data"
   PYTHONPATH=/home/eziothean/ProClaw/agent-kernel/apps/python-kernel python main.py
   ```

3. **Gateway** (HTTP:3000)
   ```bash
   cd apps/gateway
   export GATEWAY_STORAGE_PATH="/home/eziothean/ProClaw/agent-kernel/data/gateway"
   npm run start:prod
   ```

### 一键启动脚本
位置: `/home/eziothean/ProClaw/start-all.sh`

---

## ✅ 已验证功能

- ✅ Prime Personality YAML/JSON 解析
- ✅ LLM 客户端配置 (火山引擎 Ark)
- ✅ Context Compiler 运行
- ✅ Agent Thread 执行
- ✅ Gateway 健康检查
- ✅ Request Manager gRPC 服务
- ✅ 文件系统 mailbox

---

## 🔧 环境配置

### API 密钥
```bash
export ARK_API_KEY="62663763-1f8a-4c10-862e-b5d760b19fba"
export ARK_BASE_URL="https://ark.cn-beijing.volces.com/api/v3"
export ARK_MODEL="glm-4-7-251222"
```

### 路径配置
```bash
export DATA_PATH="/home/eziothean/ProClaw/agent-kernel/data"
export GATEWAY_STORAGE_PATH="/home/eziothean/ProClaw/agent-kernel/data/gateway"
```

---

## 📝 测试方法

### 直接测试 API
```bash
# 发送请求
curl -X POST "http://localhost:3000/api/v1/chat" \
  -H "Content-Type: application/json" \
  -d '{"message": "你好", "user_id": "test"}'

# 查询状态  
curl "http://localhost:3000/api/v1/requests/{request_id}"
```

### 使用 TUI
```bash
cd apps/gateway/clients/tui
proclaw
```

---

## 📂 日志位置

- **Gateway**: `/tmp/proclaw-gateway.log`
- **Python Kernel**: `/tmp/proclaw-kernel.log`
- **Request Manager**: `/tmp/request-manager.log`

---

## 🎯 下一步行动

1. **修复 Request Manager 时间戳错误** (Critical)
   - 文件: `apps/request-manager/src/services/priority-request-manager.service.ts`
   - 重点: 第 96-128 行的时间处理逻辑
   - 建议: 添加日期格式验证

2. **可选: 修复 Webhook Controller 空值错误** (Medium)
   - 文件: `apps/gateway/src/gateway/webhook.controller.ts`
   - 建议: 添加 `response?.timestamp` 检查

3. **可选: 修复 Prime Context Compiler WorkingSet 验证** (Medium)
   - 文件: `apps/python-kernel/context_compiler/prime_context_compiler_agent.py`
   - 建议: 确保 WorkingSet 构建时包含所有必需字段

---

*最后更新: 2026-03-10*  
*创建者: opencode*  
*项目: ProClaw TUI for Agent Kernel*
