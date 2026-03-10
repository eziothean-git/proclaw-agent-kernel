"""
Agentic OS Interface Skill - System-level coordination layer for Agent Kernel.

This is a Prime-scoped privileged system skill that provides:
- Session routing and management
- Cross-session message exchange
- System state queries
- Task lifecycle control

All agents (Prime Personality, Session Host, Agent Thread) use this interface
to interact with the system in an atomic and coordinated manner.
"""
import asyncio
import uuid
from datetime import datetime
from typing import Any, Callable

import structlog

from schemas.models import Request
from thread_runtime.models import (
    RoutingDecision,
    SessionFilters,
    SessionState,
    SessionSummary,
    SystemMessage,
    SystemOperationResult,
)

logger = structlog.get_logger()


class AtomicOperationManager:
    """
    Ensures atomicity of system operations.
    
    Uses asyncio locks to prevent race conditions when multiple
    agents try to modify system state simultaneously.
    """
    
    def __init__(self):
        self._locks: dict[str, asyncio.Lock] = {}
        self._operation_log: list[dict] = []
    
    async def execute(
        self,
        operation_id: str,
        resource_id: str,
        operation: Callable,
        rollback: Callable | None = None,
    ) -> SystemOperationResult:
        """
        Execute an operation atomically.
        
        Args:
            operation_id: Unique operation identifier
            resource_id: Resource being operated on (for lock granularity)
            operation: The operation to execute
            rollback: Optional rollback function if operation fails
            
        Returns:
            SystemOperationResult with success/failure status
        """
        # Get or create lock for resource
        if resource_id not in self._locks:
            self._locks[resource_id] = asyncio.Lock()
        
        lock = self._locks[resource_id]
        
        async with lock:
            start_time = datetime.utcnow()
            
            try:
                # Log operation start
                self._operation_log.append({
                    "operation_id": operation_id,
                    "resource_id": resource_id,
                    "status": "started",
                    "timestamp": start_time.isoformat(),
                })
                
                # Execute operation
                result = await operation()
                
                # Log success
                self._operation_log.append({
                    "operation_id": operation_id,
                    "resource_id": resource_id,
                    "status": "completed",
                    "timestamp": datetime.utcnow().isoformat(),
                })
                
                return SystemOperationResult(
                    success=True,
                    operation_id=operation_id,
                    result=result,
                    error=None,
                    affected_sessions=[resource_id] if "session" in resource_id else [],
                )
                
            except Exception as e:
                # Attempt rollback if provided
                if rollback:
                    try:
                        await rollback()
                    except Exception as rollback_error:
                        logger.error(
                            "Rollback failed",
                            operation_id=operation_id,
                            error=str(rollback_error),
                        )
                
                # Log failure
                self._operation_log.append({
                    "operation_id": operation_id,
                    "resource_id": resource_id,
                    "status": "failed",
                    "error": str(e),
                    "timestamp": datetime.utcnow().isoformat(),
                })
                
                return SystemOperationResult(
                    success=False,
                    operation_id=operation_id,
                    result=None,
                    error=str(e),
                    affected_sessions=[resource_id] if "session" in resource_id else [],
                )
    
    def get_operation_history(self, limit: int = 100) -> list[dict]:
        """Get recent operation history."""
        return self._operation_log[-limit:]


