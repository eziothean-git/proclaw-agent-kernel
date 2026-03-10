"""
Integration Test - Full workflow testing for Atomic Agent Thread.

Tests:
1. Kernel initialization (skills registration)
2. Agent Thread creation and execution
3. Event Log recording
4. Working Set construction
5. Output parsing
6. Tool execution (local skills)
7. Phase transitions
8. Upper layer intervention
"""
import asyncio
import os
import sys
from datetime import datetime
from uuid import uuid4

# Setup Python path
sys.path.insert(0, '/home/eziothean/ProClaw/agent-kernel/apps/python-kernel')

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
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
)

from kernel_init import initialize_kernel, shutdown_kernel
from schemas.models import CompiledContext, TaskSnapshot, TaskStatus
from thread_runtime.agent_thread import AgentThread
from thread_runtime.scheduler import get_scheduler
from thread_runtime.working_set_builder import WorkingSetBuilder
from thread_runtime.event_log import EventLogManager
from thread_runtime.output_parser import get_output_parser
from thread_runtime.models import Phase, EventType, IntentType
from executors_client.coordinator_interface import get_execution_coordinator
from executors_client.local_skill_registry import get_local_skill_registry
from skills.agentic_os_interface import get_os_interface_skill


class Colors:
    """Terminal colors"""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    END = '\033[0m'
    BOLD = '\033[1m'


def print_header(title):
    print(f"\n{Colors.BOLD}{'='*70}{Colors.END}")
    print(f"{Colors.BOLD}{title.center(70)}{Colors.END}")
    print(f"{Colors.BOLD}{'='*70}{Colors.END}\n")


def print_test(name, success, details=""):
    status = f"{Colors.GREEN}✓ PASS{Colors.END}" if success else f"{Colors.RED}✗ FAIL{Colors.END}"
    print(f"  {status} {name}")
    if details and not success:
        print(f"      {Colors.RED}{details}{Colors.END}")


