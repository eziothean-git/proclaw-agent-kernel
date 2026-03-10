"""System panel component for displaying system information."""

from datetime import datetime
from typing import Any, Optional

from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from textual.containers import Vertical
from textual.reactive import reactive
from textual.widgets import Static

from openclaw_tui.client.events import ConnectionState, ConnectionStatus, HealthStatus


class SystemPanel(Static):
    """Panel displaying system status and statistics."""

    DEFAULT_CSS = """
    SystemPanel {
        width: 100%;
        height: auto;
        padding: 0;
        background: $surface;
    }
    
    SystemPanel .panel-title {
        text-align: center;
        text-style: bold;
    }
    """

    connection_status: reactive[ConnectionStatus] = reactive(
        ConnectionStatus(state=ConnectionState.DISCONNECTED)
    )
    health_status: reactive[Optional[HealthStatus]] = reactive(None)
    system_info: reactive[dict[str, Any]] = reactive(dict)

    def compose(self):
        """Compose the system panel."""
        yield Static(id="system_content")

    def watch_connection_status(self, status: ConnectionStatus) -> None:
        """React to connection status changes."""
        self.update_content()

    def watch_health_status(self, status: Optional[HealthStatus]) -> None:
        """React to health status changes."""
        self.update_content()

    def watch_system_info(self, info: dict[str, Any]) -> None:
        """React to system info changes."""
        self.update_content()

    def update_content(self) -> None:
        """Update the panel content."""
        content = self.query_one("#system_content", Static)

        # Build info table
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column("Key", style="dim", width=12)
        table.add_column("Value")

        # Connection status
        conn_state = self.connection_status.state.value
        conn_style = {
            ConnectionState.CONNECTED: "green",
            ConnectionState.CONNECTING: "yellow",
            ConnectionState.DISCONNECTED: "red",
            ConnectionState.ERROR: "red",
            ConnectionState.RECONNECTING: "yellow",
        }.get(self.connection_status.state, "white")
        table.add_row("Connection:", Text(conn_state, style=conn_style))

        # Gateway health
        if self.health_status:
            health_icon = "✓" if self.health_status.status == "healthy" else "✗"
            health_style = "green" if self.health_status.status == "healthy" else "red"
            table.add_row(
                "Gateway:", Text(f"{health_icon} {self.health_status.status}", style=health_style)
            )
            table.add_row("Version:", self.health_status.version)
            table.add_row("Storage:", self.health_status.storage)
        else:
            table.add_row("Gateway:", Text("--", style="dim"))

        # Reconnection info
        if self.connection_status.state == ConnectionState.RECONNECTING:
            table.add_row(
                "Retry:",
                Text(f"{self.connection_status.reconnect_attempts} attempts", style="yellow"),
            )

        # Last error
        if self.connection_status.last_error:
            table.add_row("Error:", Text(self.connection_status.last_error[:50], style="red"))

        # System info
        if self.system_info:
            table.add_row("", "")  # Spacer
            for key, value in self.system_info.items():
                if isinstance(value, dict):
                    table.add_row(f"{key}:", str(value.get("status", "--")))
                else:
                    table.add_row(f"{key}:", str(value))

        panel = Panel(
            table,
            title="[bold]System Status[/bold]",
            title_align="center",
            border_style="dim",
            padding=(0, 1),
        )

        content.update(panel)

    def update_connection_status(self, status: ConnectionStatus) -> None:
        """Update connection status."""
        self.connection_status = status

    def update_health_status(self, status: Optional[HealthStatus]) -> None:
        """Update health status."""
        self.health_status = status

    def update_system_info(self, info: dict[str, Any]) -> None:
        """Update system information."""
        self.system_info = info
