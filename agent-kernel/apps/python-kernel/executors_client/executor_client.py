"""
Executor Client - HTTP client for calling TypeScript layer Executor.
Sends tool call requests and receives observations.
"""
import httpx
import structlog
from typing import Any

from schemas.models import ToolCallRequest, ToolCallResult

logger = structlog.get_logger()


class ExecutorClient:
    """
    Client for communicating with TypeScript Executor layer.
    Handles tool call execution and result retrieval.
    """
    
    def __init__(self, base_url: str = "http://localhost:3000"):
        self.base_url = base_url
        self.logger = logger.bind(component="ExecutorClient")
        self.client = httpx.AsyncClient(
            base_url=base_url,
            timeout=60.0,
        )
    
    async def execute_tool(self, request: ToolCallRequest) -> ToolCallResult:
        """
        Execute a tool call via the TypeScript executor.
        
        Args:
            request: Tool call request
            
        Returns:
            Tool call result
        """
        self.logger.info(
            "Executing tool via executor",
            request_id=request.request_id,
            skill=request.skill_name,
            tool=request.tool_name,
        )
        
        try:
            response = await self.client.post(
                "/api/v1/executor/execute",
                json={
                    "request_id": request.request_id,
                    "session_id": request.session_id,
                    "skill_name": request.skill_name,
                    "tool_name": request.tool_name,
                    "arguments": request.parameters,
                }
            )
            
            response.raise_for_status()
            data = response.json()
            
            result = ToolCallResult(
                request_id=request.request_id,
                success=data.get("success", False),
                result=data.get("result"),
                error=data.get("error"),
                execution_time_ms=data.get("execution_time_ms", 0),
            )
            
            self.logger.info(
                "Tool execution completed",
                request_id=request.request_id,
                success=result.success,
                execution_time=result.execution_time_ms,
            )
            
            return result
            
        except httpx.HTTPError as e:
            self.logger.error(
                "HTTP error calling executor",
                request_id=request.request_id,
                error=str(e),
            )
            return ToolCallResult(
                request_id=request.request_id,
                success=False,
                error=f"HTTP error: {str(e)}",
                execution_time_ms=0,
            )
        except Exception as e:
            self.logger.error(
                "Unexpected error calling executor",
                request_id=request.request_id,
                error=str(e),
            )
            return ToolCallResult(
                request_id=request.request_id,
                success=False,
                error=f"Unexpected error: {str(e)}",
                execution_time_ms=0,
            )
    
    async def cancel_execution(self, request_id: str) -> bool:
        """
        Cancel an ongoing execution.
        
        Args:
            request_id: Execution to cancel
            
        Returns:
            True if cancelled successfully
        """
        try:
            response = await self.client.post(
                f"/api/v1/executor/cancel/{request_id}"
            )
            response.raise_for_status()
            return True
        except Exception as e:
            self.logger.error(
                "Failed to cancel execution",
                request_id=request_id,
                error=str(e),
            )
            return False
    
    async def list_available_tools(self, skill_name: str) -> list[dict[str, Any]]:
        """
        List available tools from a skill.
        
        Args:
            skill_name: Name of the skill
            
        Returns:
            List of available tools
        """
        try:
            response = await self.client.get(
                f"/api/v1/executor/tools/{skill_name}"
            )
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, list):
                return payload
            return payload.get("tools", [])
        except Exception as e:
            self.logger.error(
                "Failed to list tools",
                skill=skill_name,
                error=str(e),
            )
            return []
    
    async def health_check(self) -> dict[str, Any]:
        """Check executor health."""
        try:
            response = await self.client.get("/api/v1/health")
            response.raise_for_status()
            return response.json()
        except Exception as e:
            self.logger.error("Health check failed", error=str(e))
            return {"status": "unhealthy", "error": str(e)}
    
    async def close(self) -> None:
        """Close HTTP client."""
        await self.client.aclose()


# Singleton instance
_executor_client: ExecutorClient | None = None


def get_executor_client() -> ExecutorClient:
    """Get or create singleton instance."""
    global _executor_client
    if _executor_client is None:
        base_url = "http://localhost:3000"  # Gateway URL
        _executor_client = ExecutorClient(base_url)
    return _executor_client
