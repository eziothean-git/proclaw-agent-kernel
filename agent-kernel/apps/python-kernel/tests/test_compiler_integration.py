"""
Integration tests for ProcessContextCompilerAgent.

These tests verify the end-to-end compilation flow.
"""
import json
import pytest
import tempfile
from datetime import datetime
from pathlib import Path

from schemas.models import (
    IntermediateRepresentation,
    CompiledContext,
    TaskSnapshot,
    TaskStatus,
)
from context_compiler.process_compiler import ProcessContextCompiler, get_process_compiler
from context_compiler.compiler_agent import ProcessContextCompilerAgent
from thread_runtime.models import Phase


@pytest.fixture
def temp_data_dir():
    """Create a temporary data directory with test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        data_dir = Path(tmpdir) / "data"
        data_dir.mkdir()
        
        # Create subdirectories
        (data_dir / "sessions").mkdir()
        (data_dir / "tasks").mkdir()
        (data_dir / "events").mkdir()
        (data_dir / "snapshots").mkdir()
        
        # Create a test session file
        session_data = {
            "id": "sess_test_123",
            "user_id": "user_123",
            "status": "active",
            "task_count": 3,
            "created_at": datetime.utcnow().isoformat(),
            "metadata": {"topic": "test_session"},
        }
        with open(data_dir / "sessions" / "sess_test_123.json", "w") as f:
            json.dump(session_data, f)
        
        # Create test task files
        for i in range(3):
            task_data = {
                "id": f"task_{i}",
                "session_id": "sess_test_123",
                "status": "completed",
                "goal": f"Test task {i}",
                "output": f"Output of task {i}",
                "created_at": datetime.utcnow().isoformat(),
            }
            with open(data_dir / "tasks" / f"task_{i}.json", "w") as f:
                json.dump(task_data, f)
        
        # Create an event log
        events = []
        for i in range(5):
            event = {
                "timestamp": datetime.utcnow().isoformat(),
                "event_type": "tool_result",
                "content": {"summary": f"Event {i}"},
            }
            events.append(json.dumps(event))
        
        with open(data_dir / "events" / "sess_test_123.jsonl", "w") as f:
            f.write("\n".join(events))
        
        yield str(data_dir)


@pytest.fixture
def sample_process_definition():
    """Create a sample process definition."""
    return {
        "name": "test_process",
        "goal": "Test the context compiler",
        "capabilities": ["fs-skill"],
        "security_level": "normal",
    }


@pytest.fixture
def sample_intermediate_repr():
    """Create a sample intermediate representation."""
    return IntermediateRepresentation(
        request_id="req_123",
        intent="test",
        goals=["Test context compilation"],
        processes=[],
        context_hints={},
    )


@pytest.fixture
def sample_session_context():
    """Create a sample session context."""
    return {
        "session_id": "sess_test_123",
        "user_id": "user_123",
        "request_id": "req_123",
        "request_message": "Test message",
        "request_metadata": {},
    }


@pytest.fixture
def sample_task_snapshots():
    """Create sample task snapshots."""
    return [
        TaskSnapshot(
            id="task_0",
            session_id="sess_test_123",
            process_id="proc_0",
            status=TaskStatus.COMPLETED,
            goal="Previous task 0",
        ),
        TaskSnapshot(
            id="task_1",
            session_id="sess_test_123",
            process_id="proc_1",
            status=TaskStatus.COMPLETED,
            goal="Previous task 1",
        ),
    ]


class TestProcessContextCompilerIntegration:
    """Integration tests for the full compilation flow."""
    
    @pytest.mark.asyncio
    async def test_compiler_agent_creation(
        self,
        sample_process_definition,
        sample_intermediate_repr,
        sample_session_context,
        sample_task_snapshots,
    ):
        """Test that ProcessContextCompilerAgent can be created."""
        agent = ProcessContextCompilerAgent(
            target_task_id="task_target",
            process_definition=sample_process_definition,
            intermediate_repr=sample_intermediate_repr,
            session_context=sample_session_context,
            task_snapshots=sample_task_snapshots,
        )
        
        assert agent.target_task_id == "task_target"
        assert agent.current_phase == Phase.EXPLORE
        assert len(agent.artifact_slots) == 0
    
    @pytest.mark.asyncio
    async def test_compiler_agent_run(
        self,
        sample_process_definition,
        sample_intermediate_repr,
        sample_session_context,
        sample_task_snapshots,
    ):
        """Test compiler agent execution."""
        agent = ProcessContextCompilerAgent(
            target_task_id="task_target",
            process_definition=sample_process_definition,
            intermediate_repr=sample_intermediate_repr,
            session_context=sample_session_context,
            task_snapshots=sample_task_snapshots,
        )
        
        # Run agent
        result = await agent.run()
        
        # Verify result
        assert isinstance(result, CompiledContext)
        assert result.task_id == "task_target"
        assert result.task_goal == "Test the context compiler"
        assert hasattr(result, "metadata")
    
    def test_process_compiler_singleton(self):
        """Test that get_process_compiler returns a singleton."""
        compiler1 = get_process_compiler()
        compiler2 = get_process_compiler()
        
        assert compiler1 is compiler2
        assert isinstance(compiler1, ProcessContextCompiler)
    
    @pytest.mark.asyncio
    async def test_process_compiler_compilation(
        self,
        sample_process_definition,
        sample_intermediate_repr,
        sample_session_context,
        sample_task_snapshots,
    ):
        """Test the full compilation flow via ProcessContextCompiler."""
        compiler = ProcessContextCompiler()
        
        result = await compiler.compile_task_context(
            task_id="task_target",
            process_definition=sample_process_definition,
            intermediate_repr=sample_intermediate_repr,
            session_context=sample_session_context,
            task_snapshots=sample_task_snapshots,
        )
        
        assert isinstance(result, CompiledContext)
        assert result.task_id == "task_target"
        assert result.task_goal == "Test the context compiler"
        assert len(result.allowed_capabilities) > 0
        assert "fs-skill" in result.allowed_capabilities
    
    @pytest.mark.asyncio
    async def test_compiled_context_structure(
        self,
        sample_process_definition,
        sample_intermediate_repr,
        sample_session_context,
    ):
        """Test that CompiledContext has the expected structure."""
        compiler = ProcessContextCompiler()
        
        result = await compiler.compile_task_context(
            task_id="task_test",
            process_definition=sample_process_definition,
            intermediate_repr=sample_intermediate_repr,
            session_context=sample_session_context,
            task_snapshots=[],
        )
        
        # Verify CompiledContext fields
        assert result.task_id == "task_test"
        assert result.task_goal
        assert isinstance(result.constraints, list)
        assert isinstance(result.allowed_capabilities, list)
        assert isinstance(result.forbidden_capabilities, list)
        assert isinstance(result.memory_references, list)
        assert result.compiled_at is not None
        
        # Verify metadata
        assert "compilation_steps" in result.metadata
        assert "artifacts_gathered" in result.metadata


class TestCompilerAgentExplorationCapabilities:
    """Tests for compiler agent exploration capabilities."""
    
    @pytest.mark.asyncio
    async def test_exploration_strategy_tracking(self):
        """Test that exploration strategy changes are tracked."""
        agent = ProcessContextCompilerAgent(
            target_task_id="test",
            process_definition={"goal": "test", "capabilities": []},
            intermediate_repr=IntermediateRepresentation(
                request_id="req",
                intent="test",
                goals=[],
                processes=[],
            ),
            session_context={"session_id": "sess"},
        )
        
        # Initially breadth_first
        assert agent.compiler_skill.exploration_strategy.strategy_type == "breadth_first"
        
        # Change strategy
        await agent.compiler_skill.set_exploration_strategy("depth_first")
        assert agent.compiler_skill.exploration_strategy.strategy_type == "depth_first"
        
        # Check that change was recorded
        assert len(agent.compiler_skill.exploration_metadata["strategy_changes"]) == 1
    
    @pytest.mark.asyncio
    async def test_artifact_registration(self):
        """Test that artifacts can be registered during exploration."""
        agent = ProcessContextCompilerAgent(
            target_task_id="test",
            process_definition={"goal": "test", "capabilities": []},
            intermediate_repr=IntermediateRepresentation(
                request_id="req",
                intent="test",
                goals=[],
                processes=[],
            ),
            session_context={"session_id": "sess"},
        )
        
        # Register an artifact
        result = await agent.compiler_skill.register_artifact_slot(
            slot_type="test_artifact",
            content={"data": "test"},
            priority=8,
        )
        
        assert result["success"] is True
        assert len(agent.artifact_slots) == 1
        
        # Verify slot content
        slot_id = result["slot_id"]
        assert agent.artifact_slots[slot_id].content == {"data": "test"}
        assert agent.artifact_slots[slot_id].priority == 8
    
    @pytest.mark.asyncio
    async def test_file_read_tracking(self):
        """Test that file reads are tracked."""
        agent = ProcessContextCompilerAgent(
            target_task_id="test",
            process_definition={"goal": "test", "capabilities": []},
            intermediate_repr=IntermediateRepresentation(
                request_id="req",
                intent="test",
                goals=[],
                processes=[],
            ),
            session_context={"session_id": "sess"},
        )
        
        # Simulate file reads
        agent.compiler_skill.record_file_read("data/test1.json", "summary1")
        agent.compiler_skill.record_file_read("data/test2.json", "summary2")
        
        # Check tracking
        assert len(agent.compiler_skill.exploration_metadata["files_read"]) == 2
        assert agent.compiler_skill.exploration_strategy.current_step == 2
    
    @pytest.mark.asyncio
    async def test_exploration_completion(self):
        """Test marking exploration as complete."""
        agent = ProcessContextCompilerAgent(
            target_task_id="test",
            process_definition={"goal": "test", "capabilities": []},
            intermediate_repr=IntermediateRepresentation(
                request_id="req",
                intent="test",
                goals=[],
                processes=[],
            ),
            session_context={"session_id": "sess"},
        )
        
        # Initially in EXPLORE phase
        assert agent.current_phase == Phase.EXPLORE
        
        # Mark exploration complete with high confidence
        result = await agent.compiler_skill.mark_exploration_complete(
            reason="Sufficient context gathered",
            confidence=0.8,
        )
        
        assert result["success"] is True



if __name__ == "__main__":
    pytest.main([__file__, "-v"])
