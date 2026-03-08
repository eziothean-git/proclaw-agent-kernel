"""
Master Context Compiler - Compiles context for the main personality (Prime).
Follows code rules first, model-assisted when needed.
"""
import structlog
from typing import Any
from datetime import datetime

from schemas.models import Request, Session, CompiledContext

logger = structlog.get_logger()


class MasterContextCompiler:
    """
    Compiles context for Prime Personality.
    Uses deterministic code rules as primary mechanism.
    """
    
    def __init__(self):
        self.logger = logger.bind(component="MasterContextCompiler")
        
    def compile(
        self,
        request: Request,
        session: Session,
        additional_context: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """
        Compile context for Prime Personality.
        
        Args:
            request: The current user request
            session: Session state information
            additional_context: Any additional context to include
            
        Returns:
            Compiled context dictionary
        """
        self.logger.info(
            "Compiling master context",
            request_id=request.id,
            session_id=session.id,
        )
        
        # Build context using deterministic rules
        context = {
            "request": {
                "id": request.id,
                "message": request.message,
                "created_at": request.created_at.isoformat(),
            },
            "session": {
                "id": session.id,
                "task_count": session.task_count,
                "created_at": session.created_at.isoformat(),
                "last_activity": session.last_activity.isoformat(),
            },
            "compilation_rules": self._get_compilation_rules(),
        }
        
        # Add historical context if available
        if session.task_count > 0:
            context["session_history"] = {
                "total_tasks": session.task_count,
                "recent_topics": [],  # TODO: Extract from memory
            }
        
        # Add additional context if provided
        if additional_context:
            context["additional"] = additional_context
        
        return context
    
    def _get_compilation_rules(self) -> list[str]:
        """Get compilation rules for the personality."""
        return [
            "Focus on user intent, not implementation details",
            "Decompose complex requests into discrete processes",
            "Identify required capabilities early",
            "Flag security-sensitive operations",
            "Prioritize user safety and system integrity",
            "Maintain session continuity across processes",
        ]


# Singleton instance
_master_compiler: MasterContextCompiler | None = None


def get_master_compiler() -> MasterContextCompiler:
    """Get or create singleton instance."""
    global _master_compiler
    if _master_compiler is None:
        _master_compiler = MasterContextCompiler()
    return _master_compiler
