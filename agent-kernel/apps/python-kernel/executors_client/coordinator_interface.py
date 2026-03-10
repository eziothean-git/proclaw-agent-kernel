"""
Request Execution Coordinator - Unified execution interface for all agent requests.

This is the cross-session shared execution interface that:
1. Receives standardized ExecutionRequest from any agent
2. Routes to appropriate backend (local skill or remote executor)
3. Manages execution lifecycle
4. Ensures atomicity and consistency
5. Generates standardized events
"""
import time
import uuid
from datetime import datetime
from typing import Any

import structlog

from executors_client.local_skill_registry import get_local_skill_registry
from executors_client.remote_executor_client import get_remote_executor_client
from skills.agentic_os_interface import get_os_interface_skill
from thread_runtime.models import (
    ExecutionRequest,
    ExecutionResult,
    ExecutionTicket,
    RequestType,
)
from schemas.models import ToolCallRequest, ToolCallResult

logger = structlog.get_logger()


class RequestExecutionCoordinator:
    """
    Cross-session execution coordinator.
    
    Routes execution requests to:
    - Local skills (for in-process Python skills)
    - Remote executor (for TypeScript/MCP servers)
    - System operations (via Agentic OS Interface)
    
    All agents use this coordinator for consistent execution semantics.
    """
    
    def __init__(self):
        self.logger = logger.bind(component="RequestExecutionCoordinator")
        
        # Backend components
        self.local_registry = get_local_skill_registry()
        self.remote_client = get_remote_executor_client()
        self.os_interface = get_os_interface_skill()
        
        # Routing configuration
        self._local_priority_skills: set[str] = set()
        self._remote_only_skills: set[str] = set()
        self._load_routing_config()
        
        # Ticket tracking
        self._tickets: dict[str, ExecutionTicket] = {}
        self._execution_history: list[ExecutionTicket] = []
        
        self.logger.info("RequestExecutionCoordinator initialized")
    
    def _load_routing_config(self) -> None:
        """Load routing configuration."""
        # TODO: Load from config/coordinator.yaml
        # For now, use hardcoded defaults
        self._local_priority_skills = {
            "fs-skill",
            "shell-skill",
        }
        self._remote_only_skills = set()  # Skills that must go remote
    
    def configure_routing(
        self,
        local_priority: list[str] | None = None,
        remote_only: list[str] | None = None,
    ) -> None:
        """
        Configure routing rules.
        
        Args:
            local_priority: Skills to prefer routing locally
            remote_only: Skills that must be routed remotely
        """
        if local_priority:
            self._local_priority_skills.update(local_priority)
        if remote_only:
            self._remote_only_skills.update(remote_only)
    
    async def submit(self, request: ExecutionRequest) -> ExecutionTicket:
        """
        Submit an execution request.
        
        Args:
            request: Standardized execution request
            
        Returns:
            ExecutionTicket for tracking
        """
        ticket = ExecutionTicket(
            ticket_id=f"ticket_{uuid.uuid4().hex[:12]}",
            request=request,
            status="pending",
        )
        
        self._tickets[ticket.ticket_id] = ticket
        
        self.logger.debug(
            "Execution request submitted",
            ticket_id=ticket.ticket_id,
            request_type=request.request_type.value,
            source=request.source,
            target=request.target,
        )
        
        return ticket
    
    async def execute(self, ticket: ExecutionTicket) -> ExecutionResult:
        """
        Execute a submitted request.
        
        Args:
            ticket: ExecutionTicket from submit()
            
        Returns:
            ExecutionResult with success/failure status
        """
        request = ticket.request
        start_time = time.time()
        
        # Mark as running
        ticket.status = "running"
        ticket.started_at = datetime.utcnow()
        
        self.logger.info(
            "Executing request",
            ticket_id=ticket.ticket_id,
            request_type=request.request_type.value,
            target=request.target,
            action=request.action,
        )
        
        try:
            # Route based on request type
            if request.request_type == RequestType.SKILL_CALL:
                result = await self._execute_skill_call(request)
            elif request.request_type == RequestType.SYSTEM_OPERATION:
                result = await self._execute_system_operation(request)
            elif request.request_type == RequestType.INTERNAL:
                result = await self._execute_internal(request)
            else:
                raise ValueError(f"Unknown request type: {request.request_type}")
            
            # Mark as completed
            ticket.status = "completed" if result.success else "failed"
            ticket.completed_at = datetime.utcnow()
            
            # Track execution time
            execution_time_ms = int((time.time() - start_time) * 1000)
            result.execution_time_ms = execution_time_ms
            
            # Archive ticket
            self._execution_history.append(ticket)
            if ticket.ticket_id in self._tickets:
                del self._tickets[ticket.ticket_id]
            
            self.logger.info(
                "Execution completed",
                ticket_id=ticket.ticket_id,
                success=result.success,
                execution_time_ms=execution_time_ms,
            )
            
            return result
            
        except Exception as e:
            # Mark as failed
            ticket.status = "failed"
            ticket.completed_at = datetime.utcnow()
            execution_time_ms = int((time.time() - start_time) * 1000)
            
            self.logger.error(
                "Execution failed with exception",
                ticket_id=ticket.ticket_id,
                error=str(e),
            )
            
            return ExecutionResult(
                ticket_id=ticket.ticket_id,
                success=False,
                result=None,
                error=str(e),
                execution_time_ms=execution_time_ms,
                events_generated=[],
                artifacts_produced=[],
            )
    
    async def _execute_skill_call(self, request: ExecutionRequest) -> ExecutionResult:
        """Execute a skill call request."""
        skill_name = request.target
        tool_name = request.action
        parameters = request.parameters
        
        # Decide routing
        route_local = self._should_route_local(skill_name)
        
        if route_local and self.local_registry.has_skill(skill_name):
            # Execute locally
            self.logger.debug(
                "Routing to local skill",
                skill_name=skill_name,
                tool_name=tool_name,
            )
            
            # Extract task_id and session_id from request context for directory locking
            task_id = request.context.get("task_id", request.request_id)
            session_id = request.context.get("session_id", "unknown")
            
            raw_result = await self.local_registry.execute(
                skill_name=skill_name,
                tool_name=tool_name,
                parameters=parameters,
                task_id=task_id,
                session_id=session_id,
            )
            
            return ExecutionResult(
                ticket_id=request.request_id,
                success=raw_result.get("success", False),
                result=raw_result.get("result"),
                error=raw_result.get("error"),
                execution_time_ms=0,  # Will be set by caller
                events_generated=[],
                artifacts_produced=[],
            )
        
        else:
            # Execute remotely
            self.logger.debug(
                "Routing to remote executor",
                skill_name=skill_name,
                tool_name=tool_name,
            )
            
            tool_request = ToolCallRequest(
                request_id=request.request_id,
                session_id=request.context.get("session_id", "unknown"),
                skill_name=skill_name,
                tool_name=tool_name,
                parameters=parameters,
                timeout=request.timeout_ms,
            )
            
            tool_result = await self.remote_client.execute_tool(tool_request)
            
            return ExecutionResult(
                ticket_id=request.request_id,
                success=tool_result.success,
                result=tool_result.result,
                error=tool_result.error,
                execution_time_ms=tool_result.execution_time_ms,
                events_generated=[],
                artifacts_produced=[],
            )
    
    async def _execute_system_operation(self, request: ExecutionRequest) -> ExecutionResult:
        """Execute a system operation via Agentic OS Interface."""
        operation = request.action
        
        self.logger.debug(
            "Executing system operation",
            operation=operation,
        )
        
        # Route to OS interface based on operation type
        if operation == "query_session_state":
            session_id = request.parameters.get("session_id")
            state = await self.os_interface.query_session_state(session_id)
            return ExecutionResult(
                ticket_id=request.request_id,
                success=state is not None,
                result=state.model_dump() if state else None,
                error=None if state else f"Session {session_id} not found",
                execution_time_ms=0,
                events_generated=[],
                artifacts_produced=[],
            )
        
        elif operation == "query_task_state":
            task_id = request.parameters.get("task_id")
            state = await self.os_interface.query_task_state(task_id)
            return ExecutionResult(
                ticket_id=request.request_id,
                success=state is not None,
                result=state,
                error=None if state else f"Task {task_id} not found",
                execution_time_ms=0,
                events_generated=[],
                artifacts_produced=[],
            )
        
        elif operation == "get_thread_log":
            thread_id = request.parameters.get("thread_id")
            log_data = await self.os_interface.get_thread_full_log(thread_id)
            return ExecutionResult(
                ticket_id=request.request_id,
                success=log_data is not None,
                result=log_data,
                error=None if log_data else f"Thread {thread_id} not found",
                execution_time_ms=0,
                events_generated=[],
                artifacts_produced=[],
            )
        
        elif operation == "send_message":
            from thread_runtime.models import SystemMessage
            msg_data = request.parameters.get("message", {})
            message = SystemMessage(**msg_data)
            result = await self.os_interface.send_message(message)
            return ExecutionResult(
                ticket_id=request.request_id,
                success=result.success,
                result=result.result,
                error=result.error,
                execution_time_ms=0,
                events_generated=[],
                artifacts_produced=[],
            )
        
        else:
            return ExecutionResult(
                ticket_id=request.request_id,
                success=False,
                result=None,
                error=f"Unknown system operation: {operation}",
                execution_time_ms=0,
                events_generated=[],
                artifacts_produced=[],
            )
    
    async def _execute_internal(self, request: ExecutionRequest) -> ExecutionResult:
        """Execute internal operation."""
        # Internal operations are handled within the kernel
        # Examples: state queries, configuration updates
        
        operation = request.action
        
        if operation == "get_coordinator_status":
            return ExecutionResult(
                ticket_id=request.request_id,
                success=True,
                result={
                    "active_tickets": len(self._tickets),
                    "history_size": len(self._execution_history),
                    "local_skills": self.local_registry.list_available(),
                },
                execution_time_ms=0,
                events_generated=[],
                artifacts_produced=[],
            )
        
        else:
            return ExecutionResult(
                ticket_id=request.request_id,
                success=False,
                result=None,
                error=f"Unknown internal operation: {operation}",
                execution_time_ms=0,
                events_generated=[],
                artifacts_produced=[],
            )
    
    def _should_route_local(self, skill_name: str) -> bool:
        """Determine if a skill should be routed locally."""
        # Explicit remote-only
        if skill_name in self._remote_only_skills:
            return False
        
        # Explicit local priority
        if skill_name in self._local_priority_skills:
            return True
        
        # Default: check if registered locally
        return self.local_registry.has_skill(skill_name)
    
    async def cancel(self, ticket_id: str, reason: str = "") -> bool:
        """
        Cancel an ongoing execution.
        
        Args:
            ticket_id: Ticket to cancel
            reason: Cancellation reason
            
        Returns:
            True if cancellation was initiated
        """
        ticket = self._tickets.get(ticket_id)
        if not ticket:
            self.logger.warning("Ticket not found for cancellation", ticket_id=ticket_id)
            return False
        
        if ticket.status in ("completed", "failed", "cancelled"):
            self.logger.warning(
                "Cannot cancel completed ticket",
                ticket_id=ticket_id,
                status=ticket.status,
            )
            return False
        
        # Mark as cancelled
        ticket.status = "cancelled"
        ticket.completed_at = datetime.utcnow()
        
        # Try to cancel at backend
        if ticket.request.request_type == RequestType.SKILL_CALL:
            await self.remote_client.cancel_execution(ticket_id)
        
        self.logger.info(
            "Ticket cancelled",
            ticket_id=ticket_id,
            reason=reason,
        )
        
        return True
    
    def get_ticket(self, ticket_id: str) -> ExecutionTicket | None:
        """Get ticket by ID."""
        return self._tickets.get(ticket_id)
    
    def list_active_tickets(self) -> list[ExecutionTicket]:
        """List all active (pending/running) tickets."""
        return [
            ticket for ticket in self._tickets.values()
            if ticket.status in ("pending", "running")
        ]
    
    def get_execution_history(
        self,
        limit: int = 100,
        request_type: RequestType | None = None,
    ) -> list[ExecutionTicket]:
        """Get execution history."""
        history = self._execution_history[-limit:]
        if request_type:
            history = [
                t for t in history
                if t.request.request_type == request_type
            ]
        return history


# Singleton instance
_coordinator: RequestExecutionCoordinator | None = None


def get_execution_coordinator() -> RequestExecutionCoordinator:
    """Get or create singleton instance."""
    global _coordinator
    if _coordinator is None:
        _coordinator = RequestExecutionCoordinator()
    return _coordinator
