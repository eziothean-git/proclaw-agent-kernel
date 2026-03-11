"""
Gateway Callback Skill - System Skill for Python Kernel.

负责将处理结果通过HTTP回调发送给Gateway。
这是核心系统skill，确保Kernel可以直接与Gateway通信。
"""

import asyncio
import json
import os
from datetime import datetime
from typing import Any, Optional

import httpx
import structlog

logger = structlog.get_logger()


class GatewayCallbackSkill:
    """
    Skill for sending HTTP callbacks to Gateway.
    
    Usage:
        skill = GatewayCallbackSkill()
        await skill.send_callback(
            request_id="uuid",
            session_id="uuid", 
            status="completed",
            body="response text",
            metadata={"actions": [...]}
        )
    """
    
    def __init__(self, gateway_url: Optional[str] = None):
        self.gateway_url = gateway_url or os.environ.get(
            "GATEWAY_URL", 
            "http://localhost:3000"
        )
        self.webhook_path = "/gateway/webhook/kernel-response"
        self.callback_url = f"{self.gateway_url}{self.webhook_path}"
        
        # HTTP client with connection pooling
        self.client = httpx.AsyncClient(
            timeout=30.0,
            limits=httpx.Limits(max_connections=10, max_keepalive_connections=5)
        )
        
        logger.info(
            "GatewayCallbackSkill initialized",
            gateway_url=self.gateway_url,
            callback_url=self.callback_url
        )
    
    async def send_callback(
        self,
        request_id: str,
        session_id: str,
        status: str,  # "completed" | "failed" | "partial"
        body: str = "",
        metadata: Optional[dict] = None,
        error: Optional[dict] = None,
        processing_time_ms: Optional[int] = None,
        max_retries: int = 3,
    ) -> bool:
        """
        Send callback to Gateway.
        
        Args:
            request_id: Request ID
            session_id: Session ID
            status: "completed", "failed", or "partial"
            body: Response body text
            metadata: Optional metadata including actions
            error: Optional error info if failed
            processing_time_ms: Processing time in milliseconds
            max_retries: Max retry attempts
            
        Returns:
            True if successful, False otherwise
        """
        payload = {
            "request_id": request_id,
            "session_id": session_id,
            "status": status,
            "header": {
                "timestamp": datetime.utcnow().isoformat(),
                "processing_time_ms": processing_time_ms,
            },
            "body": body,
            "metadata": metadata or {},
        }
        
        if error:
            payload["error"] = error
        
        for attempt in range(max_retries):
            try:
                response = await self.client.post(
                    self.callback_url,
                    json=payload,
                    headers={"Content-Type": "application/json"}
                )
                
                if response.status_code < 400:
                    logger.info(
                        "Callback sent successfully",
                        request_id=request_id,
                        status=status,
                        attempt=attempt + 1
                    )
                    return True
                else:
                    logger.warning(
                        "Callback failed",
                        request_id=request_id,
                        status_code=response.status_code,
                        response=response.text[:200],
                        attempt=attempt + 1
                    )
                    
            except Exception as e:
                logger.warning(
                    "Callback exception",
                    request_id=request_id,
                    error=str(e),
                    attempt=attempt + 1
                )
            
            # Exponential backoff
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # 1s, 2s, 4s
                logger.info(
                    "Retrying callback",
                    request_id=request_id,
                    wait_time=wait_time,
                    next_attempt=attempt + 2
                )
                await asyncio.sleep(wait_time)
        
        # All retries failed
        logger.error(
            "Callback failed after all retries",
            request_id=request_id,
            max_retries=max_retries
        )
        
        # Save failed callback for manual recovery
        await self._save_failed_callback(payload)
        return False
    
    async def send_completion(
        self,
        request_id: str,
        session_id: str,
        output: str,
        actions: Optional[list] = None,
        processing_time_ms: Optional[int] = None,
    ) -> bool:
        """Convenience method for sending completion callback."""
        return await self.send_callback(
            request_id=request_id,
            session_id=session_id,
            status="completed",
            body=output,
            metadata={"actions": actions or []},
            processing_time_ms=processing_time_ms,
        )
    
    async def send_error(
        self,
        request_id: str,
        session_id: str,
        error_message: str,
        error_category: str = "system_error",
        error_code: str = "INTERNAL_ERROR",
        recoverable: bool = False,
        processing_time_ms: Optional[int] = None,
    ) -> bool:
        """Convenience method for sending error callback."""
        return await self.send_callback(
            request_id=request_id,
            session_id=session_id,
            status="failed",
            body="",
            error={
                "category": error_category,
                "code": error_code,
                "message": error_message,
                "recoverable": recoverable,
            },
            processing_time_ms=processing_time_ms,
        )
    
    async def _save_failed_callback(self, payload: dict) -> None:
        """Save failed callback to file system for manual recovery."""
        try:
            data_path = os.environ.get("DATA_PATH", "./data")
            failed_dir = f"{data_path}/failed_callbacks"
            os.makedirs(failed_dir, exist_ok=True)
            
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S_%f")
            request_id = payload.get("request_id", "unknown")
            filename = f"{timestamp}_{request_id}.json"
            filepath = f"{failed_dir}/{filename}"
            
            failed_record = {
                "timestamp": datetime.utcnow().isoformat(),
                "callback_url": self.callback_url,
                "payload": payload,
            }
            
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(failed_record, f, ensure_ascii=False, indent=2)
            
            logger.info("Failed callback saved", filepath=filepath)
        except Exception as e:
            logger.error("Failed to save failed callback", error=str(e))
    
    async def close(self) -> None:
        """Close HTTP client."""
        await self.client.aclose()
        logger.info("GatewayCallbackSkill closed")


# Global instance
_callback_skill: Optional[GatewayCallbackSkill] = None


def get_callback_skill() -> GatewayCallbackSkill:
    """Get global callback skill instance."""
    global _callback_skill
    if _callback_skill is None:
        _callback_skill = GatewayCallbackSkill()
    return _callback_skill