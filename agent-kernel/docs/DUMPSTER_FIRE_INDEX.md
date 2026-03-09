# 🔥 Dumpster Fire Index — 初版实现完成度评估

> **评估日期**: 2026-03-08
> **评估范围**: `proclaw-agent-kernel` 全仓库
> **评估基线**: `schema/ARCHITECTURE_DESIGN_v4.md` (1,671 行规格说明)

---

## 📊 总览评分

| 维度 | 得分 | 火焰等级 | 说明 |
|------|------|---------|------|
| **总体完成度** | **32/100** | 🔥🔥🔥 | 骨架已搭好，核心管线可跑(Mock模式)，但距规格说明差距巨大 |

---

## 🗂️ 分层 Dumpster Fire 指数

### Layer 1: TypeScript 控制层 (Gateway)

| 模块 | 完成度 | 🔥 指数 | 状态 | 关键问题 |
|------|--------|---------|------|---------|
| **Gateway Controller** | 90% | 🟢 | 可用 | HTTP 端点定义完整，健康检查正常 |
| **Request Queue** | 95% | 🟢 | 可用 | 按 Session 串行化，FIFO 实现完整 |
| **Router** | 85% | 🟢 | 可用 | 路由逻辑真实，但无数据库持久化（纯内存） |
| **Scheduler** | 90% | 🟢 | 可用 | Cron + Timeout 调度正常工作 |
| **MCP Service** | 95% | 🟢 | 可用 | MCP 客户端初始化和技能连接完整 |
| **Telemetry** | 85% | 🟢 | 可用 | OpenTelemetry 集成正确 |
| **Kernel Service** | 80% | 🟡 | 部分 | HTTP 调用到 Python Kernel 有超时处理 |
| **Executor** | 40% | 🔴 | 残缺 | `executeWithKernel()` 是**注释掉的空壳**；技能配置硬编码 |
| **TypeScript 测试** | 0% | 💀 | 不存在 | 23 个 TS 文件，**零测试**；`jest-e2e.json` 是空文件 |
| **认证/授权** | 0% | 💀 | 不存在 | 无 JWT、无 API Key、无 RBAC |
| **数据库持久化** | 0% | 💀 | 不存在 | 所有状态纯内存，重启全丢 |

**Gateway 层综合**: **55%** — 🔥🔥 (框架健全，但关键集成是空壳)

---

### Layer 2: Python 智能层 (Kernel)

| 模块 | 完成度 | 🔥 指数 | 状态 | 关键问题 |
|------|--------|---------|------|---------|
| **FastAPI Main** | 90% | 🟢 | 可用 | 路由完整、生命周期管理正确 |
| **Storage Adapter (File)** | 95% | 🟢 | 可用 | JSON 文件存储完整实现，生产级代码 |
| **Storage Tools** | 90% | 🟢 | 可用 | 25 个存储工具函数全部实现 |
| **Runtime Store** | 100% | 🟢 | 可用 | 存储适配器封装层，逻辑正确 |
| **Schemas / Models** | 100% | 🟢 | 可用 | Pydantic 数据模型完整，定义良好 |
| **Executor Client** | 90% | 🟢 | 可用 | HTTP 客户端带错误处理 |
| **Process Compiler** | 70% | 🟡 | 部分 | 流程上下文编译工作，但 `_extract_memory_references()` 是 TODO 桩 |
| **Session Host** | 75% | 🟡 | 部分 | 任务生成管理正常；`submit_long_term_candidate()` 是桩（直接 return True） |
| **Scheduler** | 90% | 🟢 | 可用 | asyncio 任务管理和工人循环完整 |
| **Agent Thread** | 50% | 🔴 | 残缺 | Mock 模式返回假结果；真实模式需要 OpenAI API Key，无 Key 会崩溃 |
| **Prime Personality** | 30% | 🔴 | 残缺 | Mock 模式生成假 IR；真实模式 LLM 调用已注释；无 API Key 时无 fallback 会崩溃 |
| **Master Compiler** | 30% | 🔴 | 残缺 | `recent_topics` 硬编码为空 `[]`（TODO）；无实际上下文提取 |
| **SQLite Adapter** | 60% | 🟡 | 部分 | 骨架存在，但未在主流程中使用 |
| **Python 测试** | 35% | 🔴 | 残缺 | 存储层测试优秀(7/7)；其他 8 个主要模块**零测试** |

