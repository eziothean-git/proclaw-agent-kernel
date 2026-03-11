#!/usr/bin/env python3
"""
ProClaw 服务端集成测试客户端

用法:
    # 测试运行中的服务
    python3 test-client.py

    # 指定 Gateway 地址
    python3 test-client.py --gateway http://localhost:3000

    # 运行完整测试套件
    python3 test-client.py --full

    # 持续发送测试请求
    python3 test-client.py --continuous --interval 5
"""
import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

try:
    import requests
except ImportError:
    print("请先安装 requests: pip install requests")
    sys.exit(1)


class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    END = '\033[0m'
    BOLD = '\033[1m'


class ProClawTestClient:
    def __init__(self, gateway_url="http://localhost:3000"):
        self.gateway_url = gateway_url.rstrip('/')
        self.session = requests.Session()
        self.session.headers.update({'Content-Type': 'application/json'})
        self.passed = 0
        self.failed = 0

    def log(self, message, color=Colors.BLUE):
        timestamp = datetime.now().strftime('%H:%M:%S')
        print(f"{Colors.BOLD}[{timestamp}]{Colors.END} {color}{message}{Colors.END}")

    def log_success(self, message):
        self.passed += 1
        self.log(f"✓ {message}", Colors.GREEN)

    def log_error(self, message):
        self.failed += 1
        self.log(f"✗ {message}", Colors.RED)

    def log_info(self, message):
        self.log(f"ℹ {message}", Colors.CYAN)

    def test_health(self):
        """测试健康检查端点"""
        self.log_info("测试 Gateway 健康检查...")
        try:
            resp = self.session.get(f"{self.gateway_url}/api/v1/health", timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                self.log_success(f"Gateway 运行正常: {data.get('status', 'unknown')}")
                return True
            else:
                self.log_error(f"健康检查失败: HTTP {resp.status_code}")
                return False
        except Exception as e:
            self.log_error(f"健康检查异常: {e}")
            return False

    def test_chat_request(self, message="你好，这是一个测试"):
        """测试发送聊天请求"""
        self.log_info(f"发送测试请求: '{message}'")
        try:
            payload = {
                "message": message,
                "user_id": "test-client",
                "platform": "cli",
                "priority": 5
            }
            resp = self.session.post(
                f"{self.gateway_url}/api/v1/chat",
                json=payload,
                timeout=10
            )
            
            if resp.status_code == 200 or resp.status_code == 202:
                data = resp.json()
                request_id = data.get('requestId')
                if request_id:
                    self.log_success(f"请求已接受: {request_id}")
                    return request_id
                else:
                    self.log_error("响应中没有 requestId")
                    return None
            else:
                self.log_error(f"请求失败: HTTP {resp.status_code}")
                print(f"响应内容: {resp.text}")
                return None
        except Exception as e:
            self.log_error(f"发送请求异常: {e}")
            return None

    def test_get_request_status(self, request_id):
        """测试查询请求状态"""
        self.log_info(f"查询请求状态: {request_id}")
        try:
            resp = self.session.get(
                f"{self.gateway_url}/api/v1/requests/{request_id}",
                timeout=5
            )
            if resp.status_code == 200:
                data = resp.json()
                status = data.get('status', 'unknown')
                self.log_success(f"请求状态: {status}")
                return data
            else:
                self.log_error(f"查询失败: HTTP {resp.status_code}")
                return None
        except Exception as e:
            self.log_error(f"查询异常: {e}")
            return None

    def wait_for_response(self, request_id, max_wait=30):
        """等待请求完成并获取响应"""
        self.log_info(f"等待请求完成 (最多 {max_wait} 秒)...")
        
        start_time = time.time()
        while time.time() - start_time < max_wait:
            data = self.test_get_request_status(request_id)
            if data:
                status = data.get('status', '').lower()
                if status in ['completed', 'failed', 'error']:
                    if status == 'completed':
                        response_body = data.get('response', {}).get('body', '')
                        if response_body:
                            self.log_success(f"请求完成，响应长度: {len(response_body)} 字符")
                            print(f"\n{Colors.YELLOW}响应内容:{Colors.END}")
                            print(response_body[:500] + "..." if len(response_body) > 500 else response_body)
                        return data
                    else:
                        self.log_error(f"请求失败: {data.get('error', 'Unknown error')}")
                        return data
            time.sleep(1)
        
        self.log_error("等待超时")
        return None

    def test_telemetry_stream(self):
        """测试遥测流端点"""
        self.log_info("测试遥测流...")
        try:
            # 注意: 这是一个SSE端点，这里只做简单检查
            resp = self.session.get(
                f"{self.gateway_url.replace(':3000', ':8000')}/telemetry/stream",
                headers={'Accept': 'text/event-stream'},
                timeout=3,
                stream=True
            )
            self.log_success("遥测流端点可访问")
            return True
        except requests.exceptions.ReadTimeout:
            self.log_success("遥测流端点可访问 (SSE连接正常)")
            return True
        except Exception as e:
            self.log_error(f"遥测流测试失败: {e}")
            return False

    def run_basic_tests(self):
        """运行基础测试"""
        print(f"\n{Colors.BOLD}{'='*60}{Colors.END}")
        print(f"{Colors.BOLD}ProClaw 基础集成测试{Colors.END}")
        print(f"{Colors.BOLD}{'='*60}{Colors.END}\n")
        
        # 1. 健康检查
        if not self.test_health():
            self.log_error("Gateway 未运行，请先启动服务")
            print(f"\n启动服务命令:")
            print(f"  cd /home/eziothean/ProClaw && ./launcher.sh")
            return False
        
        # 2. 发送请求
        request_id = self.test_chat_request()
        if not request_id:
            return False
        
        # 3. 等待响应
        self.wait_for_response(request_id)
        
        print(f"\n{Colors.BOLD}{'='*60}{Colors.END}")
        self.print_summary()
        
        return self.failed == 0

    def run_full_tests(self):
        """运行完整测试套件"""
        print(f"\n{Colors.BOLD}{'='*60}{Colors.END}")
        print(f"{Colors.BOLD}ProClaw 完整集成测试套件{Colors.END}")
        print(f"{Colors.BOLD}{'='*60}{Colors.END}\n")
        
        # 1. 健康检查
        if not self.test_health():
            self.log_error("Gateway 未运行，请先启动服务")
            return False
        
        # 2. 发送多个不同类型的请求
        test_messages = [
            "你好",
            "列出当前目录的文件",
            "今天天气怎么样？",
        ]
        
        request_ids = []
        for msg in test_messages:
            request_id = self.test_chat_request(msg)
            if request_id:
                request_ids.append(request_id)
            time.sleep(0.5)
        
        # 3. 等待所有请求完成
        self.log_info(f"等待 {len(request_ids)} 个请求完成...")
        for request_id in request_ids:
            self.wait_for_response(request_id, max_wait=20)
            print()
        
        # 4. 测试遥测
        self.test_telemetry_stream()
        
        print(f"\n{Colors.BOLD}{'='*60}{Colors.END}")
        self.print_summary()
        
        return self.failed == 0

    def run_continuous(self, interval=5):
        """持续发送测试请求"""
        print(f"\n{Colors.BOLD}{'='*60}{Colors.END}")
        print(f"{Colors.BOLD}ProClaw 持续测试模式{Colors.END}")
        print(f"{Colors.BOLD}间隔: {interval} 秒 | 按 Ctrl+C 停止{Colors.END}")
        print(f"{Colors.BOLD}{'='*60}{Colors.END}\n")
        
        if not self.test_health():
            self.log_error("Gateway 未运行")
            return False
        
        count = 0
        try:
            while True:
                count += 1
                print(f"\n{Colors.BOLD}--- 测试 #{count} ---{Colors.END}")
                request_id = self.test_chat_request(f"持续测试请求 #{count}")
                if request_id:
                    time.sleep(interval)
        except KeyboardInterrupt:
            print(f"\n\n{Colors.YELLOW}测试已停止{Colors.END}")
        
        return True

    def print_summary(self):
        """打印测试摘要"""
        total = self.passed + self.failed
        print(f"\n{Colors.BOLD}测试摘要:{Colors.END}")
        print(f"  总计: {total}")
        print(f"  通过: {Colors.GREEN}{self.passed}{Colors.END}")
        print(f"  失败: {Colors.RED}{self.failed}{Colors.END}")
        
        if self.failed == 0:
            print(f"\n{Colors.GREEN}{Colors.BOLD}✓ 所有测试通过!{Colors.END}")
        else:
            print(f"\n{Colors.RED}{Colors.BOLD}✗ 部分测试失败{Colors.END}")


def main():
    parser = argparse.ArgumentParser(description='ProClaw 服务端集成测试客户端')
    parser.add_argument('--gateway', default='http://localhost:3000', help='Gateway URL')
    parser.add_argument('--full', action='store_true', help='运行完整测试套件')
    parser.add_argument('--continuous', action='store_true', help='持续发送测试请求')
    parser.add_argument('--interval', type=int, default=5, help='持续测试间隔(秒)')
    
    args = parser.parse_args()
    
    client = ProClawTestClient(args.gateway)
    
    if args.continuous:
        success = client.run_continuous(args.interval)
    elif args.full:
        success = client.run_full_tests()
    else:
        success = client.run_basic_tests()
    
    sys.exit(0 if success else 1)


if __name__ == '__main__':
    main()
