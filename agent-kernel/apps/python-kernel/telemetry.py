"""
Telemetry Emitter - HTTP-based telemetry streaming to Gateway.

重构说明:
- 从 SSE Server 改为 HTTP Client
- 支持批量发送，减少 HTTP 开销
- 本地缓冲防止网络故障时丢数据
- 保留 emit_telemetry() API 向后兼容
"""
import asyncio
import json
import os
import time
from collections import deque
from datetime import datetime
from typing import Any, Optional
from urllib.parse import urljoin

import aiohttp
import structlog

logger = structlog.get_logger()


class TelemetryEvent:
    """遥测事件结构"""
    
    def __init__(
        self,
        request_id: str,
        layer: int,
        layer_name: str,
        component: str,
        operation: str,
        status: str,
        message: str = "",
        session_id: Optional[str] = None,
        trace_id: Optional[str] = None,
        level: str = "standard",
        progress_pct: Optional[int] = None,
        step: Optional[int] = None,
        total_steps: Optional[int] = None,
        phase: Optional[str] = None,
        payload: Optional[dict] = None,
        metrics: Optional[dict] = None,
        sub_threads: Optional[list] = None,
        details: Optional[dict] = None,
        elapsed_ms: Optional[int] = None,
    ):
        self.timestamp = datetime.utcnow().isoformat()
        self.trace_id = trace_id or request_id
        self.request_id = request_id
        self.session_id = session_id
        self.layer = layer
        self.layer_name = layer_name
        self.component = component
        self.operation = operation
        self.status = status
        self.message = message
        self.level = level
        self.progress_pct = progress_pct
        self.step = step
        self.total_steps = total_steps
        self.phase = phase
        self.payload = payload or {}
        self.metrics = metrics or {}
        self.sub_threads = sub_threads or []
        self.details = details
        self.elapsed_ms = elapsed_ms
    
    def to_dict(self) -> dict[str, Any]:
        """转换为字典"""
        result = {
            "timestamp": self.timestamp,
            "trace_id": self.trace_id,
            "request_id": self.request_id,
            "session_id": self.session_id,
            "layer": self.layer,
            "layer_name": self.layer_name,
            "component": self.component,
            "operation": self.operation,
            "status": self.status,
            "message": self.message,
            "level": self.level,
        }
        
        if self.progress_pct is not None:
            result["progress_pct"] = self.progress_pct
        if self.step is not None:
            result["step"] = self.step
        if self.total_steps is not None:
            result["total_steps"] = self.total_steps
        if self.phase:
            result["phase"] = self.phase
        if self.payload:
            result["payload"] = self.payload
        if self.metrics:
            result["metrics"] = self.metrics
        if self.sub_threads:
            result["sub_threads"] = self.sub_threads
        if self.details:
            result["details"] = self.details
        if self.elapsed_ms is not None:
            result["elapsed_ms"] = self.elapsed_ms
            
        return result