**Python Kernel 综合**: **60%** — 🔥🔥 (存储层可圈可点，智能层大量桩代码)

---

### Layer 3: MCP Skills

| 模块 | 完成度 | 🔥 指数 | 状态 | 关键问题 |
|------|--------|---------|------|---------|
| **fs-skill (TS)** | 95% | 🟢 | 可用 | 完整 MCP Server：read/write/list + 路径白名单 |
| **shell-skill (TS)** | 95% | 🟢 | 可用 | 完整 MCP Server：命令执行 + 黑名单 + 超时 |
| **fs-skill (Python)** | 90% | 🟢 | 可用 | MCP 文件系统技能完整实现 |
| **shell-skill (Python)** | 90% | 🟢 | 可用 | MCP Shell 技能带安全检查 |
| **gateway-render-skill** | 20% | 🔴 | 残缺 | 目录存在，实现细节不明 |
| **Skills 测试** | 0% | 💀 | 不存在 | 零测试覆盖 |

**Skills 层综合**: **75%** — 🔥 (实现质量不错，但无测试保障)

---

### Layer 4: 共享包 (Packages)

| 包名 | 完成度 | 🔥 指数 | 状态 | 说明 |
|------|--------|---------|------|------|
| **shared-schema** | 100% | 🟢 | 可用 | TypeScript 类型定义，与 Python 模型对齐 |
| **skill-protocol** | 100% | 🟢 | 可用 | MCP 协议定义 |
| **observability** | 100% | 🟢 | 可用 | 遥测标准定义（仅类型，非运行时） |

**注**: 这些包仅为类型/Schema 定义，无运行时逻辑，所以 100% "完成"。

---

## 🔥 架构规格 vs 实际实现（差距分析）

> 基线文档: `schema/ARCHITECTURE_DESIGN_v4.md` — 知识图谱合成引擎

| 架构规格要求 | 实现状态 | 🔥 指数 | 差距说明 |
|-------------|---------|---------|---------|
| **知识图谱核心** (fact/concept/domain/index 节点) | 0% | 💀 | 连数据模型都不存在 |
| **边关系 + 权重 + 证据追踪** | 0% | 💀 | 完全没有图结构 |
| **Embedding 向量 + 语义相似度** | 0% | 💀 | 无 pgvector、无向量存储 |
| **HDBSCAN 聚类 + Louvain 社区检测** | 0% | 💀 | 无任何图算法 |
| **异构认知管线** (3 模型共识: Claude+GPT-4+规则引擎) | 0% | 💀 | 仅 1 个模型(Prime)，且用 Mock |
| **依赖 DAG** (变更传播、陈旧检测、拓扑重建) | 0% | 💀 | 完全不存在 |
| **PostgreSQL + pgvector 后端** | 0% | 💀 | 仅用文件/SQLite |
| **基本请求→会话→任务管线** | 80% | 🟡 | ✅ 已实现 |
| **本地技能执行 (文件/Shell)** | 90% | 🟢 | ✅ 已实现 |
| **MCP 协议集成** | 85% | 🟢 | ✅ 已实现 |
| **上下文编译器框架** | 40% | 🔴 | 框架在，核心逻辑是 TODO |
| **OpenTelemetry 可观测性** | 70% | 🟡 | 集成存在，但指标有限 |

**架构规格匹配度**: **~15%** — 💀💀💀 (代码实现的是一个**简单代理内核**，规格描述的是一个**知识图谱合成引擎**，它们是**根本不同的系统**)

---

## 🛡️ 安全 Dumpster Fire 指数

