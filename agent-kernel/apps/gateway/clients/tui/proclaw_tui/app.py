"""Main TUI application for ProClaw."""

import asyncio
from typing import Optional

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Footer, Header, Static

from proclaw_tui.client.events import ConnectionState, ConnectionStatus, EventType
from proclaw_tui.client.gateway_client import GatewayClient
from proclaw_tui.components.chat_view import ChatView
from proclaw_tui.components.input_bar import InputBar
from proclaw_tui.components.status_bar import StatusBar
from proclaw_tui.components.system_panel import SystemPanel


class ProClawApp(App):
    """ProClaw Terminal UI Application."""

    CSS = """
    Screen {
        align: center middle;
    }
    
    #main_container {
        width: 100%;
        height: 100%;
    }
    
    #content_area {
        width: 1fr;
        height: 1fr;
    }
    
    #sidebar {
        width: 30;
        height: 100%;
        dock: right;
        background: $surface-darken-1;
    }
    
    ChatView {
        height: 1fr;
        border: solid $primary;
    }
    
    SystemPanel {
        height: auto;
        max-height: 50%;
    }
    
    StatusBar {
        height: auto;
    }
    
    InputBar {
        height: auto;
    }
    """

    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
        ("ctrl+r", "refresh", "Refresh"),
        ("ctrl+s", "toggle_sidebar", "Toggle Sidebar"),
        ("f1", "show_help", "Help"),
    ]

    current_session_id: reactive[Optional[str]] = reactive(None)

    def __init__(
        self,
        gateway_url: str = "http://localhost:3000",
        user_id: str = "openclaw-user",
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.gateway_url = gateway_url
        self.user_id = user_id
        self.client = GatewayClient(
            base_url=gateway_url,
            user_id=user_id,
            max_retries=5,
            retry_delay=2.0,
        )
        self._health_check_task: Optional[asyncio.Task] = None
        self._sidebar_visible = True

    def compose(self) -> ComposeResult:
        """Compose the UI."""
        yield Header(show_clock=True, name="ProClaw Terminal")

        with Vertical(id="main_container"):
            with Horizontal(id="content_area"):
                with Vertical(id="chat_area"):
                    yield ChatView(id="chat_view")

                with Vertical(id="sidebar"):
                    yield SystemPanel(id="system_panel")

            yield StatusBar(id="status_bar")
            yield InputBar(id="input_bar")

        yield Footer()

    async def on_mount(self) -> None:
        """Initialize on mount."""
        # Start health check loop
        self._health_check_task = asyncio.create_task(self._health_check_loop())

        # Show welcome message
        chat_view = self.query_one("#chat_view", ChatView)
        chat_view.add_system_message(
            "🧠 欢迎来到 ProClaw Terminal!\n"
            "输入消息开始对话，或输入 /help 查看帮助。\n"
            "Gateway URL: " + self.gateway_url
        )

        # Check initial connection
        await self._check_connection()

    async def on_unmount(self) -> None:
        """Cleanup on unmount."""
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
        await self.client.close()

    async def _health_check_loop(self) -> None:
        """Periodically check Gateway health."""
        while True:
            try:
                await self._check_connection()
                await asyncio.sleep(5)  # Check every 5 seconds
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.log(f"Health check error: {e}")
                await asyncio.sleep(5)

    async def _check_connection(self) -> None:
        """Check Gateway connection and update UI."""
        health = await self.client.check_health()

        status_bar = self.query_one("#status_bar", StatusBar)
        system_panel = self.query_one("#system_panel", SystemPanel)

        status_bar.update_health_status(health)
        system_panel.update_health_status(health)
        system_panel.update_connection_status(self.client.connection_status)

    def on_input_bar_input_submitted(self, event: InputBar.InputSubmitted) -> None:
        """Handle user input."""
        value = event.value.strip()

        if not value:
            return

        # Handle commands
        if value.startswith("/"):
            self._handle_command(value)
        else:
            # Send message
            asyncio.create_task(self._send_message(value))

    def _handle_command(self, command: str) -> None:
        """Handle slash commands."""
        chat_view = self.query_one("#chat_view", ChatView)

        parts = command.split(maxsplit=1)
        cmd = parts[0].lower()
        args = parts[1] if len(parts) > 1 else ""

        if cmd == "/help":
            help_text = """
[bold]可用命令：[/bold]

[b]/help[/b]     - 显示此帮助信息
[b]/clear[/b]    - 清空对话历史
[b]/status[/b]   - 刷新系统状态
[b]/quit[/b]     - 退出程序

[bold]快捷键：[/bold]

Ctrl+C - 退出
Ctrl+R - 刷新状态
Ctrl+S - 切换侧边栏
F1     - 显示帮助

[bold]提示：[/bold]

• 直接输入消息与AI对话
• 会话由系统管理，无需手动创建
• 支持自动重连，网络恢复后会自动继续
            """
            chat_view.add_system_message(help_text)

        elif cmd == "/clear":
            chat_view.clear_messages()
            chat_view.add_system_message("对话历史已清空")

        elif cmd == "/status":
            asyncio.create_task(self._check_connection())
            chat_view.add_system_message("正在刷新系统状态...")

        elif cmd in ["/quit", "/exit", "/q"]:
            chat_view.add_system_message("正在退出...")
            asyncio.create_task(self._delayed_quit())

        else:
            chat_view.add_system_message(f"未知命令: {cmd}，输入 /help 查看帮助")

    async def _delayed_quit(self) -> None:
        """Quit after a short delay."""
        await asyncio.sleep(0.5)
        self.exit()

    async def _send_message(self, message: str) -> None:
        """Send a message and handle the response."""
        chat_view = self.query_one("#chat_view", ChatView)
        status_bar = self.query_one("#status_bar", StatusBar)
        system_panel = self.query_one("#system_panel", SystemPanel)

        # Display user message
        chat_view.add_user_message(message)

        # Update status
        status_bar.update_connection_status(self.client.connection_status)
        system_panel.update_connection_status(self.client.connection_status)

        # Send and receive events
        try:
            async for event in self.client.send_message(
                message=message,
                session_id=self.current_session_id,
            ):
                # Update connection status display
                status_bar.update_connection_status(self.client.connection_status)
                system_panel.update_connection_status(self.client.connection_status)

                # Handle event
                chat_view.handle_event(event)

                # Update session ID from accepted event
                if event.type == EventType.ACCEPTED and event.session_id:
                    self.current_session_id = event.session_id

        except asyncio.CancelledError:
            chat_view.add_error_message("请求已取消")
        except Exception as e:
            chat_view.add_error_message(f"请求失败: {e}")

    def action_refresh(self) -> None:
        """Refresh system status."""
        asyncio.create_task(self._check_connection())
        self.query_one("#chat_view", ChatView).add_system_message("系统状态已刷新")

    def action_toggle_sidebar(self) -> None:
        """Toggle sidebar visibility."""
        sidebar = self.query_one("#sidebar")
        self._sidebar_visible = not self._sidebar_visible
        sidebar.styles.display = "block" if self._sidebar_visible else "none"

    def action_show_help(self) -> None:
        """Show help."""
        self._handle_command("/help")
