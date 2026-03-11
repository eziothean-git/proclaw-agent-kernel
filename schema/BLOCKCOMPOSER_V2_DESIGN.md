# ProClaw BlockComposer v2 架构设计

## 文档信息

- **版本**: 1.0.0
- **日期**: 2026-03-11
- **状态**: 设计阶段
- **作者**: ProClaw Team

## 1. 设计目标

### 1.1 核心原则

- **Bash is all you need**: 通过受限的 bash 命令提供系统能力
- **全本地架构**: 无需网络，高性能，完全可控
- **严格权限**: 三层权限模型（System/Session/Thread）+ Capability Token
- **高性能缓存**: L1 内存 + L2 SQLite，最大化上下文缓存命中
- **完整可观测性**: 详细的 trace 记录、审计日志、性能指标

### 1.2 关键指标

| 指标 | 目标 | 当前 (Python) |
|------|------|--------------|
| Block composition latency | <10ms | 50-100ms |
| Cache hit rate | >90% | ~60% |
| Memory usage per session | <50MB | 200MB+ |
| Cold start time | <100ms | 2-3s |

## 2. 系统架构

### 2.1 整体架构图

```
┌─────────────────────────────────────────────────────────────┐
│  Session Host (Python)                                      │
│  - 组装 blocks（大部分场景）                                │
│  - 授权 bash 命令给 Thread（Capability Token）              │
└──────────────┬──────────────────────────────────────────────┘
               │ gRPC (Unix socket)
               ▼
┌─────────────────────────────────────────────────────────────┐
│  BlockComposer (Rust) - Systemd Service                     │
│  ┌───────────────────────────────────────────────────────┐ │
│  │ L1 Cache (内存 LRU)                                   │ │
│  │ - Block index (HashMap)                              │ │
│  │ - Hot blocks (1000 entries)                          │ │
│  │ - Token 预算计算                                      │ │
│  └───────────────────────────────────────────────────────┘ │
│  ┌───────────────────────────────────────────────────────┐ │
│  │ Providers                                             │ │
│  │ - BashProvider (命令过滤 + 沙箱)                      │ │
│  │ - CodeProvider (rg + ast-grep + 索引)                │ │
│  │ - MemoryProvider (SQLite)                            │ │
│  │ - FileProvider (受限文件访问)                        │ │
│  └───────────────────────────────────────────────────────┘ │
│  ┌───────────────────────────────────────────────────────┐ │
│  │ Policy Engine (Capability Token + 策略规则)           │ │
│  │ - 签名验证                                            │ │
│  │ - Scope 检查                                          │ │
│  │ - 路径限制                                            │ │
│  │ - 速率限制                                            │ │
│  └───────────────────────────────────────────────────────┘ │
└──────────────┬──────────────────────────────────────────────┘
               │
    ┌──────────┴──────────┐
    ▼                     ▼
┌─────────────────┐  ┌─────────────────────┐
│ SQLite (L2)     │  │ Trace Files         │
│ - Block content │  │ /var/lib/proclaw/   │
│ - Cache index   │  │   traces/           │
│ - Code index    │  │                     │
└─────────────────┘  │ - JSON Lines        │
                     │ - Zstd 压缩         │
                     │ - 分层索引          │
                     └─────────────────────┘
```

### 2.2 组件职责

| 组件 | 语言 | 职责 | 权限 |
|------|------|------|------|
| Session Host | Python | 组装 blocks、授权 Thread、管理会话 | Session Level |
| BlockComposer | Rust | 核心合成引擎、缓存管理、权限检查 | System Level |
| BashProvider | Rust | 执行受限 bash 命令 | 按 Token 授权 |
| CodeProvider | Rust | 代码检索和索引 | 按 Token 授权 |
| MemoryProvider | Rust | 长期记忆查询 | Session Level |

## 3. 权限机制

### 3.1 三层权限模型

```
Layer 3: System
├─ 访问所有 providers
├─ 修改配置
└─ 查看所有 traces

Layer 2: Session
├─ 读文件、列表目录
├─ 查询 memory
├─ 组装 blocks
└─ 授权给 Thread

Layer 1: Thread
├─ 受限的 bash 执行（需 Session 授权）
├─ 代码检索（只读）
└─ 系统状态查询
```