| 安全维度 | 状态 | 🔥 指数 | 说明 |
|---------|------|---------|------|
| **认证 (Authentication)** | 不存在 | 💀 | 无 JWT、无 API Key、无 OAuth |
| **授权 (Authorization)** | 不存在 | 💀 | 无 RBAC、无 ACL、无权限检查 |
| **输入验证** | 最基础 | 🔴 | DTO 有类型校验，但 `message` 字段无消毒 |
| **速率限制** | 不存在 | 💀 | 任何人可无限发请求 |
| **LLM Prompt 注入防护** | 不存在 | 💀 | 用户消息直接传入 LLM 系统提示 |
| **路径遍历防护** | 已实现 | 🟢 | ✅ Skills 有路径白名单验证 |
| **危险命令过滤** | 已实现 | 🟢 | ✅ Shell skill 有命令黑名单 |
| **超时保护** | 已实现 | 🟢 | ✅ Shell + Gateway 有超时限制 |
| **HTTPS** | 不存在 | 🔴 | 假设安全传输但未强制 |
| **CSRF 防护** | 不存在 | 🔴 | POST 端点无 CSRF Token |
| **密钥管理** | 原始 | 🔴 | API Key 存 `.env` 文件，无 Vault |

**安全评分**: **20/100** — 🔥🔥🔥🔥 (路径/命令安全做得好，但身份安全完全缺失)

---

## 🧪 测试 Dumpster Fire 指数

| 测试维度 | 状态 | 🔥 指数 | 具体数据 |
|---------|------|---------|---------|
| **Python 存储层测试** | 优秀 | 🟢 | 7/7 通过，File + SQLite 双适配器 |
| **Python E2E 测试** | 良好 | 🟢 | 4/4 通过，验证会话/任务/快照流程 |
| **Python 核心模块测试** | 最基础 | 🟡 | 3/3 通过，6 个因依赖缺失跳过 |
| **Python 智能层测试** | 不存在 | 💀 | Personality/Compiler/Thread 零测试 |
| **Python Skills 测试** | 不存在 | 💀 | fs-skill/shell-skill 零测试 |
| **TypeScript 测试** | 不存在 | 💀 | 23 个 TS 文件，**零测试文件** |
| **TS↔Python 集成测试** | 不存在 | 💀 | 跨语言边界完全无覆盖 |
| **安全测试** | 不存在 | 💀 | 无路径遍历/注入/越权测试 |
| **性能测试** | 不存在 | 💀 | 无负载测试/基准测试 |
| **断言质量** | 高 | 🟢 | 51+ 断言，均有中文错误消息 |

| 指标 | 值 |
|------|-----|
| Python 测试总数 | 20 (14 运行 + 6 跳过) |
| TypeScript 测试总数 | 0 |
| Python 函数覆盖率 | ~7% (20/282 函数) |
| TypeScript 覆盖率 | 0% |
| 模块覆盖率 (已测/总计) | 3/11 (27%) |

**测试评分**: **25/100** — 🔥🔥🔥 (存储层优秀，其余大片荒漠)

---

## 🏗️ 工程基础设施 Dumpster Fire 指数

| 维度 | 状态 | 🔥 指数 | 说明 |
|------|------|---------|------|
| **CI/CD 流水线** | 不存在 | 💀 | `.github/workflows/` 为空 |
| **Docker 容器化** | 不存在 | 💀 | 无 Dockerfile、无 docker-compose |
| **数据库 Migration** | 不存在 | 💀 | 无 Alembic/Flyway，无 schema 版本控制 |
| **Monorepo 构建** | 已配置 | 🟢 | Turbo + npm workspaces 正常工作 |
| **代码格式化** | 已配置 | 🟢 | Prettier (TS)、Black + Ruff (Python) |
| **类型检查** | 已配置 | 🟡 | TypeScript strict；Python mypy 已配但未验证 |
| **LICENSE 文件** | 缺失 | 🔴 | README 声明 MIT 但**无 LICENSE 文件** |
| **环境配置** | 部分 | 🟡 | `.env.example` 存在，但大量默认值硬编码 |
| **文档** | 优秀 | 🟢 | 架构文档全面、README 详尽 |
| **QUICKSTART** | 良好 | 🟢 | 有快速启动指南 |

**基础设施评分**: **30/100** — 🔥🔥🔥 (构建和文档不错，DevOps 完全缺失)

---

## 📈 综合 Dumpster Fire 仪表盘

