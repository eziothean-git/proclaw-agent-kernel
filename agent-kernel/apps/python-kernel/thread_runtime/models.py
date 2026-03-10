"""
Core data models for Agent Thread runtime.
These models define the Event Log + Working Set architecture.
"""
from datetime import datetime
from enum import Enum
from typing import Any, Literal, Optional
from pydantic import BaseModel, Field, ConfigDict


class Phase(str, Enum):
    """Execution phases for Agent Thread."""
    EXPLORE = "explore"      # Information gathering phase
    EXECUTE = "execute"      # Action execution phase
    COMPLETE = "complete"    # Completion phase


class EventType(str, Enum):
    """Types of events in the Event Log."""
    AGENT_ACTION = "agent_action"           # Agent initiated action
    TOOL_CALL = "tool_call"                 # Tool call request
    TOOL_RESULT = "tool_result"             # Tool execution result
    OBSERVATION = "observation"             # Environment observation
    PHASE_CHANGE = "phase_change"           # Phase transition
    ARTIFACT_UPDATE = "artifact_update"     # Artifact slot update
    ERROR = "error"                         # Error event
    SYSTEM = "system"                       # System event


class IntentType(str, Enum):
    """Types of intents parsed from Agent output."""
    TOOL_CALL = "tool_call"                 # Request to call a tool
    FINAL_ANSWER = "final_answer"           # Final task answer
    CLARIFICATION = "clarification"         # Request for clarification
    PHASE_TRANSITION = "phase_transition"   # Request to change phase
    ERROR = "error"                         # Error in output
    UNKNOWN = "unknown"                     # Unrecognized intent


class RequestType(str, Enum):
    """Types of execution requests."""
    SKILL_CALL = "skill_call"               # MCP skill invocation
    SYSTEM_OPERATION = "system_operation"   # System-level operation
    INTERNAL = "internal"                   # Internal operation


class Event(BaseModel):
    """Single event in the Event Log."""
    model_config = ConfigDict(strict=True)
    
    event_id: str = Field(description="Unique event identifier")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    event_type: EventType = Field(description="Type of event")
    actor: str = Field(description="ID of the actor (e.g., agent_thread_id)")
    phase: Phase = Field(description="Phase when event occurred")
    content: dict[str, Any] = Field(default_factory=dict, description="Event payload")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    
    def to_prompt_text(self) -> str:
        """Convert event to text for prompt inclusion."""
        if self.event_type == EventType.TOOL_RESULT:
            result = self.content.get("result", {})
            success = result.get("success", False)
            return f"[{self.event_type}] {'✓' if success else '✗'} {result.get('tool', 'unknown')}"
        elif self.event_type == EventType.OBSERVATION:
            return f"[{self.event_type}] {self.content.get('summary', '')}"
        elif self.event_type == EventType.PHASE_CHANGE:
            return f"[{self.event_type}] {self.content.get('from_phase', '?')} → {self.content.get('to_phase', '?')}"
        else:
            return f"[{self.event_type}] {self.content.get('summary', str(self.content))}"


class EventLog(BaseModel):
    """Complete event log for a task."""
    model_config = ConfigDict(strict=False)
    
    task_id: str = Field(description="Associated task ID")
    events: list[Event] = Field(default_factory=list)
    
    def append(self, event: Event) -> None:
        """Append an event to the log."""
        self.events.append(event)
    
    def get_recent(
        self, 
        count: int, 
        event_type: EventType | None = None,
        phase: Phase | None = None,
    ) -> list[Event]:
        """Get recent N events with optional filters."""
        filtered = self.events
        if event_type:
            filtered = [e for e in filtered if e.event_type == event_type]
        if phase:
            filtered = [e for e in filtered if e.phase == phase]
        return filtered[-count:] if len(filtered) > count else filtered
    
    def get_by_phase(self, phase: Phase) -> list[Event]:
        """Get all events for a specific phase."""
        return [e for e in self.events if e.phase == phase]
    
    def get_by_type(self, event_type: EventType) -> list[Event]:
        """Get all events of a specific type."""
        return [e for e in self.events if e.event_type == event_type]
    
    def export_for_debug(self) -> dict[str, Any]:
        """Export full log for debugging/diagnostics."""
        return {
            "task_id": self.task_id,
            "event_count": len(self.events),
            "events": [e.model_dump() for e in self.events],
            "phase_summary": self._phase_summary(),
        }
    
    def _phase_summary(self) -> dict[str, int]:
        """Generate summary of events per phase."""
        summary: dict[str, int] = {}
        for phase in Phase:
            summary[phase.value] = len(self.get_by_phase(phase))
        return summary


