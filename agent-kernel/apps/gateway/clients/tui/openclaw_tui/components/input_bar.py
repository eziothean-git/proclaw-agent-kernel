"""Input bar component for message entry."""

from textual.containers import Horizontal
from textual.message import Message
from textual.widgets import Button, Input, Static


class InputBar(Static):
    """Input bar with text entry and send button."""

    DEFAULT_CSS = """
    InputBar {
        height: auto;
        dock: bottom;
        padding: 1;
        background: $surface;
    }

    InputBar > Horizontal {
        height: auto;
    }

    InputBar Input {
        width: 1fr;
    }

    InputBar Button {
        width: auto;
        margin-left: 1;
    }
    """

    def compose(self):
        """Compose the input bar."""
        with Horizontal():
            yield Input(
                placeholder="输入消息或命令 (/help 查看帮助)...",
                id="message_input",
            )
            yield Button("发送", id="send_button", variant="primary")

    def on_mount(self):
        """Focus input on mount."""
        self.query_one("#message_input", Input).focus()

    def get_input_value(self) -> str:
        """Get current input value."""
        return self.query_one("#message_input", Input).value

    def clear_input(self) -> None:
        """Clear the input field."""
        self.query_one("#message_input", Input).value = ""

    def set_input_value(self, value: str) -> None:
        """Set input value."""
        self.query_one("#message_input", Input).value = value

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle input submission."""
        if event.value.strip():
            self.post_message(self.InputSubmitted(event.value))
            self.clear_input()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle send button press."""
        if event.button.id == "send_button":
            value = self.get_input_value()
            if value.strip():
                self.post_message(self.InputSubmitted(value))
                self.clear_input()

    class InputSubmitted(Message):
        """Message sent when user submits input."""

        def __init__(self, value: str) -> None:
            self.value = value
            super().__init__()
