"""Main TUI application for ProClaw."""

import asyncio
from typing import Optional

from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import Footer, Header, Static

from proclaw_tui.client.events import (
    ConnectionState,
    ConnectionStatus,
    EventType,
    TelemetryEvent,
)
from proclaw_tui.client.gateway_client import GatewayClient
from proclaw_tui.client.telemetry_client import TelemetryClient
from proclaw_tui.components.activity_panel import ActivityPanel
from proclaw_tui.components.chat_view import ChatView
from proclaw_tui.components.flow_graph import FlowGraph
from proclaw_tui.components.input_bar import InputBar


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
    
    /* Left panel - Chat history */
    #left_panel {
        width: 60%;
        height: 1fr;
        border-right: solid $primary;
    }
    
    ChatView {
        width: 100%;
        height: 100%;
        border: none;
    }
    
    /* Right panel - Flow graph */
    #right_panel {
        width: 40%;
        height: 100%;
        background: $surface-darken-1;
    }

    #flow_graph_container {
        width: 100%;
        height: 75%;
        overflow: auto;
    }

    #activity_panel_container {
        width: 100%;
        height: 25%;
        border-top: solid $primary;
    }

    FlowGraph {
        width: 100%;
        height: auto;
        min-height: 100%;
    }

    ActivityPanel {
        width: 100%;
        height: 100%;
    }
    
    /* Bottom bar */
    #bottom_bar {
        height: auto;
        border-top: solid $primary;
    }
    
    InputBar {
        width: 100%;
        height: auto;
    }
    
    /* Footer info line */
    #footer_info {
        height: auto;
        padding: 0 1;
        background: $surface-darken-2;
        color: $text-muted;
        text-style: dim;
    }
    """

    BINDINGS = [
        ("ctrl+c", "quit", "Quit"),
        ("ctrl+r", "refresh", "Refresh"),
        ("f1", "show_help", "Help"),
    ]

    current_session_id: reactive[Optional[str]] = reactive(None)
    current_request_id: reactive[Optional[str]] = reactive(None)

    def __init__(
        self,
        gateway_url: str = "http://localhost:3000",
        user_id: str = "proclaw-user",
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
        # Telemetry client connects directly to Python Kernel
        kernel_url = kwargs.get('kernel_url', 'http://localhost:8000')
        self.telemetry_client = TelemetryClient(
            base_url=kernel_url,
            max_retries=3,
            retry_delay=2.0,
        )
        self._health_check_task: Optional[asyncio.Task] = None
        self._telemetry_task: Optional[asyncio.Task] = None

    def compose(self) -> ComposeResult:
        """Compose the UI with new layout."""
        yield Header(show_clock=True, name="ProClaw Terminal")

        with Vertical(id="main_container"):
            # Main content area - split horizontally
            with Horizontal(id="content_area"):
                # Left side - Chat history (60%)
                with Vertical(id="left_panel"):
                    yield ChatView(id="chat_view")

                # Right side - Flow graph + Activity (40%)
                with Vertical(id="right_panel"):
                    # Use Static containers to fix layout
                    with Static(id="flow_graph_container"):
                        yield FlowGraph(id="flow_graph")
                    with Static(id="activity_panel_container"):
                        yield ActivityPanel(id="activity_panel")

            # Bottom - Input bar
            with Vertical(id="bottom_bar"):
                yield InputBar(id="input_bar")
                # Footer info line
                yield Static(
                    f"🌐 {self.gateway_url} ● connecting...",
                    id="footer_info",
                )

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
            f"Gateway URL: {self.gateway_url}"
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
        if self._telemetry_task:
            self._telemetry_task.cancel()
            try:
                await self._telemetry_task
            except asyncio.CancelledError:
                pass
        await self.client.close()
        await self.telemetry_client.close()

    async def _health_check_loop(self) -> None:
        """Periodically check Gateway health."""
        while True:
            try:
                await self._check_connection()
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.log(f"Health check error: {e}")
                await asyncio.sleep(5)

    async def _check_connection(self) -> None:
        """Check Gateway connection and update UI."""
        health = await self.client.check_health()
        footer_info = self.query_one("#footer_info", Static)

        if health:
            conn_status = "🟢 connected" if self.client.connection_status.state == ConnectionState.CONNECTED else "🟡 connecting"
            footer_info.update(
                f"🌐 {self.gateway_url} ● {conn_status} │ "
                f"v{health.version} │ Storage: {health.storage}"
            )
        else:
            footer_info.update(
                f"🌐 {self.gateway_url} ● 🔴 disconnected │ "
                f"Health check failed"
            )

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
[b]/reset[/b]    - 重置流程图
[b]/quit[/b]     - 退出程序

[bold]快捷键：[/bold]

Ctrl+C - 退出
Ctrl+R - 刷新状态
F1     - 显示帮助

[bold]界面说明：[/bold]

• 左侧：对话历史记录
• 右上角：处理流程图（实时高亮当前层）
• 右下角：当前活动详情
• 底部：系统连接信息
            """
            chat_view.add_system_message(help_text)

        elif cmd == "/clear":
            chat_view.clear_messages()
            chat_view.add_system_message("对话历史已清空")

        elif cmd == "/status":
            asyncio.create_task(self._check_connection())
            chat_view.add_system_message("正在刷新系统状态...")

        elif cmd == "/reset":
            flow_graph = self.query_one("#flow_graph", FlowGraph)
            activity_panel = self.query_one("#activity_panel", ActivityPanel)
            if self.current_request_id:
                flow_graph.reset(self.current_request_id)
            activity_panel.clear()
            chat_view.add_system_message("流程图已重置")

        elif cmd in ["/quit", "/exit", "/q"]:
            chat_view.add_system_message("正在退出...")
            asyncio.create_task(self._delayed_quit())

        else:
            chat_view.add_system_message(f"未知命令: {cmd}，输入 /help 查看帮助")

    async def _delayed_quit(self) -> None:
        """Quit after a short delay."""
        await asyncio.sleep(0.5)
        self.exit()

    async def _handle_telemetry_stream(self, request_id: str) -> None:
        """Handle telemetry events streaming from Python Kernel."""
        flow_graph = self.query_one("#flow_graph", FlowGraph)
        activity_panel = self.query_one("#activity_panel", ActivityPanel)
        
        try:
            async for telemetry_event in self.telemetry_client.stream_telemetry(request_id):
                # Update flow graph and activity panel
                flow_graph.update_telemetry(telemetry_event)
                activity_panel.update_telemetry(telemetry_event)
        except asyncio.CancelledError:
            # Stream cancelled, expected when request completes
            pass
        except Exception as e:
            self.log(f"Telemetry stream error: {e}")

    async def _send_message(self, message: str) -> None:
        """Send a message and handle the response."""
        chat_view = self.query_one("#chat_view", ChatView)
        flow_graph = self.query_one("#flow_graph", FlowGraph)
        activity_panel = self.query_one("#activity_panel", ActivityPanel)

        # Display user message
        chat_view.add_user_message(message)

        # Reset flow graph for new request
        flow_graph.reset("pending")
        activity_panel.clear()

        # Send and receive events
        telemetry_task: asyncio.Task | None = None
        try:
            async for event in self.client.send_message(
                message=message,
                session_id=self.current_session_id,
            ):
                # Update footer connection status
                await self._check_connection()

                # Handle event
                chat_view.handle_event(event)

                # Update session ID from accepted event
                if event.type == EventType.ACCEPTED and event.session_id:
                    self.current_session_id = event.session_id
                    self.current_request_id = event.request_id
                    flow_graph.reset(event.request_id)
                    
                    # Start telemetry stream for this request
                    if telemetry_task:
                        telemetry_task.cancel()
                        try:
                            await telemetry_task
                        except asyncio.CancelledError:
                            pass
                    telemetry_task = asyncio.create_task(
                        self._handle_telemetry_stream(event.request_id)
                    )

        except asyncio.CancelledError:
            chat_view.add_error_message("请求已取消")
        finally:
            # Clean up telemetry task
            if telemetry_task:
                telemetry_task.cancel()
                try:
                    await telemetry_task
                except asyncio.CancelledError:
                    pass

    def action_refresh(self) -> None:
        """Refresh system status."""
        asyncio.create_task(self._check_connection())
        self.query_one("#chat_view", ChatView).add_system_message("系统状态已刷新")

    def action_show_help(self) -> None:
        """Show help."""
        self._handle_command("/help")
