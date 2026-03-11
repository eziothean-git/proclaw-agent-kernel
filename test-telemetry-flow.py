#!/usr/bin/env python3
"""
测试遥测数据流

使用方式:
1. 启动所有服务: ./launcher.sh
2. 运行此脚本: python3 test-telemetry-flow.py
"""
import asyncio
import json
import sys
import time
from datetime import datetime

import aiohttp


async def test_telemetry_flow():
    """测试完整的遥测数据流"""
    gateway_url = "http://localhost:3000"
    
    print("🧪 测试遥测数据流")
    print("=" * 50)
    
    # 1. 发送请求到 Gateway
    print("\n1. 发送请求到 Gateway...")
    request_body = {
        "message": "Hello, test telemetry flow!",
        "user_id": "test-user",
        "session_id": f"test-session-{int(time.time())}",
        "metadata": {
            "telemetry_config": {
                "level": "detailed",
                "components": ["prime", "session_host", "agent_thread"],
                "include": {
                    "working_set": True,
                    "skill_calls": True,
                    "agent_output": True,
                    "reasoning": False,
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
            if resp.status != 202:
                print(f"❌ 请求失败: {resp.status}")
                return
            
            result = await resp.json()
            request_id = result.get("requestId")
            print(f"✅ 请求已接受: {request_id}")
        
        # 2. 连接遥测流
        print("\n2. 连接遥测流...")
        print(f"   URL: {gateway_url}/api/v1/telemetry/stream?request_id={request_id}")
        
        telemetry_count = 0
        start_time = time.time()
        
        try:
            async with session.get(
                f"{gateway_url}/api/v1/telemetry/stream?request_id={request_id}",
                headers={"Accept": "text/event-stream"}
            ) as stream:
                print("✅ 已连接到遥测流\n")
                print("📊 遥测事件:")
                print("-" * 50)
                
                async for line in stream.content:
                    line = line.decode().strip()
                    if not line or line.startswith(":"):
                        continue
                    
                    if line.startswith("data: "):
                        data_str = line[6:]  # Remove "data: " prefix
                        try:
                            event = json.loads(data_str)
                            telemetry_count += 1
                            
                            # 打印关键信息
                            event_data = event.get("data", {})
                            layer = event_data.get("layer_name", "Unknown")
                            component = event_data.get("component", "Unknown")
                            operation = event_data.get("operation", "Unknown")
                            status = event_data.get("status", "Unknown")
                            
                            print(f"[{telemetry_count:3d}] {layer:15s} | {component:15s} | {operation:20s} | {status}")
                            
                            # 检查 payload
                            payload = event_data.get("payload")
                            if payload:
                                if "saw" in payload:
                                    print(f"      👁️  Agent 看到: {payload['saw'].get('working_set_summary', '')[:50]}...")
                                if "did" in payload:
                                    print(f"      🔧 Agent 执行: {payload['did'].get('skill_name', '')}")
                                if "wrote" in payload:
                                    print(f"      ✍️  Agent 输出: {payload['wrote'].get('output_type', '')}")
                            
                            # 检查 metrics
                            metrics = event_data.get("metrics")
                            if metrics:
                                print(f"      ⏱️  耗时: {metrics.get('elapsed_ms', 0)}ms")
                            
                            # 运行超过 10 秒就退出
                            if time.time() - start_time > 10:
                                print("\n⏰ 测试超时（10秒），退出")
                                break
                                
                        except json.JSONDecodeError:
                            print(f"   ⚠️ 无法解析: {data_str[:100]}")
                            
        except Exception as e:
            print(f"❌ 遥测流错误: {e}")
        
        print("-" * 50)
        print(f"\n📈 总计收到 {telemetry_count} 个遥测事件")
        print(f"⏱️  耗时: {time.time() - start_time:.2f} 秒")
        
        # 3. 检查结果
        print("\n3. 检查结果...")
        await asyncio.sleep(1)  # 等待结果
        
        async with session.get(
            f"{gateway_url}/api/v1/requests/{request_id}/status"
        ) as resp:
            if resp.status == 200:
                status = await resp.json()
                print(f"✅ 请求状态: {status.get('status', 'Unknown')}")
            else:
                print(f"⚠️ 无法获取状态: {resp.status}")


if __name__ == "__main__":
    try:
        asyncio.run(test_telemetry_flow())
    except KeyboardInterrupt:
        print("\n\n👋 测试已中断")
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
