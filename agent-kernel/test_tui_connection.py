#!/usr/bin/env python3
"""Quick test script for TUI client connection."""
import asyncio
import sys

sys.path.insert(0, '/home/eziothean/ProClaw/agent-kernel/apps/gateway/clients/tui')

from openclaw_tui.client.gateway_client import GatewayClient
from openclaw_tui.client.events import ConnectionState

async def test_connection():
    """Test connection to Gateway."""
    print("🧪 Testing OpenClaw TUI Client Connection")
    print("=" * 50)
    
    client = GatewayClient(base_url="http://localhost:3000")
    
    # Test 1: Health check
    print("\n1️⃣  Testing Gateway health...")
    health = await client.check_health()
    if health:
        print(f"   ✅ Gateway is healthy (v{health.version})")
        print(f"   📊 Status: {health.status}")
        print(f"   💾 Storage: {health.storage}")
    else:
        print("   ❌ Gateway health check failed")
        return False
    
    # Test 2: Connection status
    print("\n2️⃣  Checking connection status...")
    status = client.connection_status
    print(f"   📡 State: {status.state.value}")
    print(f"   🔄 Reconnects: {status.reconnect_attempts}")
    
    # Test 3: System status
    print("\n3️⃣  Getting system status...")
    sys_status = await client.get_system_status()
    print(f"   🔌 Connected: {sys_status['connected']}")
    print(f"   🏥 Health: {sys_status['health']['status'] if sys_status['health'] else 'N/A'}")
    
    # Test 4: Send a test message (mock mode)
    print("\n4️⃣  Testing message flow (mock)...")
    print("   📤 Sending: 'Hello, Agent Kernel!'")
    
    message_count = 0
    async for event in client.send_message("Hello, Agent Kernel!"):
        message_count += 1
        print(f"   📥 Event #{message_count}: {event.type.value}")
        
        if event.type.value == "accepted":
            print(f"      ✅ Request ID: {event.request_id}")
            print(f"      📁 Session ID: {event.session_id}")
        elif event.type.value == "status":
            print(f"      🔄 Status: {event.status.value if event.status else 'N/A'}")
        elif event.type.value == "complete":
            print(f"      ✅ Completed!")
            break
        elif event.type.value == "error":
            print(f"      ❌ Error: {event.error}")
            break
        
        # Limit output for demo
        if message_count >= 10:
            print("   ⏹️  Stopping after 10 events...")
            break
    
    print(f"\n✅ Test completed! Received {message_count} events.")
    
    await client.close()
    return True

if __name__ == "__main__":
    try:
        success = asyncio.run(test_connection())
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted")
        sys.exit(130)
    except Exception as e:
        print(f"\n\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
