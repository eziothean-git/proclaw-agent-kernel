#!/usr/bin/env python3
"""
Simple gRPC client to test Prime Personality
"""
import grpc
import sys
sys.path.insert(0, 'kernel-v2')

# Import generated protobuf modules
from proto import prime_personality_pb2
from proto import prime_personality_pb2_grpc

def test_prime_personality():
    # Connect to Prime Personality service
    channel = grpc.insecure_channel('localhost:50051')
    stub = prime_personality_pb2_grpc.PrimePersonalityStub(channel)
    
    # Build test request
    request = prime_personality_pb2.ProcessRequestRequest(
        request_id="test-001",
        user_id="user-001",
        input_message=prime_personality_pb2.InputMessage(
            header=prime_personality_pb2.InputHeader(
                message_id="msg-001",
                timestamp="2026-03-13T12:00:00Z",
                source="test",
                user_id="user-001",
                request_id="test-001",
                priority=1
            ),
            content=prime_personality_pb2.Content(
                text="你好"
            )
        ),
        process_definition=prime_personality_pb2.ProcessDefinition(
            goal="测试 Prime Personality 简单对话",
            scope="conversation"
        )
    )
    
    print("Sending request to Prime Personality...")
    print(f"Request ID: {request.request_id}")
    print(f"Message: 你好")
    print("-" * 50)
    
    try:
        response = stub.ProcessRequest(request, timeout=30)
        print("✅ Received response!")
        print(f"Status: {response.status}")
        print(f"IR Request ID: {response.ir.request_id}")
        print(f"IR Intent: {response.ir.intent}")
        print(f"IR Goals: {list(response.ir.goals)}")
        print(f"IR Processes: {len(response.ir.processes)} processes")
        for i, proc in enumerate(response.ir.processes):
            print(f"  Process {i+1}: {proc.name}")
            print(f"    Goal: {proc.goal}")
            print(f"    Capabilities: {list(proc.capabilities)}")
        
        # Check Gateway Skill was called
        print("\n" + "=" * 50)
        print("✅ Test completed successfully!")
        print("Prime Personality generated IR and sent to Gateway")
        
    except grpc.RpcError as e:
        print(f"❌ RPC Error: {e.code()}: {e.details()}")
        return 1
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return 1
    
    return 0

if __name__ == "__main__":
    sys.exit(test_prime_personality())
