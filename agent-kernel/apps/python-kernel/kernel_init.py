"""
Kernel Initialization - Setup and registration of kernel components.

This module handles:
- Registration of local skills
- Loading configurations
- Initialization of singletons
- Setup of OS interface
"""
import structlog

from executors_client.local_skill_registry import get_local_skill_registry
from skills.agentic_os_interface import get_os_interface_skill
from skills.skill_adapters import (
    FileSystemSkillAdapter,
    ShellSkillAdapter,
    ScheduledRequestSkillAdapter,
)

logger = structlog.get_logger()


async def initialize_kernel() -> None:
    """
    Initialize the Agent Kernel.
    
    This should be called once at application startup.
    """
    logger.info("Initializing Agent Kernel...")
    
    # Register local skills
    await _register_local_skills()
    
    # Start OS interface
    await _start_os_interface()
    
    logger.info("Agent Kernel initialized successfully")


async def _register_local_skills() -> None:
    """Register local Python skills."""
    registry = get_local_skill_registry()
    
    # Register file system skill (with adapter)
    fs_skill = FileSystemSkillAdapter()
    registry.register(
        skill_name="fs-skill",
        skill_instance=fs_skill,
        tool_schemas={
            "read_file": {
                "name": "read_file",
                "description": "Read contents of a file",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                    },
                    "required": ["path"],
                },
            },
            "write_file": {
                "name": "write_file",
                "description": "Write content to a file",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "content": {"type": "string"},
                    },
                    "required": ["path", "content"],
                },
            },
            "list_directory": {
                "name": "list_directory",
                "description": "List directory contents",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                    },
                    "required": ["path"],
                },
            },
        },
    )
    logger.info("Registered fs-skill")
    
    # Register shell skill (with adapter)
    shell_skill = ShellSkillAdapter()
    registry.register(
        skill_name="shell-skill",
        skill_instance=shell_skill,
        tool_schemas={
            "execute": {
                "name": "execute",
                "description": "Execute a shell command",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "command": {"type": "string"},
                        "timeout": {"type": "integer"},
                        "working_dir": {"type": "string"},
                    },
                    "required": ["command"],
                },
            },
        },
    )
    logger.info("Registered shell-skill")
    
    # Register scheduled request skill (for Prime Personality context)
    scheduled_skill = ScheduledRequestSkillAdapter()
    registry.register(
        skill_name="scheduled-request",
        skill_instance=scheduled_skill,
        tool_schemas={
            "create_delayed_request": {
                "name": "create_delayed_request",
                "description": "Create a delayed request that triggers after a specified time",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "user_id": {"type": "string"},
                        "content": {"type": "string"},
                        "delay_seconds": {"type": "integer"},
                        "is_recurring": {"type": "boolean"},
                        "metadata": {"type": "object"},
                    },
                    "required": ["session_id", "user_id", "content", "delay_seconds"],
                },
            },
            "create_cron_request": {
                "name": "create_cron_request",
                "description": "Create a cron-based recurring request",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "user_id": {"type": "string"},
                        "content": {"type": "string"},
                        "cron_expression": {"type": "string"},
                        "metadata": {"type": "object"},
                    },
                    "required": ["session_id", "user_id", "content", "cron_expression"],
                },
            },
            "list_scheduled_requests": {
                "name": "list_scheduled_requests",
                "description": "List scheduled requests with optional filtering",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "session_id": {"type": "string"},
                        "status": {"type": "string"},
                        "limit": {"type": "integer"},
                    },
                },
            },
            "get_scheduled_request": {
                "name": "get_scheduled_request",
                "description": "Get details of a specific scheduled request",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "request_id": {"type": "string"},
                    },
                    "required": ["request_id"],
                },
            },
            "cancel_scheduled_request": {
                "name": "cancel_scheduled_request",
                "description": "Cancel a pending scheduled request",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "request_id": {"type": "string"},
                        "reason": {"type": "string"},
                    },
                    "required": ["request_id"],
                },
            },
            "pause_scheduled_request": {
                "name": "pause_scheduled_request",
                "description": "Pause a pending scheduled request",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "request_id": {"type": "string"},
                        "reason": {"type": "string"},
                    },
                    "required": ["request_id"],
                },
            },
            "resume_scheduled_request": {
                "name": "resume_scheduled_request",
                "description": "Resume a paused scheduled request",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "request_id": {"type": "string"},
                    },
                    "required": ["request_id"],
                },
            },
            "get_statistics": {
                "name": "get_statistics",
                "description": "Get statistics about scheduled requests",
                "parameters": {
                    "type": "object",
                    "properties": {},
                },
            },
        },
    )
    logger.info("Registered scheduled-request skill")
    
    logger.info(
        "Local skills registered",
        count=len(registry.list_available()),
        skills=registry.list_available(),
    )


async def _start_os_interface() -> None:
    """Start the Agentic OS Interface."""
    os_interface = get_os_interface_skill()
    await os_interface.start()
    logger.info("Agentic OS Interface started")


async def shutdown_kernel() -> None:
    """
    Shutdown the Agent Kernel gracefully.
    
    This should be called at application shutdown.
    """
    logger.info("Shutting down Agent Kernel...")
    
    # Stop OS interface
    os_interface = get_os_interface_skill()
    await os_interface.stop()
    
    logger.info("Agent Kernel shutdown complete")