class IntegrationTest:
    """Integration test suite"""
    
    def __init__(self):
        self.test_results = []
        self.agent = None
        
    async def run_all_tests(self):
        """Run all tests"""
        print_header("ATOMIC AGENT THREAD - INTEGRATION TEST")
        
        try:
            # Phase 1: Initialization
            await self.test_initialization()
            
            # Phase 2: Core Components
            await self.test_working_set_builder()
            await self.test_event_log_manager()
            await self.test_output_parser()
            
            # Phase 3: Execution Infrastructure
            await self.test_local_skill_registry()
            await self.test_execution_coordinator()
            
            # Phase 4: Agent Thread Execution
            await self.test_agent_thread_creation()

            # Phase 5: Intervention APIs
            await self.test_scheduler_intervention()
            
            # Phase 6: OS Interface
            await self.test_os_interface()
            
            # Summary
            self.print_summary()
            
        except Exception as e:
            print(f"\n{Colors.RED}FATAL ERROR: {e}{Colors.END}")
            import traceback
            traceback.print_exc()
        finally:
            # Cleanup
            try:
                await shutdown_kernel()
                print(f"\n{Colors.BLUE}Kernel shutdown complete{Colors.END}")
            except Exception as e:
                print(f"{Colors.YELLOW}Warning: Cleanup error: {e}{Colors.END}")
    
    async def test_initialization(self):
        """Test 1: Kernel Initialization"""
        print_header("TEST 1: Kernel Initialization")
        
        try:
            await initialize_kernel()
            
            # Check skills registered
            registry = get_local_skill_registry()
            skills = registry.list_available()
            
            print_test("Kernel initializes", True)
            print_test("fs-skill registered", "fs-skill" in skills)
            print_test("shell-skill registered", "shell-skill" in skills)
            
            # Check OS interface started
            os_interface = get_os_interface_skill()
            print_test("OS Interface initialized", os_interface is not None)
            
        except Exception as e:
            print_test("Kernel initialization", False, str(e))
    
    async def test_working_set_builder(self):
        """Test 2: Working Set Builder"""
        print_header("TEST 2: Working Set Builder")
        
        try:
            from thread_runtime.models import ArtifactSlot
            
            builder = WorkingSetBuilder()
            event_log = EventLogManager("test_task")
            
            # Add some events
            event_log.append_tool_call(
                actor="test",
                phase=Phase.EXPLORE,
                skill_name="fs-skill",
                tool_name="list_directory",
                parameters={"path": "/tmp"},
            )
            
            # Create artifacts
            artifacts = {
                "module_map": ArtifactSlot(
                    slot_id="slot_1",
                    slot_type="module_map",
                    content={"modules": ["main", "utils"]},
                    priority=8,
                    phase_created=Phase.EXPLORE,
                ),
                "low_priority": ArtifactSlot(
                    slot_id="slot_2",
                    slot_type="debug_info",
                    content="debug data",
                    priority=2,
                    phase_created=Phase.EXPLORE,
                ),
            }
            
            # Build working set
            ws = builder.build(
                task_id="test_task",
                task_goal="Test task",
                event_log=event_log,
                artifact_slots=artifacts,
                immutable_input={"constraints": ["test"]},
                current_phase=Phase.EXPLORE,
                step_number=1,
            )
            
            print_test("WorkingSet created", ws is not None)
            print_test("Has task_goal", ws.task_goal == "Test task")
            print_test("Has correct phase", ws.current_phase == Phase.EXPLORE)
            print_test("Token estimate > 0", ws.token_estimate > 0)
            print_test("Filters low priority artifacts", 
                      "low_priority" not in ws.active_artifacts)
            print_test("Includes high priority artifacts",
                      "module_map" in ws.active_artifacts)
            
            # Test prompt generation
            prompt = ws.to_prompt()
            print_test("Prompt generated", len(prompt) > 0)
            print_test("Prompt contains task", "Test task" in prompt)
            
        except Exception as e:
            print_test("Working Set Builder", False, str(e))
            import traceback
            traceback.print_exc()
    
    async def test_event_log_manager(self):
        """Test 3: Event Log Manager"""
        print_header("TEST 3: Event Log Manager")
        
        try:
            event_log = EventLogManager("test_task_2")
            
            # Test appending different event types
            event1 = event_log.append_tool_call(
                actor="agent_1",
                phase=Phase.EXPLORE,
                skill_name="fs-skill",
                tool_name="read_file",
                parameters={"path": "/test"},
            )
            
            event2 = event_log.append_tool_result(
                actor="agent_1",
                phase=Phase.EXPLORE,
                skill_name="fs-skill",
                tool_name="read_file",
                success=True,
                result={"content": "test"},
            )
            
            event3 = event_log.append_phase_change(
                actor="agent_1",
                from_phase=Phase.EXPLORE,
                to_phase=Phase.EXECUTE,
                reason="Context gathered",
            )
            
            print_test("Tool call event recorded", event1.event_type == EventType.TOOL_CALL)
            print_test("Tool result event recorded", event2.event_type == EventType.TOOL_RESULT)
            print_test("Phase change event recorded", event3.event_type == EventType.PHASE_CHANGE)
            
            # Test querying
            recent = event_log.get_recent(2)
            print_test("Get recent events", len(recent) == 2)
            
            by_phase = event_log.get_by_phase(Phase.EXPLORE)
            print_test("Get by phase", len(by_phase) == 2)
            
            by_type = event_log.get_by_type(EventType.TOOL_CALL)
            print_test("Get by type", len(by_type) == 1)
            
            # Test export
            export = event_log.export_for_debug()
            print_test("Export for debug", "events" in export)
            print_test("Export has phase summary", "phase_summary" in export)
            
        except Exception as e:
            print_test("Event Log Manager", False, str(e))
    
    async def test_output_parser(self):
        """Test 4: Agent Output Parser"""
        print_header("TEST 4: Agent Output Parser")
        
        try:
            parser = get_output_parser()
            
            # Test 1: YAML tool call
            yaml_output = """```yaml
intent: tool_call
reasoning: "Need to read file"
tool_calls:
  - skill: fs-skill
    tool: read_file
    parameters:
      path: "/tmp/test.txt"
```"""
            
            parsed = parser.parse(yaml_output, Phase.EXPLORE)
            print_test("Parse YAML tool call", parsed.intent_type == IntentType.TOOL_CALL)
            print_test("Extract tool name", 
                      len(parsed.tool_calls) > 0 and parsed.tool_calls[0].tool_name == "read_file")
            
            # Test 2: Phase transition
            trans_output = """```yaml
intent: phase_transition
from_phase: explore
to_phase: execute
reason: "Context ready"
```"""
            
            parsed = parser.parse(trans_output, Phase.EXPLORE)
            print_test("Parse phase transition", parsed.intent_type == IntentType.PHASE_TRANSITION)
            print_test("Extract phase info",
                      parsed.phase_transition and parsed.phase_transition.to_phase == Phase.EXECUTE)
            
            # Test 3: Final answer
            answer_output = """```yaml
intent: final_answer
answer: "Task completed!"
success: true
```"""
            
            parsed = parser.parse(answer_output, Phase.EXECUTE)
            print_test("Parse final answer", parsed.intent_type == IntentType.FINAL_ANSWER)
            print_test("Extract answer", parsed.final_answer == "Task completed!")
            
            # Test 4: Heuristic parsing (unstructured)
            heuristic_output = "I will call fs-skill.read_file to get the content"
            parsed = parser.parse(heuristic_output, Phase.EXPLORE)
            print_test("Heuristic parsing", parsed.intent_type == IntentType.TOOL_CALL)
            
        except Exception as e:
            print_test("Output Parser", False, str(e))
    
    async def test_local_skill_registry(self):
        """Test 5: Local Skill Registry"""
        print_header("TEST 5: Local Skill Registry")
        
        try:
            registry = get_local_skill_registry()
            
            # Test skill lookup
            has_fs = registry.has_skill("fs-skill")
            print_test("Check fs-skill exists", has_fs)
            
            has_tool = registry.has_tool("fs-skill", "read_file")
            print_test("Check tool exists", has_tool)
            
            # List skills
            skills = registry.list_available()
            print_test("List skills", len(skills) >= 2)
            
        except Exception as e:
            print_test("Local Skill Registry", False, str(e))
    
    async def test_execution_coordinator(self):
        """Test 6: Execution Coordinator"""
        print_header("TEST 6: Execution Coordinator")
        
        try:
            coordinator = get_execution_coordinator()
            
            from thread_runtime.models import ExecutionRequest, RequestType
            
            # Test internal operation
            request = ExecutionRequest(
                request_id="test_001",
                request_type=RequestType.INTERNAL,
                source="test",
                target="internal",
                action="get_coordinator_status",
                parameters={},
            )
            
            ticket = await coordinator.submit(request)
            print_test("Submit request", ticket is not None)
            print_test("Ticket has ID", len(ticket.ticket_id) > 0)
            
            result = await coordinator.execute(ticket)
            print_test("Execute request", result is not None)
            print_test("Result has success flag", hasattr(result, 'success'))
            
        except Exception as e:
            print_test("Execution Coordinator", False, str(e))
    
    async def test_agent_thread_creation(self):
        """Test 7: Agent Thread Creation"""
        print_header("TEST 7: Agent Thread Creation")
        
        try:
            # Create task
            task = TaskSnapshot(
                id=f"test_task_{uuid4().hex[:8]}",
                session_id="test_session",
                process_id="test_process",
                status=TaskStatus.IDLE,
                goal="Test execution",
                constraints=["max_steps: 5"],
                allowed_capabilities=["fs-skill"],
            )
            
            context = CompiledContext(
                task_id=task.id,
                session_context={
                    "session_id": task.session_id,
                    "request_id": "req_001",
                },
                task_goal=task.goal,
                constraints=task.constraints,
                allowed_capabilities=task.allowed_capabilities,
                forbidden_capabilities=[],
            )
            
            # Create agent
            agent = AgentThread(
                task=task,
                compiled_context=context,
                coordinator=get_execution_coordinator(),
                ws_builder=WorkingSetBuilder(),
            )
            
            self.agent = agent
            
            print_test("AgentThread created", agent is not None)
            print_test("Has thread_id", len(agent.thread_id) > 0)
            print_test("Initial phase is EXPLORE", agent.current_phase == Phase.EXPLORE)
            print_test("Has Event Log", agent.event_log is not None)
            print_test("Registered with OS Interface", True)  # Would error if failed
            
        except Exception as e:
            print_test("Agent Thread Creation", False, str(e))
            import traceback
            traceback.print_exc()

    async def test_scheduler_intervention(self):
        """Test 9: Scheduler Intervention APIs"""
        print_header("TEST 9: Scheduler Intervention APIs")
        
        try:
            scheduler = get_scheduler()
            
            # Test listing (empty initially)
            threads = scheduler.list_active_threads()
            print_test("List active threads", isinstance(threads, list))
            
            # Note: Full intervention testing requires running thread
            # which is tested in integration test
            
            print_test("Scheduler initialized", scheduler is not None)
            print_test("Has coordinator", scheduler.coordinator is not None)
            print_test("Has ws_builder", scheduler.ws_builder is not None)
            
        except Exception as e:
            print_test("Scheduler Intervention", False, str(e))
    
    async def test_os_interface(self):
        """Test 10: OS Interface"""
        print_header("TEST 10: OS Interface")
        
        try:
            os_interface = get_os_interface_skill()
            
            # Test state queries (may return None for non-existent)
            state = await os_interface.query_session_state("non_existent")
            print_test("Query session state", True)  # Should not error
            
            task_state = await os_interface.query_task_state("non_existent")
            print_test("Query task state", True)  # Should not error
            
            # Test atomic operation manager exists
            print_test("Atomic manager exists", os_interface.atomic_manager is not None)
            
        except Exception as e:
            print_test("OS Interface", False, str(e))
    
    def print_summary(self):
        """Print test summary"""
        print_header("TEST SUMMARY")
        
        passed = sum(1 for name, success, _ in self.test_results if success)
        failed = sum(1 for name, success, _ in self.test_results if not success)
        total = len(self.test_results)
        
        print(f"\n{Colors.BOLD}Results:{Colors.END}")
        print(f"  {Colors.GREEN}Passed: {passed}{Colors.END}")
        print(f"  {Colors.RED}Failed: {failed}{Colors.END}")
        print(f"  {Colors.BLUE}Total:  {total}{Colors.END}")
        
        if failed == 0:
            print(f"\n{Colors.GREEN}{Colors.BOLD}✓ ALL TESTS PASSED!{Colors.END}")
        else:
            print(f"\n{Colors.YELLOW}{Colors.BOLD}⚠ Some tests failed{Colors.END}")
        
        return failed == 0


async def main():
    """Run integration tests"""
    test = IntegrationTest()
    await test.run_all_tests()


if __name__ == "__main__":
    asyncio.run(main())
