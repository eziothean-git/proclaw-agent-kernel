"""
Session Host - Session-level Agent that manages Process lifecycle.
"""
from datetime import datetime
from typing import Any
from uuid import uuid4

import structlog

from context_compiler.process_compiler import get_process_compiler
from schemas.models import (
    IntermediateRepresentation,
    LongTermMemoryCandidate,
    Request,
    Session,
    TaskSnapshot,
    TaskStatus,
)
from storage.runtime_store import get_memory_manager
from thread_runtime.scheduler import get_scheduler

logger = structlog.get_logger()


class SessionHost:
    def __init__(self, session: Session):
        self.session = session
        self.logger = logger.bind(component="SessionHost", session_id=session.id)
        self.processes: dict[str, TaskSnapshot] = {}
        self.process_compiler = get_process_compiler()
        self.scheduler = get_scheduler()

    async def handle_request(self, request: Request, intermediate_repr: IntermediateRepresentation) -> dict[str, Any]:
        self.logger.info("Handling request", request_id=request.id, process_count=len(intermediate_repr.processes))
        results = []
        for process_def in intermediate_repr.processes:
            task_id = str(uuid4())
            result = await self.spawn_task(
                request=request,
                task_id=task_id,
                process_definition=process_def,
                intermediate_repr=intermediate_repr,
            )
            results.append(result)

        self.session.task_count += len(results)
        self.session.last_activity = datetime.utcnow()
        await get_memory_manager().save_session(self.session)

        overall_status = "completed" if all(result["status"] == "completed" for result in results) else "failed"

        # Aggregate results for memory extraction
        aggregated_result = {
            "status": overall_status,
            "task_ids": [result.get("task_id") for result in results],
            "output": "\n\n".join([str(result.get("output", "")) for result in results]),
            "actions": [],
        }
        for result in results:
            if "actions" in result:
                aggregated_result["actions"].extend(result["actions"])

        # Extract and submit long-term memories (Host-managed, not Agent Thread)
        try:
            memory_candidates = await self.extract_and_submit_memories(request, aggregated_result)
            self.logger.info(
                "Long-term memory extraction completed",
                session_id=self.session.id,
                request_id=request.id,
                candidates_count=len(memory_candidates),
            )
        except Exception as e:
            self.logger.error(
                "Failed to extract long-term memories",
                session_id=self.session.id,
                request_id=request.id,
                error=str(e),
            )
            memory_candidates = []

        return {
            "session_id": self.session.id,
            "request_id": request.id,
            "status": overall_status,
            "task_ids": [result.get("task_id") for result in results],
            "tasks_spawned": len(results),
            "results": results,
            "memory_candidates": len(memory_candidates),
            "output": aggregated_result["output"],
            "actions": aggregated_result["actions"],
        }

    async def spawn_task(
        self,
        request: Request,
        task_id: str,
        process_definition: dict[str, Any],
        intermediate_repr: IntermediateRepresentation,
    ) -> dict[str, Any]:
        task = TaskSnapshot(
            id=task_id,
            session_id=self.session.id,
            process_id=str(uuid4()),
            status=TaskStatus.IDLE,
            goal=process_definition.get("goal", "Execute task"),
            constraints=process_definition.get("constraints", []),
            allowed_capabilities=process_definition.get("capabilities", []),
        )
        self.processes[task_id] = task

        memory_manager = get_memory_manager()
        await memory_manager.save_task(task)
        await memory_manager.save_event(
            self.session.id,
            {
                "timestamp": datetime.utcnow().isoformat(),
                "session_id": self.session.id,
                "request_id": request.id,
                "task_id": task.id,
                "phase": "task_created",
                "actor": "session_host",
                "summary": task.goal,
                "status": "idle",
            },
        )

        compiled_context = await self.process_compiler.compile_task_context(
            task_id=task_id,
            process_definition=process_definition,
            intermediate_repr=intermediate_repr,
            session_context={
                "session_id": self.session.id,
                "user_id": self.session.user_id,
                "request_id": request.id,
                "request_message": request.message,
                "request_metadata": request.metadata,
            },
            task_snapshots=list(self.processes.values()),
        )
        return await self.scheduler.run_task(task, compiled_context)

    async def submit_long_term_candidate(self, candidate: LongTermMemoryCandidate) -> bool:
        """Submit a candidate for long-term memory storage.

        This is the primary interface for long-term memory submission.
        All memory candidates are persisted through the memory manager.
        """
        self.logger.info(
            "Submitting long-term memory candidate",
            candidate_id=candidate.id,
            category=candidate.category,
            importance=candidate.importance_score,
        )

        memory_manager = get_memory_manager()
        success = await memory_manager.save_long_term_memory(candidate)

        if success:
            self.logger.info(
                "Successfully saved long-term memory",
                candidate_id=candidate.id,
                session_id=candidate.session_id,
            )
        else:
            self.logger.error(
                "Failed to save long-term memory",
                candidate_id=candidate.id,
                session_id=candidate.session_id,
            )

        return success

    async def extract_and_submit_memories(
        self,
        request: Request,
        result: dict[str, Any],
    ) -> list[LongTermMemoryCandidate]:
        """Extract memory candidates from completed tasks and submit them.

        This method analyzes task results and creates memory candidates
        for important information that should be remembered across sessions.

        Args:
            request: Original request
            result: Task execution result

        Returns:
            List of submitted memory candidates
        """
        from uuid import uuid4

        submitted = []

        # Extract from successful task output
        if result.get("status") == "completed" and result.get("output"):
            output = result.get("output", "")

            # Heuristic: Long or complex outputs might be worth remembering
            if len(output) > 200:
                candidate = LongTermMemoryCandidate(
                    id=str(uuid4()),
                    session_id=self.session.id,
                    content=f"Task output: {output[:500]}",
                    category="task_output",
                    importance_score=0.6,
                    metadata={
                        "request_id": request.id,
                        "task_ids": result.get("task_ids", []),
                        "full_output_length": len(output),
                    },
                )
                if await self.submit_long_term_candidate(candidate):
                    submitted.append(candidate)

        # Extract from actions taken
        actions = result.get("actions", [])
        if actions:
            action_summary = "; ".join([str(a) for a in actions[:5]])
            candidate = LongTermMemoryCandidate(
                id=str(uuid4()),
                session_id=self.session.id,
                content=f"Actions performed: {action_summary}",
                category="actions",
                importance_score=0.5,
                metadata={
                    "request_id": request.id,
                    "action_count": len(actions),
                },
            )
            if await self.submit_long_term_candidate(candidate):
                submitted.append(candidate)

        # Extract user preferences from request patterns
        if request.metadata and request.metadata.get("user_preferences"):
            prefs = request.metadata.get("user_preferences", {})
            for key, value in prefs.items():
                candidate = LongTermMemoryCandidate(
                    id=str(uuid4()),
                    session_id=self.session.id,
                    content=f"User preference: {key} = {value}",
                    category="user_preference",
                    importance_score=0.7,
                    metadata={
                        "request_id": request.id,
                        "preference_key": key,
                    },
                )
                if await self.submit_long_term_candidate(candidate):
                    submitted.append(candidate)

        self.logger.info(
            "Memory extraction complete",
            session_id=self.session.id,
            candidates_submitted=len(submitted),
        )

        return submitted

    def get_task_status(self, task_id: str) -> TaskSnapshot | None:
        return self.processes.get(task_id)

    def get_all_tasks(self) -> list[TaskSnapshot]:
        return list(self.processes.values())


_session_hosts: dict[str, SessionHost] = {}


def get_session_host(session: Session) -> SessionHost:
    if session.id not in _session_hosts:
        _session_hosts[session.id] = SessionHost(session)
    return _session_hosts[session.id]


def remove_session_host(session_id: str) -> None:
    if session_id in _session_hosts:
        del _session_hosts[session_id]