```
                        🔥 DUMPSTER FIRE 综合指数 🔥

    ┌─────────────────────────────────────────────────────────┐
    │                                                         │
    │   架构规格匹配度    ████░░░░░░░░░░░░░░░░░░░░░░  15%   │
    │   安全性            █████░░░░░░░░░░░░░░░░░░░░░░  20%   │
    │   测试覆盖          ██████░░░░░░░░░░░░░░░░░░░░░  25%   │
    │   基础设施          ████████░░░░░░░░░░░░░░░░░░░  30%   │
    │   总体完成度        ████████░░░░░░░░░░░░░░░░░░░  32%   │
    │   Gateway 控制层    ██████████████░░░░░░░░░░░░░  55%   │
    │   Python 智能层     ███████████████░░░░░░░░░░░░  60%   │
    │   Skills 技能层     ███████████████████░░░░░░░░  75%   │
    │   文档质量          ██████████████████████░░░░░  85%   │
    │   存储层            ████████████████████████░░░  95%   │
    │                                                         │
    └─────────────────────────────────────────────────────────┘

    🔥 总 Dumpster Fire 指数: 4.2 / 10
       (10 = 废墟, 1 = 生产就绪)

    判定: 🔥🔥🔥🔥⬜⬜⬜⬜⬜⬜
          "着火了但消防队已经在路上"
```

---

## 🏷️ 火焰等级图例

| 图标 | 等级 | 含义 |
|------|------|------|
| 🟢 | 无火 | 功能完整，质量可接受 |
| 🟡 | 小火 | 基本可用，有已知缺陷 |
| 🔴 | 中火 | 残缺不全，需大量补充 |
| 💀 | 灾难 | 完全不存在或纯桩代码 |

---

## 🎯 最需要灭火的 Top 10 优先级

| 优先级 | 问题 | 影响 | 预估工作量 |
|--------|------|------|-----------|
| **P0** | `executeWithKernel()` 是空壳 | Gateway→Kernel 管线断裂 | 2-4h |
| **P0** | 零认证/授权 | 任何人可执行任意命令 | 1-2 天 |
| **P0** | Prime Personality 无 API Key 会崩溃 | 非 Mock 模式不可用 | 4-8h |
| **P1** | 无 CI/CD | 无法自动化质量保障 | 4-8h |
| **P1** | TypeScript 零测试 | 23 个文件无任何保障 | 2-3 天 |
| **P1** | 无 Docker 容器化 | 无法部署到任何环境 | 4-8h |
| **P1** | 内存状态无持久化 | 重启丢失所有数据 | 1-2 天 |
| **P2** | 架构规格 v4 完全未实现 | 知识图谱是空中楼阁 | 数周-数月 |
| **P2** | 上下文编译器是 TODO | 智能层核心逻辑缺失 | 1-2 周 |
| **P2** | 无数据库 Migration | 无法管理 Schema 演进 | 1-2 天 |

---

## 📝 TODO / FIXME 地雷分布

| 文件 | 行号 | 内容 | 严重度 |
|------|------|------|--------|
| `executor.service.ts` | 53 | `// TODO: Implement HTTP call to Python Kernel` | 🔴 关键管线断裂 |
| `executor.service.ts` | 139 | `// TODO: Load skill configuration from database or config` | 🟡 硬编码 |
| `executor.service.ts` | 165 | `// TODO: Load from database or config file` | 🟡 硬编码 |
| `master_compiler.py` | 49 | `# TODO: Extract from memory` | 🔴 核心功能缺失 |
| `process_compiler.py` | 47 | `# TODO: Implement intelligent memory retrieval` | 🔴 核心功能缺失 |
| `session_host.py` | 115 | `submit_long_term_candidate()` → `return True` | 🟡 桩函数 |
| `agent_thread.py` | 73-148 | `_run_mock()` 返回假结果 | 🟡 Mock 依赖 |

---

## 🧾 最终判定

