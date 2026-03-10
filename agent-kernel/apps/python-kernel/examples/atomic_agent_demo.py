"""
Usage Example - Demonstrating the new Atomic Agent architecture.

This example shows how to use the new components for:
1. Creating and running an Agent Thread
2. Inspecting thread state via Event Log
3. Upper layer intervention
"""
import asyncio
from datetime import datetime

# Initialize kernel
from kernel_init import initialize_kernel

# Core components
from thread_runtime.agent_thread import AgentThread
from thread_runtime.scheduler import get_scheduler
from thread_runtime.working_set_builder import WorkingSetBuilder
from executors_client.coordinator_interface import get_execution_coordinator
from schemas.models import CompiledContext, TaskSnapshot, TaskStatus


async def example_usage():
    """Example of using the new atomic agent architecture."""
    
    # 1. Initialize kernel (registers skills, starts OS interface)
    await initialize_kernel()
    print("✓ Kernel initialized")
    
    # 2. Create a task
    task = TaskSnapshot(
        id="task_example_001",
        session_id="session_001",
        process_id="process_001",
        status=TaskStatus.IDLE,
        goal="List files in /tmp directory",
        constraints=["max_steps: 10"],
        allowed_capabilities=["fs-skill", "shell-skill"],
    )
    
    # 3. Create compiled context
    context = CompiledContext(
        task_id=task.id,
        session_context={
            "session_id": task.session_id,
            "user_id": "user_001",
            "request_id": "req_001",
            "mock_tool_call": None,  # No mock tool call for demo
        },
        task_goal=task.goal,
        constraints=["max_steps: 10"],  # List of constraint strings
        allowed_capabilities=task.allowed_capabilities,
        forbidden_capabilities=[],
    )
    
    # 4. Create Agent Thread
    agent = AgentThread(
        task=task,
        compiled_context=context,
        coordinator=get_execution_coordinator(),
        ws_builder=WorkingSetBuilder(),
    )
    print(f"✓ Agent Thread created: {agent.thread_id}")
    
    # 5. Run the agent (in production, this would be done by scheduler)
    # For demo, we'll just show the structure
    print("\n--- Agent Thread Structure ---")
    print(f"Thread ID: {agent.thread_id}")
    print(f"Task ID: {agent.task.id}")
    print(f"Current Phase: {agent.current_phase.value}")
    print(f"Event Log: {agent.event_log.get_count()} events")
    
    # 6. Show Event Log inspection (what upper layer sees)
    print("\n--- Event Log Export (for upper layer inspection) ---")
    log_export = agent.get_event_log_export()
    print(f"Thread ID: {log_export['thread_id']}")
    print(f"Current Phase: {log_export['current_phase']}")
    print(f"Step Count: {log_export['step_count']}")
    print(f"Is Paused: {log_export['is_paused']}")
    
    # 7. Show Scheduler intervention APIs
    print("\n--- Scheduler Intervention APIs ---")
    scheduler = get_scheduler()
    
    # Register thread with scheduler (normally done automatically)
    scheduler.active_threads[task.id] = agent
    
    # Get thread info
    info = scheduler.get_active_thread_info(task.id)
    print(f"Active Thread Info: {info}")
    
    # Get full event log
    full_log = await scheduler.get_thread_log(task.id)
    print(f"Full Log Available: {full_log is not None}")
    
    # Intervention examples (would work if agent was running):
    # await scheduler.pause_task(task.id, "Need to review")
    # await scheduler.update_thread_phase(task.id, "execute")
    # await scheduler.resume_task(task.id)
    
    print("\n✓ Example complete!")
    
    # Cleanup
    scheduler.active_threads.pop(task.id, None)


