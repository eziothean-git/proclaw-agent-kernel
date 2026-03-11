# System Skills 目录映射

## 目录结构

```
/home/eziothean/ProClaw/
├── skills/system-skills/           # Python/TypeScript 技能定义
│   ├── gateway_callback_skill.py   # Gateway 回调技能
│   └── ...                         # 其他系统级技能
│
└── kernel-v2/src/                  # Rust 实现（Agent Kernel）
    ├── session/
    │   ├── process.rs              # Process 管理
    │   ├── skills.rs               # Session Host SKILL 接口
    │   └── mod.rs
    ├── scheduler/
    │   ├── thread_executor.rs      # Thread 执行引擎
    │   ├── context_builder.rs      # 上下文构建
    │   └── ...
    └── llm/
        ├── router.rs               # LLM 多 Provider 路由
        ├── config.rs               # Provider 配置
        └── ...
```

## 映射关系

### Session Host 技能

| 技能名称 | skills/system-skills/ | kernel-v2/src/ | 说明 |
|---------|---------------------|----------------|------|
| Process Management | (待定义) | session/skills.rs | 创建/管理 Process |
| Thread Management | (待定义) | session/skills.rs | 在 Process 中管理 Thread |
| Gateway Callback | gateway_callback_skill.py | - | Gateway 回调处理 |

### 执行技能

| 技能名称 | skills/system-skills/ | kernel-v2/src/ | 说明 |
|---------|---------------------|----------------|------|
| Bash Execution | - | providers/bash.rs | 命令执行 |
| LLM Generation | - | llm/router.rs | 多 Provider LLM 调用 |
| Context Build | - | scheduler/context_builder.rs | 上下文构建 |

## 架构层次

```
User/Prime Personality
    ↓
Session Host (待实现)  ← 技能接口定义在 skills/system-skills/
    ↓
SessionHostSkills (Rust)  ← 实现: kernel-v2/src/session/skills.rs
    ↓
Process Manager  ← 实现: kernel-v2/src/session/process.rs
    ↓
Thread Executor  ← 实现: kernel-v2/src/scheduler/thread_executor.rs
    ↓
Execution Coordinator  ← 实现: kernel-v2/src/coordinator/
```

## 关键组件

### 1. LLM Router (kernel-v2/src/llm/router.rs)
- 多 Provider 支持（OpenAI/Ark/Local）
- 根据难度自动选择模型
- 异步请求管理

### 2. Process 层 (kernel-v2/src/session/process.rs)
- Process 文件持久化
- Thread 全量历史管理
- 快速查找和状态追踪

### 3. Session Host Skills (kernel-v2/src/session/skills.rs)
- 为 Prime Personality 提供 SKILL 接口
- Process 生命周期管理
- Thread 在 Process 中的管理

## 使用方式

### 从 Prime Personality 调用
```python
# 通过 SKILL 接口调用（待实现）
result = await session_host.create_process(
    session_id="session_001",
    goal="Analyze codebase",
    tags=["analysis"]
)
```

### 直接访问 Thread（保留）
```rust
// 简单任务可以直接访问，降低延迟
let executor = ThreadExecutor::new(
    storage,
    coordinator,
    llm_router,
    ...
).await?;
executor.run().await?;
```

## TODO

1. [ ] 在 skills/system-skills/ 定义 Session Host SKILL 的 Python/TypeScript 接口
2. [ ] 实现 Gateway 到 Agent Kernel v2 的 gRPC 调用
3. [ ] 完善 Local Skill 注册表（接入 BashWrapper 等 Providers）
4. [ ] 添加更多单元测试和集成测试