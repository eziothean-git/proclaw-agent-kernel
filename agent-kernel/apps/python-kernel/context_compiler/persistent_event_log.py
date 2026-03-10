"""
Persistent Event Log - File-system backed Event Log for Prime Context Compiler.

Provides persistence for Event Log entries with append-only write semantics
for audit and debugging purposes.
"""
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog

from thread_runtime.event_log import EventLogManager
from thread_runtime.models import Event, EventType, Phase

logger = structlog.get_logger()


class PersistentEventLog(EventLogManager):
    """
    Event Log Manager with file-system persistence.
    
    Extends the in-memory EventLogManager with append-only file persistence,
    ensuring complete audit trail for Prime Context Compiler operations.
    
    Storage Format:
        - events.jsonl: Append-only line-delimited JSON events
        - Each line is a complete Event serialized as JSON
    
    Usage:
        event_log = PersistentEventLog(
            log_id="prime_compiler_req_123",
            storage_path="data/compilation/prime/req_123/events.jsonl"
        )
        event_log.append(EventType.TOOL_CALL, ...)
        # Automatically persisted to file
    """
    
    def __init__(self, log_id: str, storage_path: str):
        """
        Initialize persistent event log.
        
        Args:
            log_id: Unique identifier for this log
            storage_path: Path to the events.jsonl file
        """
        super().__init__(task_id=log_id)
        self.storage_path = Path(storage_path)
        self.logger = logger.bind(
            component="PersistentEventLog",
            log_id=log_id,
            storage_path=str(storage_path),
        )
        
        # Ensure storage directory exists
        self._ensure_storage()
        
        # Load existing events if file exists
        self._load_existing_events()
    
    def _ensure_storage(self) -> None:
        """Create storage directory if it doesn't exist."""
        try:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            self.logger.debug("Storage directory ensured")
        except Exception as e:
            self.logger.error(
                "Failed to create storage directory",
                error=str(e),
            )
            raise
    
    def _load_existing_events(self) -> None:
        """Load existing events from file if present."""
        if not self.storage_path.exists():
            self.logger.debug("No existing events file found")
            return
        
        try:
            with open(self.storage_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    
                    try:
                        data = json.loads(line)
                        # Convert string types back to proper types
                        data = self._deserialize_event_data(data)
                        event = Event(**data)
                        self.log.events.append(event)
                    except json.JSONDecodeError as e:
                        self.logger.warning(
                            "Failed to parse event line",
                            line_num=line_num,
                            error=str(e),
                        )
                    except Exception as e:
                        self.logger.warning(
                            "Failed to load event",
                            line_num=line_num,
                            error=str(e),
                        )
            
            self.logger.info(
                "Loaded existing events",
                count=len(self.log.events),
            )
        
        except Exception as e:
            self.logger.error(
                "Failed to load existing events",
                error=str(e),
            )
    
    def _deserialize_event_data(self, data: dict[str, Any]) -> dict[str, Any]:
        """
        Deserialize event data from JSON.
        
        Converts string representations back to proper types:
        - timestamp: str -> datetime
        - event_type: str -> EventType
        - phase: str -> Phase
        
        Args:
            data: Raw event data from JSON
            
        Returns:
            Deserialized event data
        """
        # Convert timestamp string to datetime
        if 'timestamp' in data and isinstance(data['timestamp'], str):
            try:
                data['timestamp'] = datetime.fromisoformat(data['timestamp'])
            except ValueError:
                # If parsing fails, Pydantic will use default_factory
                pass
        
        # Convert event_type string to Enum
        if 'event_type' in data and isinstance(data['event_type'], str):
            try:
                data['event_type'] = EventType(data['event_type'])
            except ValueError:
                # If invalid value, try to get from value
                for et in EventType:
                    if et.value == data['event_type']:
                        data['event_type'] = et
                        break
        
        # Convert phase string to Enum
        if 'phase' in data and isinstance(data['phase'], str):
            try:
                data['phase'] = Phase(data['phase'])
            except ValueError:
                # If invalid value, try to get from value
                for p in Phase:
                    if p.value == data['phase']:
                        data['phase'] = p
                        break
        
        return data
    
    def append(
        self,
        event_type: EventType,
        actor: str,
        phase: Phase,
        content: dict[str, Any],
        metadata: dict[str, Any] | None = None,
    ) -> Event:
        """
        Append event to log and persist to file.
        
        Overrides parent method to add file persistence.
        Events are appended atomically to the JSONL file.
        
        Args:
            event_type: Type of event
            actor: ID of the actor
            phase: Current execution phase
            content: Event payload
            metadata: Additional metadata
            
        Returns:
            The created Event
        """
        # Call parent to create event and add to memory
        event = super().append(
            event_type=event_type,
            actor=actor,
            phase=phase,
            content=content,
            metadata=metadata,
        )
        
        # Persist to file
        self._persist_event(event)
        
        return event
    
    def _persist_event(self, event: Event) -> None:
        """
        Persist a single event to file.
        
        Uses append-only write for durability and audit integrity.
        
        Args:
            event: Event to persist
        """
        try:
            # Serialize event to JSON
            event_data = event.model_dump()
            
            # Handle datetime serialization
            def serialize_datetime(obj):
                if isinstance(obj, datetime):
                    return obj.isoformat()
                raise TypeError(f"Object of type {type(obj)} is not JSON serializable")
            
            json_line = json.dumps(event_data, default=serialize_datetime) + '\n'
            
            # Append to file atomically
            with open(self.storage_path, 'a', encoding='utf-8') as f:
                f.write(json_line)
                f.flush()
                # Ensure data is written to disk
                os.fsync(f.fileno())
            
            self.logger.debug(
                "Event persisted",
                event_id=event.event_id,
                event_type=event.event_type.value,
            )
        
        except Exception as e:
            self.logger.error(
                "Failed to persist event",
                event_id=event.event_id,
                error=str(e),
            )
            # Don't raise - we still have the event in memory
    
    def export_to_file(self, export_path: str | None = None) -> str:
        """
        Export complete log to a file.
        
        Args:
            export_path: Optional custom export path
            
        Returns:
            Path to exported file
        """
        if export_path is None:
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            export_path = self.storage_path.parent / f"export_{timestamp}.json"
        
        export_path = Path(export_path)
        
        try:
            export_data = {
                "log_id": self.task_id,
                "exported_at": datetime.utcnow().isoformat(),
                "total_events": len(self.log.events),
                "events": [event.model_dump() for event in self.log.events],
            }
            
            with open(export_path, 'w', encoding='utf-8') as f:
                json.dump(export_data, f, indent=2, default=str)
            
            self.logger.info(
                "Log exported",
                export_path=str(export_path),
                event_count=len(self.log.events),
            )
            
            return str(export_path)
        
        except Exception as e:
            self.logger.error(
                "Failed to export log",
                error=str(e),
            )
            raise
    
    def get_storage_stats(self) -> dict[str, Any]:
        """
        Get storage statistics.
        
        Returns:
            Dict with storage metadata
        """
        try:
            file_size = 0
            if self.storage_path.exists():
                file_size = self.storage_path.stat().st_size
            
            return {
                "storage_path": str(self.storage_path),
                "file_exists": self.storage_path.exists(),
                "file_size_bytes": file_size,
                "file_size_kb": round(file_size / 1024, 2),
                "event_count": len(self.log.events),
                "avg_event_size_bytes": round(file_size / max(len(self.log.events), 1), 2),
            }
        
        except Exception as e:
            self.logger.error("Failed to get storage stats", error=str(e))
            return {
                "storage_path": str(self.storage_path),
                "error": str(e),
            }
