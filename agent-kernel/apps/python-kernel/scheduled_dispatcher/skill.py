"""
Scheduled Request Skill - API for Prime Personality to create and manage scheduled requests.

This skill is ONLY exposed in Prime Personality context for security.
It provides methods to:
- Create delayed requests (e.g., "remind me in 30 minutes")
- Create cron-based recurring requests (e.g., "remind me every day at 9am")
- List scheduled requests
- Cancel scheduled requests

All requests are automatically signed to prevent tampering/hallucination.
"""
import os
from datetime import datetime, timedelta
from typing import List, Optional
from uuid import uuid4

import structlog

from scheduled_dispatcher.models import (
    ScheduledRequest,
    TriggerType,
    RequestStatus,
    create_scheduled_request,
)
from scheduled_dispatcher.storage import ScheduledRequestStorage

logger = structlog.get_logger()


class ScheduledRequestSkill:
    """
    Skill for Prime Personality to manage scheduled requests.
    
    This skill generates properly signed scheduled requests that the dispatcher
    will trigger at the appropriate time.
    """
    
    def __init__(self, storage: Optional[ScheduledRequestStorage] = None):
        """
        Initialize the skill.
        
        Args:
            storage: Storage instance (creates default if None)
        """
        base_path = os.getenv("DATA_PATH", "./data")
        self.storage = storage or ScheduledRequestStorage(base_path)
        self.logger = logger.bind(component="ScheduledRequestSkill")
    
    # ============================================================================
    # Core API Methods
    # ============================================================================
    
    async def create_delayed_request(
        self,
        session_id: str,
        user_id: str,
        content: str,
        delay_seconds: int,
        is_recurring: bool = False,
        metadata: dict = None,
    ) -> dict:
        """
        Create a delayed request that triggers after a specified time.
        
        Args:
            session_id: The session ID to associate with this request
            user_id: The user ID
            content: The message content to deliver when triggered
            delay_seconds: How many seconds to wait before triggering
            is_recurring: If True, repeats with the same delay
            metadata: Additional metadata
            
        Returns:
            Dictionary with request details including ID
            
        Example:
            {
                "success": True,
                "request_id": "uuid",
                "content": "Remind me to drink water",
                "trigger_at": "2026-03-10T10:30:00",
                "delay_seconds": 1800,
            }
        """
        try:
            # Calculate trigger time
            next_trigger = datetime.utcnow() + timedelta(seconds=delay_seconds)
            
            # Create the request with signature
            request = create_scheduled_request(
                content=content,
                session_id=session_id,
                user_id=user_id,
                trigger_type=TriggerType.DELAYED,
                trigger_config={"delay_seconds": delay_seconds},
                next_trigger_at=next_trigger,
                is_recurring=is_recurring,
                metadata=metadata,
            )
            
            # Save to storage
            self.storage.save_scheduled_request(request)
            
            self.logger.info(
                "Created delayed request",
                request_id=request.id,
                session_id=session_id,
                delay_seconds=delay_seconds,
                is_recurring=is_recurring,
            )
            
            return {
                "success": True,
                "request_id": request.id,
                "content": content,
                "trigger_at": request.next_trigger_at.isoformat(),
                "delay_seconds": delay_seconds,
                "is_recurring": is_recurring,
            }
            
        except Exception as e:
            self.logger.error(
                "Failed to create delayed request",
                session_id=session_id,
                error=str(e),
            )
            return {
                "success": False,
                "error": f"Failed to create delayed request: {str(e)}",
            }
    
    async def create_cron_request(
        self,
        session_id: str,
        user_id: str,
        content: str,
        cron_expression: str,
        metadata: dict = None,
    ) -> dict:
        """
        Create a cron-based recurring request.
        
        Args:
            session_id: The session ID to associate with this request
            user_id: The user ID
            content: The message content to deliver when triggered
            cron_expression: Standard cron expression (e.g., "0 9 * * *" for 9am daily)
            metadata: Additional metadata
            
        Returns:
            Dictionary with request details including ID
            
        Cron Expression Format:
            * * * * *
            | | | | |
            | | | | +----- Day of week (0-7, where 0 and 7 are Sunday)
            | | | +------- Month (1-12)
            | | +--------- Day of month (1-31)
            | +----------- Hour (0-23)
            +------------- Minute (0-59)
            
        Examples:
            "0 9 * * *"    - Every day at 9:00 AM
            "0 */6 * * *"  - Every 6 hours
            "0 9 * * 1"    - Every Monday at 9:00 AM
            "0 0 1 * *"    - First day of every month at midnight
            
        Returns:
            {
                "success": True,
                "request_id": "uuid",
                "content": "Daily standup reminder",
                "cron_expression": "0 9 * * *",
                "next_trigger_at": "2026-03-11T09:00:00",
            }
        """
        try:
            from croniter import croniter
            
            # Validate cron expression
            try:
                itr = croniter(cron_expression, datetime.utcnow())
                next_trigger = itr.get_next(datetime)
            except Exception as e:
                return {
                    "success": False,
                    "error": f"Invalid cron expression: {str(e)}",
                }
            
            # Create the request with signature
            request = create_scheduled_request(
                content=content,
                session_id=session_id,
                user_id=user_id,
                trigger_type=TriggerType.CRON,
                trigger_config={"cron_expr": cron_expression},
                next_trigger_at=next_trigger,
                is_recurring=True,
                metadata=metadata,
            )
            
            # Save to storage
            self.storage.save_scheduled_request(request)
            
            self.logger.info(
                "Created cron request",
                request_id=request.id,
                session_id=session_id,
                cron_expression=cron_expression,
                next_trigger=next_trigger.isoformat(),
            )
            
            return {
                "success": True,
                "request_id": request.id,
                "content": content,
                "cron_expression": cron_expression,
                "next_trigger_at": next_trigger.isoformat(),
            }
            
        except Exception as e:
            self.logger.error(
                "Failed to create cron request",
                session_id=session_id,
                error=str(e),
            )
            return {
                "success": False,
                "error": f"Failed to create cron request: {str(e)}",
            }
    
    async def list_scheduled_requests(
        self,
        session_id: Optional[str] = None,
        status: str = "pending",
        limit: int = 50,
    ) -> dict:
        """
        List scheduled requests.
        
        Args:
            session_id: Filter by session ID (None for all sessions)
            status: Filter by status (pending, paused, cancelled)
            limit: Maximum number of results
            
        Returns:
            {
                "success": True,
                "count": 2,
                "requests": [
                    {
                        "id": "uuid",
                        "content": "Remind me to drink water",
                        "trigger_type": "delayed",
                        "next_trigger_at": "2026-03-10T10:30:00",
                        "is_recurring": False,
                        "status": "pending",
                    },
                    ...
                ]
            }
        """
        try:
            # Parse status
            try:
                status_enum = RequestStatus(status.lower())
            except ValueError:
                status_enum = RequestStatus.PENDING
            
            # Get requests from storage
            requests = self.storage.list_scheduled_requests(
                session_id=session_id,
                status=status_enum,
                limit=limit,
            )
            
            # Format for response
            formatted_requests = []
            for req in requests:
                formatted_requests.append({
                    "id": req.id,
                    "content": req.content,
                    "trigger_type": req.trigger_type.value,
                    "trigger_config": req.trigger_config,
                    "next_trigger_at": req.next_trigger_at.isoformat(),
                    "is_recurring": req.is_recurring,
                    "total_triggered": req.total_triggered,
                    "last_triggered_at": req.last_triggered_at.isoformat() if req.last_triggered_at else None,
                    "status": req.status.value,
                    "created_at": req.created_at.isoformat(),
                })
            
            return {
                "success": True,
                "count": len(formatted_requests),
                "requests": formatted_requests,
            }
            
        except Exception as e:
            self.logger.error(
                "Failed to list scheduled requests",
                session_id=session_id,
                error=str(e),
            )
            return {
                "success": False,
                "error": f"Failed to list requests: {str(e)}",
            }
    
    async def get_scheduled_request(
        self,
        request_id: str,
    ) -> dict:
        """
        Get details of a specific scheduled request.
        
        Args:
            request_id: The ID of the request to get
            
        Returns:
            Full request details or error
        """
        try:
            request = self.storage.get_scheduled_request(request_id)
            
            if not request:
                return {
                    "success": False,
                    "error": f"Request not found: {request_id}",
                }
            
            return {
                "success": True,
                "request": {
                    "id": request.id,
                    "content": request.content,
                    "session_id": request.session_id,
                    "user_id": request.user_id,
                    "trigger_type": request.trigger_type.value,
                    "trigger_config": request.trigger_config,
                    "next_trigger_at": request.next_trigger_at.isoformat(),
                    "is_recurring": request.is_recurring,
                    "total_triggered": request.total_triggered,
                    "last_triggered_at": request.last_triggered_at.isoformat() if request.last_triggered_at else None,
                    "status": request.status.value,
                    "created_at": request.created_at.isoformat(),
                    "metadata": request.metadata,
                }
            }
            
        except Exception as e:
            self.logger.error(
                "Failed to get scheduled request",
                request_id=request_id,
                error=str(e),
            )
            return {
                "success": False,
                "error": f"Failed to get request: {str(e)}",
            }
    
    async def cancel_scheduled_request(
        self,
        request_id: str,
        reason: str = None,
    ) -> dict:
        """
        Cancel a pending scheduled request.
        
        Args:
            request_id: The ID of the request to cancel
            reason: Optional reason for cancellation
            
        Returns:
            Success/failure status
        """
        try:
            request = self.storage.get_scheduled_request(request_id)
            
            if not request:
                return {
                    "success": False,
                    "error": f"Request not found: {request_id}",
                }
            
            if request.status != RequestStatus.PENDING:
                return {
                    "success": False,
                    "error": f"Cannot cancel request with status: {request.status.value}",
                }
            
            # Update status to cancelled
            request.status = RequestStatus.CANCELLED
            self.storage.update_scheduled_request(request)
            
            self.logger.info(
                "Cancelled scheduled request",
                request_id=request_id,
                reason=reason,
            )
            
            return {
                "success": True,
                "request_id": request_id,
                "message": f"Request {request_id} has been cancelled",
            }
            
        except Exception as e:
            self.logger.error(
                "Failed to cancel scheduled request",
                request_id=request_id,
                error=str(e),
            )
            return {
                "success": False,
                "error": f"Failed to cancel request: {str(e)}",
            }
    
    async def pause_scheduled_request(
        self,
        request_id: str,
        reason: str = None,
    ) -> dict:
        """
        Pause a pending scheduled request (can be resumed later).
        
        Args:
            request_id: The ID of the request to pause
            reason: Optional reason for pausing
            
        Returns:
            Success/failure status
        """
        try:
            request = self.storage.get_scheduled_request(request_id)
            
            if not request:
                return {
                    "success": False,
                    "error": f"Request not found: {request_id}",
                }
            
            if request.status != RequestStatus.PENDING:
                return {
                    "success": False,
                    "error": f"Cannot pause request with status: {request.status.value}",
                }
            
            # Update status to paused
            request.status = RequestStatus.PAUSED
            self.storage.update_scheduled_request(request)
            
            self.logger.info(
                "Paused scheduled request",
                request_id=request_id,
                reason=reason,
            )
            
            return {
                "success": True,
                "request_id": request_id,
                "message": f"Request {request_id} has been paused",
            }
            
        except Exception as e:
            self.logger.error(
                "Failed to pause scheduled request",
                request_id=request_id,
                error=str(e),
            )
            return {
                "success": False,
                "error": f"Failed to pause request: {str(e)}",
            }
    
    async def resume_scheduled_request(
        self,
        request_id: str,
    ) -> dict:
        """
        Resume a paused scheduled request.
        
        Args:
            request_id: The ID of the request to resume
            
        Returns:
            Success/failure status
        """
        try:
            request = self.storage.get_scheduled_request(request_id)
            
            if not request:
                return {
                    "success": False,
                    "error": f"Request not found: {request_id}",
                }
            
            if request.status != RequestStatus.PAUSED:
                return {
                    "success": False,
                    "error": f"Cannot resume request with status: {request.status.value}",
                }
            
            # Update status back to pending
            request.status = RequestStatus.PENDING
            self.storage.update_scheduled_request(request)
            
            self.logger.info(
                "Resumed scheduled request",
                request_id=request_id,
            )
            
            return {
                "success": True,
                "request_id": request_id,
                "message": f"Request {request_id} has been resumed",
            }
            
        except Exception as e:
            self.logger.error(
                "Failed to resume scheduled request",
                request_id=request_id,
                error=str(e),
            )
            return {
                "success": False,
                "error": f"Failed to resume request: {str(e)}",
            }
    
    # ============================================================================
    # Utility Methods
    # ============================================================================
    
    async def get_statistics(self) -> dict:
        """Get statistics about scheduled requests."""
        try:
            stats = self.storage.get_statistics()
            return {
                "success": True,
                "statistics": stats,
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"Failed to get statistics: {str(e)}",
            }
