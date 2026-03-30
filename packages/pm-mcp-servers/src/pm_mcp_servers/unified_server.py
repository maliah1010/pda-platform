"""Unified PDA Platform MCP Server.

Combines tools from pm-assure (23 tools) and pm-nista (5 tools) into
a single MCP server with 28 tools.  This is the server exposed via
the SSE web transport for remote MCP clients (claude.ai, Claude Desktop).

Provides the OPAL (Open Project Assurance Library) framework, ARMM
(Agent Readiness Maturity Model), GMPP reporting, and UDS dashboard export.

Tools are imported as private handler functions from each sub-server
and re-registered on a single Server instance.
"""

from __future__ import annotations

import asyncio
from typing import Any

from mcp.server import Server
from mcp.types import TextContent, Tool

# ---------------------------------------------------------------------------
# Imports: pm-assure handler functions (23 tools)
# ---------------------------------------------------------------------------

from pm_mcp_servers.pm_assure.server import (
    # Handler functions
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
)

# ---------------------------------------------------------------------------
# Imports: pm-nista handler functions (5 tools)
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
    # pm-assure (23)
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
    "create_project_from_profile": _create_project_from_profile,
    "export_dashboard_data": _export_dashboard_data,
    "export_dashboard_html": _export_dashboard_html,
    # pm-nista (5)
    "generate_gmpp_report": _generate_gmpp_report,
    "generate_narrative": _generate_narrative,
    "submit_to_nista": _submit_to_nista,
    "fetch_nista_metadata": _fetch_nista_metadata,
    "validate_gmpp_report": _validate_gmpp_report,
}

# ---------------------------------------------------------------------------
# Unified Server
# ---------------------------------------------------------------------------

app = Server("pda-platform")


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List all 28 PDA Platform tools."""
    # Import the tool definitions from each sub-server module.
    # We call the underlying list_tools functions to get the Tool objects.
    from pm_mcp_servers.pm_assure.server import app as assure_app
    from pm_mcp_servers.pm_nista.server import app as nista_app

    # The decorated list_tools functions are registered on each app.
    # We need to get the Tool objects. The simplest way is to import
    # the lists directly by calling the functions through the request handlers.
    # But since the handlers are async and registered via decorators, let's
    # just define the NISTA tools inline (only 5) and import assure's.

    # Get assure tools by calling the registered handler
    assure_tools: list[Tool] = []
    nista_tools: list[Tool] = []

    # Try to get tools from the registered handlers
    for handler_name, handler_map in assure_app.request_handlers.items():
        if "ListTools" in str(handler_name):
            try:
                result = await handler_map(None)  # type: ignore
                assure_tools = result.tools  # type: ignore
            except Exception:
                pass
            break

    for handler_name, handler_map in nista_app.request_handlers.items():
        if "ListTools" in str(handler_name):
            try:
                result = await handler_map(None)  # type: ignore
                nista_tools = result.tools  # type: ignore
            except Exception:
                pass
            break

    if assure_tools and nista_tools:
        return assure_tools + nista_tools

    # Fallback: define NISTA tools inline if the above didn't work
    if assure_tools and not nista_tools:
        nista_tools = _nista_tool_definitions()
        return assure_tools + nista_tools

    # If nothing worked, return just the NISTA inline definitions
    return _nista_tool_definitions()


def _nista_tool_definitions() -> list[Tool]:
    """Inline NISTA tool definitions as fallback."""
    return [
        Tool(
            name="generate_gmpp_report",
            description="Generate complete GMPP quarterly report from project data file",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_file": {"type": "string", "description": "Path to project file"},
                    "quarter": {"type": "string", "enum": ["Q1", "Q2", "Q3", "Q4"]},
                    "financial_year": {"type": "string", "description": "Financial year (format: 2025-26)"},
                    "generate_narratives": {"type": "boolean", "default": True},
                },
                "required": ["project_file", "quarter", "financial_year"],
            },
        ),
        Tool(
            name="generate_narrative",
            description="Generate AI-powered narrative with confidence scoring",
            inputSchema={
                "type": "object",
                "properties": {
                    "narrative_type": {
                        "type": "string",
                        "enum": ["dca", "cost", "schedule", "benefits", "risk"],
                    },
                    "project_context": {
                        "type": "object",
                        "description": "Project context data (project_name, dca_rating, costs, etc.)",
                        "properties": {
                            "project_name": {"type": "string"},
                            "department": {"type": "string"},
                            "dca_rating": {"type": "string"},
                            "baseline_cost": {"type": "number"},
                            "forecast_cost": {"type": "number"},
                            "cost_variance_percent": {"type": "number"},
                        },
                        "required": ["project_name"],
                    },
                },
                "required": ["narrative_type", "project_context"],
            },
        ),
        Tool(
            name="submit_to_nista",
            description="Submit GMPP quarterly return to NISTA API (sandbox or production)",
            inputSchema={
                "type": "object",
                "properties": {
                    "report_file": {"type": "string"},
                    "project_id": {"type": "string"},
                    "environment": {"type": "string", "enum": ["sandbox", "production"], "default": "sandbox"},
                },
                "required": ["report_file", "project_id"],
            },
        ),
        Tool(
            name="fetch_nista_metadata",
            description="Fetch project metadata from NISTA master registry",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_id": {"type": "string"},
                    "environment": {"type": "string", "enum": ["sandbox", "production"], "default": "sandbox"},
                },
                "required": ["project_id"],
            },
        ),
        Tool(
            name="validate_gmpp_report",
            description="Validate GMPP quarterly report against NISTA requirements",
            inputSchema={
                "type": "object",
                "properties": {
                    "report_file": {"type": "string"},
                    "strictness": {"type": "string", "enum": ["LENIENT", "STANDARD", "STRICT"], "default": "STANDARD"},
                },
                "required": ["report_file"],
            },
        ),
    ]


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
