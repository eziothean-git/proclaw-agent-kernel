"""
端到端测试 - 验证完整流程能跑通
"""
import pytest
import sys
import os
import tempfile
import shutil

sys.path.insert(0, '/home/eziothean/ProClaw/agent-kernel/apps/python-kernel')


class TestE2EWorkflows:
    """端到端工作流测试"""
    
    @pytest.fixture
    def temp_dir(self):
        """创建临时目录"""
        temp_path = tempfile.mkdtemp()
        yield temp_path
        shutil.rmtree(temp_path)
    
    @pytest.mark.asyncio
    async def test_create_session_and_task(self, temp_dir):
        """测试：创建Session→创建Task→执行→返回结果"""
        from storage.adapter import FileStorageAdapter
        from storage.tools import StorageTools
        
        # 初始化存储
        storage = FileStorageAdapter(base_path=temp_dir)
        tools = StorageTools()
        tools.storage = storage
        
        # 步骤1: 创建Session
        session_id = 'e2e-session-001'
        result = await tools.session_save(
            session_id=session_id,
            user_id='e2e-user',
            metadata={'source': 'e2e_test', 'platform': 'test'}
        )
        assert result['success'] is True, "Session创建失败"
        
        # 步骤2: 创建Task
        task_id = 'e2e-task-001'
        result = await tools.task_save(
            task_id=task_id,
            session_id=session_id,
            goal='端到端测试任务',
            constraints=['安全约束1', '安全约束2'],
            allowed_capabilities=['read', 'write', 'execute']
        )
        assert result['success'] is True, "Task创建失败"
        
        # 步骤3: 创建上下文快照
        snapshot_id = 'e2e-snapshot-001'
        result = await tools.snapshot_save(
            snapshot_id=snapshot_id,
            session_id=session_id,
            task_id=task_id,
            working_memory={
                'current_step': '初始化',
                'variables': {'test_var': 'value'},
                'observations': ['系统正常', '准备执行']
            }
        )
        assert result['success'] is True, "快照创建失败"
        
        # 步骤4: 模拟Task执行（更新状态）
        result = await tools.task_update(
            task_id=task_id,
            updates={'status': 'running'}
        )
        assert result['success'] is True, "Task状态更新失败"
        
        # 步骤5: 完成Task
        result = await tools.task_complete(
            task_id=task_id,
            output={
                'status': 'success',
                'result': '任务执行完成',
                'execution_time': '1.5s'
            }
        )
        assert result['success'] is True, "Task完成标记失败"
        
        # 步骤6: 验证结果
        result = await tools.task_get(task_id)
        assert result['found'] is True, "Task查询失败"
        assert result['task']['status'] == 'completed', "Task状态不正确"
        assert result['task']['output']['status'] == 'success', "Task输出不正确"
        
        # 步骤7: 验证Session包含Task
        result = await tools.task_list_by_session(session_id)
        assert result['count'] == 1, "Session Task数量不正确"
        
        print("✓ 创建Session和Task端到端测试通过")
    
    @pytest.mark.asyncio
    async def test_multi_turn_chat(self, temp_dir):
        """测试：多轮对话上下文保持"""
        from storage.adapter import FileStorageAdapter
        from storage.tools import StorageTools
        
        storage = FileStorageAdapter(base_path=temp_dir)
        tools = StorageTools()
        tools.storage = storage
        
        # 创建Session
        session_id = 'multi-turn-session'
        await tools.session_save(
            session_id=session_id,
            user_id='multi-user',
            metadata={'conversation': True}
        )
        
        # 模拟3轮对话
        conversation = [
            {'user': '你好', 'assistant': '你好！有什么可以帮你的？'},
            {'user': '帮我创建一个任务', 'assistant': '好的，已创建任务'},
            {'user': '查看所有任务', 'assistant': '当前有1个任务'},
        ]
        
        for i, turn in enumerate(conversation):
            # 保存每轮对话的快照
            snapshot_id = f'chat-snapshot-{i}'
            await tools.snapshot_save(
                snapshot_id=snapshot_id,
                session_id=session_id,
                working_memory={
                    'turn': i + 1,
                    'user_message': turn['user'],
                    'assistant_response': turn['assistant'],
                    'conversation_history': conversation[:i+1]
                }
            )
        
        # 验证所有快照都被保存
        result = await tools.snapshot_list_by_session(session_id)
        assert result['count'] == 3, "对话轮数不正确"
        
        # 验证最新快照包含完整对话历史
        result = await tools.snapshot_get_latest(session_id)
        assert result['found'] is True, "最新快照获取失败"
        assert len(result['snapshot']['working_memory']['conversation_history']) == 3, "对话历史不完整"
        
        print("✓ 多轮对话上下文保持测试通过")


class TestStorageSwitchE2E:
    """端到端存储切换测试"""
    
    @pytest.fixture
    def temp_dir(self):
        """创建临时目录"""
        temp_path = tempfile.mkdtemp()
        yield temp_path
        shutil.rmtree(temp_path)
    
    @pytest.mark.asyncio
    async def test_workflow_with_file_storage(self, temp_dir):
        """测试：使用文件存储的完整工作流"""
        from storage.adapter import FileStorageAdapter
        from storage.tools import StorageTools
        
        storage = FileStorageAdapter(base_path=temp_dir)
        tools = StorageTools()
        tools.storage = storage
        
        # 执行完整工作流
        session_id = 'file-storage-session'
        await tools.session_save(session_id=session_id, user_id='test-user')
        
        for i in range(5):
            await tools.task_save(
                task_id=f'task-{i}',
                session_id=session_id,
                goal=f'任务{i}'
            )
        
        result = await tools.task_list_by_session(session_id)
        assert result['count'] == 5
        
        print("✓ 文件存储完整工作流测试通过")
    
    @pytest.mark.asyncio
    async def test_workflow_with_sqlite_storage(self, temp_dir):
        """测试：使用SQLite存储的完整工作流"""
        from storage.adapter import SQLiteStorageAdapter
        from storage.tools import StorageTools
        
        db_path = os.path.join(temp_dir, 'test.db')
        storage = SQLiteStorageAdapter(db_path=db_path)
        await storage.initialize()
        
        tools = StorageTools()
        tools.storage = storage
        
        # 执行相同工作流
        session_id = 'sqlite-storage-session'
        await tools.session_save(session_id=session_id, user_id='test-user')
        
        for i in range(5):
            await tools.task_save(
                task_id=f'sqlite-task-{i}',
                session_id=session_id,
                goal=f'SQLite任务{i}'
            )
        
        result = await tools.task_list_by_session(session_id)
        assert result['count'] == 5
        
        print("✓ SQLite存储完整工作流测试通过")


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
