"""PM Assure MCP Server.

Provides MCP tools for assurance quality tracking including longitudinal
compliance score trend analysis and review action lifecycle management.
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
            name="nista_longitudinal_trend",
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
            name="track_review_actions",
            description=(
                "Extract review actions from project review text, persist "
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
                            "Confidence threshold below which review actions "
                            "are flagged for human review (default 0.60)."
                        ),
                        "default": 0.60,
                    },
                },
                "required": ["review_text", "review_id", "project_id"],
            },
        ),
        Tool(
            name="review_action_status",
            description=(
                "Retrieve tracked review actions for a project, optionally "
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
        Tool(
            name="check_artefact_currency",
            description=(
                "Assess whether project artefacts are current against a gate "
                "date.  Detects stale documents and last-minute compliance "
                "updates made suspiciously close to the gate."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "artefacts": {
                        "type": "array",
                        "description": (
                            "List of artefact descriptors.  Each must have "
                            "``id`` (str), ``type`` (str), and "
                            "``last_modified`` (ISO-8601 string or datetime)."
                        ),
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "type": {"type": "string"},
                                "last_modified": {"type": "string"},
                            },
                            "required": ["id", "type", "last_modified"],
                        },
                    },
                    "gate_date": {
                        "type": "string",
                        "description": "ISO-8601 gate date to assess currency against.",
                    },
                    "max_staleness_days": {
                        "type": "integer",
                        "description": "Days before gate after which an artefact is OUTDATED (default 90).",
                        "default": 90,
                    },
                    "anomaly_window_days": {
                        "type": "integer",
                        "description": (
                            "Updates this close to the gate date are flagged as "
                            "ANOMALOUS_UPDATE (default 3)."
                        ),
                        "default": 3,
                    },
                },
                "required": ["artefacts", "gate_date"],
            },
        ),
        Tool(
            name="check_confidence_divergence",
            description=(
                "Assess AI extraction confidence for a project review.  "
                "Detects high sample divergence, low consensus, and degrading "
                "confidence trends across review cycles."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "Project identifier.",
                    },
                    "review_id": {
                        "type": "string",
                        "description": "Unique identifier for the review.",
                    },
                    "confidence_score": {
                        "type": "number",
                        "description": "Overall consensus confidence score (0–1).",
                    },
                    "sample_scores": {
                        "type": "array",
                        "items": {"type": "number"},
                        "description": "Individual per-sample confidence scores.",
                    },
                    "divergence_threshold": {
                        "type": "number",
                        "description": "Max acceptable sample spread (default 0.20).",
                        "default": 0.20,
                    },
                    "min_consensus": {
                        "type": "number",
                        "description": "Minimum acceptable consensus score (default 0.60).",
                        "default": 0.60,
                    },
                    "db_path": {
                        "type": "string",
                        "description": (
                            "Optional path to the SQLite store.  "
                            "Defaults to ~/.pm_data_tools/store.db"
                        ),
                    },
                },
                "required": ["project_id", "review_id", "confidence_score", "sample_scores"],
            },
        ),
    ]


# ---------------------------------------------------------------------------
# Tool dispatch
# ---------------------------------------------------------------------------


@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Handle tool execution."""
    if name == "nista_longitudinal_trend":
        return await _nista_longitudinal_trend(arguments)
    if name == "track_review_actions":
        return await _track_review_actions(arguments)
    if name == "review_action_status":
        return await _review_action_status(arguments)
    if name == "check_artefact_currency":
        return await _check_artefact_currency(arguments)
    if name == "check_confidence_divergence":
        return await _check_confidence_divergence(arguments)
    return [TextContent(type="text", text=f"Unknown tool: {name}")]


# ---------------------------------------------------------------------------
# Implementations
# ---------------------------------------------------------------------------


async def _nista_longitudinal_trend(arguments: dict[str, Any]) -> list[TextContent]:
    """Return compliance score history, trend, and active breaches."""
    try:
        from pm_data_tools.db.store import AssuranceStore
        from pm_data_tools.schemas.nista.longitudinal import LongitudinalComplianceTracker

        project_id: str = arguments["project_id"]
        raw_db_path = arguments.get("db_path")
        db_path = Path(raw_db_path) if raw_db_path else None

        store = AssuranceStore(db_path=db_path)
        tracker = LongitudinalComplianceTracker(store=store)

        records = tracker.get_history(project_id)
        trend = tracker.compute_trend(project_id)
        breaches = tracker.check_thresholds(project_id)

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