### 3.2 Capability Token 结构

```rust
pub struct CapabilityToken {
    // Header
    pub version: u8,              // Token format version
    pub issued_at: u64,           // Unix timestamp
    pub expires_at: u64,          // Unix timestamp
    
    // Claims
    pub subject: String,          // Thread/Session ID
    pub issuer: String,           // Session Host ID
    pub level: PermissionLevel,   // system/session/thread
    pub scope: Vec<Scope>,        // 具体权限范围
    
    // Usage tracking
    pub max_calls: u32,           // 最大调用次数 (0 = unlimited)
    pub call_count: AtomicU32,    // 当前调用次数
    
    // Constraints
    pub allowed_paths: Vec<PathBuf>,
    pub blocked_patterns: Vec<String>,
    pub allowed_commands: Vec<String>,
    
    // Signature (HMAC-SHA256)
    pub signature: Vec<u8>,
}
```

### 3.3 Scope 类型

```rust
pub enum Scope {
    // File operations
    FileRead { paths: Vec<PathBuf> },
    FileList { paths: Vec<PathBuf> },
    
    // Code search
    CodeSearch { languages: Vec<String>, paths: Vec<PathBuf> },
    SymbolLookup { symbols: Vec<String> },
    
    // System
    ProcessQuery,
    SystemInfo,
    
    // Memory
    MemoryQuery { categories: Vec<String> },
}
```

### 3.4 授权流程

```
Session Host 决定授权
  │
  ├─► 检查目标操作是否在 Thread 需求范围内
  ├─► 评估风险等级（低风险/中风险/高风险）
  │
  ▼
生成 Capability Token
{
  "subject": "thread_abc123",
  "issuer": "session_host_xyz",
  "level": "thread",
  "scope": [
    {"FileRead": {"paths": ["/project/src"]}},
    {"CodeSearch": {"languages": ["rust"], "paths": ["/project"]}}
  ],
  "max_calls": 50,
  "allowed_paths": ["/project/src", "/project/Cargo.toml"],
  "expires_at": "2026-03-11T13:00:00Z",
  "signature": "..."
}
  │
  ▼
通过 CompiledContext 传递给 Thread
  │
  ▼
Thread 调用 BlockComposer
  │
  ▼
BlockComposer 验证：
  ├─► 签名有效性（HMAC-SHA256）
  ├─► 是否过期
  ├─► 调用次数限制
  ├─► 路径是否在 allowed_paths
  ├─► 命令是否匹配 scope
  └─► 应用 PolicyEngine 规则
  │
  ▼
执行或拒绝 + 记录审计日志
```

### 3.5 策略引擎

```rust
pub struct PolicyEngine {
    rules: Vec<PolicyRule>,
    audit_log: Arc<Mutex<AuditLog>>,
}

pub enum PolicyRule {
    PathRestriction {
        subject_pattern: String,
        allowed_paths: Vec<PathBuf>,
        denied_paths: Vec<PathBuf>,
    },
    TimeWindow {
        subject_pattern: String,
        start_hour: u8,
        end_hour: u8,
        timezone: String,
    },
    RateLimit {
        subject_pattern: String,
        max_requests_per_minute: u32,
        window_seconds: u64,
    },
    ResourceLimit {
        subject_pattern: String,
        max_output_size: usize,
        max_execution_time: Duration,
    },
}
```

### 3.6 审计日志

**格式**（结构化 JSON）：

```json
{
  "timestamp": "2026-03-11T12:34:56.800Z",
  "level": "INFO",
  "event_type": "permission_check",
  "subject": "thread_abc123",
  "operation": {
    "type": "bash_execute",
    "command": "cat /project/README.md"
  },
  "decision": "allow",
  "token_claims": {
    "issuer": "session_host_xyz",
    "scope": "FileRead",
    "remaining_calls": 49
  },
  "duration_ms": 2.1,
  "trace_id": "trace_abc123"
}
```

## 4. 核心组件设计

### 4.1 BlockComposer

**核心职责**：
- 组装 blocks 为最终上下文
- 管理 L1/L2 缓存
- 调度 providers
- 权限验证
- Trace 记录

**Composition Profile**:

