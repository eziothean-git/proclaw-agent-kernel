# 控制面概念定义

## 概述

在 Agent Kernel 架构中，**控制面（Control Plane）**与**数据面（Data Plane）**是两个核心概念，分别对应不同级别的权限和职责。

## 定义

### 数据面（Data Plane）
**执行层**，处理具体的 Agent 任务执行。

- **权限级别**: Agent 级别
- **核心功能**:
  - 执行具体的 Skills（Bash, File, Code等）
  - 管理 Thread 生命周期
  - 执行 SEE-ACT-UPDATE 循环
  - 通过 DirectoryLockManager 进行资源协调

- **访问范围**: 
  - 只能访问允许的工作目录
  - 受限于配置的能力白名单
  - 通过 Capability Token 进行权限验证

- **代码标记**: 无特殊标记，默认编译

### 控制面（Control Plane）
**管理层**，负责系统级管理和协调。

- **权限级别**: Host/Prime 级别
- **核心功能**:
  - Session 管理（创建、删除、查询）
  - Process 生命周期管理
  - Thread 调度控制（暂停、恢复、取消）
  - 系统级资源查询和统计
  - 跨 Session 的协调

- **访问范围**:
  - 全局 Session/Process 可见性
  - 系统级配置管理
  - 可干预任何 Thread 的执行

- **代码标记**: `#[cfg(feature = "control-plane")]`

## 架构图示

```
┌─────────────────────────────────────────────────────────────┐
│                      控制面 (Control Plane)                   │
│                      Host/Prime 权限                         │
├─────────────────────────────────────────────────────────────┤
│  Session Host        Process Manager      Thread Scheduler   │
│  - 创建/删除 Session  - 创建/删除 Process  - 调度决策         │
│  - 查询全局状态      - 管理 Thread 集合   - 暂停/恢复 Thread │
│                                                              │
│  Skills:                                                     │
│  - OSInterfaceSkill (系统接口)                               │
│  - SchedulerSkill (调度管理)                                 │
└──────────────────────────┬──────────────────────────────────┘
                           │ gRPC / 内部调用
┌──────────────────────────▼──────────────────────────────────┐
│                      数据面 (Data Plane)                      │
│                      Agent 权限                              │
├─────────────────────────────────────────────────────────────┤
│  Agent Thread          ExecutionCoordinator    Skills        │
│  - SEE-ACT-UPDATE      - DirectoryLock管理    - Bash         │
│  - Working Set构建     - Skill路由            - File         │
│  - Event Log           - 资源协调             - Code Search  │
│                                                              │
│  约束:                                                       │
│  - 只能看到当前 Session                                      │
│  - 只能访问允许的目录                                        │
│  - 只能调用允许的 Skills                                     │
└─────────────────────────────────────────────────────────────┘
```

## 设计原因

### 1. 安全隔离
控制面技能具有更高权限（可管理所有 Session），如果默认启用可能带来安全风险。通过 feature flag 控制：

- **生产环境**: 可以只启用数据面，减少攻击面
- **管理场景**: 需要时启用控制面，进行系统管理

### 2. 部署灵活性

```toml
# 纯执行节点（Worker）
[features]
default = []  # 只包含数据面

# 管理节点（Host）
[features]
default = ["control-plane"]  # 包含控制面
```

### 3. 代码清晰性
通过 `#[cfg(feature = "control-plane")]` 明确标记哪些代码属于管理层：

```rust
// 数据面：始终可用
pub mod agent_thread;
pub mod scheduler;

// 控制面：可选启用
#[cfg(feature = "control-plane")]
pub mod session;
```

## 当前实现状态

| 组件 | 类型 | 状态 |
|------|------|------|
| Agent Thread | 数据面 | ✅ 已实现 |
| ExecutionCoordinator | 数据面 | ✅ 已实现 |
| DirectoryLockManager | 数据面 | ✅ 已实现 |
| Bash/File Skills | 数据面 | ✅ 已实现 |
| Session Host | 控制面 | ✅ 已实现，默认启用 |
| Process Manager | 控制面 | ✅ 已实现，默认启用 |
| SchedulerSkill | 控制面 | ✅ 已实现，feature-gated |
| OSInterfaceSkill | 控制面 | ✅ 已实现，feature-gated |

## 使用建议

### 单节点部署
```bash
# 启用所有功能
cargo build --features control-plane
```

### 分布式部署
```bash
# Worker 节点（纯数据面）
cargo build

# Host 节点（包含控制面）
cargo build --features control-plane
```

### 前端集成
- **普通任务**: 通过数据面 API 调用（ExecuteSkill）
- **管理操作**: 通过控制面 API 调用（CreateSession, CreateProcess等）
