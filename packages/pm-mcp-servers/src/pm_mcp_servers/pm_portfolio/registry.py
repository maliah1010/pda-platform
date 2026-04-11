"""PM-Portfolio tool registry for unified server aggregation."""

from __future__ import annotations

from typing import Any

from mcp.types import TextContent

from .server import PORTFOLIO_TOOLS as TOOLS  # noqa: F401 — re-exported for unified server
from .server import (
    _get_portfolio_armm_summary,
    _get_portfolio_assumptions_risk,
    _get_portfolio_brm_overview,
    _get_portfolio_gate_readiness,
    _get_portfolio_health,
)

_DISPATCH = {
    "get_portfolio_health": _get_portfolio_health,
    "get_portfolio_gate_readiness": _get_portfolio_gate_readiness,
    "get_portfolio_brm_overview": _get_portfolio_brm_overview,
    "get_portfolio_armm_summary": _get_portfolio_armm_summary,
    "get_portfolio_assumptions_risk": _get_portfolio_assumptions_risk,
}


async def dispatch(name: str, arguments: Any) -> list[TextContent]:
    """Dispatch a pm-portfolio tool call. Handlers already return list[TextContent]."""
    handler = _DISPATCH.get(name)
    if handler is not None:
        return await handler(arguments)
    return [TextContent(type="text", text=f"Unknown tool: {name}")]
