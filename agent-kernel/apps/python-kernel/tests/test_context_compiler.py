"""
Unit tests for Context Compiler components.

Tests for:
- ContextCompilerSkill
- ProcessContextCompilerAgent
- WorkingSetBuilder dynamic rules
"""
import json
import pytest
from datetime import datetime
from unittest.mock import Mock, AsyncMock, patch

from thread_runtime.models import Phase, ArtifactSlot
from thread_runtime.working_set_builder import WorkingSetBuilder
from context_compiler.compiler_skill import (
    ContextCompilerSkill,
    ExplorationStrategy,
    WorkingSetRules,
)


class TestContextCompilerSkill:
    """Tests for ContextCompilerSkill."""
    
    @pytest.fixture
    def mock_compiler_agent(self):
        """Create a mock compiler agent."""
        agent = Mock()
        agent.current_phase = Phase.EXPLORE
        agent.artifact_slots = {}
        agent._transition_to_execute = AsyncMock()
        return agent
    
    @pytest.fixture
    def skill(self, mock_compiler_agent):
        """Create a ContextCompilerSkill instance."""
        return ContextCompilerSkill(mock_compiler_agent)
    
    # ============================================================================
    # Working Set Rules Tests
    # ============================================================================
    
    @pytest.mark.asyncio
    async def test_update_working_set_rules(self, skill):
        """Test updating working set rules."""
        result = await skill.update_working_set_rules(
            phase="explore",
            max_observations=20,
            artifact_priority_boost=["session_summary", "task_output"],
            context_notes=["Important note"],
        )
        
        assert result["success"] is True
        assert result["phase"] == "explore"
        assert skill.working_set_rules.max_observations == 20
        # Default value is 5, adding 5 = 10
        assert skill.working_set_rules.artifact_priority_boost["session_summary"] == 10
        assert skill.working_set_rules.artifact_priority_boost["task_output"] == 10
        assert "Important note" in skill.working_set_rules.context_notes
    
    @pytest.mark.asyncio
    async def test_update_working_set_rules_partial(self, skill):
        """Test updating only some working set rules."""
        result = await skill.update_working_set_rules(
            phase="explore",
            max_observations=15,
        )
        
        assert result["success"] is True
        assert skill.working_set_rules.max_observations == 15
    
    # ============================================================================
    # Exploration Strategy Tests
    # ============================================================================
    
    @pytest.mark.asyncio
    async def test_set_exploration_strategy(self, skill):
        """Test setting exploration strategy."""
        result = await skill.set_exploration_strategy(
            strategy="goal_directed",
            focus_areas=["session_history", "recent_tasks"],
            priority_files=["data/sessions/sess_123.json"],
            max_steps=30,
        )
        
        assert result["success"] is True
        assert skill.exploration_strategy.strategy_type == "goal_directed"
        assert skill.exploration_strategy.focus_areas == ["session_history", "recent_tasks"]
        assert skill.exploration_strategy.max_steps == 30
        assert len(result["suggested_next_actions"]) > 0
    
    @pytest.mark.asyncio
    async def test_strategy_change_recorded(self, skill):
        """Test that strategy changes are recorded."""
        await skill.set_exploration_strategy(strategy="depth_first")
        await skill.set_exploration_strategy(strategy="goal_directed")
        
        assert len(skill.exploration_metadata["strategy_changes"]) == 2
        assert skill.exploration_metadata["strategy_changes"][0]["from"] == "breadth_first"
        assert skill.exploration_metadata["strategy_changes"][0]["to"] == "depth_first"
    
    # ============================================================================
    # Exploration Completion Tests
    # ============================================================================
    
    @pytest.mark.asyncio
    async def test_mark_exploration_complete_success(self, skill, mock_compiler_agent):
        """Test marking exploration complete with sufficient confidence."""
        result = await skill.mark_exploration_complete(
            reason="Gathered sufficient context",
            confidence=0.8,
        )
        
        assert result["success"] is True
        assert result["phase_transition"] == "explore → execute"
        mock_compiler_agent._transition_to_execute.assert_called_once_with("Gathered sufficient context")
    
    @pytest.mark.asyncio
    async def test_mark_exploration_complete_low_confidence(self, skill):
        """Test marking exploration complete with low confidence fails."""
        result = await skill.mark_exploration_complete(
            reason="Not enough context",
            confidence=0.3,
        )
        
        assert result["success"] is False
        assert "Confidence too low" in result["error"]
    
    # ============================================================================
    # Artifact Slot Tests
    # ============================================================================
    
    @pytest.mark.asyncio
    async def test_register_artifact_slot(self, skill, mock_compiler_agent):
        """Test registering an artifact slot."""
        result = await skill.register_artifact_slot(
            slot_type="session_summary",
            content={"session_id": "sess_123", "status": "active"},
            priority=8,
        )
        
        assert result["success"] is True
        assert result["slot_type"] == "session_summary"
        assert result["total_slots"] == 1
        assert len(mock_compiler_agent.artifact_slots) == 1
    
    @pytest.mark.asyncio
    async def test_register_artifact_slot_auto_id(self, skill, mock_compiler_agent):
        """Test that artifact slot ID is auto-generated."""
        result = await skill.register_artifact_slot(
            slot_type="test_slot",
            content="test content",
        )
        
        assert result["success"] is True
        assert result["slot_id"].startswith("test_slot_")
    
    @pytest.mark.asyncio
    async def test_update_artifact_slot(self, skill, mock_compiler_agent):
        """Test updating an existing artifact slot."""
        # First register a slot
        await skill.register_artifact_slot(
            slot_type="test_slot",
            content="original content",
            slot_id="test_123",
        )
        
        # Update it
        result = await skill.update_artifact_slot(
            slot_id="test_123",
            content="updated content",
            priority=9,
        )
        
        assert result["success"] is True
        slot = mock_compiler_agent.artifact_slots["test_123"]
        assert slot.content == "updated content"
        assert slot.priority == 9
    
    @pytest.mark.asyncio
    async def test_update_nonexistent_slot(self, skill):
        """Test updating a non-existent slot fails."""
        result = await skill.update_artifact_slot(
            slot_id="nonexistent",
            content="content",
        )
        
        assert result["success"] is False
        assert "not found" in result["error"]
    
    # ============================================================================
    # Context Filtering Tests
    # ============================================================================
    
    @pytest.mark.asyncio
    async def test_filter_context(self, skill):
        """Test filtering context."""
        result = await skill.filter_context(
            observations_to_keep=["event_1", "event_2"],
            observations_to_remove=["event_3"],
            slots_to_activate=["slot_1"],
            slots_to_deactivate=["slot_2"],
        )
        
        assert result["success"] is True
        assert result["applied_filters"]["kept_observations"] == 2
        assert result["applied_filters"]["removed_observations"] == 1
        assert result["applied_filters"]["activated_slots"] == 1
        assert result["applied_filters"]["deactivated_slots"] == 1
        
        # Check internal state
        rules = skill.working_set_rules
        assert "event_1" in rules.forced_observations
        assert "event_3" in rules.filtered_observations
        assert "slot_1" in rules.forced_slots
        assert "slot_2" in rules.excluded_slots
    
    # ============================================================================
    # Utility Tests
    # ============================================================================
    
    def test_record_file_read(self, skill):
        """Test recording file reads."""
        skill.record_file_read("data/sessions/test.json", "summary of content")
        
        assert len(skill.exploration_metadata["files_read"]) == 1
        assert skill.exploration_metadata["files_read"][0]["path"] == "data/sessions/test.json"
        assert skill.exploration_strategy.current_step == 1
    
    def test_get_exploration_summary(self, skill):
        """Test getting exploration summary."""
        # Setup some state
        skill.exploration_strategy.current_step = 5
        skill.exploration_metadata["files_read"] = [{}, {}, {}]
        
        summary = skill.get_exploration_summary()
        
        assert summary["strategy"] == "breadth_first"
        assert summary["steps_taken"] == 5
        assert summary["files_read"] == 3


