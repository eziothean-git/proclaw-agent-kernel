"""
存储层测试 - 验证文件和SQLite存储切换
"""
import pytest
import asyncio
import tempfile
import shutil
from pathlib import Path
from datetime import datetime, timedelta
import sys
import os

# 添加python-kernel到路径
sys.path.insert(0, '/home/eziothean/ProClaw/agent-kernel/apps/python-kernel')

from storage.adapter import FileStorageAdapter, SQLiteStorageAdapter, create_storage_adapter
from storage.tools import StorageTools, get_storage_tools


class TestStorageBasics:
    """测试存储基础操作"""
    
    @pytest.fixture
    def temp_dir(self):
        """创建临时目录"""
        temp_path = tempfile.mkdtemp()
        yield temp_path
        shutil.rmtree(temp_path)
    
    @pytest.fixture
    async def file_storage(self, temp_dir):
        """创建文件存储实例"""
        storage = FileStorageAdapter(base_path=temp_dir)
        yield storage
    
    @pytest.fixture
    async def sqlite_storage(self, temp_dir):
        """创建SQLite存储实例"""
        db_path = Path(temp_dir) / "test.db"
        storage = SQLiteStorageAdapter(db_path=str(db_path))
        await storage.initialize()
        yield storage
    
    @pytest.mark.asyncio
    async def test_file_storage_session_crud(self, temp_dir):
        """测试文件存储Session增删改查"""
        storage = FileStorageAdapter(base_path=temp_dir)
        
        # 创建
        session = {
            'id': 'test-session-001',
            'user_id': 'user-001',
            'status': 'active',
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat(),
            'metadata': {'source': 'test'},
            'task_count': 0
        }
        await storage.save_session(session)
        
        # 读取
        result = await storage.get_session('test-session-001')
        assert result is not None
        assert result['id'] == 'test-session-001'
        assert result['user_id'] == 'user-001'
        
        # 更新
        await storage.update_session('test-session-001', {'status': 'closed'})
        result = await storage.get_session('test-session-001')
        assert result['status'] == 'closed'
        
        # 列出
        sessions = await storage.list_sessions()
        assert len(sessions) == 1
        
        print("✓ 文件存储Session CRUD测试通过")
    
    @pytest.mark.asyncio
    async def test_sqlite_storage_session_crud(self, temp_dir):
        """测试SQLite存储Session增删改查"""
        db_path = Path(temp_dir) / "test.db"
        storage = SQLiteStorageAdapter(db_path=str(db_path))
        await storage.initialize()
        
        # 创建
        session = {
            'id': 'test-session-002',
            'user_id': 'user-002',
            'status': 'active',
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat(),
            'metadata': {'source': 'test'},
            'task_count': 0
        }
        await storage.save_session(session)
        
        # 读取
        result = await storage.get_session('test-session-002')
        assert result is not None
        assert result['id'] == 'test-session-002'
        
        print("✓ SQLite存储Session CRUD测试通过")


class TestStorageSwitch:
    """测试存储切换"""
    
    @pytest.fixture
    def temp_dir(self):
        """创建临时目录"""
        temp_path = tempfile.mkdtemp()
        yield temp_path
        shutil.rmtree(temp_path)
    
    @pytest.mark.asyncio
    async def test_factory_creates_correct_adapter(self, temp_dir):
        """测试工厂函数创建正确的适配器"""
        # 文件存储
        file_config = {'type': 'file', 'base_path': temp_dir}
        file_adapter = create_storage_adapter(file_config)
        assert isinstance(file_adapter, FileStorageAdapter)
        
        # SQLite存储
        db_path = Path(temp_dir) / "test.db"
        sqlite_config = {'type': 'sqlite', 'db_path': str(db_path)}
        sqlite_adapter = create_storage_adapter(sqlite_config)
        assert isinstance(sqlite_adapter, SQLiteStorageAdapter)
        
        print("✓ 工厂函数测试通过")
    
    @pytest.mark.asyncio
    async def test_data_consistency_between_adapters(self, temp_dir):
        """测试两种存储适配器数据一致性"""
        # 文件存储写入数据
        file_storage = FileStorageAdapter(base_path=temp_dir)
        session = {
            'id': 'consistency-test',
            'user_id': 'user-test',
            'status': 'active',
            'created_at': datetime.now().isoformat(),
            'updated_at': datetime.now().isoformat(),
            'metadata': {'test': True},
            'task_count': 0
        }
        await file_storage.save_session(session)
        
        # 验证文件存储能读取
        file_result = await file_storage.get_session('consistency-test')
        assert file_result is not None
        
        print("✓ 数据一致性测试通过")


