"""Unified PDA Platform MCP Server.

Combines tools from pm-assure (24 tools) and pm-nista (5 tools) into
a single MCP server with 29 tools.  This is the server exposed via
the SSE web transport for remote MCP clients (claude.ai, Claude Desktop).

Provides the OPAL (Open Project Assurance Library) framework, ARMM
(Agent Readiness Maturity Model), GMPP reporting, and UDS dashboard export.

All Tool definitions are hardcoded here for robustness — no fragile
introspection of the MCP SDK's internal handlers.
"""

from __future__ import annotations

import asyncio
from typing import Any

from mcp.server import Server
from mcp.types import TextContent, Tool

# ---------------------------------------------------------------------------
# Import handler functions from pm-assure (24 tools)
# ---------------------------------------------------------------------------

from pm_mcp_servers.pm_assure.server import (
    _nista_longitudinal_trend,
    _track_review_actions,
    _review_action_status,
    _check_artefact_currency,
    _check_confidence_divergence,
    _recommend_review_schedule,
    _log_override_decision,
    _analyse_override_patterns,
    _ingest_lesson,
    _search_lessons,
    _log_assurance_activity,
    _analyse_assurance_overhead,
    _run_assurance_workflow,
    _get_workflow_history,
    _classify_project_domain,
    _reclassify_from_store,
    _ingest_assumption,
    _validate_assumption,
    _get_assumption_drift,
    _get_cascade_impact,
    _create_project_from_profile,
    _export_dashboard_data,
    _export_dashboard_html,
    _get_armm_report,
)

# ---------------------------------------------------------------------------
# Import handler functions from pm-nista (5 tools)
# ---------------------------------------------------------------------------

from pm_mcp_servers.pm_nista.server import (
    _generate_gmpp_report,
    _generate_narrative,
    _submit_to_nista,
    _fetch_nista_metadata,
    _validate_gmpp_report,
)

# ---------------------------------------------------------------------------
# Handler dispatch table
# ---------------------------------------------------------------------------

HANDLERS: dict[str, Any] = {
    # pm-assure: OPAL modules (20 tools)
    "nista_longitudinal_trend": _nista_longitudinal_trend,
    "track_review_actions": _track_review_actions,
    "review_action_status": _review_action_status,
    "check_artefact_currency": _check_artefact_currency,
    "check_confidence_divergence": _check_confidence_divergence,
    "recommend_review_schedule": _recommend_review_schedule,
    "log_override_decision": _log_override_decision,
    "analyse_override_patterns": _analyse_override_patterns,
    "ingest_lesson": _ingest_lesson,
    "search_lessons": _search_lessons,
    "log_assurance_activity": _log_assurance_activity,
    "analyse_assurance_overhead": _analyse_assurance_overhead,
    "run_assurance_workflow": _run_assurance_workflow,
    "get_workflow_history": _get_workflow_history,
    "classify_project_domain": _classify_project_domain,
    "reclassify_from_store": _reclassify_from_store,
    "ingest_assumption": _ingest_assumption,
    "validate_assumption": _validate_assumption,
    "get_assumption_drift": _get_assumption_drift,
    "get_cascade_impact": _get_cascade_impact,
    # pm-assure: hackathon + ARMM tools (4 tools)
    "create_project_from_profile": _create_project_from_profile,
    "export_dashboard_data": _export_dashboard_data,
    "export_dashboard_html": _export_dashboard_html,
    "get_armm_report": _get_armm_report,
    # pm-nista (5 tools)
    "generate_gmpp_report": _generate_gmpp_report,
    "generate_narrative": _generate_narrative,
    "submit_to_nista": _submit_to_nista,
    "fetch_nista_metadata": _fetch_nista_metadata,
    "validate_gmpp_report": _validate_gmpp_report,
}

# ---------------------------------------------------------------------------
# Unified Server with hardcoded Tool definitions
# ---------------------------------------------------------------------------

app = Server("pda-platform")

# Common schema fragment for db_path
_DB_PATH = {"type": "string", "description": "Optional path to the SQLite store."}
_PROJECT_ID = {"type": "string", "description": "Project identifier."}


