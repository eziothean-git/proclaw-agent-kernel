#!/usr/bin/env python3
"""
基础遥测测试 - 只发送"你好"
"""
import asyncio
import json
import aiohttp
import sys

async def test_basic_telemetry():
    """测试基础遥测流"""
    gateway_url = "http://localhost:3000"
    
    print("🧪 基础遥测测试 - 发送'你好'")
    print("=" * 60)
    
    # 1. 发送简单请求
    print("\n1. 发送请求: '你好'")
    request_body = {
        "message": "你好",
        "user_id": "test-user",
        "metadata": {
            "telemetry_config": {
                "level": "detailed",
                "include": {
                    "working_set": False,  # 不显示，但会发送
                    "skill_calls": True,
                    "agent_output": True,
                    "reasoning": True,
                    "performance": True
                }
            }
        }
    }
    
    async with aiohttp.ClientSession() as session:
        # 发送请求
        async with session.post(
            f"{gateway_url}/api/v1/chat",
            json=request_body
        ) as resp:
            if resp.status not in (201, 202):
                print(f"❌ 请求失败: {resp.status}")
                text = await resp.text()
                print(f"错误: {text}")
                return
            
            result = await resp.json()
            request_id = result.get("requestId")
            print(f"✅ 请求已接受: {request_id}")
        
        # 2. 连接遥测流
        print(f"\n2. 连接遥测流...")
        print(f"   等待遥测事件 (最多10秒)...\n")
        
        telemetry_count = 0
        events_by_layer = {}
        
        try:
            async with session.get(
                f"{gateway_url}/api/v1/telemetry/stream?request_id={request_id}",
                headers={"Accept": "text/event-stream"},
                timeout=aiohttp.ClientTimeout(total=12)
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
                            
                            # 提取关键信息
                            data = event.get("data", {})
                            layer = data.get("layer", 0)
                            layer_name = data.get("layer_name", "Unknown")
                            component = data.get("component", "Unknown")
                            operation = data.get("operation", "Unknown")
                            status = data.get("status", "Unknown")
                            
                            # 按 layer 统计
                            if layer_name not in events_by_layer:
                                events_by_layer[layer_name] = 0
                            events_by_layer[layer_name] += 1
                            
                            # 显示事件
                            print(f"[{telemetry_count:2d}] L{layer} {layer_name:15s} | {component:15s} | {operation:20s} | {status}")
                            
                            # 显示 payload 中的关键信息
                            payload = data.get("payload", {})
                            if "thought" in payload:
                                thought = payload["thought"]
                                print(f"      💭 {thought.get('reasoning', '')[:60]}...")
                            
                            if "wrote" in payload:
                                wrote = payload["wrote"]
                                print(f"      ✍️  [{wrote.get('output_type', '')}] {wrote.get('content', '')[:40]}...")
                            
                            # 如果有 sub_threads 显示进度
                            sub_threads = data.get("sub_threads", [])
                            if sub_threads:
                                for st in sub_threads:
                                    print(f"      📎 Thread {st.get('thread_id', 'N/A')[:8]}: {st.get('status', 'unknown')} ({st.get('progress_pct', 0)}%)")
                            
                            # 成功完成就退出
                            if status == "complete" and operation in ["execution", "session_orchestration"]:
                                print(f"\n✅ 检测到完成事件，结束监听")
                                break
                                
                        except json.JSONDecodeError as e:
                            print(f"   ⚠️ JSON解析错误: {e}")
                            continue
                            
        except asyncio.TimeoutError:
            print(f"\n⏰ 超时结束")
        except Exception as e:
            print(f"\n❌ 遥测流错误: {e}")
        
        print("-" * 60)
        print(f"\n📈 统计:")
        print(f"   总事件数: {telemetry_count}")
        print(f"   按层级分布:")
        for layer_name, count in sorted(events_by_layer.items()):
            print(f"      - {layer_name}: {count} 个事件")
        
        # 3. 检查最终结果
        print(f"\n3. 检查请求状态...")
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
    try:
        asyncio.run(test_basic_telemetry())
    except KeyboardInterrupt:
        print("\n\n👋 测试已中断")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
