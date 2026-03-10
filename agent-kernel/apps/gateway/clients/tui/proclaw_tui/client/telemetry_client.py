"""Telemetry client for streaming events from Python Kernel."""

import asyncio
import json
from datetime import datetime
from typing import Any, AsyncIterator, Callable, Optional

import aiohttp
from textual import log

from .events import TelemetryEvent


class TelemetryClient:
    """Client for receiving telemetry events via SSE from Python Kernel."""

    def __init__(
        self,
        base_url: str = "http://localhost:8000",
        max_retries: int = 3,
        retry_delay: float = 2.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self.session: Optional[aiohttp.ClientSession] = None
        self._event_handlers: list[Callable[[TelemetryEvent], None]] = []

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session."""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=300),
                headers={"Accept": "text/event-stream"},
            )
        return self.session

    async def close(self) -> None:
        """Close the client session."""
        if self.session and not self.session.closed:
            await self.session.close()

    def add_event_handler(self, handler: Callable[[TelemetryEvent], None]) -> None:
        """Add an event handler callback."""
        self._event_handlers.append(handler)

    def remove_event_handler(self, handler: Callable[[TelemetryEvent], None]) -> None:
        """Remove an event handler callback."""
        if handler in self._event_handlers:
            self._event_handlers.remove(handler)

    def _notify_handlers(self, event: TelemetryEvent) -> None:
        """Notify all registered handlers."""
        for handler in self._event_handlers:
            try:
                handler(event)
            except Exception as e:
                log.error(f"Telemetry event handler failed: {e}")

    async def stream_telemetry(
        self,
        request_id: Optional[str] = None,
    ) -> AsyncIterator[TelemetryEvent]:
        """
        Stream telemetry events from Python Kernel.

        Args:
            request_id: Optional request ID to filter events

        Yields:
            TelemetryEvent objects
        """
        retry_count = 0

        while retry_count <= self.max_retries:
            try:
                session = await self._get_session()

                # Build URL with optional request_id filter
                url = f"{self.base_url}/telemetry/stream"
                params = {}
                if request_id:
                    params["request_id"] = request_id

                log.info(f"Connecting to telemetry stream (attempt {retry_count + 1})")

                async with session.get(url, params=params) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise ConnectionError(f"HTTP {response.status}: {error_text}")

                    log.info("Telemetry stream connected")
                    retry_count = 0  # Reset retry count on successful connection

                    # Read SSE stream
                    async for line in response.content:
                        line_str = line.decode("utf-8").strip()

                        if not line_str:
                            continue

                        if line_str.startswith(":"):
                            # Heartbeat or comment
                            continue

                        if line_str.startswith("data: "):
                            data_str = line_str[6:]  # Remove "data: " prefix

                            try:
                                data = json.loads(data_str)
                                event = TelemetryEvent(**data)
                                self._notify_handlers(event)
                                yield event

                            except json.JSONDecodeError as e:
                                log.warning(f"Failed to parse telemetry data: {e}")
                            except Exception as e:
                                log.error(f"Failed to create TelemetryEvent: {e}")

            except asyncio.CancelledError:
                log.info("Telemetry stream cancelled")
                raise

            except Exception as e:
                log.error(f"Telemetry stream error: {e}")

                if retry_count < self.max_retries:
                    retry_count += 1
                    wait_time = self.retry_delay * (2 ** (retry_count - 1))
                    log.info(f"Reconnecting to telemetry in {wait_time}s (attempt {retry_count}/{self.max_retries})")
                    await asyncio.sleep(wait_time)
                else:
                    log.error(f"Max telemetry retries ({self.max_retries}) exceeded")
                    raise

    async def get_request_events(self, request_id: str) -> dict[str, Any]:
        """
        Get all telemetry events for a specific request.

        Args:
            request_id: Request ID

        Returns:
            Dictionary with events data
        """
        try:
            session = await self._get_session()
            async with session.get(
                f"{self.base_url}/telemetry/requests/{request_id}"
            ) as response:
                if response.status == 200:
                    return await response.json()
                else:
                    error_text = await response.text()
                    raise ConnectionError(f"HTTP {response.status}: {error_text}")
        except Exception as e:
            log.error(f"Failed to get request telemetry: {e}")
            raise
