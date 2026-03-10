"""
Prime Context Compiler Models - Data models for the Master Context Compiler.

This module defines the data structures used by the Prime Context Compiler,
including ContextPatch for agent-assisted compilation results and
PrimeCompilationSummary for audit records.
"""
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from thread_runtime.models import ArtifactSlot


class ContextPatch(BaseModel):
    """
    Output from PrimeContextCompilerAgent.
    
    Represents a patch to be applied to the base compiled context.
    Contains artifacts gathered during exploration and metadata about
    the compilation process.
    """
    model_config = ConfigDict(strict=True)
    
    status: Literal["complete", "incomplete", "error"] = Field(
        description="Compilation status"
    )
    artifacts: list[ArtifactSlot] = Field(
        default_factory=list,
        description="Artifacts gathered during exploration"
    )
    files_read: list[str] = Field(
        default_factory=list,
        description="Files read during exploration"
    )
    reasoning: str = Field(
        default="",
        description="Reasoning for the compilation result"
    )
    steps_used: int = Field(
        default=0,
        description="Number of steps used during exploration"
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Confidence score in the gathered context"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict,
        description="Additional metadata"
    )


class PrimeCompilationSummary(BaseModel):
    """
    Audit summary for Prime Context Compiler execution.
    
    Provides a high-level overview of the compilation process
    for quick querying and monitoring.
    """
    model_config = ConfigDict(strict=True)
    
    request_id: str = Field(description="Request identifier")
    session_id: str = Field(description="Session identifier")
    triggered_agent: bool = Field(
        description="Whether agent-assisted compilation was triggered"
    )
    steps_used: int = Field(description="Steps used by agent (0 if not triggered)")
    max_steps: int = Field(description="Maximum allowed steps")
    files_read: list[str] = Field(
        default_factory=list,
        description="Files read during exploration"
    )
    artifacts_gathered: int = Field(
        default=0,
        description="Number of artifacts gathered"
    )
    duration_ms: int = Field(description="Compilation duration in milliseconds")
    status: Literal["success", "incomplete", "error"] = Field(
        description="Compilation status"
    )
    trigger_reason: str = Field(
        default="",
        description="Reason for triggering agent (if triggered)"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp of compilation"
    )


class WorkingSetSnapshot(BaseModel):
    """
    Snapshot of Working Set at a specific step.
    
    Captures the complete state of the Working Set for audit purposes.
    """
    model_config = ConfigDict(strict=True)
    
    step: int = Field(description="Step number")
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="Timestamp of snapshot"
    )
    working_set_tokens: int = Field(
        description="Total tokens in Working Set"
    )
    events_included: list[str] = Field(
        default_factory=list,
        description="Event IDs included in Working Set"
    )
    artifact_slots: list[str] = Field(
        default_factory=list,
        description="Artifact slot IDs included"
    )
    phase: str = Field(description="Current phase")
    full_content: dict[str, Any] = Field(
        description="Complete Working Set content"
    )


class PrimeCompilerConfig(BaseModel):
    """
    Configuration for Prime Context Compiler.
    """
    model_config = ConfigDict(strict=True)
    
    max_steps: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Maximum exploration steps for agent"
    )
    intent_confidence_threshold: float = Field(
        default=0.6,
        ge=0.0,
        le=1.0,
        description="Threshold for triggering agent on low intent confidence"
    )
    complexity_threshold: float = Field(
        default=0.7,
        ge=0.0,
        le=1.0,
        description="Threshold for triggering agent on high complexity"
    )
    storage_base_path: str = Field(
        default="data/compilation/prime",
        description="Base path for audit storage"
    )
    enable_caching: bool = Field(
        default=True,
        description="Whether to cache exploration results"
    )
    cache_ttl_seconds: int = Field(
        default=300,
        description="Cache time-to-live in seconds"
    )
