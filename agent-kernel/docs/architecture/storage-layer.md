# 存储抽象层设计

## 设计原则

**接口先行，实现可替换**

所有存储操作通过统一抽象接口进行，上层（Agent、Session Host等）完全不关心底层实现是文件还是数据库。

## 架构图

```
┌─────────────────────────────────────────────────────┐
│                   Agent / Session Host               │
└──────────────────────┬──────────────────────────────┘
                       │ 调用工具函数
                       ▼
┌─────────────────────────────────────────────────────┐
│                  Storage Tools                      │
│  (session_save, task_get, snapshot_create, ...)    │
└──────────────────────┬──────────────────────────────┘
                       │ 调用存储接口
                       ▼
┌─────────────────────────────────────────────────────┐
│               StorageAdapter (抽象接口)              │
└──────────────────────┬──────────────────────────────┘
                       │
         ┌─────────────┴─────────────┐
         │                           │
         ▼                           ▼
┌──────────────────┐      ┌──────────────────┐
│ FileStorage      │      │ SQLiteStorage    │
│ (JSON文件)       │      │ (SQLite数据库)    │
└──────────────────┘      └──────────────────┘
         │                           │
         └─────────────┬─────────────┘
                       │
         ┌─────────────┴─────────────┐
         │                           │
         ▼                           ▼
  ./data/sessions/           SQLite WAL模式
  ./data/tasks/              事务支持
  ./data/snapshots/          索引优化
  ./data/queue/
  ./data/scheduler/
```

## 核心特性

### 1. 零代码改动切换

仅通过环境变量切换，业务代码零改动：

```bash
# 文件存储（测试阶段）
STORAGE_TYPE=file
DATA_PATH=./data

# SQLite（生产阶段）
STORAGE_TYPE=sqlite
DATABASE_PATH=./data/runtime.db

# 未来：PostgreSQL
STORAGE_TYPE=postgresql
DATABASE_URL=postgresql://...
```

### 2. 统一数据模型

无论底层存储方式，数据模型完全一致：

```python
# Session
{
    "id": "uuid",
    "user_id": "user_001",
    "status": "active",
    "created_at": "2024-01-01T00:00:00",
    "updated_at": "2024-01-01T00:00:00",
    "metadata": {...},
    "task_count": 5
}

# Task
{
    "id": "uuid",
    "session_id": "uuid",
    "goal": "任务目标",
    "status": "pending|running|completed|failed",
    "constraints": [...],
    "allowed_capabilities": [...],
    "created_at": "...",
    "completed_at": "...",
    "output": {...},
    "error": "..."
}

# Snapshot
{
    "id": "uuid",
    "session_id": "uuid",
    "task_id": "uuid",
    "working_memory": {...},
    "timestamp": "2024-01-01T00:00:00"
}
```

### 3. 工具化访问

Agent不直接操作存储，而是通过工具调用：

```python
# Agent通过tool调用
result = await agent.run([
    {"role": "user", "content": "创建新Session"}
])
# Agent内部会调用: session_save(...)
```

工具列表：
- `session_save`, `session_get`, `session_list`, `session_update`, `session_close`
- `task_save`, `task_get`, `task_list_by_session`, `task_update`, `task_complete`, `task_fail`
- `snapshot_save`, `snapshot_get`, `snapshot_get_latest`, `snapshot_list_by_session`
- `queue_enqueue`, `queue_dequeue`, `queue_peek`, `queue_get_length`
- `scheduler_schedule`, `scheduler_get_due`, `scheduler_complete`, `scheduler_cancel`

## 文件存储结构

```
data/
├── sessions/
│   ├── session-001.json
│   └── session-002.json
├── tasks/
│   ├── task-001.json
│   └── task-002.json
├── snapshots/
│   ├── snapshot-001.json
│   └── snapshot-002.json
├── queue/
│   └── requests.jsonl      # JSON Lines格式，支持追加
└── scheduler/
    ├── task-001.json
    └── task-002.json
```

## SQLite Schema

```sql
-- Session表
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    data TEXT NOT NULL,      -- JSON存储
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Task表
CREATE TABLE tasks (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    data TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_tasks_session ON tasks(session_id);

-- Snapshot表
CREATE TABLE snapshots (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    data TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_snapshots_session ON snapshots(session_id);

-- 队列表
CREATE TABLE queue (
    id TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 定时任务表
CREATE TABLE scheduler (
    id TEXT PRIMARY KEY,
    data TEXT NOT NULL,
    trigger_at TIMESTAMP NOT NULL,
    status TEXT DEFAULT 'scheduled',
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX idx_scheduler_trigger ON scheduler(trigger_at);
```

## 使用示例

### 基础使用

```python
from storage.tools import get_storage_tools

tools = get_storage_tools()

# 创建Session
await tools.session_save(
    session_id="sess-001",
    user_id="user_001",
    metadata={"platform": "cli"}
)

# 创建Task
await tools.task_save(
    task_id="task-001",
    session_id="sess-001",
    goal="演示任务",
    constraints=["安全约束"]
)

# 保存快照
await tools.snapshot_save(
    snapshot_id="snap-001",
    session_id="sess-001",
    working_memory={"step": "初始化"}
)
```

### Agent中使用

```python
from pydantic_ai import Agent
from storage.tools import STORAGE_TOOLS_REGISTRY

agent = Agent(
    'openai:gpt-4o',
    tools=list(STORAGE_TOOLS_REGISTRY.values())
)

# Agent会自动选择合适的工具
result = await agent.run("创建Session并在其中创建Task")
```

### 切换存储方式

```python
import os

# 方式1: 环境变量
os.environ['STORAGE_TYPE'] = 'sqlite'
os.environ['DATABASE_PATH'] = './data/runtime.db'

# 方式2: 直接创建
from storage.adapter import create_storage_adapter

storage = create_storage_adapter({
    'type': 'sqlite',
    'db_path': './data/runtime.db'
})
await storage.initialize()
```

## 迁移路径

### Phase 1: 文件存储（当前）
- 使用JSON/Markdown文件
- 适合开发和测试
- 人类可读，便于调试

### Phase 2: SQLite（单机部署）
- WAL模式支持并发
- 事务保证一致性
- 索引提升查询性能

### Phase 3: PostgreSQL（分布式）
- 多节点共享存储
- 高级查询和事务
- 备份和恢复

**切换成本：零代码改动，仅需修改环境变量**

## 注意事项

1. **不要绕过工具层**：Agent应通过工具函数访问存储，不要直接调用StorageAdapter
2. **事务边界**：复杂操作应在工具层封装，保证原子性
3. **性能优化**：文件存储适合小数据量，大数据量时切换到SQLite/PostgreSQL
4. **备份策略**：定期备份data目录（文件存储）或数据库文件（SQLite）
