"""Test TUI event parsing"""
import json
from datetime import datetime
from proclaw_tui.client.events import ChatStreamEvent, EventType

# Test data from curl output
test_data = {
    "type": "accepted",
    "timestamp": "2026-03-10T17:55:04.415Z",
    "requestId": "7c0640e0-74d6-476c-a0fc-8ba5dad4e073",
    "sessionId": "sess_1773165304412_k52msx2ae",
    "message": "Request accepted and queued for processing"
}

try:
    event = ChatStreamEvent.model_validate(test_data)
    print(f"✓ ACCEPTED event parsed successfully")
    print(f"  type: {event.type}")
    print(f"  request_id: {event.request_id}")
    print(f"  session_id: {event.session_id}")
except Exception as e:
    print(f"✗ Failed to parse ACCEPTED event: {e}")

# Test COMPLETE event
complete_data = {
    "type": "complete",
    "timestamp": "2026-03-10T17:55:33.369Z",
    "requestId": "7c0640e0-74d6-476c-a0fc-8ba5dad4e073",
    "sessionId": "sess_1773165304412_k52msx2ae",
    "response": {
        "header": {
            "requestId": "7c0640e0-74d6-476c-a0fc-8ba5dad4e073",
            "sessionId": "sess_1773165304412_k52msx2ae",
            "timestamp": "2026-03-10T17:55:33.367044",
            "processingTimeMs": 28913
        },
        "status": "completed",
        "body": "你好！很高兴见到你。有什么我可以帮助你的吗？",
        "metadata": {"actions": []}
    }
}

try:
    event = ChatStreamEvent.model_validate(complete_data)
    print(f"\n✓ COMPLETE event parsed successfully")
    print(f"  type: {event.type}")
    print(f"  request_id: {event.request_id}")
    print(f"  response.body: {event.response.get('body') if event.response else 'N/A'}")
except Exception as e:
    print(f"\n✗ Failed to parse COMPLETE event: {e}")

# Test with chat_view
print("\n--- Testing ChatView.handle_event ---")
from proclaw_tui.components.chat_view import ChatView

class MockChatView:
    def __init__(self):
        self.messages = []
        self._current_assistant_message = None
        
    def start_assistant_message(self):
        print("  → start_assistant_message() called")
        
    def complete_assistant_message(self, content):
        print(f"  → complete_assistant_message('{content[:30]}...') called")
        
    def handle_event(self, event):
        print(f"  Handling event: {event.type}")
        if event.type == EventType.ACCEPTED:
            self.start_assistant_message()
        elif event.type == EventType.COMPLETE:
            if event.response and "body" in event.response:
                body = event.response["body"]
                if isinstance(body, dict) and "response" in body:
                    content = body["response"]
                else:
                    content = str(body)
                self.complete_assistant_message(content)
            else:
                self.complete_assistant_message("(No response content)")

mock = MockChatView()
accepted_event = ChatStreamEvent.model_validate(test_data)
complete_event = ChatStreamEvent.model_validate(complete_data)

print("\nSending ACCEPTED event:")
mock.handle_event(accepted_event)

print("\nSending COMPLETE event:")
mock.handle_event(complete_event)

print("\n✓ All tests passed!")
