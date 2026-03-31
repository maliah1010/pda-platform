"""PM-NISTA tool registry for unified server aggregation."""

from __future__ import annotations

from typing import Any

from mcp.types import TextContent, Tool

# Import handler functions from server module.
from .server import (
    _fetch_nista_metadata,
    _generate_gmpp_report,
    _generate_narrative,
    _submit_to_nista,
    _validate_gmpp_report,
)

TOOLS: list[Tool] = [
    Tool(
        name="generate_gmpp_report",
        description="Generate complete GMPP quarterly report from project data file",
        inputSchema={
            "type": "object",
            "properties": {
                "project_file": {
                    "type": "string",
                    "description": "Path to project file (MS Project, GMPP CSV, etc.)",
                },
                "quarter": {
                    "type": "string",
                    "enum": ["Q1", "Q2", "Q3", "Q4"],
                    "description": "Quarter period (Q1-Q4)",
                },
                "financial_year": {
                    "type": "string",
                    "pattern": "^\\d{4}-\\d{2}$",
                    "description": "Financial year (format: 2025-26)",
                },
                "generate_narratives": {
                    "type": "boolean",
                    "description": "Generate AI narratives (requires ANTHROPIC_API_KEY)",
                    "default": True,
                },
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
                    "description": "Type of narrative to generate",
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
                "report_file": {
                    "type": "string",
                    "description": "Path to quarterly report JSON file",
                },
                "project_id": {
                    "type": "string",
                    "description": "Project identifier",
                },
                "environment": {
                    "type": "string",
                    "enum": ["sandbox", "production"],
                    "description": "NISTA environment",
                    "default": "sandbox",
                },
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
                "project_id": {
                    "type": "string",
                    "description": "NISTA project code or internal project ID",
                },
                "environment": {
                    "type": "string",
                    "enum": ["sandbox", "production"],
                    "description": "NISTA environment",
                    "default": "sandbox",
                },
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
                "report_file": {
                    "type": "string",
                    "description": "Path to quarterly report JSON file",
                },
                "strictness": {
                    "type": "string",
                    "enum": ["LENIENT", "STANDARD", "STRICT"],
                    "description": "Validation strictness level",
                    "default": "STANDARD",
                },
            },
            "required": ["report_file"],
        },
    ),
]

_TOOL_NAMES = {t.name for t in TOOLS}


async def dispatch(name: str, arguments: Any) -> list[TextContent]:
    """Dispatch a pm-nista tool call. Handlers already return list[TextContent]."""
    if name == "generate_gmpp_report":
        return await _generate_gmpp_report(arguments)
    elif name == "generate_narrative":
        return await _generate_narrative(arguments)
    elif name == "submit_to_nista":
        return await _submit_to_nista(arguments)
    elif name == "fetch_nista_metadata":
        return await _fetch_nista_metadata(arguments)
    elif name == "validate_gmpp_report":
        return await _validate_gmpp_report(arguments)
    else:
        return [TextContent(type="text", text=f"Unknown tool: {name}")]