```yaml
profiles:
  prime:
    token_budget: 2000
    cache_ttl: 300  # 5min
    block_types:
      - system_identity
      - global_memory
      - intent_analysis
    composition_rules:
      - type: priority
        order: [system_identity, intent_analysis, global_memory]
      - type: token_limit
        max: 2000
        truncate: bottom

  session:
    token_budget: 3000
    cache_ttl: 120  # 2min
    block_types:
      - session_context
      - active_tasks
      - conversation_history

  task:
    token_budget: 4000
    cache_ttl: 30   # 30s
    block_types:
      - task_goal
      - working_memory
      - available_tools
      - recent_observations
```

### 4.2 BashProvider

**核心思想**：Bash is all you need

**预设命令模式**：

```yaml
patterns:
  # 文件操作（读）
  read_file:
    pattern: "cat {path}"
    level: session
    max_output: 100000
    
  list_directory:
    pattern: "ls -la {path}"
    level: session
    
  find_files:
    pattern: "find {path} -name '{pattern}' -type f 2>/dev/null | head -50"
    level: session
    
  # 代码检索（读）
  grep_code:
    pattern: "rg -n --json '{pattern}' {path} 2>/dev/null | head -100"
    level: thread
    
  get_symbol:
    pattern: "ast-grep scan --rule '{rule}' {path}"
    level: thread
    
  # 系统信息（受限）
  process_status:
    pattern: "ps aux | grep {pattern} | head -20"
    level: thread
    
  disk_usage:
    pattern: "df -h"
    level: system
```

**安全机制**：
- 命令白名单（只允许预设模式）
- 路径白名单（allowed_paths）
- 输出大小限制
- 执行超时（30s）
- 禁止危险命令（rm -rf /, mkfs, fork bomb 等）

### 4.3 CodeProvider

**架构**：使用成熟的 CLI 工具，自建索引

**支持的查询类型**：

```rust
pub enum CodeQuery {
    // 文本搜索（ripgrep）
    TextSearch {
        pattern: String,
        paths: Vec<PathBuf>,
        case_sensitive: bool,
        max_results: usize,
    },
    
    // 结构搜索（ast-grep）
    StructuralSearch {
        pattern: String,
        paths: Vec<PathBuf>,
        language: String,
        max_results: usize,
    },
    
    // 符号查找（索引）
    SymbolLookup {
        symbol: String,
        symbol_type: Option<SymbolType>,
        exact_match: bool,
    },
    
    // 引用查找
    ReferenceSearch {
        symbol: String,
        paths: Vec<PathBuf>,
    },
    
    // 文件大纲
    FileOutline {
        path: PathBuf,
    },
}
```

**索引数据库 Schema**（SQLite）：

```sql
-- 文件表
CREATE TABLE files (
    id INTEGER PRIMARY KEY,
    path TEXT UNIQUE NOT NULL,
    language TEXT,
    last_modified INTEGER,
    content_hash TEXT,
    line_count INTEGER,
    indexed_at INTEGER
);

-- 符号表
CREATE TABLE symbols (
    id INTEGER PRIMARY KEY,
    file_id INTEGER REFERENCES files(id),
    name TEXT NOT NULL,
    symbol_type TEXT NOT NULL,
    line_start INTEGER,
    line_end INTEGER,
    column_start INTEGER,
    column_end INTEGER,
    signature TEXT,
    docstring TEXT,
    parent_id INTEGER REFERENCES symbols(id),
    visibility TEXT
);

-- 引用表
CREATE TABLE references (
    id INTEGER PRIMARY KEY,
    symbol_id INTEGER REFERENCES symbols(id),
    file_id INTEGER REFERENCES files(id),
    line INTEGER,
    column INTEGER,
    reference_type TEXT
);

-- 全文搜索索引（FTS5）
CREATE VIRTUAL TABLE symbol_fts USING fts5(
    name,
    content='symbols',
    content_rowid='id'
);
```

**自动索引流程**：

```
定时触发 (每 5 分钟)
  │
  ▼
扫描配置的 paths
  │
  ├─► 检查文件修改时间
  ├─► 计算内容哈希
  ├─► 与数据库对比
  │
  ▼
对于变更的文件：
  ├─► 使用 tree-sitter CLI 解析 AST
  ├─► 提取符号信息
  ├─► 更新数据库
  │
  ▼
提交事务
  │
  ▼
更新索引元数据
```

