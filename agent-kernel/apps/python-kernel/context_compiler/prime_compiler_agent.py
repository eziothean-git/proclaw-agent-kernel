"""
Prime Context Compiler Agent - Lightweight context gathering agent for Prime Personality.

This agent provides intelligent context gathering for the Master Context Compiler
with strict constraints:
- Read-only operations (fs-skill only)
- 3-5 step limit per compilation
- Outputs Context Patch (not full CompiledContext)
- Complete audit trail via PersistentEventLog

Key Design:
- Inherits AgentThread for SEE-ACT-UPDATE loop
- Uses PersistentEventLog for audit
- Saves Working Set snapshots each step
- Returns ContextPatch to be applied by MasterContextCompiler
"""
import asyncio
import json
import os
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog

from context_compiler.models import ContextPatch, WorkingSetSnapshot
from context_compiler.persistent_event_log import PersistentEventLog
from context_compiler.prime_compiler_skill import PrimeCompilerSkill
from executors_client.coordinator_interface import get_execution_coordinator
from schemas.models import CompiledContext, Request, Session, TaskSnapshot
from thread_runtime.agent_thread import AgentThread
from thread_runtime.models import ArtifactSlot, Phase
from thread_runtime.output_parser import get_output_parser
from thread_runtime.working_set_builder import WorkingSetBuilder

logger = structlog.get_logger()


