"""Test TUI client SSE connection"""
import asyncio
import aiohttp
from datetime import datetime
import sys
sys.path.insert(0, '/home/eziothean/ProClaw/agent-kernel/apps/gateway/clients/tui')

from proclaw_tui.client.events import ChatStreamEvent, EventType

async def test_sse_connection():
    """Test actual SSE connection like TUI does"""
    url = "http://localhost:3000/api/v1/chat/stream"
    params = {
        "message": "你好",
        "user_id": "test_tui",
        "platform": "test"
    }
    
    print("Connecting to SSE stream...")
    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as response:
            print(f"Connected! Status: {response.status}")
            print("Reading events...\n")
            
            event_count = 0
            async for line in response.content:
                line_str = line.decode("utf-8").strip()
                print(f"Raw line: {repr(line_str)}")
                
                if not line_str:
                    continue
                
                if line_str.startswith("data: "):
                    data_str = line_str[6:]  # Remove "data: " prefix
                    print(f"Data content: {data_str[:100]}...")
                    
                    try:
                        import json
                        data = json.loads(data_str)
                        event = ChatStreamEvent.model_validate(data)
                        event_count += 1
                        print(f"\n✓ Event {event_count} parsed: {event.type}")
                        print(f"  Request ID: {event.request_id}")
                        if event.type == EventType.COMPLETE and event.response:
                            body = event.response.get("body", "N/A")
                            print(f"  Response: {body[:50]}...")
                        
                        if event.type in (EventType.COMPLETE, EventType.ERROR):
                            print("\n✓ Stream complete!")
                            break
                            
                    except json.JSONDecodeError as e:
                        print(f"✗ JSON decode error: {e}")
                    except Exception as e:
                        print(f"✗ Validation error: {e}")
                        import traceback
                        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_sse_connection())
