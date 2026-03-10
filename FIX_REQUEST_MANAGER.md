# Request Manager 时间戳错误修复指南

## 🐛 问题描述

**错误**: `Invalid time value`  
**位置**: `apps/request-manager/src/services/priority-request-manager.service.ts`  
**影响**: 所有请求在 Request Manager 中处理失败

## 🔍 错误分析

从日志看到：
1. 请求成功入队：`Request queued at position 0`
2. 处理时失败：`Invalid time value`

可能的原因：
1. `new Date()` 接收到无效的时间字符串
2. 时间戳格式不兼容
3. 时区转换问题

## 🛠️ 修复步骤

### 步骤 1: 查看问题代码

```bash
cd /home/eziothean/ProClaw/agent-kernel/apps/request-manager
cat src/services/priority-request-manager.service.ts | head -150
```

重点关注：
- 第 96 行: `const startTime = Date.now();`
- 第 120 行: `completedAt: new Date()`
- 第 127 行: `task.startedAt?.getTime()`

### 步骤 2: 添加调试日志

在 `priority-request-manager.service.ts` 中添加日志：

```typescript
// 在第 95 行后添加
console.log('DEBUG: Task createdAt:', task.createdAt);
console.log('DEBUG: Task timeoutAt:', task.timeoutAt);
console.log('DEBUG: Task startedAt:', task.startedAt);
```

### 步骤 3: 修复时间处理

可能的修复方案 1 - 添加验证：
```typescript
// 替换第 120 行
completedAt: task.completedAt ? new Date(task.completedAt) : new Date(),
```

可能的修复方案 2 - 统一时间格式：
```typescript
// 在构造函数中添加转换
if (typeof task.createdAt === 'string') {
    task.createdAt = new Date(task.createdAt);
}
```

### 步骤 4: 重新构建和测试

```bash
cd apps/request-manager
npm run build

# 停止旧服务
pkill -f "request-manager"

# 启动新服务
npm start

# 测试
curl -X POST "http://localhost:3000/api/v1/chat" \
  -H "Content-Type: application/json" \
  -d '{"message": "测试", "user_id": "test"}'
```

## 📋 检查清单

- [ ] 查看原始错误位置
- [ ] 添加调试日志
- [ ] 实现修复
- [ ] 重新构建
- [ ] 测试修复
- [ ] 验证端到端流程

## 💡 提示

1. 使用 `console.log` 输出时间值查看格式
2. 检查是否有 `undefined` 或 `null` 值
3. 确保所有日期都是有效的 Date 对象
4. 考虑添加 try-catch 块捕获日期解析错误

## 📚 参考

- 完整问题文档: `/home/eziothean/ProClaw/PROBLEMS.md`
- 日志位置: `/tmp/request-manager.log`
- 请求数据: `/home/eziothean/ProClaw/agent-kernel/data/gateway/request-manager/inbox/`
