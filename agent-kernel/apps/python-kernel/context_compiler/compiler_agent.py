"""
Process Context Compiler Agent - High-level agent for gathering and compiling execution context.

This agent extends AgentThread to actively explore Runtime Memory and compile
context for task execution. It uses the same Event Log + Working Set architecture
but with additional capabilities:

1. Dynamic exploration of Runtime Memory (via fs-skill)
2. Context reorganization via context-compiler-skill
3. Phase-based execution: EXPLORE → EXECUTE → COMPLETE
4. Output: CompiledContext (not AgentOutput)

Key Design Principles:
- Inherits AgentThread's SEE-ACT-UPDATE loop
- Exposes special skills for context manipulation
- Can modify its own Working Set rules dynamically
- Gathers information in EXPLORE phase, compiles in EXECUTE phase
"""
import os
import uuid
from datetime import datetime
from typing import Any

import structlog

from executors_client.coordinator_interface import get_execution_coordinator
from schemas.models import AgentOutput, CompiledContext, TaskSnapshot
from thread_runtime.agent_thread import AgentThread
from thread_runtime.models import ArtifactSlot, Phase
from thread_runtime.working_set_builder import WorkingSetBuilder

from context_compiler.compiler_skill import ContextCompilerSkill

logger = structlog.get_logger()


