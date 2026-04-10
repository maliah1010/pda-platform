"""PM-Portfolio MCP server — cross-project portfolio aggregation tools (P15).

Tools:
  1. get_portfolio_health           — Aggregate compliance scores, health and open actions
  2. get_portfolio_gate_readiness   — Aggregate gate readiness assessments across projects
  3. get_portfolio_brm_overview     — Aggregate benefits realisation data across projects
  4. get_portfolio_armm_summary     — Aggregate ARMM maturity assessments across projects
  5. get_portfolio_assumptions_risk — Aggregate assumption drift severity across projects
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mcp.types import TextContent, Tool

# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

PORTFOLIO_TOOLS: list[Tool] = [
    Tool(
        name="get_portfolio_health",
        description=(
            "Aggregate compliance scores, workflow health, and open action counts "
            "across multiple projects. Returns per-project latest compliance score, "
            "health status, and open action count, plus portfolio-level averages and "
            "distributions."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "project_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of project IDs to aggregate.",
                },
                "db_path": {
                    "type": "string",
                    "description": (
                        "Optional path to the SQLite store. "
                        "Defaults to ~/.pm_data_tools/store.db"
                    ),
                },
            },
            "required": ["project_ids"],
        },
    ),
    Tool(
        name="get_portfolio_gate_readiness",
        description=(
            "Aggregate gate readiness assessments across multiple projects. "
            "Returns per-project latest readiness level and composite score, "
            "plus portfolio summary counts by readiness level."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "project_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of project IDs to aggregate.",
                },
                "gate": {
                    "type": "string",
                    "description": (
                        "Optional gate type filter (e.g. 'GATE_2'). "
                        "When supplied, only assessments for this gate are considered."
                    ),
                },
                "db_path": {
                    "type": "string",
                    "description": (
                        "Optional path to the SQLite store. "
                        "Defaults to ~/.pm_data_tools/store.db"
                    ),
                },
            },
            "required": ["project_ids"],
        },
    ),
    Tool(
        name="get_portfolio_brm_overview",
        description=(
            "Aggregate benefits realisation data across multiple projects. "
            "Returns per-project benefit counts, status breakdown, and target/realised "
            "value totals, plus portfolio-wide totals."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "project_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of project IDs to aggregate.",
                },
                "db_path": {
                    "type": "string",
                    "description": (
                        "Optional path to the SQLite store. "
                        "Defaults to ~/.pm_data_tools/store.db"
                    ),
                },
            },
            "required": ["project_ids"],
        },
    ),
    Tool(
        name="get_portfolio_armm_summary",
        description=(
            "Aggregate ARMM maturity assessments across multiple projects. "
            "Returns per-project latest overall maturity level and score, plus "
            "portfolio average score and distribution by maturity level."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "project_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of project IDs to aggregate.",
                },
                "db_path": {
                    "type": "string",
                    "description": (
                        "Optional path to the SQLite store. "
                        "Defaults to ~/.pm_data_tools/store.db"
                    ),
                },
            },
            "required": ["project_ids"],
        },
    ),
    Tool(
        name="get_portfolio_assumptions_risk",
        description=(
            "Aggregate assumption drift severity across multiple projects. "
            "Returns per-project assumption counts and drift severity breakdown, "
            "plus portfolio totals and a list of projects with CRITICAL drift."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "project_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "List of project IDs to aggregate.",
                },
                "db_path": {
                    "type": "string",
                    "description": (
                        "Optional path to the SQLite store. "
                        "Defaults to ~/.pm_data_tools/store.db"
                    ),
                },
            },
            "required": ["project_ids"],
        },
    ),
]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_store(arguments: dict[str, Any]) -> Any:
    """Create an AssuranceStore from optional db_path argument."""
    from pm_data_tools.db.store import AssuranceStore

    raw_db_path = arguments.get("db_path")
    db_path = Path(raw_db_path) if raw_db_path else None
    return AssuranceStore(db_path=db_path)


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


async def _get_portfolio_health(arguments: dict[str, Any]) -> list[TextContent]:
    """Aggregate compliance scores, health, and open actions across projects."""
    try:
        store = _get_store(arguments)
        project_ids: list[str] = arguments["project_ids"]

        projects: list[dict[str, Any]] = []
        total_score = 0.0
        scored_count = 0
        total_open_actions = 0
        by_health: dict[str, int] = {}
        no_data_count = 0

        for pid in project_ids:
            scores = store.get_confidence_scores(pid)
            latest_score: float | None = None
            health: str | None = None

            if scores:
                latest = scores[-1]
                latest_score = latest.get("score")
                health = latest.get("health")
                if latest_score is not None:
                    total_score += latest_score
                    scored_count += 1
            else:
                no_data_count += 1

            open_actions = store.get_recommendations(pid, status_filter="OPEN")
            recurring_actions = store.get_recommendations(pid, status_filter="RECURRING")
            open_count = len(open_actions) + len(recurring_actions)
            total_open_actions += open_count

            workflows = store.get_workflow_history(pid)
            workflow_health: str | None = None
            if workflows:
                workflow_health = workflows[-1].get("health")

            effective_health = workflow_health or health or "UNKNOWN"
            by_health[effective_health] = by_health.get(effective_health, 0) + 1

            projects.append({
                "project_id": pid,
                "latest_compliance_score": (
                    round(latest_score, 2) if latest_score is not None else None
                ),
                "health": health,
                "workflow_health": workflow_health,
                "open_action_count": open_count,
                "has_data": bool(scores),
            })

        avg_compliance = (
            round(total_score / scored_count, 2) if scored_count else None
        )

        output = {
            "project_count": len(project_ids),
            "projects": projects,
            "portfolio": {
                "average_compliance_score": avg_compliance,
                "by_health": by_health,
                "total_open_actions": total_open_actions,
                "projects_with_no_data": no_data_count,
            },
        }

        return [TextContent(type="text", text=json.dumps(output, indent=2, default=str))]

    except Exception as exc:
        return [TextContent(type="text", text=f"Error: {exc}")]


async def _get_portfolio_gate_readiness(
    arguments: dict[str, Any],
) -> list[TextContent]:
    """Aggregate gate readiness assessments across projects."""
    try:
        store = _get_store(arguments)
        project_ids: list[str] = arguments["project_ids"]
        gate_filter: str | None = arguments.get("gate")

        projects: list[dict[str, Any]] = []
        by_readiness: dict[str, int] = {}

        for pid in project_ids:
            history = store.get_gate_readiness_history(pid, gate=gate_filter)

            if history:
                latest = history[-1]
                readiness = latest.get("readiness")
                composite_score = latest.get("composite_score")
                gate = latest.get("gate")
                assessed_at = latest.get("assessed_at")
                by_readiness[readiness] = by_readiness.get(readiness, 0) + 1
            else:
                readiness = None
                composite_score = None
                gate = None
                assessed_at = None
                by_readiness["INSUFFICIENT_DATA"] = (
                    by_readiness.get("INSUFFICIENT_DATA", 0) + 1
                )

            projects.append({
                "project_id": pid,
                "gate": gate,
                "readiness": readiness,
                "composite_score": (
                    round(composite_score, 2)
                    if composite_score is not None
                    else None
                ),
                "assessed_at": assessed_at,
            })

        output = {
            "project_count": len(project_ids),
            "gate_filter": gate_filter,
            "projects": projects,
            "portfolio": {
                "by_readiness": by_readiness,
            },
        }

        return [TextContent(type="text", text=json.dumps(output, indent=2, default=str))]

    except Exception as exc:
        return [TextContent(type="text", text=f"Error: {exc}")]


async def _get_portfolio_brm_overview(
    arguments: dict[str, Any],
) -> list[TextContent]:
    """Aggregate benefits realisation data across projects."""
    try:
        store = _get_store(arguments)
        project_ids: list[str] = arguments["project_ids"]

        projects: list[dict[str, Any]] = []
        portfolio_total_benefits = 0
        portfolio_total_target_value = 0.0
        portfolio_total_realised_value = 0.0
        portfolio_by_status: dict[str, int] = {}

        for pid in project_ids:
            benefits = store.get_benefits(pid)

            benefit_count = len(benefits)
            by_status: dict[str, int] = {}
            total_target = 0.0
            total_realised = 0.0

            for b in benefits:
                status = b.get("status", "UNKNOWN")
                by_status[status] = by_status.get(status, 0) + 1

                tv = b.get("target_value")
                if isinstance(tv, (int, float)):
                    total_target += tv

                cv = b.get("current_value")
                if isinstance(cv, (int, float)):
                    total_realised += cv

            portfolio_total_benefits += benefit_count
            portfolio_total_target_value += total_target
            portfolio_total_realised_value += total_realised

            for status, count in by_status.items():
                portfolio_by_status[status] = (
                    portfolio_by_status.get(status, 0) + count
                )

            projects.append({
                "project_id": pid,
                "benefit_count": benefit_count,
                "by_status": by_status,
                "total_target_value": round(total_target, 2),
                "total_realised_value": round(total_realised, 2),
            })

        output = {
            "project_count": len(project_ids),
            "projects": projects,
            "portfolio": {
                "total_benefits": portfolio_total_benefits,
                "by_status": portfolio_by_status,
                "total_target_value": round(portfolio_total_target_value, 2),
                "total_realised_value": round(portfolio_total_realised_value, 2),
            },
        }

        return [TextContent(type="text", text=json.dumps(output, indent=2, default=str))]

    except Exception as exc:
        return [TextContent(type="text", text=f"Error: {exc}")]


async def _get_portfolio_armm_summary(
    arguments: dict[str, Any],
) -> list[TextContent]:
    """Aggregate ARMM maturity assessments across projects."""
    try:
        store = _get_store(arguments)
        project_ids: list[str] = arguments["project_ids"]

        projects: list[dict[str, Any]] = []
        scored_scores: list[float] = []
        by_level: dict[int, int] = {}

        for pid in project_ids:
            assessments = store.get_armm_assessments(pid)

            if assessments:
                latest = assessments[-1]
                overall_level: int | None = latest.get("overall_level")
                overall_score_pct: float | None = latest.get("overall_score_pct")
                assessed_at: str | None = latest.get("assessed_at")

                if overall_score_pct is not None:
                    scored_scores.append(overall_score_pct)
                if overall_level is not None:
                    by_level[overall_level] = by_level.get(overall_level, 0) + 1
            else:
                overall_level = None
                overall_score_pct = None
                assessed_at = None

            projects.append({
                "project_id": pid,
                "overall_level": overall_level,
                "overall_score_pct": (
                    round(overall_score_pct, 1)
                    if overall_score_pct is not None
                    else None
                ),
                "assessed_at": assessed_at,
            })

        avg_score = (
            round(sum(scored_scores) / len(scored_scores), 1)
            if scored_scores
            else None
        )

        output = {
            "project_count": len(project_ids),
            "projects": projects,
            "portfolio": {
                "average_score_pct": avg_score,
                "by_level": {str(k): v for k, v in sorted(by_level.items())},
                "projects_with_no_data": sum(
                    1 for p in projects if p["overall_level"] is None
                ),
            },
        }

        return [TextContent(type="text", text=json.dumps(output, indent=2, default=str))]

    except Exception as exc:
        return [TextContent(type="text", text=f"Error: {exc}")]


async def _get_portfolio_assumptions_risk(
    arguments: dict[str, Any],
) -> list[TextContent]:
    """Aggregate assumption drift severity across projects."""
    try:
        store = _get_store(arguments)
        project_ids: list[str] = arguments["project_ids"]

        _HIGH_CRITICAL = {"HIGH", "CRITICAL"}

        projects: list[dict[str, Any]] = []
        portfolio_total_assumptions = 0
        portfolio_high_critical_count = 0
        critical_projects: list[str] = []

        for pid in project_ids:
            assumptions = store.get_assumptions(pid)
            assumption_count = len(assumptions)
            portfolio_total_assumptions += assumption_count

            by_severity: dict[str, int] = {}
            project_high_critical = 0
            has_critical = False

            for assumption in assumptions:
                assumption_id = assumption.get("id")
                if not assumption_id:
                    continue

                validations = store.get_assumption_validations(assumption_id)
                if validations:
                    latest_validation = validations[-1]
                    severity: str = latest_validation.get("severity", "NONE")
                else:
                    severity = "NONE"

                by_severity[severity] = by_severity.get(severity, 0) + 1

                if severity in _HIGH_CRITICAL:
                    project_high_critical += 1
                if severity == "CRITICAL":
                    has_critical = True

            portfolio_high_critical_count += project_high_critical
            if has_critical:
                critical_projects.append(pid)

            projects.append({
                "project_id": pid,
                "assumption_count": assumption_count,
                "by_drift_severity": by_severity,
                "high_critical_count": project_high_critical,
            })

        output = {
            "project_count": len(project_ids),
            "projects": projects,
            "portfolio": {
                "total_assumptions": portfolio_total_assumptions,
                "total_high_critical_drift": portfolio_high_critical_count,
                "projects_with_critical_drift": critical_projects,
            },
        }

        return [TextContent(type="text", text=json.dumps(output, indent=2, default=str))]

    except Exception as exc:
        return [TextContent(type="text", text=f"Error: {exc}")]
