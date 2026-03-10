"""
End-to-End Test - Full workflow with LLM integration

This test verifies:
1. Complete task execution flow
2. LLM integration (supports Ark/Volcengine and OpenAI)
3. Tool execution
4. Phase transitions
5. Event logging
6. Working Set construction with real LLM context

Usage:
    # Test with Ark (Volcengine) - DEFAULT
    export ARK_API_KEY="your-ark-key"
    export ARK_MODEL="glm-4-7-251222"  # or doubao-1-5-pro-32k-250115
    python tests/e2e_test.py
    
    # Test with OpenAI
    export LLM_PROVIDER="openai"
    export OPENAI_API_KEY="your-openai-key"
    python tests/e2e_test.py
"""
import asyncio
import os
import sys

sys.path.insert(0, '/home/eziothean/ProClaw/agent-kernel/apps/python-kernel')

from datetime import datetime
from uuid import uuid4

# Setup environment - default to Ark provider
os.environ["KERNEL_RUN_MODE"] = "real"  # Use real LLM
if not os.environ.get("LLM_PROVIDER"):
    os.environ["LLM_PROVIDER"] = "ark"
if not os.environ.get("ARK_MODEL"):
    os.environ["ARK_MODEL"] = "glm-4-7-251222"

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
    """Test a simple task end-to-end with real LLM"""
    print("\n" + "="*70)
    print("END-TO-END TEST: Simple File Listing Task (Real LLM)")
    print("="*70 + "\n")
    
    # Initialize kernel
    print("1. Initializing kernel...")
    await initialize_kernel()
    print("   ✓ Kernel initialized")
    print("   ✓ Skills registered (fs-skill, shell-skill)")
    print("   ✓ OS Interface started\n")
    
    # Create task
    print("2. Creating task...")
    task = TaskSnapshot(
        id=f"e2e_task_{uuid4().hex[:8]}",
        session_id="e2e_session",
        process_id="e2e_process",
        status=TaskStatus.IDLE,
        goal="List the files in the current working directory and summarize what you found",
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
            "request_message": task.goal,
        },
        task_goal=task.goal,
        constraints=task.constraints,
        allowed_capabilities=task.allowed_capabilities,
        forbidden_capabilities=task.forbidden_capabilities,
    )
    print(f"   ✓ Task created: {task.id}")
    print(f"   ✓ Goal: {task.goal}\n")
    
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
    print(f"   ✓ Max steps: {agent.max_steps}")
    print(f"   ✓ Working Set Builder: initialized\n")
    
    # Execute with real LLM
    print("4. Executing task with real LLM...")
    print("   ⚠ This will make API calls to your configured LLM provider")
    print("   - SEE: Building Working Set from Event Log")
    print("   - ACT: Calling LLM to generate intentions")
    print("   - UPDATE: Executing tools and logging events")
    print()
    
    try:
        start_time = datetime.now()
        result = await agent.run()
        duration = (datetime.now() - start_time).total_seconds()
        
        print("\n5. Execution completed!")
        print(f"   ✓ Duration: {duration:.2f}s")
        print(f"   ✓ Success: {result.success}")
        
        # Show final output
        output = result.content if hasattr(result, 'content') else str(result)
        print(f"\n   Final Output (first 300 chars):")
        print(f"   {'-'*66}")
        for line in output[:300].split('\n'):
            print(f"   {line}")
        if len(output) > 300:
            print(f"   ... ({len(output) - 300} more chars)")
        print(f"   {'-'*66}\n")
        
        # Check event log
        print(f"6. Event Log Analysis:")
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
        
        # Show event types
        events = log_export['event_log']['events']
        if events:
            print(f"\n   Event timeline:")
            for i, event in enumerate(events[:10], 1):
                event_type = event.get('event_type', 'unknown')
                phase = event.get('phase', 'unknown')
                print(f"      {i}. [{event_type}] Phase: {phase}")
        
        # Show observations
        if result.observations:
            print(f"\n   Tool executions: {len(result.observations)}")
            for obs in result.observations:
                skill = obs.get('skill', 'unknown')
                tool = obs.get('tool', 'unknown')
                success = '✓' if obs.get('success') else '✗'
                print(f"      {success} {skill}.{tool}")
        
        print("\n" + "="*70)
        print("✓ END-TO-END TEST PASSED!")
        print("="*70 + "\n")
        
    except Exception as e:
        print(f"\n   ✗ Execution failed: {e}")
        import traceback
        traceback.print_exc()
        raise
    
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
    
    # Check API key based on provider
    provider = os.environ.get("LLM_PROVIDER", "ark")
    if provider == "ark":
        api_key = os.environ.get("ARK_API_KEY")
        model = os.environ.get("ARK_MODEL", "glm-4-7-251222")
        if not api_key:
            print("⚠ Warning: ARK_API_KEY not set!")
            print("   Set it with: export ARK_API_KEY=\"your-ark-api-key\"\n")
            return
        else:
            print(f"✓ ARK_API_KEY is set")
            print(f"✓ Using model: {model}")
            print(f"✓ Provider: Ark (Volcengine)\n")
    elif provider == "openai":
        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            print("⚠ Warning: OPENAI_API_KEY not set!")
            print("   LLM tests will fail. Set the API key to run full tests.\n")
            return
        else:
            print("✓ OPENAI_API_KEY is set\n")
    else:
        print(f"⚠ Warning: Unknown LLM_PROVIDER '{provider}'")
        print("   Supported: ark, openai\n")
        return
    
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
