"""
Context Compiler Skill - Dynamic context management for Process Context Compiler Agent.

This skill provides advanced capabilities for Process Context Compiler Agent to:
- Modify Working Set building rules dynamically
- Change exploration strategies
- Register artifact slots for discovered information
- Filter and reorganize context
- Signal exploration completion

Note: This skill is ONLY exposed to Process Context Compiler Agent context.
"""
from dataclasses import dataclass, field
from typing import Any, TYPE_CHECKING
from uuid import uuid4

import structlog

if TYPE_CHECKING:
    from context_compiler.compiler_agent import ProcessContextCompilerAgent

from thread_runtime.models import ArtifactSlot, Phase

logger = structlog.get_logger()


@dataclass
class ExplorationStrategy:
    """Exploration strategy configuration."""
    strategy_type: str = "breadth_first"  # breadth_first | depth_first | goal_directed
    focus_areas: list[str] = field(default_factory=list)
    priority_files: list[str] = field(default_factory=list)
    max_steps: int = 50
    current_step: int = 0


@dataclass
class WorkingSetRules:
    """Dynamic Working Set building rules."""
    max_observations: int = 10
    artifact_priority_boost: dict[str, int] = field(default_factory=dict)
    forced_observations: list[str] = field(default_factory=list)
    filtered_observations: list[str] = field(default_factory=list)
    forced_slots: list[str] = field(default_factory=list)
    excluded_slots: list[str] = field(default_factory=list)
    context_notes: list[str] = field(default_factory=list)


