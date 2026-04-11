"""pm_knowledge — pre-loaded UK government project delivery knowledge base.

Five tools:
  1. list_knowledge_categories   — discover what's available
  2. get_benchmark_data          — cost/schedule/DCA benchmarks by project type
  3. get_failure_patterns        — common failure modes with indicators and mitigations
  4. get_ipa_guidance            — IPA/HMT/Cabinet Office guidance references
  5. search_knowledge_base       — full-text search across all knowledge
"""

from __future__ import annotations

import json
from typing import Any

from mcp.server import Server
from mcp.types import TextContent, Tool

from .knowledge_base import (
    BENCHMARK_DATA,
    FAILURE_PATTERNS,
    GUIDANCE_REFERENCES,
    KNOWLEDGE_CATEGORIES,
)

server = Server("pm-knowledge")

KNOWLEDGE_TOOLS: list[Tool] = [
    Tool(
        name="list_knowledge_categories",
        description=(
            "List all categories of pre-loaded knowledge available in the PDA Platform knowledge base. "
            "Returns benchmark data types (cost overrun, schedule slip, DCA distributions by project type), "
            "failure pattern domains and gate stages, and IPA/HMT guidance topics. "
            "Use this to discover what is available before calling other knowledge tools."
        ),
        inputSchema={
            "type": "object",
            "properties": {},
        },
    ),
    Tool(
        name="get_benchmark_data",
        description=(
            "Retrieve statistical benchmark data for a specific project type and metric. "
            "Sources: IPA Annual Reports 2019-2024, NAO reports, GMPP data. "
            "Project types: IT_AND_DIGITAL, INFRASTRUCTURE, DEFENCE, HEALTH_AND_SOCIAL_CARE, CROSS_GOVERNMENT. "
            "Metrics: cost_overrun (mean/median/P80 %), schedule_slip (mean/median/P80 months, % late), "
            "dca_distribution (% at each DCA rating), common_overrun_drivers (list), "
            "optimism_bias_reference (HMT Green Book uplift ranges — CROSS_GOVERNMENT only)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "project_type": {
                    "type": "string",
                    "enum": ["IT_AND_DIGITAL", "INFRASTRUCTURE", "DEFENCE", "HEALTH_AND_SOCIAL_CARE", "CROSS_GOVERNMENT"],
                    "description": "Project type to retrieve benchmarks for.",
                },
                "metric": {
                    "type": "string",
                    "enum": ["cost_overrun", "schedule_slip", "dca_distribution", "common_overrun_drivers", "optimism_bias_reference", "all"],
                    "description": "Metric to retrieve. Use 'all' for the complete benchmark profile.",
                },
            },
            "required": ["project_type", "metric"],
        },
    ),
    Tool(
        name="get_failure_patterns",
        description=(
            "Retrieve common failure patterns identified by IPA and NAO research. "
            "Each pattern includes: description, early warning indicators, mitigation strategies, "
            "and IPA/NAO source references. "
            "Filter by domain (ALL, IT_AND_DIGITAL, INFRASTRUCTURE, DEFENCE, HEALTH_AND_SOCIAL_CARE) "
            "and/or gate stage (GATE_0 through GATE_5). "
            "Use this to cross-reference observed project indicators against known failure modes."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "enum": ["ALL", "IT_AND_DIGITAL", "INFRASTRUCTURE", "DEFENCE", "HEALTH_AND_SOCIAL_CARE"],
                    "description": "Filter by project domain. 'ALL' returns patterns applicable to all domains.",
                },
                "gate": {
                    "type": "string",
                    "enum": ["GATE_0", "GATE_1", "GATE_2", "GATE_3", "GATE_4", "GATE_5", "ANY"],
                    "description": "Filter by gate stage relevance. 'ANY' returns all patterns.",
                },
            },
            "required": [],
        },
    ),
    Tool(
        name="get_ipa_guidance",
        description=(
            "Retrieve IPA, HM Treasury, or Cabinet Office guidance references on a specific topic. "
            "Topics: optimism_bias, green_book, cabinet_office_controls, ipa_annual_report, "
            "gmpp_reporting, benefits_management, schedule_management, project_delivery_functional_standard. "
            "Returns: summary, key thresholds/principles, and source URL. "
            "Use to cite authoritative guidance when making recommendations or assessing compliance."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "enum": [
                        "optimism_bias",
                        "green_book",
                        "cabinet_office_controls",
                        "ipa_annual_report",
                        "gmpp_reporting",
                        "benefits_management",
                        "schedule_management",
                        "project_delivery_functional_standard",
                        "all",
                    ],
                    "description": "Guidance topic to retrieve. Use 'all' for a full index.",
                },
            },
            "required": ["topic"],
        },
    ),
    Tool(
        name="search_knowledge_base",
        description=(
            "Full-text search across all knowledge in the PDA Platform knowledge base: "
            "benchmark data, failure patterns, and IPA/HMT guidance. "
            "Returns ranked results with the most relevant entries first. "
            "Use this when you are not sure which specific tool to call, or when you want "
            "to find all knowledge relevant to a topic (e.g. 'supplier risk', 'benefits owner', 'schedule float')."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query. Can be a keyword, phrase, or question.",
                },
                "category": {
                    "type": "string",
                    "enum": ["benchmark_data", "failure_patterns", "ipa_guidance", "all"],
                    "description": "Restrict search to a specific category. Default: 'all'.",
                    "default": "all",
                },
            },
            "required": ["query"],
        },
    ),
]


