"""
Process Context Compiler - Compiles execution context packages for tasks.
Determines what each task Agent can see and do.
"""
import structlog
from typing import Any

from schemas.models import IntermediateRepresentation, CompiledContext, TaskSnapshot

logger = structlog.get_logger()


class ProcessContextCompiler:
    """
    Compiles task-specific execution contexts.
    Governs information visibility for each task.
    """
    
    def __init__(self):
        self.logger = logger.bind(component="ProcessContextCompiler")
        
    def compile_task_context(
        self,
        task_id: str,
        process_definition: dict[str, Any],
        intermediate_repr: IntermediateRepresentation,
        session_context: dict[str, Any],
        task_snapshots: list[TaskSnapshot] | None = None
    ) -> CompiledContext:
        """
        Compile context package for a specific task.
        
        Args:
            task_id: Unique task identifier
            process_definition: Process configuration from IR
            intermediate_repr: Full intermediate representation
            session_context: Session-level context
            task_snapshots: Previous task snapshots for context
            
        Returns:
            Compiled context for task execution
        """
        self.logger.info(
            "Compiling process context",
            task_id=task_id,
            process_name=process_definition.get("name", "unnamed"),
        )
        
        # Extract capabilities
        allowed = process_definition.get("capabilities", [])
        
        # Determine constraints based on process type
        constraints = self._determine_constraints(
            process_definition,
            intermediate_repr
        )
        
        # Build forbidden capabilities list
        forbidden = self._determine_forbidden_capabilities(
            process_definition,
            intermediate_repr
        )
        
        # Get relevant memory references
        memory_refs = self._extract_memory_references(
            task_snapshots or [],
            process_definition
        )
        
        compiled = CompiledContext(
            task_id=task_id,
            session_context=session_context,
            task_goal=process_definition.get("goal", "Execute task"),
            constraints=constraints,
            allowed_capabilities=allowed,
            forbidden_capabilities=forbidden,
            memory_references=memory_refs,
        )
        
        self.logger.info(
            "Context compiled",
            task_id=task_id,
            allowed_caps=len(allowed),
            constraints=len(constraints),
        )
        
        return compiled
    
    def _determine_constraints(
        self,
        process_definition: dict[str, Any],
        intermediate_repr: IntermediateRepresentation
    ) -> list[str]:
        """Determine execution constraints for the process."""
        constraints = [
            "Operate within allowed capabilities only",
            "Report errors clearly and immediately",
            "Do not make assumptions about system state",
        ]
        
        # Add process-specific constraints
        if security_level := process_definition.get("security_level"):
            if security_level == "high":
                constraints.extend([
                    "Require explicit confirmation for destructive operations",
                    "Log all file system access",
                ])
        
        # Add constraints from IR
        if ir_constraints := intermediate_repr.context_hints.get("constraints"):
            if isinstance(ir_constraints, list):
                constraints.extend(ir_constraints)
        
        return constraints
    
    def _determine_forbidden_capabilities(
        self,
        process_definition: dict[str, Any],
        intermediate_repr: IntermediateRepresentation
    ) -> list[str]:
        """Determine explicitly forbidden capabilities."""
        forbidden = []
        
        # Get from process definition
        if explicit_forbidden := process_definition.get("forbidden_capabilities"):
            forbidden.extend(explicit_forbidden)
        
        # Get from context hints
        if hints_forbidden := intermediate_repr.context_hints.get("forbidden_capabilities"):
            if isinstance(hints_forbidden, list):
                forbidden.extend(hints_forbidden)
        
        return list(set(forbidden))  # Remove duplicates
    
    def _extract_memory_references(
        self,
        task_snapshots: list[TaskSnapshot],
        process_definition: dict[str, Any]
    ) -> list[str]:
        """Extract relevant memory references from previous tasks."""
        # TODO: Implement intelligent memory retrieval
        # For now, just return recent task IDs
        return [snapshot.id for snapshot in task_snapshots[-5:]]


# Singleton instance
_process_compiler: ProcessContextCompiler | None = None


def get_process_compiler() -> ProcessContextCompiler:
    """Get or create singleton instance."""
    global _process_compiler
    if _process_compiler is None:
        _process_compiler = ProcessContextCompiler()
    return _process_compiler
