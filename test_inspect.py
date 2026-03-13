#!/usr/bin/env python3
"""
Test Prime Personality with raw LLM response inspection
"""
import sys
sys.path.insert(0, '/tmp')

import grpc
import prime_personality_pb2
import prime_personality_pb2_grpc
import json

def test_with_raw_response():
    print("=" * 70)
    print("Testing Prime Personality - Inspect Raw LLM Response")
    print("=" * 70)
    
    channel = grpc.insecure_channel('localhost:50051')
    stub = prime_personality_pb2_grpc.PrimePersonalityStub(channel)
    
    request = prime_personality_pb2.ProcessRequestRequest(
        input_message=prime_personality_pb2.InputMessage(
            header=prime_personality_pb2.InputHeader(
                timestamp="2026-03-13T12:00:00Z",
                platform="test",
                device_id="test-device",
                user_id="test-user",
                session_id="test-session-001",
                request_id="test-raw-001",
                priority=1
            ),
            body="你好"
        )
    )
    
    print("\n📤 Sending: '你好'")
    print("-" * 70)
    
    try:
        response = stub.ProcessRequest(request, timeout=30)
        
        print("\n✅ RESPONSE RECEIVED")
        print("=" * 70)
        
        ir = response.ir
        
        # Extract the actual text from nested content
        content_text = ir.content.text if ir.content.text else "EMPTY"
        
        print(f"\n📝 Content.text from proto:")
        print(f"  {content_text[:200]}..." if len(content_text) > 200 else f"  {content_text}")
        
        # Try to parse it as JSON to see structure
        print(f"\n🔍 Analysis:")
        try:
            parsed = json.loads(content_text)
            if isinstance(parsed, dict):
                print(f"  Content.text is valid JSON (dict)")
                if "content" in parsed and isinstance(parsed["content"], dict):
                    inner_text = parsed["content"].get("text", "NOT FOUND")
                    print(f"  ✓ Found nested content.text: {inner_text}")
                elif "text" in parsed:
                    print(f"  ✓ Found direct text: {parsed['text']}")
                else:
                    print(f"  ⚠️ JSON keys: {list(parsed.keys())}")
            else:
                print(f"  Content.text is JSON but not dict: {type(parsed)}")
        except json.JSONDecodeError:
            print(f"  ✓ Content.text is plain text (not JSON)")
        
        print("\n" + "=" * 70)
        print("EXPECTED: Content.text should be '你好！很高兴见到你...'")
        print("=" * 70)
        
    except grpc.RpcError as e:
        print(f"\n❌ RPC Error: {e.code()}: {e.details()}")
        return 1
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(test_with_raw_response())