```
┌──────────────────────────────────────────────────────────────┐
│                                                              │
│   项目状态:  "概念验证原型" (PoC / Prototype)               │
│                                                              │
│   实际完成:  一个能在 Mock 模式下跑通                        │
│              请求→会话→任务→(假)执行 管线的代理框架           │
│                                                              │
│   规格完成:  v4.0 知识图谱架构的 ~15% (基础管线)            │
│                                                              │
│   可部署性:  ❌ 不可部署 (无 Docker/CI/Auth/持久化)          │
│                                                              │
│   亮点:      ✅ 存储抽象层设计优秀                           │
│              ✅ MCP Skills 实现完整且有安全控制               │
│              ✅ 架构文档极其详尽                              │
│              ✅ 双层架构分离关注点思路正确                    │
│                                                              │
│   总分:      32/100                                          │
│   火焰等级:  🔥🔥🔥🔥 (4.2/10)                              │
│   定性描述:  "着火了但消防队已经在路上"                      │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

---

*本评估基于代码快照静态分析，未运行实际服务验证。火焰指数仅供参考，不构成投资建议。* 🔥

---

---

# 🔥 Dumpster Fire Index — Gateway V2.0 专项审计

> **评估日期**: 2026-03-09  
> **评估范围**: `agent-kernel/apps/gateway/` (V2.0 重构版)  
> **评估基线**: `schema/schema.png`（架构图）+ `apps/gateway/ARCHITECTURE.md`  
> **对比参考**: 上一版 PR 的 Gateway V1.0 评估（见本文档顶部 Layer 1 段落）  
> **评估者**: copilot-swe-agent 代码审计

---

## 📌 背景说明

Gateway 模块是 agent kernel 的**对外网关层**（schema 图左侧 `对外网关` 节点），在架构中承担：

- **接入适配**：HTTP / CLI / WebSocket / QQ 等平台统一入口  
- **IR 转换**：外部消息 → `InputMessage`（中间表示），`OutputMessage` → 平台格式  
- **请求管理**：写入文件系统信箱 `inbox/`，作为与 Python Kernel 的异步边界  
- **回调接收**：Kernel 处理完成后通过 `POST /gateway/webhook/kernel-response` 回写 `outbox/`  
- **定时调度**：`定时请求调度器` 节点，通过 cron/timeout 向请求管理器注入计划任务  
- **会话路由**：维护 userId → sessionId 映射，决策 create / reuse / queue  

---

## 📊 V2.0 综合评分

| 维度 | V1.0 得分 | V2.0 得分 | 变化 | 说明 |
|------|-----------|-----------|------|------|
| **整体设计合理性** | 55% | **75%** | ▲+20% | 信箱架构落地，异步边界清晰 |
| **关键管线完整性** | 40% | **70%** | ▲+30% | WebhookController 已实现（但原始未注册） |
| **测试覆盖** | 0% | **62 tests** | ▲从无到有 | 5 个 spec 文件覆盖核心服务 |
| **代码质量** | 60% | **72%** | ▲+12% | 减少了 stub 代码，但仍有残留缺陷 |
| **安全性** | 20% | **28%** | ▲+8% | 修复路径遍历漏洞，但无认证 |
| **架构符合度** | ~50% | **~80%** | ▲+30% | 完全匹配 schema 图的 Gateway 职责 |

**V2.0 Gateway 综合**: **73%** — 🟡 (相比 V1.0 的 55% 有显著提升)

---

## 🗂️ V2.0 模块级评估表

### ✅ 已激活模块（在 AppModule 注册）

| 模块 | 完成度 | 🔥 指数 | 对应 Schema 节点 | 关键发现 |
|------|--------|---------|-----------------|---------|
| **GatewayController** | 92% | 🟢 | `对外网关` | 输入验证已补全（ValidationPipe）；健康检查无实际探针 |
| **GatewayService** | 85% | 🟢 | `对外网关` | 信箱写入正确；`waitForResponse` 超时处理良好 |
| **StorageService** | 90% | 🟢 | `请求管理器` | 原子写入正确；O(N) 索引扫描在大规模下有性能问题 |
| **IRConverterService** | 75% | 🟡 | IR 转换层 | ⚠️ 严重：JSON Schema 用 snake_case，TS 接口用 camelCase，验证恒失败 |
| **RouterService** | 82% | 🟢 | `对外网关` 路由 | 纯内存状态，重启丢失全部 session |
| **WebhookController** | 80% | 🟢 | `对外网关` 回调入口 | **P0 已修复**：原始版本未注册进 Module，endpoint 返回 404 |
| **SchedulerService** | 85% | 🟢 | `定时请求调度器` | **P0 已修复**：原始版本接入废弃的 RequestQueueService，任务静默丢弃 |
| **CliAdapter** | 88% | 🟢 | 平台适配层 | stdin/stdout JSON 协议正确；`healthCheck()` 仅返回 isRunning |

### ⚠️ 已声明但未激活的模块（未注册进 AppModule）

| 模块 | 在 AppModule? | 对应 Schema 节点 | 影响 | 建议 |
|------|--------------|-----------------|------|------|
| **ExecutorModule** (MCP 工具执行) | ❌ 未注册 | `Agentic OS Interface Skill` | `POST /api/v1/executor/execute` 404 | 评估是否应在 Gateway 或仅 Python Kernel 端执行 |
| **McpModule** (MCP 客户端池) | ❌ 未注册 | `Skill lib` 调用层 | MCP 连接无法建立 | ExecutorModule 激活时同步注册 |
| **TelemetryModule** (OpenTelemetry) | ❌ 未注册 | 横切关注点 | 无任何链路追踪数据 | 应立即加入 AppModule |
| **KernelModule** (Python Kernel HTTP 客户端) | ❌ 未注册 | Python Kernel 直调路径 | KernelService 无法被注入 | 由 ExecutorModule 按需引入 |
| **RequestQueueModule** | ❌ 废弃 | — | 遗留代码混淆设计意图 | **建议删除** |

---

## 🔴 关键缺陷详细分析

### P0 级（已在本次 PR 修复）

| # | 缺陷 | 修复方式 | 验证 |
|---|------|---------|------|
| 1 | `WebhookController` 未注册 → `/gateway/webhook/kernel-response` 返回 404 | 添加至 `GatewayModule.controllers` | ✅ typecheck 通过 |
| 2 | `SchedulerService` 注入废弃 `RequestQueueService` → 定时任务静默丢弃 | 改为注入 `GatewayService`，写入文件信箱 | ✅ typecheck 通过 |
| 3 | `SchedulerModule` 未注册进 `AppModule` → 调度器永不启动 | 加入 `AppModule.imports` | ✅ typecheck 通过 |
| 4 | `saveAttachment` 文件名仅过滤字符但未去除 `..` → 路径遍历安全漏洞 | 先 `path.basename()` 再字符过滤 | ✅ 测试验证 |
| 5 | `executeWithKernel()` 是注释掉的 TODO stub | 接入 `KernelService.execute()` | ✅ typecheck 通过 |

### P1 级（本次 PR 修复）

| # | 缺陷 | 修复方式 |
|---|------|---------|
| 6 | `IRConverterService.loadSchemas()` 在构造函数中 fire-and-forget | 改为 `OnModuleInit.onModuleInit()` 中 `await` |
| 7 | `getSessionStatus()` 使用内联 `require('path')` / `require('fs')` | 改为模块级 `import` |
| 8 | `ChatRequestDto` 无字段验证，空 userId/message 可写入信箱 | 添加 `class-validator` 装饰器 + `ValidationPipe` |
| 9 | `pollOutbox` 与 `saveResponseToOutbox` 可重复 emit 同一响应 | 添加 `emittedRequestIds` Set 去重 |

### P1 级（本次 PR 未修复 — 需独立 PR）

| # | 缺陷 | 影响 | 预估工作量 |
|---|------|------|-----------|
| 10 | **IR 字段名不匹配**：JSON Schema 用 `snake_case`（`device_id`, `user_id`），TypeScript 接口用 `camelCase`（`deviceId`, `userId`）→ AJV 验证恒失败，Python Kernel 读到的字段名与 schema 不符 | 数据交换协议不一致，Python Kernel 解析风险 | 1-2 天（需协调 Python 端） |
| 11 | `RouterService` 会话纯内存存储，重启丢失所有 session | 生产环境重启后所有用户 session 失效 | 1-2 天（接入 Redis 或文件持久化） |
| 12 | `StorageService.getResponseFromOutbox()` / `getRequestStatus()` O(N) 全量扫描 JSONL 索引 | 信箱文件增大后延迟线性增长 | 1 天（添加内存索引缓存或数据库） |
| 13 | `WebhookController` 无认证 → 任何人可 POST 伪造内核响应 | 恶意响应可注入系统 | 4-8h（添加 HMAC 签名或 Bearer Token） |
| 14 | `GatewayController.getHealth()` 始终返回 `storage: 'healthy'` 而不做实际检查 | 存储不可用时健康检查仍报 OK | 2h |

### P2 级

| # | 缺陷 | 说明 |
|---|------|------|
| 15 | `RouterService.generateSessionId()` 使用 `Date.now() + random`，非 UUIDv4 | 碰撞概率低但非标准 |
| 16 | `ExecutorService` / `McpService` 职责边界模糊 | Schema 中 `Agentic OS Interface Skill` 在 Python Kernel 侧，不在 Gateway 侧 |
| 17 | `RequestQueueService` 标记 `@deprecated` 但仍保留全量代码 | 迷惑性遗留代码，建议删除 |
| 18 | `TelemetryModule` 已实现但未注册，OpenTelemetry 完全无效 | 可观测性归零 |
| 19 | `StorageService` 无 `OnModuleDestroy` 清理，轮询器在测试中泄漏 | Jest 每次报 `force exit` 警告 |

---

## 🧪 测试质量分析

| 测试文件 | 测试数 | 覆盖范围 | 质量评价 |
|---------|--------|---------|---------|
| `storage.service.spec.ts` | 16 | 初始化、信箱读写、附件、状态查询、事件、历史 | 🟢 全面 |
| `ir-converter.service.spec.ts` | 10 | IR 转换、附件处理、平台编译、验证降级 | 🟢 全面 |
| `router.service.spec.ts` | 12 | 三种路由决策、会话注册、状态切换 | 🟢 全面 |
| `gateway.service.spec.ts` | 16 | 请求接受流程、超时、状态查询 | 🟢 全面 |
| `webhook.controller.spec.ts` | 8 | 成功/失败/partial 状态、错误传播 | 🟢 全面 |
| **合计** | **62** | — | — |

**缺失测试**（待补充）：

| 未覆盖的组件 | 原因 / 建议 |
|------------|-----------|
| `SchedulerService` | 需要 fake timers（`jest.useFakeTimers()`） |
| `ExecutorService` 路径遍历防护 | `resolveAllowedPath` 是安全关键代码，应有专项测试 |
| `CliAdapter` | 需要 stdin mock |
| E2E 全链路（`handleChatRequest` → 写信箱 → webhook 回调 → `waitForResponse` 解析） | 需要临时文件系统 + 集成测试环境 |

---

## 🛡️ 安全评估（V2.0）

| 安全维度 | V1.0 | V2.0 | 说明 |
|---------|------|------|------|
| **认证/授权** | 💀 0% | 💀 0% | 仍无 JWT / API Key |
| **输入验证** | 🔴 30% | 🟡 65% | ChatRequestDto 已有长度+类型验证 |
| **路径遍历防护** | 🟡 60% | 🟢 90% | **本次修复**：`saveAttachment` 使用 `path.basename()` |
| **Webhook 认证** | 💀 0% | 💀 0% | 任何人可伪造内核回调 |
| **速率限制** | 💀 0% | 💀 0% | 无限制 |
| **CSRF** | 💀 0% | 💀 0% | POST 无 Token |
| **LLM Prompt 注入防护** | 💀 0% | 💀 0% | 消息直传内核无消毒 |
| **事件重放防护** | 💀 0% | 🟡 50% | **本次修复**：重复 emit 去重 |

**安全总分**: **22/100** (+2) — 🔥🔥🔥🔥

---

## 📈 V2.0 Dumpster Fire 综合仪表盘

```
                        🔥 GATEWAY V2.0 DUMPSTER FIRE 指数 🔥

    ┌──────────────────────────────────────────────────────────────────┐
    │                                                                  │
    │   认证/安全            ██░░░░░░░░░░░░░░░░░░░░░░░░░░░░  22%      │
    │   测试覆盖 (上线前)    █████████░░░░░░░░░░░░░░░░░░░░░  35%      │
    │   关键管线完整性       ████████████████████░░░░░░░░░░  70%      │
    │   代码质量             ████████████████████░░░░░░░░░░  72%      │
    │   整体设计合理性       █████████████████████░░░░░░░░░  75%      │
    │   架构 schema 符合度   ████████████████████████░░░░░░  80%      │
    │   IR 转换层完整性      ████████████████████████░░░░░░  82%      │
    │   存储层稳健性         ████████████████████████░░░░░░  90%      │
    │   文档完整性           ████████████████████████████░░  90%      │
    │                                                                  │
    └──────────────────────────────────────────────────────────────────┘

    🔥 Gateway V2.0 Dumpster Fire 指数: 3.0 / 10
       (10 = 废墟, 1 = 生产就绪)

    判定: 🔥🔥🔥⬜⬜⬜⬜⬜⬜⬜
          "火势受控，但 Webhook 认证和 IR 字段名是两颗未拆的雷"
