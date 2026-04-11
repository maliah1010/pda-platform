"""PM-EV tool registry for unified server aggregation."""

from __future__ import annotations

from typing import Any

from mcp.types import TextContent

from .server import EV_TOOLS as TOOLS  # noqa: F401 — re-exported for unified server
from .server import (
    _compute_ev_metrics,
    _generate_ev_dashboard,
)

_DISPATCH = {
    "compute_ev_metrics": _compute_ev_metrics,
    "generate_ev_dashboard": _generate_ev_dashboard,
}


async def dispatch(name: str, arguments: Any) -> list[TextContent]:
    """Dispatch a pm-ev tool call. Handlers already return list[TextContent]."""
    handler = _DISPATCH.get(name)
    if handler is not None:
        return await handler(arguments)
    return [TextContent(type="text", text=f"Unknown tool: {name}")]
