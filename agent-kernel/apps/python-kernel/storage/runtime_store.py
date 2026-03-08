"""
Runtime storage manager backed by StorageAdapter.
"""
from datetime import datetime
from typing import Any, Optional

import structlog

from schemas.models import Request, Session, TaskSnapshot
from storage.adapter import SQLiteStorageAdapter, get_storage

logger = structlog.get_logger()


class RuntimeMemoryManager:
    def __init__(self):
        self.logger = logger.bind(component="RuntimeMemoryManager")
        self.storage = get_storage()

    async def initialize(self) -> None:
        if isinstance(self.storage, SQLiteStorageAdapter):
            await self.storage.initialize()
        self.logger.info("Runtime memory initialized", backend=self.storage.__class__.__name__)

    async def save_session(self, session: Session) -> None:
        await self.storage.save_session(session.model_dump(mode='json'))

    async def get_session(self, session_id: str) -> Optional[Session]:
        data = await self.storage.get_session(session_id)
        return Session(**data) if data else None

    async def save_request(self, request: Request) -> None:
        await self.storage.save_request(request.model_dump(mode='json'))

    async def get_request(self, request_id: str) -> Optional[Request]:
        data = await self.storage.get_request(request_id)
        return Request(**data) if data else None

    async def save_task(self, task: TaskSnapshot) -> None:
        await self.storage.save_task(task.model_dump(mode='json'))

    async def get_task(self, task_id: str) -> Optional[TaskSnapshot]:
        data = await self.storage.get_task(task_id)
        return TaskSnapshot(**data) if data else None

    async def get_session_tasks(self, session_id: str) -> list[TaskSnapshot]:
        rows = await self.storage.list_tasks_by_session(session_id)
        return [TaskSnapshot(**row) for row in rows]

    async def save_snapshot(self, snapshot: dict[str, Any]) -> None:
        await self.storage.save_snapshot(snapshot)

    async def get_recent_snapshots(self, session_id: str, limit: int = 2) -> list[dict[str, Any]]:
        rows = await self.storage.list_snapshots_by_session(session_id)
        return rows[:limit]

    async def save_event(self, session_id: str, event: dict[str, Any]) -> None:
        await self.storage.append_event(session_id, event)

    async def get_recent_events(self, session_id: str, limit: int = 20) -> list[dict[str, Any]]:
        return await self.storage.list_events(session_id, limit=limit)

    async def compress_old_contexts(self, max_age_hours: int = 24) -> int:
        self.logger.info("Context compression not yet implemented", max_age_hours=max_age_hours)
        return 0

    async def close(self) -> None:
        await self.storage.close()
        self.logger.info("Runtime memory manager closed")


_memory_manager: RuntimeMemoryManager | None = None


def get_memory_manager() -> RuntimeMemoryManager:
    global _memory_manager
    if _memory_manager is None:
        _memory_manager = RuntimeMemoryManager()
    return _memory_manager
