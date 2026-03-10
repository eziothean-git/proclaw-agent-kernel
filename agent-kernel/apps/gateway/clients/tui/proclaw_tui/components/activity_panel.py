"""Activity panel component displaying current operation details."""

from datetime import datetime
from typing import Any, Optional, Union

from rich.console import Group, RenderableType
from rich.panel import Panel
from rich.progress import BarColumn, Progress, TextColumn
from rich.table import Table
from rich.text import Text
from textual.reactive import reactive
from textual.widgets import Static

from proclaw_tui.client.events import TelemetryEvent


class ActivityPanel(Static):
    """Panel displaying current activity details and progress."""

    DEFAULT_CSS = """
    ActivityPanel {
        width: 100%;
        height: auto;
        padding: 0;
        background: $surface;
    }
    """

    current_event: reactive[Optional[TelemetryEvent]] = reactive(None)
    start_time: reactive[Optional[datetime]] = reactive(None)

    def compose(self):
        """Compose the activity panel."""
        yield Static(id="activity_content")

    def watch_current_event(self, event: Optional[TelemetryEvent]) -> None:
        """React to current event changes."""
        self.update_content()

    def update_content(self) -> None:
        """Update the panel content."""
        content = self.query_one("#activity_content", Static)
        content.update(self._render_activity())

    def _render_activity(self) -> RenderableType:
        """Render the current activity display."""
        if not self.current_event:
            return Panel(
                Text("等待请求...", style="dim", justify="center"),
                title="[bold]当前活动[/bold]",
                border_style="dim",
            )

        event = self.current_event

        # Build main info table
        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("Key", style="dim cyan", width=12)
        table.add_column("Value")

        # Layer and Component
        table.add_row(
            "层:",
            Text(f"L{event.layer} · {event.layer_name}", style="cyan bold"),
        )
        table.add_row("组件:", event.component)

        # Current operation
        if event.operation:
            table.add_row("操作:", Text(event.operation, style="yellow"))

        # Phase (for Agent Thread)
        if event.phase:
            table.add_row("阶段:", Text(event.phase.upper(), style="magenta"))

        # Message/description
        if event.message:
            table.add_row("")
            table.add_row("详情:", Text(event.message, style="italic"))

        # Collect all renderable elements
        elements: list[RenderableType] = [table]

        # Progress bar
        if event.progress_pct is not None:
            progress = Progress(
                TextColumn("[progress.description]{task.description}"),
                BarColumn(bar_width=40),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                expand=False,
            )
            progress.add_task("", total=100, completed=int(event.progress_pct))
            elements.append(progress)
        elif event.step is not None and event.total_steps:
            progress = Progress(
                TextColumn("[progress.description]{task.description}"),
                BarColumn(bar_width=40),
                TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
                expand=False,
            )
            pct = int((event.step / event.total_steps) * 100)
            progress.add_task(f"Step {event.step}/{event.total_steps}", total=100, completed=pct)
            elements.append(progress)
            elements.append(progress)

        # Timing info
        if event.elapsed_ms is not None:
            elapsed_sec = event.elapsed_ms / 1000
            if event.estimated_ms:
                est_sec = event.estimated_ms / 1000
                timing_text = Text(
                    f"已用时: {elapsed_sec:.1f}s / 预估: {est_sec:.1f}s",
                    style="dim",
                )
            else:
                timing_text = Text(f"已用时: {elapsed_sec:.1f}s", style="dim")
            elements.append(timing_text)

        # Additional details
        if event.details:
            details_table = Table(show_header=False, box=None, padding=(0, 1))
            details_table.add_column("", style="dim", width=2)
            details_table.add_column("Key", style="dim", width=14)
            details_table.add_column("Value")

            for key, value in event.details.items():
                if key not in ["step", "total_steps", "phase"]:  # Skip already displayed
                    display_value = str(value)
                    if len(display_value) > 60:
                        display_value = display_value[:57] + "..."
                    details_table.add_row("", f"{key}:", display_value)

            if details_table.rows:
                elements.append(details_table)

        return Panel(
            Group(*elements),
            title="[bold]当前活动[/bold]",
            border_style="cyan",
            padding=(0, 1),
        )

    def update_telemetry(self, event: TelemetryEvent) -> None:
        """Update current activity based on telemetry event."""
        if event.status == "start":
            self.start_time = event.timestamp

        self.current_event = event
        self.update_content()

    def clear(self) -> None:
        """Clear the activity panel."""
        self.current_event = None
        self.start_time = None
        self.update_content()