class TestWorkingSetBuilderDynamicRules:
    """Tests for WorkingSetBuilder dynamic rule modifications."""
    
    @pytest.fixture
    def builder(self):
        """Create a WorkingSetBuilder instance."""
        return WorkingSetBuilder()
    
    def test_update_max_observations(self, builder):
        """Test updating max observations dynamically."""
        builder.update_max_observations(25)
        assert builder._dynamic_max_observations == 25
    
    def test_boost_artifact_priority(self, builder):
        """Test boosting artifact priority."""
        builder.boost_artifact_priority("session_summary", 3)
        assert builder._artifact_priority_boosts["session_summary"] == 3
        
        # Boost again
        builder.boost_artifact_priority("session_summary", 2)
        assert builder._artifact_priority_boosts["session_summary"] == 5
    
    def test_force_and_exclude_observations(self, builder):
        """Test forcing and excluding observations."""
        builder.force_observation("event_1")
        builder.force_observation("event_2")
        builder.exclude_observation("event_3")
        
        assert "event_1" in builder._forced_observations
        assert "event_2" in builder._forced_observations
        assert "event_3" in builder._excluded_observations
    
    def test_force_and_exclude_slots(self, builder):
        """Test forcing and excluding slots."""
        builder.force_slot("slot_1")
        builder.exclude_slot("slot_2")
        
        assert "slot_1" in builder._forced_slots
        assert "slot_2" in builder._excluded_slots
    
    def test_add_context_note(self, builder):
        """Test adding context notes."""
        builder.add_context_note("Note 1")
        builder.add_context_note("Note 2")
        
        assert len(builder._context_notes) == 2
        assert "Note 1" in builder._context_notes
    
    def test_clear_dynamic_rules(self, builder):
        """Test clearing all dynamic rules."""
        # Setup some rules
        builder.update_max_observations(20)
        builder.boost_artifact_priority("test", 5)
        builder.force_observation("event_1")
        builder.force_slot("slot_1")
        builder.add_context_note("Note")
        
        # Clear them
        builder.clear_dynamic_rules()
        
        assert builder._dynamic_max_observations is None
        assert len(builder._artifact_priority_boosts) == 0
        assert len(builder._forced_observations) == 0
        assert len(builder._forced_slots) == 0
        assert len(builder._context_notes) == 0
    
    def test_get_dynamic_rules(self, builder):
        """Test getting current dynamic rules."""
        builder.update_max_observations(15)
        builder.force_observation("event_1")
        builder.force_slot("slot_1")
        builder.add_context_note("Test note")
        
        rules = builder.get_dynamic_rules()
        
        assert rules["max_observations"] == 15
        assert "event_1" in rules["forced_observations"]
        assert "slot_1" in rules["forced_slots"]
        assert "Test note" in rules["context_notes"]


