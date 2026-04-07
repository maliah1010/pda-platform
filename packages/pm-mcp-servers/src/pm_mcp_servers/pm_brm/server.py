"""PM-BRM MCP server — Benefits Realisation Management tools.

Phase 1 tools:
  1. ingest_benefit         — Register a benefit with full IPA/Green Book metadata
  2. track_benefit_measurement — Record a measurement and compute drift/trend
  3. get_benefits_health    — Portfolio-level health assessment

Phase 2 tools (dependency network):
  4. map_benefit_dependency — Add nodes/edges to the DAG
  5. get_benefit_dependency_network — Retrieve the full DAG
  8. get_benefits_cascade_impact — Propagate change through the DAG

Phase 3 tools (AI/predictive):
  6. forecast_benefit_realisation — Linear extrapolation forecast
  7. detect_benefits_drift — Time-series drift detection

Phase 4 tools (maturity & narratives):
  9. generate_benefits_narrative — IPA gate-specific assurance narratives
 10. assess_benefits_maturity — P3M3 maturity scoring
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mcp.types import TextContent, Tool

# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------

BRM_TOOLS: list[Tool] = [
    # ------------------------------------------------------------------
    # Phase 1: MVP
    # ------------------------------------------------------------------
    Tool(
        name="ingest_benefit",
        description=(
            "Register a benefit or dis-benefit with full IPA/Green Book-compliant "
            "metadata. Validates that the benefit has the minimum required fields. "
            "Supports multi-axis classification: financial type (Green Book), "
            "recipient (IPA), and explicitness (Ward & Daniel)."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Project identifier.",
                },
                "title": {
                    "type": "string",
                    "description": "Clear, concise name of the benefit.",
                },
                "description": {
                    "type": "string",
                    "description": (
                        "Detailed narrative passing the MSP DOAM test: "
                        "Described, Observable, Attributable, Measurable."
                    ),
                },
                "financial_type": {
                    "type": "string",
                    "enum": [
                        "CASH_RELEASING",
                        "NON_CASH_RELEASING",
                        "QUANTIFIABLE",
                        "QUALITATIVE",
                    ],
                    "description": "Green Book financial classification.",
                },
                "recipient_type": {
                    "type": "string",
                    "enum": ["GOVERNMENT", "PRIVATE_SECTOR", "WIDER_UK_PUBLIC"],
                    "description": "IPA benefit recipient taxonomy.",
                },
                "is_disbenefit": {
                    "type": "boolean",
                    "description": "True if this is a negative consequence.",
                    "default": False,
                },
                "baseline_value": {
                    "type": "number",
                    "description": "Current performance state before change.",
                },
                "baseline_date": {
                    "type": "string",
                    "description": "ISO date when baseline was established.",
                },
                "target_value": {
                    "type": "number",
                    "description": "Desired end-state performance level.",
                },
                "target_date": {
                    "type": "string",
                    "description": "ISO date deadline for achieving the target.",
                },
                "measurement_kpi": {
                    "type": "string",
                    "description": "Specific metric used for tracking.",
                },
                "measurement_frequency": {
                    "type": "string",
                    "enum": ["MONTHLY", "QUARTERLY", "ANNUALLY"],
                    "description": "How often the benefit is measured.",
                    "default": "QUARTERLY",
                },
                "indicator_type": {
                    "type": "string",
                    "enum": ["LEADING", "LAGGING"],
                    "description": "Whether this is a leading or lagging indicator.",
                    "default": "LAGGING",
                },
                "explicitness": {
                    "type": "string",
                    "enum": ["FINANCIAL", "QUANTIFIABLE", "MEASURABLE", "OBSERVABLE"],
                    "description": "Ward & Daniel explicitness taxonomy.",
                    "default": "QUANTIFIABLE",
                },
                "owner_sro": {
                    "type": "string",
                    "description": "Senior Responsible Owner.",
                },
                "benefits_owner": {
                    "type": "string",
                    "description": "Operational owner post-BAU transition.",
                },
                "ipa_lifecycle_stage": {
                    "type": "string",
                    "enum": [
                        "DEFINE_SUCCESS",
                        "IDENTIFY_QUANTIFY",
                        "VALUE_APPRAISE",
                        "PLAN_REALISE",
                        "REVIEW",
                    ],
                    "description": "Current IPA lifecycle stage.",
                    "default": "IDENTIFY_QUANTIFY",
                },
                "interim_targets": {
                    "type": "array",
                    "description": (
                        "Time-phased expected values for ramp-up/tail-off. "
                        'Each element: {"date": "YYYY-MM-DD", "value": number}.'
                    ),
                    "items": {"type": "object"},
                },
                "contributing_projects": {
                    "type": "array",
                    "description": "IDs of projects contributing to this benefit.",
                    "items": {"type": "string"},
                },
                "associated_assumptions": {
                    "type": "array",
                    "description": "IDs of linked assumption tracker entries.",
                    "items": {"type": "string"},
                },
                "associated_risks": {
                    "type": "array",
                    "description": "IDs of linked risk register entries.",
                    "items": {"type": "string"},
                },
                "business_case_ref": {
                    "type": "string",
                    "description": "Business case document reference.",
                },
                "db_path": {
                    "type": "string",
                    "description": (
                        "Optional path to the SQLite store. "
                        "Defaults to ~/.pm_data_tools/store.db"
                    ),
                },
            },
            "required": [
                "project_id",
                "title",
                "description",
                "financial_type",
                "recipient_type",
            ],
        },
    ),
    Tool(
        name="track_benefit_measurement",
        description=(
            "Record a measurement against a registered benefit at a point in time. "
            "Computes realisation percentage, drift from baseline, trend direction, "
            "and drift severity classification."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "benefit_id": {
                    "type": "string",
                    "description": "ID of the benefit to measure.",
                },
                "value": {
                    "type": "number",
                    "description": "The measured value.",
                },
                "source": {
                    "type": "string",
                    "enum": ["MANUAL", "EXTERNAL_API", "DERIVED"],
                    "description": "Where the value came from.",
                    "default": "MANUAL",
                },
                "notes": {
                    "type": "string",
                    "description": "Optional notes about this measurement.",
                },
                "db_path": {
                    "type": "string",
                    "description": (
                        "Optional path to the SQLite store. "
                        "Defaults to ~/.pm_data_tools/store.db"
                    ),
                },
            },
            "required": ["benefit_id", "value"],
        },
    ),
    Tool(
        name="get_benefits_health",
        description=(
            "Portfolio-level health assessment for a project's benefits. "
            "Returns realisation rates, at-risk benefits, stale measurements, "
            "overall health score (0.0-1.0), and leading indicator warnings. "
            "Flags benefits where leading indicators predict lagging indicator failure."
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
                    "enum": [
                        "IDENTIFIED",
                        "PLANNED",
                        "REALIZING",
                        "ACHIEVED",
                        "EVAPORATED",
                        "CANCELLED",
                    ],
                    "description": "Optional status to filter by.",
                },
                "db_path": {
                    "type": "string",
                    "description": (
                        "Optional path to the SQLite store. "
                        "Defaults to ~/.pm_data_tools/store.db"
                    ),
                },
            },
            "required": ["project_id"],
        },
    ),
    # ------------------------------------------------------------------
    # Phase 2: Dependency Network
    # ------------------------------------------------------------------
    Tool(
        name="map_benefit_dependency",
        description=(
            "Create nodes and a typed edge in the benefits dependency DAG. "
            "Supports six node types: STRATEGIC_OBJECTIVE, END_BENEFIT, "
            "INTERMEDIATE_BENEFIT, BUSINESS_CHANGE, ENABLER, PROJECT_OUTPUT. "
            "Validates DAG acyclicity before persisting."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Project identifier.",
                },
                "source_node_id": {
                    "type": "string",
                    "description": "ID of the source node (must exist or be created inline).",
                },
                "target_node_id": {
                    "type": "string",
                    "description": "ID of the target node (must exist or be created inline).",
                },
                "edge_type": {
                    "type": "string",
                    "enum": ["DEPENDS_ON", "CONTRIBUTES_TO", "ENABLES"],
                    "description": "Relationship type.",
                    "default": "DEPENDS_ON",
                },
                "source_node": {
                    "type": "object",
                    "description": (
                        "Optional: create the source node inline. "
                        "Required fields: node_type, title."
                    ),
                },
                "target_node": {
                    "type": "object",
                    "description": (
                        "Optional: create the target node inline. "
                        "Required fields: node_type, title."
                    ),
                },
                "assumption_id": {
                    "type": "string",
                    "description": "Links this edge to an assumption tracker entry.",
                },
                "risk_id": {
                    "type": "string",
                    "description": "Links this edge to a risk register entry.",
                },
                "notes": {
                    "type": "string",
                    "description": "Optional notes about this relationship.",
                },
                "db_path": {
                    "type": "string",
                    "description": (
                        "Optional path to the SQLite store. "
                        "Defaults to ~/.pm_data_tools/store.db"
                    ),
                },
            },
            "required": ["project_id", "source_node_id", "target_node_id", "edge_type"],
        },
    ),
    Tool(
        name="get_benefit_dependency_network",
        description=(
            "Return the full or filtered dependency graph for a project. "
            "Includes all nodes with their types and statuses, all edges "
            "with relationship types, and optional health propagation data."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Project identifier.",
                },
                "node_type_filter": {
                    "type": "string",
                    "enum": [
                        "STRATEGIC_OBJECTIVE",
                        "END_BENEFIT",
                        "INTERMEDIATE_BENEFIT",
                        "BUSINESS_CHANGE",
                        "ENABLER",
                        "PROJECT_OUTPUT",
                    ],
                    "description": "Optional filter to return only nodes of this type.",
                },
                "db_path": {
                    "type": "string",
                    "description": (
                        "Optional path to the SQLite store. "
                        "Defaults to ~/.pm_data_tools/store.db"
                    ),
                },
            },
            "required": ["project_id"],
        },
    ),
    Tool(
        name="forecast_benefit_realisation",
        description=(
            "Project forward based on current measurement trajectory using "
            "linear extrapolation. Returns the projected value at target date "
            "and estimated probability of achieving the target."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "benefit_id": {
                    "type": "string",
                    "description": "ID of the benefit to forecast.",
                },
                "db_path": {
                    "type": "string",
                    "description": (
                        "Optional path to the SQLite store. "
                        "Defaults to ~/.pm_data_tools/store.db"
                    ),
                },
            },
            "required": ["benefit_id"],
        },
    ),
    Tool(
        name="detect_benefits_drift",
        description=(
            "Time-series analysis on measurement data detecting statistically "
            "significant deviations from planned realisation profiles. "
            "Returns drift severity per benefit, ordered worst-first."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Project identifier.",
                },
                "severity_filter": {
                    "type": "string",
                    "enum": ["NONE", "MINOR", "MODERATE", "SIGNIFICANT", "CRITICAL"],
                    "description": "Optional: return only benefits at this severity or worse.",
                },
                "db_path": {
                    "type": "string",
                    "description": (
                        "Optional path to the SQLite store. "
                        "Defaults to ~/.pm_data_tools/store.db"
                    ),
                },
            },
            "required": ["project_id"],
        },
    ),
    Tool(
        name="get_benefits_cascade_impact",
        description=(
            "Given a node in the dependency network, propagate through the DAG "
            "and return all affected downstream nodes with their types and depth "
            "from the source node."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "node_id": {
                    "type": "string",
                    "description": "ID of the starting node.",
                },
                "db_path": {
                    "type": "string",
                    "description": (
                        "Optional path to the SQLite store. "
                        "Defaults to ~/.pm_data_tools/store.db"
                    ),
                },
            },
            "required": ["node_id"],
        },
    ),
    # ------------------------------------------------------------------
    # Phase 4: Maturity & Narratives
    # ------------------------------------------------------------------
    Tool(
        name="generate_benefits_narrative",
        description=(
            "Generate an IPA-compliant benefits assurance narrative for gate reviews. "
            "Builds rich context from the benefits register and uses the existing "
            "NarrativeGenerator with multi-sample AI consensus and confidence scoring. "
            "Requires ANTHROPIC_API_KEY environment variable."
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "project_id": {
                    "type": "string",
                    "description": "Project identifier.",
                },
                "gate_number": {
                    "type": "integer",
                    "description": (
                        "IPA gate number (0-5) for gate-specific probe questions. "
                        "0=Opportunity Framing, 1=SOC, 2=OBC, 3=FBC, "
                        "4=Work to Realise, 5=Benefits Review."
                    ),
                    "minimum": 0,
                    "maximum": 5,
                },
                "db_path": {
                    "type": "string",
                    "description": (
                        "Optional path to the SQLite store. "
                        "Defaults to ~/.pm_data_tools/store.db"
                    ),
                },
            },
            "required": ["project_id"],
        },
    ),
    Tool(
        name="assess_benefits_maturity",
        description=(
            "Score a project's benefits management maturity against P3M3-aligned "
            "criteria (Level 1-5). Evaluates data completeness, process maturity, "
            "dependency mapping, and measurement tracking. Returns maturity level "
            "with evidence gaps and improvement recommendations."
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
                    "description": (
                        "Optional path to the SQLite store. "
                        "Defaults to ~/.pm_data_tools/store.db"
                    ),
                },
            },
            "required": ["project_id"],
        },
    ),
]


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


def _get_store(arguments: dict[str, Any]) -> Any:
    """Create an AssuranceStore from optional db_path argument."""
    from pm_data_tools.db.store import AssuranceStore

    raw_db_path = arguments.get("db_path")
    db_path = Path(raw_db_path) if raw_db_path else None
    return AssuranceStore(db_path=db_path)


def _get_tracker(arguments: dict[str, Any]) -> Any:
    """Create a BenefitsTracker from optional db_path argument."""
    from pm_data_tools.assurance.benefits import BenefitsTracker

    store = _get_store(arguments)
    return BenefitsTracker(store=store)


async def _ingest_benefit(arguments: dict[str, Any]) -> list[TextContent]:
    """Register a benefit with full metadata."""
    try:
        from pm_data_tools.assurance.benefits import (
            Benefit,
            Explicitness,
            FinancialType,
            IndicatorType,
            IpaLifecycleStage,
            MeasurementFrequency,
            RecipientType,
        )

        tracker = _get_tracker(arguments)

        benefit = Benefit(
            project_id=arguments["project_id"],
            title=arguments["title"],
            description=arguments["description"],
            financial_type=FinancialType(arguments["financial_type"]),
            recipient_type=RecipientType(arguments["recipient_type"]),
            is_disbenefit=arguments.get("is_disbenefit", False),
            explicitness=Explicitness(
                arguments.get("explicitness", "QUANTIFIABLE")
            ),
            baseline_value=arguments.get("baseline_value"),
            baseline_date=arguments.get("baseline_date"),
            target_value=arguments.get("target_value"),
            target_date=arguments.get("target_date"),
            measurement_kpi=arguments.get("measurement_kpi"),
            measurement_frequency=MeasurementFrequency(
                arguments.get("measurement_frequency", "QUARTERLY")
            ),
            indicator_type=IndicatorType(
                arguments.get("indicator_type", "LAGGING")
            ),
            owner_sro=arguments.get("owner_sro"),
            benefits_owner=arguments.get("benefits_owner"),
            ipa_lifecycle_stage=IpaLifecycleStage(
                arguments.get("ipa_lifecycle_stage", "IDENTIFY_QUANTIFY")
            ),
            interim_targets=arguments.get("interim_targets", []),
            contributing_projects=arguments.get("contributing_projects", []),
            associated_assumptions=arguments.get("associated_assumptions", []),
            associated_risks=arguments.get("associated_risks", []),
            business_case_ref=arguments.get("business_case_ref"),
        )

        result = tracker.ingest(benefit)

        output = {
            "status": "success",
            "benefit_id": result.id,
            "project_id": result.project_id,
            "title": result.title,
            "is_disbenefit": result.is_disbenefit,
            "financial_type": result.financial_type.value,
            "recipient_type": result.recipient_type.value,
            "message": (
                f"{'Dis-benefit' if result.is_disbenefit else 'Benefit'} "
                f"'{result.title}' registered successfully."
            ),
        }

        return [TextContent(type="text", text=json.dumps(output, indent=2, default=str))]

    except Exception as exc:
        return [TextContent(type="text", text=f"Error: {exc}")]


async def _track_benefit_measurement(
    arguments: dict[str, Any],
) -> list[TextContent]:
    """Record a measurement against a benefit."""
    try:
        from pm_data_tools.assurance.benefits import MeasurementSource

        tracker = _get_tracker(arguments)
        source = MeasurementSource(arguments.get("source", "MANUAL"))

        measurement = tracker.record_measurement(
            benefit_id=arguments["benefit_id"],
            value=arguments["value"],
            source=source,
            notes=arguments.get("notes"),
        )

        output = {
            "status": "success",
            "measurement_id": measurement.id,
            "benefit_id": measurement.benefit_id,
            "value": measurement.value,
            "drift_pct": round(measurement.drift_pct, 2),
            "drift_severity": measurement.drift_severity.value,
            "realisation_pct": (
                round(measurement.realisation_pct, 1)
                if measurement.realisation_pct is not None
                else None
            ),
            "trend_direction": (
                measurement.trend_direction.value
                if measurement.trend_direction
                else None
            ),
            "message": (
                f"Measurement recorded: {measurement.value}. "
                f"Drift: {measurement.drift_pct:.1f}% ({measurement.drift_severity.value})."
            ),
        }

        return [TextContent(type="text", text=json.dumps(output, indent=2, default=str))]

    except Exception as exc:
        return [TextContent(type="text", text=f"Error: {exc}")]


async def _get_benefits_health(arguments: dict[str, Any]) -> list[TextContent]:
    """Portfolio-level health assessment."""
    try:
        tracker = _get_tracker(arguments)
        report = tracker.analyse_health(arguments["project_id"])

        output = {
            "project_id": report.project_id,
            "timestamp": report.timestamp.isoformat(),
            "total_benefits": report.total_benefits,
            "total_disbenefits": report.total_disbenefits,
            "by_status": report.by_status,
            "by_financial_type": report.by_financial_type,
            "by_recipient": report.by_recipient,
            "stale_count": report.stale_count,
            "at_risk_count": report.at_risk_count,
            "aggregate_realisation_pct": round(report.aggregate_realisation_pct, 1),
            "overall_health_score": round(report.overall_health_score, 3),
            "leading_indicator_warnings": report.leading_indicator_warnings,
            "drift_results": [
                {
                    "benefit_id": dr.benefit.id,
                    "title": dr.benefit.title,
                    "drift_pct": round(dr.drift_pct, 2),
                    "severity": dr.severity.value,
                    "trend": dr.trend.value,
                    "realisation_pct": (
                        round(dr.realisation_pct, 1)
                        if dr.realisation_pct is not None
                        else None
                    ),
                    "days_since_measurement": dr.days_since_measurement,
                    "message": dr.message,
                }
                for dr in report.drift_results
            ],
            "message": report.message,
        }

        return [TextContent(type="text", text=json.dumps(output, indent=2, default=str))]

    except Exception as exc:
        return [TextContent(type="text", text=f"Error: {exc}")]


async def _map_benefit_dependency(
    arguments: dict[str, Any],
) -> list[TextContent]:
    """Create nodes and edge in the dependency DAG."""
    try:
        from pm_data_tools.assurance.benefits import (
            DependencyEdge,
            DependencyNode,
            EdgeType,
            NodeType,
        )

        tracker = _get_tracker(arguments)
        project_id = arguments["project_id"]

        # Create inline source node if provided
        if arguments.get("source_node"):
            sn = arguments["source_node"]
            tracker.add_node(
                DependencyNode(
                    id=arguments["source_node_id"],
                    project_id=project_id,
                    node_type=NodeType(sn["node_type"]),
                    title=sn["title"],
                    description=sn.get("description"),
                    owner=sn.get("owner"),
                    benefit_id=sn.get("benefit_id"),
                )
            )

        # Create inline target node if provided
        if arguments.get("target_node"):
            tn = arguments["target_node"]
            tracker.add_node(
                DependencyNode(
                    id=arguments["target_node_id"],
                    project_id=project_id,
                    node_type=NodeType(tn["node_type"]),
                    title=tn["title"],
                    description=tn.get("description"),
                    owner=tn.get("owner"),
                    benefit_id=tn.get("benefit_id"),
                )
            )

        # Create edge
        edge = tracker.add_edge(
            DependencyEdge(
                project_id=project_id,
                source_node=arguments["source_node_id"],
                target_node=arguments["target_node_id"],
                edge_type=EdgeType(arguments.get("edge_type", "DEPENDS_ON")),
                assumption_id=arguments.get("assumption_id"),
                risk_id=arguments.get("risk_id"),
                notes=arguments.get("notes"),
            )
        )

        output = {
            "status": "success",
            "edge_id": edge.id,
            "source_node": edge.source_node,
            "target_node": edge.target_node,
            "edge_type": edge.edge_type.value,
            "message": (
                f"Dependency edge created: {edge.source_node} "
                f"--[{edge.edge_type.value}]--> {edge.target_node}."
            ),
        }

        return [TextContent(type="text", text=json.dumps(output, indent=2, default=str))]

    except ValueError as ve:
        return [TextContent(type="text", text=f"Validation error: {ve}")]
    except Exception as exc:
        return [TextContent(type="text", text=f"Error: {exc}")]


async def _get_benefit_dependency_network(
    arguments: dict[str, Any],
) -> list[TextContent]:
    """Return the full dependency graph."""
    try:
        tracker = _get_tracker(arguments)
        network = tracker.get_network(arguments["project_id"])

        # Apply optional node_type filter
        node_type_filter = arguments.get("node_type_filter")
        if node_type_filter:
            network["nodes"] = [
                n for n in network["nodes"] if n.get("node_type") == node_type_filter
            ]

        output = {
            "project_id": arguments["project_id"],
            "node_count": len(network["nodes"]),
            "edge_count": len(network["edges"]),
            "nodes": network["nodes"],
            "edges": network["edges"],
        }

        return [TextContent(type="text", text=json.dumps(output, indent=2, default=str))]

    except Exception as exc:
        return [TextContent(type="text", text=f"Error: {exc}")]


async def _forecast_benefit_realisation(
    arguments: dict[str, Any],
) -> list[TextContent]:
    """Forecast benefit realisation."""
    try:
        tracker = _get_tracker(arguments)
        forecast = tracker.forecast(arguments["benefit_id"])

        output = {
            "benefit_id": forecast.benefit_id,
            "title": forecast.title,
            "target_value": forecast.target_value,
            "target_date": forecast.target_date.isoformat(),
            "current_trajectory_value": round(forecast.current_trajectory_value, 2),
            "probability_of_realisation": round(forecast.probability_of_realisation, 3),
            "forecast_method": forecast.forecast_method,
            "message": forecast.message,
        }

        return [TextContent(type="text", text=json.dumps(output, indent=2, default=str))]

    except Exception as exc:
        return [TextContent(type="text", text=f"Error: {exc}")]


async def _detect_benefits_drift(
    arguments: dict[str, Any],
) -> list[TextContent]:
    """Detect benefits drift for a project."""
    try:
        from pm_data_tools.assurance.assumptions import DriftSeverity

        tracker = _get_tracker(arguments)
        results = tracker.detect_drift(arguments["project_id"])

        # Apply severity filter if specified
        severity_filter = arguments.get("severity_filter")
        if severity_filter:
            threshold = {
                "NONE": 0,
                "MINOR": 1,
                "MODERATE": 2,
                "SIGNIFICANT": 3,
                "CRITICAL": 4,
            }
            min_level = threshold.get(severity_filter, 0)
            severity_order = [
                DriftSeverity.NONE,
                DriftSeverity.MINOR,
                DriftSeverity.MODERATE,
                DriftSeverity.SIGNIFICANT,
                DriftSeverity.CRITICAL,
            ]
            results = [
                r
                for r in results
                if severity_order.index(r.severity) >= min_level
            ]

        output = {
            "project_id": arguments["project_id"],
            "total_analysed": len(results),
            "drift_results": [
                {
                    "benefit_id": dr.benefit.id,
                    "title": dr.benefit.title,
                    "drift_pct": round(dr.drift_pct, 2),
                    "severity": dr.severity.value,
                    "trend": dr.trend.value,
                    "realisation_pct": (
                        round(dr.realisation_pct, 1)
                        if dr.realisation_pct is not None
                        else None
                    ),
                    "days_since_measurement": dr.days_since_measurement,
                    "message": dr.message,
                }
                for dr in results
            ],
        }

        return [TextContent(type="text", text=json.dumps(output, indent=2, default=str))]

    except Exception as exc:
        return [TextContent(type="text", text=f"Error: {exc}")]


async def _get_benefits_cascade_impact(
    arguments: dict[str, Any],
) -> list[TextContent]:
    """Propagate change through the dependency network."""
    try:
        tracker = _get_tracker(arguments)
        impacts = tracker.find_cascade_impact(arguments["node_id"])

        output = {
            "source_node_id": arguments["node_id"],
            "total_affected": len(impacts),
            "affected_nodes": impacts,
            "message": (
                f"{len(impacts)} downstream node(s) affected by change "
                f"at node {arguments['node_id']}."
            ),
        }

        return [TextContent(type="text", text=json.dumps(output, indent=2, default=str))]

    except Exception as exc:
        return [TextContent(type="text", text=f"Error: {exc}")]


# IPA gate-specific probe questions from the 2021 Assurance Guide
_IPA_GATE_PROBES: dict[int, str] = {
    0: (
        "Gate 0 (Opportunity Framing): Have the expected benefits been identified "
        "at a high level? Is there a clear link between the proposed intervention "
        "and the strategic objectives it supports?"
    ),
    1: (
        "Gate 1 (Strategic Outline Case): Is there a categorised long-list of "
        "benefits? Has a benefits dependency network been established linking "
        "project outputs to strategic objectives? Are benefit owners identified?"
    ),
    2: (
        "Gate 2 (Outline Business Case): Have benefits been valued and appraised "
        "using Green Book methodology? Is the Benefit-Cost Ratio credible? "
        "Has optimism bias been applied to benefit estimates?"
    ),
    3: (
        "Gate 3 (Full Business Case): Is there a detailed Benefits Realisation "
        "Plan? Are baselines established for all quantifiable benefits? Are KPIs "
        "defined with measurement frequency and data sources? Is benefit ownership "
        "formally assigned with named individuals?"
    ),
    4: (
        "Gate 4 (Work to Realise): Are benefits being actively tracked against "
        "baselines? Is there evidence of organisational capability to realise "
        "benefits? Has benefit ownership transitioned to BAU operational leaders? "
        "Are leading indicators being monitored for early warning?"
    ),
    5: (
        "Gate 5 (Benefits Review): What benefits have been realised and how do "
        "actuals compare to the business case? What lessons have been learned "
        "about benefits management? Are there plans for continuous improvement "
        "and ongoing benefit monitoring?"
    ),
}


async def _generate_benefits_narrative(
    arguments: dict[str, Any],
) -> list[TextContent]:
    """Generate IPA-compliant benefits assurance narrative."""
    try:
        import os

        api_key = os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            return [
                TextContent(
                    type="text",
                    text="Error: ANTHROPIC_API_KEY environment variable not set.",
                )
            ]

        from pm_data_tools.gmpp.narratives import NarrativeGenerator

        tracker = _get_tracker(arguments)
        project_id = arguments["project_id"]
        gate_number = arguments.get("gate_number")

        # Build context from benefits register
        context = tracker.build_narrative_context(project_id)

        # Enrich with gate-specific probe questions
        if gate_number is not None and gate_number in _IPA_GATE_PROBES:
            context["gate_probe"] = _IPA_GATE_PROBES[gate_number]
            context["gate_number"] = gate_number

        # Generate narrative using existing infrastructure
        generator = NarrativeGenerator(api_key=api_key)
        narrative = await generator.generate_benefits_narrative(context)

        output = {
            "project_id": project_id,
            "gate_number": gate_number,
            "narrative_text": narrative.text,
            "confidence": round(narrative.confidence, 3),
            "review_level": narrative.review_level.value,
            "samples_used": narrative.samples_used,
            "review_reason": narrative.review_reason,
            "generated_at": narrative.generated_at.isoformat(),
            "context_summary": {
                "total_benefits": context.get("total_benefit_count", 0),
                "health_score": context.get("health_score"),
                "aggregate_realisation_pct": context.get("aggregate_realisation_pct"),
                "at_risk_count": context.get("at_risk_count", 0),
            },
            "message": (
                f"Benefits narrative generated with {narrative.confidence:.0%} "
                f"confidence ({narrative.review_level.value} review recommended)."
            ),
        }

        return [TextContent(type="text", text=json.dumps(output, indent=2, default=str))]

    except Exception as exc:
        return [TextContent(type="text", text=f"Error: {exc}")]


async def _assess_benefits_maturity(
    arguments: dict[str, Any],
) -> list[TextContent]:
    """Assess benefits management maturity against P3M3 criteria."""
    try:
        tracker = _get_tracker(arguments)
        assessment = tracker.assess_maturity(arguments["project_id"])

        output = {
            "project_id": assessment.project_id,
            "timestamp": assessment.timestamp.isoformat(),
            "level": assessment.level.value,
            "level_name": assessment.level.name,
            "score_pct": round(assessment.score_pct, 1),
            "criteria_met": assessment.criteria_met,
            "criteria_total": assessment.criteria_total,
            "criteria_details": assessment.criteria_details,
            "evidence_gaps": assessment.evidence_gaps,
            "recommendations": assessment.recommendations,
            "message": assessment.message,
        }

        return [TextContent(type="text", text=json.dumps(output, indent=2, default=str))]

    except Exception as exc:
        return [TextContent(type="text", text=f"Error: {exc}")]