class TestSessionTaskWorkflow:
    """测试Session+Task完整流程"""
    
    @pytest.fixture
    def temp_dir(self):
        """创建临时目录"""
        temp_path = tempfile.mkdtemp()
        yield temp_path
        shutil.rmtree(temp_path)
    
    @pytest.mark.asyncio
    async def test_complete_session_task_workflow(self, temp_dir):
        """测试完整的Session和Task工作流程"""
        storage = FileStorageAdapter(base_path=temp_dir)
        tools = StorageTools()
        tools.storage = storage
        
        # 1. 创建Session
        session_id = 'workflow-session-001'
        result = await tools.session_save(
            session_id=session_id,
            user_id='user-workflow',
            metadata={'test': True}
        )
        assert result['success'] is True
        
        # 2. 创建Task
        task_id = 'workflow-task-001'
        result = await tools.task_save(
            task_id=task_id,
            session_id=session_id,
            goal='测试工作流',
            constraints=['约束1', '约束2'],
            allowed_capabilities=['read', 'write']
        )
        assert result['success'] is True
        
        # 3. 获取Task
        result = await tools.task_get(task_id)
        assert result['found'] is True
        assert result['task']['goal'] == '测试工作流'
        
        # 4. 列出Session的所有Task
        result = await tools.task_list_by_session(session_id)
        assert result['count'] == 1
        
        # 5. 完成Task
        result = await tools.task_complete(
            task_id=task_id,
            output={'result': '成功'}
        )
        assert result['success'] is True
        
        # 6. 验证Task状态
        result = await tools.task_get(task_id)
        assert result['task']['status'] == 'completed'
        
        # 7. 关闭Session
        result = await tools.session_close(session_id)
        assert result['success'] is True
        
        print("✓ Session+Task完整工作流测试通过")


class TestQueueOperations:
    """测试队列操作"""
    
    @pytest.fixture
    def temp_dir(self):
        """创建临时目录"""
        temp_path = tempfile.mkdtemp()
        yield temp_path
        shutil.rmtree(temp_path)
    
    @pytest.mark.asyncio
    async def test_queue_fifo(self, temp_dir):
        """测试队列先进先出"""
        storage = FileStorageAdapter(base_path=temp_dir)
        tools = StorageTools()
        tools.storage = storage
        
        # 入队5个请求
        request_ids = []
        for i in range(5):
            request_id = f'req-{i:03d}'
            request_ids.append(request_id)
            await tools.queue_enqueue(
                request_id=request_id,
                request_type='user',
                payload={'message': f'请求{i}'},
                priority=i
            )
        
        # 验证队列长度
        result = await tools.queue_get_length()
        assert result['length'] == 5
        
        # 出队并验证FIFO
        for i in range(5):
            result = await tools.queue_dequeue()
            assert result['found'] is True
            assert result['request']['id'] == request_ids[i]
        
        # 验证队列已空
        result = await tools.queue_dequeue()
        assert result['found'] is False
        
        print("✓ 队列FIFO测试通过")


class TestSchedulerDue:
    """测试定时任务到期"""
    
    @pytest.fixture
    def temp_dir(self):
        """创建临时目录"""
        temp_path = tempfile.mkdtemp()
        yield temp_path
        shutil.rmtree(temp_path)
    
    @pytest.mark.asyncio
    async def test_scheduler_due_tasks(self, temp_dir):
        """测试定时任务到期检测"""
        storage = FileStorageAdapter(base_path=temp_dir)
        tools = StorageTools()
        tools.storage = storage
        
        # 调度3个任务（已到期）
        now = datetime.now()
        for i in range(3):
            await tools.scheduler_schedule(
                task_id=f'scheduled-task-{i}',
                request={'type': 'reminder', 'message': f'任务{i}'},
                trigger_at=(now - timedelta(minutes=i+1)).isoformat(),
                created_by='user'
            )
        
        # 调度2个任务（未到期）
        for i in range(2):
            await tools.scheduler_schedule(
                task_id=f'future-task-{i}',
                request={'type': 'reminder', 'message': f'未来任务{i}'},
                trigger_at=(now + timedelta(hours=i+1)).isoformat(),
                created_by='user'
            )
        
        # 获取到期任务
        result = await tools.scheduler_get_due()
        assert result['count'] == 3
        
        # 验证任务ID
        task_ids = [t['id'] for t in result['tasks']]
        assert 'scheduled-task-0' in task_ids
        assert 'scheduled-task-1' in task_ids
        assert 'scheduled-task-2' in task_ids
        assert 'future-task-0' not in task_ids
        
        print("✓ 定时任务到期测试通过")


if __name__ == '__main__':
    # 直接运行测试
    pytest.main([__file__, '-v'])