class TestWorkingSetBuilderSelectionWithDynamicRules:
    """Tests for WorkingSetBuilder selection logic with dynamic rules."""
    
    @pytest.fixture
    def builder(self):
        """Create a WorkingSetBuilder instance."""
        return WorkingSetBuilder()
    
    @pytest.fixture
    def sample_events(self):
        """Create sample events for testing."""
        from thread_runtime.models import Event, EventType
        
        events = []
        for i in range(10):
            event = Event(
                event_id=f"event_{i}",
                event_type=EventType.TOOL_RESULT,
                actor="test",
                phase=Phase.EXPLORE,
                content={"summary": f"Event {i}"},
            )
            events.append(event)
        return events
    
    @pytest.fixture
    def sample_artifacts(self):
        """Create sample artifact slots for testing."""
        return {
            "slot_1": ArtifactSlot(
                slot_id="slot_1",
                slot_type="session_summary",
                content="Session data",
                priority=5,
                phase_created=Phase.EXPLORE,
            ),
            "slot_2": ArtifactSlot(
                slot_id="slot_2",
                slot_type="task_output",
                content="Task output",
                priority=7,
                phase_created=Phase.EXPLORE,
            ),
            "slot_3": ArtifactSlot(
                slot_id="slot_3",
                slot_type="session_summary",
                content="More session data",
                priority=6,
                phase_created=Phase.EXPLORE,
            ),
        }
    
    def test_select_observations_with_forced(self, builder, sample_events):
        """Test that forced observations are always included."""
        from thread_runtime.working_set_builder import ObservationSelectionRule
        
        rule = ObservationSelectionRule(
            phase=Phase.EXPLORE,
            max_count=3,
            lookback_steps=None,
            priority_event_types=[],
        )
        
        # Force some events
        builder.force_observation("event_0")
        builder.force_observation("event_5")
        
        observations = builder._select_observations(sample_events, rule)
        
        # Check that forced events are included
        event_ids = [obs["event_id"] for obs in observations]
        assert "event_0" in event_ids
        assert "event_5" in event_ids
    
    def test_select_observations_with_excluded(self, builder, sample_events):
        """Test that excluded observations are not included."""
        from thread_runtime.working_set_builder import ObservationSelectionRule
        from thread_runtime.models import EventType
        
        rule = ObservationSelectionRule(
            phase=Phase.EXPLORE,
            max_count=10,
            lookback_steps=None,
            priority_event_types=[EventType.TOOL_RESULT],
        )
        
        # Exclude some events
        builder.exclude_observation("event_1")
        builder.exclude_observation("event_3")
        
        observations = builder._select_observations(sample_events, rule)
        
        # Check that excluded events are not included
        event_ids = [obs["event_id"] for obs in observations]
        assert "event_1" not in event_ids
        assert "event_3" not in event_ids
    
    def test_select_artifacts_with_forced(self, builder, sample_artifacts):
        """Test that forced slots are always included."""
        from thread_runtime.working_set_builder import SlotSelectionRule
        
        rule = SlotSelectionRule(
            phase=Phase.EXPLORE,
            slot_types=["session_summary"],
            max_slots=2,
            priority_threshold=1,
        )
        
        # Force a slot
        builder.force_slot("slot_2")  # slot_2 is task_output, not in allowed types
        
        selected = builder._select_artifacts(sample_artifacts, rule)
        
        # Forced slot should be included even if type doesn't match
        assert "slot_2" in selected
    
    def test_select_artifacts_with_excluded(self, builder, sample_artifacts):
        """Test that excluded slots are not included."""
        from thread_runtime.working_set_builder import SlotSelectionRule
        
        rule = SlotSelectionRule(
            phase=Phase.EXPLORE,
            slot_types=["session_summary", "task_output"],
            max_slots=10,
            priority_threshold=1,
        )
        
        # Exclude a slot
        builder.exclude_slot("slot_1")
        
        selected = builder._select_artifacts(sample_artifacts, rule)
        
        # Excluded slot should not be included
        assert "slot_1" not in selected
    
    def test_select_artifacts_with_priority_boost(self, builder, sample_artifacts):
        """Test that priority boosts affect selection."""
        from thread_runtime.working_set_builder import SlotSelectionRule
        
        rule = SlotSelectionRule(
            phase=Phase.EXPLORE,
            slot_types=["session_summary", "task_output"],
            max_slots=2,
            priority_threshold=1,
        )
        
        # Boost slot_1's type (session_summary)
        builder.boost_artifact_priority("session_summary", 5)
        
        selected = builder._select_artifacts(sample_artifacts, rule)
        
        # slot_1 should be prioritized (it's session_summary with boosted priority)
        assert "slot_1" in selected


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