class ProcessContextCompilerAgent(AgentThread):
    """
    High-level Agent for compiling execution context.
    
    This agent actively explores Runtime Memory to gather information
    and compile a complete execution context for the target task.
    
    Capabilities:
    - Read files from data/sessions/, data/tasks/, data/events/, data/snapshots/
    - Register discovered information as Artifact Slots
    - Modify Working Set building rules dynamically
    - Change exploration strategy based on findings
    - Filter and reorganize context
    - Signal when exploration is complete
    
    Output:
        CompiledContext - structured context package for task execution
    """
    
    def __init__(
        self,
        target_task_id: str,
        process_definition: dict[str, Any],
        intermediate_repr: Any,
        session_context: dict[str, Any],
        task_snapshots: list[TaskSnapshot] | None = None,
    ):
        """
        Initialize Process Context Compiler Agent.
        
        Args:
            target_task_id: The actual task ID we're compiling context for
            process_definition: Process configuration from IR
            intermediate_repr: Full intermediate representation
            session_context: Session-level context
            task_snapshots: Previous task snapshots for reference
        """
        # Store compilation parameters
        self.target_task_id = target_task_id
        self.process_definition = process_definition
        self.intermediate_repr = intermediate_repr
        self.task_snapshots = task_snapshots or []
        
        # Create a "meta-task" for the compiler itself
        compiler_task = TaskSnapshot(
            id=f"compiler_{target_task_id}_{uuid.uuid4().hex[:8]}",
            session_id=session_context.get("session_id", "unknown"),
            process_id="context_compiler",
            goal=f"Compile execution context for task: {process_definition.get('goal', 'unknown')}",
            allowed_capabilities=["fs-skill", "context-compiler-skill"],
        )
        
        # Create initial empty CompiledContext (will be filled during execution)
        initial_compiled_context = CompiledContext(
            task_id=target_task_id,
            session_context=session_context,
            task_goal=process_definition.get("goal", "Execute task"),
            constraints=["explore_only", "read_only", "compile_context"],
            allowed_capabilities=process_definition.get("capabilities", []),
            forbidden_capabilities=process_definition.get("forbidden_capabilities", []),
            memory_references=[],
        )
        
        # Initialize parent AgentThread
        super().__init__(
            task=compiler_task,
            compiled_context=initial_compiled_context,
            coordinator=get_execution_coordinator(),
            ws_builder=WorkingSetBuilder(),
        )
        
        # Compiler-specific state
        self.collected_info: dict[str, Any] = {}
        self.exploration_complete = False
        self.compilation_result: CompiledContext | None = None
        
        # Initialize and register context-compiler-skill
        self.compiler_skill = ContextCompilerSkill(self)
        self._register_compiler_skill()
        
        self.logger.info(
            "Process Context Compiler Agent initialized",
            target_task_id=target_task_id,
            process_name=process_definition.get("name", "unnamed"),
        )
    
    def _register_compiler_skill(self) -> None:
        """Register context-compiler-skill with the coordinator."""
        try:
            # Import here to avoid circular import
            from skills.skill_adapters import ContextCompilerSkillAdapter
            
            adapter = ContextCompilerSkillAdapter()
            adapter.attach_compiler_agent(self)
            
            # Register with coordinator
            if hasattr(self.coordinator, 'register_local_skill'):
                self.coordinator.register_local_skill("context-compiler-skill", adapter)
                self.logger.info("Registered context-compiler-skill with coordinator")
            else:
                self.logger.warning("Coordinator does not support skill registration")
        except Exception as e:
            self.logger.error("Failed to register context-compiler-skill", error=str(e))
    
    def _build_system_prompt(self) -> str:
        """Build system prompt for the compiler agent."""
        return f"""You are a Process Context Compiler Agent. Your mission is to gather and 
compile execution context for a task by exploring Runtime Memory.

## Your Goal

Compile complete execution context for task:
{self.process_definition.get('goal', 'unknown')}

## Your Capabilities (via tool calls)

You have access to these skills:

1. **fs-skill** - Read files from Runtime Memory
   - list_directory: List directory contents
   - read_file: Read file contents

2. **context-compiler-skill** - Dynamic context management (YOUR SUPERPOWER)
   - update_working_set_rules: Modify how context is assembled
   - set_exploration_strategy: Change exploration approach  
   - mark_exploration_complete: Signal when you have enough context
   - register_artifact_slot: Store discovered information
   - update_artifact_slot: Update existing artifact
   - filter_context: Actively include/exclude information

## Exploration Strategy

You operate in EXPLORE phase initially. Your job is to:

1. **Explore Runtime Memory**:
   - Read session files: data/sessions/{{session_id}}.json
   - Read task files: data/tasks/*.json
   - Read event logs: data/events/{{session_id}}.jsonl
   - Read snapshots: data/snapshots/*.json

2. **Gather Key Information**:
   - Task goal and requirements
   - Session history and context
   - Previous related task outputs
   - Relevant events and observations
   - Available skills and constraints

3. **Use Your Powers**:
   - Register findings as artifact slots (e.g., "session_summary", "relevant_tasks")
   - Adjust exploration strategy if needed (breadth_first → depth_first → goal_directed)
   - Filter context to focus on relevant information
   - Modify Working Set rules to include more/less context

4. **Signal Completion**:
   - Call mark_exploration_complete when you have sufficient context
   - Provide confidence score (0.0-1.0)
   - Explain why exploration is complete

## Output Format

```yaml
intent: tool_call | phase_transition | final_answer
reasoning: "Your reasoning"

# For tool_call:
tool_calls:
  - skill: fs-skill | context-compiler-skill
    tool: <tool_name>
    parameters:
      key: value

# For phase_transition:
to_phase: execute | complete
reason: "Why transitioning"

# For final_answer:
answer: "Your final response"
success: true | false
```

## Guidelines

1. **Start with Predefined Paths**: Follow suggested exploration paths, but feel free to deviate based on findings
2. **Register Structured Findings**: Use register_artifact_slot to store important discoveries
3. **Adjust Dynamically**: Change strategy or rules based on what you find
4. **Know When to Stop**: Call mark_exploration_complete when you have enough context (confidence >= 0.7)
5. **Stay Within Constraints**: Only read files, don't modify or execute

## Current Session

Session ID: {self.task.session_id}
Target Task ID: {self.target_task_id}
Phase: {self.current_phase.value}

Begin exploration!
"""
    
    async def run(self) -> CompiledContext:
        """
        Main execution loop - overrides AgentThread.run().
        
        Returns:
            CompiledContext with compiled execution context
        """
        self.logger.info(
            "Starting context compilation",
            target_task_id=self.target_task_id,
            goal=self.process_definition.get("goal"),
        )
        
        try:
            # Phase 1: EXPLORE - Gather information
            while self.current_phase == Phase.EXPLORE and self.step_count < self.max_steps:
                if self.is_paused:
                    await self._wait_for_resume()
                
                self.step_count += 1
                
                # SEE: Build working set
                working_set = self._build_working_set()
                
                # ACT: Generate exploration action
                raw_output = await self._generate_action(working_set)
                
                # Parse output
                from thread_runtime.output_parser import get_output_parser
                parser = get_output_parser()
                parsed = parser.parse(raw_output, self.current_phase)
                
                # Handle different intents
                if parsed.intent_type.value == "tool_call":
                    await self._handle_tool_calls(parsed)
                elif parsed.intent_type.value == "final_answer":
                    # Treat as exploration complete signal
                    await self._transition_to_execute("Agent signaled completion")
                elif parsed.intent_type.value == "phase_transition":
                    await self._handle_phase_transition(parsed)
                elif parsed.intent_type.value == "error":
                    self.logger.error("Exploration error", error=parsed.error_message)
                    break
                
                # Check if exploration was marked complete
                if self.exploration_complete:
                    break
            
            # Phase 2: EXECUTE - Compile context
            if self.current_phase == Phase.EXECUTE or self.exploration_complete:
                self.compilation_result = await self._compile_context()
                return self.compilation_result
            
            # If we exited the loop without compiling, create minimal context
            self.logger.warning("Exploration ended without explicit completion")
            return await self._compile_context(minimal=True)
            
        except Exception as e:
            self.logger.error("Context compilation failed", error=str(e))
            # Return minimal context on error
            return await self._compile_context(minimal=True)
    
    async def _transition_to_execute(self, reason: str) -> None:
        """Transition from EXPLORE to EXECUTE phase."""
        old_phase = self.current_phase
        self.current_phase = Phase.EXECUTE
        self.exploration_complete = True
        
        # Log phase change
        self.event_log.append_phase_change(
            actor=self.thread_id,
            from_phase=old_phase,
            to_phase=Phase.EXECUTE,
            reason=reason,
        )
        
        self.logger.info(
            "Phase transition",
            from_phase=old_phase.value,
            to_phase=Phase.EXECUTE.value,
            reason=reason,
        )
    
    async def _compile_context(self, minimal: bool = False) -> CompiledContext:
        """
        Compile the final CompiledContext from gathered information.
        
        Args:
            minimal: If True, create minimal context even with limited info
            
        Returns:
            CompiledContext with all gathered information
        """
        self.logger.info("Compiling final context", minimal=minimal)
        
        # Gather information from artifact slots
        memory_references = []
        relevant_tasks = []
        session_summary = {}
        
        for slot_id, slot in self.artifact_slots.items():
            if slot.slot_type == "memory_reference":
                memory_references.append(slot.content)
            elif slot.slot_type == "relevant_task":
                relevant_tasks.append(slot.content)
            elif slot.slot_type == "session_summary":
                session_summary = slot.content
        
        # If no artifacts registered but we have task snapshots, use them
        if not memory_references and self.task_snapshots:
            memory_references = [snapshot.id for snapshot in self.task_snapshots[-5:]]
        
        # Determine capabilities from process definition
        allowed_capabilities = self.process_definition.get("capabilities", [])
        forbidden_capabilities = self.process_definition.get("forbidden_capabilities", [])
        
        # Build constraints list
        constraints = [
            "Operate within allowed capabilities only",
            "Report errors clearly and immediately",
            "Do not make assumptions about system state",
        ]
        
        # Add security constraints
        if self.process_definition.get("security_level") == "high":
            constraints.extend([
                "Require explicit confirmation for destructive operations",
                "Log all file system access",
            ])
        
        # Add IR context hints constraints
        if ir_constraints := getattr(self.intermediate_repr, 'context_hints', {}).get("constraints"):
            if isinstance(ir_constraints, list):
                constraints.extend(ir_constraints)
        
        # Create compiled context
        compiled = CompiledContext(
            task_id=self.target_task_id,
            session_context=self.compiled_context.session_context,
            task_goal=self.process_definition.get("goal", "Execute task"),
            constraints=constraints,
            allowed_capabilities=allowed_capabilities,
            forbidden_capabilities=forbidden_capabilities,
            memory_references=memory_references,
        )
        
        # Add compilation metadata
        compiled.metadata = {
            "compilation_steps": self.step_count,
            "artifacts_gathered": len(self.artifact_slots),
            "exploration_strategy": self.compiler_skill.exploration_strategy.strategy_type if self.compiler_skill else "unknown",
            "files_read": len(self.compiler_skill.exploration_metadata["files_read"]) if self.compiler_skill else 0,
        }
        
        self.logger.info(
            "Context compilation complete",
            task_id=self.target_task_id,
            artifacts=len(self.artifact_slots),
            memory_refs=len(memory_references),
        )
        
        return compiled
    
    async def _handle_file_read_result(self, file_path: str, content: str) -> None:
        """
        Process the result of reading a file during exploration.
        
        Args:
            file_path: Path of the file that was read
            content: Content of the file
        """
        # Record file read
        self.compiler_skill.record_file_read(file_path, content[:200])
        
        # Store in collected info
        self.collected_info[file_path] = content
        
        # Extract and register structured information
        await self._extract_and_register_info(file_path, content)
        
        self.logger.debug("Processed file read", file_path=file_path)
    
    async def _extract_and_register_info(self, file_path: str, content: str) -> None:
        """
        Extract structured information from file content and register as artifact.
        
        This is where the compiler "understands" what it has read.
        """
        try:
            import json
            
            # Try to parse as JSON
            if file_path.endswith('.json'):
                data = json.loads(content)
                
                # Determine file type and extract relevant info
                if 'sessions' in file_path:
                    # Session file
                    await self.compiler_skill.register_artifact_slot(
                        slot_type="session_summary",
                        content={
                            "session_id": data.get("id"),
                            "status": data.get("status"),
                            "task_count": data.get("task_count"),
                            "metadata": data.get("metadata", {}),
                        },
                        priority=8,
                    )
                
                elif 'tasks' in file_path:
                    # Task file
                    await self.compiler_skill.register_artifact_slot(
                        slot_type="relevant_task",
                        content={
                            "task_id": data.get("id"),
                            "goal": data.get("goal"),
                            "status": data.get("status"),
                            "output": data.get("output"),
                        },
                        priority=7,
                    )
                    
                    # Also add to memory references
                    await self.compiler_skill.register_artifact_slot(
                        slot_type="memory_reference",
                        content=data.get("id"),
                        priority=5,
                    )
                
                elif 'snapshots' in file_path:
                    # Snapshot file
                    await self.compiler_skill.register_artifact_slot(
                        slot_type="task_snapshot",
                        content={
                            "snapshot_id": data.get("id"),
                            "task_id": data.get("task_id"),
                            "phase": data.get("phase"),
                        },
                        priority=6,
                    )
            
            elif file_path.endswith('.jsonl'):
                # Event log file
                events = []
                for line in content.strip().split('\n'):
                    if line:
                        try:
                            event = json.loads(line)
                            events.append(event)
                        except json.JSONDecodeError:
                            continue
                
                # Register recent events summary
                if events:
                    await self.compiler_skill.register_artifact_slot(
                        slot_type="recent_events",
                        content={
                            "event_count": len(events),
                            "latest_events": events[-5:],  # Last 5 events
                        },
                        priority=6,
                    )
        
        except Exception as e:
            self.logger.warning(
                "Failed to extract info from file",
                file_path=file_path,
                error=str(e),
            )
    
    def get_exploration_summary(self) -> dict[str, Any]:
        """Get summary of exploration progress."""
        return {
            "target_task_id": self.target_task_id,
            "steps_taken": self.step_count,
            "phase": self.current_phase.value,
            "artifacts_registered": len(self.artifact_slots),
            "files_read": len(self.collected_info),
            "exploration_complete": self.exploration_complete,
        }
