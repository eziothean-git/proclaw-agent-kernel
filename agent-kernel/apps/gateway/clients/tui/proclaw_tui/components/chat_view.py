"""Chat view component for displaying messages."""

from datetime import datetime
from typing import Optional

from rich.console import RenderableType
from rich.markdown import Markdown
from rich.panel import Panel
from rich.text import Text
from textual.reactive import reactive
from textual.widgets import RichLog

from proclaw_tui.client.events import ChatStreamEvent, EventType


class Message:
    """A single message in the conversation."""

    def __init__(
        self,
        role: str,
        content: str,
        timestamp: Optional[datetime] = None,
        status: Optional[str] = None,
    ):
        self.role = role  # "user", "assistant", "system", "error"
        self.content = content
        self.timestamp = timestamp or datetime.now()
        self.status = status  # For assistant messages: "thinking", "completed", etc.

    def to_rich(self) -> RenderableType:
        """Convert message to rich renderable."""
        # Role icon
        icons = {
            "user": "👤",
            "assistant": "🤖",
            "system": "⚙️",
            "error": "❌",
        }
        icon = icons.get(self.role, "💬")

        # Format content based on role
        if self.role == "assistant":
            # Try to render as markdown
            try:
                content = Markdown(self.content)
            except Exception:
                content = Text(self.content)
        else:
            content = Text(self.content)

        # Build header
        time_str = self.timestamp.strftime("%H:%M:%S")
        header = Text(f"{icon} {time_str}", style="dim")

        if self.status:
            header.append(f" [{self.status}]", style="yellow italic")

        # Combine
        return Panel(
            content,
            title=header,
            border_style=self._get_border_style(),
        )

    def _get_border_style(self) -> str:
        """Get border style based on role."""
        styles = {
            "user": "blue",
            "assistant": "green",
            "system": "dim",
            "error": "red",
        }
        return styles.get(self.role, "white")


class ChatView(RichLog):
    """Widget for displaying chat messages."""

    DEFAULT_CSS = """
    ChatView {
        width: 100%;
        height: 1fr;
        border: solid green;
        padding: 1;
    }
    """

    messages: reactive[list[Message]] = reactive(list)

    def __init__(self, **kwargs):
        super().__init__(highlight=True, markup=True, **kwargs)
        self.messages = []
        self._current_assistant_message: Optional[Message] = None

    def add_user_message(self, content: str) -> None:
        """Add a user message."""
        msg = Message(role="user", content=content)
        self.messages.append(msg)
        self.write(msg.to_rich())

    def start_assistant_message(self) -> None:
        """Start a new assistant message with 'thinking' status."""
        msg = Message(role="assistant", content="", status="thinking...")
        self._current_assistant_message = msg
        self.messages.append(msg)
        self.write(msg.to_rich())

    def update_assistant_status(self, status: str) -> None:
        """Update the status of the current assistant message."""
        if self._current_assistant_message:
            self._current_assistant_message.status = status
            self.refresh_messages()

    def complete_assistant_message(self, content: str) -> None:
        """Complete the current assistant message with final content."""
        if self._current_assistant_message:
            self._current_assistant_message.content = content
            self._current_assistant_message.status = None
            self.refresh_messages()
            self._current_assistant_message = None

    def add_system_message(self, content: str) -> None:
        """Add a system message."""
        msg = Message(role="system", content=content)
        self.messages.append(msg)
        self.write(msg.to_rich())

    def add_error_message(self, content: str) -> None:
        """Add an error message."""
        msg = Message(role="error", content=content)
        self.messages.append(msg)
        self.write(msg.to_rich())

    def refresh_messages(self) -> None:
        """Refresh all messages display."""
        self.clear()
        for msg in self.messages:
            self.write(msg.to_rich())

    def clear_messages(self) -> None:
        """Clear all messages."""
        self.messages = []
        self._current_assistant_message = None
        self.clear()

    def handle_event(self, event: ChatStreamEvent) -> None:
        """Handle a chat stream event."""
        if event.type == EventType.ACCEPTED:
            self.start_assistant_message()

        elif event.type == EventType.STATUS:
            if event.status:
                status_text = event.status.value
                if event.status.value == "processing":
                    status_text = "processing..."
                self.update_assistant_status(status_text)

        elif event.type == EventType.COMPLETE:
            if event.response and "body" in event.response:
                body = event.response["body"]
                if isinstance(body, dict) and "response" in body:
                    content = body["response"]
                else:
                    content = str(body)
                self.complete_assistant_message(content)
            else:
                self.complete_assistant_message("(No response content)")

        elif event.type == EventType.ERROR:
            error_msg = event.error or "Unknown error"
            if self._current_assistant_message:
                self._current_assistant_message.status = "error"
                self._current_assistant_message.content = f"Error: {error_msg}"
                self.refresh_messages()
                self._current_assistant_message = None
            else:
                self.add_error_message(error_msg)
