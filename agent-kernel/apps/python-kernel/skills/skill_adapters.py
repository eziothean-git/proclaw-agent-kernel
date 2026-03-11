"""
Skill Adapters - Adapt MCP-style skills for LocalSkillRegistry
"""
from typing import Any

from skills.fs_skill import FileSystemSkill
from skills.shell_skill import ShellSkill
from scheduled_dispatcher.skill import ScheduledRequestSkill


class FileSystemSkillAdapter:
    """Adapter to make FileSystemSkill work with LocalSkillRegistry"""
    
    def __init__(self, allowed_paths=None):
        self.skill = FileSystemSkill(allowed_paths)
    
    async def read_file(self, path: str):
        """Read file contents"""
        result = await self.skill._read_file(path)
        return {"success": True, "content": result[0].text if result else "", "error": None}
    
    async def write_file(self, path: str, content: str):
        """Write file contents"""
        result = await self.skill._write_file(path, content)
        return {"success": True, "result": result[0].text if result else "", "error": None}
    
    async def list_directory(self, path: str):
        """List directory contents"""
        result = await self.skill._list_directory(path)
        return {"success": True, "result": result[0].text if result else "", "error": None}


class ShellSkillAdapter:
    """Adapter to make ShellSkill work with LocalSkillRegistry"""

    def __init__(self):
        self.skill = ShellSkill()

    async def execute(self, command: str, timeout: int = 30, working_dir: str | None = None):
        """Execute shell command"""
        result = await self.skill._execute_command(command, timeout, working_dir)
        text = result[0].text if result else ""
        last_line = text.strip().rsplit("\n", 1)[-1].strip() if text.strip() else ""
        if not last_line.startswith("Exit code:"):
            # Unexpected output format from shell_skill; treat as error
            return {"success": False, "result": text, "error": "Unexpected shell output format"}
        success = last_line == "Exit code: 0"
        return {
            "success": success,
            "result": text,
            "error": None,
        }

class ScheduledRequestSkillAdapter:
    """Adapter to make ScheduledRequestSkill work with LocalSkillRegistry"""
    
    def __init__(self, base_path=None):
        """Initialize the adapter with optional base path for storage."""
        import os
        if base_path is None:
            base_path = os.getenv("DATA_PATH", "./data")
        self.skill = ScheduledRequestSkill()
    
    async def create_delayed_request(
        self,
        session_id: str,
        user_id: str,
        content: str,
        delay_seconds: int,
        is_recurring: bool = False,
        metadata: dict = None
    ):
        """Create a delayed scheduled request."""
        result = await self.skill.create_delayed_request(
            session_id=session_id,
            user_id=user_id,
            content=content,
            delay_seconds=delay_seconds,
            is_recurring=is_recurring,
            metadata=metadata or {}
        )
        return result
    
    async def create_cron_request(
        self,
        session_id: str,
        user_id: str,
        content: str,
        cron_expression: str,
        metadata: dict = None
    ):
        """Create a cron-based recurring request."""
        result = await self.skill.create_cron_request(
            session_id=session_id,
            user_id=user_id,
            content=content,
            cron_expression=cron_expression,
            metadata=metadata or {}
        )
        return result
    
    async def list_scheduled_requests(
        self,
        session_id: str = None,
        status: str = "pending",
        limit: int = 50
    ):
        """List scheduled requests with optional filtering."""
        result = await self.skill.list_scheduled_requests(
            session_id=session_id,
            status=status,
            limit=limit
        )
        return result
    
    async def get_scheduled_request(self, request_id: str):
        """Get details of a specific scheduled request."""
        result = await self.skill.get_scheduled_request(request_id=request_id)
        return result
    
    async def cancel_scheduled_request(self, request_id: str, reason: str = None):
        """Cancel a pending scheduled request."""
        result = await self.skill.cancel_scheduled_request(
            request_id=request_id,
            reason=reason
        )
        return result
    
    async def pause_scheduled_request(self, request_id: str, reason: str = None):
        """Pause a pending scheduled request."""
        result = await self.skill.pause_scheduled_request(
            request_id=request_id,
            reason=reason
        )
        return result
    
    async def resume_scheduled_request(self, request_id: str):
        """Resume a paused scheduled request."""
        result = await self.skill.resume_scheduled_request(request_id=request_id)
        return result
    
    async def get_statistics(self):
        """Get statistics about scheduled requests."""
        result = await self.skill.get_statistics()
        return result