class PrimeContextCompilerAgent(AgentThread):
    """
    Lightweight context gathering agent for Prime Context Compiler.
    
    Characteristics:
    - Read-only: Only fs-skill allowed
    - Step-limited: 3-5 steps maximum
    - Output: ContextPatch (not CompiledContext)
    - Audit: Full event log and Working Set snapshots
    
    Usage:
        agent = PrimeContextCompilerAgent(
            request_id="req_123",
            request=request,
            session=session,
            base_context={...},
            max_steps=3
        )
        patch = await agent.run()
    """
    
    def __init__(
        self,
        request_id: str,
        request: Request,
        session: Session,
        base_context: dict[str, Any],
        max_steps: int = 3,
    ):
        """
        Initialize Prime Context Compiler Agent.
        
        Args:
            request_id: Unique request identifier
            request: The user request
            session: Current session
            base_context: Base context from rule-based compilation
            max_steps: Maximum exploration steps (default 3)
        """
        # Store compilation parameters
        self.request_id = request_id
        self.request = request
        self.session = session
        self.base_context = base_context
        self.max_steps_limit = max_steps
        
        # Create compiler task with read-only constraints
        compiler_task = TaskSnapshot(
            id=f"prime_compiler_{request_id}_{uuid.uuid4().hex[:8]}",
            session_id=session.id,
            process_id="prime_context_compiler",
            goal=f"Gather context for request: {request.message[:100]}",
            allowed_capabilities=["fs-skill", "prime-compiler-skill"],
            constraints=[
                f"max_steps: {max_steps}",
                "read_only",
                "no_write_operations",
            ],
        )
        
        # Create initial compiled context (minimal, will be patched)
        initial_context = CompiledContext(
            task_id=compiler_task.id,
            session_context={
                "session_id": session.id,
                "user_id": request.user_id,
                "request_id": request_id,
            },
            task_goal="Gather context for Prime Personality",
            constraints=["read_only", "explore_only"],
            allowed_capabilities=compiler_task.allowed_capabilities,
            forbidden_capabilities=["write", "delete", "execute"],
            memory_references=[],
        )
        
        # Initialize parent AgentThread
        super().__init__(
            task=compiler_task,
            compiled_context=initial_context,
            coordinator=get_execution_coordinator(),
            ws_builder=WorkingSetBuilder(),
        )
        
        # Override max_steps from parent
        self.max_steps = max_steps
        
        # Setup storage paths
        self.storage_dir = Path(f"data/compilation/prime/{request_id}")
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        
        # Initialize persistent event log
        self.event_log = PersistentEventLog(
            log_id=f"prime_compiler_{request_id}",
            storage_path=str(self.storage_dir / "events.jsonl"),
        )
        
        # Working Set history for audit
        self.ws_history: list[WorkingSetSnapshot] = []
        
        # Compiler skill (read-only)
        self.compiler_skill = PrimeCompilerSkill(self)
        self._register_compiler_skill()
        
        # Update logger with context
        self.logger = logger.bind(
            component="PrimeContextCompilerAgent",
            thread_id=self.thread_id,
            request_id=request_id,
            max_steps=max_steps,
        )
        
        self.logger.info(
            "Prime Context Compiler Agent initialized",
            session_id=session.id,
            goal=compiler_task.goal,
        )
    
    def _register_compiler_skill(self) -> None:
        """Register prime-compiler-skill with coordinator."""
        try:
            from skills.skill_adapters import PrimeCompilerSkillAdapter
            
            adapter = PrimeCompilerSkillAdapter()
            adapter.attach_compiler_agent(self)
            
            if hasattr(self.coordinator, 'register_local_skill'):
                self.coordinator.register_local_skill("prime-compiler-skill", adapter)
                self.logger.info("Registered prime-compiler-skill")
            else:
                self.logger.warning("Coordinator does not support skill registration")
        
        except Exception as e:
            self.logger.error("Failed to register prime-compiler-skill", error=str(e))
    
    def _build_system_prompt(self) -> str:
        """Build system prompt for the compiler agent."""
        return f"""You are a Prime Context Compiler Agent. Your mission is to gather additional context for the Prime Personality to better understand and process the user's request.

## Your Goal

Gather relevant context for the request: "{self.request.message}"

## Your Constraints (IMPORTANT)

1. **READ-ONLY**: You can only read files, never write or modify anything
2. **STEP LIMITED**: Maximum {self.max_steps} steps - use them wisely
3. **CONTEXT PATCH**: Your output will be used to enhance the base context, not replace it

## Your Capabilities

You have access to these skills:

1. **fs-skill** - Read files from Runtime Memory
   - list_directory: List directory contents
   - read_file: Read file contents

2. **prime-compiler-skill** - Context gathering
   - register_artifact_slot: Store discovered information
   - mark_exploration_complete: Signal when you have enough context
   - get_exploration_summary: Check exploration progress

## Exploration Strategy

Since you only have {self.max_steps} steps:

1. **Start with high-value files**: session history, recent tasks, user preferences
2. **Register findings immediately**: Use register_artifact_slot for important discoveries
3. **Know when to stop**: Call mark_exploration_complete when you have sufficient context (confidence >= 0.7)
4. **Be selective**: Don't waste steps on low-value information

## Suggested Exploration Path

1. Check session history: data/sessions/{self.session.id}.json
2. Look for relevant previous tasks: data/tasks/*.json
3. Check recent events: data/events/{self.session.id}.jsonl
4. Review any user preferences or patterns

## Output Format

```yaml
intent: tool_call | final_answer
reasoning: "Your reasoning"

# For tool_call:
tool_calls:
  - skill: fs-skill | prime-compiler-skill
    tool: <tool_name>
    parameters:
      key: value

# For final_answer:
answer: "Summary of gathered context"
confidence: 0.0-1.0
reason: "Why exploration is complete"
```

## Guidelines

1. **Be focused**: Only gather information relevant to this specific request
2. **Register artifacts**: Use register_artifact_slot for structured findings
3. **Track confidence**: Call mark_exploration_complete when confidence >= 0.7
4. **Stay within limits**: You have exactly {self.max_steps} steps - use them efficiently
5. **Read-only only**: Never attempt to write, delete, or execute anything

## Current Context

Session ID: {self.session.id}
User ID: {self.request.user_id}
Step: {{current_step}} / {self.max_steps}
Phase: {{current_phase}}

Begin exploration!
"""
    
    async def run(self) -> ContextPatch:
        """
        Main execution loop - gather context and return patch.
        
        Returns:
            ContextPatch with gathered artifacts and metadata
        """
        start_time = time.time()
        self.logger.info(
            "Starting context compilation",
            request_id=self.request_id,
            message=self.request.message[:100],
        )
        
        try:
            # Exploration loop
            while self.step_count < self.max_steps:
                if self.is_paused:
                    await self._wait_for_resume()
                
                self.step_count += 1
                
                # SEE: Build working set with brief history
                working_set = self._build_working_set()
                
                # Persist Working Set snapshot
                self._save_working_set_snapshot(working_set)
                
                # ACT: Generate action
                raw_output = await self._generate_action(working_set)
                
                # Parse output
                parsed = self.parser.parse(raw_output, self.current_phase)
                
                # Log the decision
                self._log_action(parsed)
                
                # Handle intents
                if parsed.intent_type.value == "tool_call":
                    await self._handle_tool_calls(parsed)
                
                elif parsed.intent_type.value == "final_answer":
                    # Agent signals completion
                    confidence = getattr(parsed, 'confidence', 0.5)
                    await self.compiler_skill.mark_exploration_complete(
                        reason=getattr(parsed, 'reason', "Agent signaled completion"),
                        confidence=confidence,
                    )
                    break
                
                elif parsed.intent_type.value == "error":
                    self.logger.error("Agent error", error=parsed.error_message)
                    break
                
                # Check if exploration marked complete
                if self.compiler_skill.is_exploration_complete():
                    break
            
            # Build and return Context Patch
            patch = self._build_context_patch()
            
            # Save artifacts and summary
            self._save_artifacts()
            self._save_summary(patch, time.time() - start_time)
            
            self.logger.info(
                "Context compilation complete",
                request_id=self.request_id,
                steps_used=self.step_count,
                artifacts=len(patch.artifacts),
                confidence=patch.confidence,
            )
            
            return patch
        
        except Exception as e:
            self.logger.error("Context compilation failed", error=str(e))
            # Return error patch
            return ContextPatch(
                status="error",
                artifacts=[],
                files_read=[f["path"] for f in self.compiler_skill.exploration_metadata.files_read],
                reasoning=f"Error during compilation: {str(e)}",
                steps_used=self.step_count,
                confidence=0.0,
            )
    
    def _build_working_set(self):
        """Build working set with brief event history."""
        # Get brief recent events (last 3-5)
        recent_events = self.event_log.get_recent_as_text(count=5)
        
        # Get priority artifacts
        priority_artifacts = sorted(
            self.artifact_slots.values(),
            key=lambda a: a.priority,
            reverse=True,
        )[:5]
        
        # Build working set
        from thread_runtime.models import WorkingSet
        
        return WorkingSet(
            immutable_input=self._build_immutable_input(self.compiled_context),
            recent_observations=recent_events,
            artifact_slots=priority_artifacts,
            current_phase=self.current_phase,
            step_number=self.step_count,
            max_steps=self.max_steps,
        )
    
    def _save_working_set_snapshot(self, working_set) -> None:
        """Save Working Set snapshot for audit."""
        try:
            snapshot = WorkingSetSnapshot(
                step=self.step_count,
                working_set_tokens=len(working_set.to_prompt_text()),
                events_included=[e.event_id for e in self.event_log.get_recent(count=5)],
                artifact_slots=[s.slot_id for s in working_set.artifact_slots],
                phase=self.current_phase.value,
                full_content={
                    "immutable_input": working_set.immutable_input,
                    "recent_observations": working_set.recent_observations,
                    "artifact_count": len(working_set.artifact_slots),
                },
            )
            
            self.ws_history.append(snapshot)
            
            # Save to file
            ws_dir = self.storage_dir / "working_set_history"
            ws_dir.mkdir(exist_ok=True)
            
            ws_path = ws_dir / f"step_{self.step_count:02d}.json"
            with open(ws_path, 'w', encoding='utf-8') as f:
                json.dump(snapshot.model_dump(), f, indent=2, default=str)
        
        except Exception as e:
            self.logger.warning("Failed to save Working Set snapshot", error=str(e))
    
    def _log_action(self, parsed) -> None:
        """Log agent action to Event Log."""
        self.event_log.append(
            event_type="observation",  # Using string to avoid import issues
            actor=self.thread_id,
            phase=self.current_phase,
            content={
                "type": "agent_action",
                "intent": parsed.intent_type.value,
                "step": self.step_count,
                "reasoning": getattr(parsed, 'reasoning', "")[:200],
            },
            metadata={"step": self.step_count},
        )
    
    def _build_context_patch(self) -> ContextPatch:
        """Build final Context Patch from gathered information."""
        # Gather artifacts
        artifacts = list(self.artifact_slots.values())
        
        # Gather files read
        files_read = [
            f["path"] for f in self.compiler_skill.exploration_metadata.files_read
        ]
        
        # Determine status
        if self.compiler_skill.is_exploration_complete():
            status = "complete"
        elif self.step_count >= self.max_steps:
            status = "incomplete"
        else:
            status = "error"
        
        # Build reasoning
        reasoning_parts = [
            f"Exploration completed in {self.step_count} steps",
            f"Gathered {len(artifacts)} artifacts",
            f"Read {len(files_read)} files",
        ]
        
        if artifacts:
            reasoning_parts.append(
                f"Artifacts: {', '.join(a.slot_type for a in artifacts)}"
            )
        
        return ContextPatch(
            status=status,
            artifacts=artifacts,
            files_read=files_read,
            reasoning="; ".join(reasoning_parts),
            steps_used=self.step_count,
            confidence=self.compiler_skill.exploration_metadata.confidence_score,
            metadata={
                "max_steps": self.max_steps,
                "exploration_strategy": self.compiler_skill.exploration_metadata.strategy,
                "session_id": self.session.id,
            },
        )
    
    def _save_artifacts(self) -> None:
        """Save artifacts to file."""
        try:
            artifacts_data = [
                {
                    "slot_id": slot.slot_id,
                    "slot_type": slot.slot_type,
                    "content": slot.content,
                    "priority": slot.priority,
                    "created_at": slot.created_at.isoformat() if slot.created_at else None,
                }
                for slot in self.artifact_slots.values()
            ]
            
            artifacts_path = self.storage_dir / "artifacts.json"
            with open(artifacts_path, 'w', encoding='utf-8') as f:
                json.dump(artifacts_data, f, indent=2, default=str)
            
            self.logger.debug("Artifacts saved", count=len(artifacts_data))
        
        except Exception as e:
            self.logger.error("Failed to save artifacts", error=str(e))
    
    def _save_summary(self, patch: ContextPatch, duration: float) -> None:
        """Save compilation summary."""
        try:
            from context_compiler.models import PrimeCompilationSummary
            
            summary = PrimeCompilationSummary(
                request_id=self.request_id,
                session_id=self.session.id,
                triggered_agent=True,
                steps_used=patch.steps_used,
                max_steps=self.max_steps,
                files_read=patch.files_read,
                artifacts_gathered=len(patch.artifacts),
                duration_ms=int(duration * 1000),
                status="success" if patch.status == "complete" else patch.status,
                trigger_reason="Agent-assisted compilation triggered",
            )
            
            summary_path = self.storage_dir / "summary.json"
            with open(summary_path, 'w', encoding='utf-8') as f:
                json.dump(summary.model_dump(), f, indent=2, default=str)
            
            self.logger.debug("Summary saved")
        
        except Exception as e:
            self.logger.error("Failed to save summary", error=str(e))
    
    async def _handle_file_read_result(self, file_path: str, content: str) -> None:
        """Handle file read result - register as artifact."""
        # Record file read
        self.compiler_skill.record_file_read(file_path, content[:200])
        
        # Try to extract structured information
        await self._extract_and_register_info(file_path, content)
    
    async def _extract_and_register_info(self, file_path: str, content: str) -> None:
        """Extract structured information from file content."""
        try:
            if file_path.endswith('.json'):
                data = json.loads(content)
                
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
                            events.append(json.loads(line))
                        except json.JSONDecodeError:
                            continue
                
                if events:
                    await self.compiler_skill.register_artifact_slot(
                        slot_type="recent_events",
                        content={
                            "event_count": len(events),
                            "latest_events": events[-5:],
                        },
                        priority=6,
                    )
        
        except Exception as e:
            self.logger.warning(
                "Failed to extract info from file",
                file_path=file_path,
                error=str(e),
            )
