"""
Agent Scheduler - Manages Agent thread lifecycle using asyncio.
"""
import asyncio
from datetime import datetime
from uuid import uuid4

import structlog

from executors_client.executor_client import get_executor_client
from schemas.models import CompiledContext, TaskSnapshot, TaskStatus
from storage.runtime_store import get_memory_manager
from thread_runtime.agent_thread import AgentThread

logger = structlog.get_logger()


class AgentScheduler:
    def __init__(self):
        self.logger = logger.bind(component="AgentScheduler")
        self.task_queue: asyncio.Queue[tuple[TaskSnapshot, CompiledContext]] = asyncio.Queue()
        self.active_tasks: dict[str, asyncio.Task] = {}
        self.executor_client = get_executor_client()
        self.max_concurrent_tasks = 5
        self._running = False

    async def start(self) -> None:
        self._running = True
        self.logger.info("Agent scheduler started")
        workers = [asyncio.create_task(self._worker_loop()) for _ in range(self.max_concurrent_tasks)]
        await asyncio.gather(*workers)

    async def stop(self) -> None:
        self._running = False
        self.logger.info("Stopping agent scheduler")
        for task_id, task in list(self.active_tasks.items()):
            task.cancel()
            self.logger.info("Cancelled task", task_id=task_id)
        self.active_tasks.clear()

    async def submit_task(self, task: TaskSnapshot, compiled_context: CompiledContext) -> None:
        await self.task_queue.put((task, compiled_context))

    async def run_task(self, task: TaskSnapshot, context: CompiledContext) -> dict:
        memory_manager = get_memory_manager()
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

        agent = AgentThread(task=task, compiled_context=context, executor_client=self.executor_client)
        asyncio_task = asyncio.create_task(agent.run())
        self.active_tasks[task.id] = asyncio_task

        try:
            result = await asyncio_task
            task.status = TaskStatus.COMPLETED if result.success else TaskStatus.FAILED
            task.completed_at = datetime.utcnow()
            task.output = result.content
            task.error = result.error
            await memory_manager.save_task(task)
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
            self.active_tasks.pop(task.id, None)

    async def _worker_loop(self) -> None:
        while self._running:
            try:
                task, context = await asyncio.wait_for(self.task_queue.get(), timeout=1.0)
                await self.run_task(task, context)
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                self.logger.error("Worker loop error", error=str(e))

    async def cancel_task(self, task_id: str) -> bool:
        task = self.active_tasks.get(task_id)
        if task:
            task.cancel()
            self.logger.info("Task cancellation requested", task_id=task_id)
            return True
        self.logger.warning("Task not found for cancellation", task_id=task_id)
        return False

    def get_active_task_count(self) -> int:
        return len(self.active_tasks)


_scheduler: AgentScheduler | None = None


def get_scheduler() -> AgentScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = AgentScheduler()
    return _scheduler
