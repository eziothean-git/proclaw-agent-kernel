"""
Persistent Directory Lock Manager - Cross-process safe directory locking system.

Provides:
- Directory-level locking with FIFO queue
- SQLite persistence for auditability
- File-based locking for cross-process safety
- Automatic timeout and cleanup
- Complete audit logging

Architecture:
- SQLite: Stores lock state, queue, and audit logs
- File lock (fcntl): Ensures mutual exclusion across processes
- Background task: Cleans up expired locks
"""
import asyncio
import fcntl
import json
import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import structlog

logger = structlog.get_logger()


class PersistentDirectoryLockManager:
    """
    Cross-process safe directory lock manager with persistence.
    
    Features:
    - Directory-level locks (read/write levels)
    - FIFO queue for waiting requests
    - SQLite persistence for auditability
    - File-based locking (fcntl) for cross-process safety
    - Automatic timeout and cleanup
    - Complete audit trail
    """
    
    def __init__(self, db_path: str = "./data/directory_locks.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._file_lock_path = self.db_path.with_suffix('.lock')
        self._cleanup_task: Optional[asyncio.Task] = None
        self._stop_cleanup = asyncio.Event()
        
        self._init_db()
        logger.info("PersistentDirectoryLockManager initialized", db_path=str(self.db_path))
    
    def _init_db(self) -> None:
        """Initialize database tables and indexes."""
        with self._get_db() as conn:
            conn.executescript("""
                -- Active directory locks
                CREATE TABLE IF NOT EXISTS directory_locks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    directory_path TEXT UNIQUE NOT NULL,
                    holder_task_id TEXT NOT NULL,
                    holder_session_id TEXT NOT NULL,
                    holder_process_id TEXT NOT NULL,
                    acquired_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    expires_at TIMESTAMP NOT NULL,
                    lock_level TEXT CHECK(lock_level IN ('read', 'write')) DEFAULT 'write',
                    timeout_seconds INTEGER DEFAULT 300
                );
                
                -- FIFO queue for waiting requests
                CREATE TABLE IF NOT EXISTS directory_lock_queue (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    queue_position INTEGER NOT NULL,
                    directory_path TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    process_id TEXT NOT NULL,
                    enqueued_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    timeout_seconds INTEGER DEFAULT 300,
                    status TEXT CHECK(status IN ('waiting', 'acquired', 'timeout', 'cancelled')) DEFAULT 'waiting',
                    UNIQUE(directory_path, task_id)
                );
                
                -- Complete audit log
                CREATE TABLE IF NOT EXISTS directory_lock_audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    operation TEXT CHECK(operation IN (
                        'LOCK_ACQUIRE', 'LOCK_RELEASE', 'LOCK_TIMEOUT', 
                        'QUEUE_ENQUEUE', 'QUEUE_DEQUEUE', 'QUEUE_TIMEOUT',
                        'CONFLICT_DETECTED', 'AUTO_RELEASE'
                    )),
                    task_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    process_id TEXT NOT NULL,
                    directory_path TEXT NOT NULL,
                    details JSON,
                    success BOOLEAN NOT NULL
                );
                
                -- Indexes for performance
                CREATE INDEX IF NOT EXISTS idx_locks_path ON directory_locks(directory_path);
                CREATE INDEX IF NOT EXISTS idx_locks_holder ON directory_locks(holder_task_id);
                CREATE INDEX IF NOT EXISTS idx_queue_path ON directory_lock_queue(directory_path);
                CREATE INDEX IF NOT EXISTS idx_queue_status ON directory_lock_queue(status);
                CREATE INDEX IF NOT EXISTS idx_queue_position ON directory_lock_queue(directory_path, queue_position);
                CREATE INDEX IF NOT EXISTS idx_audit_task ON directory_lock_audit_log(task_id);
                CREATE INDEX IF NOT EXISTS idx_audit_timestamp ON directory_lock_audit_log(timestamp);
            """)
    
    @contextmanager
    def _get_db(self):
        """Get database connection with proper error handling."""
        conn = sqlite3.connect(
            str(self.db_path),
            check_same_thread=False,
            timeout=30.0,
            isolation_level=None  # Autocommit mode for simplicity
        )
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    
    @contextmanager
    def _acquire_file_lock(self, timeout: float = 30.0):
        """
        Acquire file-based lock for cross-process mutual exclusion.
        
        This is critical for SQLite access across multiple processes.
        Uses fcntl for Unix-like systems.
        """
        lock_file = open(self._file_lock_path, 'w')
        try:
            # Try non-blocking first
            try:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except (IOError, OSError, BlockingIOError):
                logger.debug("Waiting for file lock...")
                # Blocking wait with timeout
                import signal
                
                def timeout_handler(signum, frame):
                    raise TimeoutError(f"File lock timeout after {timeout}s")
                
                old_handler = signal.signal(signal.SIGALRM, timeout_handler)
                signal.alarm(int(timeout))
                try:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
                finally:
                    signal.alarm(0)
                    signal.signal(signal.SIGALRM, old_handler)
            
            yield
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            lock_file.close()
    
    async def acquire_lock(
        self,
        directory_path: str,
        task_id: str,
        session_id: str,
        timeout_seconds: float = 300.0,
        lock_level: str = "write",
    ) -> bool:
        """
        Acquire a directory lock with FIFO queue.
        
        Args:
            directory_path: Path to the directory to lock
            task_id: Unique task identifier
            session_id: Session identifier
            timeout_seconds: Maximum time to wait for lock
            lock_level: 'read' or 'write' (default: write)
            
        Returns:
            True if lock acquired, False if timeout
        """
        normalized_path = str(Path(directory_path).resolve())
        process_id = str(os.getpid())
        start_time = datetime.utcnow()
        
        # First attempt: try to acquire immediately
        with self._acquire_file_lock():
            with self._get_db() as conn:
                # Check if lock is available
                existing = conn.execute(
                    """SELECT holder_task_id, holder_session_id, holder_process_id 
                       FROM directory_locks WHERE directory_path = ?""",
                    (normalized_path,)
                ).fetchone()
                
                if not existing:
                    # Lock available, acquire immediately
                    expires_at = start_time + timedelta(seconds=timeout_seconds)
                    conn.execute(
                        """INSERT INTO directory_locks 
                           (directory_path, holder_task_id, holder_session_id, 
                            holder_process_id, expires_at, lock_level, timeout_seconds)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (normalized_path, task_id, session_id, process_id, 
                         expires_at.isoformat(), lock_level, int(timeout_seconds))
                    )
                    
                    self._log_audit(conn, 'LOCK_ACQUIRE', task_id, session_id,
                                   process_id, normalized_path, 
                                   {"immediate": True, "timeout_seconds": timeout_seconds}, True)
                    
                    logger.info("Lock acquired immediately",
                               directory=normalized_path, task=task_id, 
                               session=session_id, process=process_id)
                    return True
                
                # Lock held by someone else, check compatibility
                existing_level = existing['lock_level'] if 'lock_level' in existing.keys() else 'write'
                if lock_level == 'read' and existing_level == 'read':
                    # Multiple read locks allowed
                    expires_at = start_time + timedelta(seconds=timeout_seconds)
                    conn.execute(
                        """INSERT INTO directory_locks 
                           (directory_path, holder_task_id, holder_session_id, 
                            holder_process_id, expires_at, lock_level, timeout_seconds)
                           VALUES (?, ?, ?, ?, ?, ?, ?)""",
                        (normalized_path, task_id, session_id, process_id,
                         expires_at.isoformat(), lock_level, int(timeout_seconds))
                    )
                    
                    self._log_audit(conn, 'LOCK_ACQUIRE', task_id, session_id,
                                   process_id, normalized_path,
                                   {"shared_read": True, "existing_holder": existing['holder_task_id']}, True)
                    
                    logger.info("Shared read lock acquired",
                               directory=normalized_path, task=task_id)
                    return True
                
                # Need to wait, join queue
                max_position = conn.execute(
                    """SELECT COALESCE(MAX(queue_position), 0) FROM directory_lock_queue 
                       WHERE directory_path = ? AND status = 'waiting'""",
                    (normalized_path,)
                ).fetchone()[0]
                
                queue_position = max_position + 1
                conn.execute(
                    """INSERT INTO directory_lock_queue 
                       (queue_position, directory_path, task_id, session_id, 
                        process_id, timeout_seconds)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (queue_position, normalized_path, task_id, session_id,
                     process_id, int(timeout_seconds))
                )
                
                self._log_audit(conn, 'QUEUE_ENQUEUE', task_id, session_id,
                               process_id, normalized_path,
                               {"queue_position": queue_position,
                                "current_holder": existing['holder_task_id']}, True)
                
                logger.info("Joined lock queue",
                           directory=normalized_path, task=task_id,
                           queue_position=queue_position, session=session_id)
        
        # Wait asynchronously for the lock
        return await self._wait_for_lock(
            normalized_path, task_id, session_id, process_id,
            timeout_seconds, start_time, queue_position
        )
    
    async def _wait_for_lock(
        self,
        directory_path: str,
        task_id: str,
        session_id: str,
        process_id: str,
        timeout_seconds: float,
        start_time: datetime,
        queue_position: int
    ) -> bool:
        """Wait asynchronously until lock is acquired or timeout."""
        check_interval = 0.5  # Check every 500ms
        
        while True:
            elapsed = (datetime.utcnow() - start_time).total_seconds()
            remaining = timeout_seconds - elapsed
            
            if remaining <= 0:
                # Timeout - remove from queue
                with self._acquire_file_lock():
                    with self._get_db() as conn:
                        conn.execute(
                            """UPDATE directory_lock_queue 
                               SET status = 'timeout' 
                               WHERE task_id = ? AND directory_path = ? AND status = 'waiting'""",
                            (task_id, directory_path)
                        )
                        self._log_audit(conn, 'QUEUE_TIMEOUT', task_id, session_id,
                                       process_id, directory_path,
                                       {"waited_seconds": elapsed, 
                                        "queue_position": queue_position}, False)
                
                logger.warning("Lock acquisition timeout",
                              directory=directory_path, task=task_id,
                              waited_seconds=elapsed)
                return False
            
            # Check if it's our turn
            with self._acquire_file_lock():
                with self._get_db() as conn:
                    # Check if we can acquire the lock
                    current_lock = conn.execute(
                        "SELECT 1 FROM directory_locks WHERE directory_path = ?",
                        (directory_path,)
                    ).fetchone()
                    
                    if not current_lock:
                        # Lock is free, check if we're first in queue
                        next_in_queue = conn.execute(
                            """SELECT task_id FROM directory_lock_queue 
                               WHERE directory_path = ? AND status = 'waiting'
                               ORDER BY queue_position LIMIT 1""",
                            (directory_path,)
                        ).fetchone()
                        
                        if next_in_queue and next_in_queue['task_id'] == task_id:
                            # It's our turn!
                            expires_at = datetime.utcnow() + timedelta(seconds=timeout_seconds)
                            conn.execute(
                                """INSERT INTO directory_locks 
                                   (directory_path, holder_task_id, holder_session_id, 
                                    holder_process_id, expires_at)
                                   VALUES (?, ?, ?, ?, ?)""",
                                (directory_path, task_id, session_id, process_id,
                                 expires_at.isoformat())
                            )
                            
                            conn.execute(
                                """UPDATE directory_lock_queue 
                                   SET status = 'acquired' 
                                   WHERE task_id = ? AND directory_path = ?""",
                                (task_id, directory_path)
                            )
                            
                            waited = (datetime.utcnow() - start_time).total_seconds()
                            self._log_audit(conn, 'LOCK_ACQUIRE', task_id, session_id,
                                           process_id, directory_path,
                                           {"waited_seconds": waited, 
                                            "from_queue": True,
                                            "queue_position": queue_position}, True)
                            
                            logger.info("Lock acquired from queue",
                                       directory=directory_path, task=task_id,
                                       waited_seconds=waited, session=session_id)
                            return True
            
            # Wait before next check
            try:
                await asyncio.wait_for(
                    self._stop_cleanup.wait(),
                    timeout=min(check_interval, remaining)
                )
                # Stop signal received
                return False
            except asyncio.TimeoutError:
                continue
    
    async def release_lock(
        self,
        directory_path: str,
        task_id: str,
        session_id: str
    ) -> bool:
        """
        Release a directory lock.
        
        Args:
            directory_path: Path to the locked directory
            task_id: Task that holds the lock
            session_id: Session identifier
            
        Returns:
            True if released, False if not holder
        """
        normalized_path = str(Path(directory_path).resolve())
        process_id = str(os.getpid())
        
        with self._acquire_file_lock():
            with self._get_db() as conn:
                # Verify we're the holder
                lock = conn.execute(
                    """SELECT * FROM directory_locks 
                       WHERE directory_path = ? AND holder_task_id = ?""",
                    (normalized_path, task_id)
                ).fetchone()
                
                if not lock:
                    self._log_audit(conn, 'LOCK_RELEASE', task_id, session_id,
                                   process_id, normalized_path,
                                   {"error": "Not lock holder"}, False)
                    return False
                
                # Calculate held duration
                acquired_at = datetime.fromisoformat(lock['acquired_at'])
                held_duration = (datetime.utcnow() - acquired_at).total_seconds()
                
                # Release the lock
                conn.execute(
                    "DELETE FROM directory_locks WHERE directory_path = ? AND holder_task_id = ?",
                    (normalized_path, task_id)
                )
                
                self._log_audit(conn, 'LOCK_RELEASE', task_id, session_id,
                               process_id, normalized_path,
                               {"held_duration_seconds": held_duration}, True)
                
                logger.info("Lock released",
                           directory=normalized_path, task=task_id,
                           held_duration=held_duration, session=session_id)
                return True
    
    def _log_audit(
        self,
        conn: sqlite3.Connection,
        operation: str,
        task_id: str,
        session_id: str,
        process_id: str,
        directory_path: str,
        details: dict,
        success: bool
    ) -> None:
        """Record audit log entry."""
        conn.execute(
            """INSERT INTO directory_lock_audit_log 
               (operation, task_id, session_id, process_id, directory_path, details, success)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (operation, task_id, session_id, process_id, directory_path,
             json.dumps(details), success)
        )
    
    async def start_cleanup_task(self, interval_seconds: float = 30.0) -> None:
        """Start background task to clean up expired locks."""
        self._stop_cleanup.clear()
        
        async def cleanup_loop():
            while not self._stop_cleanup.is_set():
                try:
                    await asyncio.wait_for(
                        self._stop_cleanup.wait(),
                        timeout=interval_seconds
                    )
                except asyncio.TimeoutError:
                    self._cleanup_expired_locks()
        
        self._cleanup_task = asyncio.create_task(cleanup_loop())
        logger.info("Cleanup task started", interval_seconds=interval_seconds)
    
    async def stop_cleanup_task(self) -> None:
        """Stop the background cleanup task."""
        self._stop_cleanup.set()
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
        logger.info("Cleanup task stopped")
    
    def _cleanup_expired_locks(self) -> int:
        """Clean up expired locks. Returns number of locks released."""
        released_count = 0
        now = datetime.utcnow().isoformat()
        
        with self._acquire_file_lock():
            with self._get_db() as conn:
                # Find expired locks
                expired = conn.execute(
                    """SELECT * FROM directory_locks WHERE expires_at < ?""",
                    (now,)
                ).fetchall()
                
                for lock in expired:
                    conn.execute(
                        "DELETE FROM directory_locks WHERE id = ?",
                        (lock['id'],)
                    )
                    
                    acquired_at = datetime.fromisoformat(lock['acquired_at'])
                    held_duration = (datetime.utcnow() - acquired_at).total_seconds()
                    
                    self._log_audit(conn, 'AUTO_RELEASE', lock['holder_task_id'],
                                   lock['holder_session_id'], lock['holder_process_id'],
                                   lock['directory_path'],
                                   {"expired_at": lock['expires_at'],
                                    "held_duration_seconds": held_duration}, True)
                    
                    logger.warning("Auto-released expired lock",
                                  directory=lock['directory_path'],
                                  task=lock['holder_task_id'],
                                  session=lock['holder_session_id'],
                                  held_duration=held_duration)
                    released_count += 1
        
        if released_count > 0:
            logger.info("Expired locks cleaned up", count=released_count)
        
        return released_count
    
    def get_lock_status(self, directory_path: str) -> Optional[dict]:
        """Get current lock status for a directory."""
        normalized_path = str(Path(directory_path).resolve())
        
        with self._acquire_file_lock():
            with self._get_db() as conn:
                lock = conn.execute(
                    """SELECT * FROM directory_locks WHERE directory_path = ?""",
                    (normalized_path,)
                ).fetchone()
                
                if not lock:
                    return None
                
                queue_length = conn.execute(
                    """SELECT COUNT(*) FROM directory_lock_queue 
                       WHERE directory_path = ? AND status = 'waiting'""",
                    (normalized_path,)
                ).fetchone()[0]
                
                return {
                    "directory": normalized_path,
                    "holder_task": lock['holder_task_id'],
                    "holder_session": lock['holder_session_id'],
                    "holder_process": lock['holder_process_id'],
                    "acquired_at": lock['acquired_at'],
                    "expires_at": lock['expires_at'],
                    "lock_level": lock['lock_level'],
                    "queue_length": queue_length,
                }
    
    def get_audit_log(
        self,
        task_id: Optional[str] = None,
        directory_path: Optional[str] = None,
        limit: int = 100,
        since: Optional[datetime] = None
    ) -> list[dict]:
        """Query audit log."""
        with self._acquire_file_lock():
            with self._get_db() as conn:
                query = "SELECT * FROM directory_lock_audit_log WHERE 1=1"
                params = []
                
                if task_id:
                    query += " AND task_id = ?"
                    params.append(task_id)
                
                if directory_path:
                    query += " AND directory_path = ?"
                    params.append(str(Path(directory_path).resolve()))
                
                if since:
                    query += " AND timestamp >= ?"
                    params.append(since.isoformat())
                
                query += " ORDER BY timestamp DESC LIMIT ?"
                params.append(limit)
                
                rows = conn.execute(query, params).fetchall()
                
                return [
                    {
                        "timestamp": row['timestamp'],
                        "operation": row['operation'],
                        "task_id": row['task_id'],
                        "session_id": row['session_id'],
                        "process_id": row['process_id'],
                        "directory_path": row['directory_path'],
                        "details": json.loads(row['details']) if row['details'] else {},
                        "success": bool(row['success']),
                    }
                    for row in rows
                ]


# Singleton instance
_lock_manager: Optional[PersistentDirectoryLockManager] = None


def get_directory_lock_manager(db_path: str = "./data/directory_locks.db") -> PersistentDirectoryLockManager:
    """Get or create singleton instance."""
    global _lock_manager
    if _lock_manager is None:
        _lock_manager = PersistentDirectoryLockManager(db_path)
    return _lock_manager
