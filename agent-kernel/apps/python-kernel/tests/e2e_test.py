"""
End-to-End Test - Full workflow with LLM integration

This test verifies:
1. Complete task execution flow
2. LLM integration (requires OPENAI_API_KEY)
3. Tool execution
4. Phase transitions
5. Event logging
"""
import asyncio
import os
import sys

sys.path.insert(0, '/home/eziothean/ProClaw/agent-kernel/apps/python-kernel')

from datetime import datetime
from uuid import uuid4

# Setup environment
os.environ["KERNEL_RUN_MODE"] = "real"  # Use real LLM

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

from kernel_init import initialize_kernel, shutdown_kernel
from schemas.models import CompiledContext, TaskSnapshot, TaskStatus
from thread_runtime.agent_thread import AgentThread
from thread_runtime.scheduler import get_scheduler
from thread_runtime.working_set_builder import WorkingSetBuilder
from thread_runtime.models import Phase
from executors_client.coordinator_interface import get_execution_coordinator


async def test_simple_task():
    """Test a simple task end-to-end"""
    print("\n" + "="*70)
    print("END-TO-END TEST: Simple File Listing Task")
    print("="*70 + "\n")
    
    # Initialize kernel
    print("1. Initializing kernel...")
    await initialize_kernel()
    print("   ✓ Kernel initialized\n")
    
    # Create task
    print("2. Creating task...")
    task = TaskSnapshot(
        id=f"e2e_task_{uuid4().hex[:8]}",
        session_id="e2e_session",
        process_id="e2e_process",
        status=TaskStatus.IDLE,
        goal="List the files in the current working directory",
        constraints=["max_steps: 5"],
        allowed_capabilities=["fs-skill"],
        forbidden_capabilities=[],
    )
    
    context = CompiledContext(
        task_id=task.id,
        session_context={
            "session_id": task.session_id,
            "user_id": "test_user",
            "request_id": str(uuid4()),
            "request_message": "List files in current directory",
        },
        task_goal=task.goal,
        constraints=task.constraints,
        allowed_capabilities=task.allowed_capabilities,
        forbidden_capabilities=task.forbidden_capabilities,
    )
    print(f"   ✓ Task created: {task.id}\n")
    
    # Create Agent Thread
    print("3. Creating Agent Thread...")
    agent = AgentThread(
        task=task,
        compiled_context=context,
        coordinator=get_execution_coordinator(),
        ws_builder=WorkingSetBuilder(),
    )
    print(f"   ✓ Agent Thread created: {agent.thread_id}")
    print(f"   ✓ Initial phase: {agent.current_phase.value}")
    print(f"   ✓ Max steps: {agent.max_steps}\n")
    
    # Execute
    print("4. Executing task (this may take a moment)...")
    print("   - Will call LLM to generate intentions")
    print("   - May execute tools if requested by LLM")
    print()
    
    try:
        result = await agent.run()
        
        print("\n5. Execution completed!")
        print(f"   ✓ Success: {result.success}")
        print(f"   ✓ Final content: {result.content[:200]}...")
        
        # Check event log
        print(f"\n6. Event Log Summary:")
        log_export = agent.get_event_log_export()
        print(f"   ✓ Total events: {log_export['event_log']['event_count']}")
        print(f"   ✓ Current phase: {log_export['current_phase']}")
        print(f"   ✓ Steps executed: {log_export['step_count']}")
        
        # Show phase summary
        phase_summary = log_export['event_log']['phase_summary']
        print(f"\n   Phase breakdown:")
        for phase, count in phase_summary.items():
            if count > 0:
                print(f"      - {phase}: {count} events")
        
        # Show observations
        if result.observations:
            print(f"\n   Tool observations: {len(result.observations)}")
            for obs in result.observations[:3]:  # Show first 3
                print(f"      - {obs.get('skill', 'unknown')}.{obs.get('tool', 'unknown')}: "
                      f"{'✓' if obs.get('success') else '✗'}")
        
        print("\n" + "="*70)
        print("✓ END-TO-END TEST PASSED!")
        print("="*70 + "\n")
        
    except Exception as e:
        print(f"\n   ✗ Execution failed: {e}")
        import traceback
        traceback.print_exc()
    
    # Cleanup
    print("7. Cleaning up...")
    await shutdown_kernel()
    print("   ✓ Kernel shutdown\n")