async def _track_review_actions(
    arguments: dict[str, Any],
) -> list[TextContent]:
    """Extract and persist review actions from project review text."""
    try:
        import anthropic as _anthropic_module  # noqa: F401 — import check

        from agent_planning.confidence import ConfidenceExtractor
        from agent_planning.providers.anthropic import AnthropicProvider
        from pm_data_tools.assurance import FindingAnalyzer

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

        analyzer = FindingAnalyzer(
            extractor=ce,
            min_confidence=float(arguments.get("min_confidence", 0.60)),
        )

        result = await analyzer.extract(
            review_text=arguments["review_text"],
            review_id=arguments["review_id"],
            project_id=arguments["project_id"],
        )

        output: dict[str, Any] = {
            "extraction_confidence": result.extraction_confidence,
            "review_level": result.review_level,
            "cost_usd": result.cost_usd,
            "review_actions": [
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


async def _review_action_status(
    arguments: dict[str, Any],
) -> list[TextContent]:
    """Return current review actions for a project."""
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
            "review_actions": rows,
        }

        return [
            TextContent(
                type="text",
                text=json.dumps(output, indent=2, default=str),
            )
        ]

    except Exception as exc:
        return [TextContent(type="text", text=f"Error: {exc}")]


async def _check_artefact_currency(
    arguments: dict[str, Any],
) -> list[TextContent]:
    """Assess artefact currency against a gate date."""
    try:
        from datetime import datetime, timezone

        from pm_data_tools.assurance.currency import (
            ArtefactCurrencyValidator,
            CurrencyConfig,
        )

        gate_date = datetime.fromisoformat(arguments["gate_date"])
        if gate_date.tzinfo is None:
            gate_date = gate_date.replace(tzinfo=timezone.utc)

        config = CurrencyConfig(
            max_staleness_days=int(arguments.get("max_staleness_days", 90)),
            anomaly_window_days=int(arguments.get("anomaly_window_days", 3)),
        )
        validator = ArtefactCurrencyValidator(config=config)

        results = validator.check_batch(
            artefacts=arguments["artefacts"],
            gate_date=gate_date,
        )

        summary: dict[str, Any] = {
            "gate_date": gate_date.isoformat(),
            "total": len(results),
            "current": sum(1 for r in results if r.status.value == "CURRENT"),
            "outdated": sum(1 for r in results if r.status.value == "OUTDATED"),
            "anomalous_update": sum(
                1 for r in results if r.status.value == "ANOMALOUS_UPDATE"
            ),
            "artefacts": [
                {
                    "artefact_id": r.artefact_id,
                    "artefact_type": r.artefact_type,
                    "status": r.status.value,
                    "staleness_days": r.staleness_days,
                    "anomaly_window_days": r.anomaly_window_days,
                    "message": r.message,
                }
                for r in results
            ],
        }

        return [
            TextContent(
                type="text",
                text=json.dumps(summary, indent=2, default=str),
            )
        ]

    except Exception as exc:
        return [TextContent(type="text", text=f"Error: {exc}")]


async def _check_confidence_divergence(
    arguments: dict[str, Any],
) -> list[TextContent]:
    """Assess AI confidence divergence for a review."""
    try:
        from pathlib import Path

        from pm_data_tools.assurance.divergence import DivergenceConfig, DivergenceMonitor
        from pm_data_tools.db.store import AssuranceStore

        raw_db_path = arguments.get("db_path")
        db_path = Path(raw_db_path) if raw_db_path else None
        store = AssuranceStore(db_path=db_path)

        config = DivergenceConfig(
            divergence_threshold=float(arguments.get("divergence_threshold", 0.20)),
            min_consensus=float(arguments.get("min_consensus", 0.60)),
        )
        monitor = DivergenceMonitor(config=config, store=store)

        result = monitor.check(
            project_id=arguments["project_id"],
            review_id=arguments["review_id"],
            confidence_score=float(arguments["confidence_score"]),
            sample_scores=[float(s) for s in arguments["sample_scores"]],
        )

        output: dict[str, Any] = {
            "project_id": result.project_id,
            "review_id": result.review_id,
            "confidence_score": result.confidence_score,
            "sample_scores": result.sample_scores,
            "signal_type": result.signal.signal_type.value,
            "spread": result.signal.spread,
            "previous_confidence": result.signal.previous_confidence,
            "message": result.signal.message,
            "snapshot_id": result.snapshot_id,
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