### 4.4 MemoryProvider

**职责**：长期记忆查询

**实现**：直接访问 SQLite memory database

```rust
pub struct MemoryProvider {
    db: Arc<Mutex<Connection>>,
}

impl MemoryProvider {
    pub async fn query_facts(
        &self,
        query: &str,
        categories: &[String],
        limit: usize,
    ) -> Result<Vec<MemoryFact>> {
        let db = self.db.lock().await;
        
        let sql = if categories.is_empty() {
            "SELECT * FROM facts 
             WHERE content MATCH ?1 
             ORDER BY relevance DESC 
             LIMIT ?2"
        } else {
            "SELECT * FROM facts 
             WHERE content MATCH ?1 
             AND category IN (?3) 
             ORDER BY relevance DESC 
             LIMIT ?2"
        };
        
        // 执行查询...
    }
}
```

## 5. gRPC 接口

### 5.1 服务定义

```protobuf
syntax = "proto3";

package proclaw.block_composer.v1;

service BlockComposer {
  // 核心功能
  rpc Compose(ComposeRequest) returns (ComposeResponse);
  rpc QueryBlocks(QueryBlocksRequest) returns (QueryBlocksResponse);
  rpc ExecuteBash(ExecuteBashRequest) returns (ExecuteBashResponse);
  rpc QueryCode(QueryCodeRequest) returns (QueryCodeResponse);
  
  // 权限管理
  rpc ValidateToken(ValidateTokenRequest) returns (ValidateTokenResponse);
  rpc RevokeToken(RevokeTokenRequest) returns (RevokeTokenResponse);
  
  // 可观测性
  rpc GetTrace(GetTraceRequest) returns (TraceResponse);
  rpc ListTraces(ListTracesRequest) returns (ListTracesResponse);
  rpc ReplayTrace(ReplayTraceRequest) returns (ReplayTraceResponse);
  rpc GetMetrics(GetMetricsRequest) returns (MetricsResponse);
  rpc SubscribeTraces(SubscribeTracesRequest) returns (stream TraceEvent);
}
```

### 5.2 核心消息

**ComposeRequest**:

```protobuf
message ComposeRequest {
  string session_id = 1;
  string task_id = 2;
  Profile profile = 3;
  repeated BlockType block_types = 4;
  map<string, string> context = 5;
  string capability_token = 6;
}
```

**ComposeResponse**:

```protobuf
message ComposeResponse {
  string composed_text = 1;
  repeated string block_ids_used = 2;
  uint32 total_tokens = 3;
  bool cache_hit = 4;
  string trace_id = 5;
  google.protobuf.Duration latency = 6;
}
```

**ExecuteBashRequest**:

```protobuf
message ExecuteBashRequest {
  string command = 1;
  string capability_token = 2;
  int32 timeout_seconds = 3;
  string working_directory = 4;
}
```

**QueryCodeRequest**:

```protobuf
message QueryCodeRequest {
  oneof query {
    TextSearchQuery text_search = 1;
    StructuralSearchQuery structural_search = 2;
    SymbolLookupQuery symbol_lookup = 3;
    ReferenceSearchQuery reference_search = 4;
    FileOutlineQuery file_outline = 5;
  }
  string capability_token = 6;
  int32 max_results = 7;
}
```

## 6. Trace 系统

### 6.1 存储结构

```
/var/lib/proclaw/traces/
├── 2026/
│   ├── 03/
│   │   ├── 11/
│   │   │   ├── trace_20260311_123456_abc123.json
│   │   │   ├── trace_20260311_123456_abc123.json.zst
│   │   │   └── ...
│   │   └── index.jsonl
│   └── index.jsonl
├── index.jsonl
└── current/
    ├── active.jsonl
    └── buffer/
```

### 6.2 Trace 文件格式

**JSON Lines**，每个 trace 一个文件：

