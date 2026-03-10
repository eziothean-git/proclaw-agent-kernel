"""
Scheduled Request Storage - File-based storage for scheduled requests.

This module provides file-based storage for scheduled requests with full audit trail.
Organized as:
- scheduled/: Current pending requests
- triggered/{date}/: Audit logs of triggered requests
- failed/: Failed attempts for retry
- index.jsonl: Operation log
"""
import json
import os
import shutil
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import structlog

from scheduled_dispatcher.models import (
    ScheduledRequest,
    TriggeredRecord,
    FailedRecord,
    RequestStatus,
    get_scheduled_dir,
    get_triggered_dir,
    get_failed_dir,
    get_scheduler_index_path,
)

logger = structlog.get_logger()


class ScheduledRequestStorage:
    """
    File-based storage for scheduled requests.
    
    All operations are logged to index.jsonl for audit purposes.
    """
    
    def __init__(self, base_path: str = "./data"):
        self.base_path = Path(base_path)
        self._ensure_directories()
        self.logger = logger.bind(component="ScheduledRequestStorage")
    
    def _ensure_directories(self) -> None:
        """Create necessary directories if they don't exist."""
        for dir_path in [
            get_scheduled_dir(str(self.base_path)),
            get_triggered_dir(str(self.base_path)),
            get_failed_dir(str(self.base_path)),
        ]:
            Path(dir_path).mkdir(parents=True, exist_ok=True)
    
    def _write_json(self, path: Path, data: dict) -> None:
        """Write JSON data to file atomically."""
        # Write to temp file first, then rename for atomicity
        temp_path = path.with_suffix('.tmp')
        with open(temp_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
        temp_path.rename(path)
    
    def _read_json(self, path: Path) -> Optional[dict]:
        """Read JSON data from file."""
        if not path.exists():
            return None
        try:
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return None
    
    def _log_operation(self, operation: str, request_id: str, details: dict = None) -> None:
        """Log an operation to the index file."""
        index_path = Path(get_scheduler_index_path(str(self.base_path)))
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "operation": operation,
            "request_id": request_id,
            "details": details or {},
        }
        with open(index_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry, ensure_ascii=False, default=str) + '\n')
    
    # ============================================================================
    # Scheduled Request CRUD
    # ============================================================================
    
    def save_scheduled_request(self, request: ScheduledRequest) -> None:
        """Save or update a scheduled request."""
        path = Path(get_scheduled_dir(str(self.base_path))) / f"{request.id}.json"
        self._write_json(path, request.to_storage_dict())
        self._log_operation("save", request.id, {"trigger_at": request.next_trigger_at.isoformat()})
        self.logger.debug("Saved scheduled request", request_id=request.id)
    
    def get_scheduled_request(self, request_id: str) -> Optional[ScheduledRequest]:
        """Get a scheduled request by ID."""
        path = Path(get_scheduled_dir(str(self.base_path))) / f"{request_id}.json"
        data = self._read_json(path)
        if data:
            return ScheduledRequest.from_storage_dict(data)
        return None
    
    def list_scheduled_requests(
        self,
        session_id: Optional[str] = None,
        status: Optional[RequestStatus] = None,
        limit: int = 100,
    ) -> List[ScheduledRequest]:
        """List scheduled requests with optional filtering."""
        scheduled_dir = Path(get_scheduled_dir(str(self.base_path)))
        requests = []
        
        for file_path in scheduled_dir.glob("*.json"):
            data = self._read_json(file_path)
            if not data:
                continue
            
            request = ScheduledRequest.from_storage_dict(data)
            
            # Apply filters
            if session_id and request.session_id != session_id:
                continue
            if status and request.status != status:
                continue
            
            requests.append(request)
        
        # Sort by next trigger time, then limit
        requests.sort(key=lambda r: r.next_trigger_at)
        return requests[:limit]
    
    def delete_scheduled_request(self, request_id: str) -> bool:
        """Delete a scheduled request (hard delete)."""
        path = Path(get_scheduled_dir(str(self.base_path))) / f"{request_id}.json"
        if path.exists():
            path.unlink()
            self._log_operation("delete", request_id)
            self.logger.debug("Deleted scheduled request", request_id=request_id)
            return True
        return False
    
    def update_scheduled_request(self, request: ScheduledRequest) -> None:
        """Update an existing scheduled request."""
        self.save_scheduled_request(request)
        self._log_operation("update", request.id, {"status": request.status.value})
    
    # ============================================================================
    # Triggered Records (Audit Trail)
    # ============================================================================
    
    def save_triggered_record(self, record: TriggeredRecord) -> Path:
        """
        Save a triggered record to the audit log.
        
        Returns the path where the record was saved.
        """
        triggered_dir = Path(get_triggered_dir(str(self.base_path)))
        triggered_dir.mkdir(parents=True, exist_ok=True)
        
        # Include timestamp in filename for uniqueness
        timestamp = datetime.utcnow().strftime("%H%M%S")
        filename = f"{record.original_request_id}_{timestamp}.json"
        path = triggered_dir / filename
        
        self._write_json(path, record.to_storage_dict())
        self._log_operation(
            "triggered",
            record.original_request_id,
            {
                "status": record.status,
                "inbox_path": record.inbox_path,
                "signature_valid": record.signature_valid,
            }
        )
        self.logger.info(
            "Saved triggered record",
            request_id=record.original_request_id,
            status=record.status,
        )
        return path
    
    def list_triggered_records(
        self,
        request_id: Optional[str] = None,
        session_id: Optional[str] = None,
        date_str: Optional[str] = None,
        limit: int = 100,
    ) -> List[TriggeredRecord]:
        """List triggered records with optional filtering."""
        triggered_dir = Path(get_triggered_dir(str(self.base_path), date_str))
        
        if not triggered_dir.exists():
            return []
        
        records = []
        for file_path in triggered_dir.glob("*.json"):
            data = self._read_json(file_path)
            if not data:
                continue
            
            record = TriggeredRecord.from_storage_dict(data)
            
            # Apply filters
            if request_id and record.original_request_id != request_id:
                continue
            if session_id and record.session_id != session_id:
                continue
            
            records.append(record)
        
        # Sort by trigger time descending
        records.sort(key=lambda r: r.triggered_at, reverse=True)
        return records[:limit]
    
    # ============================================================================
    # Failed Records (Retry Queue)
    # ============================================================================
    
    def save_failed_record(self, record: FailedRecord) -> None:
        """Save a failed record for retry."""
        failed_dir = Path(get_failed_dir(str(self.base_path)))
        failed_dir.mkdir(parents=True, exist_ok=True)
        
        # Include timestamp in filename
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        filename = f"{record.original_request_id}_{timestamp}.json"
        path = failed_dir / filename
        
        self._write_json(path, record.to_storage_dict())
        self._log_operation(
            "failed",
            record.original_request_id,
            {
                "error": record.error_message,
                "retry_count": record.retry_count,
                "next_retry": record.next_retry_at.isoformat(),
            }
        )
        self.logger.warning(
            "Saved failed record for retry",
            request_id=record.original_request_id,
            error=record.error_message,
            retry_count=record.retry_count,
        )
    
    def list_failed_records(self, ready_to_retry: bool = True) -> List[FailedRecord]:
        """
        List failed records.
        
        Args:
            ready_to_retry: If True, only return records where next_retry_at <= now
        """
        failed_dir = Path(get_failed_dir(str(self.base_path)))
        
        if not failed_dir.exists():
            return []
        
        now = datetime.utcnow()
        records = []
        
        for file_path in failed_dir.glob("*.json"):
            data = self._read_json(file_path)
            if not data:
                continue
            
            record = FailedRecord(**data)
            
            if ready_to_retry and record.next_retry_at > now:
                continue
            
            records.append(record)
        
        # Sort by next retry time
        records.sort(key=lambda r: r.next_retry_at)
        return records
    
    def remove_failed_record(self, request_id: str, failed_at_str: str) -> bool:
        """Remove a failed record (after successful retry)."""
        failed_dir = Path(get_failed_dir(str(self.base_path)))
        
        # Find file by pattern: {request_id}_{timestamp}.json
        for file_path in failed_dir.glob(f"{request_id}_*.json"):
            data = self._read_json(file_path)
            if data and data.get("failed_at") == failed_at_str:
                file_path.unlink()
                self._log_operation("retry_succeeded", request_id)
                return True
        
        return False
    
    # ============================================================================
    # Utility Methods
    # ============================================================================
    
    def get_due_requests(self, before: Optional[datetime] = None) -> List[ScheduledRequest]:
        """Get all pending requests that are due to trigger."""
        if before is None:
            before = datetime.utcnow()
        
        all_pending = self.list_scheduled_requests(status=RequestStatus.PENDING)
        return [r for r in all_pending if r.next_trigger_at <= before]
    
    def cleanup_old_triggered_records(self, days: int = 30) -> int:
        """Clean up triggered records older than N days."""
        triggered_base = Path(get_triggered_dir(str(self.base_path))).parent
        cutoff = datetime.utcnow().timestamp() - (days * 24 * 60 * 60)
        removed = 0
        
        for date_dir in triggered_base.iterdir():
            if date_dir.is_dir():
                try:
                    dir_time = datetime.strptime(date_dir.name, "%Y-%m-%d").timestamp()
                    if dir_time < cutoff:
                        shutil.rmtree(date_dir)
                        removed += 1
                        self.logger.info("Cleaned up old triggered records", date_dir=date_dir.name)
                except ValueError:
                    continue
        
        return removed
    
    def get_statistics(self) -> dict:
        """Get storage statistics."""
        scheduled_dir = Path(get_scheduled_dir(str(self.base_path)))
        triggered_dir = Path(get_triggered_dir(str(self.base_path))).parent
        failed_dir = Path(get_failed_dir(str(self.base_path)))
        
        stats = {
            "scheduled_pending": len(list(scheduled_dir.glob("*.json"))),
            "triggered_total": 0,
            "failed_pending": len(list(failed_dir.glob("*.json"))),
        }
        
        # Count triggered records across all dates
        if triggered_dir.exists():
            for date_dir in triggered_dir.iterdir():
                if date_dir.is_dir():
                    stats["triggered_total"] += len(list(date_dir.glob("*.json")))
        
        return stats
