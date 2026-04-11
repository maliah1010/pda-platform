"""PM-Financial tool registry for unified server aggregation."""

from __future__ import annotations

from typing import Any

from mcp.types import TextContent

from .server import FINANCIAL_TOOLS as TOOLS  # noqa: F401 — re-exported for unified server
from .server import (
    _get_cost_performance,
    _get_spend_profile,
    _log_cost_forecast,
    _log_financial_actuals,
    _set_financial_baseline,
)

_DISPATCH = {
    "set_financial_baseline": _set_financial_baseline,
    "log_financial_actuals": _log_financial_actuals,
    "get_cost_performance": _get_cost_performance,
    "log_cost_forecast": _log_cost_forecast,
    "get_spend_profile": _get_spend_profile,
}


async def dispatch(name: str, arguments: Any) -> list[TextContent]:
    """Dispatch a pm-financial tool call. Handlers already return list[TextContent]."""
    handler = _DISPATCH.get(name)
    if handler is not None:
        return await handler(arguments)
    return [TextContent(type="text", text=f"Unknown tool: {name}")]
