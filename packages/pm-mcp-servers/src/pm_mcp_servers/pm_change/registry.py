"""PM-Change tool registry for unified server aggregation."""

from __future__ import annotations

from typing import Any

from mcp.types import TextContent

from .server import CHANGE_TOOLS as TOOLS  # noqa: F401 — re-exported for unified server
from .server import (
    _analyse_change_pressure,
    _get_change_impact_summary,
    _get_change_log,
    _log_change_request,
    _update_change_status,
)

_DISPATCH = {
    "log_change_request": _log_change_request,
    "update_change_status": _update_change_status,
    "get_change_log": _get_change_log,
    "get_change_impact_summary": _get_change_impact_summary,
    "analyse_change_pressure": _analyse_change_pressure,
}


async def dispatch(name: str, arguments: Any) -> list[TextContent]:
    """Dispatch a pm-change tool call. Handlers already return list[TextContent]."""
    handler = _DISPATCH.get(name)
    if handler is not None:
        return await handler(arguments)
    return [TextContent(type="text", text=f"Unknown tool: {name}")]
