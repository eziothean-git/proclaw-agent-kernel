"""Gateway client with SSE support and reconnection logic."""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, AsyncIterator, Optional

import aiohttp
from textual import log

from .events import ChatStreamEvent, ConnectionState, ConnectionStatus, EventType, HealthStatus

logger = logging.getLogger(__name__)


class GatewayClient:
    """Client for communicating with Agent Kernel Gateway."""

    def __init__(
        self,
        base_url: str = "http://localhost:3000",
        user_id: str = "proclaw-user",
        max_retries: int = 5,
        retry_delay: float = 2.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.user_id = user_id
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.session: Optional[aiohttp.ClientSession] = None
        self._connection_status = ConnectionStatus(state=ConnectionState.DISCONNECTED)

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=300),  # 5 minute timeout
                headers={"Accept": "text/event-stream"},
            )
        return self.session

    async def close(self) -> None:
        """Close the client session."""
        if self.session and not self.session.closed:
            await self.session.close()
        self._connection_status.state = ConnectionState.DISCONNECTED

    @property
    def connection_status(self) -> ConnectionStatus:
        """Get current connection status."""
        return self._connection_status

    async def check_health(self) -> Optional[HealthStatus]:
        """Check Gateway health status."""
        try:
            session = await self._get_session()
            async with session.get(f"{self.base_url}/api/v1/health") as response:
                if response.status == 200:
                    data = await response.json()
                    return HealthStatus(
                        status=data["status"],
                        gateway=data["gateway"],
                        storage=data["storage"],
                        timestamp=datetime.fromisoformat(data["timestamp"]),
                        version=data["version"],
                    )
        except Exception as e:
            log.warning(f"Health check failed: {e}")
        return None

    async def send_message(
        self,
        message: str,
        session_id: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> AsyncIterator[ChatStreamEvent]:
        """Send a message and receive SSE events with automatic reconnection.

        Args:
            message: The message to send
            session_id: Optional session ID to reuse
            metadata: Optional metadata

        Yields:
            ChatStreamEvent: SSE events from the Gateway
        """
        retry_count = 0
        last_error: Optional[str] = None

        while retry_count <= self.max_retries:
            try:
                self._connection_status.state = ConnectionState.CONNECTING
                self._connection_status.reconnect_attempts = retry_count

                session = await self._get_session()

                # Build query parameters
                params = {
                    "message": message,
                    "user_id": self.user_id,
                    "platform": "tui",
                }
                if session_id:
                    params["session_id"] = session_id
                if metadata:
                    params["metadata"] = json.dumps(metadata)

                log.info(f"Connecting to SSE stream (attempt {retry_count + 1})")

                async with session.get(
                    f"{self.base_url}/api/v1/chat/stream",
                    params=params,
                ) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise ConnectionError(f"HTTP {response.status}: {error_text}")

                    self._connection_status.state = ConnectionState.CONNECTED
                    self._connection_status.connected_at = datetime.now()
                    self._connection_status.last_error = None
                    self._connection_status.reconnect_attempts = 0
                    retry_count = 0  # Reset retry count on successful connection

                    log.info("SSE connection established")

                    # Read SSE stream
                    async for line in response.content:
                        line_str = line.decode("utf-8").strip()

                        if not line_str:
                            continue

                        if line_str.startswith("data: "):
                            data_str = line_str[6:]  # Remove "data: " prefix

                            try:
                                data = json.loads(data_str)
                                event = ChatStreamEvent.model_validate(data)
                                yield event

                                # If we get a complete or error event, we're done
                                if event.type in (EventType.COMPLETE, EventType.ERROR):
                                    return

                            except json.JSONDecodeError as e:
                                log.warning(f"Failed to parse SSE data: {e}")
                            except Exception as e:
                                log.error(f"Failed to validate event: {e}")

            except asyncio.CancelledError:
                log.info("SSE stream cancelled")
                self._connection_status.state = ConnectionState.DISCONNECTED
                raise

            except Exception as e:
                last_error = str(e)
                log.error(f"SSE connection error: {e}")
                self._connection_status.state = ConnectionState.ERROR
                self._connection_status.last_error = last_error

                if retry_count < self.max_retries:
                    retry_count += 1
                    self._connection_status.state = ConnectionState.RECONNECTING
                    self._connection_status.reconnect_attempts = retry_count

                    wait_time = self.retry_delay * (2 ** (retry_count - 1))  # Exponential backoff
                    log.info(
                        f"Reconnecting in {wait_time}s (attempt {retry_count}/{self.max_retries})"
                    )
                    await asyncio.sleep(wait_time)
                else:
                    log.error(f"Max retries ({self.max_retries}) exceeded")
                    # Yield error event
                    yield ChatStreamEvent(
                        type=EventType.ERROR,
                        timestamp=datetime.now(),
                        request_id="client",
                        error=f"Connection failed after {self.max_retries} retries: {last_error}",
                    )
                    return

    async def get_request_status(self, request_id: str) -> Optional[dict[str, Any]]:
        """Get status of a specific request.

        Args:
            request_id: The request ID

        Returns:
            Request status data or None if not found
        """
        try:
            session = await self._get_session()
            async with session.get(
                f"{self.base_url}/api/v1/requests/{request_id}/status"
            ) as response:
                if response.status == 200:
                    return await response.json()
        except Exception as e:
            log.warning(f"Failed to get request status: {e}")
        return None

    async def get_system_status(self) -> dict[str, Any]:
        """Get overall system status.

        Returns:
            Dictionary with system status information
        """
        health = await self.check_health()

        return {
            "connected": self._connection_status.state == ConnectionState.CONNECTED,
            "connection_state": self._connection_status.state.value,
            "health": health.model_dump() if health else None,
            "last_error": self._connection_status.last_error,
        }
