"""
Scheduled Request Dispatcher - Core models and security utilities.

This module provides:
- Data models for scheduled requests and triggered records
- Signature generation and verification for security
- Storage path utilities
"""
import hashlib
import hmac
import os
import secrets
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import uuid4

from pydantic import BaseModel, Field, ConfigDict


class TriggerType(str, Enum):
    """Types of scheduled triggers."""
    DELAYED = "delayed"
    CRON = "cron"


class RequestStatus(str, Enum):
    """Status of scheduled requests."""
    PENDING = "pending"
    PAUSED = "paused"
    CANCELLED = "cancelled"


class ScheduledRequest(BaseModel):
    """
    A scheduled request created by Prime Personality.
    
    This represents a future message from the prime personality to itself,
    scheduled to be triggered at a specific time or on a recurring basis.
    """
    model_config = ConfigDict(strict=True)
    
    # Identity
    id: str = Field(default_factory=lambda: str(uuid4()), description="Unique request ID")
    
    # Content
    content: str = Field(description="The message content to be delivered")
    session_id: str = Field(description="Associated session ID")
    user_id: str = Field(description="User who created this request")
    
    # Trigger configuration
    trigger_type: TriggerType = Field(description="Type of trigger: delayed or cron")
    trigger_config: dict = Field(default_factory=dict, description="Trigger-specific configuration")
    next_trigger_at: datetime = Field(description="Next scheduled trigger time (UTC)")
    
    # Security
    prime_signature: Optional[str] = Field(default=None, description="HMAC signature to prevent tampering/hallucination")
    created_at: datetime = Field(default_factory=datetime.utcnow, description="Creation timestamp (UTC)")
    created_by: str = Field(default="prime_personality", description="Entity that created this request")
    
    # Recurrence tracking
    is_recurring: bool = Field(default=False, description="Whether this is a recurring request")
    total_triggered: int = Field(default=0, description="Total number of times triggered")
    last_triggered_at: Optional[datetime] = Field(default=None, description="Last trigger timestamp")
    
    # Status
    status: RequestStatus = Field(default=RequestStatus.PENDING, description="Current status")
    metadata: dict = Field(default_factory=dict, description="Additional metadata")
    
    def to_storage_dict(self) -> dict:
        """Convert to dict for storage (handles datetime serialization)."""
        data = self.model_dump()
        # Ensure datetime fields are ISO format strings for JSON serialization
        for key in ['next_trigger_at', 'created_at', 'last_triggered_at']:
            if data.get(key) is not None:
                if isinstance(data[key], datetime):
                    data[key] = data[key].isoformat()
        return data
    
    @classmethod
    def from_storage_dict(cls, data: dict) -> "ScheduledRequest":
        """Create from storage dict (handles datetime and enum parsing)."""
        # Parse ISO format datetime strings back to datetime objects
        for key in ['next_trigger_at', 'created_at', 'last_triggered_at']:
            if data.get(key) is not None and isinstance(data[key], str):
                data[key] = datetime.fromisoformat(data[key].replace('Z', '+00:00'))
        
        # Convert string enums to Enum instances
        if isinstance(data.get('trigger_type'), str):
            data['trigger_type'] = TriggerType(data['trigger_type'])
        if isinstance(data.get('status'), str):
            data['status'] = RequestStatus(data['status'])
        
        return cls(**data)


class TriggeredRecord(BaseModel):
    """
    Record of a triggered scheduled request.
    
    This is created after a scheduled request is triggered and serves as
    an audit log. For recurring requests, a new record is created each time.
    """
    model_config = ConfigDict(strict=True)
    
    # Identity
    id: str = Field(default_factory=lambda: str(uuid4()), description="Unique record ID")
    original_request_id: str = Field(description="ID of the original scheduled request")
    
    # Trigger info
    triggered_at: datetime = Field(default_factory=datetime.utcnow, description="When the trigger occurred (UTC)")
    trigger_sequence: int = Field(default=1, description="Sequence number for recurring requests")
    
    # Verification
    signature_valid: bool = Field(description="Whether the signature was valid at trigger time")
    
    # Result
    inbox_path: Optional[str] = Field(default=None, description="Path to the inbox file created")
    retry_count: int = Field(default=0, description="Number of retry attempts before success")
    error_message: Optional[str] = Field(default=None, description="Error message if failed")
    status: str = Field(default="success", description="Status: success, failed, or retrying")
    
    # Context
    session_id: str = Field(description="Session ID at trigger time")
    content_snapshot: str = Field(description="Content at trigger time (for audit)")
    
    def to_storage_dict(self) -> dict:
        """Convert to dict for storage."""
        data = self.model_dump()
        for key in ['triggered_at']:
            if data.get(key) is not None and isinstance(data[key], datetime):
                data[key] = data[key].isoformat()
        return data
    
    @classmethod
    def from_storage_dict(cls, data: dict) -> "TriggeredRecord":
        """Create from storage dict."""
        for key in ['triggered_at']:
            if data.get(key) is not None and isinstance(data[key], str):
                data[key] = datetime.fromisoformat(data[key].replace('Z', '+00:00'))
        return cls(**data)


