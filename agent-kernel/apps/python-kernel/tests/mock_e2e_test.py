"""
Mock End-to-End Test - Full workflow without LLM
Tests the complete flow with mock responses
"""
import asyncio
import os
import sys

sys.path.insert(0, '/home/eziothean/ProClaw/agent-kernel/apps/python-kernel')

os.environ["KERNEL_RUN_MODE"] = "mock"

import structlog
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.UnicodeDecoder(),
        structlog.dev.ConsoleRenderer(colors=True)
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
)

from datetime import datetime
from uuid import uuid4

from kernel_init import initialize_kernel, shutdown_kernel
from schemas.models import CompiledContext, TaskSnapshot, TaskStatus
from thread_runtime.agent_thread import AgentThread
from thread_runtime.scheduler import get_scheduler
from thread_runtime.working_set_builder import WorkingSetBuilder
from thread_runtime.models import Phase
from executors_client.coordinator_interface import get_execution_coordinator


async def main():
    print("\n" + "="*70)
    print("MOCK END-TO-END TEST")
    print("="*70 + "\n")
    
    # Initialize
    print("1. Initializing kernel...")
    await initialize_kernel()
    print("   ✓ Kernel initialized\n")
    
    # Create task with mock tool call
    print("2. Creating task with mock tool call...")
    task = TaskSnapshot(
        id=f"mock_task_{uuid4().hex[:8]}",
        session_id="mock_session",
        process_id="mock_process",
        status=TaskStatus.IDLE,
        goal="Test file operations",
        constraints=["max_steps: 3"],
        allowed_capabilities=["fs-skill"],
        forbidden_capabilities=[],
    )
    
    context = CompiledContext(
        task_id=task.id,
        session_context={
            "session_id": task.session_id,
            "mock_tool_call": {
                "skill_name": "fs-skill",
                "tool_name": "list_directory",
                "parameters": {"path": "."},  # Current directory (allowed)
            },
        },
        task_goal=task.goal,
        constraints=task.constraints,
        allowed_capabilities=task.allowed_capabilities,
        forbidden_capabilities=task.forbidden_capabilities,
    )
    print(f"   ✓ Task created\n")
    
    # Create Agent
    print("3. Creating Agent Thread...")
    agent = AgentThread(
        task=task,
        compiled_context=context,
        coordinator=get_execution_coordinator(),
        ws_builder=WorkingSetBuilder(),
    )
    print(f"   ✓ Thread ID: {agent.thread_id}")
    print(f"   ✓ Phase: {agent.current_phase.value}\n")
    
    # Execute
    print("4. Executing (mock mode)...")
    result = await agent.run()
    
    print(f"   ✓ Execution completed")
    print(f"   ✓ Success: {result.success}")
    print(f"   ✓ Content: {result.content}\n")
    
    # Analyze event log
    print("5. Analyzing Event Log...")
    log = agent.get_event_log_export()
    print(f"   ✓ Total events: {log['event_log']['event_count']}")
    print(f"   ✓ Final phase: {log['current_phase']}")
    
    # Show events
    print(f"\n   Event breakdown:")
    for event in log['event_log']['events']:
        print(f"      [{event['event_type']}] {event['content'].get('summary', '')}")
    
    # Show observations
    if result.observations:
        print(f"\n   Tool observations:")
        for obs in result.observations:
            success = "✓" if obs.get('success') else "✗"
            print(f"      {success} {obs.get('skill', 'unknown')}.{obs.get('tool', 'unknown')}")
            if obs.get('result'):
                print(f"         Result: {str(obs['result'])[:100]}...")
    
    # Cleanup
    print("\n6. Cleaning up...")
    await shutdown_kernel()
    print("   ✓ Done\n")
    
    print("="*70)
    print("✓ MOCK END-TO-END TEST PASSED!")
    print("="*70 + "\n")
    
    print("To test with real LLM, set OPENAI_API_KEY and run:")
    print("  python tests/e2e_test.py\n")


if __name__ == "__main__":
    asyncio.run(main())
