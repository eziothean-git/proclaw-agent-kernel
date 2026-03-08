"""
Storage Tools - Agent可调用的存储工具
所有存储操作通过工具函数暴露，底层实现透明
"""
from typing import Any, Dict, List, Optional
from datetime import datetime
from storage.adapter import get_storage


class StorageTools:
    """存储工具集合 - Agent通过tool调用"""
    
    def __init__(self):
        self.storage = get_storage()
    
    # ========== Session 工具 ==========
    
    async def session_save(self, session_id: str, user_id: str, metadata: dict = None) -> dict:
        """
        保存Session
        
        Args:
            session_id: Session唯一标识
            user_id: 用户ID
            metadata: 元数据字典
            
        Returns:
            {"success": True, "session_id": session_id}
        """
        session = {
            'id': session_id,
            'user_id': user_id,
            'status': 'active',
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat(),
            'metadata': metadata or {},
            'task_count': 0
        }
        await self.storage.save_session(session)
        return {"success": True, "session_id": session_id}
    
    async def session_get(self, session_id: str) -> dict:
        """
        获取Session信息
        
        Args:
            session_id: Session ID
            
        Returns:
            {"found": True, "session": {...}} 或 {"found": False}
        """
        session = await self.storage.get_session(session_id)
        if session:
            return {"found": True, "session": session}
        return {"found": False, "session": None}
    
    async def session_list(self, status: str = None) -> dict:
        """
        列出所有Session
        
        Args:
            status: 可选，按状态过滤
            
        Returns:
            {"sessions": [...], "count": n}
        """
        sessions = await self.storage.list_sessions()
        if status:
            sessions = [s for s in sessions if s.get('status') == status]
        return {"sessions": sessions, "count": len(sessions)}
    
    async def session_update(self, session_id: str, updates: dict) -> dict:
        """
        更新Session字段
        
        Args:
            session_id: Session ID
            updates: 要更新的字段字典
            
        Returns:
            {"success": True} 或 {"success": False, "error": "Session not found"}
        """
        session = await self.storage.get_session(session_id)
        if not session:
            return {"success": False, "error": "Session not found"}
        
        updates['updated_at'] = datetime.now().isoformat()
        await self.storage.update_session(session_id, updates)
        return {"success": True}
    
    async def session_close(self, session_id: str) -> dict:
        """
        关闭Session
        
        Args:
            session_id: Session ID
            
        Returns:
            {"success": True} 或 {"success": False, "error": "..."}
        """
        return await self.session_update(session_id, {'status': 'closed'})
    
    # ========== Task 工具 ==========
    
    async def task_save(self, task_id: str, session_id: str, goal: str, 
                       constraints: List[str] = None, 
                       allowed_capabilities: List[str] = None) -> dict:
        """
        创建新Task
        
        Args:
            task_id: Task唯一标识
            session_id: 所属Session ID
            goal: Task目标描述
            constraints: 约束条件列表
            allowed_capabilities: 允许的能力列表
            
        Returns:
            {"success": True, "task_id": task_id}
        """
        task = {
            'id': task_id,
            'session_id': session_id,
            'goal': goal,
            'status': 'pending',
            'constraints': constraints or [],
            'allowed_capabilities': allowed_capabilities or [],
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat()
        }
        await self.storage.save_task(task)
        
        # 更新Session的task_count
        await self._increment_task_count(session_id)
        
        return {"success": True, "task_id": task_id}
    
    async def task_get(self, task_id: str) -> dict:
        """
        获取Task信息
        
        Args:
            task_id: Task ID
            
        Returns:
            {"found": True, "task": {...}} 或 {"found": False}
        """
        task = await self.storage.get_task(task_id)
        if task:
            return {"found": True, "task": task}
        return {"found": False, "task": None}
    
    async def task_list_by_session(self, session_id: str, status: str = None) -> dict:
        """
        列出Session的所有Task
        
        Args:
            session_id: Session ID
            status: 可选，按状态过滤
            
        Returns:
            {"tasks": [...], "count": n}
        """
        tasks = await self.storage.list_tasks_by_session(session_id)
        if status:
            tasks = [t for t in tasks if t.get('status') == status]
        return {"tasks": tasks, "count": len(tasks)}
    
    async def task_update(self, task_id: str, updates: dict) -> dict:
        """
        更新Task字段
        
        Args:
            task_id: Task ID
            updates: 要更新的字段字典
            
        Returns:
            {"success": True} 或 {"success": False, "error": "..."}
        """
        task = await self.storage.get_task(task_id)
        if not task:
            return {"success": False, "error": "Task not found"}
        
        updates['updated_at'] = datetime.now().isoformat()
        await self.storage.update_task(task_id, updates)
        return {"success": True}
    
    async def task_complete(self, task_id: str, output: Any = None) -> dict:
        """
        标记Task完成
        
        Args:
            task_id: Task ID
            output: Task输出结果
            
        Returns:
            {"success": True} 或 {"success": False, "error": "..."}
        """
        updates = {
            'status': 'completed',
            'output': output,
            'completed_at': datetime.now().isoformat()
        }
        return await self.task_update(task_id, updates)
    
    async def task_fail(self, task_id: str, error: str) -> dict:
        """
        标记Task失败
        
        Args:
            task_id: Task ID
            error: 错误信息
            
        Returns:
            {"success": True} 或 {"success": False, "error": "..."}
        """
        updates = {
            'status': 'failed',
            'error': error,
            'completed_at': datetime.now().isoformat()
        }
        return await self.task_update(task_id, updates)
    
    # ========== Snapshot 工具 ==========
    
    async def snapshot_save(self, snapshot_id: str, session_id: str, 
                           working_memory: dict, task_id: str = None) -> dict:
        """
        保存上下文快照
        
        Args:
            snapshot_id: 快照ID
            session_id: Session ID
            working_memory: 工作记忆内容
            task_id: 关联的Task ID（可选）
            
        Returns:
            {"success": True, "snapshot_id": snapshot_id}
        """
        snapshot = {
            'id': snapshot_id,
            'session_id': session_id,
            'task_id': task_id,
            'working_memory': working_memory,
            'timestamp': datetime.now().isoformat()
        }
        await self.storage.save_snapshot(snapshot)
        return {"success": True, "snapshot_id": snapshot_id}
    
    async def snapshot_get(self, snapshot_id: str) -> dict:
        """
        获取快照
        
        Args:
            snapshot_id: 快照ID
            
        Returns:
            {"found": True, "snapshot": {...}} 或 {"found": False}
        """
        snapshot = await self.storage.get_snapshot(snapshot_id)
        if snapshot:
            return {"found": True, "snapshot": snapshot}
        return {"found": False, "snapshot": None}
    
    async def snapshot_get_latest(self, session_id: str) -> dict:
        """
        获取Session最新快照
        
        Args:
            session_id: Session ID
            
        Returns:
            {"found": True, "snapshot": {...}} 或 {"found": False}
        """
        snapshot = await self.storage.get_latest_snapshot(session_id)
        if snapshot:
            return {"found": True, "snapshot": snapshot}
        return {"found": False, "snapshot": None}
    
    async def snapshot_list_by_session(self, session_id: str, limit: int = 10) -> dict:
        """
        列出Session的快照历史
        
        Args:
            session_id: Session ID
            limit: 返回数量限制
            
        Returns:
            {"snapshots": [...], "count": n}
        """
        snapshots = await self.storage.list_snapshots_by_session(session_id)
        return {"snapshots": snapshots[:limit], "count": len(snapshots)}
    
    # ========== Queue 工具 ==========
    
    async def queue_enqueue(self, request_id: str, request_type: str, 
                           payload: dict, priority: int = 0) -> dict:
        """
        将请求加入队列
        
        Args:
            request_id: 请求ID
            request_type: 请求类型（user/scheduled）
            payload: 请求内容
            priority: 优先级（数字越小优先级越高）
            
        Returns:
            {"success": True, "position": n}
        """
        request = {
            'id': request_id,
            'type': request_type,
            'payload': payload,
            'priority': priority,
            'status': 'pending',
            'created_at': datetime.now().isoformat()
        }
        await self.storage.enqueue_request(request)
        position = await self.storage.get_queue_length()
        return {"success": True, "position": position}
    
    async def queue_dequeue(self) -> dict:
        """
        从队列取出请求
        
        Returns:
            {"found": True, "request": {...}} 或 {"found": False}
        """
        request = await self.storage.dequeue_request()
        if request:
            return {"found": True, "request": request}
        return {"found": False, "request": None}
    
    async def queue_peek(self) -> dict:
        """
        查看队列头部（不出队）
        
        Returns:
            {"found": True, "request": {...}} 或 {"found": False}
        """
        request = await self.storage.peek_queue()
        if request:
            return {"found": True, "request": request}
        return {"found": False, "request": None}
    
    async def queue_get_length(self) -> dict:
        """
        获取队列长度
        
        Returns:
            {"length": n}
        """
        length = await self.storage.get_queue_length()
        return {"length": length}
    
    # ========== Scheduler 工具 ==========
    
    async def scheduler_schedule(self, task_id: str, request: dict, 
                                 trigger_at: str, created_by: str = 'user') -> dict:
        """
        调度未来任务
        
        Args:
            task_id: 任务ID
            request: 请求内容
            trigger_at: 触发时间（ISO格式）
            created_by: 创建者（user/hook）
            
        Returns:
            {"success": True, "scheduled_at": trigger_at}
        """
        task = {
            'id': task_id,
            'request': request,
            'trigger_at': trigger_at,
            'created_by': created_by,
            'status': 'scheduled',
            'created_at': datetime.now().isoformat()
        }
        await self.storage.schedule_task(task)
        return {"success": True, "scheduled_at": trigger_at}
    
    async def scheduler_get_due(self, before: str = None) -> dict:
        """
        获取到期的定时任务
        
        Args:
            before: 截止时间（ISO格式），默认为当前时间
            
        Returns:
            {"tasks": [...], "count": n}
        """
        if before is None:
            before = datetime.now()
        else:
            before = datetime.fromisoformat(before)
        
        tasks = await self.storage.get_due_tasks(before)
        return {"tasks": tasks, "count": len(tasks)}
    
    async def scheduler_complete(self, task_id: str) -> dict:
        """
        标记定时任务完成
        
        Args:
            task_id: 任务ID
            
        Returns:
            {"success": True} 或 {"success": False, "error": "..."}
        """
        await self.storage.complete_scheduled_task(task_id)
        return {"success": True}
    
    async def scheduler_cancel(self, task_id: str) -> dict:
        """
        取消定时任务
        
        Args:
            task_id: 任务ID
            
        Returns:
            {"success": True} 或 {"success": False, "error": "..."}
        """
        await self.storage.cancel_scheduled_task(task_id)
        return {"success": True}
    
    # ========== 辅助方法 ==========
    
    async def _increment_task_count(self, session_id: str):
        """增加Session的task_count"""
        session = await self.storage.get_session(session_id)
        if session:
            count = session.get('task_count', 0) + 1
            await self.storage.update_session(session_id, {'task_count': count})