```

---

## 🎯 V2.0 → V2.1 优先灭火清单

| 优先级 | 问题 | 影响 | 预估工作量 |
|--------|------|------|-----------|
| **P0** | IR 字段名 snake_case vs camelCase 不匹配 | Python Kernel 读写格式错误 | 1-2 天 |
| **P0** | WebhookController 无认证 | 任意伪造 Kernel 回调 | 4-8h |
| **P1** | RouterService session 无持久化 | 重启丢失所有路由状态 | 1-2 天 |
| **P1** | TelemetryModule 未注册进 AppModule | 零可观测性 | 1h |
| **P1** | 删除废弃 RequestQueueModule/Service | 减少迷惑性遗留代码 | 2h |
| **P1** | ExecutorModule/McpModule 注册或重定位 | 消除孤儿模块 | 4h |
| **P2** | StorageService O(N) 扫描改为内存索引 | 规模化性能保障 | 1 天 |
| **P2** | `SchedulerService` 测试（fake timers） | 覆盖定时任务关键路径 | 4h |
| **P2** | `ExecutorService.resolveAllowedPath` 安全测试 | 路径遍历防护验证 | 2h |
| **P3** | `GatewayController.getHealth()` 真实探针 | 准确反映系统可用性 | 2h |

---

## 🧾 V2.0 最终判定

```
┌────────────────────────────────────────────────────────────────────┐
│                                                                    │
│   模块状态:  "接近可集成的控制层"                                  │
│                                                                    │
│   已实现:   ✅ 文件系统信箱异步模式（inbox/outbox）                │
│             ✅ Kernel 回调 Webhook（已修复注册问题）                │
│             ✅ 多平台适配器接口（CLI 已实现）                       │
│             ✅ 定时调度器接入网关信箱（已修复连接断裂）              │
│             ✅ 完整 IR 转换层（含 JSON Schema 验证框架）            │
│             ✅ 输入验证（class-validator）                          │
│             ✅ 62 个单元测试覆盖核心服务                            │
│                                                                    │
│   关键未完成: ❌ IR wire format 字段名不一致（camelCase≠snake_case）│
│              ❌ Webhook 无认证                                      │
│              ❌ 零认证/授权（整体）                                 │
│              ❌ Session 状态纯内存（重启归零）                       │
│              ❌ 4 个模块孤儿（未注册进 AppModule）                  │
│                                                                    │
│   vs V1.0:   Gateway V1.0 (55%) → V2.0 (73%) ▲+18%               │
│              V1.0 的 executeWithKernel stub → V2.0 已接入          │
│              V1.0 的零测试 → V2.0 有 62 个测试                     │
│              V1.0 的 WebhookController 缺失 → V2.0 已实现+注册     │
│                                                                    │
│   总分:      73/100 (vs V1.0: 55/100)                              │
│   火焰等级:  🔥🔥🔥 (3.0/10)                                       │
│   定性描述:  "设计意图明确，实现骨架健壮，但有两颗雷需要拆除"      │
│                                                                    │
└────────────────────────────────────────────────────────────────────┘
```

---

*V2.0 评估基于代码审计 + 静态分析，参考 schema/schema.png 架构图。评估日期 2026-03-09。* 🔥

