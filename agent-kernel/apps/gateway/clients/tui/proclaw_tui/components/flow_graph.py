"""Flow graph component displaying the 7-layer architecture progress."""

from datetime import datetime
from typing import Optional

from rich.align import Align
from rich.console import RenderableType
from rich.panel import Panel
from rich.style import Style
from rich.text import Text
from textual.reactive import reactive
from textual.widgets import Static

from proclaw_tui.client.events import FlowLayerState, FlowState, TelemetryEvent


# Layer definitions
LAYERS = {
    1: {"name": "Gateway", "short": "Gateway"},
    2: {"name": "Request Manager", "short": "Request Manager"},
    3: {"name": "Prime Personality", "short": "Prime Personality"},
    4: {"name": "OS Interface", "short": "Agentic OS Interface"},
    5: {"name": "Session Host", "short": "Session Host"},
    6: {"name": "Agent Thread", "short": "Agent Thread"},
    7: {"name": "Memory", "short": "Long-term Memory"},
}


class FlowGraph(Static):
    """Widget displaying the 7-layer flow graph with current progress."""

    DEFAULT_CSS = """
    FlowGraph {
        width: 100%;
        height: auto;
        padding: 0;
    }
    """

    flow_state: reactive[FlowState] = reactive(
        FlowState(request_id="", current_layer=1)
    )
    _layer_states: reactive[dict[int, FlowLayerState]] = reactive({})

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._pending_layer_states = self._create_layer_states()

    def _create_layer_states(self) -> dict[int, FlowLayerState]:
        """Create initial layer states."""
        return {
            layer: FlowLayerState(layer=layer, name=LAYERS[layer]["short"])
            for layer in range(1, 8)
        }

    def compose(self):
        """Compose the widget."""
        yield Static(id="flow_content")

    def on_mount(self) -> None:
        """Initialize layer states on mount."""
        self._layer_states = self._pending_layer_states
        self.update_content()

    def watch_flow_state(self, state: FlowState) -> None:
        """React to flow state changes."""
        self.update_content()

    def watch__layer_states(self, states: dict[int, FlowLayerState]) -> None:
        """React to layer state changes."""
        self.update_content()

    def update_content(self) -> None:
        """Update the flow graph display."""
        try:
            content = self.query_one("#flow_content", Static)
            rendered = self._render_flow()
            content.update(rendered)
        except Exception as e:
            # Component not ready yet, skip update
            pass

    def _render_flow(self) -> RenderableType:
        """Render the complete flow graph."""
        lines = []
        
        # Header
        lines.append(Text("处理流程", style="bold cyan"))
        lines.append(Text(""))
        
        # Render each layer
        for layer_num in range(1, 8):
            layer_text = self._render_layer_text(layer_num)
            lines.append(layer_text)
            
            # Add arrow if not the last layer
            if layer_num < 7:
                lines.append(Text("    ↓", style="grey50"))
        
        return Panel(
            Align.left(Text("\n").join(lines)),
            border_style="grey50",
            padding=(0, 1),
        )

    def _render_layer_text(self, layer_num: int) -> Text:
        """Render a single layer as text with styling."""
        layer_info = LAYERS[layer_num]
        layer_state = self._layer_states.get(layer_num)
        
        if not layer_state:
            layer_state = FlowLayerState(layer=layer_num, name=layer_info["short"])
        
        # Determine status indicator
        is_current = layer_num == self.flow_state.current_layer
        is_completed = layer_state.status == "completed"
        is_error = layer_state.status == "error"
        
        if is_current:
            icon = "🟢"
            style = "bold green"
        elif is_error:
            icon = "❌"
            style = "red"
        elif is_completed:
            icon = "✓"
            style = "dim"
        else:
            icon = "○"
            style = "grey50"
        
        # Build line
        name = layer_info["name"]
        line_text = f"{icon} {name}"
        
        # Add step info for active Agent Thread
        if is_current and layer_num == 6:
            details = layer_state.details
            if details.get("step") is not None:
                line_text += f" (Step {details['step']}/{details.get('total_steps', '?')})"
            if details.get("phase"):
                line_text += f" [{details['phase'].upper()}]"
        
        return Text(line_text, style=style)

    def update_telemetry(self, event: TelemetryEvent) -> None:
        """Update flow state based on telemetry event."""
        layer_num = event.layer
        
        # Update layer state
        if layer_num not in self._layer_states:
            self._layer_states[layer_num] = FlowLayerState(
                layer=layer_num, name=LAYERS[layer_num]["short"]
            )
        
        layer_state = self._layer_states[layer_num]
        
        # Update status
        if event.status == "start":
            layer_state.status = "active"
            layer_state.started_at = event.timestamp
            self.flow_state.current_layer = layer_num
        elif event.status == "complete":
            layer_state.status = "completed"
            layer_state.completed_at = event.timestamp
            if layer_state.started_at:
                from datetime import datetime
                layer_state.duration_ms = int(
                    (event.timestamp - layer_state.started_at).total_seconds() * 1000
                )
        elif event.status == "error":
            layer_state.status = "error"
        
        # Update details for Agent Thread
        if layer_num == 6:
            layer_state.details.update({
                "step": event.step,
                "total_steps": event.total_steps,
                "phase": event.phase,
                "operation": event.operation,
            })
        
        self.update_content()

    def reset(self, request_id: str) -> None:
        """Reset flow graph for a new request."""
        self.flow_state = FlowState(request_id=request_id, current_layer=1)
        self._pending_layer_states = self._create_layer_states()
        self._layer_states = self._pending_layer_states
        self.update_content()

    def get_layer_details(self, layer: int) -> Optional[FlowLayerState]:
        """Get details for a specific layer."""
        return self._layer_states.get(layer)
