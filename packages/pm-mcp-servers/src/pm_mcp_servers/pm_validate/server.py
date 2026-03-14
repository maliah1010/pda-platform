"""PM-Validate MCP Server

MCP server providing comprehensive validation tools for project management data.
Includes NISTA compliance checking for UK government projects.

Developed by members of the PDA Task Force to support NISTA Programme and Project Data Standard trial.
"""

import asyncio
import logging
from mcp.server import Server
from mcp.types import Tool, TextContent

from pm_mcp_servers.pm_validate.tools import (
    validate_structure,
    validate_semantic,
    validate_nista,
    validate_custom,
    check_freshness,
)

logger = logging.getLogger(__name__)

# Create MCP server
app = Server("pm-validate")


@app.list_tools()
async def list_tools() -> list[Tool]:
    """List available validation tools."""
    return [
        Tool(
            name="validate_structure",
            description="Validate project data structure and integrity. Checks for orphan tasks, circular dependencies, invalid references, duplicate IDs, hierarchy integrity, date consistency, and assignment validity.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "Project ID to validate"
                    },
                    "checks": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Specific checks to run, or ['all']",
                        "default": ["all"]
                    }
                },
                "required": ["project_id"]
            }
        ),
        Tool(
            name="validate_semantic",
            description="Validate business rules and scheduling logic. Checks schedule logic, negative float, resource overallocation, constraint violations, cost consistency, baseline variance, and milestone dates.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "Project ID to validate"
                    },
                    "rules": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Specific rules to check, or ['all']",
                        "default": ["all"]
                    },
                    "thresholds": {
                        "type": "object",
                        "description": "Custom threshold values"
                    }
                },
                "required": ["project_id"]
            }
        ),
        Tool(
            name="validate_nista",
            description="Validate against NISTA Programme and Project Data Standard. Essential for UK government project compliance. Checks required fields, DCA values, and formats per NISTA specification.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "Project ID to validate"
                    },
                    "schema_version": {
                        "type": "string",
                        "description": "NISTA schema version",
                        "default": "1.0"
                    },
                    "strictness": {
                        "type": "string",
                        "enum": ["lenient", "standard", "strict"],
                        "description": "Validation strictness level",
                        "default": "standard"
                    }
                },
                "required": ["project_id"]
            }
        ),
        Tool(
            name="validate_custom",
            description="Run custom validation rules defined by the user. Supports multiple condition types for organization-specific requirements.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project_id": {
                        "type": "string",
                        "description": "Project ID to validate"
                    },
                    "rules": {
                        "type": "array",
                        "items": {"type": "object"},
                        "description": "List of custom rule definitions"
                    }
                },
                "required": ["project_id", "rules"]
            }
        ),
        Tool(
            name="check_freshness",
            description=(
                "Analyse evidence freshness of a project management file or evidence pack "
                "(directory). Returns a freshness score (0–100), RAG status (green/amber/red), "
                "and structured alerts for stale documents, suspicious burst editing ('fresh paint'), "
                "missing provenance, and documents at version 1 with no revision history. "
                "Supports all eight PM formats: MS Project XML, Primavera P6, Jira, Monday, "
                "Asana, Smartsheet, GMPP, and NISTA."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "file_path": {
                        "type": "string",
                        "description": "Absolute path to the file or directory to analyse."
                    },
                    "file_format": {
                        "type": "string",
                        "enum": [
                            "mspdi", "p6_xer", "nista", "jira",
                            "monday", "asana", "smartsheet", "gmpp"
                        ],
                        "description": "Force a specific format (auto-detected when omitted)."
                    },
                    "gate_date": {
                        "type": "string",
                        "description": (
                            "ISO-8601 gate/review date for fresh-paint detection "
                            "(e.g. '2026-04-01'). When set, burst editing immediately "
                            "before this date is flagged."
                        )
                    },
                    "fresh_threshold_days": {
                        "type": "integer",
                        "description": "Days within which a document is green (default 30).",
                        "default": 30
                    },
                    "stale_threshold_days": {
                        "type": "integer",
                        "description": "Days beyond which a document is red (default 90).",
                        "default": 90
                    },
                    "recursive": {
                        "type": "boolean",
                        "description": "Scan sub-directories when file_path is a directory.",
                        "default": False
                    }
                },
                "required": ["file_path"]
            }
        ),
    ]


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Execute a validation tool."""
    try:
        if name == "validate_structure":
            result = await validate_structure(arguments)
        elif name == "validate_semantic":
            result = await validate_semantic(arguments)
        elif name == "validate_nista":
            result = await validate_nista(arguments)
        elif name == "validate_custom":
            result = await validate_custom(arguments)
        elif name == "check_freshness":
            result = await check_freshness(arguments)
        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]
        
        import json
        return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]
    
    except Exception as e:
        logger.exception(f"Error in {name}: {e}")
        return [TextContent(type="text", text=f"Error: {str(e)}")]


async def main():
    """Run the MCP server."""
    from mcp.server.stdio import stdio_server
    
    async with stdio_server() as (read_stream, write_stream):
        await app.run(
            read_stream,
            write_stream,
            app.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())
