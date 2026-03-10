"""
Local Skill Registry - Registry for local Python-based skills.

Manages registration and execution of skills running in the same process.
This allows direct skill invocation without HTTP overhead.

Features directory-level locking for cross-agent safety.
"""
from typing import Any, Callable
from pathlib import Path
import structlog

from executors_client.directory_lock_manager import get_directory_lock_manager

logger = structlog.get_logger()


class LocalSkillRegistry:
    """
    Registry for local Python skills.
    
    Skills can be registered as:
    - Class instances with methods
    - Function dictionaries
    - Any callable that accepts (tool_name, parameters)
    
    Features:
    - Directory-level locking for cross-agent safety
    - FIFO queue for concurrent access
    - Automatic timeout and cleanup
    - Complete audit trail
    """
    
    def __init__(self, lock_manager=None):
        self.logger = logger.bind(component="LocalSkillRegistry")
        self._skills: dict[str, Any] = {}  # skill_name -> skill_instance
        self._tool_schemas: dict[str, dict] = {}  # skill.tool -> schema
        self._lock_manager = lock_manager or get_directory_lock_manager()
        self._default_lock_timeout = 300.0  # 5 minutes
    
    def register(
        self,
        skill_name: str,
        skill_instance: Any,
        tool_schemas: dict[str, dict] | None = None,
    ) -> None:
        """
        Register a skill instance.
        
        Args:
            skill_name: Unique name for the skill
            skill_instance: The skill instance/class
            tool_schemas: Optional schema definitions for tools
        """
        self._skills[skill_name] = skill_instance
        
        if tool_schemas:
            for tool_name, schema in tool_schemas.items():
                self._tool_schemas[f"{skill_name}.{tool_name}"] = schema
        
        self.logger.info(
            "Skill registered",
            skill_name=skill_name,
            tool_count=len(tool_schemas) if tool_schemas else 0,
        )
    
    def unregister(self, skill_name: str) -> None:
        """Unregister a skill."""
        if skill_name in self._skills:
            del self._skills[skill_name]
            
            # Remove associated tool schemas
            prefix = f"{skill_name}."
            tools_to_remove = [
                key for key in self._tool_schemas.keys()
                if key.startswith(prefix)
            ]
            for key in tools_to_remove:
                del self._tool_schemas[key]
            
            self.logger.info("Skill unregistered", skill_name=skill_name)
    
    def get(self, skill_name: str) -> Any | None:
        """Get a skill instance by name."""
        return self._skills.get(skill_name)
    
    def list_available(self) -> list[str]:
        """List all registered skill names."""
        return list(self._skills.keys())
    
    def list_tools(self, skill_name: str) -> list[str]:
        """List available tools for a skill."""
        prefix = f"{skill_name}."
        return [
            key.replace(prefix, "")
            for key in self._tool_schemas.keys()
            if key.startswith(prefix)
        ]
    
    def has_skill(self, skill_name: str) -> bool:
        """Check if a skill is registered."""
        return skill_name in self._skills
    
    def has_tool(self, skill_name: str, tool_name: str) -> bool:
        """Check if a skill has a specific tool."""
        key = f"{skill_name}.{tool_name}"
        return key in self._tool_schemas or self._can_execute(skill_name, tool_name)
    
    async def execute(
        self,
        skill_name: str,
        tool_name: str,
        parameters: dict[str, Any],
        task_id: str = None,
        session_id: str = None,
        timeout_seconds: float = None,
    ) -> dict[str, Any]:
        """
        Execute a tool on a registered skill with directory-level locking.
        
        Args:
            skill_name: Name of the skill
            tool_name: Name of the tool to execute
            parameters: Tool parameters
            task_id: Task identifier for lock management
            session_id: Session identifier for lock management
            timeout_seconds: Lock acquisition timeout (default: 300s)
            
        Returns:
            Execution result dict with keys:
            - success: bool
            - result: Any (tool output)
            - error: str | None
        """
        skill = self._skills.get(skill_name)
        if not skill:
            return {
                "success": False,
                "result": None,
                "error": f"Skill '{skill_name}' not found in local registry",
            }
        
        # Extract paths that need locking
        paths_to_lock = self._extract_paths(skill_name, tool_name, parameters)
        
        if not paths_to_lock or not task_id:
            # No paths to lock or no task_id, execute without locking
            return await self._execute_with_error_handling(skill, skill_name, tool_name, parameters)
        
        # Sort paths to avoid deadlocks (consistent ordering)
        sorted_paths = sorted(set(paths_to_lock))
        timeout = timeout_seconds or self._default_lock_timeout
        acquired_paths = []
        
        try:
            # Acquire all directory locks
            for path in sorted_paths:
                success = await self._lock_manager.acquire_lock(
                    directory_path=path,
                    task_id=task_id,
                    session_id=session_id or "unknown",
                    timeout_seconds=timeout,
                    lock_level="write",  # Default to write lock for safety
                )
                
                if not success:
                    # Failed to acquire lock, release any acquired locks
                    for acquired in acquired_paths[:]:
                        try:
                            await self._lock_manager.release_lock(acquired, task_id, session_id or "unknown")
                        except Exception:
                            pass  # Ignore release errors during cleanup
                        acquired_paths.remove(acquired)
                    
                    return {
                        "success": False,
                        "result": None,
                        "error": f"Failed to acquire lock for directory: {path}. "
                                 f"The directory is being used by another task.",
                    }
                
                acquired_paths.append(path)
            
            # Execute the operation with locks held
            return await self._execute_with_error_handling(skill, skill_name, tool_name, parameters)
            
        finally:
            # Always release locks, even on exception
            for path in acquired_paths:
                try:
                    await self._lock_manager.release_lock(path, task_id, session_id or "unknown")
                except Exception as e:
                    self.logger.error(
                        "Failed to release lock",
                        directory=path,
                        task_id=task_id,
                        error=str(e),
                    )
    
    async def _execute_with_error_handling(
        self,
        skill: Any,
        skill_name: str,
        tool_name: str,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        """Execute skill with error handling."""
        try:
            result = await self._try_execute(skill, tool_name, parameters)
            return {
                "success": True,
                "result": result,
                "error": None,
            }
        except Exception as e:
            self.logger.error(
                "Skill execution failed",
                skill_name=skill_name,
                tool_name=tool_name,
                error=str(e),
            )
            return {
                "success": False,
                "result": None,
                "error": f"Execution failed: {str(e)}",
            }
    
    def _extract_paths(self, skill_name: str, tool_name: str, parameters: dict[str, Any]) -> list[str]:
        """
        Extract directory paths that need to be locked from skill parameters.
        
        Args:
            skill_name: Name of the skill
            tool_name: Name of the tool
            parameters: Tool parameters
            
        Returns:
            List of directory paths to lock
        """
        paths = []
        
        if skill_name == "fs-skill":
            # File system skill - extract paths and get parent directories
            path_keys = ["path", "source", "target", "src", "dst", "directory", "dir"]
            for key in path_keys:
                if key in parameters and parameters[key]:
                    try:
                        path = Path(parameters[key]).resolve()
                        # Lock the parent directory
                        if path.is_file() or not path.exists():
                            paths.append(str(path.parent))
                        else:
                            paths.append(str(path))
                    except (ValueError, OSError):
                        pass
        
        elif skill_name == "shell-skill":
            # Shell commands - extract working directory if specified
            if "working_dir" in parameters:
                try:
                    path = Path(parameters["working_dir"]).resolve()
                    paths.append(str(path))
                except (ValueError, OSError):
                    pass
            # Also check if command contains paths (basic heuristic)
            if "command" in parameters:
                command = parameters["command"]
                # Extract potential paths from command (simplified)
                import re
                path_patterns = [
                    r'cd\s+(["\']?[^;|&<>"\']+["\']?)',
                    r'--directory[=\s]+(["\']?[^;|&<>"\']+["\']?)',
                ]
                for pattern in path_patterns:
                    matches = re.findall(pattern, command)
                    for match in matches:
                        try:
                            path = Path(match.strip('"\'')).resolve()
                            paths.append(str(path))
                        except (ValueError, OSError):
                            pass
        
        # Remove duplicates and normalize
        return list(set(paths))
    
    async def _try_execute(
        self,
        skill: Any,
        tool_name: str,
        parameters: dict[str, Any],
    ) -> Any:
        """
        Try to execute tool using various patterns.
        
        Patterns tried in order:
        1. Method call on skill instance
        2. Dict-style access (skill[tool_name])
        3. __call__ with tool_name parameter
        """
        # Pattern 1: Method on skill instance
        if hasattr(skill, tool_name):
            method = getattr(skill, tool_name)
            if callable(method):
                if asyncio.iscoroutinefunction(method):
                    return await method(**parameters)
                else:
                    return method(**parameters)
        
        # Pattern 2: call_tool method (MCP-style)
        if hasattr(skill, 'call_tool'):
            call_tool = skill.call_tool
            if asyncio.iscoroutinefunction(call_tool):
                return await call_tool(tool_name, parameters)
            else:
                return call_tool(tool_name, parameters)
        
        # Pattern 3: Dict-style skill
        if isinstance(skill, dict) and tool_name in skill:
            tool = skill[tool_name]
            if callable(tool):
                if asyncio.iscoroutinefunction(tool):
                    return await tool(**parameters)
                else:
                    return tool(**parameters)
        
        # Pattern 4: __call__ with tool_name
        if callable(skill) and not asyncio.iscoroutinefunction(skill):
            return skill(tool_name, **parameters)
        
        raise ValueError(f"Tool '{tool_name}' not found on skill")
    
    def _can_execute(self, skill_name: str, tool_name: str) -> bool:
        """Check if we can execute a tool (without actually executing)."""
        skill = self._skills.get(skill_name)
        if not skill:
            return False
        
        return (
            hasattr(skill, tool_name) or
            hasattr(skill, 'call_tool') or
            (isinstance(skill, dict) and tool_name in skill)
        )
    
    def get_tool_schema(self, skill_name: str, tool_name: str) -> dict | None:
        """Get schema for a tool."""
        key = f"{skill_name}.{tool_name}"
        return self._tool_schemas.get(key)


# Singleton instances
_local_registry: LocalSkillRegistry | None = None
_lock_manager_initialized: bool = False


def get_local_skill_registry() -> LocalSkillRegistry:
    """Get or create singleton instance."""
    global _local_registry, _lock_manager_initialized
    
    if _local_registry is None:
        # Initialize lock manager first
        lock_manager = get_directory_lock_manager()
        _local_registry = LocalSkillRegistry(lock_manager=lock_manager)
    
    return _local_registry


def start_lock_cleanup_task() -> None:
    """Start the background cleanup task for directory locks."""
    global _lock_manager_initialized
    
    if not _lock_manager_initialized:
        lock_manager = get_directory_lock_manager()
        import asyncio
        asyncio.create_task(lock_manager.start_cleanup_task())
        _lock_manager_initialized = True
        logger.info("Lock cleanup task started")


def register_skill(
    skill_name: str,
    skill_instance: Any,
    tool_schemas: dict[str, dict] | None = None,
) -> None:
    """Convenience function to register a skill."""
    registry = get_local_skill_registry()
    registry.register(skill_name, skill_instance, tool_schemas)


# Import asyncio for type checking
import asyncio
