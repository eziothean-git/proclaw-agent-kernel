"""
Tests for Prime Context Compiler.

Basic validation tests to ensure the implementation works correctly.
"""
import os
import sys
import tempfile
import pytest
from datetime import datetime
from pathlib import Path

# Ensure imports work
sys.path.insert(0, '/home/eziothean/ProClaw/agent-kernel/apps/python-kernel')

from context_compiler.models import ContextPatch, PrimeCompilationSummary, PrimeCompilerConfig
from context_compiler.persistent_event_log import PersistentEventLog
from context_compiler.compilation_auditor import PrimeCompilationAuditor
from context_compiler.prime_compiler_skill import PrimeCompilerSkill
from context_compiler.master_compiler import MasterContextCompiler, get_master_compiler
from schemas.models import Request, Session, CompiledContext


class TestPrimeCompilerModels:
    """Test data models."""
    
    def test_context_patch_creation(self):
        """Test ContextPatch model."""
        patch = ContextPatch(
            status="complete",
            artifacts=[],
            files_read=["file1.txt", "file2.txt"],
            reasoning="Test reasoning",
            steps_used=3,
            confidence=0.8,
        )
        
        assert patch.status == "complete"
        assert len(patch.files_read) == 2
        assert patch.confidence == 0.8
        assert patch.steps_used == 3
    
    def test_prime_compilation_summary(self):
        """Test PrimeCompilationSummary model."""
        summary = PrimeCompilationSummary(
            request_id="req_123",
            session_id="sess_456",
            triggered_agent=True,
            steps_used=3,
            max_steps=5,
            files_read=["file.txt"],
            artifacts_gathered=2,
            duration_ms=1200,
            status="success",
        )
        
        assert summary.request_id == "req_123"
        assert summary.triggered_agent is True
        assert summary.steps_used <= summary.max_steps
    
    def test_prime_compiler_config(self):
        """Test PrimeCompilerConfig model."""
        config = PrimeCompilerConfig(
            max_steps=5,
            intent_confidence_threshold=0.5,
        )
        
        assert config.max_steps == 5
        assert config.intent_confidence_threshold == 0.5
        assert config.enable_caching is True


class TestPersistentEventLog:
    """Test PersistentEventLog."""
    
    def test_event_log_creation(self, tmp_path):
        """Test creating persistent event log."""
        storage_path = tmp_path / "test_events.jsonl"
        
        event_log = PersistentEventLog(
            log_id="test_log",
            storage_path=str(storage_path),
        )
        
        assert event_log.task_id == "test_log"
        assert storage_path.exists()
    
    def test_event_persistence(self, tmp_path):
        """Test events are persisted to file."""
        storage_path = tmp_path / "test_events.jsonl"
        
        event_log = PersistentEventLog(
            log_id="test_log",
            storage_path=str(storage_path),
        )
        
        from thread_runtime.models import EventType, Phase
        
        # Append an event
        event = event_log.append(
            event_type=EventType.TOOL_CALL,
            actor="test_actor",
            phase=Phase.EXPLORE,
            content={"test": "data"},
        )
        
        assert event.event_id is not None
        assert storage_path.exists()
        
        # Check file content
        content = storage_path.read_text()
        assert "test_actor" in content
        assert "TOOL_CALL" in content
    
    def test_event_log_reload(self, tmp_path):
        """Test reloading events from file."""
        storage_path = tmp_path / "test_events.jsonl"
        
        # Create and add events
        from thread_runtime.models import EventType, Phase
        
        event_log1 = PersistentEventLog(
            log_id="test_log",
            storage_path=str(storage_path),
        )
        
        event_log1.append(
            event_type=EventType.TOOL_CALL,
            actor="actor1",
            phase=Phase.EXPLORE,
            content={},
        )
        
        # Create new instance (simulates reload)
        event_log2 = PersistentEventLog(
            log_id="test_log",
            storage_path=str(storage_path),
        )
        
        assert len(event_log2.log.events) == 1


