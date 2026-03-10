"""
Process Context Compiler - Compiles execution context packages for tasks.
Determines what each task Agent can see and do.

This compiler uses ProcessContextCompilerAgent (a high-level agent) to actively
explore Runtime Memory and compile context for task execution.
"""
import asyncio
import structlog
from typing import Any

from schemas.models import IntermediateRepresentation, CompiledContext, TaskSnapshot
from context_compiler.compiler_agent import ProcessContextCompilerAgent

logger = structlog.get_logger()


def _run_async(coro):
    """Helper to run async code, handling both sync and async contexts."""
    try:
        loop = asyncio.get_running_loop()
        # We're in an async context, use create_task
        import concurrent.futures
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(asyncio.run, coro)
            return future.result()
    except RuntimeError:
        # No running loop, use asyncio.run
        return asyncio.run(coro)


class ProcessContextCompiler:
    """
    Compiles task-specific execution contexts using an intelligent Agent.
    
    This compiler creates a ProcessContextCompilerAgent that actively explores
    Runtime Memory to gather and compile the most relevant context for task
    execution. The agent can:
    
    - Read files from data/sessions/, data/tasks/, data/events/, data/snapshots/
    - Register discovered information as structured artifacts
    - Modify its own context assembly rules dynamically
    - Change exploration strategy based on findings
    - Signal when sufficient context has been gathered
    
    The agent operates in two phases:
    1. EXPLORE: Gather information from Runtime Memory
    2. EXECUTE: Compile gathered information into CompiledContext
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
        Compile context package for a specific task using ProcessContextCompilerAgent.
        
        Creates and runs a compiler agent that actively explores Runtime Memory
        to gather the most relevant context for the target task.
        
        Args:
            task_id: Unique task identifier
            process_definition: Process configuration from IR
            intermediate_repr: Full intermediate representation
            session_context: Session-level context
            task_snapshots: Previous task snapshots for context
            
        Returns:
            CompiledContext with gathered execution context
        """
        self.logger.info(
            "Compiling process context via Agent",
            task_id=task_id,
            process_name=process_definition.get("name", "unnamed"),
        )
        
        # Create compiler agent
        agent = ProcessContextCompilerAgent(
            target_task_id=task_id,
            process_definition=process_definition,
            intermediate_repr=intermediate_repr,
            session_context=session_context,
            task_snapshots=task_snapshots,
        )
        
        # Run agent (async)
        compiled = _run_async(agent.run())
        
        self.logger.info(
            "Context compiled successfully",
            task_id=task_id,
            compilation_steps=compiled.metadata.get("compilation_steps", 0),
            artifacts_gathered=compiled.metadata.get("artifacts_gathered", 0),
            memory_refs=len(compiled.memory_references),
        )
        
        return compiled


# Singleton instance
_process_compiler: ProcessContextCompiler | None = None


def get_process_compiler() -> ProcessContextCompiler:
    """Get or create singleton instance."""
    global _process_compiler
    if _process_compiler is None:
        _process_compiler = ProcessContextCompiler()
    return _process_compiler
