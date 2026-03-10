# ProClaw 架构问题与改进计划

## 当前严重问题

### 1. SKILL 系统 - 完全重写级别的问题
**状态**: 🔴 严重阻塞
**问题描述**:
- 所有 Skill 实现混乱不堪，参数定义不一致
- `list_directory` 时而用 `path` 时而用 `directory`
- `shell-skill` 注册的 tool 和执行时的 tool 名称不匹配
- 完全没有统一的参数验证和错误处理

**具体例子**:
```python
# 注册时
tool_name="execute_command"
# 执行时找的是
action="execute_command"  # 但实际上注册的是别的名字

# 参数不一致
list_directory(path="...")  # 定义时
list_directory(directory="...")  # 调用时传入
```

**解决方案**:
- [ ] 完全重写 Skill 注册和调用机制
- [ ] 统一使用 Pydantic 模型进行参数验证
- [ ] 建立 Skill 契约（接口定义）
- [ ] 添加 Skill 版本管理和兼容性检查

**优先级**: P0 - 阻塞基础功能

---

### 2. 进程管理 - 能用但不优雅
**状态**: 🟡 需要改进
**问题描述**:
- 虽然有统一的 `launcher.sh`，但进程管理仍然分散
- 启动顺序依赖人工控制（Request Manager → Python Kernel → Gateway）
- 没有健康检查自动重启机制
- 日志分散在多个文件，难以追踪

**改进方案**:
- [ ] 实现进程管理器（Process Manager）
- [ ] 自动依赖管理和服务发现
- [ ] 统一日志收集和查询
- [ ] 优雅停机（Graceful Shutdown）

**参考实现**:
- 使用 supervisord 或 systemd
- 或者自己实现一个轻量级进程管理器

**优先级**: P1 - 提升稳定性

---

### 3. 系统操作（文件、Shell）- 架构级别混乱
**状态**: 🔴 需要架构重构
**问题描述**:
- 文件系统操作和 Shell 操作完全分离，没有统一的安全模型
- 每个操作都要单独定义 tool，无法复用
- 没有沙箱环境，Agent 可以随意访问任何文件
- 权限控制粒度太粗（只有低/中/高三级）

**Claude 方案参考**:
Claude Desktop 的做法：
1. **根据任务需求自动选择环境**:
   - 简单文件读写 → 受限环境（指定目录）
   - 代码执行 → 临时容器/沙箱
   - 系统管理 → 需要用户确认

2. **动态权限提升**:
   - 开始时只有只读权限
   - 需要写入时请求权限
   - 敏感操作需要用户确认

3. **统一的 bash 环境**:
   ```typescript
   // 伪代码
   class SecureEnvironment {
     - readonly: boolean
     - allowedPaths: string[]
     - networkAccess: boolean
     - timeout: number
     - userConfirmation: boolean
     
     + execute(command): Result
     + readFile(path): Content
     + writeFile(path, content): void
   }
   ```

**建议架构**:
```python
class SecureBashEnvironment:
    """
    统一的受控 bash 环境
    根据 task_level 自动设置安全边界
    """
    def __init__(self, task_level: str, workspace: str):
        self.readonly = task_level == "read"
        self.workspace = workspace  # 只能访问此目录
        self.allow_network = task_level in ["medium", "high"]
        self.timeout = 30 if task_level == "low" else 300
        self.require_confirmation = task_level == "high"
    
    async def execute(self, command: str) -> Result:
        # 1. 命令白名单检查
        # 2. 路径安全检查（确保在 workspace 内）
        # 3. 执行命令
        # 4. 返回结果
```

**实施步骤**:
- [ ] 设计 SecureEnvironment 接口
- [ ] 实现基于 Docker 的沙箱（可选）
- [ ] 实现基于 chroot + 权限控制的轻量级方案
- [ ] 重构所有系统操作 Skill 使用新架构
- [ ] 移除分散的 fs-skill、shell-skill，统一为 system-environment-skill

**优先级**: P1 - 安全性和可用性

---

### 4. 当前快速修复的问题

#### 4.1 SKILL 参数不匹配（临时修复）
**文件**: `skills/local/fs-skill/src/index.ts`
**问题**: `list_directory` 参数不一致
**临时修复**: 统一改为 `path` 参数

#### 4.2 Tool 名称不匹配
**文件**: `skills/local/shell-skill/src/index.ts`
**问题**: 注册的 tool 和调用时的名称不一致
**临时修复**: 检查并统一 tool 名称

---

## 重构计划

### 阶段 1: 修复基础 SKILL（本周）
- [ ] 修复参数不匹配问题
- [ ] 统一 tool 名称
- [ ] 添加基本参数验证

### 阶段 2: 实现 SecureEnvironment（下周）
- [ ] 设计接口
- [ ] 实现路径隔离
- [ ] 实现命令白名单
- [ ] 实现权限分级

### 阶段 3: 迁移现有 Skill（下下周）
- [ ] 重构 fs-skill 使用 SecureEnvironment
- [ ] 重构 shell-skill 使用 SecureEnvironment
- [ ] 移除重复的代码
- [ ] 统一错误处理

### 阶段 4: 优化进程管理（后续）
- [ ] 实现进程管理器
- [ ] 统一日志
- [ ] 自动重启

---

## 参考资源

### Claude Desktop 实现
- MCP (Model Context Protocol) 安全模型
- 动态权限请求机制
- 沙箱环境隔离

### 其他参考
- Docker-in-Docker (DinD) 方案
- Firecracker microVM 方案
- gVisor 安全容器方案
- 传统 chroot + seccomp 方案

---

## 备注

这些问题不是阻塞性的，但严重限制了系统的可用性和安全性。

当前临时解决方案：
1. 简单对话走快速路径（已实现）
2. 复杂任务虽然能跑但是依赖关系混乱
3. 生产环境使用前必须解决安全问题

**不要在这个屎山上继续堆功能了！先重构基础架构。**
