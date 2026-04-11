"""PM-Resource tool registry for unified server aggregation."""

from __future__ import annotations

from typing import Any

from mcp.types import TextContent

from .server import RESOURCE_TOOLS as TOOLS  # noqa: F401 — re-exported for unified server
from .server import (
    _analyse_resource_loading,
    _detect_resource_conflicts,
    _get_critical_resources,
    _get_portfolio_capacity,
    _log_resource_plan,
)

_DISPATCH = {
    "analyse_resource_loading": _analyse_resource_loading,
    "detect_resource_conflicts": _detect_resource_conflicts,
    "get_critical_resources": _get_critical_resources,
    "log_resource_plan": _log_resource_plan,
    "get_portfolio_capacity": _get_portfolio_capacity,
}


async def dispatch(name: str, arguments: Any) -> list[TextContent]:
    """Dispatch a pm-resource tool call. Handlers already return list[TextContent]."""
    handler = _DISPATCH.get(name)
    if handler is not None:
        return await handler(arguments)
    return [TextContent(type="text", text=f"Unknown tool: {name}")]
