"""PM Assure MCP Server.

Provides MCP tools for assurance quality tracking including NISTA compliance
score trend analysis and recommendation lifecycle management.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

from mcp.server import Server
from mcp.types import TextContent, Tool

app = Server("pm-assure-server")


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available PM Assure tools."""
    return [
        Tool(
            name="nista_score_trend",
            description=(
                "Retrieve NISTA compliance score history, trend direction, and "
                "active threshold breaches for a project."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "The project identifier to query.",
                    },
                    "db_path": {
                        "type": "string",
                        "description": (
                            "Optional path to the SQLite store.  "
                            "Defaults to ~/.pm_data_tools/store.db"
                        ),
                    },
                },
                "required": ["project_id"],
            },
        ),
        Tool(
            name="track_recommendations",
            description=(
                "Extract assurance recommendations from review text, persist "
                "them to the store, and detect any recurrences from prior cycles."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "review_text": {
                        "type": "string",
                        "description": "Full text of the project review document.",
                    },
                    "review_id": {
                        "type": "string",
                        "description": "Unique identifier for this review.",
                    },
                    "project_id": {
                        "type": "string",
                        "description": "Project identifier.",
                    },
                    "min_confidence": {
                        "type": "number",
                        "description": (
                            "Confidence threshold below which recommendations "
                            "are flagged for human review (default 0.60)."
                        ),
                        "default": 0.60,
                    },
                },
                "required": ["review_text", "review_id", "project_id"],
            },
        ),
        Tool(
            name="recommendation_status",
            description=(
                "Retrieve tracked recommendations for a project, optionally "
                "filtered by status.  Returns recurrence flags."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "Project identifier.",
                    },
                    "status_filter": {
                        "type": "string",
                        "enum": ["OPEN", "IN_PROGRESS", "CLOSED", "RECURRING"],
                        "description": "Optional status to filter by.",
                    },
                },
                "required": ["project_id"],
            },
        ),
    ]


# ---------------------------------------------------------------------------
# Tool dispatch
# ---------------------------------------------------------------------------


@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool execution."""
    if name == "nista_score_trend":
        return await _nista_score_trend(arguments)
    if name == "track_recommendations":
        return await _track_recommendations(arguments)
    if name == "recommendation_status":
        return await _recommendation_status(arguments)
    return [TextContent(type="text", text=f"Unknown tool: {name}")]


# ---------------------------------------------------------------------------
# Implementations
# ---------------------------------------------------------------------------


async def _nista_score_trend(arguments: dict[str, Any]) -> list[TextContent]:
    """Return compliance score history, trend, and active breaches."""
    try:
        from pm_data_tools.db.store import AssuranceStore
        from pm_data_tools.schemas.nista.history import NISTAScoreHistory

        project_id: str = arguments["project_id"]
        raw_db_path = arguments.get("db_path")
        db_path = Path(raw_db_path) if raw_db_path else None

        store = AssuranceStore(db_path=db_path)
        history = NISTAScoreHistory(store=store)

        records = history.get_history(project_id)
        trend = history.compute_trend(project_id)
        breaches = history.check_thresholds(project_id)

        output: dict[str, Any] = {
            "project_id": project_id,
            "history": [
                {
                    "run_id": r.run_id,
                    "timestamp": r.timestamp.isoformat(),
                    "score": r.score,
                    "dimension_scores": r.dimension_scores,
                }
                for r in records
            ],
            "trend": trend.value,
            "active_breaches": [
                {
                    "breach_type": b.breach_type,
                    "current_score": b.current_score,
                    "previous_score": b.previous_score,
                    "threshold_value": b.threshold_value,
                    "message": b.message,
                }
                for b in breaches
            ],
        }

        return [
            TextContent(
                type="text",
                text=json.dumps(output, indent=2, default=str),
            )
        ]

    except Exception as exc:
        return [TextContent(type="text", text=f"Error: {exc}")]


async def _track_recommendations(
    arguments: dict[str, Any],
) -> list[TextContent]:
    """Extract and persist recommendations from review text."""
    try:
        import anthropic as _anthropic_module  # noqa: F401 — import check

        from agent_planning.confidence import ConfidenceExtractor
        from agent_planning.providers.anthropic import AnthropicProvider
        from pm_data_tools.assurance import RecommendationExtractor

        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            return [
                TextContent(
                    type="text",
                    text="Error: ANTHROPIC_API_KEY environment variable not set.",
                )
            ]

        provider = AnthropicProvider(api_key=api_key)
        ce = ConfidenceExtractor(provider)

        extractor = RecommendationExtractor(
            extractor=ce,
            min_confidence=float(arguments.get("min_confidence", 0.60)),
        )

        result = await extractor.extract(
            review_text=arguments["review_text"],
            review_id=arguments["review_id"],
            project_id=arguments["project_id"],
        )

        output: dict[str, Any] = {
            "extraction_confidence": result.extraction_confidence,
            "review_level": result.review_level,
            "cost_usd": result.cost_usd,
            "recommendations": [
                {
                    "id": r.id,
                    "text": r.text,
                    "category": r.category,
                    "status": r.status.value,
                    "owner": r.owner,
                    "confidence": r.confidence,
                    "flagged_for_review": r.flagged_for_review,
                    "recurrence_of": r.recurrence_of,
                }
                for r in result.recommendations
            ],
        }

        return [
            TextContent(
                type="text",
                text=json.dumps(output, indent=2, default=str),
            )
        ]

    except Exception as exc:
        return [TextContent(type="text", text=f"Error: {exc}")]


async def _recommendation_status(
    arguments: dict[str, Any],
) -> list[TextContent]:
    """Return current recommendations for a project."""
    try:
        from pm_data_tools.db.store import AssuranceStore

        project_id: str = arguments["project_id"]
        status_filter: str | None = arguments.get("status_filter")

        store = AssuranceStore()
        rows = store.get_recommendations(
            project_id=project_id,
            status_filter=status_filter,
        )

        output: dict[str, Any] = {
            "project_id": project_id,
            "status_filter": status_filter,
            "count": len(rows),
            "recommendations": rows,
        }

        return [
            TextContent(
                type="text",
                text=json.dumps(output, indent=2, default=str),
            )
        ]

    except Exception as exc:
        return [TextContent(type="text", text=f"Error: {exc}")]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the pm-assure MCP server."""
    import mcp.server.stdio

    async def arun() -> None:
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await app.run(
                read_stream,
                write_stream,
                app.create_initialization_options(),
            )

    asyncio.run(arun())


if __name__ == "__main__":  # pragma: no cover
    main()
