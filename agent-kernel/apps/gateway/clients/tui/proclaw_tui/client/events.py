"""Event definitions for Gateway SSE communication."""

from datetime import datetime
from enum import Enum
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


class EventType(str, Enum):
    """Types of SSE events."""

    ACCEPTED = "accepted"
    STATUS = "status"
    COMPLETE = "complete"
    ERROR = "error"
    HEARTBEAT = "heartbeat"
    TELEMETRY = "telemetry"  # 新增：遥测事件


class RequestStatus(str, Enum):
    """Request processing statuses."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ChatStreamEvent(BaseModel):
    """SSE event from Gateway."""

    type: EventType = Field(description="Event type")
    timestamp: datetime = Field(description="Event timestamp")
    request_id: str = Field(alias="requestId", description="Request ID")
    session_id: Optional[str] = Field(alias="sessionId", default=None, description="Session ID")
    message: Optional[str] = Field(default=None, description="Status message")
    status: Optional[RequestStatus] = Field(default=None, description="Request status")
    response: Optional[dict[str, Any]] = Field(default=None, description="Complete response")
    error: Optional[str] = Field(default=None, description="Error message")

    model_config = {"populate_by_name": True}


class TelemetryEvent(BaseModel):
    """Standard telemetry event for real-time progress tracking."""

    timestamp: datetime = Field(description="Event timestamp")
    request_id: str = Field(description="Request ID")
    session_id: Optional[str] = Field(default=None, description="Session ID")

    # Location info
    layer: int = Field(ge=1, le=7, description="Architecture layer (1-7)")
    layer_name: str = Field(description="Layer name")
    component: str = Field(description="Component name (e.g., AgentThread)")
    operation: str = Field(description="Operation name (e.g., tool_call)")

    # Status info
    status: Literal["start", "progress", "complete", "error"] = Field(
        description="Operation status"
    )
    progress_pct: Optional[int] = Field(default=None, ge=0, le=100, description="Progress percentage")

    # Details
    message: str = Field(description="Human-readable description")
    details: dict[str, Any] = Field(default_factory=dict, description="Structured data")

    # Performance
    elapsed_ms: Optional[int] = Field(default=None, description="Elapsed time in ms")
    estimated_ms: Optional[int] = Field(default=None, description="Estimated total time in ms")

    # Step info (for Layer 6 Agent Thread)
    step: Optional[int] = Field(default=None, description="Current step number")
    total_steps: Optional[int] = Field(default=None, description="Total steps")
    phase: Optional[str] = Field(default=None, description="Current phase (explore/execute/complete)")

    model_config = {"populate_by_name": True}


class FlowLayerState(BaseModel):
    """State of a single layer in the flow graph."""

    layer: int = Field(ge=1, le=7)
    name: str
    status: Literal["pending", "active", "completed", "error"] = "pending"
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_ms: Optional[int] = None
    details: dict[str, Any] = Field(default_factory=dict)


class FlowState(BaseModel):
    """Complete flow graph state."""

    request_id: str
    current_layer: int = 1
    layers: dict[int, FlowLayerState] = Field(default_factory=dict)
    active_operation: Optional[str] = None
    overall_progress: int = Field(default=0, ge=0, le=100)


class HealthStatus(BaseModel):
    """Gateway health status."""

    status: str
    gateway: str
    storage: str
    timestamp: datetime
    version: str


class ConnectionState(Enum):
    """Client connection states."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"
    RECONNECTING = "reconnecting"


class ConnectionStatus(BaseModel):
    """Current connection status."""

    state: ConnectionState
    last_error: Optional[str] = None
    connected_at: Optional[datetime] = None
    reconnect_attempts: int = 0
