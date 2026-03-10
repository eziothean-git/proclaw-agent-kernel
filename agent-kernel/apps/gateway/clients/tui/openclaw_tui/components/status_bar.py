"""Status bar component for connection and system status."""

from datetime import datetime
from typing import Optional

from rich.text import Text
from textual.reactive import reactive
from textual.widgets import Static

from openclaw_tui.client.events import ConnectionState, ConnectionStatus, HealthStatus


class StatusBar(Static):
    """Status bar showing connection and system information."""

    DEFAULT_CSS = """
    StatusBar {
        height: auto;
        dock: bottom;
        padding: 0 1;
        background: $surface-darken-1;
        color: $text;
    }
    """

    connection_status: reactive[ConnectionStatus] = reactive(
        ConnectionStatus(state=ConnectionState.DISCONNECTED)
    )
    health_status: reactive[Optional[HealthStatus]] = reactive(None)
    last_update: reactive[datetime] = reactive(datetime.now())

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.update_status_display()

    def watch_connection_status(self, status: ConnectionStatus) -> None:
        """React to connection status changes."""
        self.update_status_display()

    def watch_health_status(self, status: Optional[HealthStatus]) -> None:
        """React to health status changes."""
        self.update_status_display()

    def update_status_display(self) -> None:
        """Update the status display."""
        # Connection indicator
        conn_style = {
            ConnectionState.CONNECTED: "green",
            ConnectionState.CONNECTING: "yellow",
            ConnectionState.DISCONNECTED: "red",
            ConnectionState.ERROR: "red",
            ConnectionState.RECONNECTING: "yellow",
        }.get(self.connection_status.state, "white")

        conn_icon = {
            ConnectionState.CONNECTED: "●",
            ConnectionState.CONNECTING: "◐",
            ConnectionState.DISCONNECTED: "○",
            ConnectionState.ERROR: "✗",
            ConnectionState.RECONNECTING: "↻",
        }.get(self.connection_status.state, "?")

        conn_text = Text(f"{conn_icon} {self.connection_status.state.value}", style=conn_style)

        # Gateway health
        if self.health_status:
            gw_style = "green" if self.health_status.status == "healthy" else "red"
            gw_text = Text(f"GW: {self.health_status.version}", style=gw_style)
        else:
            gw_text = Text("GW: --", style="dim")

        # Reconnection info
        if self.connection_status.state == ConnectionState.RECONNECTING:
            retry_text = Text(f"Retry: {self.connection_status.reconnect_attempts}", style="yellow")
        else:
            retry_text = Text("")

        # Combine
        status_line = Text()
        status_line.append(conn_text)
        status_line.append("  |  ")
        status_line.append(gw_text)

        if retry_text.plain:
            status_line.append("  |  ")
            status_line.append(retry_text)

        # Add help hint
        status_line.append("  |  ", style="dim")
        status_line.append("/help", style="blue")

        self.update(status_line)

    def update_connection_status(self, status: ConnectionStatus) -> None:
        """Update connection status."""
        self.connection_status = status
        self.last_update = datetime.now()

    def update_health_status(self, status: Optional[HealthStatus]) -> None:
        """Update health status."""
        self.health_status = status
        self.last_update = datetime.now()
