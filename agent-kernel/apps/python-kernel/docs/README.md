# Agent Thread Runtime 文档目录

本目录包含 Atomic Agent Thread 实现的完整技术文档。

## 📚 文档清单

### 1. [AGENT_THREAD_RUNTIME.md](./AGENT_THREAD_RUNTIME.md)
**架构概述文档**

- 核心设计原则（Event Log + Working Set）
- 模块架构总览
- 各组件详细说明
- 配置指南
- 最佳实践
- 故障排查

**适合读者：** 架构师、系统设计师、需要理解整体设计的开发者

---

### 2. [API_REFERENCE.md](./API_REFERENCE.md)
**API 参考手册**

- 所有类和函数的完整 API 签名
- 参数说明
- 返回值说明
- 使用示例
- 配置参考

**适合读者：** 开发者、集成工程师、需要查阅具体 API 的用户

---

### 3. [ARCHITECTURE_FLOWS.md](./ARCHITECTURE_FLOWS.md)
**架构流程详解**

- SEE-ACT-UPDATE 循环详细流程
- Working Set 构建流程
- Execution Coordinator 路由流程
- 上层干预时序图
- Phase 切换流程
- 数据流总结

**适合读者：** 需要深入理解执行流程的开发者、调试工程师

---

## 🚀 快速开始

### 第一步：理解架构
阅读 [AGENT_THREAD_RUNTIME.md](./AGENT_THREAD_RUNTIME.md) 了解：
- Event Log + Working Set 模型
- SEE-ACT-UPDATE 循环
- Phase-based 执行

### 第二步：查阅 API
阅读 [API_REFERENCE.md](./API_REFERENCE.md) 了解：
- 如何创建 Agent Thread
- 如何使用 Working Set Builder
- 如何干预线程执行

### 第三步：理解流程
阅读 [ARCHITECTURE_FLOWS.md](./ARCHITECTURE_FLOWS.md) 了解：
- 数据如何流动
- 干预如何工作
- 状态如何转换

---

## 📖 阅读顺序建议

### 对于系统架构师
1. AGENT_THREAD_RUNTIME.md（整体架构）
2. ARCHITECTURE_FLOWS.md（流程细节）
3. API_REFERENCE.md（实现参考）

### 对于应用开发者
1. AGENT_THREAD_RUNTIME.md（理解概念）
2. API_REFERENCE.md（学会使用 API）
3. 查看 `examples/atomic_agent_demo.py`（实际代码）

### 对于调试工程师
1. API_REFERENCE.md（了解可用工具）
2. ARCHITECTURE_FLOWS.md（理解执行流程）
3. AGENT_THREAD_RUNTIME.md（理解设计意图）

---

## 🎯 核心概念速查

### Event Log vs Working Set
```
Event Log: 完整历史记录（无限增长，不直接喂给模型）
    ↓
Working Set Builder: 规则筛选
    ↓
Working Set: 有界上下文（固定大小，实际喂给模型）
```

### SEE-ACT-UPDATE
```
SEE:   从 Event Log 构建 Working Set
ACT:   LLM 生成输出，Parser 解析意图
UPDATE: 执行意图，记录到 Event Log
```

### Phase 切换
```
Agent 自主决定 ←───┐
                    │
                    ▼
EXPLORE → EXECUTE → COMPLETE
    ▲         │         │
    └─────────┴─────────┘
    上层强制干预
```

---

## 🔧 关键 API 速查

### 创建并运行 Agent
```python
from thread_runtime.agent_thread import AgentThread
from thread_runtime.working_set_builder import WorkingSetBuilder
from executors_client.coordinator_interface import get_execution_coordinator

agent = AgentThread(
    task=task_snapshot,
    compiled_context=compiled_context,
    coordinator=get_execution_coordinator(),
    ws_builder=WorkingSetBuilder(),
)
result = await agent.run()
```

### 上层干预
```python
from thread_runtime.scheduler import get_scheduler

scheduler = get_scheduler()

# 查看状态
log = await scheduler.get_thread_log(task_id)

# 暂停
await scheduler.pause_task(task_id, "Review needed")

# 修改阶段
await scheduler.update_thread_phase(task_id, "execute")

# 恢复
await scheduler.resume_task(task_id)
```

---

## 📁 相关文件

- 示例代码：`../examples/atomic_agent_demo.py`
- 实现总览：`../ATOMIC_AGENT_IMPLEMENTATION.md`
- 配置文件：`../config/working_set_rules.yaml`, `../config/coordinator.yaml`

---

## 💡 设计原则总结

1. **规则驱动 > LLM 驱动**：Working Set 构建由规则决定，非 LLM
2. **有界上下文 > 无限历史**：Working Set 固定大小，Event Log 无限增长
3. **自主 + 干预**：Agent 自主执行，上层可强制干预
4. **原子操作**：系统操作通过 OS Interface 原子执行
5. **可观测性**：全量 Event Log 供上层查看

---

## 🆘 获取帮助

1. 查阅 [AGENT_THREAD_RUNTIME.md](./AGENT_THREAD_RUNTIME.md) 的故障排查部分
2. 查看 [API_REFERENCE.md](./API_REFERENCE.md) 的使用示例
3. 运行 `examples/atomic_agent_demo.py` 了解实际行为
4. 检查日志输出（使用 structlog）

---

**最后更新：** 2024年3月
