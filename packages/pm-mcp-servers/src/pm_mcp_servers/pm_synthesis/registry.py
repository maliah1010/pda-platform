"""PM-Synthesis tool registry for unified server aggregation."""

from __future__ import annotations

from typing import Any

from mcp.types import TextContent

from .server import SYNTHESIS_TOOLS as TOOLS  # noqa: F401 — re-exported for unified server
from .server import (
    _compare_project_health,
    _summarise_project_health,
)

_DISPATCH = {
    "summarise_project_health": _summarise_project_health,
    "compare_project_health": _compare_project_health,
}


async def dispatch(name: str, arguments: Any) -> list[TextContent]:
    """Dispatch a pm-synthesis tool call. Handlers already return list[TextContent]."""
    handler = _DISPATCH.get(name)
    if handler is not None:
        return await handler(arguments)
    return [TextContent(type="text", text=f"Unknown tool: {name}")]