# ── Handlers ──────────────────────────────────────────────────────────────────

async def _list_knowledge_categories(_arguments: dict[str, Any]) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps(KNOWLEDGE_CATEGORIES, indent=2))]


async def _get_benchmark_data(arguments: dict[str, Any]) -> list[TextContent]:
    project_type = arguments["project_type"]
    metric = arguments["metric"]

    data = BENCHMARK_DATA.get(project_type)
    if not data:
        return [TextContent(type="text", text=json.dumps({"error": f"No benchmark data for project type: {project_type}"}))]

    if metric == "all":
        result = {"project_type": project_type, "benchmarks": data}
    else:
        metric_data = data.get(metric)
        if metric_data is None:
            available = list(data.keys())
            return [TextContent(type="text", text=json.dumps({
                "error": f"Metric '{metric}' not available for {project_type}",
                "available_metrics": available,
            }))]
        result = {"project_type": project_type, "metric": metric, "data": metric_data}

    return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def _get_failure_patterns(arguments: dict[str, Any]) -> list[TextContent]:
    domain = arguments.get("domain", "ALL")
    gate = arguments.get("gate", "ANY")

    patterns = FAILURE_PATTERNS

    if domain != "ALL":
        patterns = [p for p in patterns if domain in p["domains"] or "ALL" in p["domains"]]

    if gate != "ANY":
        patterns = [p for p in patterns if gate in p["gates"]]

    result = {
        "filters": {"domain": domain, "gate": gate},
        "count": len(patterns),
        "patterns": patterns,
    }
    return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def _get_ipa_guidance(arguments: dict[str, Any]) -> list[TextContent]:
    topic = arguments["topic"]

    if topic == "all":
        index = [{"id": g["id"], "topic": g["topic"], "title": g["title"], "publisher": g["publisher"], "year": g["year"]} for g in GUIDANCE_REFERENCES]
        result = {"count": len(index), "guidance_index": index}
    else:
        matches = [g for g in GUIDANCE_REFERENCES if g["topic"] == topic]
        if not matches:
            available = [g["topic"] for g in GUIDANCE_REFERENCES]
            return [TextContent(type="text", text=json.dumps({"error": f"No guidance found for topic: {topic}", "available_topics": available}))]
        result = {"count": len(matches), "guidance": matches}

    return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def _search_knowledge_base(arguments: dict[str, Any]) -> list[TextContent]:
    query = arguments["query"].lower()
    category = arguments.get("category", "all")
    results: list[dict] = []

    def score(text: str) -> int:
        words = query.split()
        return sum(1 for w in words if w in text.lower())

    if category in ("all", "failure_patterns"):
        for p in FAILURE_PATTERNS:
            searchable = " ".join([
                p["name"], p["description"],
                " ".join(p["indicators"]),
                p["mitigation"],
                " ".join(p["domains"]),
            ])
            s = score(searchable)
            if s > 0:
                results.append({"category": "failure_pattern", "score": s, "id": p["id"], "name": p["name"], "description": p["description"][:200] + "...", "indicators_count": len(p["indicators"])})

    if category in ("all", "ipa_guidance"):
        for g in GUIDANCE_REFERENCES:
            searchable = " ".join([g["topic"], g["title"], g["summary"]])
            s = score(searchable)
            if s > 0:
                results.append({"category": "ipa_guidance", "score": s, "id": g["id"], "topic": g["topic"], "title": g["title"], "summary": g["summary"][:200] + "..."})

    if category in ("all", "benchmark_data"):
        for ptype, metrics in BENCHMARK_DATA.items():
            for mname, mdata in metrics.items():
                searchable = ptype + " " + mname + " " + str(mdata)
                s = score(searchable)
                if s > 0:
                    results.append({"category": "benchmark_data", "score": s, "project_type": ptype, "metric": mname, "preview": str(mdata)[:150]})

    results.sort(key=lambda x: x["score"], reverse=True)
    results = results[:10]

    return [TextContent(type="text", text=json.dumps({"query": arguments["query"], "category": category, "count": len(results), "results": results}, indent=2))]


# ── MCP handlers ──────────────────────────────────────────────────────────────

@server.list_tools()
async def list_tools() -> list[Tool]:
    return KNOWLEDGE_TOOLS


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, Any]) -> list[TextContent]:
    handlers = {
        "list_knowledge_categories": _list_knowledge_categories,
        "get_benchmark_data": _get_benchmark_data,
        "get_failure_patterns": _get_failure_patterns,
        "get_ipa_guidance": _get_ipa_guidance,
        "search_knowledge_base": _search_knowledge_base,
    }
    handler = handlers.get(name)
    if not handler:
        return [TextContent(type="text", text=json.dumps({"error": f"Unknown tool: {name}"}))]
    return await handler(arguments)


def main() -> None:
    import asyncio
    from mcp.server.stdio import stdio_server
    async def _run() -> None:
        async with stdio_server() as (r, w):
            await server.run(r, w, server.create_initialization_options())
    asyncio.run(_run())


if __name__ == "__main__":
    main()