class FailedRecord(BaseModel):
    """
    Record of a failed trigger attempt that can be retried.
    
    Stored separately from triggered records to allow for retry logic.
    """
    model_config = ConfigDict(strict=True)
    
    original_request_id: str = Field(description="ID of the scheduled request")
    failed_at: datetime = Field(default_factory=datetime.utcnow, description="Failure timestamp (UTC)")
    error_message: str = Field(description="Error description")
    retry_count: int = Field(default=0, description="Number of retry attempts so far")
    next_retry_at: datetime = Field(description="When to retry next")
    request_data: dict = Field(description="Full request data for retry")
    
    def to_storage_dict(self) -> dict:
        """Convert to dict for storage."""
        data = self.model_dump()
        for key in ['failed_at', 'next_retry_at']:
            if data.get(key) is not None and isinstance(data[key], datetime):
                data[key] = data[key].isoformat()
        return data


# ============================================================================
# Signature Security
# ============================================================================

def _get_signature_secret() -> str:
    """Get or generate the signature secret."""
    secret = os.getenv("PRIME_SIGNATURE_SECRET")
    if not secret:
        # Generate a new secret if not set
        secret = secrets.token_hex(32)
        os.environ["PRIME_SIGNATURE_SECRET"] = secret
    return secret


def generate_signature(session_id: str, created_at: str, content: str) -> str:
    """
    Generate an HMAC signature to prevent tampering/hallucination.
    
    This signature is generated using a secret known only to Prime Personality
    and the Scheduled Request Dispatcher. When a request is triggered, the
    dispatcher verifies this signature to ensure it was legitimately created.
    
    Args:
        session_id: The session ID
        created_at: ISO format timestamp string
        content: The request content
        
    Returns:
        Signature string in format "sig:{16-char-hex}"
    """
    secret = _get_signature_secret()
    
    # Combine data in a consistent order
    data = f"{session_id}:{created_at}:{content}"
    
    # Generate HMAC-SHA256
    signature = hmac.new(
        secret.encode('utf-8'),
        data.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()[:16]  # First 16 chars provide sufficient collision resistance
    
    return f"sig:{signature}"


def verify_signature(request: ScheduledRequest) -> bool:
    """
    Verify the signature of a scheduled request.
    
    Args:
        request: The scheduled request to verify
        
    Returns:
        True if signature is valid, False otherwise
    """
    try:
        # Format created_at as ISO string for consistent hashing
        created_at_str = request.created_at.isoformat()
        
        expected = generate_signature(
            request.session_id,
            created_at_str,
            request.content
        )
        
        return request.prime_signature == expected
    except Exception:
        return False


def create_scheduled_request(
    content: str,
    session_id: str,
    user_id: str,
    trigger_type: TriggerType,
    trigger_config: dict,
    next_trigger_at: datetime,
    is_recurring: bool = False,
    metadata: dict = None,
) -> ScheduledRequest:
    """
    Factory function to create a properly signed scheduled request.
    
    This should ONLY be called from Prime Personality context.
    
    Args:
        content: The message content
        session_id: Associated session ID
        user_id: User ID
        trigger_type: Type of trigger
        trigger_config: Trigger configuration (delay_seconds or cron_expr)
        next_trigger_at: When to trigger (UTC)
        is_recurring: Whether this repeats
        metadata: Additional metadata
        
    Returns:
        A new ScheduledRequest with valid signature
    """
    now = datetime.utcnow()
    
    # Create the request first without signature
    request = ScheduledRequest(
        content=content,
        session_id=session_id,
        user_id=user_id,
        trigger_type=trigger_type,
        trigger_config=trigger_config,
        next_trigger_at=next_trigger_at,
        is_recurring=is_recurring,
        created_at=now,
        metadata=metadata or {},
    )
    
    # Generate signature using the data
    request.prime_signature = generate_signature(
        session_id,
        now.isoformat(),
        content
    )
    
    return request


# ============================================================================
# Storage Path Utilities
# ============================================================================

def get_scheduler_base_path(base_path: str = "./data") -> str:
    """Get the base path for scheduler storage."""
    return os.path.join(base_path, "scheduler")


def get_scheduled_dir(base_path: str = "./data") -> str:
    """Get the directory for pending scheduled requests."""
    return os.path.join(get_scheduler_base_path(base_path), "scheduled")


def get_triggered_dir(base_path: str = "./data", date_str: str = None) -> str:
    """Get the directory for triggered records, organized by date."""
    if date_str is None:
        date_str = datetime.utcnow().strftime("%Y-%m-%d")
    return os.path.join(get_scheduler_base_path(base_path), "triggered", date_str)


def get_failed_dir(base_path: str = "./data") -> str:
    """Get the directory for failed trigger attempts."""
    return os.path.join(get_scheduler_base_path(base_path), "failed")


def get_scheduler_index_path(base_path: str = "./data") -> str:
    """Get the path to the scheduler index file."""
    return os.path.join(get_scheduler_base_path(base_path), "index.jsonl")