class ContextCompilerSkillAdapter:
    """
    Adapter to make ContextCompilerSkill work with LocalSkillRegistry.
    
    This adapter wraps the ContextCompilerSkill and exposes its methods
    for the ProcessContextCompilerAgent to call via the coordinator.
    
    Note: This skill is ONLY registered for Process Context Compiler Agent
    and should not be exposed to regular Agent Threads.
    """
    
    def __init__(self, compiler_agent: Any = None):
        """
        Initialize the adapter.
        
        Note: The actual skill instance is set later when the compiler agent
        is created. This is because the skill needs a reference to the agent.
        """
        self.skill = None
        self._pending_compiler_agent = compiler_agent
    
    def attach_compiler_agent(self, compiler_agent: Any) -> None:
        """
        Attach the compiler agent to this adapter.
        
        This must be called before any skill methods are invoked.
        """
        from context_compiler.compiler_skill import ContextCompilerSkill
        self.skill = ContextCompilerSkill(compiler_agent)
        self._pending_compiler_agent = None
    
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
        Dynamically modify Working Set building rules.
        
        Args:
            phase: The phase to modify rules for (explore/execute/complete)
            max_observations: Maximum number of observations to include
            artifact_priority_boost: List of artifact types to boost priority
            context_notes: Additional notes to add to context
        """
        if not self.skill:
            return {"success": False, "error": "Skill not initialized"}
        
        return await self.skill.update_working_set_rules(
            phase=phase,
            max_observations=max_observations,
            artifact_priority_boost=artifact_priority_boost,
            context_notes=context_notes,
        )
    
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
        
        Args:
            strategy: Strategy type (breadth_first | depth_first | goal_directed)
            focus_areas: Areas to focus exploration on
            priority_files: Specific files to prioritize reading
            max_steps: Maximum exploration steps allowed
        """
        if not self.skill:
            return {"success": False, "error": "Skill not initialized"}
        
        return await self.skill.set_exploration_strategy(
            strategy=strategy,
            focus_areas=focus_areas,
            priority_files=priority_files,
            max_steps=max_steps,
        )
    
    async def mark_exploration_complete(
        self,
        reason: str,
        confidence: float,
    ) -> dict:
        """
        Signal that exploration is complete and trigger phase transition.
        
        Args:
            reason: Explanation of why exploration is complete
            confidence: Confidence score (0.0-1.0) in gathered context
        """
        if not self.skill:
            return {"success": False, "error": "Skill not initialized"}
        
        return await self.skill.mark_exploration_complete(
            reason=reason,
            confidence=confidence,
        )
    
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
        
        Args:
            slot_type: Type of artifact (e.g., session_summary, task_output)
            content: The artifact content
            priority: Priority for Working Set selection (1-10)
            slot_id: Optional custom slot ID
        """
        if not self.skill:
            return {"success": False, "error": "Skill not initialized"}
        
        return await self.skill.register_artifact_slot(
            slot_type=slot_type,
            content=content,
            priority=priority,
            slot_id=slot_id,
        )
    
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
        """
        if not self.skill:
            return {"success": False, "error": "Skill not initialized"}
        
        return await self.skill.update_artifact_slot(
            slot_id=slot_id,
            content=content,
            priority=priority,
        )
    
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
        
        Args:
            observations_to_keep: Event IDs to force include
            observations_to_remove: Event IDs to exclude
            slots_to_activate: Slot IDs to force include
            slots_to_deactivate: Slot IDs to exclude
        """
        if not self.skill:
            return {"success": False, "error": "Skill not initialized"}
        
        return await self.skill.filter_context(
            observations_to_keep=observations_to_keep,
            observations_to_remove=observations_to_remove,
            slots_to_activate=slots_to_activate,
            slots_to_deactivate=slots_to_deactivate,
        )
    
    # ============================================================================
    # Utility Methods
    # ============================================================================
    
    async def get_exploration_summary(self) -> dict:
        """Get summary of exploration progress."""
        if not self.skill:
            return {"success": False, "error": "Skill not initialized"}
        
        return {
            "success": True,
            "summary": self.skill.get_exploration_summary(),
        }


class PrimeCompilerSkillAdapter:
    """
    Adapter to make PrimeCompilerSkill work with LocalSkillRegistry.
    
    This skill is ONLY exposed to PrimeContextCompilerAgent and provides
    read-only context gathering capabilities.
    
    Key differences from ContextCompilerSkill:
    - Read-only operations (no context filtering or rule modifications)
    - Simpler interface focused on gathering information
    - No write operations to avoid side effects in entry layer
    """
    
    def __init__(self, compiler_agent: Any = None):
        """
        Initialize the adapter.
        
        Args:
            compiler_agent: The PrimeContextCompilerAgent instance
        """
        self.skill = None
        self._pending_compiler_agent = compiler_agent
    
    def attach_compiler_agent(self, compiler_agent: Any) -> None:
        """
        Attach the compiler agent to this adapter.
        
        This must be called before any skill methods are invoked.
        """
        from context_compiler.prime_compiler_skill import PrimeCompilerSkill
        self.skill = PrimeCompilerSkill(compiler_agent)
        self._pending_compiler_agent = None
    
    async def register_artifact_slot(
        self,
        slot_type: str,
        content: Any,
        priority: int = 5,
        slot_id: str | None = None,
    ) -> dict:
        """
        Register discovered information as an Artifact Slot.
        
        Args:
            slot_type: Type of artifact (e.g., session_summary, task_output)
            content: The artifact content
            priority: Priority for Working Set selection (1-10)
            slot_id: Optional custom slot ID
        """
        if not self.skill:
            return {"success": False, "error": "Skill not initialized"}
        
        return await self.skill.register_artifact_slot(
            slot_type=slot_type,
            content=content,
            priority=priority,
            slot_id=slot_id,
        )
    
    async def get_artifact_slot(self, slot_id: str) -> dict:
        """
        Get an existing artifact slot.
        
        Args:
            slot_id: ID of the slot to retrieve
        """
        if not self.skill:
            return {"success": False, "error": "Skill not initialized"}
        
        return await self.skill.get_artifact_slot(slot_id)
    
    async def mark_exploration_complete(
        self,
        reason: str,
        confidence: float,
    ) -> dict:
        """
        Signal that exploration is complete.
        
        Args:
            reason: Explanation of why exploration is complete
            confidence: Confidence score (0.0-1.0)
        """
        if not self.skill:
            return {"success": False, "error": "Skill not initialized"}
        
        return await self.skill.mark_exploration_complete(
            reason=reason,
            confidence=confidence,
        )
    
    async def get_exploration_summary(self) -> dict:
        """Get summary of exploration progress."""
        if not self.skill:
            return {"success": False, "error": "Skill not initialized"}
        
        return {
            "success": True,
            "summary": self.skill.get_exploration_summary(),
        }
    
    async def get_all_artifacts(self) -> dict:
        """Get all registered artifacts."""
        if not self.skill:
            return {"success": False, "error": "Skill not initialized"}
        
        return {
            "success": True,
            "artifacts": self.skill.get_all_artifacts(),
        }
    
    async def get_artifacts_by_type(self, slot_type: str) -> dict:
        """
        Get artifacts of a specific type.
        
        Args:
            slot_type: Type of artifacts to retrieve
        """
        if not self.skill:
            return {"success": False, "error": "Skill not initialized"}
        
        return {
            "success": True,
            "artifacts": self.skill.get_artifacts_by_type(slot_type),
        }
