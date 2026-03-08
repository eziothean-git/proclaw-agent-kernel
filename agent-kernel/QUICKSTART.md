# Agent Kernel 脚手架使用指南

## 项目结构

```
agent-kernel/
├── apps/
│   ├── gateway/                  # TypeScript控制面 (NestJS)
│   │   ├── src/
│   │   │   ├── gateway/         # 对外网关
│   │   │   ├── request-queue/   # 请求队列管理器
│   │   │   ├── scheduler/       # 定时请求调度器
│   │   │   ├── router/          # Info Router
│   │   │   ├── executor/        # Request Executor + MCP Client
│   │   │   ├── mcp/             # MCP服务
│   │   │   └── telemetry/       # 可观测性
│   │   └── package.json
│   │
│   └── python-kernel/           # Python智能面
│       ├── personality/         # Prime Personality
│       ├── context_compiler/    # 主/进程Context Compiler
│       ├── session_host/        # Session Host
│       ├── thread_runtime/      # Agent线程 + 调度器
│       ├── storage/             # 存储抽象层 ⭐ 核心
│       │   ├── adapter.py       # 存储适配器（文件/SQLite）
│       │   ├── tools.py         # 存储工具（Agent调用）
│       │   └── runtime_store.py # 运行态存储
│       ├── executors_client/    # 执行器客户端
│       ├── skills/              # Python Skills
│       ├── schemas/             # 数据模型
│       ├── examples/            # 示例代码
│       │   └── storage_demo.py  # 存储工具演示
│       └── requirements.txt
│
├── packages/
│   ├── shared-schema/           # 共享数据模型
│   ├── skill-protocol/          # MCP协议定义
│   └── observability/           # 可观测性工具
│
├── skills/
│   └── local/                   # 本地MCP Skills
│       ├── fs-skill/           # 文件系统
│       ├── shell-skill/        # Shell执行
│       └── gateway-render-skill/ # 网关渲染
│
├── docs/
│   └── architecture/
│       ├── overview.md         # 架构概览
│       └── storage-layer.md    # 存储层设计 ⭐
│
├── data/                        # 数据存储目录
├── scripts/
│   └── start.sh                # 启动脚本
└── .env.example                # 环境变量示例
```

## 快速开始

### 1. 安装依赖

```bash
# 安装Python依赖
cd apps/python-kernel
pip install -r requirements.txt

# 安装Node.js依赖（可选，如需要Gateway）
cd ../gateway
npm install
```

### 2. 配置环境变量

```bash
# 复制示例配置
cp .env.example .env

# 编辑 .env，配置API密钥等
vim .env
```

### 3. 运行存储演示

```bash
# 运行存储工具演示
bash scripts/start.sh
# 选择选项 4: 运行存储工具演示

# 或直接运行
cd apps/python-kernel
python examples/storage_demo.py
```

## 核心特性

### 1. 存储抽象层（零返工设计）⭐

**关键设计**：所有存储操作通过统一接口，文件/SQLite/PostgreSQL无缝切换

```python
# 文件存储（测试）
export STORAGE_TYPE=file
export DATA_PATH=./data

# SQLite（生产）
export STORAGE_TYPE=sqlite
export DATABASE_PATH=./data/runtime.db

# 代码无需改动！
from storage.tools import get_storage_tools
tools = get_storage_tools()
await tools.session_save(...)
```

### 2. 工具化访问

Agent通过工具调用存储，而非直接操作：

```python
from pydantic_ai import Agent
from storage.tools import STORAGE_TOOLS_REGISTRY

agent = Agent(
    'openai:gpt-4o',
    tools=list(STORAGE_TOOLS_REGISTRY.values())
)

# Agent会自动调用：session_save, task_get, snapshot_create等
result = await agent.run("创建Session和Task")
```

### 3. 完整模块

| 模块 | 技术栈 | 状态 |
|------|--------|------|
| Gateway | TypeScript + NestJS | ✅ |
| Request Queue | TypeScript + 内存队列 | ✅ |
| Scheduler | TypeScript + 定时器 | ✅ |
| Prime Personality | Python + PydanticAI | ✅ |
| Context Compiler | Python | ✅ |
| Session Host | Python | ✅ |
| Agent Threads | Python + asyncio | ✅ |
| Storage Layer | Python | ✅ 新增 |
| MCP Skills | TypeScript/Python | ✅ |

## 存储工具列表

### Session管理
- `session_save` - 创建Session
- `session_get` - 获取Session
- `session_list` - 列出所有Session
- `session_update` - 更新Session
- `session_close` - 关闭Session

### Task管理
- `task_save` - 创建Task
- `task_get` - 获取Task
- `task_list_by_session` - 列出Session的Tasks
- `task_update` - 更新Task
- `task_complete` - 标记完成
- `task_fail` - 标记失败

### 上下文快照
- `snapshot_save` - 保存快照
- `snapshot_get` - 获取快照
- `snapshot_get_latest` - 获取最新快照
- `snapshot_list_by_session` - 列出快照历史

### 队列操作
- `queue_enqueue` - 入队
- `queue_dequeue` - 出队
- `queue_peek` - 查看头部
- `queue_get_length` - 队列长度

### 定时任务
- `scheduler_schedule` - 调度任务
- `scheduler_get_due` - 获取到期任务
- `scheduler_complete` - 标记完成
- `scheduler_cancel` - 取消任务

## 开发流程

### 添加新存储操作

1. **在adapter.py添加接口**：
```python
class StorageAdapter(ABC):
    @abstractmethod
    async def my_new_operation(self, data: dict) -> None:
        pass
```

2. **在FileStorageAdapter和SQLiteStorageAdapter实现**

3. **在tools.py添加工具**：
```python
async def my_new_tool(self, data: dict) -> dict:
    await self.storage.my_new_operation(data)
    return {"success": True}
```

4. **在STORAGE_TOOLS_REGISTRY注册**

### 切换存储实现

只需修改环境变量，无需改动任何业务代码：

```bash
# 文件存储（人类可读，适合调试）
STORAGE_TYPE=file

# SQLite（事务支持，WAL模式）
STORAGE_TYPE=sqlite

# PostgreSQL（分布式，未来支持）
STORAGE_TYPE=postgresql
DATABASE_URL=postgresql://...
```

## 数据存储结构

### 文件存储
```
data/
├── sessions/           # Session数据
├── tasks/             # Task数据
├── snapshots/         # 上下文快照
├── queue/             # 请求队列
└── scheduler/         # 定时任务
```

### SQLite
```sql
sessions, tasks, snapshots, queue, scheduler 五张表
WAL模式支持读写并发
索引优化查询性能
```

## 下一步

1. **运行演示**：`bash scripts/start.sh`，选择选项4
2. **查看文档**：`docs/architecture/storage-layer.md`
3. **阅读代码**：`apps/python-kernel/storage/`
4. **扩展功能**：在现有模块基础上添加业务逻辑

## 重要提醒

- ✅ 所有Agent通过工具调用存储，不要直接操作StorageAdapter
- ✅ 存储切换仅需修改环境变量，无需改动代码
- ✅ Session级别状态，无Memory Base
- ✅ 文件存储适合开发，SQLite适合生产单机部署
- ✅ 数据模型保持一致（JSON结构）

## License

MIT