```json
{"type":"header","trace_id":"trace_abc123","session_id":"sess_xyz","task_id":"task_789","profile":"session","started_at":"2026-03-11T12:34:56.789Z"}
{"type":"event","timestamp":"2026-03-11T12:34:56.790Z","event_type":"cache_check","attributes":{"key":"session:sess_xyz:task_789","hit":false},"duration_ms":0.1}
{"type":"event","timestamp":"2026-03-11T12:34:56.791Z","event_type":"provider_call","attributes":{"provider":"MemoryProvider","query":"session_context"},"duration_ms":5.2}
{"type":"footer","timestamp":"2026-03-11T12:34:56.810Z","total_duration_ms":21.0,"blocks_used":2,"total_tokens":300,"cache_hit":false}
```

### 6.3 索引文件格式

```json
{"trace_id":"trace_abc123","session_id":"sess_xyz","task_id":"task_789","profile":"session","started_at":"2026-03-11T12:34:56.789Z","duration_ms":21.0,"cache_hit":false,"block_count":2,"token_count":300,"file_path":"2026/03/11/trace_20260311_123456_abc123.json","compressed":false}
```

### 6.4 压缩策略

- **24 小时后压缩**（Zstd，level 3）
- **保留未压缩副本 7 天**
- **30 天后删除**

## 7. 部署配置

### 7.1 Systemd Service

```ini
[Unit]
Description=ProClaw BlockComposer
After=network.target

[Service]
Type=notify
User=proclaw
Group=proclaw
ExecStart=/usr/local/bin/proclaw-composer --config /etc/proclaw/composer.yaml

# 资源限制
MemoryMax=2G
CPUQuota=200%
LimitNOFILE=65536

# 安全设置
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
PrivateTmp=true

Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### 7.2 配置文件

```yaml
server:
  socket_path: "/run/proclaw/composer.sock"
  workers: 4
  max_concurrent_requests: 100

cache:
  l1:
    max_entries: 1000
    default_ttl_seconds:
      prime: 300
      session: 120
      task: 30
  l2:
    path: "/var/lib/proclaw/cache.db"
    max_size_mb: 512

providers:
  bash:
    timeout_seconds: 30
    max_output_size: 100000
    blocked_commands:
      - "rm -rf /"
      - "mkfs"
  
  code:
    index:
      database_path: "/var/lib/proclaw/code_index.db"
      update_interval_seconds: 300
      paths:
        - path: "/home/user/projects"
          languages: ["rust", "python"]

observability:
  metrics:
    enabled: true
    port: 9090
  traces:
    base_path: "/var/lib/proclaw/traces"
    retention_days: 30
  audit:
    path: "/var/log/proclaw/audit.log"
```

## 8. 实施计划

### Phase 1: 基础设施（1-2 周）

1. 搭建 Rust 项目骨架
2. 实现 gRPC server 和消息结构
3. 创建 systemd service 配置
4. 基础测试框架

### Phase 2: 核心功能（2-3 周）

1. 实现 BlockComposer 核心（L1/L2 缓存）
2. 实现 BashProvider（带权限控制）
3. 实现 MemoryProvider
4. 基础权限引擎

### Phase 3: 高级功能（1-2 周）

1. 实现 CodeProvider
2. 自动代码索引
3. 完整的 Trace 系统
4. 策略引擎增强

### Phase 4: 集成（1 周）

1. 创建 Python gRPC client
2. 与现有 Python Kernel 并行运行
3. 性能基准测试
4. 逐步迁移调用点

## 9. 与现有系统兼容性

### 9.1 并行运行策略

```
Phase 1:
┌──────────────────────┐      ┌──────────────────────┐
│ 现有 Python Kernel   │      │ 新 BlockComposer     │
│ (保持运行)           │◄────►│ (gRPC via socket)    │
└──────────────────────┘      └──────────────────────┘

Phase 2:
- Session Host 先使用新 Composer
- 保留旧 Context Compiler 作为 fallback
- A/B 测试缓存命中率

Phase 3:
- 删除旧系统
- 清理代码
```

### 9.2 Python Client

```python
# block_composer_client.py
class BlockComposerClient:
    def __init__(self, socket_path: str = "/run/proclaw/composer.sock"):
        self.channel = grpc.insecure_channel(f"unix:{socket_path}")
        self.stub = composer_pb2_grpc.BlockComposerStub(self.channel)
    
    async def compose(
        self,
        session_id: str,
        profile: str,
        block_types: List[str]
    ) -> ComposedContext:
        request = ComposeRequest(...)
        response = await self.stub.Compose(request)
        return ComposedContext(...)
