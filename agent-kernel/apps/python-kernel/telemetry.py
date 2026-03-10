"""
Telemetry Manager - SSE-based telemetry streaming for TUI.
"""
import asyncio
import json
import time
from collections import deque
from datetime import datetime
from typing import Any, AsyncIterator, Optional

import structlog

logger = structlog.get_logger()


class TelemetryEvent:
    """Standard telemetry event structure matching TUI expectations."""
    
    def __init__(
        self,
        request_id: str,
        layer: int,
        layer_name: str,
        component: str,
        operation: str,
        status: str,  # "start", "progress", "complete", "error"
        message: str,
        session_id: Optional[str] = None,
        progress_pct: Optional[int] = None,
        step: Optional[int] = None,
        total_steps: Optional[int] = None,
        phase: Optional[str] = None,
        details: Optional[dict] = None,
        elapsed_ms: Optional[int] = None,
        estimated_ms: Optional[int] = None,
    ):
        self.timestamp = datetime.utcnow()
        self.request_id = request_id
        self.session_id = session_id
        self.layer = layer
        self.layer_name = layer_name
        self.component = component
        self.operation = operation
        self.status = status
        self.message = message
        self.progress_pct = progress_pct
        self.step = step
        self.total_steps = total_steps
        self.phase = phase
        self.details = details or {}
        self.elapsed_ms = elapsed_ms
        self.estimated_ms = estimated_ms
    
    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "timestamp": self.timestamp.isoformat(),
            "request_id": self.request_id,
            "session_id": self.session_id,
            "layer": self.layer,
            "layer_name": self.layer_name,
            "component": self.component,
            "operation": self.operation,
            "status": self.status,
            "message": self.message,
            "progress_pct": self.progress_pct,
            "step": self.step,
            "total_steps": self.total_steps,
            "phase": self.phase,
            "details": self.details,
            "elapsed_ms": self.elapsed_ms,
            "estimated_ms": self.estimated_ms,
        }
    
    def to_sse_data(self) -> str:
        """Convert to SSE data format."""
        return f"data: {json.dumps(self.to_dict())}\n\n"


class TelemetryManager:
    """
    Manages telemetry events and SSE streaming.
    Singleton pattern for global access.
    """
    
    _instance: Optional["TelemetryManager"] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        self._event_queue: deque[TelemetryEvent] = deque(maxlen=1000)
        self._subscribers: list[asyncio.Queue] = []
        self._active_requests: dict[str, dict] = {}  # Track active request states
        self._lock = asyncio.Lock()
        
        logger.info("TelemetryManager initialized")
    
    async def emit(self, event: TelemetryEvent) -> None:
        """
        Emit a telemetry event to all subscribers.
        
        Args:
            event: The telemetry event to emit
        """
        async with self._lock:
            # Store in queue
            self._event_queue.append(event)
            
            # Track active request state
            if event.request_id not in self._active_requests:
                self._active_requests[event.request_id] = {
                    "started_at": event.timestamp,
                    "current_layer": event.layer,
                    "events": [],
                }
            
            self._active_requests[event.request_id]["current_layer"] = event.layer
            self._active_requests[event.request_id]["events"].append(event.to_dict())
            
            # Broadcast to all subscribers
            dead_subscribers = []
            for queue in self._subscribers:
                try:
                    queue.put_nowait(event)
                except asyncio.QueueFull:
                    dead_subscribers.append(queue)
            
            # Clean up dead subscribers
            for dead in dead_subscribers:
                if dead in self._subscribers:
                    self._subscribers.remove(dead)
        
        logger.debug(
            "Telemetry event emitted",
            request_id=event.request_id,
            layer=event.layer,
            operation=event.operation,
            status=event.status,
        )
    
    def subscribe(self) -> asyncio.Queue:
        """
        Subscribe to telemetry events.
        
        Returns:
            Queue that will receive telemetry events
        """
        queue: asyncio.Queue = asyncio.Queue(maxsize=100)
        self._subscribers.append(queue)
        logger.debug(f"New telemetry subscriber added. Total: {len(self._subscribers)}")
        return queue
    
    def unsubscribe(self, queue: asyncio.Queue) -> None:
        """Unsubscribe from telemetry events."""
        if queue in self._subscribers:
            self._subscribers.remove(queue)
            logger.debug(f"Telemetry subscriber removed. Total: {len(self._subscribers)}")
    
    async def event_stream(self, request_id: Optional[str] = None) -> AsyncIterator[str]:
        """
        Generate SSE event stream.
        
        Args:
            request_id: Optional request ID to filter events
            
        Yields:
            SSE formatted event strings
        """
        queue = self.subscribe()
        
        try:
            while True:
                try:
                    # Wait for event with timeout
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    
                    # Filter by request_id if specified
                    if request_id and event.request_id != request_id:
                        continue
                    
                    yield event.to_sse_data()
                    
                except asyncio.TimeoutError:
                    # Send heartbeat
                    yield ":heartbeat\n\n"
                    
        except asyncio.CancelledError:
            logger.debug("Telemetry stream cancelled")
            raise
        finally:
            self.unsubscribe(queue)
    
    def get_request_events(self, request_id: str) -> list[dict]:
        """Get all events for a specific request."""
        if request_id in self._active_requests:
            return self._active_requests[request_id]["events"]
        return []
    
    def cleanup_request(self, request_id: str) -> None:
        """Clean up request tracking data."""
        if request_id in self._active_requests:
            del self._active_requests[request_id]
            logger.debug(f"Cleaned up telemetry data for request {request_id}")


# Global instance
_telemetry_manager: Optional[TelemetryManager] = None


def get_telemetry_manager() -> TelemetryManager:
    """Get the global telemetry manager instance."""
    global _telemetry_manager
    if _telemetry_manager is None:
        _telemetry_manager = TelemetryManager()
    return _telemetry_manager


# Convenience function for emitting telemetry
def emit_telemetry(
    request_id: str,
    layer: int,
    layer_name: str,
    component: str,
    operation: str,
    status: str,
    message: str,
    session_id: Optional[str] = None,
    **kwargs
) -> None:
    """
    Convenience function to emit a telemetry event.
    
    Args:
        request_id: Request ID
        layer: Architecture layer (1-7)
        layer_name: Layer name
        component: Component name
        operation: Operation name
        status: Event status ("start", "progress", "complete", "error")
        message: Human-readable message
        session_id: Optional session ID
        **kwargs: Additional fields (progress_pct, step, total_steps, phase, details, etc.)
    """
    event = TelemetryEvent(
        request_id=request_id,
        layer=layer,
        layer_name=layer_name,
        component=component,
        operation=operation,
        status=status,
        message=message,
        session_id=session_id,
        **kwargs
    )
    
    # Use asyncio.create_task for non-blocking emit
    try:
        loop = asyncio.get_running_loop()
        asyncio.create_task(get_telemetry_manager().emit(event))
    except RuntimeError:
        # No event loop running, just log it
        logger.debug(f"Telemetry event queued (no event loop): {event_name}", 
                    request_id=request_id, layer=layer)
    except Exception as e:
        logger.error(f"Failed to emit telemetry: {e}")