async def demonstrate_working_set():
    """Demonstrate Working Set Builder."""
    from thread_runtime.event_log import EventLogManager
    from thread_runtime.models import EventType, Phase, ArtifactSlot
    
    print("\n=== Working Set Builder Demo ===\n")
    
    # Create components
    event_log = EventLogManager("demo_task")
    ws_builder = WorkingSetBuilder()
    
    # Add some events
    event_log.append_tool_call(
        actor="agent_001",
        phase=Phase.EXPLORE,
        skill_name="fs-skill",
        tool_name="list_directory",
        parameters={"path": "/tmp"},
    )
    
    event_log.append_tool_result(
        actor="agent_001",
        phase=Phase.EXPLORE,
        skill_name="fs-skill",
        tool_name="list_directory",
        success=True,
        result={"files": ["file1.txt", "file2.txt"]},
    )
    
    # Create artifact slots
    artifacts = {
        "module_map": ArtifactSlot(
            slot_id="slot_001",
            slot_type="module_map",
            content={"modules": ["main", "utils"]},
            priority=8,
            phase_created=Phase.EXPLORE,
        ),
        "context_report": ArtifactSlot(
            slot_id="slot_002",
            slot_type="context_report",
            content="Directory contains 2 files",
            priority=6,
            phase_created=Phase.EXPLORE,
        ),
    }
    
    # Build Working Set for Explore phase
    working_set = ws_builder.build(
        task_id="demo_task",
        task_goal="Explore directory structure",
        event_log=event_log,
        artifact_slots=artifacts,
        immutable_input={"constraints": ["be careful"]},
        current_phase=Phase.EXPLORE,
        step_number=3,
    )
    
    print("Working Set built:")
    print(f"  Phase: {working_set.current_phase.value}")
    print(f"  Step: {working_set.step_number}")
    print(f"  Token Estimate: {working_set.token_estimate}")
    print(f"  Active Artifacts: {list(working_set.active_artifacts.keys())}")
    print(f"  Recent Observations: {len(working_set.recent_observations)}")
    
    # Show prompt preview
    print("\n--- Prompt Preview (truncated) ---")
    prompt = working_set.to_prompt()
    print(prompt[:500] + "...")


async def demonstrate_output_parser():
    """Demonstrate Agent Output Parser."""
    from thread_runtime.output_parser import get_output_parser
    from thread_runtime.models import Phase
    
    print("\n=== Agent Output Parser Demo ===\n")
    
    parser = get_output_parser()
    
    # Example 1: Structured YAML output
    yaml_output = """```yaml
intent: tool_call
reasoning: "Need to read the file content"
tool_calls:
  - skill: fs-skill
    tool: read_file
    parameters:
      path: "/tmp/test.txt"
```"""
    
    parsed = parser.parse(yaml_output, Phase.EXPLORE)
    print(f"Parsed Intent: {parsed.intent_type.value}")
    print(f"Confidence: {parsed.confidence}")
    print(f"Tool Calls: {len(parsed.tool_calls)}")
    if parsed.tool_calls:
        print(f"  - {parsed.tool_calls[0].skill_name}.{parsed.tool_calls[0].tool_name}")
    
    # Example 2: Phase transition
    transition_output = """```yaml
intent: phase_transition
from_phase: explore
to_phase: execute
reason: "Have gathered enough context"
```"""
    
    parsed = parser.parse(transition_output, Phase.EXPLORE)
    print(f"\nParsed Intent: {parsed.intent_type.value}")
    if parsed.phase_transition:
        print(f"Transition: {parsed.phase_transition.from_phase.value} -> {parsed.phase_transition.to_phase.value}")
    
    # Example 3: Final answer
    answer_output = """```yaml
intent: final_answer
answer: "Task completed successfully!"
success: true
```"""
    
    parsed = parser.parse(answer_output, Phase.EXECUTE)
    print(f"\nParsed Intent: {parsed.intent_type.value}")
    print(f"Final Answer: {parsed.final_answer}")


async def main():
    """Run all demonstrations."""
    print("=" * 60)
    print("Atomic Agent Implementation Demo")
    print("=" * 60)
    
    await example_usage()
    await demonstrate_working_set()
    await demonstrate_output_parser()
    
    print("\n" + "=" * 60)
    print("Demo Complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