class TelemetryEmitter:
    """
    遥测发射器 - 批量 HTTP POST 发送到 Gateway
    
    特性:
    - 异步批量发送
    - 本地缓冲防丢
    - 自动重连
    """
    
    _instance: Optional["TelemetryEmitter"] = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        self.gateway_url = os.getenv("GATEWAY_URL", "http://localhost:3000")
        self.endpoint = urljoin(self.gateway_url, "/v1/telemetry/batch")
        
        # 批量发送配置
        self.batch_size = int(os.getenv("TELEMETRY_BATCH_SIZE", "10"))
        self.batch_interval = float(os.getenv("TELEMETRY_BATCH_INTERVAL", "0.1"))
        self.max_retries = int(os.getenv("TELEMETRY_MAX_RETRIES", "3"))
        
        # 缓冲
        self._buffer: deque[TelemetryEvent] = deque(maxlen=1000)
        self._lock = asyncio.Lock()
        self._session: Optional[aiohttp.ClientSession] = None
        self._flush_task: Optional[asyncio.Task] = None
        self._running = False
        
        logger.info(
            "TelemetryEmitter initialized",
            gateway_url=self.gateway_url,
            batch_size=self.batch_size,
            batch_interval=self.batch_interval,
        )
    
    async def start(self):
        """启动发射器"""
        if self._running:
            return
        
        self._running = True
        self._session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=5.0),
            headers={"Content-Type": "application/json"},
        )
        
        # 启动后台刷新任务
        self._flush_task = asyncio.create_task(self._flush_loop())
        
        logger.info("TelemetryEmitter started")
    
    async def stop(self):
        """停止发射器，发送剩余事件"""
        if not self._running:
            return
        
        self._running = False
        
        # 取消刷新任务
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
        
        # 发送剩余事件
        await self._flush_buffer()
        
        # 关闭 session
        if self._session:
            await self._session.close()
            self._session = None
        
        logger.info("TelemetryEmitter stopped")
    
    async def emit(self, event: TelemetryEvent):
        """
        发射遥测事件
        
        Args:
            event: 遥测事件
        """
        # 确保已启动
        if not self._running:
            await self.start()
        
        async with self._lock:
            self._buffer.append(event)
            
            # 如果 buffer 满了，立即发送
            if len(self._buffer) >= self.batch_size:
                asyncio.create_task(self._flush_buffer())
        
        logger.debug(
            "Telemetry event queued",
            request_id=event.request_id,
            layer=event.layer_name,
            operation=event.operation,
        )
    
    async def _flush_loop(self):
        """后台定时刷新循环"""
        while self._running:
            try:
                await asyncio.sleep(self.batch_interval)
                if self._buffer:
                    await self._flush_buffer()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in telemetry flush loop: {e}")
    
    async def _flush_buffer(self):
        """发送 buffer 中的事件"""
        async with self._lock:
            if not self._buffer:
                return
            
            # 取出所有事件
            events = list(self._buffer)
            self._buffer.clear()
        
        # 发送事件
        await self._send_batch(events)
    
    async def _send_batch(self, events: list[TelemetryEvent]):
        """批量发送事件到 Gateway"""
        if not events or not self._session:
            return
        
        payload = {
            "events": [e.to_dict() for e in events]
        }
        
        for attempt in range(self.max_retries):
            try:
                async with self._session.post(
                    self.endpoint,
                    json=payload,
                ) as response:
                    if 200 <= response.status < 300:
                        logger.debug(
                            f"Telemetry batch sent successfully",
                            count=len(events),
                        )
                        return
                    else:
                        text = await response.text()
                        logger.warning(
                            f"Telemetry batch failed with status {response.status}: {text}"
                        )
            except Exception as e:
                logger.error(f"Failed to send telemetry batch (attempt {attempt + 1}): {e}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(0.1 * (attempt + 1))  # 指数退避
        
        # 所有重试失败，记录日志（buffer 已经清空，数据丢失）
        logger.error(f"Failed to send telemetry batch after {self.max_retries} attempts, {len(events)} events lost")


# 全局实例
_emitter: Optional[TelemetryEmitter] = None


def get_telemetry_emitter() -> TelemetryEmitter:
    """获取全局发射器实例"""
    global _emitter
    if _emitter is None:
        _emitter = TelemetryEmitter()
    return _emitter


# 向后兼容的 API
async def emit_telemetry_async(
    request_id: str,
    layer: int,
    layer_name: str,
    component: str,
    operation: str,
    status: str,
    message: str = "",
    session_id: Optional[str] = None,
    **kwargs
) -> None:
    """
    异步发射遥测事件
    
    Args:
        request_id: 请求 ID
        layer: 架构层 (1-7)
        layer_name: 层名称
        component: 组件名
        operation: 操作名
        status: 状态 (start/progress/complete/error)
        message: 消息
        session_id: 会话 ID
        **kwargs: 其他字段
    """
    event = TelemetryEvent(
        request_id=request_id,
        layer=layer,
        layer_name=layer_name,
        component=component,
        operation=operation,
        status=status,
        message=message,
        session_id=session_id,
        **kwargs
    )
    
    await get_telemetry_emitter().emit(event)


def emit_telemetry(
    request_id: str,
    layer: int,
    layer_name: str,
    component: str,
    operation: str,
    status: str,
    message: str = "",
    session_id: Optional[str] = None,
    **kwargs
) -> None:
    """
    同步发射遥测事件（后台异步执行）
    
    向后兼容的 API，保持原有调用方式
    """
    try:
        loop = asyncio.get_running_loop()
        asyncio.create_task(emit_telemetry_async(
            request_id=request_id,
            layer=layer,
            layer_name=layer_name,
            component=component,
            operation=operation,
            status=status,
            message=message,
            session_id=session_id,
            **kwargs
        ))
    except RuntimeError:
        # 没有事件循环，无法发送
        logger.debug(f"Telemetry event dropped (no event loop)", request_id=request_id)
