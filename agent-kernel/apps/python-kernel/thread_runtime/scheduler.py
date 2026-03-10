"""
Agent Scheduler - Manages Agent thread lifecycle using asyncio.

Updated to work with refactored Agent Thread (Event Log + Working Set architecture).
Provides intervention APIs for upper layer control.
"""
import asyncio
from datetime import datetime
from uuid import uuid4
from typing import Any

import structlog

from executors_client.coordinator_interface import get_execution_coordinator
from schemas.models import CompiledContext, TaskSnapshot, TaskStatus
from storage.runtime_store import get_memory_manager
from thread_runtime.agent_thread import AgentThread
from thread_runtime.models import Phase
from thread_runtime.working_set_builder import WorkingSetBuilder

logger = structlog.get_logger()


class AgentScheduler:
    """
    Manages Agent Thread lifecycle and provides upper layer intervention.
    
    New capabilities:
    - Works with refactored Agent Thread
    - Provides thread state inspection
    - Allows phase/context updates
    - Integrates with OS Interface for monitoring
    """
    
    def __init__(self):
        self.logger = logger.bind(component="AgentScheduler")
        self.task_queue: asyncio.Queue[tuple[TaskSnapshot, CompiledContext]] = asyncio.Queue()
        self.active_tasks: dict[str, asyncio.Task] = {}
        self.active_threads: dict[str, AgentThread] = {}  # task_id -> AgentThread
        self.coordinator = get_execution_coordinator()
        self.ws_builder = WorkingSetBuilder()
        self.max_concurrent_tasks = 5
        self._running = False

    async def start(self) -> None:
        self._running = True
        self.logger.info("Agent scheduler started")
        workers = [
            asyncio.create_task(self._worker_loop())
            for _ in range(self.max_concurrent_tasks)
        ]
        await asyncio.gather(*workers)

    async def stop(self) -> None:
        self._running = False
        self.logger.info("Stopping agent scheduler")
        
        # Cancel all active asyncio tasks
        for task_id, task in list(self.active_tasks.items()):
            task.cancel()
            self.logger.info("Cancelled task", task_id=task_id)
        
        self.active_tasks.clear()
        self.active_threads.clear()

    async def submit_task(
        self,
        task: TaskSnapshot,
        compiled_context: CompiledContext,
    ) -> None:
        """Submit a task to the queue."""
        await self.task_queue.put((task, compiled_context))

    async def run_task(
        self,
        task: TaskSnapshot,
        context: CompiledContext,
    ) -> dict[str, Any]:
        """
        Execute a task using Agent Thread.
        
        Args:
            task: Task to execute
            context: Compiled context
            
        Returns:
            Execution result dict
        """
        memory_manager = get_memory_manager()
        
        # Update task status
        task.status = TaskStatus.RUNNING
        task.started_at = datetime.utcnow()
        await memory_manager.save_task(task)
        await memory_manager.save_event(
            task.session_id,
            {
                "timestamp": datetime.utcnow().isoformat(),
                "session_id": task.session_id,
                "request_id": context.session_context.get("request_id"),
                "task_id": task.id,
                "phase": "task_started",
                "actor": "scheduler",
                "summary": task.goal,
                "status": "running",
            },
        )

        # Create Agent Thread with new architecture
        agent_thread = AgentThread(
            task=task,
            compiled_context=context,
            coordinator=self.coordinator,
            ws_builder=self.ws_builder,
        )
        
        # Track the thread
        self.active_threads[task.id] = agent_thread
        
        # Create asyncio task
        asyncio_task = asyncio.create_task(agent_thread.run())
        self.active_tasks[task.id] = asyncio_task

        try:
            result = await asyncio_task
            
            # Update task status
            task.status = TaskStatus.COMPLETED if result.success else TaskStatus.FAILED
            task.completed_at = datetime.utcnow()
            task.output = result.content
            task.error = result.error
            await memory_manager.save_task(task)
            
            # Save snapshot
            await memory_manager.save_snapshot(
                {
                    "id": f"snap_{uuid4()}",
                    "session_id": task.session_id,
                    "task_id": task.id,
                    "working_memory": {
                        "task_goal": task.goal,
                        "result": result.content,
                        "success": result.success,
                        "observations": result.observations,
                    },
                    "timestamp": datetime.utcnow().isoformat(),
                }
            )
            
            # Save completion event
            await memory_manager.save_event(
                task.session_id,
                {
                    "timestamp": datetime.utcnow().isoformat(),
                    "session_id": task.session_id,
                    "request_id": context.session_context.get("request_id"),
                    "task_id": task.id,
                    "phase": "task_completed" if result.success else "task_failed",
                    "actor": "scheduler",
                    "summary": task.goal,
                    "status": "completed" if result.success else "failed",
                },
            )
            
            return {
                "task_id": task.id,
                "status": task.status.value,
                "goal": task.goal,
                "output": task.output,
                "error": task.error,
            }
            
        except asyncio.CancelledError:
            task.status = TaskStatus.PAUSED
            task.error = "Task cancelled"
            await memory_manager.save_task(task)
            raise
            
        finally:
            # Cleanup
            self.active_tasks.pop(task.id, None)
            self.active_threads.pop(task.id, None)

    async def _worker_loop(self) -> None:
        """Worker loop to process queued tasks."""
        while self._running:
            try:
                task, context = await asyncio.wait_for(
                    self.task_queue.get(),
                    timeout=1.0,
                )
                await self.run_task(task, context)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                self.logger.error("Worker loop error", error=str(e))

    # ========== Intervention APIs (for upper layer) ==========
    
    async def pause_task(self, task_id: str, reason: str = "") -> bool:
        """
        Pause a running task.
        
        Args:
            task_id: Task to pause
            reason: Reason for pausing
            
        Returns:
            True if task was paused
        """
        agent_thread = self.active_threads.get(task_id)
        if not agent_thread:
            self.logger.warning("Task not found for pause", task_id=task_id)
            return False
        
        await agent_thread.pause(reason)
        self.logger.info("Task paused", task_id=task_id, reason=reason)
        return True

    async def resume_task(self, task_id: str) -> bool:
        """
        Resume a paused task.
        
        Args:
            task_id: Task to resume
            
        Returns:
            True if task was resumed
        """
        agent_thread = self.active_threads.get(task_id)
        if not agent_thread:
            self.logger.warning("Task not found for resume", task_id=task_id)
            return False
        
        await agent_thread.resume()
        self.logger.info("Task resumed", task_id=task_id)
        return True

    async def get_thread_log(self, task_id: str) -> dict[str, Any] | None:
        """
        Get full event log of a thread.
        
        This is how upper layers inspect thread state.
        
        Args:
            task_id: Task ID
            
        Returns:
            Full event log export or None if task not found
        """
        agent_thread = self.active_threads.get(task_id)
        if not agent_thread:
            return None
        
        return agent_thread.get_event_log_export()

    async def update_thread_phase(
        self,
        task_id: str,
        new_phase: Phase | str,
    ) -> bool:
        """
        Update thread phase (intervention API).
        
        Args:
            task_id: Task to update
            new_phase: New phase (Phase enum or string)
            
        Returns:
            True if phase was updated
        """
        agent_thread = self.active_threads.get(task_id)
        if not agent_thread:
            self.logger.warning(
                "Task not found for phase update",
                task_id=task_id,
            )
            return False
        
        # Convert string to Phase if needed
        if isinstance(new_phase, str):
            new_phase = Phase(new_phase)
        
        await agent_thread.apply_context_update({"phase": new_phase})
        self.logger.info(
            "Thread phase updated",
            task_id=task_id,
            new_phase=new_phase.value,
        )
        return True

    async def update_thread_context(
        self,
        task_id: str,
        updates: dict[str, Any],
    ) -> bool:
        """
        Update thread context (intervention API).
        
        Args:
            task_id: Task to update
            updates: Context updates to apply
            
        Returns:
            True if context was updated
        """
        agent_thread = self.active_threads.get(task_id)
        if not agent_thread:
            self.logger.warning(
                "Task not found for context update",
                task_id=task_id,
            )
            return False
        
        await agent_thread.apply_context_update(updates)
        self.logger.info(
            "Thread context updated",
            task_id=task_id,
            updates=list(updates.keys()),
        )
        return True

    def get_active_thread_info(self, task_id: str) -> dict[str, Any] | None:
        """
        Get brief info about an active thread.
        
        Args:
            task_id: Task ID
            
        Returns:
            Thread info dict or None
        """
        agent_thread = self.active_threads.get(task_id)
        if not agent_thread:
            return None
        
        return {
            "task_id": task_id,
            "thread_id": agent_thread.thread_id,
            "current_phase": agent_thread.current_phase.value,
            "step_count": agent_thread.step_count,
            "is_paused": agent_thread.is_paused,
            "pause_reason": agent_thread.pause_reason,
            "max_steps": agent_thread.max_steps,
        }

    def list_active_threads(self) -> list[dict[str, Any]]:
        """List all active threads with brief info."""
        return [
            {
                "task_id": task_id,
                "thread_id": thread.thread_id,
                "phase": thread.current_phase.value,
                "step_count": thread.step_count,
                "is_paused": thread.is_paused,
            }
            for task_id, thread in self.active_threads.items()
        ]

    # ========== Legacy API (for backward compatibility) ==========
    
    async def cancel_task(self, task_id: str) -> bool:
        """
        Cancel a task (legacy API, now uses pause).
        
        Args:
            task_id: Task to cancel
            
        Returns:
            True if cancellation was initiated
        """
        # First try to pause
        paused = await self.pause_task(task_id, "Cancelled by user")
        if paused:
            return True
        
        # If not found as active thread, try cancelling asyncio task
        task = self.active_tasks.get(task_id)
        if task:
            task.cancel()
            self.logger.info("Task cancellation requested", task_id=task_id)
            return True
        
        self.logger.warning("Task not found for cancellation", task_id=task_id)
        return False

    def get_active_task_count(self) -> int:
        """Get number of active tasks."""
        return len(self.active_tasks)


# Singleton instance
_scheduler: AgentScheduler | None = None


def get_scheduler() -> AgentScheduler:
    """Get or create singleton instance."""
    global _scheduler
    if _scheduler is None:
        _scheduler = AgentScheduler()
    return _scheduler