def _all_tool_definitions() -> list[Tool]:
    """All 29 Tool definitions, hardcoded for robustness."""
    return [
        # ===== OPAL-2: Longitudinal Compliance =====
        Tool(name="nista_longitudinal_trend", description="OPAL-2: Retrieve NISTA compliance score history, trend direction, and active threshold breaches for a project.", inputSchema={"type": "object", "properties": {"project_id": _PROJECT_ID, "db_path": _DB_PATH}, "required": ["project_id"]}),
        # ===== OPAL-3: Review Actions =====
        Tool(name="track_review_actions", description="OPAL-3: Extract review actions from project review text, persist them, and detect cross-cycle recurrences.", inputSchema={"type": "object", "properties": {"review_text": {"type": "string"}, "review_id": {"type": "string"}, "project_id": _PROJECT_ID, "min_confidence": {"type": "number", "default": 0.60}}, "required": ["review_text", "review_id", "project_id"]}),
        Tool(name="review_action_status", description="OPAL-3: Retrieve tracked review actions, optionally filtered by status (OPEN/IN_PROGRESS/CLOSED/RECURRING).", inputSchema={"type": "object", "properties": {"project_id": _PROJECT_ID, "status_filter": {"type": "string", "enum": ["OPEN", "IN_PROGRESS", "CLOSED", "RECURRING"]}, "db_path": _DB_PATH}, "required": ["project_id"]}),
        # ===== OPAL-1: Artefact Currency =====
        Tool(name="check_artefact_currency", description="OPAL-1: Assess document currency against upcoming gate dates. Detects stale artefacts and anomalous last-minute updates.", inputSchema={"type": "object", "properties": {"project_id": _PROJECT_ID, "gate_date": {"type": "string"}, "artefacts": {"type": "array", "items": {"type": "object"}}, "db_path": _DB_PATH}, "required": ["project_id", "gate_date", "artefacts"]}),
        # ===== OPAL-4: Confidence Divergence =====
        Tool(name="check_confidence_divergence", description="OPAL-4: Monitor AI extraction confidence and flag high sample divergence or low consensus.", inputSchema={"type": "object", "properties": {"project_id": _PROJECT_ID, "review_id": {"type": "string"}, "confidence_score": {"type": "number"}, "sample_scores": {"type": "array", "items": {"type": "number"}}, "db_path": _DB_PATH}, "required": ["project_id", "review_id", "confidence_score", "sample_scores"]}),
        # ===== OPAL-5: Adaptive Scheduling =====
        Tool(name="recommend_review_schedule", description="OPAL-5: Recommend next review date and urgency using OPAL-1 to OPAL-4 signals.", inputSchema={"type": "object", "properties": {"project_id": _PROJECT_ID, "artefacts": {"type": "array", "items": {"type": "object"}}, "gate_date": {"type": "string"}, "db_path": _DB_PATH}, "required": ["project_id", "artefacts", "gate_date"]}),
        # ===== OPAL-6: Governance Overrides =====
        Tool(name="log_override_decision", description="OPAL-6: Log a governance override decision with authoriser, rationale, conditions, and evidence.", inputSchema={"type": "object", "properties": {"project_id": _PROJECT_ID, "override_type": {"type": "string", "enum": ["RAG_OVERRIDE", "GATE_PROGRESSION", "RECOMMENDATION_DISMISSED", "SCHEDULE_OVERRIDE", "BUDGET_OVERRIDE"]}, "decision_date": {"type": "string"}, "authoriser": {"type": "string"}, "rationale": {"type": "string"}, "db_path": _DB_PATH}, "required": ["project_id", "override_type", "decision_date", "authoriser", "rationale"]}),
        Tool(name="analyse_override_patterns", description="OPAL-6: Analyse override patterns — breakdown by type, outcome, impact rate, top authorisers.", inputSchema={"type": "object", "properties": {"project_id": _PROJECT_ID, "db_path": _DB_PATH}, "required": ["project_id"]}),
        # ===== OPAL-7: Lessons Learned =====
        Tool(name="ingest_lesson", description="OPAL-7: Ingest a lesson learned with category, sentiment, impact, and applicability.", inputSchema={"type": "object", "properties": {"project_id": _PROJECT_ID, "title": {"type": "string"}, "description": {"type": "string"}, "category": {"type": "string"}, "sentiment": {"type": "string", "enum": ["POSITIVE", "NEGATIVE", "NEUTRAL"]}, "impact_description": {"type": "string"}, "project_type": {"type": "string"}, "db_path": _DB_PATH}, "required": ["project_id", "title", "description", "category"]}),
        Tool(name="search_lessons", description="OPAL-7: Search lessons learned by keyword, category, or sentiment.", inputSchema={"type": "object", "properties": {"query": {"type": "string"}, "project_id": _PROJECT_ID, "category": {"type": "string"}, "sentiment": {"type": "string"}, "db_path": _DB_PATH}, "required": ["query"]}),
        # ===== OPAL-8: Overhead Optimiser =====
        Tool(name="log_assurance_activity", description="OPAL-8: Log an assurance activity with effort, participants, findings, and confidence delta.", inputSchema={"type": "object", "properties": {"project_id": _PROJECT_ID, "activity_type": {"type": "string"}, "description": {"type": "string"}, "date": {"type": "string"}, "effort_hours": {"type": "number"}, "participants": {"type": "integer"}, "findings_count": {"type": "integer"}, "confidence_before": {"type": "number"}, "confidence_after": {"type": "number"}, "db_path": _DB_PATH}, "required": ["project_id", "activity_type", "description", "date", "effort_hours"]}),
        Tool(name="analyse_assurance_overhead", description="OPAL-8: Analyse assurance overhead — efficiency rating, recommendations, effort breakdown.", inputSchema={"type": "object", "properties": {"project_id": _PROJECT_ID, "db_path": _DB_PATH}, "required": ["project_id"]}),
        # ===== OPAL-9: Workflow Orchestration =====
        Tool(name="run_assurance_workflow", description="OPAL-9: Execute a multi-step assurance workflow (FULL_ASSURANCE, RISK_ASSESSMENT, COMPLIANCE_FOCUS, TREND_ANALYSIS, CURRENCY_FOCUS).", inputSchema={"type": "object", "properties": {"project_id": _PROJECT_ID, "workflow_type": {"type": "string", "enum": ["FULL_ASSURANCE", "RISK_ASSESSMENT", "COMPLIANCE_FOCUS", "TREND_ANALYSIS", "CURRENCY_FOCUS"]}, "db_path": _DB_PATH}, "required": ["project_id"]}),
        Tool(name="get_workflow_history", description="OPAL-9: Retrieve past workflow executions with health status and step details.", inputSchema={"type": "object", "properties": {"project_id": _PROJECT_ID, "db_path": _DB_PATH}, "required": ["project_id"]}),
        # ===== OPAL-10: Domain Classification =====
        Tool(name="classify_project_domain", description="OPAL-10: Classify project complexity domain (CLEAR/COMPLICATED/COMPLEX/CHAOTIC) using 7 indicators.", inputSchema={"type": "object", "properties": {"project_id": _PROJECT_ID, "technical_complexity": {"type": "number"}, "stakeholder_complexity": {"type": "number"}, "requirement_clarity": {"type": "number"}, "delivery_track_record": {"type": "number"}, "organisational_change": {"type": "number"}, "regulatory_exposure": {"type": "number"}, "dependency_count": {"type": "number"}, "db_path": _DB_PATH}, "required": ["project_id"]}),
        Tool(name="reclassify_from_store", description="OPAL-10: Reclassify domain using only store-derived signals (no explicit indicators needed).", inputSchema={"type": "object", "properties": {"project_id": _PROJECT_ID, "db_path": _DB_PATH}, "required": ["project_id"]}),
        # ===== OPAL-11: Assumption Drift =====
        Tool(name="ingest_assumption", description="OPAL-11: Ingest a project assumption with baseline value, tolerance, owner, and external data source.", inputSchema={"type": "object", "properties": {"project_id": _PROJECT_ID, "text": {"type": "string"}, "category": {"type": "string", "enum": ["COST", "SCHEDULE", "RESOURCE", "TECHNICAL", "COMMERCIAL", "REGULATORY", "STAKEHOLDER", "EXTERNAL"]}, "baseline_value": {"type": "number"}, "unit": {"type": "string"}, "tolerance_pct": {"type": "number"}, "owner": {"type": "string"}, "source": {"type": "string", "enum": ["MANUAL", "EXTERNAL_API", "DERIVED"]}, "external_ref": {"type": "string"}, "db_path": _DB_PATH}, "required": ["project_id", "text", "category", "baseline_value"]}),
        Tool(name="validate_assumption", description="OPAL-11: Validate an assumption with a new current value. Returns drift percentage and severity.", inputSchema={"type": "object", "properties": {"assumption_id": {"type": "string"}, "current_value": {"type": "number"}, "source": {"type": "string"}, "notes": {"type": "string"}, "db_path": _DB_PATH}, "required": ["assumption_id", "current_value"]}),
        Tool(name="get_assumption_drift", description="OPAL-11: Get full assumption health analysis — drift scores, stale count, cascade warnings.", inputSchema={"type": "object", "properties": {"project_id": _PROJECT_ID, "db_path": _DB_PATH}, "required": ["project_id"]}),
        Tool(name="get_cascade_impact", description="OPAL-11: Find transitive downstream assumptions affected by a breached assumption.", inputSchema={"type": "object", "properties": {"assumption_id": {"type": "string"}, "db_path": _DB_PATH}, "required": ["assumption_id"]}),
        # ===== OPAL-12: ARMM Assessment =====
        Tool(name="get_armm_report", description="OPAL-12: Retrieve ARMM maturity report — overall level (0-4), 4 dimensions, 28 topics, 251 criteria, blocking topics, improvement priorities.", inputSchema={"type": "object", "properties": {"project_id": _PROJECT_ID, "include_criteria": {"type": "boolean", "default": False}, "db_path": _DB_PATH}, "required": ["project_id"]}),
        # ===== Hackathon Tools =====
        Tool(name="create_project_from_profile", description="Create a full OPAL project from metadata. Generates 12 months of OPAL-1 to OPAL-12 data calibrated to the project's complexity domain.", inputSchema={"type": "object", "properties": {"project_id": _PROJECT_ID, "name": {"type": "string"}, "department": {"type": "string"}, "category": {"type": "string"}, "domain": {"type": "string", "enum": ["CLEAR", "COMPLICATED", "COMPLEX", "CHAOTIC"]}, "sro": {"type": "string"}, "technical_complexity": {"type": "number"}, "stakeholder_complexity": {"type": "number"}, "requirement_clarity": {"type": "number"}, "delivery_track_record": {"type": "number"}, "organisational_change": {"type": "number"}, "regulatory_exposure": {"type": "number"}, "dependency_count": {"type": "number"}, "whole_life_cost_m": {"type": "number"}, "summary": {"type": "string"}, "key_risks": {"type": "array", "items": {"type": "string"}}, "db_path": _DB_PATH}, "required": ["project_id", "name", "department", "domain"]}),
        Tool(name="export_dashboard_data", description="Export all OPAL assurance data as static JSON for the UDS Renderer.", inputSchema={"type": "object", "properties": {"project_id": _PROJECT_ID, "output_dir": {"type": "string"}, "db_path": _DB_PATH}, "required": ["project_id", "output_dir"]}),
        Tool(name="export_dashboard_html", description="Generate a self-contained TortoiseAI-branded HTML dashboard. Works offline, emailable, printable.", inputSchema={"type": "object", "properties": {"project_id": _PROJECT_ID, "project_name": {"type": "string"}, "department": {"type": "string"}, "domain": {"type": "string"}, "key_risks": {"type": "array", "items": {"type": "string"}}, "output_dir": {"type": "string"}, "db_path": _DB_PATH}, "required": ["project_id", "project_name"]}),
        # ===== PM-NISTA: GMPP Reporting =====
        Tool(name="generate_gmpp_report", description="Generate complete GMPP quarterly report from project data file.", inputSchema={"type": "object", "properties": {"project_file": {"type": "string"}, "quarter": {"type": "string", "enum": ["Q1", "Q2", "Q3", "Q4"]}, "financial_year": {"type": "string"}, "generate_narratives": {"type": "boolean", "default": True}}, "required": ["project_file", "quarter", "financial_year"]}),
        Tool(name="generate_narrative", description="Generate AI-powered narrative (DCA, cost, schedule, benefits, risk) with confidence scoring.", inputSchema={"type": "object", "properties": {"narrative_type": {"type": "string", "enum": ["dca", "cost", "schedule", "benefits", "risk"]}, "project_context": {"type": "object", "properties": {"project_name": {"type": "string"}, "department": {"type": "string"}, "dca_rating": {"type": "string"}, "baseline_cost": {"type": "number"}, "forecast_cost": {"type": "number"}, "cost_variance_percent": {"type": "number"}}, "required": ["project_name"]}}, "required": ["narrative_type", "project_context"]}),
        Tool(name="submit_to_nista", description="Submit GMPP quarterly return to NISTA API (sandbox or production).", inputSchema={"type": "object", "properties": {"report_file": {"type": "string"}, "project_id": _PROJECT_ID, "environment": {"type": "string", "enum": ["sandbox", "production"], "default": "sandbox"}}, "required": ["report_file", "project_id"]}),
        Tool(name="fetch_nista_metadata", description="Fetch project metadata from NISTA master registry.", inputSchema={"type": "object", "properties": {"project_id": _PROJECT_ID, "environment": {"type": "string", "enum": ["sandbox", "production"], "default": "sandbox"}}, "required": ["project_id"]}),
        Tool(name="validate_gmpp_report", description="Validate GMPP quarterly report against NISTA requirements.", inputSchema={"type": "object", "properties": {"report_file": {"type": "string"}, "strictness": {"type": "string", "enum": ["LENIENT", "STANDARD", "STRICT"], "default": "STANDARD"}}, "required": ["report_file"]}),
    ]


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List all 29 PDA Platform tools."""
    return _all_tool_definitions()


@app.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    """Dispatch tool calls to the correct handler."""
    handler = HANDLERS.get(name)
    if handler is None:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]
    return await handler(arguments)


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the unified PDA Platform MCP server (stdio transport)."""
    import mcp.server.stdio

    async def arun() -> None:
        async with mcp.server.stdio.stdio_server() as (read_stream, write_stream):
            await app.run(
                read_stream,
                write_stream,
                app.create_initialization_options(),
            )

    asyncio.run(arun())


if __name__ == "__main__":
    main()