# 工具注册表 - 供Agent框架使用
STORAGE_TOOLS_REGISTRY = {
    # Session工具
    "session_save": StorageTools.session_save,
    "session_get": StorageTools.session_get,
    "session_list": StorageTools.session_list,
    "session_update": StorageTools.session_update,
    "session_close": StorageTools.session_close,
    
    # Task工具
    "task_save": StorageTools.task_save,
    "task_get": StorageTools.task_get,
    "task_list_by_session": StorageTools.task_list_by_session,
    "task_update": StorageTools.task_update,
    "task_complete": StorageTools.task_complete,
    "task_fail": StorageTools.task_fail,
    
    # Snapshot工具
    "snapshot_save": StorageTools.snapshot_save,
    "snapshot_get": StorageTools.snapshot_get,
    "snapshot_get_latest": StorageTools.snapshot_get_latest,
    "snapshot_list_by_session": StorageTools.snapshot_list_by_session,
    
    # Queue工具
    "queue_enqueue": StorageTools.queue_enqueue,
    "queue_dequeue": StorageTools.queue_dequeue,
    "queue_peek": StorageTools.queue_peek,
    "queue_get_length": StorageTools.queue_get_length,
    
    # Scheduler工具
    "scheduler_schedule": StorageTools.scheduler_schedule,
    "scheduler_get_due": StorageTools.scheduler_get_due,
    "scheduler_complete": StorageTools.scheduler_complete,
    "scheduler_cancel": StorageTools.scheduler_cancel,
}


def get_storage_tools() -> StorageTools:
    """获取存储工具实例"""
    return StorageTools()
