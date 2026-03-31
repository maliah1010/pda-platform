"""PM-Data tool registry for unified server aggregation."""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp.types import TextContent, Tool

from .tools import (
    convert_format,
    get_critical_path,
    get_dependencies,
    get_project_summary,
    load_project,
    query_tasks,
)

logger = logging.getLogger(__name__)

# Shared in-memory project store (session-scoped)
projects: dict[str, Any] = {}

TOOLS: list[Tool] = [
    Tool(
        name="load_project",
        description="Load a project file from various PM tools (MS Project, P6, Jira, Monday, Asana, Smartsheet, GMPP, NISTA) and return canonical representation",
        inputSchema={
            "type": "object",
            "properties": {
                "file_path": {
                    "type": "string",
                    "description": "Path to project file",
                },
                "format": {
                    "type": "string",
                    "enum": ["auto", "mspdi", "p6_xer", "jira", "monday", "asana", "smartsheet", "gmpp", "nista"],
                    "default": "auto",
                    "description": "File format (auto-detect by default)",
                },
            },
            "required": ["file_path"],
        },
    ),
    Tool(
        name="query_tasks",
        description="Query tasks with optional filters (status, critical path, milestones, assignee, dates)",
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Project identifier from load_project",
                },
                "filters": {
                    "type": "object",
                    "properties": {
                        "status": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Filter by task status",
                        },
                        "is_critical": {
                            "type": "boolean",
                            "description": "Filter critical path tasks",
                        },
                        "is_milestone": {
                            "type": "boolean",
                            "description": "Filter milestone tasks",
                        },
                        "assignee": {
                            "type": "string",
                            "description": "Filter by resource assignment",
                        },
                        "start_after": {
                            "type": "string",
                            "format": "date",
                            "description": "Filter tasks starting after date (YYYY-MM-DD)",
                        },
                        "end_before": {
                            "type": "string",
                            "format": "date",
                            "description": "Filter tasks ending before date (YYYY-MM-DD)",
                        },
                    },
                },
                "limit": {
                    "type": "integer",
                    "default": 100,
                    "description": "Maximum number of tasks to return",
                },
            },
            "required": ["project_id"],
        },
    ),
    Tool(
        name="get_critical_path",
        description="Get critical path tasks and optionally near-critical tasks (within 5 days float)",
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Project identifier",
                },
                "include_near_critical": {
                    "type": "boolean",
                    "default": False,
                    "description": "Include tasks with <=5 days float",
                },
            },
            "required": ["project_id"],
        },
    ),
    Tool(
        name="get_dependencies",
        description="Get task dependencies (predecessors/successors) for dependency analysis",
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Project identifier",
                },
                "task_id": {
                    "type": "string",
                    "description": "Specific task ID (optional, returns all if omitted)",
                },
                "direction": {
                    "type": "string",
                    "enum": ["predecessors", "successors", "both"],
                    "default": "both",
                    "description": "Direction of dependencies to return",
                },
            },
            "required": ["project_id"],
        },
    ),
    Tool(
        name="convert_format",
        description="Convert project to different format (MSPDI XML, JSON, NISTA)",
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Project identifier",
                },
                "target_format": {
                    "type": "string",
                    "enum": ["mspdi", "json", "nista_json", "nista_csv"],
                    "description": "Target format for conversion",
                },
            },
            "required": ["project_id", "target_format"],
        },
    ),
    Tool(
        name="get_project_summary",
        description="Get high-level project summary (task counts, dates, critical path length, source format)",
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Project identifier",
                },
            },
            "required": ["project_id"],
        },
    ),
]

_TOOL_NAMES = {t.name for t in TOOLS}


async def dispatch(name: str, arguments: Any) -> list[TextContent]:
    """Dispatch a pm-data tool call and return normalised TextContent."""
    try:
        if name == "load_project":
            result = await load_project(arguments, projects)
        elif name == "query_tasks":
            result = await query_tasks(arguments, projects)
        elif name == "get_critical_path":
            result = await get_critical_path(arguments, projects)
        elif name == "get_dependencies":
            result = await get_dependencies(arguments, projects)
        elif name == "convert_format":
            result = await convert_format(arguments, projects)
        elif name == "get_project_summary":
            result = await get_project_summary(arguments, projects)
        else:
            result = {"error": {"code": "UNKNOWN_TOOL", "message": f"Unknown tool: {name}"}}

        return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]

    except Exception as exc:
        logger.error("Error executing tool %s: %s", name, exc, exc_info=True)
        return [TextContent(type="text", text=json.dumps({"error": {"code": "TOOL_EXECUTION_ERROR", "message": str(exc)}}, indent=2))]
