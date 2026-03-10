"""
Working Set Builder - Rule-driven context constructor for Agent Threads.

Builds bounded Working Sets from Event Log + Artifact Slots based on configurable rules.
"""
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog
import yaml

from thread_runtime.models import (
    ArtifactSlot,
    Event,
    EventLog,
    EventType,
    Phase,
    WorkingSet,
)

logger = structlog.get_logger()


@dataclass
class SlotSelectionRule:
    """Rule for selecting artifact slots."""
    phase: Phase
    slot_types: list[str]
    max_slots: int
    priority_threshold: int


@dataclass
class ObservationSelectionRule:
    """Rule for selecting observations."""
    phase: Phase
    max_count: int
    lookback_steps: int | None
    priority_event_types: list[EventType]


@dataclass
class TokenBudget:
    """Token budget allocation."""
    max_total: int
    reserved_for_immutable: int
    reserved_for_observations: int
    reserved_for_artifacts: int
    reserved_for_notes: int


class WorkingSetBuilder:
    """
    Rule-driven Working Set constructor.
    
    Uses YAML configuration to define rules for:
    - Artifact slot selection per phase
    - Observation filtering per phase
    - Token budget management
    """
    
    def __init__(self, config_path: str | None = None):
        self.logger = logger.bind(component="WorkingSetBuilder")
        
        # Load configuration
        self.config = self._load_config(config_path)
        
        # Parse rules from config
        self.slot_rules: dict[Phase, SlotSelectionRule] = {}
        self.obs_rules: dict[Phase, ObservationSelectionRule] = {}
        self.token_budget: TokenBudget
        self.artifact_priorities: dict[str, int] = {}
        
        self._parse_config()
    
    def _load_config(self, config_path: str | None) -> dict:
        """Load configuration from YAML file."""
        if config_path and Path(config_path).exists():
            self.logger.info("Loading config from file", path=config_path)
            with open(config_path) as f:
                return yaml.safe_load(f)
        
        # Use default config
        self.logger.info("Using default configuration")
        return self._default_config()
    
    def _default_config(self) -> dict:
        """Default configuration."""
        return {
            "version": "1.0",
            "phases": {
                "explore": {
                    "description": "Information gathering phase",
                    "slot_selection": {
                        "slot_types": ["module_map", "symbol_index", "context_report", "file_tree"],
                        "max_slots": 3,
                        "priority_threshold": 5,
                    },
                    "observation_selection": {
                        "max_count": 10,
                        "lookback_steps": 20,
                        "priority_event_types": ["tool_result", "observation", "error"],
                    },
                },
                "execute": {
                    "description": "Action execution phase",
                    "slot_selection": {
                        "slot_types": ["patch_plan", "dependency_summary", "test_plan", "verification_result"],
                        "max_slots": 4,
                        "priority_threshold": 5,
                    },
                    "observation_selection": {
                        "max_count": 5,
                        "lookback_steps": 10,
                        "priority_event_types": ["tool_result", "error"],
                    },
                },
                "complete": {
                    "description": "Completion phase",
                    "slot_selection": {
                        "slot_types": ["final_result", "summary", "next_steps"],
                        "max_slots": 2,
                        "priority_threshold": 1,
                    },
                    "observation_selection": {
                        "max_count": 3,
                        "lookback_steps": 5,
                        "priority_event_types": ["tool_result"],
                    },
                },
            },
            "artifact_priorities": {
                "module_map": 8,
                "symbol_index": 7,
                "context_report": 6,
                "file_tree": 5,
                "patch_plan": 9,
                "dependency_summary": 7,
                "test_plan": 8,
                "verification_result": 8,
                "final_result": 10,
                "summary": 9,
                "next_steps": 7,
            },
            "token_budget": {
                "max_total": 4000,
                "reserved_for_immutable": 500,
                "reserved_for_observations": 1500,
                "reserved_for_artifacts": 1500,
                "reserved_for_notes": 500,
            },
        }
    
    def _parse_config(self) -> None:
        """Parse configuration into rule objects."""
        # Parse phase rules
        for phase_name, phase_config in self.config.get("phases", {}).items():
            phase = Phase(phase_name)
            
            # Slot selection rule
            slot_cfg = phase_config.get("slot_selection", {})
            self.slot_rules[phase] = SlotSelectionRule(
                phase=phase,
                slot_types=slot_cfg.get("slot_types", []),
                max_slots=slot_cfg.get("max_slots", 3),
                priority_threshold=slot_cfg.get("priority_threshold", 1),
            )
            
            # Observation selection rule
            obs_cfg = phase_config.get("observation_selection", {})
            event_types = [
                EventType(et) for et in obs_cfg.get("priority_event_types", [])
            ]
            lookback = obs_cfg.get("lookback_steps")
            self.obs_rules[phase] = ObservationSelectionRule(
                phase=phase,
                max_count=obs_cfg.get("max_count", 10),
                lookback_steps=lookback if lookback != -1 else None,
                priority_event_types=event_types,
            )
        
        # Parse artifact priorities
        self.artifact_priorities = self.config.get("artifact_priorities", {})
        
        # Parse token budget
        budget_cfg = self.config.get("token_budget", {})
        self.token_budget = TokenBudget(
            max_total=budget_cfg.get("max_total", 4000),
            reserved_for_immutable=budget_cfg.get("reserved_for_immutable", 500),
            reserved_for_observations=budget_cfg.get("reserved_for_observations", 1500),
            reserved_for_artifacts=budget_cfg.get("reserved_for_artifacts", 1500),
            reserved_for_notes=budget_cfg.get("reserved_for_notes", 500),
        )
    
    def build(
        self,
        task_id: str,
        task_goal: str,
        event_log: EventLog | Any,  # Accept EventLogManager too
        artifact_slots: dict[str, ArtifactSlot],
        immutable_input: dict[str, Any],
        current_phase: Phase,
        step_number: int = 1,
        confirmed_facts: list[str] | None = None,
        pending_decisions: list[str] | None = None,
        context_notes: list[str] | None = None,
    ) -> WorkingSet:
        """
        Build a Working Set based on rules.
        
        Args:
            task_id: Task identifier
            task_goal: Task objective
            event_log: Event log (or EventLogManager)
            artifact_slots: Available artifact slots
            immutable_input: Immutable context
            current_phase: Current execution phase
            step_number: Current step number
            confirmed_facts: List of confirmed facts
            pending_decisions: List of pending decisions
            context_notes: Additional context notes
            
        Returns:
            Constructed WorkingSet
        """
        self.logger.debug(
            "Building Working Set",
            task_id=task_id,
            phase=current_phase.value,
            step=step_number,
        )
        
        # Get rules for current phase
        slot_rule = self.slot_rules.get(current_phase, self.slot_rules[Phase.EXPLORE])
        obs_rule = self.obs_rules.get(current_phase, self.obs_rules[Phase.EXPLORE])
        
        # Extract events from EventLogManager if needed
        if hasattr(event_log, 'log'):
            events = event_log.log.events
        else:
            events = event_log.events
        
        # Select active artifacts
        active_artifacts = self._select_artifacts(
            artifact_slots, slot_rule
        )
        
        # Select recent observations
        recent_observations = self._select_observations(
            events, obs_rule
        )
        
        # Get previous action result
        previous_result = self._get_previous_result(events)
        
        # Build Working Set
        working_set = WorkingSet(
            task_id=task_id,
            task_goal=task_goal,
            current_phase=current_phase,
            step_number=step_number,
            immutable_context=immutable_input,
            confirmed_facts=confirmed_facts or [],
            recent_observations=recent_observations,
            active_artifacts=active_artifacts,
            previous_action_result=previous_result,
            pending_decisions=pending_decisions or [],
            context_notes=context_notes or [],
        )
        
        # Estimate and validate tokens
        working_set.token_estimate = self._estimate_tokens(working_set)
        
        if working_set.token_estimate > self.token_budget.max_total:
            self.logger.warning(
                "Working Set exceeds token budget, truncating",
                estimated=working_set.token_estimate,
                budget=self.token_budget.max_total,
            )
            working_set = self._truncate_if_needed(working_set)
        
        self.logger.debug(
            "Working Set built",
            phase=current_phase.value,
            artifacts=len(active_artifacts),
            observations=len(recent_observations),
            tokens=working_set.token_estimate,
        )
        
        return working_set
    
    def _select_artifacts(
        self,
        artifact_slots: dict[str, ArtifactSlot],
        rule: SlotSelectionRule,
    ) -> dict[str, Any]:
        """Select artifact slots based on rules."""
        # Filter by type and priority threshold
        candidates = []
        for slot_id, slot in artifact_slots.items():
            # Check if slot type is in allowed types
            if slot.slot_type not in rule.slot_types:
                continue
            
            # Check priority threshold
            if slot.priority < rule.priority_threshold:
                continue
            
            candidates.append((slot_id, slot))
        
        # Sort by priority (descending)
        candidates.sort(key=lambda x: x[1].priority, reverse=True)
        
        # Take top N
        selected = candidates[:rule.max_slots]
        
        # Convert to dict
        return {slot_id: slot.content for slot_id, slot in selected}
    
    def _select_observations(
        self,
        events: list[Event],
        rule: ObservationSelectionRule,
    ) -> list[dict[str, Any]]:
        """Select recent observations based on rules."""
        if not events:
            return []
        
        # Determine lookback range
        if rule.lookback_steps is not None:
            start_idx = max(0, len(events) - rule.lookback_steps)
            recent_events = events[start_idx:]
        else:
            recent_events = events
        
        # Filter by event type priority
        filtered = []
        for event in reversed(recent_events):  # Most recent first
            if event.event_type in rule.priority_event_types:
                filtered.append(event)
            if len(filtered) >= rule.max_count:
                break
        
        # Convert to observation format
        observations = []
        for event in reversed(filtered):  # Back to chronological order
            obs = {
                "event_id": event.event_id,
                "event_type": event.event_type.value,
                "phase": event.phase.value,
                "timestamp": event.timestamp.isoformat(),
                "text": event.to_prompt_text(),
                "content": event.content,
            }
            observations.append(obs)
        
        return observations
    
    def _get_previous_result(
        self,
        events: list[Event],
    ) -> dict[str, Any] | None:
        """Extract the most recent action result."""
        for event in reversed(events):
            if event.event_type in (EventType.TOOL_RESULT, EventType.OBSERVATION):
                return {
                    "event_id": event.event_id,
                    "event_type": event.event_type.value,
                    "summary": event.content.get("summary", ""),
                    "success": event.content.get("success", True),
                    "content": event.content,
                }
        return None
    
    def _estimate_tokens(self, working_set: WorkingSet) -> int:
        """
        Rough token estimation.
        Very approximate: ~4 chars per token for English text.
        """
        text = working_set.to_prompt()
        # Rough estimate: 1 token ≈ 4 characters
        return len(text) // 4
    
    def _truncate_if_needed(self, working_set: WorkingSet) -> WorkingSet:
        """Truncate Working Set if it exceeds token budget."""
        # Truncate observations first
        while (
            working_set.token_estimate > self.token_budget.max_total
            and len(working_set.recent_observations) > 3
        ):
            working_set.recent_observations.pop(0)
            working_set.token_estimate = self._estimate_tokens(working_set)
        
        # Then truncate artifacts
        if working_set.token_estimate > self.token_budget.max_total:
            while (
                len(working_set.active_artifacts) > 1
                and working_set.token_estimate > self.token_budget.max_total
            ):
                # Remove lowest priority artifact
                keys = list(working_set.active_artifacts.keys())
                if keys:
                    del working_set.active_artifacts[keys[0]]
                working_set.token_estimate = self._estimate_tokens(working_set)
        
        return working_set
    
    def get_config_summary(self) -> dict[str, Any]:
        """Get summary of current configuration."""
        return {
            "phases": list(self.slot_rules.keys()),
            "artifact_priorities": self.artifact_priorities,
            "token_budget": {
                "max_total": self.token_budget.max_total,
                "immutable": self.token_budget.reserved_for_immutable,
                "observations": self.token_budget.reserved_for_observations,
                "artifacts": self.token_budget.reserved_for_artifacts,
                "notes": self.token_budget.reserved_for_notes,
            },
        }
