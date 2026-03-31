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


ASSURE_TOOLS: list[Tool] = [
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
        Tool(
            name="ingest_lesson",
            description=(
                "Ingest a structured lessons learned record into the knowledge "
                "base.  Captures category, sentiment, project type, phase, tags, "
                "and impact description for later search and analysis."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "Identifier of the source project.",
                    },
                    "title": {
                        "type": "string",
                        "description": "Short summary of the lesson.",
                    },
                    "description": {
                        "type": "string",
                        "description": "Full lesson narrative.",
                    },
                    "category": {
                        "type": "string",
                        "enum": [
                            "GOVERNANCE",
                            "TECHNICAL",
                            "COMMERCIAL",
                            "STAKEHOLDER",
                            "RESOURCE",
                            "REQUIREMENTS",
                            "ESTIMATION",
                            "RISK_MANAGEMENT",
                            "BENEFITS_REALISATION",
                            "OTHER",
                        ],
                        "description": "Domain classification for the lesson.",
                    },
                    "sentiment": {
                        "type": "string",
                        "enum": ["POSITIVE", "NEGATIVE"],
                        "description": "Whether this is a positive or negative lesson.",
                    },
                    "project_type": {
                        "type": "string",
                        "description": "Optional project type (e.g. 'ICT', 'Infrastructure').",
                    },
                    "project_phase": {
                        "type": "string",
                        "description": "Optional project phase (e.g. 'Initiation', 'Delivery').",
                    },
                    "department": {
                        "type": "string",
                        "description": "Optional originating department.",
                    },
                    "tags": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Free-form tags for keyword discovery.",
                    },
                    "recorded_by": {
                        "type": "string",
                        "description": "Name or role of the person recording the lesson.",
                    },
                    "impact_description": {
                        "type": "string",
                        "description": "What happened as a result of this lesson.",
                    },
                    "db_path": {
                        "type": "string",
                        "description": "Optional path to the SQLite store.",
                    },
                },
                "required": ["project_id", "title", "description", "category", "sentiment"],
            },
        ),
        Tool(
            name="search_lessons",
            description=(
                "Search the lessons learned corpus by free-text query.  "
                "Uses semantic search when sentence-transformers is available, "
                "otherwise falls back to keyword matching.  Supports filtering "
                "by project type, category, and sentiment."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Free-text search query.",
                    },
                    "project_type": {
                        "type": "string",
                        "description": "Optional project type filter.",
                    },
                    "category": {
                        "type": "string",
                        "enum": [
                            "GOVERNANCE",
                            "TECHNICAL",
                            "COMMERCIAL",
                            "STAKEHOLDER",
                            "RESOURCE",
                            "REQUIREMENTS",
                            "ESTIMATION",
                            "RISK_MANAGEMENT",
                            "BENEFITS_REALISATION",
                            "OTHER",
                        ],
                        "description": "Optional category filter.",
                    },
                    "sentiment": {
                        "type": "string",
                        "enum": ["POSITIVE", "NEGATIVE"],
                        "description": "Optional sentiment filter.",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Maximum number of results to return (default 10).",
                        "default": 10,
                    },
                    "db_path": {
                        "type": "string",
                        "description": "Optional path to the SQLite store.",
                    },
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="log_assurance_activity",
            description=(
                "Log an assurance activity with effort tracking.  Records "
                "person-hours, participants, artefacts reviewed, findings "
                "produced, and before/after compliance scores."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "Project identifier.",
                    },
                    "activity_type": {
                        "type": "string",
                        "enum": [
                            "GATE_REVIEW",
                            "DOCUMENT_REVIEW",
                            "COMPLIANCE_CHECK",
                            "RISK_ASSESSMENT",
                            "STAKEHOLDER_REVIEW",
                            "AUDIT",
                            "OTHER",
                        ],
                        "description": "Classification of the activity.",
                    },
                    "description": {
                        "type": "string",
                        "description": "What was done.",
                    },
                    "date": {
                        "type": "string",
                        "description": "ISO-8601 date of the activity.",
                    },
                    "effort_hours": {
                        "type": "number",
                        "description": "Person-hours spent on this activity.",
                    },
                    "participants": {
                        "type": "integer",
                        "description": "Number of people involved (default 1).",
                        "default": 1,
                    },
                    "artefacts_reviewed": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Artefact IDs checked during this activity.",
                    },
                    "findings_count": {
                        "type": "integer",
                        "description": "Number of findings or actions produced.",
                        "default": 0,
                    },
                    "confidence_before": {
                        "type": "number",
                        "description": "NISTA compliance score before the activity (0–100).",
                    },
                    "confidence_after": {
                        "type": "number",
                        "description": "NISTA compliance score after the activity (0–100).",
                    },
                    "db_path": {
                        "type": "string",
                        "description": "Optional path to the SQLite store.",
                    },
                },
                "required": [
                    "project_id",
                    "activity_type",
                    "description",
                    "date",
                    "effort_hours",
                ],
            },
        ),
        Tool(
            name="analyse_assurance_overhead",
            description=(
                "Run a complete assurance overhead analysis for a project.  "
                "Computes effort metrics, finding rates, duplicate checks, "
                "efficiency rating, and human-readable optimisation "
                "recommendations."
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
        Tool(
            name="run_assurance_workflow",
            description=(
                "Run a multi-step assurance workflow for a project.  "
                "Orchestrates P1–P8 steps deterministically, computes overall "
                "project health (HEALTHY / ATTENTION_NEEDED / AT_RISK / CRITICAL), "
                "and returns aggregated risk signals, recommended actions, and "
                "an executive summary.  Five workflow types available."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "Project identifier.",
                    },
                    "workflow_type": {
                        "type": "string",
                        "enum": [
                            "FULL_ASSURANCE",
                            "COMPLIANCE_FOCUS",
                            "CURRENCY_FOCUS",
                            "TREND_ANALYSIS",
                            "RISK_ASSESSMENT",
                        ],
                        "description": "Which workflow plan to execute.",
                    },
                    "artefacts": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "type": {"type": "string"},
                                "last_modified": {"type": "string"},
                            },
                            "required": ["id", "type", "last_modified"],
                        },
                        "description": (
                            "Optional artefact list for P1 currency check.  "
                            "Each item must have 'id', 'type', and "
                            "'last_modified' (ISO-8601 datetime string)."
                        ),
                    },
                    "gate_date": {
                        "type": "string",
                        "description": (
                            "Optional ISO-8601 gate date for P1 currency check.  "
                            "Required when artefacts is provided."
                        ),
                    },
                    "db_path": {
                        "type": "string",
                        "description": "Optional path to the SQLite store.",
                    },
                },
                "required": ["project_id", "workflow_type"],
            },
        ),
        Tool(
            name="get_workflow_history",
            description=(
                "Retrieve the assurance workflow execution history for a project.  "
                "Returns all past workflow results ordered by start time ascending."
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
        Tool(
            name="classify_project_domain",
            description=(
                "Classify a project into a complexity domain (CLEAR / COMPLICATED / "
                "COMPLEX / CHAOTIC) using up to seven explicit indicators and "
                "store-derived signals from P2, P3, P6, and P8.  Returns the "
                "domain, composite score, and a tailored assurance profile."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "Project identifier.",
                    },
                    "technical_complexity": {
                        "type": "number",
                        "description": "Technical novelty and integration complexity (0–1).",
                    },
                    "stakeholder_complexity": {
                        "type": "number",
                        "description": "Breadth and diversity of stakeholders (0–1).",
                    },
                    "requirement_clarity": {
                        "type": "number",
                        "description": (
                            "How well-defined requirements are (0–1; high = clearer, "
                            "inverted internally)."
                        ),
                    },
                    "delivery_track_record": {
                        "type": "number",
                        "description": (
                            "Team's prior delivery success rate (0–1; high = better, "
                            "inverted internally)."
                        ),
                    },
                    "organisational_change": {
                        "type": "number",
                        "description": "Degree of organisational change required (0–1).",
                    },
                    "regulatory_exposure": {
                        "type": "number",
                        "description": "Level of regulatory or compliance risk (0–1).",
                    },
                    "dependency_count": {
                        "type": "number",
                        "description": "Normalised count of external dependencies (0–1).",
                    },
                    "notes": {
                        "type": "string",
                        "description": "Optional free-text notes about this classification.",
                    },
                    "db_path": {
                        "type": "string",
                        "description": "Optional path to the SQLite store.",
                    },
                },
                "required": ["project_id"],
            },
        ),
        Tool(
            name="reclassify_from_store",
            description=(
                "Reclassify a project's complexity domain using only store-derived "
                "signals (P2 trend, P3 open actions, P6 override rate, P8 efficiency).  "
                "No explicit indicators required.  Useful for automated or scheduled "
                "reclassification."
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
        Tool(
            name="ingest_assumption",
            description=(
                "Ingest a project assumption with its baseline value into the "
                "assumption tracker.  Supports cost, schedule, resource, technical, "
                "commercial, regulatory, stakeholder, and external assumption types."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "project_id": {"type": "string", "description": "Project identifier."},
                    "text": {"type": "string", "description": "Human-readable assumption statement."},
                    "category": {
                        "type": "string",
                        "enum": ["COST", "SCHEDULE", "RESOURCE", "TECHNICAL", "COMMERCIAL", "REGULATORY", "STAKEHOLDER", "EXTERNAL"],
                        "description": "Assumption category.",
                    },
                    "baseline_value": {"type": "number", "description": "The original assumed value."},
                    "unit": {"type": "string", "description": "Measurement unit (e.g. '%', 'GBP', 'days')."},
                    "tolerance_pct": {"type": "number", "description": "Acceptable drift percentage (default 10)."},
                    "source": {
                        "type": "string",
                        "enum": ["MANUAL", "EXTERNAL_API", "DERIVED"],
                        "description": "Source of the assumption value.",
                    },
                    "external_ref": {"type": "string", "description": "External data source identifier (e.g. 'ONS_CPI')."},
                    "owner": {"type": "string", "description": "Name or role responsible for this assumption."},
                    "notes": {"type": "string", "description": "Optional free-text notes."},
                    "db_path": {"type": "string", "description": "Optional path to the SQLite store."},
                },
                "required": ["project_id", "text", "category", "baseline_value"],
            },
        ),
        Tool(
            name="validate_assumption",
            description=(
                "Update an assumption's current value, record the validation, "
                "and compute drift against the baseline.  Returns drift percentage "
                "and severity classification."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "assumption_id": {"type": "string", "description": "UUID of the assumption to update."},
                    "new_value": {"type": "number", "description": "The updated current value."},
                    "source": {
                        "type": "string",
                        "enum": ["MANUAL", "EXTERNAL_API", "DERIVED"],
                        "description": "Source of the new value (default MANUAL).",
                    },
                    "notes": {"type": "string", "description": "Optional notes about this update."},
                    "db_path": {"type": "string", "description": "Optional path to the SQLite store."},
                },
                "required": ["assumption_id", "new_value"],
            },
        ),
        Tool(
            name="get_assumption_drift",
            description=(
                "Run a full assumption health analysis for a project.  "
                "Returns drift status for all assumptions, stale count, "
                "cascade warnings, and an overall drift score (0–1)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "project_id": {"type": "string", "description": "Project identifier."},
                    "db_path": {"type": "string", "description": "Optional path to the SQLite store."},
                },
                "required": ["project_id"],
            },
        ),
        Tool(
            name="get_cascade_impact",
            description=(
                "Find all assumptions that depend on the given assumption "
                "(direct and transitive).  Returns affected assumption IDs "
                "with their texts and current drift status."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "assumption_id": {"type": "string", "description": "UUID of the source assumption."},
                    "db_path": {"type": "string", "description": "Optional path to the SQLite store."},
                },
                "required": ["assumption_id"],
            },
        ),
    ]


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available PM Assure tools."""
    return ASSURE_TOOLS


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
    if name == "ingest_lesson":
        return await _ingest_lesson(arguments)
    if name == "search_lessons":
        return await _search_lessons(arguments)
    if name == "log_assurance_activity":
        return await _log_assurance_activity(arguments)
    if name == "analyse_assurance_overhead":
        return await _analyse_assurance_overhead(arguments)
    if name == "run_assurance_workflow":
        return await _run_assurance_workflow(arguments)
    if name == "get_workflow_history":
        return await _get_workflow_history(arguments)
    if name == "classify_project_domain":
        return await _classify_project_domain(arguments)
    if name == "reclassify_from_store":
        return await _reclassify_from_store(arguments)
    if name == "ingest_assumption":
        return await _ingest_assumption(arguments)
    if name == "validate_assumption":
        return await _validate_assumption(arguments)
    if name == "get_assumption_drift":
        return await _get_assumption_drift(arguments)
    if name == "get_cascade_impact":
        return await _get_cascade_impact(arguments)
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


async def _ingest_lesson(arguments: dict[str, Any]) -> list[TextContent]:
    """Ingest a structured lesson into the knowledge base."""
    try:
        from pathlib import Path

        from pm_data_tools.assurance.lessons import (
            LessonCategory,
            LessonRecord,
            LessonSentiment,
            LessonsKnowledgeEngine,
        )
        from pm_data_tools.db.store import AssuranceStore

        raw_db_path = arguments.get("db_path")
        db_path = Path(raw_db_path) if raw_db_path else None
        store = AssuranceStore(db_path=db_path)

        lesson = LessonRecord(
            project_id=arguments["project_id"],
            title=arguments["title"],
            description=arguments["description"],
            category=LessonCategory(arguments["category"]),
            sentiment=LessonSentiment(arguments["sentiment"]),
            project_type=arguments.get("project_type"),
            project_phase=arguments.get("project_phase"),
            department=arguments.get("department"),
            tags=list(arguments.get("tags", [])),
            recorded_by=arguments.get("recorded_by"),
            impact_description=arguments.get("impact_description"),
        )

        engine = LessonsKnowledgeEngine(store=store)
        ingested = engine.ingest(lesson)

        output: dict[str, Any] = {
            "id": ingested.id,
            "project_id": ingested.project_id,
            "title": ingested.title,
            "category": ingested.category.value,
            "sentiment": ingested.sentiment.value,
            "date_recorded": ingested.date_recorded.isoformat(),
            "message": f"Lesson ingested with id '{ingested.id}'.",
        }

        return [
            TextContent(
                type="text",
                text=json.dumps(output, indent=2, default=str),
            )
        ]

    except Exception as exc:
        return [TextContent(type="text", text=f"Error: {exc}")]


async def _search_lessons(arguments: dict[str, Any]) -> list[TextContent]:
    """Search the lessons corpus by free-text query."""
    try:
        from pathlib import Path

        from pm_data_tools.assurance.lessons import (
            LessonCategory,
            LessonSentiment,
            LessonsKnowledgeEngine,
        )
        from pm_data_tools.db.store import AssuranceStore

        raw_db_path = arguments.get("db_path")
        db_path = Path(raw_db_path) if raw_db_path else None
        store = AssuranceStore(db_path=db_path)

        raw_category = arguments.get("category")
        raw_sentiment = arguments.get("sentiment")

        engine = LessonsKnowledgeEngine(store=store)
        response = engine.search(
            query=arguments["query"],
            project_type=arguments.get("project_type"),
            category=LessonCategory(raw_category) if raw_category else None,
            sentiment=LessonSentiment(raw_sentiment) if raw_sentiment else None,
            limit=int(arguments.get("limit", 10)),
        )

        output: dict[str, Any] = {
            "query": response.query,
            "search_method": response.search_method,
            "total_in_corpus": response.total_in_corpus,
            "results_count": len(response.results),
            "results": [
                {
                    "id": r.lesson.id,
                    "project_id": r.lesson.project_id,
                    "title": r.lesson.title,
                    "category": r.lesson.category.value,
                    "sentiment": r.lesson.sentiment.value,
                    "project_type": r.lesson.project_type,
                    "relevance_score": r.relevance_score,
                    "match_reason": r.match_reason,
                }
                for r in response.results
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


async def _log_assurance_activity(arguments: dict[str, Any]) -> list[TextContent]:
    """Log an assurance activity with effort tracking."""
    try:
        from datetime import date
        from pathlib import Path

        from pm_data_tools.assurance.overhead import (
            ActivityType,
            AssuranceActivity,
            AssuranceOverheadOptimiser,
        )
        from pm_data_tools.db.store import AssuranceStore

        raw_db_path = arguments.get("db_path")
        db_path = Path(raw_db_path) if raw_db_path else None
        store = AssuranceStore(db_path=db_path)

        cb = arguments.get("confidence_before")
        ca = arguments.get("confidence_after")

        activity = AssuranceActivity(
            project_id=arguments["project_id"],
            activity_type=ActivityType(arguments["activity_type"]),
            description=arguments["description"],
            date=date.fromisoformat(str(arguments["date"])),
            effort_hours=float(arguments["effort_hours"]),
            participants=int(arguments.get("participants", 1)),
            artefacts_reviewed=list(arguments.get("artefacts_reviewed", [])),
            findings_count=int(arguments.get("findings_count", 0)),
            confidence_before=float(cb) if cb is not None else None,
            confidence_after=float(ca) if ca is not None else None,
        )

        optimiser = AssuranceOverheadOptimiser(store=store)
        logged = optimiser.log_activity(activity)

        output: dict[str, Any] = {
            "id": logged.id,
            "project_id": logged.project_id,
            "activity_type": logged.activity_type.value,
            "date": logged.date.isoformat(),
            "effort_hours": logged.effort_hours,
            "findings_count": logged.findings_count,
            "message": f"Activity logged with id '{logged.id}'.",
        }

        return [
            TextContent(
                type="text",
                text=json.dumps(output, indent=2, default=str),
            )
        ]

    except Exception as exc:
        return [TextContent(type="text", text=f"Error: {exc}")]


async def _analyse_assurance_overhead(arguments: dict[str, Any]) -> list[TextContent]:
    """Run a complete assurance overhead analysis for a project."""
    try:
        from pathlib import Path

        from pm_data_tools.assurance.overhead import AssuranceOverheadOptimiser
        from pm_data_tools.db.store import AssuranceStore

        raw_db_path = arguments.get("db_path")
        db_path = Path(raw_db_path) if raw_db_path else None
        store = AssuranceStore(db_path=db_path)

        project_id: str = arguments["project_id"]
        optimiser = AssuranceOverheadOptimiser(store=store)
        analysis = optimiser.analyse(project_id)

        output: dict[str, Any] = {
            "project_id": analysis.project_id,
            "timestamp": analysis.timestamp.isoformat(),
            "total_activities": analysis.total_activities,
            "total_effort_hours": analysis.total_effort_hours,
            "total_participants_hours": analysis.total_participants_hours,
            "effort_by_type": analysis.effort_by_type,
            "activities_with_findings": analysis.activities_with_findings,
            "activities_without_findings": analysis.activities_without_findings,
            "finding_rate": analysis.finding_rate,
            "avg_confidence_lift": analysis.avg_confidence_lift,
            "efficiency_rating": analysis.efficiency_rating.value,
            "duplicate_checks": [
                {
                    "activity_id": d.activity_id,
                    "duplicate_of": d.duplicate_of,
                    "overlap_type": d.overlap_type,
                    "detail": d.detail,
                }
                for d in analysis.duplicate_checks
            ],
            "recommendations": analysis.recommendations,
            "message": analysis.message,
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


async def _run_assurance_workflow(arguments: dict[str, Any]) -> list[TextContent]:
    """Execute a multi-step assurance workflow for a project."""
    try:
        from pathlib import Path

        from pm_data_tools.assurance.workflows import AssuranceWorkflowEngine, WorkflowType
        from pm_data_tools.db.store import AssuranceStore

        raw_db_path = arguments.get("db_path")
        db_path = Path(raw_db_path) if raw_db_path else None
        store = AssuranceStore(db_path=db_path)

        project_id: str = arguments["project_id"]
        workflow_type = WorkflowType(arguments["workflow_type"])
        artefacts = list(arguments.get("artefacts") or []) or None
        gate_date = arguments.get("gate_date")

        engine = AssuranceWorkflowEngine(store=store)
        result = engine.execute(
            project_id=project_id,
            workflow_type=workflow_type,
            artefacts=artefacts,
            gate_date=gate_date,
        )

        output: dict[str, Any] = {
            "id": result.id,
            "project_id": result.project_id,
            "workflow_type": result.workflow_type.value,
            "health": result.health.value,
            "started_at": result.started_at.isoformat(),
            "completed_at": result.completed_at.isoformat(),
            "duration_ms": round(result.duration_ms, 1),
            "steps": [
                {
                    "step_name": s.step_name,
                    "status": s.status.value,
                    "duration_ms": round(s.duration_ms, 1),
                    "risk_signal": (
                        {
                            "source": s.risk_signal.source,
                            "signal_name": s.risk_signal.signal_name,
                            "severity": s.risk_signal.severity,
                            "detail": s.risk_signal.detail,
                        }
                        if s.risk_signal
                        else None
                    ),
                    "error_message": s.error_message,
                }
                for s in result.steps
            ],
            "aggregated_risk_signals": [
                {
                    "source": sig.source,
                    "signal_name": sig.signal_name,
                    "severity": sig.severity,
                    "detail": sig.detail,
                }
                for sig in result.aggregated_risk_signals
            ],
            "recommended_actions": result.recommended_actions,
            "executive_summary": result.executive_summary,
        }

        return [
            TextContent(
                type="text",
                text=json.dumps(output, indent=2, default=str),
            )
        ]

    except Exception as exc:
        return [TextContent(type="text", text=f"Error: {exc}")]


async def _get_workflow_history(arguments: dict[str, Any]) -> list[TextContent]:
    """Retrieve workflow execution history for a project."""
    try:
        from pathlib import Path

        from pm_data_tools.assurance.workflows import AssuranceWorkflowEngine
        from pm_data_tools.db.store import AssuranceStore

        raw_db_path = arguments.get("db_path")
        db_path = Path(raw_db_path) if raw_db_path else None
        store = AssuranceStore(db_path=db_path)

        project_id: str = arguments["project_id"]
        engine = AssuranceWorkflowEngine(store=store)
        history = engine.get_workflow_history(project_id)

        output: dict[str, Any] = {
            "project_id": project_id,
            "total_executions": len(history),
            "executions": [
                {
                    "id": r.id,
                    "workflow_type": r.workflow_type.value,
                    "health": r.health.value,
                    "started_at": r.started_at.isoformat(),
                    "duration_ms": round(r.duration_ms, 1),
                    "steps_completed": sum(
                        1 for s in r.steps
                        if s.status.value == "COMPLETED"
                    ),
                    "signals_count": len(r.aggregated_risk_signals),
                }
                for r in history
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


async def _classify_project_domain(arguments: dict[str, Any]) -> list[TextContent]:
    """Classify a project into a complexity domain."""
    try:
        from pathlib import Path

        from pm_data_tools.assurance.classifier import (
            ClassificationInput,
            ProjectDomainClassifier,
        )
        from pm_data_tools.db.store import AssuranceStore

        raw_db_path = arguments.get("db_path")
        db_path = Path(raw_db_path) if raw_db_path else None
        store = AssuranceStore(db_path=db_path)

        def _opt_float(key: str) -> float | None:
            val = arguments.get(key)
            return float(val) if val is not None else None

        inp = ClassificationInput(
            project_id=arguments["project_id"],
            technical_complexity=_opt_float("technical_complexity"),
            stakeholder_complexity=_opt_float("stakeholder_complexity"),
            requirement_clarity=_opt_float("requirement_clarity"),
            delivery_track_record=_opt_float("delivery_track_record"),
            organisational_change=_opt_float("organisational_change"),
            regulatory_exposure=_opt_float("regulatory_exposure"),
            dependency_count=_opt_float("dependency_count"),
            notes=arguments.get("notes"),
        )

        clf = ProjectDomainClassifier(store=store)
        result = clf.classify(inp)

        output: dict[str, Any] = {
            "id": result.id,
            "project_id": result.project_id,
            "domain": result.domain.value,
            "composite_score": round(result.composite_score, 3),
            "explicit_score": (
                round(result.explicit_score, 3) if result.explicit_score is not None else None
            ),
            "derived_score": (
                round(result.derived_score, 3) if result.derived_score is not None else None
            ),
            "classified_at": result.classified_at.isoformat(),
            "indicators": [
                {
                    "name": i.name,
                    "raw_value": i.raw_value,
                    "complexity_contribution": round(i.complexity_contribution, 3),
                }
                for i in result.indicators
            ],
            "profile": {
                "review_frequency_days": result.profile.review_frequency_days,
                "recommended_tools": result.profile.recommended_tools,
                "confidence_threshold": result.profile.confidence_threshold,
                "compliance_floor": result.profile.compliance_floor,
                "notes": result.profile.notes,
            },
            "rationale": result.rationale,
        }

        return [
            TextContent(
                type="text",
                text=json.dumps(output, indent=2, default=str),
            )
        ]

    except Exception as exc:
        return [TextContent(type="text", text=f"Error: {exc}")]


async def _reclassify_from_store(arguments: dict[str, Any]) -> list[TextContent]:
    """Reclassify a project using only store-derived signals."""
    try:
        from pathlib import Path

        from pm_data_tools.assurance.classifier import ProjectDomainClassifier
        from pm_data_tools.db.store import AssuranceStore

        raw_db_path = arguments.get("db_path")
        db_path = Path(raw_db_path) if raw_db_path else None
        store = AssuranceStore(db_path=db_path)

        project_id: str = arguments["project_id"]
        clf = ProjectDomainClassifier(store=store)
        result = clf.reclassify_from_store(project_id)

        output: dict[str, Any] = {
            "id": result.id,
            "project_id": result.project_id,
            "domain": result.domain.value,
            "composite_score": round(result.composite_score, 3),
            "derived_score": (
                round(result.derived_score, 3) if result.derived_score is not None else None
            ),
            "classified_at": result.classified_at.isoformat(),
            "profile": {
                "review_frequency_days": result.profile.review_frequency_days,
                "recommended_tools": result.profile.recommended_tools,
                "confidence_threshold": result.profile.confidence_threshold,
                "compliance_floor": result.profile.compliance_floor,
                "notes": result.profile.notes,
            },
            "rationale": result.rationale,
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
# P11 — Assumption Drift Tracker handlers
# ---------------------------------------------------------------------------


async def _ingest_assumption(arguments: dict[str, Any]) -> list[TextContent]:
    """Ingest a project assumption with its baseline value."""
    try:
        from pathlib import Path

        from pm_data_tools.assurance.assumptions import (
            Assumption,
            AssumptionCategory,
            AssumptionSource,
            AssumptionTracker,
        )
        from pm_data_tools.db.store import AssuranceStore

        raw_db_path = arguments.get("db_path")
        db_path = Path(raw_db_path) if raw_db_path else None
        store = AssuranceStore(db_path=db_path)
        tracker = AssumptionTracker(store=store)

        assumption = Assumption(
            project_id=arguments["project_id"],
            text=arguments["text"],
            category=AssumptionCategory(arguments["category"]),
            baseline_value=float(arguments["baseline_value"]),
            unit=arguments.get("unit", ""),
            tolerance_pct=float(arguments.get("tolerance_pct", 10.0)),
            source=AssumptionSource(arguments.get("source", "MANUAL")),
            external_ref=arguments.get("external_ref"),
            owner=arguments.get("owner"),
            notes=arguments.get("notes"),
        )
        tracker.ingest(assumption)

        output: dict[str, Any] = {
            "id": assumption.id,
            "project_id": assumption.project_id,
            "text": assumption.text,
            "category": assumption.category.value,
            "baseline_value": assumption.baseline_value,
            "unit": assumption.unit,
            "tolerance_pct": assumption.tolerance_pct,
            "source": assumption.source.value,
        }
        return [TextContent(type="text", text=json.dumps(output, indent=2, default=str))]

    except Exception as exc:
        return [TextContent(type="text", text=f"Error: {exc}")]


async def _validate_assumption(arguments: dict[str, Any]) -> list[TextContent]:
    """Update an assumption's current value and record the validation."""
    try:
        from pathlib import Path

        from pm_data_tools.assurance.assumptions import AssumptionSource, AssumptionTracker
        from pm_data_tools.db.store import AssuranceStore

        raw_db_path = arguments.get("db_path")
        db_path = Path(raw_db_path) if raw_db_path else None
        store = AssuranceStore(db_path=db_path)
        tracker = AssumptionTracker(store=store)

        validation = tracker.update_value(
            assumption_id=arguments["assumption_id"],
            new_value=float(arguments["new_value"]),
            source=AssumptionSource(arguments.get("source", "MANUAL")),
            notes=arguments.get("notes"),
        )

        output: dict[str, Any] = {
            "id": validation.id,
            "assumption_id": validation.assumption_id,
            "validated_at": validation.validated_at.isoformat(),
            "previous_value": validation.previous_value,
            "new_value": validation.new_value,
            "drift_pct": validation.drift_pct,
            "severity": validation.severity.value,
            "notes": validation.notes,
        }
        return [TextContent(type="text", text=json.dumps(output, indent=2, default=str))]

    except Exception as exc:
        return [TextContent(type="text", text=f"Error: {exc}")]


