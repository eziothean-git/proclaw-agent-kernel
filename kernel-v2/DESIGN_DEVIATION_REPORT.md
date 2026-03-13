# 设计实现偏差报告

## 1. 当前实现状态

### ✅ 已完成部分
- **Data Plane**: Agent Thread, Block Composer, Execution Coordinator, Directory Lock Manager
- **ComposerSkill**: 统一的 Block 管理 + Composition + 带锁执行接口
- **控制面基础**: Session, Process, ThreadManager 结构存在
- **gRPC 服务**: 基本接口完整，get_resource_status 已恢复全功能

### ⚠️ 疑似设计理解偏差

#### 偏差 1: ComposerSkill 的定位
**我的实现**: 作为内部 Skill，封装 Block 管理和执行
```rust
pub struct ComposerSkill {
    composer: Arc<BlockComposerEngine>,
    coordinator: Arc<ExecutionCoordinator>,
    // ...
}
```

**可能的误解**: 是否应该暴露为 gRPC 服务？是否应该支持更多的控制面功能？

**问题**: 目前 ComposerSkill 与 SessionHostSkills 的关系不明确。

---

#### 偏差 2: OS Interface Skill / Scheduler Skill 的启用
**当前状态**: 用 `#[cfg(feature = "control-plane")]` 标记

**代码**:
```rust
#[cfg(feature = "control-plane")]
pub mod scheduler_skill;
#[cfg(feature = "control-plane")]
pub mod os_interface_skill;
```

**问题**: 
- 是否应该在默认 build 中启用？
- 这些 Skill 是否应该注册到 SkillRegistry？
- 目前 SkillRegistry 只注册了 BashSkill，控制面 Skills 未注册

---

#### 偏差 3: SessionHostSkills 与 ProcessManager 的关系
**我的理解**: SessionHostSkills 封装 ProcessManager 和 ThreadManager

**代码**:
```rust
pub struct SessionHostSkills {
    process_manager: Arc<RwLock<ProcessManager>>,
    thread_manager: Arc<ThreadManager>,
    block_composer: Arc<BlockComposerEngine>,
}
```

**问题**:
- SessionHostSkills 是否应该是唯一的控制面入口？
- OS Interface Skill 和 SessionHostSkills 功能重叠
- 没有清晰的职责划分

---

#### 偏差 4: Thread 的 Profile（Prime/Session/Task）
**当前实现**: Profile 只是 BlockComposer 的参数

**使用**:
```rust
composer.compose(session_id, task_id, Profile::Task, blocks, context)
```

**问题**:
- 不同的 Profile 是否应该对应不同的 Thread 类型？
- Prime/Session/Task Profile 是否应该有专门的 Thread 配置？
- 目前只是 token 预算不同，是否还需要其他差异？

---

#### 偏差 5: 控制面功能的实际可用性
**当前问题**:
- OSInterfaceSkill 和 SchedulerSkill 实现了，但没有在 gRPC 服务层暴露
- 没有注册到 SkillRegistry，无法通过 ExecuteSkill 调用
- ProcessManager::create_process 需要 mutable self，但 gRPC 服务层没有暴露

**疑问**:
- 控制面功能是应该通过 gRPC 直接暴露，还是通过 Skill 调用？
- 前端如何调用 create_process / create_thread？

---

## 2. 测试遇到的问题

### 问题 1: API 不匹配
尝试编写集成测试时发现：
- `ImmutableInput` 没有 `new()` 方法，需要直接构造结构体
- `ProcessManager::create_process` 参数是 `(session_id, process_goal, tags)`，不是 `ProcessDefinition`
- `ProcessManager::new` 是 async 的，但之前没注意到

**根本原因**: 我在没有详细阅读所有 API 的情况下假设了接口。

### 问题 2: 控制面 Skills 未注册
```rust
// SkillRegistry::new 只注册了 BashSkill
pub fn new(bash_skill: Arc<BashSkill>) -> Self {
    Self {
        bash_skill,
        #[cfg(feature = "control-plane")]
        scheduler_skill: None,  // 未注册
        #[cfg(feature = "control-plane")]
        os_interface_skill: None,  // 未注册
    }
}
```

**问题**: 即使启用了 control-plane feature，这些 Skills 也不会被注册。

### 问题 3: SessionHostSkills vs OSInterfaceSkill 重复
两者都提供类似功能：
- SessionHostSkills::create_process
- OSInterfaceSkill::create_process

**疑问**: 是否应该合并？还是分工不同？

---

## 3. 需要澄清的设计问题

### Q1: 控制面功能的暴露方式
选项 A: 直接通过 gRPC 方法暴露（如 `CreateProcess`）
选项 B: 通过 Skill 系统暴露（如 `ExecuteSkill { skill: "os_interface", tool: "create_process" }`）
选项 C: 两者都支持

**当前状态**: 混合，不清晰

### Q2: OS Interface Skill 的定位
- 是供外部调用的 API 层？
- 还是供内部使用的封装？
- 与 SessionHostSkills 的关系是什么？

### Q3: Thread Profile 的具体含义
- Prime Profile: 用于什么场景？什么权限？
- Session Profile: 用于什么场景？什么权限？
- Task Profile: 用于什么场景？什么权限？

只是 token 预算不同，还是有更深层的区别？

### Q4: 完整交付的定义
您提到：
> "完整交付的定义是能够通过OS Interface Skill提供的所有功能，所有后端不同等级/配置的Thread都能正常运行"

这是否意味着：
1. OS Interface Skill 的所有 tools 必须可调用？
2. Thread 必须支持 Prime/Session/Task 三种模式？
3. 需要端到端的集成测试验证？

### Q5: 控制面与数据面的运行时关系
- 是否可以在运行时动态启用/禁用控制面？
- 还是编译时决定？
- Worker 节点（纯 Data Plane）如何与 Host 节点（带 Control Plane）通信？

---

## 4. 建议下一步

基于以上分析，建议：

1. **明确控制面架构**: 
   - OS Interface Skill 是否应该注册到 SkillRegistry？
   - 还是应该直接暴露 gRPC 方法？

2. **统一接口设计**:
   - 明确 SessionHostSkills 和 OSInterfaceSkill 的分工
   - 删除或合并重复功能

3. **完善 Thread Profile**:
   - 除了 token 预算，是否还有其他差异？
   - 是否需要不同的权限/配置？

4. **暴露控制面功能**:
   - 在 gRPC 服务层添加 CreateProcess/CreateThread 方法
   - 或者确保 Skills 可以被执行

5. **修复 API 不一致**:
   - 添加必要的构造方法（如 ImmutableInput::new）
   - 统一参数风格

请指正我的理解偏差，我可以按正确方向重新实现。
