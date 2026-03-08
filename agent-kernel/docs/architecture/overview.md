# Agent Kernel 架构文档

## 系统边界

### 包含模块 ✅
- 对外网关（Gateway）
- 请求队列管理器（Queue）
- 定时请求调度器（Scheduler）
- Prime Personality
- 主Context Compiler
- Info Router
- Session Host
- 进程Context Compiler
- Agent线程调度器
- Agent线程
- Request Executor
- 存储抽象层（文件/SQLite）

### 不包含模块 ❌
- Memory Base（长期记忆底座）
- 跨Session经验沉淀
- 知识图谱（Knowledge Graph）

## 核心流程

```
用户输入
  ↓
Gateway（统一中间表示）
  ↓
Queue（串行化）
  ↓
Prime Personality（人格解释）
  ↓
主Context Compiler（入口收敛）
  ↓
Info Router（Session路由）
  ↓
Session Host（Session状态）
  ↓
进程Context Compiler（执行上下文）
  ↓
Agent线程（工具调用）
  ↓
Executor（MCP执行）
  ↓
结果回流 → 输出
```

## 存储策略

### 接口层
所有模块通过统一接口操作数据：
- `StorageAdapter` 抽象接口
- 工具层封装：`session_get`, `task_save`, `snapshot_create` 等

### 实现层
- **Phase 1**: 文件存储（JSON/Markdown）
- **Phase 2**: SQLite（WAL模式）
- **Phase 3**: PostgreSQL（分布式）

### 切换方式
仅通过环境变量切换，业务代码零改动：
```bash
STORAGE_TYPE=file      # 文件存储
STORAGE_TYPE=sqlite    # SQLite
STORAGE_TYPE=postgres  # PostgreSQL
```

## Session管理

Session级状态存储：
- Session元数据（创建时间、状态、配置）
- Task列表（当前Session内的任务）
- 上下文快照（运行态工作记忆）
- **注意**: Session结束后可选择性归档，但不自动沉淀到Memory Base

## Agent协作

### A2A通信
Agent线程间通过Session Host协调：
- 消息传递：JSON-RPC
- 状态共享：Session级存储
- 生命周期：由调度器统一管理

### 工具调用
统一使用MCP协议：
- 本地工具：stdio传输
- 远程服务：HTTP传输
- 工具注册：启动时动态发现
