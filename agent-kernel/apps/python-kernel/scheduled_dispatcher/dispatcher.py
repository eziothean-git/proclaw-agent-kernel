"""
Scheduled Request Dispatcher - Core scheduling engine.

This module provides the background task that:
1. Scans for due scheduled requests
2. Verifies their signatures
3. Triggers them by writing to inbox
4. Handles retries for failed attempts
5. Updates recurring tasks with next trigger time
"""
import asyncio
import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from uuid import uuid4

import structlog
from croniter import croniter

from scheduled_dispatcher.models import (
    ScheduledRequest,
    TriggeredRecord,
    FailedRecord,
    TriggerType,
    verify_signature,
)
from scheduled_dispatcher.storage import ScheduledRequestStorage

logger = structlog.get_logger()


class ScheduledRequestDispatcher:
    """
    Background dispatcher for scheduled requests.
    
    Runs continuously, checking for due requests and triggering them.
    All operations are logged for audit purposes.
    """
    
    def __init__(
        self,
        storage: ScheduledRequestStorage,
        inbox_path: str,
        check_interval: float = 60.0,
        max_retries: int = 3,
        retry_delays: list = None,
    ):
        """
        Initialize the dispatcher.
        
        Args:
            storage: Storage instance for scheduled requests
            inbox_path: Path to the gateway inbox directory
            check_interval: How often to check for due requests (seconds)
            max_retries: Maximum retry attempts for failed triggers
            retry_delays: Delay between retries in seconds [1st, 2nd, 3rd, ...]
        """
        self.storage = storage
        self.inbox_path = Path(inbox_path)
        self.check_interval = check_interval
        self.max_retries = max_retries
        self.retry_delays = retry_delays or [60, 300, 900]  # 1min, 5min, 15min
        
        self._running = False
        self._task: Optional[asyncio.Task] = None
        self.logger = logger.bind(component="ScheduledRequestDispatcher")
        
        # Ensure inbox directory exists
        self.inbox_path.mkdir(parents=True, exist_ok=True)
    
    async def start(self) -> None:
        """Start the dispatcher background task."""
        if self._running:
            self.logger.warning("Dispatcher already running")
            return
        
        self._running = True
        self._task = asyncio.create_task(self._run_loop())
        self.logger.info(
            "Dispatcher started",
            check_interval=self.check_interval,
            inbox_path=str(self.inbox_path),
        )
    
    async def stop(self) -> None:
        """Stop the dispatcher."""
        if not self._running:
            return
        
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        
        self.logger.info("Dispatcher stopped")
    
    async def _run_loop(self) -> None:
        """Main loop that continuously checks for due requests."""
        while self._running:
            try:
                await self._check_and_dispatch()
            except Exception as e:
                self.logger.error("Error in dispatch loop", error=str(e), exc_info=True)
            
            try:
                await asyncio.sleep(self.check_interval)
            except asyncio.CancelledError:
                break
    
    async def _check_and_dispatch(self) -> None:
        """Check for due requests and dispatch them."""
        now = datetime.utcnow()
        
        # 1. Process scheduled requests that are due
        due_requests = self.storage.get_due_requests(before=now)
        
        if due_requests:
            self.logger.info(f"Found {len(due_requests)} due requests")
            
            for request in due_requests:
                await self._dispatch_request(request)
        
        # 2. Process failed records that are ready for retry
        failed_records = self.storage.list_failed_records(ready_to_retry=True)
        
        if failed_records:
            self.logger.info(f"Found {len(failed_records)} failed records ready for retry")
            
            for record in failed_records:
                await self._retry_failed_record(record)
    
    async def _dispatch_request(self, request: ScheduledRequest) -> None:
        """
        Dispatch a single scheduled request.
        
        Flow:
        1. Verify signature
        2. Write to inbox
        3. Create triggered record
        4. Update recurring task or delete one-time task
        """
        self.logger.info(
            "Dispatching scheduled request",
            request_id=request.id,
            session_id=request.session_id,
            trigger_type=request.trigger_type.value,
        )
        
        # 1. Verify signature
        is_valid = verify_signature(request)
        
        if not is_valid:
            self.logger.error(
                "Signature verification failed",
                request_id=request.id,
                signature=request.prime_signature,
            )
            
            # Record the failure but don't retry - signature failures are permanent
            triggered_record = TriggeredRecord(
                original_request_id=request.id,
                signature_valid=False,
                session_id=request.session_id,
                content_snapshot=request.content,
                status="failed",
                error_message="Invalid signature - possible tampering or hallucination",
            )
            self.storage.save_triggered_record(triggered_record)
            
            # Delete the invalid request
            self.storage.delete_scheduled_request(request.id)
            return
        
        # 2. Write to inbox (with retry logic)
        inbox_path = None
        retry_count = 0
        error_msg = None
        
        try:
            inbox_path = await self._write_to_inbox_with_retry(request)
        except Exception as e:
            error_msg = str(e)
            retry_count = self.max_retries
            self.logger.error(
                "Failed to write to inbox after retries",
                request_id=request.id,
                error=error_msg,
            )
        
        # 3. Create triggered record
        triggered_record = TriggeredRecord(
            original_request_id=request.id,
            trigger_sequence=request.total_triggered + 1,
            signature_valid=is_valid,
            inbox_path=inbox_path,
            retry_count=retry_count,
            error_message=error_msg,
            status="success" if inbox_path else "failed",
            session_id=request.session_id,
            content_snapshot=request.content,
        )
        self.storage.save_triggered_record(triggered_record)
        
        # 4. Update request state
        if inbox_path:
            # Success
            request.total_triggered += 1
            request.last_triggered_at = datetime.utcnow()
            
            if request.is_recurring:
                # Calculate next trigger time for recurring requests
                next_trigger = self._calculate_next_trigger(request)
                if next_trigger:
                    request.next_trigger_at = next_trigger
                    self.storage.update_scheduled_request(request)
                    self.logger.info(
                        "Updated recurring request with next trigger time",
                        request_id=request.id,
                        next_trigger=next_trigger.isoformat(),
                    )
                else:
                    # Could not calculate next trigger, delete it
                    self.storage.delete_scheduled_request(request.id)
                    self.logger.warning(
                        "Deleted recurring request - could not calculate next trigger",
                        request_id=request.id,
                    )
            else:
                # One-time request, delete it
                self.storage.delete_scheduled_request(request.id)
                self.logger.info("Completed one-time request", request_id=request.id)
        else:
            # Failed to write to inbox, create failed record for retry
            failed_record = FailedRecord(
                original_request_id=request.id,
                error_message=error_msg or "Unknown error",
                retry_count=0,
                next_retry_at=datetime.utcnow() + timedelta(seconds=self.retry_delays[0]),
                request_data=request.to_storage_dict(),
            )
            self.storage.save_failed_record(failed_record)
            
            # Delete from scheduled to avoid re-triggering until retry succeeds
            self.storage.delete_scheduled_request(request.id)
    
    async def _write_to_inbox_with_retry(self, request: ScheduledRequest) -> str:
        """
        Write a request to the inbox with retry logic.
        
        Args:
            request: The scheduled request to write
            
        Returns:
            Path to the created inbox file
            
        Raises:
            Exception: If all retries fail
        """
        inbox_request = self._create_inbox_request(request)
        
        for attempt in range(self.max_retries):
            try:
                return await self._write_to_inbox(inbox_request)
            except Exception as e:
                if attempt == self.max_retries - 1:
                    raise
                
                delay = self.retry_delays[min(attempt, len(self.retry_delays) - 1)]
                self.logger.warning(
                    "Inbox write failed, retrying",
                    request_id=request.id,
                    attempt=attempt + 1,
                    delay=delay,
                    error=str(e),
                )
                await asyncio.sleep(delay)
        
        # Should never reach here
        raise Exception("Max retries exceeded")
    
    async def _write_to_inbox(self, request_data: dict) -> str:
        """
        Write a request to the inbox directory.
        
        This creates both the request file and updates the index.
        """
        request_id = request_data["id"]
        
        # Create date-based directory
        date_str = datetime.utcnow().strftime("%Y-%m-%d")
        date_dir = self.inbox_path / date_str
        date_dir.mkdir(parents=True, exist_ok=True)
        
        # Write request file
        request_file = date_dir / f"{request_id}.json"
        with open(request_file, 'w', encoding='utf-8') as f:
            json.dump(request_data, f, indent=2, ensure_ascii=False, default=str)
        
        # Update index
        index_file = self.inbox_path / "index.jsonl"
        index_entry = {
            "requestId": request_id,
            "status": "pending",
            "path": str(request_file),
            "timestamp": datetime.utcnow().isoformat(),
            "priority": 5,  # Default priority
        }
        
        with open(index_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(index_entry, ensure_ascii=False) + '\n')
        
        self.logger.debug("Wrote request to inbox", request_id=request_id, path=str(request_file))
        return str(request_file)
    
    def _create_inbox_request(self, scheduled: ScheduledRequest) -> dict:
        """Convert a scheduled request to inbox format."""
        return {
            "id": str(uuid4()),  # New ID for the inbox request
            "header": {
                "sessionId": scheduled.session_id,
                "userId": scheduled.user_id,
                "platform": "scheduled",
                "source": "scheduled_dispatcher",
                "originalRequestId": scheduled.id,
            },
            "body": scheduled.content,
            "metadata": {
                "scheduled_request_id": scheduled.id,
                "trigger_type": scheduled.trigger_type.value,
                "is_scheduled": True,
                "trigger_sequence": scheduled.total_triggered + 1,
            }
        }
    
    def _calculate_next_trigger(self, request: ScheduledRequest) -> Optional[datetime]:
        """
        Calculate the next trigger time for a recurring request.
        
        Args:
            request: The recurring scheduled request
            
        Returns:
            Next trigger datetime or None if cannot calculate
        """
        if request.trigger_type == TriggerType.CRON:
            # Parse cron expression
            cron_expr = request.trigger_config.get("cron_expr")
            if not cron_expr:
                return None
            
            try:
                itr = croniter(cron_expr, request.last_triggered_at or request.created_at)
                return itr.get_next(datetime)
            except Exception as e:
                self.logger.error(
                    "Failed to parse cron expression",
                    request_id=request.id,
                    cron_expr=cron_expr,
                    error=str(e),
                )
                return None
        
        elif request.trigger_type == TriggerType.DELAYED:
            # For delayed requests treated as recurring, use the same delay
            delay_seconds = request.trigger_config.get("delay_seconds", 3600)
            return request.last_triggered_at + timedelta(seconds=delay_seconds)
        
        return None
    
    async def _retry_failed_record(self, record: FailedRecord) -> None:
        """
        Retry a failed trigger attempt.
        """
        self.logger.info(
            "Retrying failed record",
            request_id=record.original_request_id,
            retry_count=record.retry_count + 1,
        )
        
        try:
            # Recreate the scheduled request from stored data
            request_data = record.request_data
            request = ScheduledRequest.from_storage_dict(request_data)
            
            # Attempt to dispatch
            inbox_path = await self._write_to_inbox_with_retry(request)
            
            # Success! Create triggered record
            triggered_record = TriggeredRecord(
                original_request_id=request.id,
                trigger_sequence=request.total_triggered + 1,
                signature_valid=True,
                inbox_path=inbox_path,
                retry_count=record.retry_count + 1,
                status="success",
                session_id=request.session_id,
                content_snapshot=request.content,
            )
            self.storage.save_triggered_record(triggered_record)
            
            # Remove from failed records
            self.storage.remove_failed_record(
                record.original_request_id,
                record.failed_at.isoformat()
            )
            
            # For recurring requests, update with next trigger
            if request.is_recurring:
                request.total_triggered += 1
                request.last_triggered_at = datetime.utcnow()
                next_trigger = self._calculate_next_trigger(request)
                if next_trigger:
                    request.next_trigger_at = next_trigger
                    self.storage.save_scheduled_request(request)
            
            self.logger.info(
                "Retry succeeded",
                request_id=record.original_request_id,
                inbox_path=inbox_path,
            )
            
        except Exception as e:
            # Still failed, update retry count and schedule next retry
            record.retry_count += 1
            
            if record.retry_count >= self.max_retries:
                # Max retries exceeded, mark as permanently failed
                triggered_record = TriggeredRecord(
                    original_request_id=record.original_request_id,
                    trigger_sequence=0,
                    signature_valid=True,
                    retry_count=record.retry_count,
                    error_message=f"Max retries exceeded: {str(e)}",
                    status="failed",
                    session_id=record.request_data.get("session_id", ""),
                    content_snapshot=record.request_data.get("content", ""),
                )
                self.storage.save_triggered_record(triggered_record)
                
                # Remove from failed records
                self.storage.remove_failed_record(
                    record.original_request_id,
                    record.failed_at.isoformat()
                )
                
                self.logger.error(
                    "Max retries exceeded, request permanently failed",
                    request_id=record.original_request_id,
                    error=str(e),
                )
            else:
                # Schedule next retry
                delay = self.retry_delays[min(record.retry_count, len(self.retry_delays) - 1)]
                record.next_retry_at = datetime.utcnow() + timedelta(seconds=delay)
                self.storage.save_failed_record(record)
                
                self.logger.warning(
                    "Retry failed, scheduled next attempt",
                    request_id=record.original_request_id,
                    retry_count=record.retry_count,
                    next_retry=record.next_retry_at.isoformat(),
                    error=str(e),
                )
    
    def get_statistics(self) -> dict:
        """Get dispatcher statistics."""
        return {
            **self.storage.get_statistics(),
            "running": self._running,
            "check_interval": self.check_interval,
            "inbox_path": str(self.inbox_path),
        }
