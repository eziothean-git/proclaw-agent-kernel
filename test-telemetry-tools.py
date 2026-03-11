#!/usr/bin/env python3
"""
遥测测试 - 发送需要工具调用的任务
"""
import asyncio
import json
import aiohttp

async def test_telemetry_with_tools():
    """测试需要工具调用的遥测流"""
    gateway_url = "http://localhost:3000"
    
    print("🧪 遥测测试 - 发送需要工具调用的任务")
    print("=" * 60)
    
    # 发送需要文件操作的请求
    print("\n1. 发送请求: '列出当前目录的文件'")
    request_body = {
        "message": "列出当前目录的文件",
        "user_id": "test-user",
        "metadata": {
            "telemetry_config": {
                "level": "detailed",
                "include": {
                    "working_set": False,
                    "skill_calls": True,
                    "agent_output": True,
                    "reasoning": True,
                    "performance": True
                }
            }
        }
    }
    
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{gateway_url}/api/v1/chat",
            json=request_body
        ) as resp:
            if resp.status not in (201, 202):
                print(f"❌ 请求失败: {resp.status}")
                return
            
            result = await resp.json()
            request_id = result.get("requestId")
            print(f"✅ 请求已接受: {request_id}")
        
        print(f"\n2. 连接遥测流...")
        print(f"   等待遥测事件 (最多60秒)...\n")
        
        telemetry_count = 0
        events_by_layer = {}
        
        try:
            async with session.get(
                f"{gateway_url}/api/v1/telemetry/stream?request_id={request_id}",
                headers={"Accept": "text/event-stream"},
                timeout=aiohttp.ClientTimeout(total=62)
            ) as stream:
                print("📊 收到的遥测事件:")
                print("-" * 60)
                
                async for line in stream.content:
                    line = line.decode().strip()
                    if not line or line.startswith(":"):
                        continue
                    
                    if line.startswith("data: "):
                        try:
                            event = json.loads(line[6:])
                            telemetry_count += 1
                            
                            data = event.get("data", {})
                            layer = data.get("layer", 0)
                            layer_name = data.get("layer_name", "Unknown")
                            component = data.get("component", "Unknown")
                            operation = data.get("operation", "Unknown")
                            status = data.get("status", "Unknown")
                            
                            if layer_name not in events_by_layer:
                                events_by_layer[layer_name] = 0
                            events_by_layer[layer_name] += 1
                            
                            print(f"[{telemetry_count:2d}] L{layer} {layer_name:15s} | {component:15s} | {operation:20s} | {status}")
                            
                            payload = data.get("payload", {})
                            if "thought" in payload:
                                thought = payload["thought"]
                                reasoning = thought.get('reasoning', '')
                                if reasoning:
                                    print(f"      💭 {reasoning[:60]}...")
                            
                            if "wrote" in payload:
                                wrote = payload["wrote"]
                                print(f"      ✍️  [{wrote.get('output_type', '')}] {wrote.get('content', '')[:40]}...")
                            
                            if "did" in payload:
                                did = payload["did"]
                                print(f"      🔧 调用: {did.get('skill_name', '')}.{did.get('tool_name', '')}")
                            
                            sub_threads = data.get("sub_threads", [])
                            if sub_threads:
                                for st in sub_threads:
                                    print(f"      📎 Thread {st.get('thread_id', 'N/A')[:8]}: {st.get('status', 'unknown')} ({st.get('progress_pct', 0)}%)")
                            
                            if status == "complete" and operation in ["execution", "session_orchestration", "request_completed"]:
                                print(f"\n✅ 检测到完成事件，结束监听")
                                break
                                
                        except json.JSONDecodeError:
                            continue
                            
        except asyncio.TimeoutError:
            print(f"\n⏰ 超时结束")
        except Exception as e:
            print(f"\n❌ 遥测流错误: {e}")
        
        print("-" * 60)
        print(f"\n📈 统计:")
        print(f"   总事件数: {telemetry_count}")
        print(f"   按层级分布:")
        for layer_name, count in sorted(events_by_layer.items(), key=lambda x: x[0]):
            print(f"      - {layer_name}: {count} 个事件")
        
        print(f"\n3. 检查最终结果...")
        await asyncio.sleep(0.5)
        
        try:
            async with session.get(
                f"{gateway_url}/api/v1/requests/{request_id}/status",
                timeout=aiohttp.ClientTimeout(total=5)
            ) as resp:
                if resp.status == 200:
                    status_data = await resp.json()
                    print(f"   最终状态: {status_data.get('status', 'Unknown')}")
                else:
                    print(f"   状态查询返回: {resp.status}")
        except Exception as e:
            print(f"   无法获取状态: {e}")

if __name__ == "__main__":
    asyncio.run(test_telemetry_with_tools())