class ArtifactSlot(BaseModel):
    """Structured intermediate output slot."""
    model_config = ConfigDict(strict=True)
    
    slot_id: str = Field(description="Unique slot identifier")
    slot_type: str = Field(description="Type of artifact (e.g., module_map, patch_plan)")
    content: Any = Field(description="Slot content")
    priority: int = Field(ge=1, le=10, description="Priority for Working Set selection")
    phase_created: Phase = Field(description="Phase when artifact was created")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    def update(self, content: Any) -> None:
        """Update slot content."""
        self.content = content
        self.updated_at = datetime.utcnow()
    
    def to_prompt_text(self, max_length: int = 500) -> str:
        """Convert artifact to text for prompt inclusion."""
        content_str = str(self.content)
        if len(content_str) > max_length:
            content_str = content_str[:max_length] + "... [truncated]"
        return f"## {self.slot_type} (priority: {self.priority})\n{content_str}"


class WorkingSet(BaseModel):
    """Bounded working context fed to the model."""
    model_config = ConfigDict(strict=False)
    
    # Core identifiers
    task_id: str = Field(description="Task identifier")
    task_goal: str = Field(description="Task objective")
    
    # Current state
    current_phase: Phase = Field(description="Current execution phase")
    step_number: int = Field(ge=1, description="Current step number")
    
    # Immutable context (always included)
    immutable_context: dict[str, Any] = Field(
        default_factory=dict,
        description="Initial input, never changes"
    )
    
    # Variable context
    confirmed_facts: list[str] = Field(default_factory=list)
    recent_observations: list[dict[str, Any]] = Field(default_factory=list)
    active_artifacts: dict[str, Any] = Field(default_factory=dict)
    previous_action_result: dict[str, Any] | None = Field(default=None)
    pending_decisions: list[str] = Field(default_factory=list)
    context_notes: list[str] = Field(default_factory=list)
    
    # Metadata
    token_estimate: int = Field(default=0, description="Estimated token count")
    built_at: datetime = Field(default_factory=datetime.utcnow)
    
    def to_prompt(self) -> str:
        """Convert Working Set to prompt text."""
        lines = [
            "=" * 60,
            "WORKING CONTEXT",
            "=" * 60,
            "",
            f"Task: {self.task_goal}",
            f"Phase: {self.current_phase.value}",
            f"Step: {self.step_number}",
            "",
        ]
        
        # Immutable context
        if self.immutable_context:
            lines.extend([
                "-" * 40,
                "IMMUTABLE CONSTRAINTS",
                "-" * 40,
            ])
            for key, value in self.immutable_context.items():
                lines.append(f"{key}: {value}")
            lines.append("")
        
        # Confirmed facts
        if self.confirmed_facts:
            lines.extend([
                "-" * 40,
                "CONFIRMED FACTS",
                "-" * 40,
            ])
            for fact in self.confirmed_facts:
                lines.append(f"• {fact}")
            lines.append("")
        
        # Active artifacts
        if self.active_artifacts:
            lines.extend([
                "-" * 40,
                "ACTIVE ARTIFACTS",
                "-" * 40,
            ])
            for name, content in self.active_artifacts.items():
                content_str = str(content)
                if len(content_str) > 300:
                    content_str = content_str[:300] + "..."
                lines.append(f"\n[{name}]:")
                lines.append(content_str)
            lines.append("")
        
        # Recent observations
        if self.recent_observations:
            lines.extend([
                "-" * 40,
                "RECENT OBSERVATIONS",
                "-" * 40,
            ])
            for obs in self.recent_observations[-5:]:  # Last 5
                obs_text = obs.get("text", str(obs))
                lines.append(f"• {obs_text}")
            lines.append("")
        
        # Previous action result
        if self.previous_action_result:
            lines.extend([
                "-" * 40,
                "PREVIOUS ACTION RESULT",
                "-" * 40,
                str(self.previous_action_result.get("summary", self.previous_action_result)),
                "",
            ])
        
        # Pending decisions
        if self.pending_decisions:
            lines.extend([
                "-" * 40,
                "PENDING DECISIONS",
                "-" * 40,
            ])
            for decision in self.pending_decisions:
                lines.append(f"? {decision}")
            lines.append("")
        
        lines.extend([
            "=" * 60,
            f"Token estimate: {self.token_estimate}",
            "=" * 60,
        ])
        
        return "\n".join(lines)


