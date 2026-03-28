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
        Tool(
            name="recommend_review_schedule",
            description=(
                "Generate an adaptive review scheduling recommendation for a "
                "project by analysing its P1–P4 assurance signals.  Returns "
                "urgency, recommended date, composite score, and rationale."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "Project identifier.",
                    },
                    "last_review_date": {
                        "type": "string",
                        "description": "ISO-8601 date of the most recent review (optional).",
                    },
                    "artefacts": {
                        "type": "array",
                        "description": (
                            "Optional artefact list for P1 currency check.  "
                            "Each requires ``id``, ``type``, ``last_modified``."
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
                        "description": "ISO-8601 gate date for the P1 currency check.",
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
            name="log_override_decision",
            description=(
                "Log a governance override decision — e.g. proceeding past a "
                "failed gate, dismissing a recommendation, or accepting a risk.  "
                "Captures the full context: authoriser, rationale, conditions, "
                "and evidence references."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "Project identifier.",
                    },
                    "override_type": {
                        "type": "string",
                        "enum": [
                            "GATE_PROGRESSION",
                            "RECOMMENDATION_DISMISSED",
                            "RAG_OVERRIDE",
                            "RISK_ACCEPTANCE",
                            "SCHEDULE_OVERRIDE",
                        ],
                        "description": "Category of the override.",
                    },
                    "decision_date": {
                        "type": "string",
                        "description": "ISO-8601 date of the override decision.",
                    },
                    "authoriser": {
                        "type": "string",
                        "description": "Who authorised the override.",
                    },
                    "rationale": {
                        "type": "string",
                        "description": "Why the override was approved.",
                    },
                    "overridden_finding_id": {
                        "type": "string",
                        "description": "Optional link to a P3 ReviewAction id, gate, or RAG reference.",
                    },
                    "overridden_value": {
                        "type": "string",
                        "description": "What the assurance advice was (e.g. 'RED').",
                    },
                    "override_value": {
                        "type": "string",
                        "description": "What was decided instead (e.g. 'Proceed with conditions').",
                    },
                    "conditions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Conditions attached to the override.",
                    },
                    "evidence_refs": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Document references supporting the decision.",
                    },
                    "db_path": {
                        "type": "string",
                        "description": "Optional path to the SQLite store.",
                    },
                },
                "required": [
                    "project_id",
                    "override_type",
                    "decision_date",
                    "authoriser",
                    "rationale",
                ],
            },
        ),
        Tool(
            name="analyse_override_patterns",
            description=(
                "Analyse the governance override history for a project.  "
                "Returns total overrides, breakdown by type and outcome, "
                "impact rate, and top authorisers."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "Project identifier.",
                    },
                    "db_path": {
                        "type": "string",
                        "description": "Optional path to the SQLite store.",
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
    if name == "recommend_review_schedule":
        return await _recommend_review_schedule(arguments)
    if name == "log_override_decision":
        return await _log_override_decision(arguments)
    if name == "analyse_override_patterns":
        return await _analyse_override_patterns(arguments)
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


async def _recommend_review_schedule(
    arguments: dict[str, Any],
) -> list[TextContent]:
    """Generate an adaptive review scheduling recommendation."""
    try:
        from datetime import date, datetime, timezone
        from pathlib import Path

        from pm_data_tools.assurance.currency import ArtefactCurrencyValidator
        from pm_data_tools.assurance.divergence import (
            DivergenceResult,
            DivergenceSignal,
            SignalType,
        )
        from pm_data_tools.assurance.scheduler import AdaptiveReviewScheduler
        from pm_data_tools.db.store import AssuranceStore
        from pm_data_tools.schemas.nista.longitudinal import LongitudinalComplianceTracker

        project_id: str = arguments["project_id"]
        raw_db_path = arguments.get("db_path")
        db_path = Path(raw_db_path) if raw_db_path else None
        store = AssuranceStore(db_path=db_path)

        # Parse optional last_review_date
        last_review_date: date | None = None
        raw_lrd = arguments.get("last_review_date")
        if raw_lrd:
            last_review_date = date.fromisoformat(str(raw_lrd))

        # P1 — artefact currency
        currency_scores = None
        if arguments.get("artefacts") and arguments.get("gate_date"):
            gate_date = datetime.fromisoformat(str(arguments["gate_date"]))
            if gate_date.tzinfo is None:
                gate_date = gate_date.replace(tzinfo=timezone.utc)
            validator = ArtefactCurrencyValidator()
            currency_scores = validator.check_batch(
                artefacts=arguments["artefacts"],
                gate_date=gate_date,
            )

        # P2 — compliance trend
        tracker = LongitudinalComplianceTracker(store=store)
        trend = tracker.compute_trend(project_id)
        breaches = tracker.check_thresholds(project_id)

        # P3 — review action counts
        all_actions = store.get_recommendations(project_id=project_id)
        total_actions = len(all_actions)
        open_actions = sum(1 for a in all_actions if a.get("status") == "OPEN")
        recurring_actions = sum(
            1 for a in all_actions if a.get("status") == "RECURRING"
        )

        # P4 — latest divergence snapshot
        divergence_result: DivergenceResult | None = None
        snapshots = store.get_divergence_history(project_id)
        if snapshots:
            latest = snapshots[-1]
            sig_type = SignalType(str(latest["signal_type"]))
            divergence_result = DivergenceResult(
                project_id=str(latest["project_id"]),
                review_id=str(latest["review_id"]),
                confidence_score=float(latest["confidence_score"]),  # type: ignore[arg-type]
                sample_scores=latest["sample_scores"],  # type: ignore[arg-type]
                signal=DivergenceSignal(
                    signal_type=sig_type,
                    project_id=str(latest["project_id"]),
                    review_id=str(latest["review_id"]),
                    confidence_score=float(latest["confidence_score"]),  # type: ignore[arg-type]
                    spread=0.0,
                    previous_confidence=None,
                    message="",
                ),
                snapshot_id=str(latest["id"]),
            )

        scheduler = AdaptiveReviewScheduler(store=store)
        rec = scheduler.recommend(
            project_id=project_id,
            last_review_date=last_review_date,
            currency_scores=currency_scores,
            trend=trend,
            breaches=breaches,
            open_actions=open_actions if total_actions > 0 else None,
            total_actions=total_actions if total_actions > 0 else None,
            recurring_actions=recurring_actions if total_actions > 0 else None,
            divergence_result=divergence_result,
        )

        output: dict[str, Any] = {
            "project_id": rec.project_id,
            "urgency": rec.urgency.value,
            "recommended_date": rec.recommended_date.isoformat(),
            "days_until_review": rec.days_until_review,
            "composite_score": rec.composite_score,
            "rationale": rec.rationale,
            "signals": [
                {
                    "source": s.source,
                    "signal_name": s.signal_name,
                    "severity": s.severity,
                    "detail": s.detail,
                }
                for s in rec.signals
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


async def _log_override_decision(
    arguments: dict[str, Any],
) -> list[TextContent]:
    """Log a governance override decision."""
    try:
        from datetime import date
        from pathlib import Path

        from pm_data_tools.assurance.overrides import (
            OverrideDecision,
            OverrideDecisionLogger,
            OverrideOutcome,
            OverrideType,
        )
        from pm_data_tools.db.store import AssuranceStore

        raw_db_path = arguments.get("db_path")
        db_path = Path(raw_db_path) if raw_db_path else None
        store = AssuranceStore(db_path=db_path)

        decision = OverrideDecision(
            project_id=arguments["project_id"],
            override_type=OverrideType(arguments["override_type"]),
            decision_date=date.fromisoformat(str(arguments["decision_date"])),
            authoriser=arguments["authoriser"],
            rationale=arguments["rationale"],
            overridden_finding_id=arguments.get("overridden_finding_id"),
            overridden_value=arguments.get("overridden_value"),
            override_value=arguments.get("override_value"),
            conditions=list(arguments.get("conditions", [])),
            evidence_refs=list(arguments.get("evidence_refs", [])),
        )

        log_obj = OverrideDecisionLogger(store=store)
        logged = log_obj.log_override(decision)

        output: dict[str, Any] = {
            "id": logged.id,
            "project_id": logged.project_id,
            "override_type": logged.override_type.value,
            "decision_date": logged.decision_date.isoformat(),
            "authoriser": logged.authoriser,
            "outcome": logged.outcome.value,
            "message": f"Override decision logged with id '{logged.id}'.",
        }

        return [
            TextContent(
                type="text",
                text=json.dumps(output, indent=2, default=str),
            )
        ]

    except Exception as exc:
        return [TextContent(type="text", text=f"Error: {exc}")]


async def _analyse_override_patterns(
    arguments: dict[str, Any],
) -> list[TextContent]:
    """Return override pattern summary for a project."""
    try:
        from pathlib import Path

        from pm_data_tools.assurance.overrides import OverrideDecisionLogger
        from pm_data_tools.db.store import AssuranceStore

        raw_db_path = arguments.get("db_path")
        db_path = Path(raw_db_path) if raw_db_path else None
        store = AssuranceStore(db_path=db_path)

        project_id: str = arguments["project_id"]
        log_obj = OverrideDecisionLogger(store=store)
        summary = log_obj.analyse_patterns(project_id)

        output: dict[str, Any] = {
            "project_id": summary.project_id,
            "total_overrides": summary.total_overrides,
            "by_type": summary.by_type,
            "by_outcome": summary.by_outcome,
            "pending_outcomes": summary.pending_outcomes,
            "impact_rate": summary.impact_rate,
            "top_authorisers": summary.top_authorisers,
            "message": summary.message,
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