async def _get_assumption_drift(arguments: dict[str, Any]) -> list[TextContent]:
    """Run a full assumption health analysis for a project."""
    try:
        from pathlib import Path

        from pm_data_tools.assurance.assumptions import AssumptionTracker
        from pm_data_tools.db.store import AssuranceStore

        raw_db_path = arguments.get("db_path")
        db_path = Path(raw_db_path) if raw_db_path else None
        store = AssuranceStore(db_path=db_path)
        tracker = AssumptionTracker(store=store)

        report = tracker.analyse_project(arguments["project_id"])

        output: dict[str, Any] = {
            "project_id": report.project_id,
            "timestamp": report.timestamp.isoformat(),
            "total_assumptions": report.total_assumptions,
            "validated_count": report.validated_count,
            "stale_count": report.stale_count,
            "overall_drift_score": report.overall_drift_score,
            "by_severity": report.by_severity,
            "by_category": report.by_category,
            "cascade_warnings": report.cascade_warnings,
            "message": report.message,
            "drift_results": [
                {
                    "assumption_id": dr.assumption.id,
                    "text": dr.assumption.text,
                    "category": dr.assumption.category.value,
                    "baseline_value": dr.assumption.baseline_value,
                    "current_value": dr.assumption.current_value,
                    "unit": dr.assumption.unit,
                    "drift_pct": dr.drift_pct,
                    "severity": dr.severity.value,
                    "days_since_validation": dr.days_since_validation,
                    "cascade_impact_count": len(dr.cascade_impact),
                    "message": dr.message,
                }
                for dr in report.drift_results
            ],
        }
        return [TextContent(type="text", text=json.dumps(output, indent=2, default=str))]

    except Exception as exc:
        return [TextContent(type="text", text=f"Error: {exc}")]


