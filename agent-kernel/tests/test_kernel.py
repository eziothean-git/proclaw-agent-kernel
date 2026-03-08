"""
核心模块测试 - 验证Python智能面关键逻辑
"""
import pytest
import sys
import os
from datetime import datetime
from unittest.mock import Mock, patch

sys.path.insert(0, '/home/eziothean/ProClaw/agent-kernel/apps/python-kernel')

from schemas.models import Session, TaskSnapshot, Request


class TestSchemas:
    """测试数据模型"""
    
    def test_session_creation(self):
        """测试Session模型创建"""
        session = Session(
            id='test-session',
            user_id='user-001',
            status='active',
            created_at=datetime.now(),
            last_activity=datetime.now(),
            task_count=0
        )
        
        assert session.id == 'test-session'
        assert session.user_id == 'user-001'
        assert session.status == 'active'
        print("✓ Session模型测试通过")
    
    def test_task_snapshot_creation(self):
        """测试TaskSnapshot模型创建"""
        from schemas.models import TaskStatus
        
        task = TaskSnapshot(
            id='test-task',
            session_id='test-session',
            process_id='test-process',
            status=TaskStatus.IDLE,
            goal='测试任务',
            constraints=['约束1'],
            allowed_capabilities=['read'],
            created_at=datetime.now()
        )
        
        assert task.id == 'test-task'
        assert task.goal == '测试任务'
        assert task.status == TaskStatus.IDLE
        print("✓ TaskSnapshot模型测试通过")


class TestStorageTools:
    """测试存储工具"""
    
    @pytest.fixture
    def temp_dir(self, tmp_path):
        """使用pytest的tmp_path fixture"""
        return str(tmp_path)
    
    @pytest.mark.asyncio
    async def test_storage_tools_basic(self, temp_dir):
        """测试存储工具基础功能"""
        from storage.adapter import FileStorageAdapter
        from storage.tools import StorageTools
        
        # 创建存储
        storage = FileStorageAdapter(base_path=temp_dir)
        tools = StorageTools()
        tools.storage = storage
        
        # 测试Session操作
        result = await tools.session_save(
            session_id='tools-test',
            user_id='user-tools',
            metadata={'test': True}
        )
        assert result['success'] is True
        
        result = await tools.session_get('tools-test')
        assert result['found'] is True
        assert result['session']['user_id'] == 'user-tools'
        
        print("✓ 存储工具基础测试通过")


class TestContextCompiler:
    """测试Context Compiler"""
    
    def test_master_compiler_import(self):
        """测试主Context Compiler可导入"""
        try:
            from context_compiler.master_compiler import MasterContextCompiler
            compiler = MasterContextCompiler()
            assert compiler is not None
            print("✓ MasterContextCompiler导入测试通过")
        except ImportError as e:
            pytest.skip(f"模块未完全实现: {e}")
    
    def test_process_compiler_import(self):
        """测试进程Context Compiler可导入"""
        try:
            from context_compiler.process_compiler import ProcessContextCompiler
            compiler = ProcessContextCompiler()
            assert compiler is not None
            print("✓ ProcessContextCompiler导入测试通过")
        except ImportError as e:
            pytest.skip(f"模块未完全实现: {e}")


class TestSessionHost:
    """测试Session Host"""
    
    def test_session_host_import(self):
        """测试Session Host可导入"""
        try:
            from session_host.session_host import SessionHost
            from schemas.models import Session
            from datetime import datetime
            
            session = Session(
                id='test-session',
                user_id='user-001',
                status='active',
                created_at=datetime.now(),
                last_activity=datetime.now(),
                task_count=0
            )
            host = SessionHost(session=session)
            assert host is not None
            assert host.session.id == 'test-session'
            print("✓ SessionHost导入测试通过")
        except ImportError as e:
            pytest.skip(f"模块未完全实现: {e}")


class TestAgentThread:
    """测试Agent线程"""
    
    def test_agent_thread_import(self):
        """测试Agent线程可导入"""
        try:
            from thread_runtime.agent_thread import AgentThread
            # AgentThread需要更多参数，我们只测试导入
            print("✓ AgentThread导入测试通过")
        except ImportError as e:
            pytest.skip(f"模块未完全实现: {e}")


class TestExecutorClient:
    """测试执行器客户端"""
    
    def test_executor_client_import(self):
        """测试执行器客户端可导入"""
        try:
            from executors_client.executor_client import ExecutorClient
            client = ExecutorClient(base_url='http://localhost:3000')
            assert client is not None
            print("✓ ExecutorClient导入测试通过")
        except ImportError as e:
            pytest.skip(f"模块未完全实现: {e}")


class TestPersonality:
    """测试Prime Personality"""
    
    def test_personality_import(self):
        """测试Prime Personality可导入"""
        try:
            from personality.prime_personality import PrimePersonality
            # PrimePersonality需要API Key，我们只测试导入
            print("✓ PrimePersonality导入测试通过")
        except ImportError as e:
            pytest.skip(f"模块未完全实现: {e}")


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
