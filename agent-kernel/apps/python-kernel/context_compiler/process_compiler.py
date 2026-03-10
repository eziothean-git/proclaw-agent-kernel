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


async def _run_async(coro):
    """Helper to run async code in async context."""
    return await coro


class ProcessContextCompiler:
    """
    Compiles task-specific execution contexts using an intelligent Agent.
    
    For simple tasks (conversation, direct response), returns lightweight context
    without starting an Agent. Only complex tasks (file operations, etc.) trigger
    the Agent-based exploration.
    
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
        
    async def compile_task_context(
        self,
        task_id: str,
        process_definition: dict[str, Any],
        intermediate_repr: IntermediateRepresentation,
        session_context: dict[str, Any],
        task_snapshots: list[TaskSnapshot] | None = None
    ) -> CompiledContext:
        """
        Compile context package for a specific task.
        
        For simple tasks (conversation, no capabilities), returns lightweight context
        immediately without Agent exploration. Complex tasks use Agent-based compilation.
        
        Args:
            task_id: Unique task identifier
            process_definition: Process configuration from IR
            intermediate_repr: Full intermediate representation
            session_context: Session-level context
            task_snapshots: Previous task snapshots for context
            
        Returns:
            CompiledContext with gathered execution context
        """
        process_name = process_definition.get("name", "unnamed")
        capabilities = process_definition.get("capabilities", [])
        goal = process_definition.get("goal", "")
        
        # FAST PATH: Simple conversation/response tasks don't need Agent exploration
        if not capabilities and ("respond" in process_name or "conversation" in process_name or "greeting" in goal.lower()):
            self.logger.info(
                "Fast path for simple task - no Agent needed",
                task_id=task_id,
                process_name=process_name,
                reason="simple_conversation_no_capabilities"
            )
            
            return CompiledContext(
                task_id=task_id,
                system_message="You are a helpful AI assistant. Respond directly to the user.",
                working_context={
                    "task_type": "conversation",
                    "goal": goal,
                    "requires_exploration": False,
                },
                tools_available=[],
                artifacts=[],
                memory_references=[],
                metadata={
                    "compiled_at": asyncio.get_event_loop().time(),
                    "compilation_steps": 0,
                    "artifacts_gathered": 0,
                    "fast_path": True,
                }
            )
        
        # SLOW PATH: Complex tasks need Agent exploration
        self.logger.info(
            "Compiling process context via Agent",
            task_id=task_id,
            process_name=process_name,
            capabilities=capabilities,
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
        compiled = await agent.run()

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
