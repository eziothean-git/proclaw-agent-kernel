"""
Prime Compiler Skill - Read-only context gathering skill for Prime Context Compiler Agent.

This skill provides ONLY read operations for the Prime Context Compiler Agent
to gather context information. It explicitly does NOT provide any write
operations to ensure the "read-only" constraint is enforced.

Key characteristics:
- Register artifacts (in-memory only, not persistent)
- Mark exploration complete
- No write operations to filesystem or memory
- No context filtering that affects external state
"""
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any
from uuid import uuid4

import structlog

from thread_runtime.models import ArtifactSlot, Phase

if TYPE_CHECKING:
    from context_compiler.prime_compiler_agent import PrimeContextCompilerAgent

logger = structlog.get_logger()


@dataclass
class ExplorationMetadata:
    """Metadata tracking exploration progress."""
    files_read: list[dict[str, Any]] = field(default_factory=list)
    confidence_score: float = 0.0
    start_time: Any = field(default=None)
    strategy: str = "breadth_first"


class PrimeCompilerSkill:
    """
    Read-only context gathering skill for Prime Context Compiler.
    
    Provides capabilities for:
    - Registering discovered information as artifact slots
    - Tracking exploration progress
    - Marking exploration as complete
    
    Explicitly does NOT provide:
    - File write operations
    - Context state modifications
    - Working Set rule changes that affect external systems
    
    This skill is designed to be safe for use in the entry-layer
    Prime Context Compiler where we want minimal side effects.
    """
    
    def __init__(self, compiler_agent: "PrimeContextCompilerAgent"):
        """
        Initialize the skill.
        
        Args:
            compiler_agent: Reference to the compiler agent
        """
        self.compiler = compiler_agent
        self.logger = logger.bind(component="PrimeCompilerSkill")
        
        # Exploration tracking
        self.exploration_metadata = ExplorationMetadata()
        self.exploration_complete = False
    
    # ============================================================================
    # Artifact Registration (Read-only storage)
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
        
        This only stores in memory within the agent's artifact_slots dict.
        No external persistence - artifacts are included in the final patch.
        
        Args:
            slot_type: Type of artifact (e.g., session_summary, relevant_task)
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
            
            # Store in agent's artifact_slots (in-memory only)
            self.compiler.artifact_slots[slot_id] = artifact
            
            # Log to Event Log for audit
            self.compiler.event_log.append_artifact_update(
                actor=self.compiler.thread_id,
                phase=self.compiler.current_phase,
                slot_id=slot_id,
                slot_type=slot_type,
                operation="create",
            )
            
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
    
    async def get_artifact_slot(self, slot_id: str) -> dict:
        """
        Get an existing artifact slot.
        
        Args:
            slot_id: ID of the slot to retrieve
            
        Returns:
            Dict with slot content or error
        """
        try:
            if slot_id not in self.compiler.artifact_slots:
                return {
                    "success": False,
                    "error": f"Slot not found: {slot_id}",
                }
            
            slot = self.compiler.artifact_slots[slot_id]
            
            return {
                "success": True,
                "slot_id": slot_id,
                "slot_type": slot.slot_type,
                "content": slot.content,
                "priority": slot.priority,
                "created_at": slot.created_at.isoformat() if slot.created_at else None,
            }
        
        except Exception as e:
            self.logger.error("Failed to get artifact slot", error=str(e))
            return {
                "success": False,
                "error": f"Failed to get slot: {str(e)}",
            }
    
    # ============================================================================
    # Exploration Management
    # ============================================================================
    
    async def mark_exploration_complete(
        self,
        reason: str,
        confidence: float,
    ) -> dict:
        """
        Signal that exploration is complete.
        
        This sets a flag that causes the agent to exit the exploration loop.
        The agent then compiles the final Context Patch.
        
        Args:
            reason: Explanation of why exploration is complete
            confidence: Confidence score (0.0-1.0) in gathered context
            
        Returns:
            Dict with success status and summary
        """
        try:
            if confidence < 0.5:
                return {
                    "success": False,
                    "error": "Confidence too low to finalize exploration",
                    "suggestion": "Continue exploring or request clarification",
                    "current_confidence": confidence,
                }
            
            self.exploration_metadata.confidence_score = confidence
            self.exploration_complete = True
            
            # Log to Event Log
            self.compiler.event_log.append(
                event_type="observation",  # Using string to avoid import issues
                actor=self.compiler.thread_id,
                phase=self.compiler.current_phase,
                content={
                    "type": "exploration_complete",
                    "reason": reason,
                    "confidence": confidence,
                    "files_read_count": len(self.exploration_metadata.files_read),
                },
                metadata={"confidence": confidence},
            )
            
            self.logger.info(
                "Exploration marked complete",
                reason=reason,
                confidence=confidence,
                files_read=len(self.exploration_metadata.files_read),
            )
            
            return {
                "success": True,
                "phase_transition": "explore → compile",
                "reason": reason,
                "confidence": confidence,
                "exploration_summary": {
                    "files_read": self.exploration_metadata.files_read,
                    "artifacts_registered": len(self.compiler.artifact_slots),
                    "confidence": confidence,
                },
            }
        
        except Exception as e:
            self.logger.error("Failed to mark exploration complete", error=str(e))
            return {
                "success": False,
                "error": f"Failed to complete exploration: {str(e)}",
            }
    
    def record_file_read(self, file_path: str, content_summary: str | None = None) -> None:
        """
        Record that a file was read during exploration.
        
        This is for tracking/auditing purposes only - no actual file operation.
        
        Args:
            file_path: Path of the file that was read
            content_summary: Optional summary of content (first N chars)
        """
        self.exploration_metadata.files_read.append({
            "path": file_path,
            "summary": content_summary[:200] if content_summary else None,
        })
        
        self.logger.debug("Recorded file read", file_path=file_path)
    
    # ============================================================================
    # Query Methods (Read-only)
    # ============================================================================
    
    def get_exploration_summary(self) -> dict:
        """
        Get summary of exploration progress.
        
        Returns:
            Dict with exploration statistics
        """
        return {
            "files_read": len(self.exploration_metadata.files_read),
            "files_read_details": self.exploration_metadata.files_read,
            "artifacts_registered": len(self.compiler.artifact_slots),
            "confidence_score": self.exploration_metadata.confidence_score,
            "exploration_complete": self.exploration_complete,
            "strategy": self.exploration_metadata.strategy,
        }
    
    def get_all_artifacts(self) -> dict[str, Any]:
        """
        Get all registered artifacts.
        
        Returns:
            Dict mapping slot_id to artifact content
        """
        return {
            slot_id: {
                "slot_type": slot.slot_type,
                "content": slot.content,
                "priority": slot.priority,
            }
            for slot_id, slot in self.compiler.artifact_slots.items()
        }
    
    def get_artifacts_by_type(self, slot_type: str) -> list[dict]:
        """
        Get all artifacts of a specific type.
        
        Args:
            slot_type: Type of artifacts to retrieve
            
        Returns:
            List of matching artifacts
        """
        return [
            {
                "slot_id": slot_id,
                "content": slot.content,
                "priority": slot.priority,
            }
            for slot_id, slot in self.compiler.artifact_slots.items()
            if slot.slot_type == slot_type
        ]
    
    # ============================================================================
    # Utility Methods
    # ============================================================================
    
    def set_exploration_strategy(self, strategy: str) -> None:
        """
        Set exploration strategy (for informational purposes).
        
        This does not affect the actual exploration - it's for logging/auditing.
        
        Args:
            strategy: Strategy name (breadth_first, depth_first, goal_directed)
        """
        self.exploration_metadata.strategy = strategy
        self.logger.debug("Exploration strategy set", strategy=strategy)
    
    def is_exploration_complete(self) -> bool:
        """Check if exploration has been marked complete."""
        return self.exploration_complete
