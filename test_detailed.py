#!/usr/bin/env python3
"""
Test Prime Personality and print full IR
"""
import sys
sys.path.insert(0, '/tmp')

import grpc
import prime_personality_pb2
import prime_personality_pb2_grpc
import json

def test_detailed():
    print("=" * 70)
    print("Testing Prime Personality - Detailed IR Output")
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
                request_id="test-detailed-001",
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
        print(f"\n📋 IR Fields:")
        print(f"  request_id: {ir.request_id}")
        print(f"  intent: {ir.intent}")
        print(f"  goals: {list(ir.goals)}")
        print(f"  processes: {len(ir.processes)} process(es)")
        
        # Print content details
        if ir.content.text:
            print(f"\n📝 Content Text:")
            print(f"  {ir.content.text}")
        else:
            print(f"\n⚠️  Content Text: EMPTY")
        
        if ir.content.attachments:
            print(f"\n📎 Attachments: {len(ir.content.attachments)}")
            for att in ir.content.attachments:
                print(f"    - {att.name} ({att.mime_type})")
        else:
            print(f"\n📎 Attachments: None")
        
        if ir.content.references:
            print(f"\n🔗 References: {len(ir.content.references)}")
        else:
            print(f"\n🔗 References: None")
        
        # Print raw JSON
        print(f"\n" + "=" * 70)
        print("📄 RAW IR (as dict):")
        print("=" * 70)
        
        ir_dict = {
            "request_id": ir.request_id,
            "intent": ir.intent,
            "goals": list(ir.goals),
            "processes": [
                {
                    "name": p.name,
                    "goal": p.goal,
                    "capabilities": list(p.capabilities),
                    "constraints": list(p.constraints),
                    "security_level": p.security_level,
                }
                for p in ir.processes
            ],
            "content": {
                "text": ir.content.text if ir.content.text else None,
                "attachments": [
                    {
                        "id": a.id,
                        "name": a.name,
                        "mime_type": a.mime_type,
                    }
                    for a in ir.content.attachments
                ] if ir.content.attachments else [],
            } if ir.content else None,
        }
        print(json.dumps(ir_dict, indent=2, ensure_ascii=False))
        
        print("\n" + "=" * 70)
        if ir.content.text:
            print("✅ SUCCESS: IR contains content.text")
        else:
            print("❌ FAILED: IR content.text is empty")
            print("   LLM did not generate the response text!")
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
    sys.exit(test_detailed())