class ContextCompilerSkill:
    """
    Skill for Process Context Compiler Agent to manage context dynamically.
    
    This skill allows the compiler agent to:
    1. Modify Working Set building rules
    2. Change exploration strategy
    3. Register discovered information as artifacts
    4. Filter and reorganize context
    5. Signal when exploration is complete
    
    These capabilities make Process Context Compiler a "high-level agent"
    that can actively participate in context reorganization.
    """
    
    def __init__(self, compiler_agent: "ProcessContextCompilerAgent"):
        self.compiler = compiler_agent
        self.logger = logger.bind(component="ContextCompilerSkill")
        
        # Exploration state
        self.exploration_strategy = ExplorationStrategy()
        self.working_set_rules = WorkingSetRules()
        self.exploration_metadata = {
            "files_read": [],
            "strategy_changes": [],
            "start_time": None,
            "confidence_score": 0.0,
        }
    
    # ============================================================================
    # Working Set Rules Management
    # ============================================================================
    
    async def update_working_set_rules(
        self,
        phase: str,
        max_observations: int | None = None,
        artifact_priority_boost: list[str] | None = None,
        context_notes: list[str] | None = None,
    ) -> dict:
        """
        Dynamically modify Working Set building rules for the current phase.
        
        This allows the compiler to adjust how context is assembled based on
        what it has discovered during exploration.
        
        Args:
            phase: The phase to modify rules for (explore/execute/complete)
            max_observations: Maximum number of observations to include
            artifact_priority_boost: List of artifact types to boost priority
            context_notes: Additional notes to add to context
            
        Returns:
            Dict with success status and updated rules summary
        """
        try:
            if max_observations is not None:
                self.working_set_rules.max_observations = max_observations
                self.logger.info(
                    "Updated max_observations",
                    phase=phase,
                    max_observations=max_observations,
                )
            
            if artifact_priority_boost:
                for slot_type in artifact_priority_boost:
                    current = self.working_set_rules.artifact_priority_boost.get(slot_type, 5)
                    self.working_set_rules.artifact_priority_boost[slot_type] = min(current + 5, 10)
                self.logger.info(
                    "Boosted artifact priorities",
                    types=artifact_priority_boost,
                )
            
            if context_notes:
                self.working_set_rules.context_notes.extend(context_notes)
                self.logger.info(
                    "Added context notes",
                    count=len(context_notes),
                )
            
            return {
                "success": True,
                "phase": phase,
                "updated_rules": {
                    "max_observations": self.working_set_rules.max_observations,
                    "priority_boosts": self.working_set_rules.artifact_priority_boost,
                    "context_notes_count": len(self.working_set_rules.context_notes),
                },
            }
        except Exception as e:
            self.logger.error("Failed to update working set rules", error=str(e))
            return {
                "success": False,
                "error": f"Failed to update rules: {str(e)}",
            }
    
    # ============================================================================
    # Exploration Strategy Management
    # ============================================================================
    
    async def set_exploration_strategy(
        self,
        strategy: str,
        focus_areas: list[str] | None = None,
        priority_files: list[str] | None = None,
        max_steps: int | None = None,
    ) -> dict:
        """
        Set or change the exploration strategy.
        
        Allows the compiler to switch from breadth-first to depth-first
        or goal-directed exploration based on findings.
        
        Args:
            strategy: Strategy type (breadth_first | depth_first | goal_directed)
            focus_areas: Areas to focus exploration on
            priority_files: Specific files to prioritize reading
            max_steps: Maximum exploration steps allowed
            
        Returns:
            Dict with success status and suggested next actions
        """
        try:
            old_strategy = self.exploration_strategy.strategy_type
            
            self.exploration_strategy.strategy_type = strategy
            if focus_areas:
                self.exploration_strategy.focus_areas = focus_areas
            if priority_files:
                self.exploration_strategy.priority_files = priority_files
            if max_steps:
                self.exploration_strategy.max_steps = max_steps
            
            # Record strategy change
            self.exploration_metadata["strategy_changes"].append({
                "from": old_strategy,
                "to": strategy,
                "step": self.exploration_strategy.current_step,
            })
            
            self.logger.info(
                "Exploration strategy changed",
                from_strategy=old_strategy,
                to_strategy=strategy,
                focus_areas=focus_areas,
            )
            
            # Suggest next actions based on new strategy
            suggested_actions = self._suggest_exploration_actions()
            
            return {
                "success": True,
                "strategy": strategy,
                "focus_areas": self.exploration_strategy.focus_areas,
                "priority_files": self.exploration_strategy.priority_files,
                "suggested_next_actions": suggested_actions,
            }
        except Exception as e:
            self.logger.error("Failed to set exploration strategy", error=str(e))
            return {
                "success": False,
                "error": f"Failed to set strategy: {str(e)}",
            }
    
    def _suggest_exploration_actions(self) -> list[dict]:
        """Suggest next exploration actions based on current strategy."""
        suggestions = []
        
        if self.exploration_strategy.priority_files:
            # Suggest reading priority files first
            for file_path in self.exploration_strategy.priority_files[:3]:
                suggestions.append({
                    "action": "read_file",
                    "path": file_path,
                    "reason": "Priority file in current strategy",
                })
        
        if self.exploration_strategy.strategy_type == "goal_directed":
            suggestions.append({
                "action": "analyze_findings",
                "reason": "Goal-directed exploration requires analyzing current findings",
            })
        elif self.exploration_strategy.strategy_type == "depth_first":
            suggestions.append({
                "action": "drill_down",
                "reason": "Depth-first: explore current focus area thoroughly",
            })
        else:  # breadth_first
            suggestions.append({
                "action": "expand_scope",
                "reason": "Breadth-first: explore adjacent areas",
            })
        
        return suggestions
    
    async def mark_exploration_complete(
        self,
        reason: str,
        confidence: float,
    ) -> dict:
        """
        Signal that exploration is complete and trigger phase transition.
        
        This is the key mechanism for transitioning from EXPLORE to EXECUTE phase.
        The compiler calls this when it has gathered sufficient context.
        
        Args:
            reason: Explanation of why exploration is complete
            confidence: Confidence score (0.0-1.0) in gathered context
            
        Returns:
            Dict with success status and phase transition info
        """
        try:
            if confidence < 0.5:
                return {
                    "success": False,
                    "error": "Confidence too low to finalize exploration",
                    "suggestion": "Continue exploring or request clarification",
                    "current_confidence": confidence,
                }
            
            self.exploration_metadata["confidence_score"] = confidence
            
            # Trigger phase transition
            await self.compiler._transition_to_execute(reason)
            
            self.logger.info(
                "Exploration marked complete",
                reason=reason,
                confidence=confidence,
                files_read=len(self.exploration_metadata["files_read"]),
            )
            
            return {
                "success": True,
                "phase_transition": "explore → execute",
                "reason": reason,
                "confidence": confidence,
                "exploration_summary": {
                    "files_read": self.exploration_metadata["files_read"],
                    "strategy_changes": len(self.exploration_metadata["strategy_changes"]),
                    "steps_taken": self.exploration_strategy.current_step,
                },
            }
        except Exception as e:
            self.logger.error("Failed to mark exploration complete", error=str(e))
            return {
                "success": False,
                "error": f"Failed to complete exploration: {str(e)}",
            }
    
    # ============================================================================
    # Artifact Slot Management
    # ============================================================================
    
    async def register_artifact_slot(
        self,
        slot_type: str,
        content: Any,
        priority: int = 5,
        slot_id: str | None = None,
    ) -> dict:
        """
        Register discovered information as an Artifact Slot.
        
        Artifact Slots store structured intermediate outputs from exploration,
        such as session summaries, task outputs, or event analyses.
        
        Args:
            slot_type: Type of artifact (e.g., session_summary, task_output)
            content: The artifact content
            priority: Priority for Working Set selection (1-10)
            slot_id: Optional custom slot ID (auto-generated if not provided)
            
        Returns:
            Dict with success status and slot info
        """
        try:
            if slot_id is None:
                slot_id = f"{slot_type}_{uuid4().hex[:8]}"
            
            artifact = ArtifactSlot(
                slot_id=slot_id,
                slot_type=slot_type,
                content=content,
                priority=max(1, min(10, priority)),  # Clamp to 1-10
                phase_created=self.compiler.current_phase,
            )
            
            self.compiler.artifact_slots[slot_id] = artifact
            
            self.logger.info(
                "Registered artifact slot",
                slot_id=slot_id,
                slot_type=slot_type,
                priority=priority,
            )
            
            return {
                "success": True,
                "slot_id": slot_id,
                "slot_type": slot_type,
                "active_slots": list(self.compiler.artifact_slots.keys()),
                "total_slots": len(self.compiler.artifact_slots),
            }
        except Exception as e:
            self.logger.error("Failed to register artifact slot", error=str(e))
            return {
                "success": False,
                "error": f"Failed to register slot: {str(e)}",
            }
    
    async def update_artifact_slot(
        self,
        slot_id: str,
        content: Any,
        priority: int | None = None,
    ) -> dict:
        """
        Update an existing Artifact Slot.
        
        Args:
            slot_id: ID of the slot to update
            content: New content for the slot
            priority: Optional new priority
            
        Returns:
            Dict with success status
        """
        try:
            if slot_id not in self.compiler.artifact_slots:
                return {
                    "success": False,
                    "error": f"Slot not found: {slot_id}",
                }
            
            slot = self.compiler.artifact_slots[slot_id]
            slot.update(content)
            
            if priority is not None:
                slot.priority = max(1, min(10, priority))
            
            self.logger.info("Updated artifact slot", slot_id=slot_id)
            
            return {
                "success": True,
                "slot_id": slot_id,
                "updated_at": slot.updated_at.isoformat(),
            }
        except Exception as e:
            self.logger.error("Failed to update artifact slot", error=str(e))
            return {
                "success": False,
                "error": f"Failed to update slot: {str(e)}",
            }
    
    # ============================================================================
    # Context Filtering
    # ============================================================================
    
    async def filter_context(
        self,
        observations_to_keep: list[str] | None = None,
        observations_to_remove: list[str] | None = None,
        slots_to_activate: list[str] | None = None,
        slots_to_deactivate: list[str] | None = None,
    ) -> dict:
        """
        Actively filter and reorganize context.
        
        This is a key capability of high-level agents: they can decide
        which information to include or exclude from the Working Set.
        
        Args:
            observations_to_keep: Event IDs to force include
            observations_to_remove: Event IDs to exclude
            slots_to_activate: Slot IDs to force include
            slots_to_deactivate: Slot IDs to exclude
            
        Returns:
            Dict with success status and filter summary
        """
        try:
            applied = {
                "kept_observations": 0,
                "removed_observations": 0,
                "activated_slots": 0,
                "deactivated_slots": 0,
            }
            
            if observations_to_keep:
                self.working_set_rules.forced_observations.extend(observations_to_keep)
                applied["kept_observations"] = len(observations_to_keep)
            
            if observations_to_remove:
                self.working_set_rules.filtered_observations.extend(observations_to_remove)
                applied["removed_observations"] = len(observations_to_remove)
            
            if slots_to_activate:
                self.working_set_rules.forced_slots.extend(slots_to_activate)
                applied["activated_slots"] = len(slots_to_activate)
            
            if slots_to_deactivate:
                self.working_set_rules.excluded_slots.extend(slots_to_deactivate)
                applied["deactivated_slots"] = len(slots_to_deactivate)
            
            self.logger.info(
                "Applied context filters",
                **applied,
            )
            
            return {
                "success": True,
                "applied_filters": applied,
                "current_rules": {
                    "forced_observations": len(self.working_set_rules.forced_observations),
                    "filtered_observations": len(self.working_set_rules.filtered_observations),
                    "forced_slots": len(self.working_set_rules.forced_slots),
                    "excluded_slots": len(self.working_set_rules.excluded_slots),
                },
            }
        except Exception as e:
            self.logger.error("Failed to filter context", error=str(e))
            return {
                "success": False,
                "error": f"Failed to filter context: {str(e)}",
            }
    
    # ============================================================================
    # Utility Methods
    # ============================================================================
    
    def record_file_read(self, file_path: str, content_summary: str | None = None) -> None:
        """Record that a file was read during exploration."""
        self.exploration_metadata["files_read"].append({
            "path": file_path,
            "step": self.exploration_strategy.current_step,
            "summary": content_summary[:100] if content_summary else None,
        })
        self.exploration_strategy.current_step += 1
    
    def get_exploration_summary(self) -> dict:
        """Get summary of exploration progress."""
        return {
            "strategy": self.exploration_strategy.strategy_type,
            "steps_taken": self.exploration_strategy.current_step,
            "max_steps": self.exploration_strategy.max_steps,
            "files_read": len(self.exploration_metadata["files_read"]),
            "strategy_changes": len(self.exploration_metadata["strategy_changes"]),
            "confidence_score": self.exploration_metadata["confidence_score"],
            "artifact_slots": len(self.compiler.artifact_slots),
        }
    
    def get_working_set_rules(self) -> WorkingSetRules:
        """Get current Working Set rules."""
        return self.working_set_rules
    
    def get_exploration_strategy(self) -> ExplorationStrategy:
        """Get current exploration strategy."""
        return self.exploration_strategy
