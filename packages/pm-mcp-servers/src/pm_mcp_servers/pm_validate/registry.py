"""PM-Validate tool registry for unified server aggregation."""

from __future__ import annotations

import json
import logging
from typing import Any

from mcp.types import TextContent, Tool

from pm_mcp_servers.pm_validate.tools import (
    validate_custom,
    validate_nista,
    validate_semantic,
    validate_structure,
)

logger = logging.getLogger(__name__)

TOOLS: list[Tool] = [
    Tool(
        name="validate_structure",
        description="Validate project data structure and integrity. Checks for orphan tasks, circular dependencies, invalid references, duplicate IDs, hierarchy integrity, date consistency, and assignment validity.",
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Project ID to validate",
                },
                "checks": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Specific checks to run, or ['all']",
                    "default": ["all"],
                },
            },
            "required": ["project_id"],
        },
    ),
    Tool(
        name="validate_semantic",
        description="Validate business rules and scheduling logic. Checks schedule logic, negative float, resource overallocation, constraint violations, cost consistency, baseline variance, and milestone dates.",
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Project ID to validate",
                },
                "rules": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Specific rules to check, or ['all']",
                    "default": ["all"],
                },
                "thresholds": {
                    "type": "object",
                    "description": "Custom threshold values",
                },
            },
            "required": ["project_id"],
        },
    ),
    Tool(
        name="validate_nista",
        description="Validate against NISTA Programme and Project Data Standard. Essential for UK government project compliance. Checks required fields, DCA values, and formats per NISTA specification.",
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Project ID to validate",
                },
                "schema_version": {
                    "type": "string",
                    "description": "NISTA schema version",
                    "default": "1.0",
                },
                "strictness": {
                    "type": "string",
                    "enum": ["lenient", "standard", "strict"],
                    "description": "Validation strictness level",
                    "default": "standard",
                },
            },
            "required": ["project_id"],
        },
    ),
    Tool(
        name="validate_custom",
        description="Run custom validation rules defined by the user. Supports multiple condition types for organization-specific requirements.",
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Project ID to validate",
                },
                "rules": {
                    "type": "array",
                    "items": {"type": "object"},
                    "description": "List of custom rule definitions",
                },
            },
            "required": ["project_id", "rules"],
        },
    ),
]

_TOOL_NAMES = {t.name for t in TOOLS}


async def dispatch(name: str, arguments: Any) -> list[TextContent]:
    """Dispatch a pm-validate tool call and return normalised TextContent."""
    try:
        if name == "validate_structure":
            result = await validate_structure(arguments)
        elif name == "validate_semantic":
            result = await validate_semantic(arguments)
        elif name == "validate_nista":
            result = await validate_nista(arguments)
        elif name == "validate_custom":
            result = await validate_custom(arguments)
        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

        return [TextContent(type="text", text=json.dumps(result, indent=2, default=str))]

    except Exception as exc:
        logger.exception("Error in %s: %s", name, exc)
        return [TextContent(type="text", text=f"Error: {exc}")]
