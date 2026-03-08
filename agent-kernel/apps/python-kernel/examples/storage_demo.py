"""
示例Agent - 展示如何使用存储工具
"""
import asyncio
import uuid
from datetime import datetime
from pydantic_ai import Agent
from storage.tools import get_storage_tools, STORAGE_TOOLS_REGISTRY


# 创建示例Agent
example_agent = Agent(
    'openai:gpt-4o',
    system_prompt="""你是一个示例Agent，演示如何使用存储工具。

你可以使用以下工具来管理状态：

## Session管理
- session_save: 创建新Session
- session_get: 获取Session信息
- session_list: 列出所有Session
- session_update: 更新Session
- session_close: 关闭Session

## Task管理
- task_save: 创建Task
- task_get: 获取Task信息
- task_list_by_session: 列出Session的Tasks
- task_update: 更新Task
- task_complete: 标记Task完成
- task_fail: 标记Task失败

## 上下文快照
- snapshot_save: 保存上下文快照
- snapshot_get: 获取快照
- snapshot_get_latest: 获取最新快照
- snapshot_list_by_session: 列出快照历史

## 队列操作
- queue_enqueue: 将请求加入队列
- queue_dequeue: 从队列取出请求
- queue_peek: 查看队列头部
- queue_get_length: 获取队列长度

## 定时任务
- scheduler_schedule: 调度未来任务
- scheduler_get_due: 获取到期任务
- scheduler_complete: 标记任务完成
- scheduler_cancel: 取消任务

所有存储操作对你是透明的，无需关心底层是文件还是数据库。
""",
    tools=list(STORAGE_TOOLS_REGISTRY.values())
)


async def demo_session_workflow():
    """演示Session完整工作流"""
    tools = get_storage_tools()
    
    print("=== 演示：Session工作流 ===\n")
    
    # 1. 创建Session
    session_id = str(uuid.uuid4())
    result = await tools.session_save(
        session_id=session_id,
        user_id="user_001",
        metadata={"source": "demo", "platform": "cli"}
    )
    print(f"✓ 创建Session: {result}")
    
    # 2. 获取Session
    result = await tools.session_get(session_id)
    print(f"✓ 获取Session: {result}\n")
    
    # 3. 创建Task
    task_id = str(uuid.uuid4())
    result = await tools.task_save(
        task_id=task_id,
        session_id=session_id,
        goal="演示Task操作",
        constraints=["不要修改系统文件", "只读取数据"],
        allowed_capabilities=["read", "write"]
    )
    print(f"✓ 创建Task: {result}")
    
    # 4. 获取Task
    result = await tools.task_get(task_id)
    print(f"✓ 获取Task: {result}\n")
    
    # 5. 创建上下文快照
    snapshot_id = str(uuid.uuid4())
    result = await tools.snapshot_save(
        snapshot_id=snapshot_id,
        session_id=session_id,
        task_id=task_id,
        working_memory={
            "current_step": "初始化",
            "variables": {"x": 10, "y": 20},
            "observations": ["系统正常", "准备执行"]
        }
    )
    print(f"✓ 创建Snapshot: {result}")
    
    # 6. 获取最新快照
    result = await tools.snapshot_get_latest(session_id)
    print(f"✓ 获取最新Snapshot: {result}\n")
    
    # 7. 完成Task
    result = await tools.task_complete(
        task_id=task_id,
        output={"result": "success", "data": "演示完成"}
    )
    print(f"✓ 完成Task: {result}")
    
    # 8. 列出所有Task
    result = await tools.task_list_by_session(session_id)
    print(f"✓ 列出Tasks: {result}\n")
    
    # 9. 关闭Session
    result = await tools.session_close(session_id)
    print(f"✓ 关闭Session: {result}")
    
    print("\n=== Session工作流演示完成 ===")


async def demo_queue_workflow():
    """演示队列工作流"""
    tools = get_storage_tools()
    
    print("\n=== 演示：队列工作流 ===\n")
    
    # 1. 入队多个请求
    for i in range(3):
        request_id = str(uuid.uuid4())
        result = await tools.queue_enqueue(
            request_id=request_id,
            request_type="user",
            payload={"message": f"请求 {i+1}", "priority": i},
            priority=i
        )
        print(f"✓ 入队请求 {i+1}: {result}")
    
    # 2. 查看队列长度
    result = await tools.queue_get_length()
    print(f"✓ 队列长度: {result}\n")
    
    # 3. 查看队列头部
    result = await tools.queue_peek()
    print(f"✓ 队列头部: {result}\n")
    
    # 4. 出队处理
    while True:
        result = await tools.queue_dequeue()
        if not result.get('found'):
            break
        print(f"✓ 出队请求: {result}")
    
    print("\n=== 队列工作流演示完成 ===")


async def demo_scheduler_workflow():
    """演示定时任务工作流"""
    tools = get_storage_tools()
    
    print("\n=== 演示：定时任务工作流 ===\n")
    
    # 1. 调度未来任务
    task_id = str(uuid.uuid4())
    future_time = datetime.now().isoformat()
    result = await tools.scheduler_schedule(
        task_id=task_id,
        request={"type": "reminder", "message": "别忘了开会"},
        trigger_at=future_time,
        created_by="user"
    )
    print(f"✓ 调度任务: {result}")
    
    # 2. 获取到期任务
    result = await tools.scheduler_get_due()
    print(f"✓ 到期任务: {result}\n")
    
    # 3. 标记任务完成
    if result.get('count', 0) > 0:
        for task in result['tasks']:
            result = await tools.scheduler_complete(task['id'])
            print(f"✓ 完成任务 {task['id']}: {result}")
    
    print("\n=== 定时任务工作流演示完成 ===")


async def demo_with_agent():
    """使用Agent进行存储操作"""
    print("\n=== 演示：Agent使用存储工具 ===\n")
    
    # 让Agent决定如何操作存储
    result = await example_agent.run(
        "请帮我：1) 创建一个新Session，2) 在这个Session中创建一个Task，"
        "3) 保存一个上下文快照，4) 标记Task完成。请展示每一步的结果。"
    )
    
    print(f"Agent响应:\n{result.data}")
    print("\n=== Agent演示完成 ===")


async def main():
    """主函数"""
    print("🚀 Agent Kernel 存储工具演示\n")
    print("=" * 50)
    
    # 设置环境变量（如果需要）
    import os
    os.environ.setdefault('STORAGE_TYPE', 'file')
    os.environ.setdefault('DATA_PATH', './data')
    
    try:
        # 演示基础工作流
        await demo_session_workflow()
        await demo_queue_workflow()
        await demo_scheduler_workflow()
        
        # 演示Agent使用
        await demo_with_agent()
        
        print("\n" + "=" * 50)
        print("✅ 所有演示完成！")
        print(f"\n数据存储位置: {os.environ.get('DATA_PATH', './data')}")
        print("查看 data/ 目录了解文件存储结构")
        
    except Exception as e:
        print(f"\n❌ 演示失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
