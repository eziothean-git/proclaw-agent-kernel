"""Event definitions for Gateway SSE communication."""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class EventType(str, Enum):
    """Types of SSE events."""

    ACCEPTED = "accepted"
    STATUS = "status"
    COMPLETE = "complete"
    ERROR = "error"
    HEARTBEAT = "heartbeat"


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