```

## 10. 监控与调试

### 10.1 Prometheus 指标

```
block_composer_cache_hits_total{profile="prime"}
block_composer_cache_miss_total{profile="session"}
block_composer_latency_seconds_bucket{le="0.01"}
block_composer_blocks_total{type="session_context"}
```

### 10.2 Trace 可视化

```
Composition Trace: trace_abc123
├── Cache Check: "session:sess_456:task_xyz"
│   └── MISS (latency: 0.2ms)
├── Provider: MemoryProvider
│   ├── Query: session_context
│   └── Latency: 5ms
├── Block Selection
│   ├── Selected: session_context (p:10, tokens: 120)
│   └── Truncated: file_readme (200 -> 180 tokens)
└── Complete: 2 blocks, 300 tokens, 18ms
```

## 11. 附录

### 11.1 依赖工具

- **ripgrep**: 文本搜索 (`rg`)
- **ast-grep**: 结构搜索 (`ast-grep`)
- **tree-sitter**: AST 解析 (`tree-sitter`)

### 11.2 文件路径

```
/etc/proclaw/
├── composer.yaml          # 主配置
├── bash_patterns.yaml     # Bash 命令模式
└── policies.yaml          # 策略规则

/var/lib/proclaw/
├── cache.db               # L2 缓存
├── code_index.db          # 代码索引
├── memory.db              # 长期记忆
└── traces/                # Trace 文件

/var/log/proclaw/
├── audit.log              # 审计日志
└── composer.log           # 应用日志

/run/proclaw/
└── composer.sock          # gRPC socket
```

### 11.3 环境变量

- `COMPOSER_SECRET_KEY`: Token 签名密钥
- `COMPOSER_SOCKET_PATH`: Socket 路径
- `COMPOSER_DATA_DIR`: 数据目录
- `RUST_LOG`: 日志级别

---

## 12. 实施进展

### 12.1 已完成功能 (2026-03-11)

**✅ Phase 1 & 2 & 3 已完成**

#### BashWrapper 统一命令执行
- **重构完成**：统一使用 `BashWrapper` 替代多个 Provider（FileProvider/CodeProvider 已删除）
- **4种执行模式**：
  - `FileMode`: cat, ls, find, pwd, readlink
  - `SearchMode`: rg, ast-grep, grep, find  
  - `SystemMode`: ps, df, du, uptime, uname
  - `Custom`: 用户自定义正则模式
- **安全控制**：危险命令黑名单、超时控制（默认5-30s）、输出截断（100KB）
- **原始输出**：保持 bash 原生输出格式，不解析
- **工作目录支持**：减少 token 消耗
- **命令历史**：按 thread 记录所有操作，支持上帝视角查看

#### L2 缓存文件系统版
- **存储格式**：JSON Lines 文件（替代 SQLite）
- **文件命名**：`{date}_{thread_id}_{cmd}_{simplified_args}_{hash[:8]}.jsonl`
- **目录结构**：
  ```
  /var/lib/proclaw/cache/
  ├── index.jsonl              # 快速查找索引
  └── 2026-03-11/              # 按日期分区
      └── thread_xxx_cat_arg_hash.jsonl
  ```
- **长期存储**：无 TTL，永久保留（外挂数据库自动同步）
- **L1/L2 两级协作**：内存 LRU + 文件系统持久化

#### Trace 系统 + Thread 历史
- **实时写入**：每次操作立即落盘
- **Thread 历史**：
  - 操作时间序列（seq, timestamp, operation, details）
  - 当前工作目录追踪
  - 访问过的路径列表
  - 操作计数和成功率
- **存储结构**：
  ```
  /var/lib/proclaw/traces/
  ├── index.jsonl              # 全局索引
  ├── threads/
  │   └── {thread_id}.json     # Thread 完整历史
  └── daily/
      └── 2026-03-11/
          └── {thread_id}_{trace_id}.jsonl
  ```
- **上帝视角支持**：协调层可读取 thread 历史判断运行状态

#### 测试与构建
- **编译状态**：✅ Debug & Release 构建通过
- **单元测试**：7 个测试全部通过
- **代码质量**：Clippy 无错误（43 warnings - 未使用代码）

### 12.2 架构调整

**重大变更：**
1. **删除 CodeProvider/FileProvider**：功能合并到 BashWrapper
2. **L2 缓存改为文件系统**：JSON Lines 格式，便于外挂数据库同步
3. **Provider 架构简化**：一个 BashWrapper 通过权限模式控制，而非多个 Provider
4. **Trace 系统增强**：新增 Thread 历史记录，支持上帝视角

**当前文件结构：**
```
kernel-v2/
├── src/
│   ├── providers/
│   │   ├── bash.rs          ✅ BashWrapper (完整实现)
│   │   └── memory.rs        ✅ MemoryProvider
│   ├── block_composer/
│   │   ├── mod.rs           ✅ 核心引擎
│   │   └── cache.rs         ✅ L1/L2 缓存 (文件系统版)
│   ├── observability/
│   │   └── trace.rs         ✅ Trace系统 + Thread历史
│   ├── auth/
│   │   └── mod.rs           ✅ 权限管理
│   ├── server.rs            ✅ gRPC服务
│   └── main.rs              ✅ 入口点
├── config/
│   └── composer.yaml.example ✅ 更新配置
└── target/release/
    └── proclaw-composer     ✅ 可执行文件
