"""
Prime Compilation Auditor - Query and audit interface for Prime Context Compiler.

Provides read-only access to compilation records for debugging, monitoring,
and compliance auditing purposes.
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Any

import structlog

from context_compiler.models import (
    PrimeCompilationSummary,
    WorkingSetSnapshot,
)
from thread_runtime.models import Event

logger = structlog.get_logger()


class PrimeCompilationAuditor:
    """
    Auditor for Prime Context Compiler operations.
    
    Provides query capabilities for:
    - Compilation summaries
    - Full event logs
    - Working Set history
    - Gathered artifacts
    - Cross-request analysis
    
    Usage:
        auditor = PrimeCompilationAuditor()
        
        # Get summary
        summary = auditor.get_summary("req_123")
        
        # Get full events
        events = auditor.get_full_events("req_123")
        
        # List compilations for a session
        compilations = auditor.list_compilations(session_id="sess_456")
    """
    
    BASE_PATH: str = "data/compilation/prime"
    
    def __init__(self, base_path: str | None = None):
        """
        Initialize auditor.
        
        Args:
            base_path: Override default storage base path
        """
        self.base_path = Path(base_path or self.BASE_PATH)
        self.logger = logger.bind(
            component="PrimeCompilationAuditor",
            base_path=str(self.base_path),
        )
    
    def _get_request_path(self, request_id: str) -> Path:
        """Get storage path for a request."""
        return self.base_path / request_id
    
    def get_summary(self, request_id: str) -> PrimeCompilationSummary | None:
        """
        Get compilation summary for a request.
        
        Args:
            request_id: Request identifier
            
        Returns:
            Compilation summary or None if not found
        """
        summary_path = self._get_request_path(request_id) / "summary.json"
        
        if not summary_path.exists():
            self.logger.debug("Summary not found", request_id=request_id)
            return None
        
        try:
            with open(summary_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Handle datetime parsing
            if 'created_at' in data and isinstance(data['created_at'], str):
                data['created_at'] = datetime.fromisoformat(data['created_at'])
            
            return PrimeCompilationSummary(**data)
        
        except Exception as e:
            self.logger.error(
                "Failed to load summary",
                request_id=request_id,
                error=str(e),
            )
            return None
    
    def get_full_events(self, request_id: str) -> list[Event]:
        """
        Get complete event log for a request.
        
        Args:
            request_id: Request identifier
            
        Returns:
            List of events (chronological order)
        """
        events_path = self._get_request_path(request_id) / "events.jsonl"
        
        if not events_path.exists():
            self.logger.debug("Events file not found", request_id=request_id)
            return []
        
        events = []
        
        try:
            with open(events_path, 'r', encoding='utf-8') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line:
                        continue
                    
                    try:
                        data = json.loads(line)
                        
                        # Parse datetime fields
                        if 'timestamp' in data and isinstance(data['timestamp'], str):
                            data['timestamp'] = datetime.fromisoformat(data['timestamp'])
                        
                        event = Event(**data)
                        events.append(event)
                    
                    except json.JSONDecodeError as e:
                        self.logger.warning(
                            "Failed to parse event line",
                            request_id=request_id,
                            line_num=line_num,
                            error=str(e),
                        )
                    except Exception as e:
                        self.logger.warning(
                            "Failed to load event",
                            request_id=request_id,
                            line_num=line_num,
                            error=str(e),
                        )
            
            self.logger.debug(
                "Loaded events",
                request_id=request_id,
                count=len(events),
            )
            
            return events
        
        except Exception as e:
            self.logger.error(
                "Failed to load events",
                request_id=request_id,
                error=str(e),
            )
            return []
    
    def get_working_set_at_step(self, request_id: str, step: int) -> WorkingSetSnapshot | None:
        """
        Get Working Set snapshot at a specific step.
        
        Args:
            request_id: Request identifier
            step: Step number (1-indexed)
            
        Returns:
            Working Set snapshot or None if not found
        """
        ws_path = self._get_request_path(request_id) / "working_set_history" / f"step_{step:02d}.json"
        
        if not ws_path.exists():
            self.logger.debug(
                "Working set snapshot not found",
                request_id=request_id,
                step=step,
            )
            return None
        
        try:
            with open(ws_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            # Parse datetime
            if 'timestamp' in data and isinstance(data['timestamp'], str):
                data['timestamp'] = datetime.fromisoformat(data['timestamp'])
            
            return WorkingSetSnapshot(**data)
        
        except Exception as e:
            self.logger.error(
                "Failed to load working set snapshot",
                request_id=request_id,
                step=step,
                error=str(e),
            )
            return None
    
    def get_working_set_history(self, request_id: str) -> list[WorkingSetSnapshot]:
        """
        Get all Working Set snapshots for a request.
        
        Args:
            request_id: Request identifier
            
        Returns:
            List of Working Set snapshots
        """
        ws_dir = self._get_request_path(request_id) / "working_set_history"
        
        if not ws_dir.exists():
            return []
        
        snapshots = []
        
        # Find all step files and sort by step number
        step_files = sorted(ws_dir.glob("step_*.json"))
        
        for step_file in step_files:
            try:
                with open(step_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Parse datetime
                if 'timestamp' in data and isinstance(data['timestamp'], str):
                    data['timestamp'] = datetime.fromisoformat(data['timestamp'])
                
                snapshot = WorkingSetSnapshot(**data)
                snapshots.append(snapshot)
            
            except Exception as e:
                self.logger.warning(
                    "Failed to load working set snapshot",
                    request_id=request_id,
                    file=str(step_file),
                    error=str(e),
                )
        
        return snapshots
    
    def get_artifacts(self, request_id: str) -> list[dict[str, Any]]:
        """
        Get gathered artifacts for a request.
        
        Args:
            request_id: Request identifier
            
        Returns:
            List of artifact dictionaries
        """
        artifacts_path = self._get_request_path(request_id) / "artifacts.json"
        
        if not artifacts_path.exists():
            return []
        
        try:
            with open(artifacts_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        
        except Exception as e:
            self.logger.error(
                "Failed to load artifacts",
                request_id=request_id,
                error=str(e),
            )
            return []
    
    def list_compilations(
        self,
        session_id: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[PrimeCompilationSummary]:
        """
        List compilation records with optional filtering.
        
        Args:
            session_id: Filter by session ID
            limit: Maximum number of results
            offset: Skip first N results
            
        Returns:
            List of compilation summaries
        """
        if not self.base_path.exists():
            return []
        
        summaries = []
        
        # Iterate through all request directories
        for request_dir in self.base_path.iterdir():
            if not request_dir.is_dir():
                continue
            
            summary_path = request_dir / "summary.json"
            if not summary_path.exists():
                continue
            
            try:
                with open(summary_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                # Filter by session_id if specified
                if session_id and data.get('session_id') != session_id:
                    continue
                
                # Parse datetime
                if 'created_at' in data and isinstance(data['created_at'], str):
                    data['created_at'] = datetime.fromisoformat(data['created_at'])
                
                summary = PrimeCompilationSummary(**data)
                summaries.append(summary)
            
            except Exception as e:
                self.logger.warning(
                    "Failed to load summary",
                    request_dir=str(request_dir),
                    error=str(e),
                )
        
        # Sort by created_at descending (most recent first)
        summaries.sort(key=lambda s: s.created_at, reverse=True)
        
        # Apply pagination
        return summaries[offset:offset + limit]
    
    def get_compilation_stats(self, session_id: str | None = None) -> dict[str, Any]:
        """
        Get aggregate statistics about compilations.
        
        Args:
            session_id: Optional session filter
            
        Returns:
            Statistics dictionary
        """
        summaries = self.list_compilations(session_id=session_id, limit=10000)
        
        if not summaries:
            return {
                "total_compilations": 0,
                "agent_triggered_count": 0,
                "avg_steps": 0,
                "avg_duration_ms": 0,
            }
        
        total = len(summaries)
        agent_triggered = sum(1 for s in summaries if s.triggered_agent)
        avg_steps = sum(s.steps_used for s in summaries) / total
        avg_duration = sum(s.duration_ms for s in summaries) / total
        
        return {
            "total_compilations": total,
            "agent_triggered_count": agent_triggered,
            "agent_trigger_rate": round(agent_triggered / total, 2),
            "avg_steps": round(avg_steps, 2),
            "avg_duration_ms": round(avg_duration, 2),
            "total_files_read": sum(len(s.files_read) for s in summaries),
            "total_artifacts": sum(s.artifacts_gathered for s in summaries),
        }
    
    def export_full_report(self, request_id: str, export_path: str | None = None) -> str:
        """
        Export complete compilation report for a request.
        
        Args:
            request_id: Request identifier
            export_path: Optional custom export path
            
        Returns:
            Path to exported report
        """
        if export_path is None:
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            export_path = self._get_request_path(request_id) / f"full_report_{timestamp}.json"
        
        export_path = Path(export_path)
        
        try:
            report = {
                "request_id": request_id,
                "exported_at": datetime.utcnow().isoformat(),
                "summary": self.get_summary(request_id),
                "events": [e.model_dump() for e in self.get_full_events(request_id)],
                "working_set_history": [
                    ws.model_dump() for ws in self.get_working_set_history(request_id)
                ],
                "artifacts": self.get_artifacts(request_id),
            }
            
            with open(export_path, 'w', encoding='utf-8') as f:
                json.dump(report, f, indent=2, default=str)
            
            self.logger.info(
                "Full report exported",
                request_id=request_id,
                export_path=str(export_path),
            )
            
            return str(export_path)
        
        except Exception as e:
            self.logger.error(
                "Failed to export report",
                request_id=request_id,
                error=str(e),
            )
            raise
