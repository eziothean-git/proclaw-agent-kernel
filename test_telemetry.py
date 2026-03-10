"""
Test script for telemetry data flow.
Tests the Python Kernel SSE endpoint without requiring full services.
"""
import asyncio
import sys
import time

sys.path.insert(0, '/home/eziothean/ProClaw/agent-kernel/apps/python-kernel')

from telemetry import TelemetryManager, TelemetryEvent, emit_telemetry


async def test_telemetry_stream():
    """Test telemetry streaming."""
    print("=== Telemetry Stream Test ===\n")
    
    manager = TelemetryManager()
    
    # Create test events
    events = [
        TelemetryEvent(
            request_id='test-req-001',
            layer=6,
            layer_name='Agent Thread',
            component='AgentThread',
            operation='execution',
            status='start',
            message='Starting execution: Test task',
            session_id='test-sess-001',
            phase='explore',
            step=0,
            total_steps=5,
        ),
        TelemetryEvent(
            request_id='test-req-001',
            layer=6,
            layer_name='Agent Thread',
            component='AgentThread',
            operation='step',
            status='progress',
            message='Step 1/5 - Phase: explore',
            session_id='test-sess-001',
            phase='explore',
            step=1,
            total_steps=5,
            progress_pct=20,
        ),
        TelemetryEvent(
            request_id='test-req-001',
            layer=6,
            layer_name='Agent Thread',
            component='AgentThread',
            operation='tool_call',
            status='progress',
            message='Calling fs-skill.list_files',
            session_id='test-sess-001',
            phase='explore',
            step=1,
            total_steps=5,
            details={'skill_name': 'fs-skill', 'tool_name': 'list_files'},
        ),
        TelemetryEvent(
            request_id='test-req-001',
            layer=6,
            layer_name='Agent Thread',
            component='AgentThread',
            operation='tool_result',
            status='progress',
            message='✓ fs-skill.list_files',
            session_id='test-sess-001',
            phase='explore',
            step=1,
            total_steps=5,
            elapsed_ms=150,
            details={'skill_name': 'fs-skill', 'tool_name': 'list_files', 'success': True},
        ),
        TelemetryEvent(
            request_id='test-req-001',
            layer=6,
            layer_name='Agent Thread',
            component='AgentThread',
            operation='execution',
            status='complete',
            message='Task completed successfully',
            session_id='test-sess-001',
            phase='complete',
            step=5,
            total_steps=5,
        ),
    ]
    
    # Test subscriber
    subscriber_count = [0]
    
    async def subscriber():
        queue = manager.subscribe()
        print(f"✓ Subscribed to telemetry stream\n")
        
        received = 0
        while received < len(events):
            try:
                event = await asyncio.wait_for(queue.get(), timeout=5.0)
                received += 1
                print(f"[{received}/{len(events)}] {event.layer_name} - {event.operation} - {event.status}")
                print(f"  Message: {event.message}")
                if event.step is not None:
                    print(f"  Step: {event.step}/{event.total_steps}")
                if event.progress_pct is not None:
                    print(f"  Progress: {event.progress_pct}%")
                print()
            except asyncio.TimeoutError:
                print("❌ Timeout waiting for event")
                break
        
        subscriber_count[0] = received
        manager.unsubscribe(queue)
        print(f"✓ Subscriber finished, received {received} events")
    
    # Start subscriber
    subscriber_task = asyncio.create_task(subscriber())
    
    # Wait a bit for subscriber to start
    await asyncio.sleep(0.1)
    
    # Emit events with delays to simulate real execution
    print("Emitting events...\n")
    for event in events:
        await manager.emit(event)
        await asyncio.sleep(0.1)  # Small delay between events
    
    # Wait for subscriber to finish
    await subscriber_task
    
    # Verify
    stored_events = manager.get_request_events('test-req-001')
    print(f"\n=== Test Results ===")
    print(f"✓ Events emitted: {len(events)}")
    print(f"✓ Events received: {subscriber_count[0]}")
    print(f"✓ Events stored: {len(stored_events)}")
    
    if subscriber_count[0] == len(events) == len(stored_events):
        print("\n✅ All tests passed!")
        return True
    else:
        print("\n❌ Test failed - event count mismatch")
        return False


if __name__ == "__main__":
    success = asyncio.run(test_telemetry_stream())
    sys.exit(0 if success else 1)