```

---

## 13. 下一步计划 (Phase 4)

### 13.1 优先级 1：高级 LLM API 路由

**目标**：实现更智能的 LLM 路由和负载均衡

**功能：**
- **多 Provider 支持**：OpenAI, Anthropic, Local LLM 等
- **智能路由**：根据模型能力、成本、延迟选择最优 Provider
- **故障转移**：自动切换失败的 Provider
- **请求队列**：优先级队列 + 流控
- **成本追踪**：按 session/task 统计 token 消耗和费用

**技术栈：**
- Rust (核心路由)
- TypeScript (配置和管理 API)

### 13.2 优先级 2：LLM 输出 Parser (重构)

**目标**：结构化解析 LLM 输出，提取 Action/Thought

**功能：**
- **多格式支持**：JSON/YAML/Markdown 混合输出解析
- **流式解析**：边接收边解析，降低延迟
- **错误恢复**：部分损坏输出也能提取有效信息
- **结构化输出**：统一为内部 Action 格式

**技术栈：**
- Rust (核心解析引擎 - 高性能)
- TypeScript (格式定义和验证 - 灵活配置)

### 13.3 优先级 3：执行协调器 (重构)

**目标**：协调多个 Agent 执行，管理依赖和并发

**功能：**
- **依赖图执行**：根据 task 依赖关系智能调度
- **并发控制**：限制同时运行的 Agent 数量
- **状态同步**：Agent 间状态共享和通知
- **故障处理**：失败重试、回滚、降级策略
- **资源管理**：CPU/内存/网络资源配额

**技术栈：**
- Rust (核心调度 - 高性能、低延迟)
- TypeScript (策略配置 - 业务逻辑)

### 13.4 最终架构

```
┌─────────────────────────────────────────────┐
│  ProClaw Kernel v2 (Rust + TypeScript)      │
├─────────────────────────────────────────────┤
│  TypeScript Layer                           │
│  - API Gateway (HTTP/gRPC)                 │
│  - LLM Router Configuration                │
│  - Parser Format Definitions               │
│  - Execution Policies                      │
├─────────────────────────────────────────────┤
│  Rust Core Layer                            │
│  - BlockComposer (已完成 ✅)               │
│  - BashWrapper (已完成 ✅)                 │
│  - LLM API Router (Phase 4)                │
│  - Output Parser (Phase 4)                 │
│  - Execution Coordinator (Phase 4)         │
│  - Trace & Cache (已完成 ✅)               │
└─────────────────────────────────────────────┘
```

---

**文档版本**: 2.0.0  
**最后更新**: 2026-03-11 (Phase 3 完成)  
**维护者**: ProClaw Team  
**状态**: Phase 3 已完成，准备进入 Phase 4 (LLM Router + Parser + Coordinator)
