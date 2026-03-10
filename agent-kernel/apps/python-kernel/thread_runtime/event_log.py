"""
Event Log Manager - Manages event logging and querying for Agent Threads.
"""
import uuid
from datetime import datetime
from typing import Any

import structlog

from thread_runtime.models import Event, EventLog, EventType, Phase

logger = structlog.get_logger()


class EventLogManager:
    """
    Manages Event Log for a single task.
    
    Provides:
    - Event appending with auto-generated IDs
    - Querying and filtering
    - Export for debugging
    - Persistence integration hooks
    """
    
    def __init__(self, task_id: str):
        self.task_id = task_id
        self.log = EventLog(task_id=task_id, events=[])
        self.logger = logger.bind(component="EventLogManager", task_id=task_id)
    
    def append(
        self,
        event_type: EventType,
        actor: str,
        phase: Phase,
        content: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> Event:
        """
        Append a new event to the log.
        
        Args:
            event_type: Type of event
            actor: ID of the actor (e.g., agent_thread_id)
            phase: Current execution phase
            content: Event payload
            metadata: Additional metadata
            
        Returns:
            The created Event
        """
        event = Event(
            event_id=f"evt_{uuid.uuid4().hex[:12]}",
            event_type=event_type,
            actor=actor,
            phase=phase,
            content=content,
            metadata=metadata or {},
        )
        self.log.append(event)
        
        self.logger.debug(
            "Event appended",
            event_id=event.event_id,
            event_type=event_type.value,
            phase=phase.value,
        )
        
        return event
    
    def append_tool_call(
        self,
        actor: str,
        phase: Phase,
        skill_name: str,
        tool_name: str,
        parameters: dict[str, Any],
    ) -> Event:
        """Convenience method for tool call events."""
        return self.append(
            event_type=EventType.TOOL_CALL,
            actor=actor,
            phase=phase,
            content={
                "skill": skill_name,
                "tool": tool_name,
                "parameters": parameters,
                "summary": f"Call {skill_name}.{tool_name}",
            },
            metadata={"skill_name": skill_name, "tool_name": tool_name},
        )
    
    def append_tool_result(
        self,
        actor: str,
        phase: Phase,
        skill_name: str,
        tool_name: str,
        success: bool,
        result: Any,
        error: str | None = None,
    ) -> Event:
        """Convenience method for tool result events."""
        return self.append(
            event_type=EventType.TOOL_RESULT,
            actor=actor,
            phase=phase,
            content={
                "skill": skill_name,
                "tool": tool_name,
                "success": success,
                "result": result,
                "error": error,
                "summary": f"{'✓' if success else '✗'} {skill_name}.{tool_name}",
            },
            metadata={"skill_name": skill_name, "tool_name": tool_name, "success": success},
        )
    
    def append_observation(
        self,
        actor: str,
        phase: Phase,
        observation_type: str,
        content: Any,
        summary: str = "",
    ) -> Event:
        """Convenience method for observation events."""
        return self.append(
            event_type=EventType.OBSERVATION,
            actor=actor,
            phase=phase,
            content={
                "type": observation_type,
                "content": content,
                "summary": summary or f"Observation: {observation_type}",
            },
            metadata={"observation_type": observation_type},
        )
    
    def append_phase_change(
        self,
        actor: str,
        from_phase: Phase,
        to_phase: Phase,
        reason: str = "",
    ) -> Event:
        """Convenience method for phase change events."""
        return self.append(
            event_type=EventType.PHASE_CHANGE,
            actor=actor,
            phase=to_phase,  # Log in the new phase
            content={
                "from_phase": from_phase.value,
                "to_phase": to_phase.value,
                "reason": reason,
                "summary": f"Phase: {from_phase.value} → {to_phase.value}",
            },
            metadata={"from_phase": from_phase.value, "to_phase": to_phase.value},
        )
    
    def append_artifact_update(
        self,
        actor: str,
        phase: Phase,
        slot_id: str,
        slot_type: str,
        operation: str = "create",
    ) -> Event:
        """Convenience method for artifact update events."""
        return self.append(
            event_type=EventType.ARTIFACT_UPDATE,
            actor=actor,
            phase=phase,
            content={
                "slot_id": slot_id,
                "slot_type": slot_type,
                "operation": operation,
                "summary": f"Artifact {operation}: {slot_type}",
            },
            metadata={"slot_id": slot_id, "slot_type": slot_type, "operation": operation},
        )
    
    def append_error(
        self,
        actor: str,
        phase: Phase,
        error_message: str,
        error_type: str = "runtime",
        context: dict[str, Any] | None = None,
    ) -> Event:
        """Convenience method for error events."""
        return self.append(
            event_type=EventType.ERROR,
            actor=actor,
            phase=phase,
            content={
                "error_type": error_type,
                "message": error_message,
                "context": context or {},
                "summary": f"Error ({error_type}): {error_message[:100]}",
            },
            metadata={"error_type": error_type},
        )
    
    def get_recent(
        self,
        count: int = 10,
        event_type: EventType | None = None,
        phase: Phase | None = None,
    ) -> list[Event]:
        """
        Get recent events with optional filters.
        
        Args:
            count: Number of events to return
            event_type: Filter by event type
            phase: Filter by phase
            
        Returns:
            List of matching events (most recent first)
        """
        return self.log.get_recent(count, event_type, phase)
    
    def get_recent_as_text(self, count: int = 5) -> str:
        """Get recent events formatted as text for prompts."""
        events = self.get_recent(count)
        if not events:
            return "No recent events."
        return "\n".join([f"- {e.to_prompt_text()}" for e in reversed(events)])
    
    def get_by_phase(self, phase: Phase) -> list[Event]:
        """Get all events for a specific phase."""
        return self.log.get_by_phase(phase)
    
    def get_by_type(self, event_type: EventType) -> list[Event]:
        """Get all events of a specific type."""
        return self.log.get_by_type(event_type)
    
    def get_all(self) -> list[Event]:
        """Get all events."""
        return self.log.events.copy()
    
    def get_count(self) -> int:
        """Get total event count."""
        return len(self.log.events)
    
    def export_for_debug(self) -> dict[str, Any]:
        """
        Export complete log for debugging.
        This is what the upper layer uses to inspect thread state.
        """
        return self.log.export_for_debug()
    
    def get_summary(self) -> dict[str, Any]:
        """Get a brief summary of the log."""
        return {
            "task_id": self.task_id,
            "total_events": len(self.log.events),
            "phase_summary": self.log._phase_summary(),
            "last_event": self.log.events[-1].to_prompt_text() if self.log.events else None,
        }
    
    def clear(self) -> None:
        """Clear all events (use with caution)."""
        self.log.events.clear()
        self.logger.warning("Event log cleared")
