"""
Local Skill Registry - Registry for local Python-based skills.

Manages registration and execution of skills running in the same process.
This allows direct skill invocation without HTTP overhead.
"""
from typing import Any, Callable
import structlog

logger = structlog.get_logger()


class LocalSkillRegistry:
    """
    Registry for local Python skills.
    
    Skills can be registered as:
    - Class instances with methods
    - Function dictionaries
    - Any callable that accepts (tool_name, parameters)
    """
    
    def __init__(self):
        self.logger = logger.bind(component="LocalSkillRegistry")
        self._skills: dict[str, Any] = {}  # skill_name -> skill_instance
        self._tool_schemas: dict[str, dict] = {}  # skill.tool -> schema
    
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
    ) -> dict[str, Any]:
        """
        Execute a tool on a registered skill.
        
        Args:
            skill_name: Name of the skill
            tool_name: Name of the tool to execute
            parameters: Tool parameters
            
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
        
        try:
            # Try different execution patterns
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


# Singleton instance
_local_registry: LocalSkillRegistry | None = None


def get_local_skill_registry() -> LocalSkillRegistry:
    """Get or create singleton instance."""
    global _local_registry
    if _local_registry is None:
        _local_registry = LocalSkillRegistry()
    return _local_registry


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
