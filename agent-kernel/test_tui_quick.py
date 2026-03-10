#!/usr/bin/env python3
"""Quick connectivity test for TUI client."""
import asyncio
import sys

sys.path.insert(0, '/home/eziothean/ProClaw/agent-kernel/apps/gateway/clients/tui')

from proclaw_tui.client.gateway_client import GatewayClient
from proclaw_tui.client.events import ConnectionState

async def test_connection():
    """Test basic connection to Gateway."""
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
        print(f"   ⏰ Time: {health.timestamp}")
    else:
        print("   ❌ Gateway health check failed")
        return False
    
    # Test 2: Connection status
    print("\n2️⃣  Checking connection status...")
    status = client.connection_status
    print(f"   📡 State: {status.state.value}")
    print(f"   🔄 Reconnects: {status.reconnect_attempts}")
    print(f"   ❌ Last Error: {status.last_error or 'None'}")
    
    # Test 3: System status
    print("\n3️⃣  Getting system status...")
    sys_status = await client.get_system_status()
    print(f"   🔌 Connected: {sys_status['connected']}")
    print(f"   📡 Connection State: {sys_status['connection_state']}")
    if sys_status['health']:
        print(f"   🏥 Gateway: {sys_status['health']['gateway']}")
        print(f"   💾 Storage: {sys_status['health']['storage']}")
    
    print("\n✅ All connectivity tests passed!")
    print("\n💡 TUI client is ready to use.")
    print("   Run: openclaw")
    print("   Or:  cd agent-kernel/apps/gateway/clients/tui && python -m openclaw_tui.main")
    
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
