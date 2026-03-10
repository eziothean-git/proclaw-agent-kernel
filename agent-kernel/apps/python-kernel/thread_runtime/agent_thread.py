"""
Agent Thread - Execution-level atomic Agent with Event Log + Working Set architecture.

This is the refactored Agent Thread that:
- Uses Event Log instead of conversation history
- Builds Working Sets via rule-driven WorkingSetBuilder
- Parses output via AgentOutputParser
- Executes via RequestExecutionCoordinator
- Implements SEE-ACT-UPDATE loop

Phase-aware: Supports Explore → Execute → Complete transitions.
"""
import os
import uuid
from datetime import datetime
from typing import Any

import structlog

from executors_client.coordinator_interface import get_execution_coordinator
from llm_client import get_llm_client, LLMClient
from schemas.models import AgentOutput, CompiledContext, TaskSnapshot
from skills.agentic_os_interface import get_os_interface_skill
from telemetry import emit_telemetry
from thread_runtime.event_log import EventLogManager
from thread_runtime.models import (
    ArtifactSlot,
    EventType,
    ExecutionRequest,
    IntentType,
    Phase,
    RequestType,
    SystemMessage,
    WorkingSet,
)
from thread_runtime.output_parser import get_output_parser
from thread_runtime.working_set_builder import WorkingSetBuilder

logger = structlog.get_logger()


