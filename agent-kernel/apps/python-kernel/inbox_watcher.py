"""
Gateway Inbox 监听器 - 监听文件系统 Mailbox 中的新请求。

功能：
1. 轮询 Gateway 的 inbox 目录
2. 读取新请求文件
3. 提交到处理队列
4. 处理完成后通过 callback 通知 Gateway
"""
import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import structlog

from schemas.models import Request, RequestStatus, Session
from storage.runtime_store import get_memory_manager
from thread_runtime.scheduler import get_scheduler

logger = structlog.get_logger()


class InboxWatcher:
    """Gateway Inbox 监听器"""
    
    def __init__(
        self,
        inbox_path: str,
        gateway_url: str = "http://localhost:3000",
        poll_interval: float = 1.0,
    ):
        self.inbox_path = Path(inbox_path)
        self.gateway_url = gateway_url
        self.poll_interval = poll_interval
        self.processed_requests: set[str] = set()
        self._running = False
        self._task: asyncio.Task | None = None
        self._client = httpx.AsyncClient(timeout=30.0)
        self.logger = logger.bind(component="InboxWatcher")
        
    async def start(self) -> None:
        """启动监听器"""
        self._running = True
        self._task = asyncio.create_task(self._watch_loop())
        self.logger.info(
            "Inbox watcher started",
            inbox_path=str(self.inbox_path),
            poll_interval=self.poll_interval,
        )
        
    async def stop(self) -> None:
        """停止监听器"""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        await self._client.aclose()
        self.logger.info("Inbox watcher stopped")
        
    async def _watch_loop(self) -> None:
        """监听循环"""
        while self._running:
            try:
                await self._check_inbox()
            except Exception as e:
                self.logger.error("Inbox check error", error=str(e))
            
            await asyncio.sleep(self.poll_interval)
            
    async def _check_inbox(self) -> None:
        """检查 inbox 中的新请求"""
        if not self.inbox_path.exists():
            return
            
        # 读取 inbox 索引文件
        index_path = self.inbox_path / "index.jsonl"
        if not index_path.exists():
            return
            
        try:
            with open(index_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
                
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                    
                try:
                    entry = json.loads(line)
                    request_id = entry.get("requestId")
                    
                    if not request_id or request_id in self.processed_requests:
                        continue
                        
                    # 检查状态是否为 pending
                    if entry.get("status") != "pending":
                        continue
                        
                    # 读取请求文件
                    request_path = Path(entry.get("path", ""))
                    if not request_path.exists():
                        # 尝试从日期目录读取
                        date_str = datetime.now().strftime("%Y-%m-%d")
                        request_path = self.inbox_path / date_str / f"{request_id}.json"
                        
                    if not request_path.exists():
                        self.logger.warning(
                            "Request file not found",
                            request_id=request_id,
                            path=str(request_path),
                        )
                        continue
                        
                    # 处理请求
                    await self._process_request_file(request_path, request_id)
                    self.processed_requests.add(request_id)
                    
                except json.JSONDecodeError:
                    continue
                except Exception as e:
                    self.logger.error(
                        "Failed to process inbox entry",
                        error=str(e),
                    )
                    
        except Exception as e:
            self.logger.error("Failed to read inbox index", error=str(e))
            
    async def _process_request_file(self, request_path: Path, request_id: str) -> None:
        """处理单个请求文件"""
        try:
            with open(request_path, "r", encoding="utf-8") as f:
                request_data = json.load(f)
                
            self.logger.info(
                "Processing request from inbox",
                request_id=request_id,
                path=str(request_path),
            )
            
            # 提取请求信息
            header = request_data.get("header", {})
            body = request_data.get("body", "")
            metadata = request_data.get("metadata", {})
            
            # 创建 Request 对象
            request = Request(
                id=request_id,
                session_id=header.get("sessionId") or f"sess_{uuid4().hex[:12]}",
                user_id=header.get("userId") or "unknown",
                message=body,
                metadata={
                    **metadata,
                    "platform": header.get("platform"),
                    "device_id": header.get("deviceId"),
                    "source_ip": header.get("sourceIp"),
                    "client_version": header.get("clientVersion"),
                },
            )
            
            # 保存请求到存储
            memory_manager = get_memory_manager()
            await memory_manager.save_request(request)
            
            # 创建会话（如果不存在）
            session = await memory_manager.get_session(request.session_id)
            if not session:
                session = Session(
                    id=request.session_id,
                    user_id=request.user_id,
                )
                await memory_manager.save_session(session)
                
            # 记录事件
            await memory_manager.save_event(
                request.session_id,
                {
                    "timestamp": datetime.utcnow().isoformat(),
                    "session_id": request.session_id,
                    "request_id": request.id,
                    "phase": "request_received_from_inbox",
                    "actor": "inbox_watcher",
                    "summary": request.message[:100],
                    "status": "received",
                },
            )
            
            # 构建 callback URL
            callback_url = f"{self.gateway_url}/gateway/webhook/kernel-response"
            
            # 异步处理请求
            asyncio.create_task(
                self._handle_request_async(request_id, callback_url)
            )
            
        except Exception as e:
            self.logger.error(
                "Failed to process request file",
                request_id=request_id,
                path=str(request_path),
                error=str(e),
            )
            
    async def _handle_request_async(self, request_id: str, callback_url: str) -> None:
        """异步处理请求"""
        from main import process_request_async
        
        try:
            await process_request_async(request_id, callback_url)
        except Exception as e:
            self.logger.error(
                "Request processing failed",
                request_id=request_id,
                error=str(e),
            )


# 全局实例
_inbox_watcher: InboxWatcher | None = None


def get_inbox_watcher() -> InboxWatcher:
    """获取 InboxWatcher 实例"""
    global _inbox_watcher
    if _inbox_watcher is None:
        inbox_path = os.getenv("GATEWAY_INBOX_PATH", "/home/eziothean/ProClaw/agent-kernel/data/gateway/inbox")
        gateway_url = os.getenv("GATEWAY_URL", "http://localhost:3000")
        poll_interval = float(os.getenv("INBOX_POLL_INTERVAL", "1.0"))
        
        _inbox_watcher = InboxWatcher(
            inbox_path=inbox_path,
            gateway_url=gateway_url,
            poll_interval=poll_interval,
        )
    return _inbox_watcher


def reset_inbox_watcher() -> None:
    """重置 InboxWatcher 实例（用于测试）"""
    global _inbox_watcher
    _inbox_watcher = None
