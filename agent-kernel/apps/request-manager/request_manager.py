#!/usr/bin/env python3
"""
Request Manager - 最小实现示例
基于文件系统的信箱机制，与 Gateway 解耦

运行方式:
    python request_manager.py

功能:
    1. 监听 inbox 目录中的新请求
    2. 按优先级排序，串行处理
    3. 调用 Prime Personality（模拟）
    4. 将响应写入 outbox 目录
"""

import asyncio
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

# Configuration
BASE_DIR = Path(os.environ.get("GATEWAY_STORAGE_PATH", "/var/gateway"))
INBOX_DIR = BASE_DIR / "inbox"
OUTBOX_DIR = BASE_DIR / "outbox"
PENDING_DIR = BASE_DIR / "pending"
POLL_INTERVAL = float(os.environ.get("REQUEST_MANAGER_POLL_INTERVAL", "0.5"))


class RequestManager:
    """请求管理器 - 文件系统信箱消费者"""
    
    def __init__(self):
        self.logger = self._setup_logger()
        self.running = False
        self.processed_count = 0
        
    def _setup_logger(self):
        """简单的日志记录器"""
        class SimpleLogger:
            def info(self, msg):
                print(f"[INFO] {datetime.now().isoformat()} {msg}")
                
            def error(self, msg):
                print(f"[ERROR] {datetime.now().isoformat()} {msg}", file=sys.stderr)
                
            def debug(self, msg):
                if os.environ.get("DEBUG"):
                    print(f"[DEBUG] {datetime.now().isoformat()} {msg}")
        
        return SimpleLogger()
    
    async def initialize(self):
        """初始化目录结构"""
        INBOX_DIR.mkdir(parents=True, exist_ok=True)
        OUTBOX_DIR.mkdir(parents=True, exist_ok=True)
        PENDING_DIR.mkdir(parents=True, exist_ok=True)
        
        self.logger.info(f"Request Manager initialized")
        self.logger.info(f"Inbox: {INBOX_DIR}")
        self.logger.info(f"Outbox: {OUTBOX_DIR}")
    
    async def scan_inbox(self) -> List[Path]:
        """扫描 inbox 目录，返回待处理的请求文件列表"""
        inbox_files = []
        
        # 遍历所有日期子目录
        for date_dir in INBOX_DIR.iterdir():
            if not date_dir.is_dir():
                continue
                
            for file_path in date_dir.glob("*.json"):
                # 检查是否已经在处理中
                pending_file = PENDING_DIR / file_path.name
                if not pending_file.exists():
                    inbox_files.append(file_path)
        
        return inbox_files
    
    async def load_request(self, file_path: Path) -> Optional[Dict]:
        """加载请求文件"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            self.logger.error(f"Failed to load request {file_path}: {e}")
            return None
    
    async def mark_as_processing(self, request_id: str, file_path: Path):
        """标记请求为处理中"""
        pending_file = PENDING_DIR / f"{request_id}.json"
        
        # 创建软链接或复制文件
        try:
            if hasattr(os, 'symlink'):
                pending_file.symlink_to(file_path.absolute())
            else:
                # Windows 可能不支持 symlink，复制文件
                import shutil
                shutil.copy(file_path, pending_file)
        except Exception as e:
            self.logger.error(f"Failed to mark as processing: {e}")
    
    async def unmark_processing(self, request_id: str):
        """移除处理中标记"""
        pending_file = PENDING_DIR / f"{request_id}.json"
        try:
            if pending_file.exists():
                pending_file.unlink()
        except Exception as e:
            self.logger.error(f"Failed to unmark processing: {e}")
    
    async def process_request(self, request: Dict, file_path: Path) -> Dict:
        """
        处理单个请求
        这里应该调用真正的 Prime Personality
        """
        request_id = request["header"]["request_id"]
        user_id = request["header"]["user_id"]
        body = request["body"]
        
        self.logger.info(f"Processing request {request_id} from user {user_id}")
        self.logger.debug(f"Body: {body[:100]}...")
        
        # 模拟处理延迟
        await asyncio.sleep(1)
        
        # 模拟 Prime Personality 处理
        # 在实际实现中，这里应该调用:
        # - Prime Personality
        # - Session Host
        # - Executor
        # 等组件
        
        response_body = f"这是对你的消息 '{body[:30]}...' 的回复。\n\n"
        response_body += "【模拟回复】在实际系统中，这里会经过:\n"
        response_body += "1. Prime Personality 解析意图\n"
        response_body += "2. Session Host 分配任务\n"
        response_body += "3. Executor 执行具体操作\n"
        response_body += "4. 结果汇总返回\n"
        
        return {
            "header": {
                "request_id": request_id,
                "session_id": request["header"].get("session_id"),
                "timestamp": datetime.utcnow().isoformat(),
                "processing_time_ms": 1000,
            },
            "status": "completed",
            "body": response_body,
            "metadata": {
                "actions": [
                    {
                        "type": "process",
                        "status": "success",
                        "duration_ms": 1000,
                    }
                ]
            }
        }
    
    async def save_response(self, request_id: str, response: Dict):
        """将响应保存到 outbox"""
        try:
            # 创建日期目录
            date_str = datetime.now().strftime("%Y-%m-%d")
            date_dir = OUTBOX_DIR / date_str
            date_dir.mkdir(exist_ok=True)
            
            # 写入响应文件
            response_path = date_dir / f"{request_id}.json"
            with open(response_path, 'w', encoding='utf-8') as f:
                json.dump(response, f, indent=2, ensure_ascii=False)
            
            # 更新索引
            index_path = OUTBOX_DIR / "index.jsonl"
            index_entry = {
                "timestamp": datetime.utcnow().isoformat(),
                "request_id": request_id,
                "session_id": response["header"].get("session_id"),
                "status": response["status"],
                "path": str(response_path),
            }
            
            with open(index_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(index_entry) + "\n")
            
            self.logger.info(f"Response saved to {response_path}")
            
        except Exception as e:
            self.logger.error(f"Failed to save response: {e}")
            raise
    
    async def handle_error(self, request_id: str, request: Dict, error: Exception):
        """处理错误，将错误响应写入 outbox"""
        error_response = {
            "header": {
                "request_id": request_id,
                "session_id": request["header"].get("session_id"),
                "timestamp": datetime.utcnow().isoformat(),
            },
            "status": "failed",
            "body": "",
            "error": {
                "category": "system_error",
                "code": "INTERNAL_ERROR",
                "message": str(error),
                "recoverable": False,
            }
        }
        
        await self.save_response(request_id, error_response)
    
    async def process_single_request(self, file_path: Path):
        """处理单个请求的完整流程"""
        request = await self.load_request(file_path)
        if not request:
            return
        
        request_id = request["header"]["request_id"]
        
        try:
            # 标记为处理中
            await self.mark_as_processing(request_id, file_path)
            
            # 处理请求
            response = await self.process_request(request, file_path)
            
            # 保存响应
            await self.save_response(request_id, response)
            
            self.processed_count += 1
            
        except Exception as e:
            self.logger.error(f"Failed to process request {request_id}: {e}")
            await self.handle_error(request_id, request, e)
            
        finally:
            # 清理标记
            await self.unmark_processing(request_id)
            
            # 可选：归档或删除 inbox 文件
            # await self.archive_request(file_path)
    
    async def run(self):
        """主循环"""
        self.running = True
        
        self.logger.info("Request Manager started")
        self.logger.info(f"Polling interval: {POLL_INTERVAL}s")
        self.logger.info("Press Ctrl+C to stop")
        
        try:
            while self.running:
                # 扫描 inbox
                inbox_files = await self.scan_inbox()
                
                if inbox_files:
                    self.logger.info(f"Found {len(inbox_files)} pending requests")
                    
                    # 读取所有请求并排序
                    requests = []
                    for file_path in inbox_files:
                        request = await self.load_request(file_path)
                        if request:
                            priority = request["header"].get("priority", 0)
                            requests.append((priority, file_path, request))
                    
                    # 按优先级排序（高优先级在前）
                    requests.sort(key=lambda x: -x[0])
                    
                    # 串行处理
                    for priority, file_path, request in requests:
                        self.logger.info(f"Processing request with priority {priority}")
                        await self.process_single_request(file_path)
                
                # 等待下一次轮询
                await asyncio.sleep(POLL_INTERVAL)
                
        except KeyboardInterrupt:
            self.logger.info("\nStopping Request Manager...")
            self.running = False
        
        self.logger.info(f"Total processed: {self.processed_count}")


def main():
    """入口点"""
    manager = RequestManager()
    
    # 初始化
    asyncio.run(manager.initialize())
    
    # 运行主循环
    try:
        asyncio.run(manager.run())
    except Exception as e:
        print(f"Fatal error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
