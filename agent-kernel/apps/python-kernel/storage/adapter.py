"""
Storage Adapter - unified runtime persistence for file and SQLite backends.
"""
import json
import os
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional

import aiosqlite


class StorageAdapter(ABC):
    """Storage abstraction used by the runtime and tools."""

    @abstractmethod
    async def save_session(self, session: dict) -> None:
        pass

    @abstractmethod
    async def get_session(self, session_id: str) -> Optional[dict]:
        pass

    @abstractmethod
    async def list_sessions(self) -> List[dict]:
        pass

    @abstractmethod
    async def update_session(self, session_id: str, updates: dict) -> None:
        pass

    @abstractmethod
    async def save_request(self, request: dict) -> None:
        pass

    @abstractmethod
    async def get_request(self, request_id: str) -> Optional[dict]:
        pass

    @abstractmethod
    async def list_requests_by_session(self, session_id: str) -> List[dict]:
        pass

    @abstractmethod
    async def save_task(self, task: dict) -> None:
        pass

    @abstractmethod
    async def get_task(self, task_id: str) -> Optional[dict]:
        pass

    @abstractmethod
    async def list_tasks_by_session(self, session_id: str) -> List[dict]:
        pass

    @abstractmethod
    async def update_task(self, task_id: str, updates: dict) -> None:
        pass

    @abstractmethod
    async def save_snapshot(self, snapshot: dict) -> None:
        pass

    @abstractmethod
    async def get_snapshot(self, snapshot_id: str) -> Optional[dict]:
        pass

    @abstractmethod
    async def get_latest_snapshot(self, session_id: str) -> Optional[dict]:
        pass

    @abstractmethod
    async def list_snapshots_by_session(self, session_id: str) -> List[dict]:
        pass

    @abstractmethod
    async def append_event(self, session_id: str, event: dict) -> None:
        pass

    @abstractmethod
    async def list_events(self, session_id: str, limit: int = 20) -> List[dict]:
        pass

    @abstractmethod
    async def enqueue_request(self, request: dict) -> None:
        pass

    @abstractmethod
    async def dequeue_request(self) -> Optional[dict]:
        pass

    @abstractmethod
    async def peek_queue(self) -> Optional[dict]:
        pass

    @abstractmethod
    async def get_queue_length(self) -> int:
        pass

    @abstractmethod
    async def schedule_task(self, task: dict) -> None:
        pass

    @abstractmethod
    async def get_due_tasks(self, before: datetime) -> List[dict]:
        pass

    @abstractmethod
    async def complete_scheduled_task(self, task_id: str) -> None:
        pass

    @abstractmethod
    async def cancel_scheduled_task(self, task_id: str) -> None:
        pass

    @abstractmethod
    async def close(self) -> None:
        pass