class AgenticOSInterfaceSkill:
    """
    System-level coordination skill.
    
    This is the unified interface for all agents to interact with the system.
    It ensures atomic operations and provides a consistent API for:
    - Session management
    - Message routing
    - State queries
    - Task control
    """
    
    def __init__(self):
        self.logger = logger.bind(component="AgenticOSInterfaceSkill")
        
        # Core components
        self.atomic_manager = AtomicOperationManager()
        
        # Registries (populated externally)
        self._session_hosts: dict[str, Any] = {}  # session_id -> SessionHost
        self._task_schedulers: dict[str, Any] = {}  # session_id -> Scheduler
        self._active_threads: dict[str, Any] = {}  # thread_id -> AgentThread info
        
        # Message bus for cross-session communication
        self._message_bus: asyncio.Queue[SystemMessage] = asyncio.Queue()
        self._message_handlers: dict[str, list[Callable]] = {}
        
        # Start message processing loop
        self._message_processor_task: asyncio.Task | None = None
    
    async def start(self) -> None:
        """Start the message processing loop."""
        if self._message_processor_task is None:
            self._message_processor_task = asyncio.create_task(
                self._process_messages_loop()
            )
            self.logger.info("Agentic OS Interface Skill started")
    
    async def stop(self) -> None:
        """Stop the message processing loop."""
        if self._message_processor_task:
            self._message_processor_task.cancel()
            try:
                await self._message_processor_task
            except asyncio.CancelledError:
                pass
            self._message_processor_task = None
            self.logger.info("Agentic OS Interface Skill stopped")
    
    def register_session_host(self, session_id: str, session_host: Any) -> None:
        """Register a Session Host instance."""
        self._session_hosts[session_id] = session_host
        self.logger.debug("Session host registered", session_id=session_id)
    
    def unregister_session_host(self, session_id: str) -> None:
        """Unregister a Session Host instance."""
        if session_id in self._session_hosts:
            del self._session_hosts[session_id]
            self.logger.debug("Session host unregistered", session_id=session_id)
    
    def register_thread(
        self,
        thread_id: str,
        session_id: str,
        task_id: str,
        thread_ref: Any,
    ) -> None:
        """Register an Agent Thread for monitoring and control."""
        self._active_threads[thread_id] = {
            "session_id": session_id,
            "task_id": task_id,
            "thread_ref": thread_ref,
            "registered_at": datetime.utcnow().isoformat(),
        }
        self.logger.debug("Thread registered", thread_id=thread_id, session_id=session_id)
    
    def unregister_thread(self, thread_id: str) -> None:
        """Unregister an Agent Thread."""
        if thread_id in self._active_threads:
            del self._active_threads[thread_id]
            self.logger.debug("Thread unregistered", thread_id=thread_id)
    
    # ========== Routing Interface ==========
    
    async def route_request(
        self,
        request: Request,
        intent: str,
        context_hints: dict[str, Any],
    ) -> RoutingDecision:
        """
        Decide where to route a request.
        
        Logic:
        1. Check intent type
        2. Query existing sessions
        3. Decide: new session, reuse session, or light response
        """
        operation_id = f"route_{uuid.uuid4().hex[:8]}"
        
        async def _do_route():
            # Simple heuristic routing logic
            # In production, this would use more sophisticated logic
            
            sessions = await self.list_sessions(SessionFilters())
            
            # Check for active sessions from same user
            user_sessions = [
                s for s in sessions
                if s.status == "active" and hasattr(request, 'user_id')
            ]
            
            # Decision logic
            if intent in ("greeting", "simple_query", "status_check"):
                # Light-weight intents don't need full session
                return RoutingDecision(
                    decision_type="light_response",
                    target_session_id=None,
                    reason=f"Intent '{intent}' can be handled without session",
                    confidence=0.9,
                )
            
            elif user_sessions and not context_hints.get("force_new_session"):
                # Reuse most recent active session
                target = user_sessions[0]
                return RoutingDecision(
                    decision_type="reuse_session",
                    target_session_id=target.session_id,
                    reason=f"Reusing active session {target.session_id}",
                    confidence=0.8,
                )
            
            else:
                # Create new session
                return RoutingDecision(
                    decision_type="new_session",
                    target_session_id=None,
                    reason="No suitable existing session found",
                    confidence=0.9,
                )
        
        result = await self.atomic_manager.execute(
            operation_id=operation_id,
            resource_id="routing",
            operation=_do_route,
        )
        
        return result.result if result.success else RoutingDecision(
            decision_type="new_session",
            target_session_id=None,
            reason="Routing failed, defaulting to new session",
            confidence=0.5,
        )
    
    async def list_sessions(
        self,
        filters: SessionFilters,
    ) -> list[SessionSummary]:
        """List sessions matching the filters."""
        summaries = []
        
        for session_id, session_host in self._session_hosts.items():
            try:
                # Get session info from host
                session = session_host.session
                
                # Apply filters
                if filters.user_id and session.user_id != filters.user_id:
                    continue
                if filters.status and session.status != filters.status:
                    continue
                if filters.active_only and session.status != "active":
                    continue
                
                # Generate summary
                summary = SessionSummary(
                    session_id=session_id,
                    status=session.status,
                    task_count=session.task_count,
                    last_activity=session.last_activity,
                    summary=f"Session for user {session.user_id}",
                )
                summaries.append(summary)
                
            except Exception as e:
                self.logger.error(
                    "Failed to get session summary",
                    session_id=session_id,
                    error=str(e),
                )
        
        return summaries
    
    # ========== Message Exchange Interface ==========
    
    async def send_message(
        self,
        message: SystemMessage,
    ) -> SystemOperationResult:
        """
        Send a message to a target session or thread.
        
        Ensures atomic message delivery.
        """
        operation_id = message.msg_id
        
        async def _do_send():
            await self._message_bus.put(message)
            return {"delivered": True, "timestamp": datetime.utcnow().isoformat()}
        
        return await self.atomic_manager.execute(
            operation_id=operation_id,
            resource_id=f"message_bus:{message.target}",
            operation=_do_send,
        )
    
    async def broadcast(
        self,
        message: SystemMessage,
        target_sessions: list[str],
    ) -> SystemOperationResult:
        """Broadcast a message to multiple sessions."""
        operation_id = f"broadcast_{uuid.uuid4().hex[:8]}"
        
        async def _do_broadcast():
            results = []
            for session_id in target_sessions:
                msg_copy = SystemMessage(
                    msg_id=f"{message.msg_id}_{session_id}",
                    source=message.source,
                    target=session_id,
                    msg_type=message.msg_type,
                    content=message.content,
                    priority=message.priority,
                )
                await self._message_bus.put(msg_copy)
                results.append(session_id)
            
            return {"delivered_to": results}
        
        return await self.atomic_manager.execute(
            operation_id=operation_id,
            resource_id="message_bus:broadcast",
            operation=_do_broadcast,
        )
    
    async def _process_messages_loop(self) -> None:
        """Background task to process messages from the bus."""
        while True:
            try:
                message = await self._message_bus.get()
                await self._dispatch_message(message)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error("Message processing error", error=str(e))
    
    async def _dispatch_message(self, message: SystemMessage) -> None:
        """Dispatch a message to its target."""
        target = message.target
        
        if target == "broadcast":
            # Handle broadcast
            for session_id in self._session_hosts:
                await self._deliver_to_session(session_id, message)
        elif target in self._session_hosts:
            # Deliver to specific session
            await self._deliver_to_session(target, message)
        elif target in self._active_threads:
            # Deliver to specific thread
            await self._deliver_to_thread(target, message)
        else:
            self.logger.warning(
                "Message target not found",
                target=target,
                msg_id=message.msg_id,
            )
    
    async def _deliver_to_session(
        self,
        session_id: str,
        message: SystemMessage,
    ) -> None:
        """Deliver message to a Session Host."""
        session_host = self._session_hosts.get(session_id)
        if session_host and hasattr(session_host, 'handle_system_message'):
            await session_host.handle_system_message(message)
    
    async def _deliver_to_thread(
        self,
        thread_id: str,
        message: SystemMessage,
    ) -> None:
        """Deliver message to an Agent Thread."""
        thread_info = self._active_threads.get(thread_id)
        if thread_info and thread_info.get("thread_ref"):
            thread_ref = thread_info["thread_ref"]
            if hasattr(thread_ref, 'handle_system_message'):
                await thread_ref.handle_system_message(message)
    
    # ========== State Query Interface ==========
    
    async def query_session_state(
        self,
        session_id: str,
    ) -> SessionState | None:
        """Query the full state of a session."""
        session_host = self._session_hosts.get(session_id)
        if not session_host:
            return None
        
        try:
            session = session_host.session
            tasks = session_host.get_all_tasks()
            
            return SessionState(
                session_id=session_id,
                status=session.status,
                active_tasks=[
                    {
                        "task_id": t.id,
                        "status": t.status.value if hasattr(t.status, 'value') else str(t.status),
                        "goal": t.goal,
                    }
                    for t in tasks
                ],
                recent_events=[],  # Would be populated from storage
                available_context=["session", "tasks", "history"],
                metadata={
                    "user_id": session.user_id,
                    "created_at": session.created_at.isoformat(),
                },
            )
        except Exception as e:
            self.logger.error(
                "Failed to query session state",
                session_id=session_id,
                error=str(e),
            )
            return None
    
    async def query_task_state(
        self,
        task_id: str,
    ) -> dict[str, Any] | None:
        """Query the state of a specific task."""
        # Search across all session hosts
        for session_id, session_host in self._session_hosts.items():
            try:
                task = session_host.get_task_status(task_id)
                if task:
                    status_val = (
                        task.status.value if hasattr(task.status, "value") else str(task.status)
                    )
                    return {
                        "task_id": task_id,
                        "session_id": session_id,
                        "status": status_val,
                        "goal": task.goal,
                        "error": task.error,
                    }
            except Exception:
                continue
        
        return None
    
    # ========== Thread Control Interface ==========
    
    async def get_thread_full_log(
        self,
        thread_id: str,
    ) -> dict[str, Any] | None:
        """
        Get the full event log of a thread.
        This is how upper layers inspect thread state.
        """
        thread_info = self._active_threads.get(thread_id)
        if not thread_info:
            return None
        
        thread_ref = thread_info.get("thread_ref")
        if thread_ref and hasattr(thread_ref, 'get_event_log_export'):
            return thread_ref.get_event_log_export()
        
        return None
    
    async def update_thread_context(
        self,
        thread_id: str,
        updates: dict[str, Any],
    ) -> SystemOperationResult:
        """
        Update thread context.
        Used by upper layers to intervene in thread execution.
        """
        operation_id = f"update_thread_{uuid.uuid4().hex[:8]}"
        
        async def _do_update():
            thread_info = self._active_threads.get(thread_id)
            if not thread_info:
                raise ValueError(f"Thread {thread_id} not found")
            
            thread_ref = thread_info.get("thread_ref")
            if thread_ref and hasattr(thread_ref, 'apply_context_update'):
                await thread_ref.apply_context_update(updates)
                return {"updated": True}
            else:
                raise ValueError(f"Thread {thread_id} does not support updates")
        
        return await self.atomic_manager.execute(
            operation_id=operation_id,
            resource_id=f"thread:{thread_id}",
            operation=_do_update,
        )
    
    async def pause_thread(
        self,
        thread_id: str,
        reason: str = "",
    ) -> SystemOperationResult:
        """Pause a running thread."""
        operation_id = f"pause_thread_{uuid.uuid4().hex[:8]}"
        
        async def _do_pause():
            thread_info = self._active_threads.get(thread_id)
            if not thread_info:
                raise ValueError(f"Thread {thread_id} not found")
            
            thread_ref = thread_info.get("thread_ref")
            if thread_ref and hasattr(thread_ref, 'pause'):
                await thread_ref.pause(reason)
                return {"paused": True}
            else:
                raise ValueError(f"Thread {thread_id} does not support pause")
        
        return await self.atomic_manager.execute(
            operation_id=operation_id,
            resource_id=f"thread:{thread_id}",
            operation=_do_pause,
        )
    
    async def resume_thread(
        self,
        thread_id: str,
    ) -> SystemOperationResult:
        """Resume a paused thread."""
        operation_id = f"resume_thread_{uuid.uuid4().hex[:8]}"
        
        async def _do_resume():
            thread_info = self._active_threads.get(thread_id)
            if not thread_info:
                raise ValueError(f"Thread {thread_id} not found")
            
            thread_ref = thread_info.get("thread_ref")
            if thread_ref and hasattr(thread_ref, 'resume'):
                await thread_ref.resume()
                return {"resumed": True}
            else:
                raise ValueError(f"Thread {thread_id} does not support resume")
        
        return await self.atomic_manager.execute(
            operation_id=operation_id,
            resource_id=f"thread:{thread_id}",
            operation=_do_resume,
        )
    
    # ========== Session Control Interface ==========
    
    async def pause_session(
        self,
        session_id: str,
        reason: str = "",
    ) -> SystemOperationResult:
        """Pause all tasks in a session."""
        operation_id = f"pause_session_{uuid.uuid4().hex[:8]}"
        
        async def _do_pause():
            session_host = self._session_hosts.get(session_id)
            if not session_host:
                raise ValueError(f"Session {session_id} not found")
            
            # Pause all active threads in session
            paused_threads = []
            for thread_id, thread_info in self._active_threads.items():
                if thread_info.get("session_id") == session_id:
                    result = await self.pause_thread(thread_id, reason)
                    if result.success:
                        paused_threads.append(thread_id)
            
            return {"paused_threads": paused_threads}
        
        return await self.atomic_manager.execute(
            operation_id=operation_id,
            resource_id=f"session:{session_id}",
            operation=_do_pause,
        )
    
    async def resume_session(
        self,
        session_id: str,
    ) -> SystemOperationResult:
        """Resume all paused tasks in a session."""
        operation_id = f"resume_session_{uuid.uuid4().hex[:8]}"
        
        async def _do_resume():
            resumed_threads = []
            for thread_id, thread_info in self._active_threads.items():
                if thread_info.get("session_id") == session_id:
                    result = await self.resume_thread(thread_id)
                    if result.success:
                        resumed_threads.append(thread_id)
            
            return {"resumed_threads": resumed_threads}
        
        return await self.atomic_manager.execute(
            operation_id=operation_id,
            resource_id=f"session:{session_id}",
            operation=_do_resume,
        )
    
    async def cancel_task(
        self,
        task_id: str,
        reason: str = "",
    ) -> SystemOperationResult:
        """Cancel a specific task."""
        operation_id = f"cancel_task_{uuid.uuid4().hex[:8]}"
        
        async def _do_cancel():
            # Find which session owns this task
            for session_id, session_host in self._session_hosts.items():
                task = session_host.get_task_status(task_id)
                if task:
                    # Cancel via scheduler
                    from thread_runtime.scheduler import get_scheduler
                    scheduler = get_scheduler()
                    success = await scheduler.cancel_task(task_id)
                    return {"cancelled": success, "session_id": session_id}
            
            raise ValueError(f"Task {task_id} not found")
        
        return await self.atomic_manager.execute(
            operation_id=operation_id,
            resource_id=f"task:{task_id}",
            operation=_do_cancel,
        )


# Singleton instance
_os_interface_skill: AgenticOSInterfaceSkill | None = None


def get_os_interface_skill() -> AgenticOSInterfaceSkill:
    """Get or create singleton instance."""
    global _os_interface_skill
    if _os_interface_skill is None:
        _os_interface_skill = AgenticOSInterfaceSkill()
    return _os_interface_skill
