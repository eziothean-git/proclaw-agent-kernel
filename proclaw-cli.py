#!/usr/bin/env python3
"""
ProClaw 临时测试 CLI
简单的命令行客户端，用于测试服务端流程
"""
import argparse
import asyncio
import json
import sys
from datetime import datetime
from typing import Optional

import aiohttp


class SimpleCLI:
    """简单的 ProClaw CLI 客户端"""
    
    def __init__(self, gateway_url: str = "http://localhost:3000"):
        self.gateway_url = gateway_url.rstrip("/")
        
    async def send_message(self, message: str, user_id: str = "cli-user") -> None:
        """发送消息并打印流式响应"""
        url = f"{self.gateway_url}/api/v1/chat/stream"
        params = {
            "message": message,
            "user_id": user_id,
            "platform": "cli"
        }
        
        print(f"\n{'='*60}")
        print(f"🚀 发送请求: {message}")
        print(f"{'='*60}\n")
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, params=params, timeout=aiohttp.ClientTimeout(total=300)) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        print(f"❌ HTTP错误 {response.status}: {error_text}")
                        return
                    
                    print(f"✅ 连接成功 (HTTP {response.status})")
                    print(f"⏳ 等待响应...\n")
                    print("-" * 60)
                    
                    request_id: Optional[str] = None
                    session_id: Optional[str] = None
                    
                    async for line in response.content:
                        line_str = line.decode("utf-8").strip()
                        
                        if not line_str:
                            continue
                        
                        # SSE 格式: data: {...}
                        if line_str.startswith("data: "):
                            data_str = line_str[6:]  # 移除 "data: " 前缀
                            
                            try:
                                event = json.loads(data_str)
                                event_type = event.get("type")
                                
                                if event_type == "accepted":
                                    request_id = event.get("requestId")
                                    session_id = event.get("sessionId")
                                    print(f"✅ [{self._timestamp()}] 请求已接受")
                                    print(f"   Request ID: {request_id}")
                                    print(f"   Session ID: {session_id}")
                                    print()
                                    
                                elif event_type == "complete":
                                    print(f"✅ [{self._timestamp()}] 请求完成")
                                    response_data = event.get("response", {})
                                    status = response_data.get("status")
                                    
                                    if status == "completed":
                                        body = response_data.get("body", "")
                                        processing_time = response_data.get("header", {}).get("processingTimeMs", 0)
                                        print(f"\n📝 回复内容:")
                                        print(f"{body}")
                                        print(f"\n⏱️  处理时间: {processing_time}ms")
                                    else:
                                        error = response_data.get("error", {})
                                        print(f"\n❌ 请求失败:")
                                        print(f"   类别: {error.get('category', 'unknown')}")
                                        print(f"   代码: {error.get('code', 'N/A')}")
                                        print(f"   消息: {error.get('message', 'Unknown error')}")
                                    
                                    print("-" * 60)
                                    return
                                    
                                elif event_type == "error":
                                    print(f"❌ [{self._timestamp()}] 错误:")
                                    print(f"   {event.get('error', 'Unknown error')}")
                                    print("-" * 60)
                                    return
                                    
                            except json.JSONDecodeError as e:
                                print(f"⚠️  JSON解析错误: {e}")
                                print(f"   原始数据: {data_str[:100]}")
                                
        except asyncio.TimeoutError:
            print(f"❌ 请求超时")
        except Exception as e:
            print(f"❌ 错误: {e}")
            import traceback
            traceback.print_exc()
    
    def _timestamp(self) -> str:
        """返回当前时间戳"""
        return datetime.now().strftime("%H:%M:%S")
    
    async def health_check(self) -> bool:
        """检查服务健康状态"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.gateway_url}/api/v1/health", timeout=5) as response:
                    if response.status == 200:
                        data = await response.json()
                        print(f"✅ Gateway 状态: {data.get('status', 'unknown')}")
                        print(f"   版本: {data.get('version', 'N/A')}")
                        print(f"   存储: {data.get('storage', 'N/A')}")
                        return True
                    else:
                        print(f"❌ Gateway 返回 HTTP {response.status}")
                        return False
        except Exception as e:
            print(f"❌ 无法连接到 Gateway: {e}")
            return False


async def interactive_mode(cli: SimpleCLI, user_id: str):
    """交互模式"""
    print("\n" + "="*60)
    print("🤖 ProClaw CLI - 交互模式")
    print("="*60)
    print("输入消息与AI对话，输入 'quit' 或 'exit' 退出\n")
    
    while True:
        try:
            message = input("You: ").strip()
            
            if not message:
                continue
                
            if message.lower() in ("quit", "exit", "q"):
                print("👋 再见!")
                break
                
            if message.lower() in ("health", "status"):
                await cli.health_check()
                continue
                
            await cli.send_message(message, user_id)
            
        except KeyboardInterrupt:
            print("\n👋 再见!")
            break
        except EOFError:
            break


async def main():
    parser = argparse.ArgumentParser(
        description="ProClaw 临时测试 CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s "你好"                    # 发送单条消息
  %(prog)s -i                        # 进入交互模式
  %(prog)s "测试" --user-id admin    # 指定用户ID
  %(prog)s --health                  # 检查服务健康状态
        """
    )
    
    parser.add_argument(
        "message",
        nargs="?",
        help="要发送的消息 (如果不提供则进入交互模式)"
    )
    
    parser.add_argument(
        "-i", "--interactive",
        action="store_true",
        help="进入交互模式"
    )
    
    parser.add_argument(
        "--url",
        default="http://localhost:3000",
        help="Gateway URL (默认: http://localhost:3000)"
    )
    
    parser.add_argument(
        "--user-id",
        default="cli-user",
        help="用户ID (默认: cli-user)"
    )
    
    parser.add_argument(
        "--health",
        action="store_true",
        help="检查服务健康状态"
    )
    
    args = parser.parse_args()
    
    cli = SimpleCLI(args.url)
    
    # 健康检查
    if args.health:
        healthy = await cli.health_check()
        sys.exit(0 if healthy else 1)
    
    # 交互模式
    if args.interactive or not args.message:
        await interactive_mode(cli, args.user_id)
    else:
        # 单条消息模式
        await cli.send_message(args.message, args.user_id)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 再见!")
        sys.exit(0)