async def _get_cascade_impact(arguments: dict[str, Any]) -> list[TextContent]:
    """Find all assumptions affected by drift in the given assumption."""
    try:
        from pathlib import Path

        from pm_data_tools.assurance.assumptions import (
            AssumptionTracker,
            _row_to_assumption,
        )
        from pm_data_tools.db.store import AssuranceStore

        raw_db_path = arguments.get("db_path")
        db_path = Path(raw_db_path) if raw_db_path else None
        store = AssuranceStore(db_path=db_path)
        tracker = AssumptionTracker(store=store)

        assumption_id: str = arguments["assumption_id"]
        impacted_ids = tracker.get_cascade_impact(assumption_id)

        items: list[dict[str, Any]] = []
        for aid in impacted_ids:
            row = store.get_assumption_by_id(aid)
            if row is not None:
                a = _row_to_assumption(row)
                dr = tracker.compute_drift(a)
                items.append({
                    "assumption_id": aid,
                    "text": a.text,
                    "category": a.category.value,
                    "baseline_value": a.baseline_value,
                    "current_value": a.current_value,
                    "drift_pct": dr.drift_pct,
                    "severity": dr.severity.value,
                })

        output: dict[str, Any] = {
            "source_assumption_id": assumption_id,
            "impacted_count": len(items),
            "impacted_assumptions": items,
        }
        return [TextContent(type="text", text=json.dumps(output, indent=2, default=str))]

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
