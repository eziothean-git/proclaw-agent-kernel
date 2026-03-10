"""
Pydantic models for Agent Kernel Python layer.
Shared with TypeScript layer via JSON Schema.
"""
from datetime import datetime
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, Field, ConfigDict


class RequestStatus(str, Enum):
    """Status of a user request."""
    PENDING = "pending"
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class TaskStatus(str, Enum):
    """Status of a task."""
    IDLE = "idle"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


class Request(BaseModel):
    """User request model."""
    model_config = ConfigDict(
        strict=False,
        json_schema_extra={
            "examples": [
                {
                    "id": "req_123",
                    "session_id": "sess_123",
                    "user_id": "user_123",
                    "message": "Hello",
                    "status": "pending",
                    "created_at": "2024-01-01T00:00:00",
                    "metadata": {},
                }
            ]
        },
    )

    id: str = Field(description="Unique request identifier")
    session_id: str = Field(description="Session identifier")
    user_id: str = Field(description="User identifier")
    message: str = Field(description="User message content")
    status: RequestStatus = Field(default=RequestStatus.PENDING)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    processed_at: Optional[datetime] = Field(default=None)
    completed_at: Optional[datetime] = Field(default=None)
    metadata: dict[str, Any] = Field(default_factory=dict)


class Session(BaseModel):
    """Session state model."""
    model_config = ConfigDict(strict=False)

    id: str = Field(description="Session identifier")
    user_id: str = Field(description="User identifier")
    status: str = Field(default="active", description="Session status")
    created_at: datetime = Field(default_factory=datetime.utcnow)
    last_activity: datetime = Field(default_factory=datetime.utcnow)
    task_count: int = Field(default=0)
    active_processes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskSnapshot(BaseModel):
    """Task runtime snapshot model."""
    model_config = ConfigDict(strict=False)

    id: str = Field(description="Task identifier")
    session_id: str = Field(description="Parent session ID")
    process_id: str = Field(description="Parent process ID")
    status: TaskStatus = Field(default=TaskStatus.IDLE)
    goal: str = Field(description="Task objective")
    constraints: list[str] = Field(default_factory=list)
    allowed_capabilities: list[str] = Field(default_factory=list)
    forbidden_capabilities: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    started_at: Optional[datetime] = Field(default=None)
    completed_at: Optional[datetime] = Field(default=None)
    output: Optional[str] = Field(default=None)
    error: Optional[str] = Field(default=None)


class IntermediateRepresentation(BaseModel):
    """Prime Personality output - structured intermediate representation."""
    model_config = ConfigDict(strict=True)
    
    request_id: str = Field(description="Original request ID")
    intent: str = Field(description="High-level intent classification")
    goals: list[str] = Field(description="List of goals to achieve")
    processes: list[dict[str, Any]] = Field(
        description="Process definitions with capabilities"
    )
    context_hints: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional context for compilation"
    )


class CompiledContext(BaseModel):
    """Compiled context for Agent execution."""
    model_config = ConfigDict(strict=True)

    task_id: str = Field(description="Task identifier")
    session_context: dict[str, Any] = Field(description="Session-level context")
    task_goal: str = Field(description="Specific task objective")
    constraints: list[str] = Field(description="Execution constraints")
    allowed_capabilities: list[str] = Field(description="Permitted skills/tools")
    forbidden_capabilities: list[str] = Field(description="Forbidden skills/tools")
    memory_references: list[str] = Field(default_factory=list)
    compiled_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict, description="Compilation metadata")


class AgentOutput(BaseModel):
    """Agent thread output model."""
    model_config = ConfigDict(strict=True)
    
    task_id: str = Field(description="Task identifier")
    content: str = Field(description="Agent response content")
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    observations: list[dict[str, Any]] = Field(default_factory=list)
    success: bool = Field(default=True)
    error: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.utcnow)


class LongTermMemoryCandidate(BaseModel):
    """Candidate for long-term memory storage."""
    model_config = ConfigDict(strict=True)
    
    id: str = Field(description="Candidate ID")
    session_id: str = Field(description="Source session ID")
    content: str = Field(description="Memory content")
    category: str = Field(description="Memory category")
    importance_score: float = Field(ge=0.0, le=1.0)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ToolCallRequest(BaseModel):
    """Tool call request to TS Executor."""
    model_config = ConfigDict(strict=True)
    
    request_id: str = Field(description="Unique request ID")
    session_id: str = Field(description="Session ID")
    skill_name: str = Field(description="Skill/MCP server name")
    tool_name: str = Field(description="Tool to invoke")
    parameters: dict[str, Any] = Field(default_factory=dict)
    timeout: int = Field(default=30000, description="Timeout in milliseconds")


class ToolCallResult(BaseModel):
    """Tool call result from TS Executor."""
    model_config = ConfigDict(strict=True)
    
    request_id: str = Field(description="Original request ID")
    success: bool = Field(description="Whether call succeeded")
    result: Optional[Any] = Field(default=None)
    error: Optional[str] = Field(default=None)
    execution_time_ms: int = Field(description="Execution time in milliseconds")


class HealthCheck(BaseModel):
    """Health check response."""
    model_config = ConfigDict(strict=True)
    
    status: str = Field(default="healthy")
    version: str = Field(default="0.1.0")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    components: dict[str, str] = Field(default_factory=dict)
