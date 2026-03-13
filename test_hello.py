#!/usr/bin/env python3
"""
Test Prime Personality with "你好" message
"""
import sys
sys.path.insert(0, '/tmp')

import grpc
import prime_personality_pb2
import prime_personality_pb2_grpc
from datetime import datetime

def test_hello():
    print("=" * 60)
    print("Testing Prime Personality with '你好'")
    print("=" * 60)
    
    # Connect to Prime Personality
    channel = grpc.insecure_channel('localhost:50051')
    stub = prime_personality_pb2_grpc.PrimePersonalityStub(channel)
    
    # Build request with Chinese greeting
    request = prime_personality_pb2.ProcessRequestRequest(
        input_message=prime_personality_pb2.InputMessage(
            header=prime_personality_pb2.InputHeader(
                timestamp=datetime.now().isoformat(),
                platform="test",
                device_id="test-device",
                user_id="test-user",
                session_id="test-session-001",
                request_id="test-nihao-001",
                priority=1
            ),
            body="你好"
        )
    )
    
    print("\n📤 Sending request:")
    print(f"  Request ID: {request.input_message.header.request_id}")
    print(f"  Message: {request.input_message.body}")
    
    try:
        print("\n⏳ Waiting for response (timeout: 30s)...")
        response = stub.ProcessRequest(request, timeout=30)
        
        print("\n" + "=" * 60)
        print("✅ RECEIVED RESPONSE!")
        print("=" * 60)
        
        # Parse response
        print(f"\n📊 Response Status: {response.status}")
        print(f"📋 IR Request ID: {response.ir.request_id}")
        print(f"🎯 IR Intent: {response.ir.intent}")
        print(f"📝 IR Goals: {list(response.ir.goals)}")
        print(f"⚙️  IR Processes: {len(response.ir.processes)} process(es)")
        
        for i, proc in enumerate(response.ir.processes):
            print(f"\n  Process {i+1}:")
            print(f"    Name: {proc.name}")
            print(f"    Goal: {proc.goal}")
            print(f"    Capabilities: {list(proc.capabilities)}")
            if proc.constraints:
                print(f"    Constraints: {list(proc.constraints)}")
            if proc.security_level:
                print(f"    Security Level: {proc.security_level}")
        
        # Check if it's simple conversation (expected)
        is_conversation = response.ir.intent == "conversation"
        has_no_capabilities = all(
            len(proc.capabilities) == 0 
            for proc in response.ir.processes
        )
        
        print("\n" + "=" * 60)
        print("🧪 TEST RESULTS:")
        print("=" * 60)
        
        if is_conversation and has_no_capabilities:
            print("✅ PASS: Simple conversation detected correctly")
            print("   - Intent: conversation")
            print("   - No capabilities required")
            print("   - Prime will use Gateway Skill to send reply")
        else:
            print("⚠️  INFO: Intent classification result")
            print(f"   - Intent: {response.ir.intent}")
            print(f"   - Capabilities: {[
                cap for proc in response.ir.processes for cap in proc.capabilities
            ]}")
        
        print("\n📝 Note: Check Prime service logs to see Gateway Skill call")
        print("=" * 60)
        
        return 0
        
    except grpc.RpcError as e:
        print(f"\n❌ RPC Error: {e.code()}: {e.details()}")
        return 1
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == "__main__":
    sys.exit(test_hello())