class AgentThread:
    """
    Atomic Agent Thread with Event Log + Working Set architecture.
    
    Key characteristics:
    - Rule-driven working set updates (not semantic context editing)
    - SEE-ACT-UPDATE loop
    - Phase-based execution (Explore → Execute → Complete)
    - Observable state via full Event Log export
    """
    
    def __init__(
        self,
        task: TaskSnapshot,
        compiled_context: CompiledContext,
        coordinator: Any | None = None,
        ws_builder: WorkingSetBuilder | None = None,
    ):
        self.task = task
        self.compiled_context = compiled_context
        self.thread_id = f"thread_{uuid.uuid4().hex[:8]}"
        
        # Core components
        self.coordinator = coordinator or get_execution_coordinator()
        self.ws_builder = ws_builder or WorkingSetBuilder()
        self.parser = get_output_parser()
        
        # Runtime state
        self.event_log = EventLogManager(task.id)
        self.artifact_slots: dict[str, ArtifactSlot] = {}
        self.immutable_input = self._build_immutable_input(compiled_context)
        
        # Execution state
        self.current_phase = Phase.EXPLORE
        self.step_count = 0
        self.max_steps = self._parse_max_steps(compiled_context.constraints)
        self.is_paused = False
        self.pause_reason: str | None = None
        
        # Setup logger first (before any operations that might need it)
        self.logger = logger.bind(
            component="AgentThread",
            thread_id=self.thread_id,
            task_id=task.id,
        )

        # Initialize LLM client
        self.agent = self._create_agent()

        # Register with OS interface for monitoring/control
        self._register_with_os_interface()

        self.logger.info(
            "Agent Thread initialized",
            phase=self.current_phase.value,
        )
    
    def _parse_max_steps(self, constraints: list[str]) -> int:
        """Parse max_steps from constraints list."""
        for constraint in constraints:
            if "max_steps:" in constraint:
                try:
                    return int(constraint.split(":")[1].strip())
                except (ValueError, IndexError):
                    pass
        return 50  # Default

    def _build_immutable_input(self, context: CompiledContext) -> dict[str, Any]:
        """Build immutable input bundle from compiled context."""
        return {
            "task_goal": context.task_goal,
            "constraints": context.constraints,
            "allowed_capabilities": context.allowed_capabilities,
            "forbidden_capabilities": context.forbidden_capabilities,
            "session_context": context.session_context,
        }
    
    def _create_agent(self):
        """Create LLM agent (for real mode)."""
        try:
            # Use unified LLM Client supporting OpenAI, Kimi, and custom providers
            client = get_llm_client()
            success = client.initialize(system_prompt=self._build_system_prompt())
            
            if success:
                self.logger.info(
                    "LLM client initialized",
                    provider=client.config.provider,
                    model=client.config.model,
                )
                return client
            else:
                self.logger.error("Failed to initialize LLM client, falling back to mock mode")
                return None
                
        except Exception as e:
            self.logger.warning("Failed to create LLM agent", error=str(e))
            return None
    
    def _build_system_prompt(self) -> str:
        """Build system prompt for LLM."""
        return f"""You are an Agent Thread executing a task.

Task: {self.compiled_context.task_goal}

You operate in a SEE-ACT-UPDATE loop with bounded context.
Your available information is limited to the Working Set provided each step.

## Phase-aware execution:
- EXPLORE: Gather information, understand the problem
- EXECUTE: Perform actions based on gathered context
- COMPLETE: Finalize and report results

## Output format (YAML):
```yaml
intent: tool_call | phase_transition | final_answer | clarification
reasoning: "Your reasoning here"

# For tool_call:
tool_calls:
  - skill: skill_name
    tool: tool_name
    parameters:
      key: value

# For phase_transition:
to_phase: execute | complete
reason: "Why transitioning"

# For final_answer:
answer: "Your final response"
success: true | false
```

## Guidelines:
1. Stay within allowed capabilities
2. Use structured output format
3. Request clarification if unclear
4. Transition phases when appropriate
5. Report success/failure clearly
"""
    
    def _register_with_os_interface(self) -> None:
        """Register this thread with OS interface for monitoring."""
        try:
            os_interface = get_os_interface_skill()
            os_interface.register_thread(
                thread_id=self.thread_id,
                session_id=self.task.session_id,
                task_id=self.task.id,
                thread_ref=self,
            )
        except Exception as e:
            self.logger.warning("Failed to register with OS interface", error=str(e))
    
    def _unregister_from_os_interface(self) -> None:
        """Unregister from OS interface."""
        try:
            os_interface = get_os_interface_skill()
            os_interface.unregister_thread(self.thread_id)
        except Exception:
            pass
    
    async def run(self) -> AgentOutput:
        """
        Main execution loop - SEE-ACT-UPDATE.
        
        Returns:
            AgentOutput with final result
        """
        import time
        thread_start_time = time.perf_counter()
        
        self.logger.info(
            "Starting agent thread execution",
            goal=self.compiled_context.task_goal,
        )
        
        # Telemetry: Thread execution started
        emit_telemetry(
            request_id=self.task.id,
            layer=6,
            layer_name="Agent Thread",
            component="AgentThread",
            operation="execution",
            status="start",
            message=f"Starting execution: {self.compiled_context.task_goal[:50]}...",
            session_id=self.task.session_id,
            phase=self.current_phase.value,
            step=self.step_count,
            total_steps=self.max_steps,
        )
        
        try:
            while self.step_count < self.max_steps:
                step_start_time = time.perf_counter()
                
                # Check if paused
                if self.is_paused:
                    await self._wait_for_resume()
                
                self.step_count += 1
                
                # Telemetry: Step started
                emit_telemetry(
                    request_id=self.task.id,
                    layer=6,
                    layer_name="Agent Thread",
                    component="AgentThread",
                    operation="step",
                    status="progress",
                    message=f"Step {self.step_count}/{self.max_steps} - Phase: {self.current_phase.value}",
                    session_id=self.task.session_id,
                    phase=self.current_phase.value,
                    step=self.step_count,
                    total_steps=self.max_steps,
                    progress_pct=int((self.step_count / self.max_steps) * 100),
                )
                
                # SEE: Build working set
                working_set = self._build_working_set()
                
                # ACT: Generate action
                raw_output = await self._generate_action(working_set)
                
                # Parse output
                parsed = self.parser.parse(raw_output, self.current_phase)
                
                # Handle different intents
                if parsed.intent_type == IntentType.FINAL_ANSWER:
                    return await self._handle_final_answer(parsed)
                
                elif parsed.intent_type == IntentType.TOOL_CALL:
                    await self._handle_tool_calls(parsed)
                
                elif parsed.intent_type == IntentType.PHASE_TRANSITION:
                    await self._handle_phase_transition(parsed)
                
                elif parsed.intent_type == IntentType.CLARIFICATION:
                    return await self._handle_clarification(parsed)
                
                elif parsed.intent_type == IntentType.ERROR:
                    return await self._handle_error(parsed)
                
                else:  # UNKNOWN
                    self.logger.warning(
                        "Unknown intent, continuing",
                        raw_output=raw_output[:200],
                    )
                    # Continue loop
            
            # Max steps reached
            elapsed_ms = int((time.perf_counter() - thread_start_time) * 1000)
            
            # Telemetry: Max steps reached
            emit_telemetry(
                request_id=self.task.id,
                layer=6,
                layer_name="Agent Thread",
                component="AgentThread",
                operation="execution",
                status="error",
                message="Maximum iterations reached without completion",
                session_id=self.task.session_id,
                phase=self.current_phase.value,
                step=self.step_count,
                total_steps=self.max_steps,
                elapsed_ms=elapsed_ms,
            )
            
            return AgentOutput(
                task_id=self.task.id,
                content="Maximum iterations reached without completion",
                success=False,
                error="Max iterations exceeded",
                observations=[],
            )
            
        except Exception as e:
            elapsed_ms = int((time.perf_counter() - thread_start_time) * 1000)
            
            # Telemetry: Execution failed
            emit_telemetry(
                request_id=self.task.id,
                layer=6,
                layer_name="Agent Thread",
                component="AgentThread",
                operation="execution",
                status="error",
                message=f"Execution failed: {str(e)}",
                session_id=self.task.session_id,
                phase=self.current_phase.value,
                step=self.step_count,
                total_steps=self.max_steps,
                elapsed_ms=elapsed_ms,
                details={"error": str(e)},
            )
            
            self.logger.error("Agent thread failed", error=str(e))
            return AgentOutput(
                task_id=self.task.id,
                content=f"Execution failed: {str(e)}",
                success=False,
                error=str(e),
                observations=[],
            )
        finally:
            self._unregister_from_os_interface()
    
    def _build_working_set(self) -> WorkingSet:
        """Build current working set using WorkingSetBuilder."""
        return self.ws_builder.build(
            task_id=self.task.id,
            task_goal=self.compiled_context.task_goal,
            event_log=self.event_log,
            artifact_slots=self.artifact_slots,
            immutable_input=self.immutable_input,
            current_phase=self.current_phase,
            step_number=self.step_count,
        )
    
    async def _generate_action(self, working_set: WorkingSet) -> str:
        """Generate action using LLM."""
        prompt = working_set.to_prompt()

        if self.agent is None:
            raise RuntimeError("LLM agent not initialized. Cannot generate action.")

        try:
            # Use LLMClient.generate() method
            result = await self.agent.generate(prompt)
            return result
        except Exception as e:
            self.logger.error("LLM call failed", error=str(e))
            raise
    
    async def _handle_tool_calls(self, parsed: Any) -> None:
        """Execute tool calls via coordinator."""
        for tool_call in parsed.tool_calls:
            import time
            tool_start_time = time.perf_counter()
            
            # Log tool call
            self.event_log.append_tool_call(
                actor=self.thread_id,
                phase=self.current_phase,
                skill_name=tool_call.skill_name,
                tool_name=tool_call.tool_name,
                parameters=tool_call.parameters,
            )
            
            # Telemetry: Tool call
            emit_telemetry(
                request_id=self.task.id,
                layer=6,
                layer_name="Agent Thread",
                component="AgentThread",
                operation="tool_call",
                status="progress",
                message=f"Calling {tool_call.skill_name}.{tool_call.tool_name}",
                session_id=self.task.session_id,
                phase=self.current_phase.value,
                step=self.step_count,
                total_steps=self.max_steps,
                details={
                    "skill_name": tool_call.skill_name,
                    "tool_name": tool_call.tool_name,
                    "parameters": tool_call.parameters,
                },
            )
            
            # Create execution request
            request = ExecutionRequest(
                request_id=f"exec_{uuid.uuid4().hex[:8]}",
                request_type=RequestType.SKILL_CALL,
                source=self.thread_id,
                target=tool_call.skill_name,
                action=tool_call.tool_name,
                parameters=tool_call.parameters,
                context={
                    "session_id": self.task.session_id,
                    "task_id": self.task.id,
                    "step": self.step_count,
                },
            )
            
            # Submit and execute
            ticket = await self.coordinator.submit(request)
            result = await self.coordinator.execute(ticket)
            
            tool_elapsed_ms = int((time.perf_counter() - tool_start_time) * 1000)
            
            # Log result
            self.event_log.append_tool_result(
                actor=self.thread_id,
                phase=self.current_phase,
                skill_name=tool_call.skill_name,
                tool_name=tool_call.tool_name,
                success=result.success,
                result=result.result,
                error=result.error,
            )
            
            # Telemetry: Tool result
            emit_telemetry(
                request_id=self.task.id,
                layer=6,
                layer_name="Agent Thread",
                component="AgentThread",
                operation="tool_result",
                status="progress" if result.success else "error",
                message=f"{'✓' if result.success else '✗'} {tool_call.skill_name}.{tool_call.tool_name}",
                session_id=self.task.session_id,
                phase=self.current_phase.value,
                step=self.step_count,
                total_steps=self.max_steps,
                elapsed_ms=tool_elapsed_ms,
                details={
                    "skill_name": tool_call.skill_name,
                    "tool_name": tool_call.tool_name,
                    "success": result.success,
                    "has_error": result.error is not None,
                },
            )
    
    async def _handle_phase_transition(self, parsed: Any) -> None:
        """Handle phase transition request."""
        if not parsed.phase_transition:
            self.logger.warning("Phase transition intent without transition data")
            return
        
        transition = parsed.phase_transition
        
        # Validate transition
        if transition.from_phase != self.current_phase:
            self.logger.warning(
                "Phase transition from wrong phase",
                expected=transition.from_phase.value,
                actual=self.current_phase.value,
            )
            return
        
        # Log transition
        self.event_log.append_phase_change(
            actor=self.thread_id,
            from_phase=transition.from_phase,
            to_phase=transition.to_phase,
            reason=transition.reason,
        )
        
        # Execute transition
        old_phase = self.current_phase
        self.current_phase = transition.to_phase
        
        self.logger.info(
            "Phase transition",
            from_phase=old_phase.value,
            to_phase=self.current_phase.value,
            reason=transition.reason,
        )
        
        # Telemetry: Phase transition
        emit_telemetry(
            request_id=self.task.id,
            layer=6,
            layer_name="Agent Thread",
            component="AgentThread",
            operation="phase_transition",
            status="progress",
            message=f"Phase transition: {old_phase.value} -> {self.current_phase.value}",
            session_id=self.task.session_id,
            phase=self.current_phase.value,
            step=self.step_count,
            total_steps=self.max_steps,
            details={
                "from_phase": old_phase.value,
                "to_phase": self.current_phase.value,
                "reason": transition.reason,
            },
        )
    
    async def _handle_final_answer(self, parsed: Any) -> AgentOutput:
        """Handle final answer."""
        import time
        answer = parsed.final_answer or parsed.raw_content
        
        self.logger.info(
            "Task completed",
            success=True,
            steps=self.step_count,
        )
        
        # Telemetry: Execution completed
        emit_telemetry(
            request_id=self.task.id,
            layer=6,
            layer_name="Agent Thread",
            component="AgentThread",
            operation="execution",
            status="complete",
            message="Task completed successfully",
            session_id=self.task.session_id,
            phase=self.current_phase.value,
            step=self.step_count,
            total_steps=self.max_steps,
        )
        
        return AgentOutput(
            task_id=self.task.id,
            content=answer,
            success=True,
            observations=self._collect_observations(),
        )
    
    async def _handle_clarification(self, parsed: Any) -> AgentOutput:
        """Handle clarification request."""
        question = parsed.clarification_request or "Clarification needed"
        
        return AgentOutput(
            task_id=self.task.id,
            content=question,
            success=False,
            error="Clarification requested",
            observations=self._collect_observations(),
        )
    
    async def _handle_error(self, parsed: Any) -> AgentOutput:
        """Handle error intent."""
        error_msg = parsed.error_message or "Unknown error"
        
        return AgentOutput(
            task_id=self.task.id,
            content=f"Error: {error_msg}",
            success=False,
            error=error_msg,
            observations=self._collect_observations(),
        )
    
    def _collect_observations(self) -> list[dict[str, Any]]:
        """Collect observations from event log."""
        observations = []
        for event in self.event_log.get_by_type(EventType.TOOL_RESULT):
            observations.append({
                "tool": event.content.get("tool"),
                "skill": event.content.get("skill"),
                "success": event.content.get("success"),
                "result": event.content.get("result"),
                "error": event.content.get("error"),
            })
        return observations
    
    # ========== Control Interface (for OS Interface) ==========
    
    async def _wait_for_resume(self) -> None:
        """Wait until resumed."""
        while self.is_paused:
            await asyncio.sleep(0.1)
    
    async def pause(self, reason: str = "") -> None:
        """Pause thread execution."""
        self.is_paused = True
        self.pause_reason = reason
        self.logger.info("Thread paused", reason=reason)
    
    async def resume(self) -> None:
        """Resume thread execution."""
        self.is_paused = False
        self.pause_reason = None
        self.logger.info("Thread resumed")
    
    async def apply_context_update(self, updates: dict[str, Any]) -> None:
        """Apply context updates from upper layer."""
        if "phase" in updates:
            new_phase = updates["phase"]
            if isinstance(new_phase, str):
                new_phase = Phase(new_phase)
            self.current_phase = new_phase
            self.logger.info("Phase updated via external request", phase=new_phase.value)
        
        if "max_steps" in updates:
            self.max_steps = updates["max_steps"]
        
        if "context_notes" in updates:
            # Add to next working set
            pass
    
    async def handle_system_message(self, message: SystemMessage) -> None:
        """Handle system message from OS interface."""
        self.logger.debug(
            "Received system message",
            msg_type=message.msg_type,
            source=message.source,
        )
        
        if message.msg_type == "command":
            cmd = message.content.get("command")
            if cmd == "pause":
                await self.pause(message.content.get("reason", ""))
            elif cmd == "resume":
                await self.resume()
            elif cmd == "update_context":
                await self.apply_context_update(message.content.get("updates", {}))
    
    def get_event_log_export(self) -> dict[str, Any]:
        """Export full event log for upper layer inspection."""
        return {
            "thread_id": self.thread_id,
            "task_id": self.task.id,
            "current_phase": self.current_phase.value,
            "step_count": self.step_count,
            "is_paused": self.is_paused,
            "event_log": self.event_log.export_for_debug(),
            "artifacts": {
                slot_id: {
                    "slot_type": slot.slot_type,
                    "priority": slot.priority,
                }
                for slot_id, slot in self.artifact_slots.items()
            },
        }


# Import asyncio for sleep
import asyncio