class ToolCallIntent(BaseModel):
    """Structured tool call intent."""
    model_config = ConfigDict(strict=True)
    
    skill_name: str = Field(description="Skill/MCP server name")
    tool_name: str = Field(description="Tool to invoke")
    parameters: dict[str, Any] = Field(default_factory=dict)
    reasoning: str = Field(default="", description="Why this tool is being called")


class PhaseTransitionIntent(BaseModel):
    """Intent to transition between phases."""
    model_config = ConfigDict(strict=True)
    
    from_phase: Phase
    to_phase: Phase
    reason: str
    artifacts_to_finalize: list[str] = Field(default_factory=list)


class ParsedIntent(BaseModel):
    """Parsed intent from Agent output."""
    model_config = ConfigDict(strict=True)
    
    intent_type: IntentType
    confidence: float = Field(ge=0.0, le=1.0)
    raw_content: str = Field(description="Original raw output")
    structured_data: dict[str, Any] = Field(default_factory=dict)
    
    # Type-specific data
    tool_calls: list[ToolCallIntent] = Field(default_factory=list)
    phase_transition: PhaseTransitionIntent | None = Field(default=None)
    final_answer: str | None = Field(default=None)
    clarification_request: str | None = Field(default=None)
    error_message: str | None = Field(default=None)


class ExecutionRequest(BaseModel):
    """Standardized execution request."""
    model_config = ConfigDict(strict=True)
    
    request_id: str = Field(description="Unique request ID")
    request_type: RequestType
    source: str = Field(description="Requester ID (e.g., agent_thread_id)")
    target: str = Field(description="Target (skill_name or system_endpoint)")
    action: str = Field(description="Specific action/tool to execute")
    parameters: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict, description="Execution context")
    priority: int = Field(default=5, ge=1, le=10)
    timeout_ms: int = Field(default=30000)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class ExecutionTicket(BaseModel):
    """Execution ticket tracking a submitted request."""
    model_config = ConfigDict(strict=True)
    
    ticket_id: str = Field(description="Unique ticket ID")
    request: ExecutionRequest
    status: Literal["pending", "running", "completed", "failed", "cancelled"] = "pending"
    submitted_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: datetime | None = Field(default=None)
    completed_at: datetime | None = Field(default=None)


class ExecutionResult(BaseModel):
    """Result of an execution."""
    model_config = ConfigDict(strict=True)
    
    ticket_id: str
    success: bool
    result: Any | None = Field(default=None)
    error: str | None = Field(default=None)
    execution_time_ms: int
    events_generated: list[str] = Field(default_factory=list)
    artifacts_produced: list[str] = Field(default_factory=list)


# Agentic OS Interface Models

class RoutingDecision(BaseModel):
    """Decision for request routing."""
    model_config = ConfigDict(strict=True)
    
    decision_type: Literal["new_session", "reuse_session", "light_response"]
    target_session_id: str | None = Field(default=None)
    reason: str
    confidence: float = Field(ge=0.0, le=1.0)


class SessionFilters(BaseModel):
    """Filters for session queries."""
    model_config = ConfigDict(strict=True)
    
    user_id: str | None = Field(default=None)
    status: str | None = Field(default=None)
    tags: list[str] = Field(default_factory=list)
    active_only: bool = Field(default=True)


class SessionSummary(BaseModel):
    """Summary of a session."""
    model_config = ConfigDict(strict=True)
    
    session_id: str
    status: str
    task_count: int
    last_activity: datetime
    summary: str = Field(description="Auto-generated summary")


class SystemMessage(BaseModel):
    """Message for cross-session communication."""
    model_config = ConfigDict(strict=True)
    
    msg_id: str
    source: str = Field(description="Sender ID")
    target: str = Field(description="Receiver ID or 'broadcast'")
    msg_type: Literal["command", "query", "notification", "response"]
    content: dict[str, Any]
    priority: int = Field(ge=1, le=10)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class SessionState(BaseModel):
    """Full state of a session."""
    model_config = ConfigDict(strict=True)
    
    session_id: str
    status: str
    active_tasks: list[dict[str, Any]]  # Task summaries
    recent_events: list[dict[str, Any]]
    available_context: list[str]
    metadata: dict[str, Any] = Field(default_factory=dict)


class SystemOperationResult(BaseModel):
    """Result of a system operation."""
    model_config = ConfigDict(strict=True)
    
    success: bool
    operation_id: str
    result: Any | None = Field(default=None)
    error: str | None = Field(default=None)
    affected_sessions: list[str] = Field(default_factory=list)
    executed_at: datetime = Field(default_factory=datetime.utcnow)