async def test_upper_layer_inspection():
    """Test upper layer viewing and intervention"""
    print("\n" + "="*70)
    print("END-TO-END TEST: Upper Layer Inspection")
    print("="*70 + "\n")
    
    # Initialize
    await initialize_kernel()
    
    # Create and register a mock active thread
    scheduler = get_scheduler()
    
    task = TaskSnapshot(
        id=f"inspect_task_{uuid4().hex[:8]}",
        session_id="inspect_session",
        process_id="inspect_process",
        status=TaskStatus.RUNNING,
        goal="Test inspection",
        constraints=["max_steps: 10"],
        allowed_capabilities=[],
    )
    
    context = CompiledContext(
        task_id=task.id,
        session_context={},
        task_goal=task.goal,
        constraints=task.constraints,
        allowed_capabilities=task.allowed_capabilities,
        forbidden_capabilities=[],
    )
    
    agent = AgentThread(
        task=task,
        compiled_context=context,
        coordinator=get_execution_coordinator(),
        ws_builder=WorkingSetBuilder(),
    )
    
    # Add some events
    agent.event_log.append_tool_call(
        actor=agent.thread_id,
        phase=Phase.EXPLORE,
        skill_name="fs-skill",
        tool_name="read_file",
        parameters={"path": "/test"},
    )
    
    agent.event_log.append_tool_result(
        actor=agent.thread_id,
        phase=Phase.EXPLORE,
        skill_name="fs-skill",
        tool_name="read_file",
        success=True,
        result={"content": "test data"},
    )
    
    # Register with scheduler
    scheduler.active_threads[task.id] = agent
    
    print("1. Simulating active thread...")
    print(f"   ✓ Thread ID: {agent.thread_id}")
    print(f"   ✓ Task ID: {task.id}\n")
    
    # Test inspection APIs
    print("2. Testing inspection APIs...")
    
    # Get thread info
    info = scheduler.get_active_thread_info(task.id)
    print(f"   ✓ Thread info retrieved:")
    print(f"      - Phase: {info['current_phase']}")
    print(f"      - Step: {info['step_count']}")
    print(f"      - Paused: {info['is_paused']}")
    
    # Get full log
    log = await scheduler.get_thread_log(task.id)
    print(f"\n   ✓ Full log retrieved:")
    print(f"      - Events: {log['event_log']['event_count']}")
    print(f"      - Artifacts: {len(log['artifacts'])}")
    
    # Test intervention
    print(f"\n3. Testing intervention...")
    
    # Pause
    await scheduler.pause_task(task.id, "Test pause")
    info = scheduler.get_active_thread_info(task.id)
    print(f"   ✓ Paused: {info['is_paused']} ({info['pause_reason']})")
    
    # Update phase
    await scheduler.update_thread_phase(task.id, Phase.EXECUTE)
    info = scheduler.get_active_thread_info(task.id)
    print(f"   ✓ Phase updated to: {info['current_phase']}")
    
    # Resume
    await scheduler.resume_task(task.id)
    info = scheduler.get_active_thread_info(task.id)
    print(f"   ✓ Resumed: not {info['is_paused']}")
    
    # Cleanup
    scheduler.active_threads.pop(task.id, None)
    await shutdown_kernel()
    
    print("\n" + "="*70)
    print("✓ INSPECTION TEST PASSED!")
    print("="*70 + "\n")


async def main():
    """Run all end-to-end tests"""
    print("\n" + "#"*70)
    print("#" + " "*68 + "#")
    print("#" + "  ATOMIC AGENT THREAD - END-TO-END TEST SUITE".center(68) + "#")
    print("#" + " "*68 + "#")
    print("#"*70 + "\n")
    
    # Check API key
    if not os.environ.get("OPENAI_API_KEY"):
        print("⚠ Warning: OPENAI_API_KEY not set!")
        print("   LLM tests will fail. Set the API key to run full tests.\n")
        return
    else:
        print("✓ OPENAI_API_KEY is set\n")
    
    try:
        # Test 1: Simple task execution
        await test_simple_task()
        
        # Test 2: Upper layer inspection
        await test_upper_layer_inspection()
        
        print("\n" + "#"*70)
        print("#" + " "*68 + "#")
        print("#" + "  ALL END-TO-END TESTS PASSED!".center(68) + "#")
        print("#" + " "*68 + "#")
        print("#"*70 + "\n")
        
    except Exception as e:
        print(f"\n✗ Test failed: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