class FileStorageAdapter(StorageAdapter):
    def __init__(self, base_path: str = "./data"):
        self.base_path = Path(base_path)
        self._ensure_directories()

    def _ensure_directories(self):
        for dir_name in ['sessions', 'requests', 'tasks', 'snapshots', 'events', 'queue', 'scheduler']:
            (self.base_path / dir_name).mkdir(parents=True, exist_ok=True)

    def _write_json(self, path: Path, data: dict):
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)

    def _read_json(self, path: Path) -> Optional[dict]:
        if not path.exists():
            return None
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

    async def save_session(self, session: dict) -> None:
        self._write_json(self.base_path / 'sessions' / f"{session['id']}.json", session)

    async def get_session(self, session_id: str) -> Optional[dict]:
        return self._read_json(self.base_path / 'sessions' / f"{session_id}.json")

    async def list_sessions(self) -> List[dict]:
        return [self._read_json(file_path) for file_path in (self.base_path / 'sessions').glob('*.json') if self._read_json(file_path)]

    async def update_session(self, session_id: str, updates: dict) -> None:
        session = await self.get_session(session_id)
        if session:
            session.update(updates)
            await self.save_session(session)

    async def save_request(self, request: dict) -> None:
        self._write_json(self.base_path / 'requests' / f"{request['id']}.json", request)

    async def get_request(self, request_id: str) -> Optional[dict]:
        return self._read_json(self.base_path / 'requests' / f"{request_id}.json")

    async def list_requests_by_session(self, session_id: str) -> List[dict]:
        requests: List[dict] = []
        for file_path in (self.base_path / 'requests').glob('*.json'):
            request = self._read_json(file_path)
            if request and request.get('session_id') == session_id:
                requests.append(request)
        return sorted(requests, key=lambda item: item.get('created_at', ''), reverse=True)

    async def save_task(self, task: dict) -> None:
        self._write_json(self.base_path / 'tasks' / f"{task['id']}.json", task)

    async def get_task(self, task_id: str) -> Optional[dict]:
        return self._read_json(self.base_path / 'tasks' / f"{task_id}.json")

    async def list_tasks_by_session(self, session_id: str) -> List[dict]:
        tasks: List[dict] = []
        for file_path in (self.base_path / 'tasks').glob('*.json'):
            task = self._read_json(file_path)
            if task and task.get('session_id') == session_id:
                tasks.append(task)
        return sorted(tasks, key=lambda item: item.get('created_at', ''), reverse=True)

    async def update_task(self, task_id: str, updates: dict) -> None:
        task = await self.get_task(task_id)
        if task:
            task.update(updates)
            await self.save_task(task)

    async def save_snapshot(self, snapshot: dict) -> None:
        self._write_json(self.base_path / 'snapshots' / f"{snapshot['id']}.json", snapshot)

    async def get_snapshot(self, snapshot_id: str) -> Optional[dict]:
        return self._read_json(self.base_path / 'snapshots' / f"{snapshot_id}.json")

    async def get_latest_snapshot(self, session_id: str) -> Optional[dict]:
        snapshots = await self.list_snapshots_by_session(session_id)
        return snapshots[0] if snapshots else None

    async def list_snapshots_by_session(self, session_id: str) -> List[dict]:
        snapshots: List[dict] = []
        for file_path in (self.base_path / 'snapshots').glob('*.json'):
            snapshot = self._read_json(file_path)
            if snapshot and snapshot.get('session_id') == session_id:
                snapshots.append(snapshot)
        return sorted(snapshots, key=lambda item: item.get('timestamp', ''), reverse=True)

    async def append_event(self, session_id: str, event: dict) -> None:
        event_file = self.base_path / 'events' / f"{session_id}.jsonl"
        with open(event_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(event, ensure_ascii=False, default=str) + '\n')

    async def list_events(self, session_id: str, limit: int = 20) -> List[dict]:
        event_file = self.base_path / 'events' / f"{session_id}.jsonl"
        if not event_file.exists():
            return []
        with open(event_file, 'r', encoding='utf-8') as f:
            events = [json.loads(line) for line in f if line.strip()]
        return events[-limit:]

    async def enqueue_request(self, request: dict) -> None:
        queue_file = self.base_path / 'queue' / 'requests.jsonl'
        with open(queue_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(request, ensure_ascii=False, default=str) + '\n')

    async def dequeue_request(self) -> Optional[dict]:
        queue_file = self.base_path / 'queue' / 'requests.jsonl'
        if not queue_file.exists():
            return None
        with open(queue_file, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        for index, line in enumerate(lines):
            request = json.loads(line)
            if request.get('status') == 'pending':
                request['status'] = 'processing'
                lines[index] = json.dumps(request, ensure_ascii=False, default=str) + '\n'
                with open(queue_file, 'w', encoding='utf-8') as f:
                    f.writelines(lines)
                return request
        return None

    async def peek_queue(self) -> Optional[dict]:
        queue_file = self.base_path / 'queue' / 'requests.jsonl'
        if not queue_file.exists():
            return None
        with open(queue_file, 'r', encoding='utf-8') as f:
            for line in f:
                request = json.loads(line)
                if request.get('status') == 'pending':
                    return request
        return None

    async def get_queue_length(self) -> int:
        queue_file = self.base_path / 'queue' / 'requests.jsonl'
        if not queue_file.exists():
            return 0
        with open(queue_file, 'r', encoding='utf-8') as f:
            return sum(1 for line in f if json.loads(line).get('status') == 'pending')

    async def schedule_task(self, task: dict) -> None:
        self._write_json(self.base_path / 'scheduler' / f"{task['id']}.json", task)

    async def get_due_tasks(self, before: datetime) -> List[dict]:
        tasks: List[dict] = []
        for file_path in (self.base_path / 'scheduler').glob('*.json'):
            task = self._read_json(file_path)
            if task and task.get('status') == 'scheduled':
                trigger_at = datetime.fromisoformat(task['trigger_at'])
                if trigger_at <= before:
                    tasks.append(task)
        return tasks

    async def complete_scheduled_task(self, task_id: str) -> None:
        task = self._read_json(self.base_path / 'scheduler' / f"{task_id}.json")
        if task:
            task['status'] = 'completed'
            await self.schedule_task(task)

    async def cancel_scheduled_task(self, task_id: str) -> None:
        path = self.base_path / 'scheduler' / f"{task_id}.json"
        if path.exists():
            path.unlink()

    async def close(self) -> None:
        return None


class SQLiteStorageAdapter(StorageAdapter):
    def __init__(self, db_path: str = "./data/runtime.db"):
        self.db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None

    async def initialize(self):
        self._db = await aiosqlite.connect(self.db_path)
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._create_tables()

    async def _create_tables(self):
        await self._db.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS requests (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                data TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                data TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS snapshots (
                id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                data TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                data TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS queue (
                id TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                status TEXT DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS scheduler (
                id TEXT PRIMARY KEY,
                data TEXT NOT NULL,
                trigger_at TIMESTAMP NOT NULL,
                status TEXT DEFAULT 'scheduled',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_requests_session ON requests(session_id);
            CREATE INDEX IF NOT EXISTS idx_tasks_session ON tasks(session_id);
            CREATE INDEX IF NOT EXISTS idx_snapshots_session ON snapshots(session_id);
            CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id);
            CREATE INDEX IF NOT EXISTS idx_scheduler_trigger ON scheduler(trigger_at);
        """)
        await self._db.commit()

    async def save_session(self, session: dict) -> None:
        await self._db.execute(
            "INSERT OR REPLACE INTO sessions (id, data, updated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
            (session['id'], json.dumps(session, ensure_ascii=False)),
        )
        await self._db.commit()

    async def get_session(self, session_id: str) -> Optional[dict]:
        async with self._db.execute("SELECT data FROM sessions WHERE id = ?", (session_id,)) as cursor:
            row = await cursor.fetchone()
            return json.loads(row[0]) if row else None

    async def list_sessions(self) -> List[dict]:
        async with self._db.execute("SELECT data FROM sessions") as cursor:
            rows = await cursor.fetchall()
            return [json.loads(row[0]) for row in rows]

    async def update_session(self, session_id: str, updates: dict) -> None:
        session = await self.get_session(session_id)
        if session:
            session.update(updates)
            await self.save_session(session)

    async def save_request(self, request: dict) -> None:
        await self._db.execute(
            "INSERT OR REPLACE INTO requests (id, session_id, data, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            (request['id'], request.get('session_id'), json.dumps(request, ensure_ascii=False)),
        )
        await self._db.commit()

    async def get_request(self, request_id: str) -> Optional[dict]:
        async with self._db.execute("SELECT data FROM requests WHERE id = ?", (request_id,)) as cursor:
            row = await cursor.fetchone()
            return json.loads(row[0]) if row else None

    async def list_requests_by_session(self, session_id: str) -> List[dict]:
        async with self._db.execute(
            "SELECT data FROM requests WHERE session_id = ? ORDER BY created_at DESC",
            (session_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [json.loads(row[0]) for row in rows]

    async def save_task(self, task: dict) -> None:
        await self._db.execute(
            "INSERT OR REPLACE INTO tasks (id, session_id, data, updated_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)",
            (task['id'], task.get('session_id'), json.dumps(task, ensure_ascii=False)),
        )
        await self._db.commit()

    async def get_task(self, task_id: str) -> Optional[dict]:
        async with self._db.execute("SELECT data FROM tasks WHERE id = ?", (task_id,)) as cursor:
            row = await cursor.fetchone()
            return json.loads(row[0]) if row else None

    async def list_tasks_by_session(self, session_id: str) -> List[dict]:
        async with self._db.execute(
            "SELECT data FROM tasks WHERE session_id = ? ORDER BY created_at DESC",
            (session_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [json.loads(row[0]) for row in rows]

    async def update_task(self, task_id: str, updates: dict) -> None:
        task = await self.get_task(task_id)
        if task:
            task.update(updates)
            await self.save_task(task)

    async def save_snapshot(self, snapshot: dict) -> None:
        await self._db.execute(
            "INSERT OR REPLACE INTO snapshots (id, session_id, data) VALUES (?, ?, ?)",
            (snapshot['id'], snapshot.get('session_id'), json.dumps(snapshot, ensure_ascii=False)),
        )
        await self._db.commit()

    async def get_snapshot(self, snapshot_id: str) -> Optional[dict]:
        async with self._db.execute("SELECT data FROM snapshots WHERE id = ?", (snapshot_id,)) as cursor:
            row = await cursor.fetchone()
            return json.loads(row[0]) if row else None

    async def get_latest_snapshot(self, session_id: str) -> Optional[dict]:
        async with self._db.execute(
            "SELECT data FROM snapshots WHERE session_id = ? ORDER BY created_at DESC LIMIT 1",
            (session_id,),
        ) as cursor:
            row = await cursor.fetchone()
            return json.loads(row[0]) if row else None

    async def list_snapshots_by_session(self, session_id: str) -> List[dict]:
        async with self._db.execute(
            "SELECT data FROM snapshots WHERE session_id = ? ORDER BY created_at DESC",
            (session_id,),
        ) as cursor:
            rows = await cursor.fetchall()
            return [json.loads(row[0]) for row in rows]

    async def append_event(self, session_id: str, event: dict) -> None:
        await self._db.execute(
            "INSERT INTO events (session_id, data) VALUES (?, ?)",
            (session_id, json.dumps(event, ensure_ascii=False)),
        )
        await self._db.commit()

    async def list_events(self, session_id: str, limit: int = 20) -> List[dict]:
        async with self._db.execute(
            "SELECT data FROM events WHERE session_id = ? ORDER BY id DESC LIMIT ?",
            (session_id, limit),
        ) as cursor:
            rows = await cursor.fetchall()
            return list(reversed([json.loads(row[0]) for row in rows]))

    async def enqueue_request(self, request: dict) -> None:
        await self._db.execute(
            "INSERT OR REPLACE INTO queue (id, data, status) VALUES (?, ?, 'pending')",
            (request['id'], json.dumps(request, ensure_ascii=False)),
        )
        await self._db.commit()

    async def dequeue_request(self) -> Optional[dict]:
        async with self._db.execute(
            "SELECT id, data FROM queue WHERE status = 'pending' ORDER BY created_at ASC LIMIT 1"
        ) as cursor:
            row = await cursor.fetchone()
        if row:
            await self._db.execute("UPDATE queue SET status = 'processing' WHERE id = ?", (row[0],))
            await self._db.commit()
            return json.loads(row[1])
        return None

    async def peek_queue(self) -> Optional[dict]:
        async with self._db.execute(
            "SELECT data FROM queue WHERE status = 'pending' ORDER BY created_at ASC LIMIT 1"
        ) as cursor:
            row = await cursor.fetchone()
            return json.loads(row[0]) if row else None

    async def get_queue_length(self) -> int:
        async with self._db.execute("SELECT COUNT(*) FROM queue WHERE status = 'pending'") as cursor:
            row = await cursor.fetchone()
            return row[0]

    async def schedule_task(self, task: dict) -> None:
        await self._db.execute(
            "INSERT OR REPLACE INTO scheduler (id, data, trigger_at, status) VALUES (?, ?, ?, ?)",
            (task['id'], json.dumps(task, ensure_ascii=False), task.get('trigger_at'), task.get('status', 'scheduled')),
        )
        await self._db.commit()

    async def get_due_tasks(self, before: datetime) -> List[dict]:
        async with self._db.execute(
            "SELECT data FROM scheduler WHERE trigger_at <= ? AND status = 'scheduled'",
            (before.isoformat(),),
        ) as cursor:
            rows = await cursor.fetchall()
            return [json.loads(row[0]) for row in rows]

    async def complete_scheduled_task(self, task_id: str) -> None:
        await self._db.execute("UPDATE scheduler SET status = 'completed' WHERE id = ?", (task_id,))
        await self._db.commit()

    async def cancel_scheduled_task(self, task_id: str) -> None:
        await self._db.execute("DELETE FROM scheduler WHERE id = ?", (task_id,))
        await self._db.commit()

    async def close(self) -> None:
        if self._db:
            await self._db.close()


# Factory helpers

def create_storage_adapter(config: dict) -> StorageAdapter:
    storage_type = config.get('type', 'file')
    if storage_type == 'file':
        return FileStorageAdapter(base_path=config.get('base_path', './data'))
    if storage_type == 'sqlite':
        return SQLiteStorageAdapter(db_path=config.get('db_path', './data/runtime.db'))
    raise ValueError(f"Unknown storage type: {storage_type}")


_storage_instance: Optional[StorageAdapter] = None


def get_storage() -> StorageAdapter:
    global _storage_instance
    if _storage_instance is None:
        _storage_instance = create_storage_adapter({
            'type': os.getenv('STORAGE_TYPE', 'file'),
            'base_path': os.getenv('DATA_PATH', './data'),
            'db_path': os.getenv('DATABASE_PATH', './data/runtime.db'),
        })
    return _storage_instance


def set_storage(adapter: StorageAdapter):
    global _storage_instance
    _storage_instance = adapter