class TestMasterContextCompiler:
    """Test MasterContextCompiler."""
    
    def test_compiler_initialization(self):
        """Test compiler initialization."""
        config = PrimeCompilerConfig(max_steps=3)
        compiler = MasterContextCompiler(config)
        
        assert compiler.config.max_steps == 3
        assert compiler.config.enable_caching is True
    
    def test_rule_based_compile(self):
        """Test rule-based compilation."""
        compiler = MasterContextCompiler()
        
        request = Request(
            id="req_test",
            session_id="sess_test",
            user_id="user_test",
            message="List files in current directory",
        )
        
        session = Session(
            id="sess_test",
            user_id="user_test",
            task_count=0,
        )
        
        context = compiler._rule_based_compile(request, session, None)
        
        assert isinstance(context, CompiledContext)
        assert context.session_context["request"]["id"] == "req_test"
        assert "analysis" in context.session_context
    
    def test_trigger_determination(self):
        """Test trigger determination logic."""
        compiler = MasterContextCompiler()
        
        # Test low confidence trigger
        request = Request(
            id="req_test",
            session_id="sess_test",
            user_id="user_test",
            message="Do something",
        )
        
        base_context = CompiledContext(
            task_id="test",
            session_context={
                "analysis": {
                    "intent": {"confidence": 0.3},
                    "complexity_score": 0.2,
                }
            },
            task_goal="test",
            constraints=[],
            allowed_capabilities=[],
            forbidden_capabilities=[],
        )
        
        trigger = compiler._determine_trigger_reason(request, base_context)
        assert trigger is not None
        assert "low_intent_confidence" in trigger
    
    def test_cross_session_trigger(self):
        """Test cross-session keyword trigger."""
        compiler = MasterContextCompiler()
        
        request = Request(
            id="req_test",
            session_id="sess_test",
            user_id="user_test",
            message="What did I ask for last time?",
        )
        
        base_context = CompiledContext(
            task_id="test",
            session_context={
                "analysis": {
                    "intent": {"confidence": 0.9},
                    "complexity_score": 0.2,
                }
            },
            task_goal="test",
            constraints=[],
            allowed_capabilities=[],
            forbidden_capabilities=[],
        )
        
        trigger = compiler._determine_trigger_reason(request, base_context)
        assert trigger is not None
        assert "cross_session_keyword" in trigger


class TestCompilationAuditor:
    """Test PrimeCompilationAuditor."""
    
    def test_auditor_initialization(self, tmp_path):
        """Test auditor initialization."""
        auditor = PrimeCompilationAuditor(base_path=str(tmp_path))
        assert auditor.base_path == tmp_path
    
    def test_get_summary_nonexistent(self, tmp_path):
        """Test getting summary for non-existent request."""
        auditor = PrimeCompilationAuditor(base_path=str(tmp_path))
        
        summary = auditor.get_summary("nonexistent")
        assert summary is None
    
    def test_get_full_events_nonexistent(self, tmp_path):
        """Test getting events for non-existent request."""
        auditor = PrimeCompilationAuditor(base_path=str(tmp_path))
        
        events = auditor.get_full_events("nonexistent")
        assert events == []


class TestIntegration:
    """Integration tests."""
    
    def test_full_compile_flow_rule_only(self, tmp_path):
        """Test full compile flow without agent."""
        config = PrimeCompilerConfig(
            max_steps=3,
            storage_base_path=str(tmp_path / "compilation"),
        )
        compiler = MasterContextCompiler(config)
        
        request = Request(
            id="req_simple",
            session_id="sess_simple",
            user_id="user_simple",
            message="Hello",
        )
        
        session = Session(
            id="sess_simple",
            user_id="user_simple",
            task_count=0,
        )
        
        # Should not trigger agent for simple greeting
        context = compiler.compile(request, session, None)
        
        assert isinstance(context, CompiledContext)
        assert context.session_context["request"]["message"] == "Hello"
    
    def test_cache_functionality(self, tmp_path):
        """Test caching mechanism."""
        config = PrimeCompilerConfig(
            max_steps=3,
            cache_ttl_seconds=60,
            storage_base_path=str(tmp_path / "compilation"),
        )
        compiler = MasterContextCompiler(config)
        
        request = Request(
            id="req_cache",
            session_id="sess_cache",
            user_id="user_cache",
            message="Complex task with multiple steps and requirements",
        )
        
        session = Session(
            id="sess_cache",
            user_id="user_cache",
            task_count=0,
        )
        
        # Compute cache key
        cache_key = compiler._compute_cache_key(request, session)
        
        # Initially no cache
        assert compiler._get_cached_patch(cache_key) is None
        
        # Create mock patch and cache it
        from context_compiler.models import ContextPatch
        mock_patch = ContextPatch(
            status="complete",
            artifacts=[],
            files_read=["test.txt"],
            reasoning="Test",
            steps_used=2,
            confidence=0.9,
        )
        
        compiler._cache_patch(cache_key, mock_patch)
        
        # Should retrieve from cache
        cached = compiler._get_cached_patch(cache_key)
        assert cached is not None
        assert cached.status == "complete"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
