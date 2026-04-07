"""Benefits Realisation Management (P13).

Captures project benefits with full IPA/Green Book/MSP/PMI-compliant metadata,
tracks measurement time-series against baselines and interim targets, detects
drift, manages the benefits dependency network as a directed acyclic graph,
computes cascade impacts, and produces portfolio-level health reports.

Usage::

    from pm_data_tools.assurance.benefits import (
        BenefitsTracker,
        Benefit,
        BenefitStatus,
        FinancialType,
        RecipientType,
    )
    from pm_data_tools.db.store import AssuranceStore

    store = AssuranceStore()
    tracker = BenefitsTracker(store=store)

    benefit = tracker.ingest(
        Benefit(
            project_id="PROJ-001",
            title="Reduced processing time",
            description="Average claim processing time reduced from 15 to 5 days",
            financial_type=FinancialType.NON_CASH_RELEASING,
            recipient_type=RecipientType.GOVERNMENT,
            baseline_value=15.0,
            target_value=5.0,
            measurement_kpi="avg_processing_days",
        )
    )

    measurement = tracker.record_measurement(
        benefit_id=benefit.id,
        value=12.0,
        notes="Q1 measurement",
    )

    report = tracker.analyse_health("PROJ-001")
    # report.overall_health_score -> 0.0-1.0
"""

from __future__ import annotations

import json
import uuid
from collections import deque
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any

import structlog
from pydantic import BaseModel, Field

from ..db.store import AssuranceStore
from .assumptions import DriftSeverity

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class BenefitStatus(Enum):
    """Lifecycle status of a benefit.

    Attributes:
        IDENTIFIED: Benefit recognised but not yet baselined.
        PLANNED: Baseline and target established, measurement plan in place.
        REALIZING: Active measurement tracking in progress.
        ACHIEVED: Target value met or exceeded.
        EVAPORATED: Benefit will not be realised — value lost.
        CANCELLED: Benefit deliberately removed from scope.
    """

    IDENTIFIED = "IDENTIFIED"
    PLANNED = "PLANNED"
    REALIZING = "REALIZING"
    ACHIEVED = "ACHIEVED"
    EVAPORATED = "EVAPORATED"
    CANCELLED = "CANCELLED"


class FinancialType(Enum):
    """Green Book financial classification.

    Attributes:
        CASH_RELEASING: Direct financial savings reducing government spend.
        NON_CASH_RELEASING: Financial value not reducing cash expenditure.
        QUANTIFIABLE: Measurable in non-financial units (e.g. time saved).
        QUALITATIVE: Observable but not numerically measurable.
    """

    CASH_RELEASING = "CASH_RELEASING"
    NON_CASH_RELEASING = "NON_CASH_RELEASING"
    QUANTIFIABLE = "QUANTIFIABLE"
    QUALITATIVE = "QUALITATIVE"


class RecipientType(Enum):
    """IPA benefit recipient taxonomy.

    Attributes:
        GOVERNMENT: Internal departmental accrual.
        PRIVATE_SECTOR: Benefits accruing to private sector partners.
        WIDER_UK_PUBLIC: Benefits accruing to the wider UK public.
    """

    GOVERNMENT = "GOVERNMENT"
    PRIVATE_SECTOR = "PRIVATE_SECTOR"
    WIDER_UK_PUBLIC = "WIDER_UK_PUBLIC"


class Explicitness(Enum):
    """Ward & Daniel benefit explicitness taxonomy.

    Attributes:
        FINANCIAL: Directly measurable in monetary terms.
        QUANTIFIABLE: Measurable in numeric units but not money.
        MEASURABLE: Observable change against a defined baseline.
        OBSERVABLE: Expert judgment required; no numeric baseline.
    """

    FINANCIAL = "FINANCIAL"
    QUANTIFIABLE = "QUANTIFIABLE"
    MEASURABLE = "MEASURABLE"
    OBSERVABLE = "OBSERVABLE"


class IndicatorType(Enum):
    """Whether a benefit's KPI is a leading or lagging indicator.

    Attributes:
        LEADING: Predictive metric gathered during execution.
        LAGGING: Post-implementation outcome metric.
    """

    LEADING = "LEADING"
    LAGGING = "LAGGING"


class MeasurementFrequency(Enum):
    """How often the benefit should be measured.

    Attributes:
        MONTHLY: Measured every month.
        QUARTERLY: Measured every quarter.
        ANNUALLY: Measured once per year.
    """

    MONTHLY = "MONTHLY"
    QUARTERLY = "QUARTERLY"
    ANNUALLY = "ANNUALLY"


class IpaLifecycleStage(Enum):
    """IPA five-stage benefits lifecycle.

    Attributes:
        DEFINE_SUCCESS: Opportunity framing.
        IDENTIFY_QUANTIFY: Strategic Outline Case.
        VALUE_APPRAISE: Outline Business Case.
        PLAN_REALISE: Full Business Case.
        REVIEW: Post-delivery operations.
    """

    DEFINE_SUCCESS = "DEFINE_SUCCESS"
    IDENTIFY_QUANTIFY = "IDENTIFY_QUANTIFY"
    VALUE_APPRAISE = "VALUE_APPRAISE"
    PLAN_REALISE = "PLAN_REALISE"
    REVIEW = "REVIEW"


class NodeType(Enum):
    """Benefits dependency network node types.

    Attributes:
        STRATEGIC_OBJECTIVE: Terminal goal nodes.
        END_BENEFIT: Ultimate measurable value (lagging KPIs).
        INTERMEDIATE_BENEFIT: Stepping-stone benefits (leading KPIs).
        BUSINESS_CHANGE: Operational modifications required.
        ENABLER: Capabilities the project builds.
        PROJECT_OUTPUT: Root deliverables linked to schedule.
    """

    STRATEGIC_OBJECTIVE = "STRATEGIC_OBJECTIVE"
    END_BENEFIT = "END_BENEFIT"
    INTERMEDIATE_BENEFIT = "INTERMEDIATE_BENEFIT"
    BUSINESS_CHANGE = "BUSINESS_CHANGE"
    ENABLER = "ENABLER"
    PROJECT_OUTPUT = "PROJECT_OUTPUT"


class EdgeType(Enum):
    """Relationship types between dependency network nodes.

    Attributes:
        DEPENDS_ON: Target depends on source being delivered.
        CONTRIBUTES_TO: Source contributes to target realisation.
        ENABLES: Source enables target to occur.
    """

    DEPENDS_ON = "DEPENDS_ON"
    CONTRIBUTES_TO = "CONTRIBUTES_TO"
    ENABLES = "ENABLES"


class MeasurementSource(Enum):
    """Where a benefit measurement value comes from.

    Attributes:
        MANUAL: Manually entered by the project team.
        EXTERNAL_API: From an external data source.
        DERIVED: Calculated from other measurements or project data.
    """

    MANUAL = "MANUAL"
    EXTERNAL_API = "EXTERNAL_API"
    DERIVED = "DERIVED"


class TrendDirection(Enum):
    """Direction of benefit realisation trend.

    Attributes:
        IMPROVING: Moving towards target.
        STABLE: No significant change.
        DECLINING: Moving away from target.
        INSUFFICIENT_DATA: Fewer than minimum measurements for trend.
    """

    IMPROVING = "IMPROVING"
    STABLE = "STABLE"
    DECLINING = "DECLINING"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class BenefitConfig(BaseModel):
    """Configuration for benefits tracking.

    Attributes:
        staleness_days: Measurements older than this are stale (default 90).
        minor_threshold_pct: Drift below this -> MINOR.
        moderate_threshold_pct: Below this -> MODERATE.
        significant_threshold_pct: Below this -> SIGNIFICANT, above -> CRITICAL.
        min_measurements_for_trend: Minimum measurements to compute trend.
    """

    staleness_days: int = 90
    minor_threshold_pct: float = 5.0
    moderate_threshold_pct: float = 15.0
    significant_threshold_pct: float = 30.0
    min_measurements_for_trend: int = 3


class Benefit(BaseModel):
    """A single project benefit or dis-benefit with full metadata.

    Attributes:
        id: Unique identifier (UUID4 by default).
        project_id: Project this benefit belongs to.
        title: Clear, concise name of the benefit.
        description: Detailed narrative passing the MSP DOAM test.
        is_disbenefit: True if this is a negative consequence.
        status: Lifecycle status.
        financial_type: Green Book financial classification.
        recipient_type: IPA benefit recipient.
        explicitness: Ward & Daniel explicitness level.
        baseline_value: Current performance state before change.
        baseline_date: Date the baseline was established.
        target_value: Desired end-state performance level.
        target_date: Deadline for achieving the target.
        current_actual_value: Latest measured value.
        interim_targets: Time-phased expected values for ramp-up/tail-off.
        measurement_kpi: Specific metric used for tracking.
        measurement_frequency: How often the benefit is measured.
        indicator_type: Whether leading or lagging.
        owner_sro: Senior Responsible Owner.
        benefits_owner: Operational owner post-BAU transition.
        business_change_owner: Owner of enabling changes.
        ipa_lifecycle_stage: Current IPA lifecycle stage.
        business_case_ref: Business case document reference.
        gate_alignment: Which gate review this relates to.
        contributing_projects: IDs of projects contributing to this benefit.
        associated_risks: IDs of linked risk register entries.
        associated_assumptions: IDs of linked assumption tracker entries.
        confidence_score: AI-derived realisation likelihood (0-100).
        created_at: Timestamp of creation.
        updated_at: Timestamp of last update.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str
    title: str
    description: str
    is_disbenefit: bool = False
    status: BenefitStatus = BenefitStatus.IDENTIFIED
    financial_type: FinancialType
    recipient_type: RecipientType
    explicitness: Explicitness = Explicitness.QUANTIFIABLE
    baseline_value: float | None = None
    baseline_date: date | None = None
    target_value: float | None = None
    target_date: date | None = None
    current_actual_value: float | None = None
    interim_targets: list[dict[str, Any]] = Field(default_factory=list)
    measurement_kpi: str | None = None
    measurement_frequency: MeasurementFrequency = MeasurementFrequency.QUARTERLY
    indicator_type: IndicatorType = IndicatorType.LAGGING
    owner_sro: str | None = None
    benefits_owner: str | None = None
    business_change_owner: str | None = None
    ipa_lifecycle_stage: IpaLifecycleStage = IpaLifecycleStage.IDENTIFY_QUANTIFY
    business_case_ref: str | None = None
    gate_alignment: str | None = None
    contributing_projects: list[str] = Field(default_factory=list)
    associated_risks: list[str] = Field(default_factory=list)
    associated_assumptions: list[str] = Field(default_factory=list)
    confidence_score: float | None = None
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )
    updated_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )


class BenefitMeasurement(BaseModel):
    """Record of a single measurement against a benefit.

    Attributes:
        id: Unique identifier (UUID4 by default).
        benefit_id: The benefit being measured.
        project_id: The project this measurement belongs to.
        measured_at: UTC timestamp of the measurement.
        value: The measured value.
        source: Where the value came from.
        drift_pct: Percentage drift from the baseline or interim target.
        drift_severity: Severity classification for this measurement.
        realisation_pct: Percentage of target achieved (0-100+).
        trend_direction: Direction of trend based on recent measurements.
        notes: Optional notes about this measurement.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    benefit_id: str
    project_id: str
    measured_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )
    value: float
    source: MeasurementSource = MeasurementSource.MANUAL
    drift_pct: float = 0.0
    drift_severity: DriftSeverity = DriftSeverity.NONE
    realisation_pct: float | None = None
    trend_direction: TrendDirection | None = None
    notes: str | None = None


class DependencyNode(BaseModel):
    """A node in the benefits dependency network (DAG).

    Attributes:
        id: Unique identifier (UUID4 by default).
        project_id: The project this node belongs to.
        node_type: Type of node in the dependency hierarchy.
        title: Name of the node.
        description: Optional description.
        status: Current status of the node.
        owner: Named individual responsible.
        target_date: Expected delivery/realisation date.
        benefit_id: Links to benefits table for benefit-type nodes.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str
    node_type: NodeType
    title: str
    description: str | None = None
    status: str = "PLANNED"
    owner: str | None = None
    target_date: date | None = None
    benefit_id: str | None = None


class DependencyEdge(BaseModel):
    """A directed edge in the benefits dependency network.

    Attributes:
        id: Unique identifier (UUID4 by default).
        project_id: The project this edge belongs to.
        source_node: ID of the source node.
        target_node: ID of the target node.
        edge_type: Relationship type.
        assumption_id: Links to assumption tracker if applicable.
        risk_id: Links to risk register if applicable.
        notes: Optional notes about this relationship.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str
    source_node: str
    target_node: str
    edge_type: EdgeType = EdgeType.DEPENDS_ON
    assumption_id: str | None = None
    risk_id: str | None = None
    notes: str | None = None


# ---------------------------------------------------------------------------
# Analysis output models
# ---------------------------------------------------------------------------


class BenefitDriftResult(BaseModel):
    """Result of a drift analysis for a single benefit.

    Attributes:
        benefit: The benefit being analysed.
        drift_pct: Absolute percentage drift from baseline.
        severity: Drift severity classification.
        days_since_measurement: Days since last measurement, or None.
        trend: Trend direction based on recent measurements.
        realisation_pct: Percentage of target achieved.
        cascade_impact: IDs of downstream affected nodes.
        message: Human-readable description.
    """

    benefit: Benefit
    drift_pct: float
    severity: DriftSeverity
    days_since_measurement: int | None
    trend: TrendDirection
    realisation_pct: float | None
    cascade_impact: list[str]
    message: str


class BenefitsHealthReport(BaseModel):
    """Aggregate benefits health for a project.

    Attributes:
        project_id: The analysed project.
        timestamp: UTC timestamp of the analysis.
        total_benefits: Total number of tracked benefits.
        total_disbenefits: Total number of tracked dis-benefits.
        by_status: Count per BenefitStatus value.
        by_financial_type: Count per FinancialType value.
        by_recipient: Count per RecipientType value.
        stale_count: Benefits not measured within staleness window.
        at_risk_count: Benefits with SIGNIFICANT or CRITICAL drift.
        drift_results: Per-benefit drift analysis results.
        aggregate_realisation_pct: Weighted realisation across measurable benefits.
        overall_health_score: Composite health (0.0-1.0, 1.0 = healthy).
        leading_indicator_warnings: Warnings from leading indicator analysis.
        message: Human-readable report summary.
    """

    project_id: str
    timestamp: datetime
    total_benefits: int
    total_disbenefits: int
    by_status: dict[str, int]
    by_financial_type: dict[str, int]
    by_recipient: dict[str, int]
    stale_count: int
    at_risk_count: int
    drift_results: list[BenefitDriftResult]
    aggregate_realisation_pct: float
    overall_health_score: float
    leading_indicator_warnings: list[str]
    message: str


class BenefitsMaturityLevel(int, Enum):
    """P3M3 Benefits Management maturity levels (1-5).

    Attributes:
        AWARENESS: No formal benefits process.
        REPEATABLE: Some projects identify benefits inconsistently.
        DEFINED: Standardised processes, benefits review plans.
        MANAGED: Double-counting elimination, rigorous reviews.
        OPTIMISED: Clear linkage to strategy, continuous improvement.
    """

    AWARENESS = 1
    REPEATABLE = 2
    DEFINED = 3
    MANAGED = 4
    OPTIMISED = 5


MATURITY_THRESHOLDS: dict[BenefitsMaturityLevel, float] = {
    BenefitsMaturityLevel.AWARENESS: 0.0,
    BenefitsMaturityLevel.REPEATABLE: 20.0,
    BenefitsMaturityLevel.DEFINED: 40.0,
    BenefitsMaturityLevel.MANAGED: 65.0,
    BenefitsMaturityLevel.OPTIMISED: 85.0,
}

MATURITY_DESCRIPTIONS: dict[BenefitsMaturityLevel, str] = {
    BenefitsMaturityLevel.AWARENESS: (
        "No formal benefits management process. Benefits may be mentioned in "
        "business cases but are not systematically tracked or measured."
    ),
    BenefitsMaturityLevel.REPEATABLE: (
        "Some projects identify and track benefits, but processes are inconsistent. "
        "Benefits registers may exist but lack baselines or regular measurement."
    ),
    BenefitsMaturityLevel.DEFINED: (
        "Standardised benefits management processes. Benefits registers are maintained "
        "with baselines, targets, and regular measurements. Ownership is assigned."
    ),
    BenefitsMaturityLevel.MANAGED: (
        "Benefits management is quantitatively managed. Double-counting is eliminated, "
        "dependency networks are mapped, and rigorous reviews occur at gate stages."
    ),
    BenefitsMaturityLevel.OPTIMISED: (
        "Clear linkage between strategic decisions and benefits realisation. Continuous "
        "improvement, knowledge transfer, and proactive forecasting are embedded."
    ),
}


class BenefitsMaturityAssessment(BaseModel):
    """Result of a P3M3-aligned benefits management maturity assessment.

    Attributes:
        project_id: The assessed project.
        timestamp: UTC timestamp of the assessment.
        level: P3M3 maturity level (1-5).
        score_pct: Overall score as percentage.
        criteria_total: Total criteria assessed.
        criteria_met: Criteria met.
        criteria_details: Per-criterion results.
        evidence_gaps: Specific gaps identified.
        recommendations: Improvement recommendations.
        message: Human-readable summary.
    """

    project_id: str
    timestamp: datetime
    level: BenefitsMaturityLevel
    score_pct: float
    criteria_total: int
    criteria_met: int
    criteria_details: dict[str, bool]
    evidence_gaps: list[str]
    recommendations: list[str]
    message: str


class BenefitForecast(BaseModel):
    """Forecast result for a single benefit.

    Attributes:
        benefit_id: The benefit being forecast.
        title: Benefit title for display.
        target_value: The target value.
        target_date: Deadline for achieving the target.
        current_trajectory_value: Linear projection at target date.
        probability_of_realisation: Estimated probability (0.0-1.0).
        evm_correlation: CPI/SPI impact data if available.
        forecast_method: Method used for forecasting.
        message: Human-readable forecast summary.
    """

    benefit_id: str
    title: str
    target_value: float
    target_date: date
    current_trajectory_value: float
    probability_of_realisation: float
    evm_correlation: dict[str, Any] | None = None
    forecast_method: str
    message: str


# ---------------------------------------------------------------------------
# Severity weights — reuse same scale as assumption drift
# ---------------------------------------------------------------------------

_SEVERITY_WEIGHTS: dict[DriftSeverity, float] = {
    DriftSeverity.NONE: 0.0,
    DriftSeverity.MINOR: 0.2,
    DriftSeverity.MODERATE: 0.5,
    DriftSeverity.SIGNIFICANT: 0.8,
    DriftSeverity.CRITICAL: 1.0,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _row_to_benefit(row: dict[str, Any]) -> Benefit:
    """Deserialise a database row to a :class:`Benefit`."""
    interim_raw = row.get("interim_targets", "[]")
    interim = json.loads(str(interim_raw)) if isinstance(interim_raw, str) else []

    contrib_raw = row.get("contributing_projects", "[]")
    contrib = json.loads(str(contrib_raw)) if isinstance(contrib_raw, str) else []

    risks_raw = row.get("associated_risks", "[]")
    risks = json.loads(str(risks_raw)) if isinstance(risks_raw, str) else []

    assumptions_raw = row.get("associated_assumptions", "[]")
    assumptions = json.loads(str(assumptions_raw)) if isinstance(assumptions_raw, str) else []

    baseline_date = None
    if row.get("baseline_date"):
        baseline_date = date.fromisoformat(str(row["baseline_date"]))

    target_date = None
    if row.get("target_date"):
        target_date = date.fromisoformat(str(row["target_date"]))

    return Benefit(
        id=str(row["id"]),
        project_id=str(row["project_id"]),
        title=str(row["title"]),
        description=str(row["description"]),
        is_disbenefit=bool(row.get("is_disbenefit", 0)),
        status=BenefitStatus(str(row["status"])),
        financial_type=FinancialType(str(row["financial_type"])),
        recipient_type=RecipientType(str(row["recipient_type"])),
        explicitness=Explicitness(str(row.get("explicitness", "QUANTIFIABLE"))),
        baseline_value=float(row["baseline_value"]) if row.get("baseline_value") is not None else None,
        baseline_date=baseline_date,
        target_value=float(row["target_value"]) if row.get("target_value") is not None else None,
        target_date=target_date,
        current_actual_value=(
            float(row["current_actual_value"])
            if row.get("current_actual_value") is not None
            else None
        ),
        interim_targets=interim,
        measurement_kpi=str(row["measurement_kpi"]) if row.get("measurement_kpi") else None,
        measurement_frequency=MeasurementFrequency(
            str(row.get("measurement_frequency", "QUARTERLY"))
        ),
        indicator_type=IndicatorType(str(row.get("indicator_type", "LAGGING"))),
        owner_sro=str(row["owner_sro"]) if row.get("owner_sro") else None,
        benefits_owner=str(row["benefits_owner"]) if row.get("benefits_owner") else None,
        business_change_owner=(
            str(row["business_change_owner"]) if row.get("business_change_owner") else None
        ),
        ipa_lifecycle_stage=IpaLifecycleStage(
            str(row.get("ipa_lifecycle_stage", "IDENTIFY_QUANTIFY"))
        ),
        business_case_ref=str(row["business_case_ref"]) if row.get("business_case_ref") else None,
        gate_alignment=str(row["gate_alignment"]) if row.get("gate_alignment") else None,
        contributing_projects=contrib,
        associated_risks=risks,
        associated_assumptions=assumptions,
        confidence_score=(
            float(row["confidence_score"]) if row.get("confidence_score") is not None else None
        ),
        created_at=datetime.fromisoformat(str(row["created_at"])),
        updated_at=datetime.fromisoformat(str(row["updated_at"])),
    )


def _row_to_measurement(row: dict[str, Any]) -> BenefitMeasurement:
    """Deserialise a database row to a :class:`BenefitMeasurement`."""
    return BenefitMeasurement(
        id=str(row["id"]),
        benefit_id=str(row["benefit_id"]),
        project_id=str(row["project_id"]),
        measured_at=datetime.fromisoformat(str(row["measured_at"])),
        value=float(row["value"]),
        source=MeasurementSource(str(row.get("source", "MANUAL"))),
        drift_pct=float(row.get("drift_pct", 0.0)),
        drift_severity=DriftSeverity(str(row.get("drift_severity", "NONE"))),
        realisation_pct=(
            float(row["realisation_pct"]) if row.get("realisation_pct") is not None else None
        ),
        trend_direction=(
            TrendDirection(str(row["trend_direction"]))
            if row.get("trend_direction")
            else None
        ),
        notes=str(row["notes"]) if row.get("notes") else None,
    )


def _row_to_node(row: dict[str, Any]) -> DependencyNode:
    """Deserialise a database row to a :class:`DependencyNode`."""
    target_date = None
    if row.get("target_date"):
        target_date = date.fromisoformat(str(row["target_date"]))

    return DependencyNode(
        id=str(row["id"]),
        project_id=str(row["project_id"]),
        node_type=NodeType(str(row["node_type"])),
        title=str(row["title"]),
        description=str(row["description"]) if row.get("description") else None,
        status=str(row.get("status", "PLANNED")),
        owner=str(row["owner"]) if row.get("owner") else None,
        target_date=target_date,
        benefit_id=str(row["benefit_id"]) if row.get("benefit_id") else None,
    )


def _row_to_edge(row: dict[str, Any]) -> DependencyEdge:
    """Deserialise a database row to a :class:`DependencyEdge`."""
    return DependencyEdge(
        id=str(row["id"]),
        project_id=str(row["project_id"]),
        source_node=str(row["source_node"]),
        target_node=str(row["target_node"]),
        edge_type=EdgeType(str(row.get("edge_type", "DEPENDS_ON"))),
        assumption_id=str(row["assumption_id"]) if row.get("assumption_id") else None,
        risk_id=str(row["risk_id"]) if row.get("risk_id") else None,
        notes=str(row["notes"]) if row.get("notes") else None,
    )


# ---------------------------------------------------------------------------
# Tracker
# ---------------------------------------------------------------------------


class BenefitsTracker:
    """Track, measure, and analyse benefit realisation across projects.

    Captures project benefits with full IPA/Green Book metadata, records
    time-series measurements against baselines, detects drift, manages
    the benefits dependency network as a DAG, and produces portfolio-level
    health reports.

    Example::

        store = AssuranceStore()
        tracker = BenefitsTracker(store=store)

        b = tracker.ingest(
            Benefit(
                project_id="PROJ-001",
                title="Reduced processing time",
                description="Average claim processing reduced from 15 to 5 days",
                financial_type=FinancialType.NON_CASH_RELEASING,
                recipient_type=RecipientType.GOVERNMENT,
                baseline_value=15.0,
                target_value=5.0,
            )
        )
        tracker.record_measurement(b.id, value=12.0)
        report = tracker.analyse_health("PROJ-001")
    """

    def __init__(
        self,
        store: AssuranceStore | None = None,
        config: BenefitConfig | None = None,
    ) -> None:
        """Initialise the benefits tracker.

        Args:
            store: Shared :class:`~pm_data_tools.db.store.AssuranceStore`.
                A default store is created if not provided.
            config: Tracking configuration. Uses defaults if not provided.
        """
        self._store = store or AssuranceStore()
        self._config = config or BenefitConfig()

    # ------------------------------------------------------------------
    # CRUD operations
    # ------------------------------------------------------------------

    def ingest(self, benefit: Benefit) -> Benefit:
        """Persist a benefit. Returns the benefit with its ID.

        Args:
            benefit: The :class:`Benefit` to persist.

        Returns:
            The same benefit object (with auto-generated ``id`` if unset).
        """
        self._store.upsert_benefit(
            {
                "id": benefit.id,
                "project_id": benefit.project_id,
                "title": benefit.title,
                "description": benefit.description,
                "is_disbenefit": 1 if benefit.is_disbenefit else 0,
                "status": benefit.status.value,
                "financial_type": benefit.financial_type.value,
                "recipient_type": benefit.recipient_type.value,
                "explicitness": benefit.explicitness.value,
                "baseline_value": benefit.baseline_value,
                "baseline_date": (
                    benefit.baseline_date.isoformat() if benefit.baseline_date else None
                ),
                "target_value": benefit.target_value,
                "target_date": (
                    benefit.target_date.isoformat() if benefit.target_date else None
                ),
                "current_actual_value": benefit.current_actual_value,
                "interim_targets": json.dumps(benefit.interim_targets),
                "measurement_kpi": benefit.measurement_kpi,
                "measurement_frequency": benefit.measurement_frequency.value,
                "indicator_type": benefit.indicator_type.value,
                "owner_sro": benefit.owner_sro,
                "benefits_owner": benefit.benefits_owner,
                "business_change_owner": benefit.business_change_owner,
                "ipa_lifecycle_stage": benefit.ipa_lifecycle_stage.value,
                "business_case_ref": benefit.business_case_ref,
                "gate_alignment": benefit.gate_alignment,
                "contributing_projects": json.dumps(benefit.contributing_projects),
                "associated_risks": json.dumps(benefit.associated_risks),
                "associated_assumptions": json.dumps(benefit.associated_assumptions),
                "confidence_score": benefit.confidence_score,
                "created_at": benefit.created_at.isoformat(),
                "updated_at": benefit.updated_at.isoformat(),
            }
        )
        logger.info(
            "benefit_ingested",
            id=benefit.id,
            project_id=benefit.project_id,
            title=benefit.title,
            is_disbenefit=benefit.is_disbenefit,
        )
        return benefit

    def ingest_batch(self, benefits: list[Benefit]) -> int:
        """Ingest multiple benefits. Returns count ingested.

        Args:
            benefits: List of :class:`Benefit` objects to persist.

        Returns:
            Number of benefits successfully ingested.
        """
        count = 0
        for benefit in benefits:
            self.ingest(benefit)
            count += 1
        logger.info("benefit_batch_ingested", count=count)
        return count

    def get_benefits(
        self,
        project_id: str,
        status: BenefitStatus | None = None,
        financial_type: FinancialType | None = None,
    ) -> list[Benefit]:
        """Retrieve benefits for a project, optionally filtered.

        Args:
            project_id: The project identifier.
            status: Optional :class:`BenefitStatus` filter.
            financial_type: Optional :class:`FinancialType` filter.

        Returns:
            List of :class:`Benefit` objects.
        """
        rows = self._store.get_benefits(
            project_id=project_id,
            status_filter=status.value if status else None,
            financial_type_filter=financial_type.value if financial_type else None,
        )
        return [_row_to_benefit(r) for r in rows]

    def update_status(self, benefit_id: str, status: BenefitStatus) -> Benefit:
        """Update a benefit's lifecycle status.

        Args:
            benefit_id: ID of the :class:`Benefit` to update.
            status: New :class:`BenefitStatus`.

        Returns:
            The updated :class:`Benefit`.

        Raises:
            ValueError: If no benefit with the given ID exists.
        """
        row = self._store.get_benefit_by_id(benefit_id)
        if row is None:
            raise ValueError(f"Benefit {benefit_id!r} not found")

        self._store.update_benefit_status(benefit_id, status.value)
        logger.info(
            "benefit_status_updated",
            id=benefit_id,
            status=status.value,
        )
        updated_row = self._store.get_benefit_by_id(benefit_id)
        return _row_to_benefit(updated_row)  # type: ignore[arg-type]

    # ------------------------------------------------------------------
    # Measurement tracking
    # ------------------------------------------------------------------

    def record_measurement(
        self,
        benefit_id: str,
        value: float,
        source: MeasurementSource = MeasurementSource.MANUAL,
        notes: str | None = None,
    ) -> BenefitMeasurement:
        """Record a measurement against a registered benefit.

        Computes drift from baseline, realisation percentage, and trend
        direction from the measurement history.

        Args:
            benefit_id: ID of the :class:`Benefit` to measure.
            value: The measured value.
            source: Where the value came from.
            notes: Optional notes about this measurement.

        Returns:
            The created :class:`BenefitMeasurement` record.

        Raises:
            ValueError: If no benefit with the given ID exists.
        """
        row = self._store.get_benefit_by_id(benefit_id)
        if row is None:
            raise ValueError(f"Benefit {benefit_id!r} not found")

        benefit = _row_to_benefit(row)
        now = datetime.now(tz=timezone.utc)

        # Compute drift from baseline
        drift_pct = 0.0
        if benefit.baseline_value is not None and benefit.baseline_value != 0.0:
            drift_pct = abs(
                (value - benefit.baseline_value) / benefit.baseline_value
            ) * 100.0

        severity = self._classify_drift(drift_pct)

        # Compute realisation percentage
        realisation_pct = self._compute_realisation_pct_from_values(
            baseline=benefit.baseline_value,
            target=benefit.target_value,
            current=value,
            is_disbenefit=benefit.is_disbenefit,
        )

        # Get history for trend computation
        history_rows = self._store.get_benefit_measurements(benefit_id)
        history = [_row_to_measurement(r) for r in history_rows]
        # Include current measurement for trend
        all_values = [m.value for m in history] + [value]
        trend = self._compute_trend(all_values)

        measurement = BenefitMeasurement(
            benefit_id=benefit_id,
            project_id=benefit.project_id,
            measured_at=now,
            value=value,
            source=source,
            drift_pct=drift_pct,
            drift_severity=severity,
            realisation_pct=realisation_pct,
            trend_direction=trend,
            notes=notes,
        )

        self._store.upsert_benefit_measurement(
            {
                "id": measurement.id,
                "benefit_id": measurement.benefit_id,
                "project_id": measurement.project_id,
                "measured_at": measurement.measured_at.isoformat(),
                "value": measurement.value,
                "source": measurement.source.value,
                "drift_pct": measurement.drift_pct,
                "drift_severity": measurement.drift_severity.value,
                "realisation_pct": measurement.realisation_pct,
                "trend_direction": (
                    measurement.trend_direction.value
                    if measurement.trend_direction
                    else None
                ),
                "notes": measurement.notes,
                "created_at": now.isoformat(),
            }
        )

        # Update current_actual_value on the benefit
        self._store.upsert_benefit(
            {
                **dict(row),
                "current_actual_value": value,
                "updated_at": now.isoformat(),
            }
        )

        logger.info(
            "benefit_measurement_recorded",
            benefit_id=benefit_id,
            value=value,
            drift_pct=drift_pct,
            severity=severity.value,
            realisation_pct=realisation_pct,
        )
        return measurement

    def get_measurements(self, benefit_id: str) -> list[BenefitMeasurement]:
        """Retrieve all measurements for a benefit, oldest first.

        Args:
            benefit_id: The benefit identifier.

        Returns:
            List of :class:`BenefitMeasurement` objects.
        """
        rows = self._store.get_benefit_measurements(benefit_id)
        return [_row_to_measurement(r) for r in rows]

    # ------------------------------------------------------------------
    # Health analysis
    # ------------------------------------------------------------------

    def analyse_health(self, project_id: str) -> BenefitsHealthReport:
        """Full health analysis for a project's benefits portfolio.

        Computes per-benefit drift, staleness, at-risk counts, aggregate
        realisation, and an overall health score (0.0-1.0).

        Args:
            project_id: The project identifier.

        Returns:
            A :class:`BenefitsHealthReport` with full analysis.
        """
        now = datetime.now(tz=timezone.utc)
        benefits = self.get_benefits(project_id)

        if not benefits:
            return BenefitsHealthReport(
                project_id=project_id,
                timestamp=now,
                total_benefits=0,
                total_disbenefits=0,
                by_status={s.value: 0 for s in BenefitStatus},
                by_financial_type={f.value: 0 for f in FinancialType},
                by_recipient={r.value: 0 for r in RecipientType},
                stale_count=0,
                at_risk_count=0,
                drift_results=[],
                aggregate_realisation_pct=0.0,
                overall_health_score=1.0,
                leading_indicator_warnings=[],
                message="No benefits registered for this project.",
            )

        # Classify
        by_status: dict[str, int] = {s.value: 0 for s in BenefitStatus}
        by_financial_type: dict[str, int] = {f.value: 0 for f in FinancialType}
        by_recipient: dict[str, int] = {r.value: 0 for r in RecipientType}
        total_disbenefits = 0

        for b in benefits:
            by_status[b.status.value] = by_status.get(b.status.value, 0) + 1
            by_financial_type[b.financial_type.value] = (
                by_financial_type.get(b.financial_type.value, 0) + 1
            )
            by_recipient[b.recipient_type.value] = (
                by_recipient.get(b.recipient_type.value, 0) + 1
            )
            if b.is_disbenefit:
                total_disbenefits += 1

        # Analyse each benefit
        drift_results: list[BenefitDriftResult] = []
        stale_count = 0
        at_risk_count = 0
        realisation_values: list[float] = []
        leading_warnings: list[str] = []

        for b in benefits:
            measurements = self.get_measurements(b.id)

            # Staleness
            days_since: int | None = None
            if measurements:
                last = measurements[-1]
                delta = now - last.measured_at
                days_since = delta.days
                if days_since > self._config.staleness_days:
                    stale_count += 1

            # Drift from baseline
            drift_pct = 0.0
            if b.current_actual_value is not None and b.baseline_value is not None:
                if b.baseline_value != 0.0:
                    drift_pct = abs(
                        (b.current_actual_value - b.baseline_value)
                        / b.baseline_value
                    ) * 100.0

            severity = self._classify_drift(drift_pct)
            if severity in (DriftSeverity.SIGNIFICANT, DriftSeverity.CRITICAL):
                at_risk_count += 1

            # Trend
            values = [m.value for m in measurements]
            trend = self._compute_trend(values)

            # Realisation
            realisation_pct = self._compute_realisation_pct_from_values(
                baseline=b.baseline_value,
                target=b.target_value,
                current=b.current_actual_value,
                is_disbenefit=b.is_disbenefit,
            )
            if realisation_pct is not None:
                realisation_values.append(realisation_pct)

            # Leading indicator warnings
            if (
                b.indicator_type == IndicatorType.LEADING
                and trend == TrendDirection.DECLINING
            ):
                leading_warnings.append(
                    f"Leading indicator '{b.title}' is declining — "
                    f"downstream lagging benefits may be at risk."
                )

            # Build message
            parts: list[str] = [f"{b.title}: {severity.value} drift ({drift_pct:.1f}%)"]
            if realisation_pct is not None:
                parts.append(f"realisation {realisation_pct:.1f}%")
            parts.append(f"trend {trend.value}")
            message = ", ".join(parts)

            drift_results.append(
                BenefitDriftResult(
                    benefit=b,
                    drift_pct=drift_pct,
                    severity=severity,
                    days_since_measurement=days_since,
                    trend=trend,
                    realisation_pct=realisation_pct,
                    cascade_impact=[],
                    message=message,
                )
            )

        # Aggregate realisation
        aggregate_realisation = (
            sum(realisation_values) / len(realisation_values)
            if realisation_values
            else 0.0
        )

        # Overall health score (1.0 = healthy, 0.0 = critical)
        if drift_results:
            severity_sum = sum(
                _SEVERITY_WEIGHTS[dr.severity] for dr in drift_results
            )
            overall_health = max(0.0, 1.0 - (severity_sum / len(drift_results)))
        else:
            overall_health = 1.0

        # Build summary message
        total = len(benefits)
        active = by_status.get("REALIZING", 0)
        achieved = by_status.get("ACHIEVED", 0)
        evaporated = by_status.get("EVAPORATED", 0)
        message = (
            f"{total} benefits tracked ({total - total_disbenefits} benefits, "
            f"{total_disbenefits} dis-benefits). "
            f"{active} realizing, {achieved} achieved, {evaporated} evaporated. "
            f"Aggregate realisation: {aggregate_realisation:.1f}%. "
            f"Health score: {overall_health:.2f}. "
            f"{at_risk_count} at risk, {stale_count} stale."
        )

        return BenefitsHealthReport(
            project_id=project_id,
            timestamp=now,
            total_benefits=total - total_disbenefits,
            total_disbenefits=total_disbenefits,
            by_status=by_status,
            by_financial_type=by_financial_type,
            by_recipient=by_recipient,
            stale_count=stale_count,
            at_risk_count=at_risk_count,
            drift_results=drift_results,
            aggregate_realisation_pct=aggregate_realisation,
            overall_health_score=overall_health,
            leading_indicator_warnings=leading_warnings,
            message=message,
        )

    # ------------------------------------------------------------------
    # Dependency network
    # ------------------------------------------------------------------

    def add_node(self, node: DependencyNode) -> DependencyNode:
        """Add a node to the benefits dependency network.

        Args:
            node: The :class:`DependencyNode` to add.

        Returns:
            The persisted node.
        """
        now = datetime.now(tz=timezone.utc)
        self._store.upsert_dependency_node(
            {
                "id": node.id,
                "project_id": node.project_id,
                "node_type": node.node_type.value,
                "title": node.title,
                "description": node.description,
                "status": node.status,
                "owner": node.owner,
                "target_date": (
                    node.target_date.isoformat() if node.target_date else None
                ),
                "benefit_id": node.benefit_id,
                "created_at": now.isoformat(),
            }
        )
        logger.info(
            "dependency_node_added",
            id=node.id,
            node_type=node.node_type.value,
            title=node.title,
        )
        return node

    def add_edge(self, edge: DependencyEdge) -> DependencyEdge:
        """Add a directed edge to the benefits dependency network.

        Validates that adding this edge does not create a cycle.

        Args:
            edge: The :class:`DependencyEdge` to add.

        Returns:
            The persisted edge.

        Raises:
            ValueError: If the edge would create a cycle in the DAG.
        """
        # Check for cycles by temporarily adding edge and running detection
        existing_edges = self._store.get_dependency_edges(edge.project_id)
        adjacency: dict[str, list[str]] = {}
        for e_row in existing_edges:
            src = str(e_row["source_node"])
            tgt = str(e_row["target_node"])
            adjacency.setdefault(src, []).append(tgt)

        # Add the proposed edge
        adjacency.setdefault(edge.source_node, []).append(edge.target_node)

        # DFS cycle detection
        if self._has_cycle(adjacency):
            raise ValueError(
                f"Adding edge {edge.source_node} -> {edge.target_node} "
                f"would create a cycle in the dependency network."
            )

        now = datetime.now(tz=timezone.utc)
        self._store.upsert_dependency_edge(
            {
                "id": edge.id,
                "project_id": edge.project_id,
                "source_node": edge.source_node,
                "target_node": edge.target_node,
                "edge_type": edge.edge_type.value,
                "assumption_id": edge.assumption_id,
                "risk_id": edge.risk_id,
                "notes": edge.notes,
                "created_at": now.isoformat(),
            }
        )
        logger.info(
            "dependency_edge_added",
            id=edge.id,
            source=edge.source_node,
            target=edge.target_node,
            edge_type=edge.edge_type.value,
        )
        return edge

    def get_network(self, project_id: str) -> dict[str, Any]:
        """Return the full dependency network for a project.

        Args:
            project_id: The project identifier.

        Returns:
            Dict with ``nodes`` and ``edges`` lists.
        """
        node_rows = self._store.get_dependency_nodes(project_id)
        edge_rows = self._store.get_dependency_edges(project_id)

        nodes = [_row_to_node(r) for r in node_rows]
        edges = [_row_to_edge(r) for r in edge_rows]

        return {
            "nodes": [n.model_dump(mode="json") for n in nodes],
            "edges": [e.model_dump(mode="json") for e in edges],
        }

    def validate_dag(self, project_id: str) -> list[str]:
        """Check the dependency network for cycles.

        Args:
            project_id: The project identifier.

        Returns:
            List of error messages. Empty list means valid DAG.
        """
        edge_rows = self._store.get_dependency_edges(project_id)
        adjacency: dict[str, list[str]] = {}
        for e_row in edge_rows:
            src = str(e_row["source_node"])
            tgt = str(e_row["target_node"])
            adjacency.setdefault(src, []).append(tgt)

        errors: list[str] = []
        if self._has_cycle(adjacency):
            errors.append("Cycle detected in the benefits dependency network.")
        return errors

    # ------------------------------------------------------------------
    # Cascade & drift
    # ------------------------------------------------------------------

    def find_cascade_impact(self, node_id: str) -> list[dict[str, Any]]:
        """Find all downstream nodes affected by a change at the given node.

        Uses BFS through the dependency network to propagate impact.

        Args:
            node_id: The starting node ID.

        Returns:
            List of dicts with ``node_id``, ``node_type``, ``title``,
            ``depth`` (distance from the source node).
        """
        node = self._store.get_dependency_node_by_id(node_id)
        if node is None:
            return []

        project_id = str(node["project_id"])
        edge_rows = self._store.get_dependency_edges(project_id)

        # Build adjacency: source -> [targets]
        adjacency: dict[str, list[str]] = {}
        for e_row in edge_rows:
            src = str(e_row["source_node"])
            tgt = str(e_row["target_node"])
            adjacency.setdefault(src, []).append(tgt)

        # BFS
        visited: set[str] = set()
        queue: deque[tuple[str, int]] = deque([(node_id, 0)])
        impacts: list[dict[str, Any]] = []

        while queue:
            current, depth = queue.popleft()
            if current in visited:
                continue
            visited.add(current)

            if current != node_id:
                current_node = self._store.get_dependency_node_by_id(current)
                if current_node:
                    impacts.append(
                        {
                            "node_id": current,
                            "node_type": str(current_node["node_type"]),
                            "title": str(current_node["title"]),
                            "depth": depth,
                        }
                    )

            for neighbour in adjacency.get(current, []):
                if neighbour not in visited:
                    queue.append((neighbour, depth + 1))

        return impacts

    def detect_drift(self, project_id: str) -> list[BenefitDriftResult]:
        """Detect benefits with significant measurement drift.

        Analyses all benefits for a project and returns drift results,
        ordered by severity (worst first).

        Args:
            project_id: The project identifier.

        Returns:
            List of :class:`BenefitDriftResult` objects, worst first.
        """
        report = self.analyse_health(project_id)
        # Sort by severity weight descending
        sorted_results = sorted(
            report.drift_results,
            key=lambda dr: _SEVERITY_WEIGHTS[dr.severity],
            reverse=True,
        )
        return sorted_results

    # ------------------------------------------------------------------
    # Forecasting
    # ------------------------------------------------------------------

    def forecast(self, benefit_id: str) -> BenefitForecast:
        """Forecast benefit realisation using linear extrapolation.

        Projects the current measurement trajectory forward to the target
        date and estimates the probability of achieving the target value.

        Args:
            benefit_id: The benefit to forecast.

        Returns:
            A :class:`BenefitForecast` with trajectory and probability.

        Raises:
            ValueError: If the benefit does not exist or has no target.
        """
        row = self._store.get_benefit_by_id(benefit_id)
        if row is None:
            raise ValueError(f"Benefit {benefit_id!r} not found")

        benefit = _row_to_benefit(row)

        if benefit.target_value is None or benefit.target_date is None:
            raise ValueError(
                f"Benefit {benefit_id!r} has no target value or target date"
            )

        measurements = self.get_measurements(benefit_id)

        if len(measurements) < 2:
            return BenefitForecast(
                benefit_id=benefit_id,
                title=benefit.title,
                target_value=benefit.target_value,
                target_date=benefit.target_date,
                current_trajectory_value=benefit.current_actual_value or 0.0,
                probability_of_realisation=0.0,
                forecast_method="insufficient_data",
                message=(
                    f"Insufficient measurement data for '{benefit.title}'. "
                    f"At least 2 measurements required for forecasting."
                ),
            )

        # Linear extrapolation
        # Convert measurement timestamps to days-since-first
        first_ts = measurements[0].measured_at
        x_vals = [
            (m.measured_at - first_ts).total_seconds() / 86400.0
            for m in measurements
        ]
        y_vals = [m.value for m in measurements]

        # Simple least-squares linear regression
        n = len(x_vals)
        sum_x = sum(x_vals)
        sum_y = sum(y_vals)
        sum_xy = sum(x * y for x, y in zip(x_vals, y_vals, strict=True))
        sum_x2 = sum(x * x for x in x_vals)

        denom = n * sum_x2 - sum_x * sum_x
        if denom == 0:
            slope = 0.0
            intercept = sum_y / n
        else:
            slope = (n * sum_xy - sum_x * sum_y) / denom
            intercept = (sum_y - slope * sum_x) / n

        # Project to target date
        target_days = (
            datetime.combine(benefit.target_date, datetime.min.time()).replace(
                tzinfo=timezone.utc
            )
            - first_ts
        ).total_seconds() / 86400.0
        projected_value = intercept + slope * target_days

        # Probability: how close projected value gets to target
        if benefit.baseline_value is not None:
            total_change_needed = benefit.target_value - benefit.baseline_value
            if total_change_needed != 0:
                projected_change = projected_value - benefit.baseline_value
                probability = max(0.0, min(1.0, projected_change / total_change_needed))
            else:
                probability = 1.0
        else:
            # No baseline: use ratio of projected to target
            if benefit.target_value != 0:
                probability = max(
                    0.0, min(1.0, projected_value / benefit.target_value)
                )
            else:
                probability = 1.0

        message = (
            f"Linear extrapolation for '{benefit.title}': "
            f"projected value at target date = {projected_value:.2f} "
            f"(target = {benefit.target_value:.2f}). "
            f"Probability of realisation: {probability:.0%}."
        )

        return BenefitForecast(
            benefit_id=benefit_id,
            title=benefit.title,
            target_value=benefit.target_value,
            target_date=benefit.target_date,
            current_trajectory_value=projected_value,
            probability_of_realisation=probability,
            forecast_method="linear_extrapolation",
            message=message,
        )

    # ------------------------------------------------------------------
    # Maturity assessment
    # ------------------------------------------------------------------

    def assess_maturity(self, project_id: str) -> BenefitsMaturityAssessment:
        """Assess benefits management maturity against P3M3 criteria.

        Evaluates the project's benefits data completeness and process
        maturity against 15 criteria derived from P3M3 Level 1-5 indicators.
        Uses a weakest-link-informed scoring approach consistent with ARMM.

        Args:
            project_id: The project identifier.

        Returns:
            A :class:`BenefitsMaturityAssessment` with level, gaps, and
            recommendations.
        """
        now = datetime.now(tz=timezone.utc)
        benefits = self.get_benefits(project_id)

        criteria: dict[str, bool] = {}
        gaps: list[str] = []
        recommendations: list[str] = []

        # --- Level 1 (Awareness): Benefits exist ---
        has_benefits = len(benefits) > 0
        criteria["benefits_identified"] = has_benefits
        if not has_benefits:
            gaps.append("No benefits registered for this project.")
            recommendations.append("Register all business case benefits in the benefits register.")

        # --- Level 2 (Repeatable): Basic metadata ---
        has_descriptions = all(len(b.description) > 20 for b in benefits) if benefits else False
        criteria["descriptions_adequate"] = has_descriptions
        if not has_descriptions and benefits:
            gaps.append("Some benefits lack adequate descriptions (DOAM test).")
            recommendations.append("Ensure all benefit descriptions pass the DOAM test.")

        has_owners = all(b.owner_sro is not None for b in benefits) if benefits else False
        criteria["owners_assigned"] = has_owners
        if not has_owners and benefits:
            gaps.append("Not all benefits have an assigned SRO.")
            recommendations.append("Assign a named SRO to every benefit.")

        has_financial_types = all(b.financial_type is not None for b in benefits) if benefits else False
        criteria["financial_classification"] = has_financial_types

        # --- Level 3 (Defined): Baselines, targets, measurements ---
        has_baselines = (
            all(b.baseline_value is not None for b in benefits if b.explicitness != Explicitness.OBSERVABLE)
            if benefits
            else False
        )
        criteria["baselines_established"] = has_baselines
        if not has_baselines and benefits:
            gaps.append("Not all quantifiable benefits have baseline values.")
            recommendations.append("Establish baseline measurements for all quantifiable benefits.")

        has_targets = (
            all(b.target_value is not None for b in benefits if b.explicitness != Explicitness.OBSERVABLE)
            if benefits
            else False
        )
        criteria["targets_set"] = has_targets
        if not has_targets and benefits:
            gaps.append("Not all quantifiable benefits have target values.")
            recommendations.append("Set measurable targets for all quantifiable benefits.")

        has_kpis = (
            all(b.measurement_kpi is not None for b in benefits if b.explicitness != Explicitness.OBSERVABLE)
            if benefits
            else False
        )
        criteria["kpis_defined"] = has_kpis
        if not has_kpis and benefits:
            gaps.append("Not all benefits have measurement KPIs defined.")
            recommendations.append("Define specific KPI metrics for all quantifiable benefits.")

        benefits_with_measurements = 0
        for b in benefits:
            measurements = self.get_measurements(b.id)
            if measurements:
                benefits_with_measurements += 1
        has_measurements = benefits_with_measurements > 0 if benefits else False
        criteria["measurements_recorded"] = has_measurements
        if not has_measurements and benefits:
            gaps.append("No benefit measurements have been recorded.")
            recommendations.append("Begin recording regular measurements against baselines.")

        # --- Level 4 (Managed): Dependencies, lifecycle, dis-benefits ---
        network = self.get_network(project_id)
        has_dependencies = len(network.get("edges", [])) > 0
        criteria["dependency_network_mapped"] = has_dependencies
        if not has_dependencies and benefits:
            gaps.append("No benefits dependency network has been mapped.")
            recommendations.append("Map the benefits dependency network from outputs to strategic objectives.")

        has_disbenefits = any(b.is_disbenefit for b in benefits)
        criteria["disbenefits_tracked"] = has_disbenefits
        if not has_disbenefits and benefits:
            gaps.append("No dis-benefits have been identified or tracked.")
            recommendations.append("Identify and track dis-benefits alongside positive benefits.")

        has_lifecycle_progression = any(
            b.status not in (BenefitStatus.IDENTIFIED,)
            for b in benefits
        ) if benefits else False
        criteria["lifecycle_active"] = has_lifecycle_progression
        if not has_lifecycle_progression and benefits:
            gaps.append("All benefits are still in IDENTIFIED status.")
            recommendations.append("Progress benefits through the lifecycle as planning matures.")

        has_business_case_refs = any(b.business_case_ref is not None for b in benefits)
        criteria["business_case_linked"] = has_business_case_refs
        if not has_business_case_refs and benefits:
            gaps.append("No benefits are linked to business case references.")
            recommendations.append("Link benefits to their originating business case documents.")

        # --- Level 5 (Optimised): Forecasting, assumptions, interim targets ---
        has_interim_targets = any(len(b.interim_targets) > 0 for b in benefits)
        criteria["interim_targets_defined"] = has_interim_targets
        if not has_interim_targets and benefits:
            gaps.append("No benefits have time-phased interim targets.")
            recommendations.append("Define interim target profiles for ramp-up/tail-off tracking.")

        has_assumption_links = any(len(b.associated_assumptions) > 0 for b in benefits)
        criteria["assumptions_linked"] = has_assumption_links
        if not has_assumption_links and benefits:
            gaps.append("No benefits are linked to tracked assumptions.")
            recommendations.append("Link benefits to assumption tracker entries for cross-domain drift detection.")

        all_measured = benefits_with_measurements == len(benefits) if benefits else False
        criteria["comprehensive_measurement"] = all_measured
        if not all_measured and benefits:
            gaps.append(
                f"Only {benefits_with_measurements}/{len(benefits)} benefits have measurements."
            )
            recommendations.append("Ensure all benefits have at least one measurement recorded.")

        # Score
        criteria_met = sum(1 for v in criteria.values() if v)
        criteria_total = len(criteria)
        score_pct = (criteria_met / criteria_total * 100) if criteria_total > 0 else 0.0

        # Determine level (weakest-link: highest level where all lower thresholds met)
        level = BenefitsMaturityLevel.AWARENESS
        for ml in (
            BenefitsMaturityLevel.REPEATABLE,
            BenefitsMaturityLevel.DEFINED,
            BenefitsMaturityLevel.MANAGED,
            BenefitsMaturityLevel.OPTIMISED,
        ):
            if score_pct >= MATURITY_THRESHOLDS[ml]:
                level = ml

        message = (
            f"Benefits management maturity: Level {level.value} ({level.name}). "
            f"Score: {score_pct:.0f}% ({criteria_met}/{criteria_total} criteria met). "
            f"{len(gaps)} evidence gap(s) identified."
        )

        logger.info(
            "benefits_maturity_assessed",
            project_id=project_id,
            level=level.value,
            score_pct=score_pct,
            criteria_met=criteria_met,
        )

        return BenefitsMaturityAssessment(
            project_id=project_id,
            timestamp=now,
            level=level,
            score_pct=score_pct,
            criteria_total=criteria_total,
            criteria_met=criteria_met,
            criteria_details=criteria,
            evidence_gaps=gaps,
            recommendations=recommendations,
            message=message,
        )

    # ------------------------------------------------------------------
    # Narrative context builder
    # ------------------------------------------------------------------

    def build_narrative_context(self, project_id: str) -> dict[str, Any]:
        """Build rich context dict for narrative generation from register data.

        This context can be passed to the existing NarrativeGenerator's
        ``generate_benefits_narrative()`` method, enriching it with data
        from the benefits register instead of manual inputs.

        Args:
            project_id: The project identifier.

        Returns:
            Dict with keys expected by NarrativeGenerator prompts, plus
            additional BRM-specific fields.
        """
        report = self.analyse_health(project_id)
        benefits = self.get_benefits(project_id)

        # Compute totals for GMPP-compatible fields
        total_planned = sum(
            b.target_value or 0.0
            for b in benefits
            if not b.is_disbenefit and b.financial_type in (
                FinancialType.CASH_RELEASING, FinancialType.NON_CASH_RELEASING
            )
        )
        realised = sum(
            b.current_actual_value or 0.0
            for b in benefits
            if not b.is_disbenefit
            and b.status == BenefitStatus.ACHIEVED
            and b.financial_type in (
                FinancialType.CASH_RELEASING, FinancialType.NON_CASH_RELEASING
            )
        )

        # Build per-benefit summaries
        benefit_summaries: list[str] = []
        for dr in report.drift_results:
            parts = [f"- {dr.benefit.title}: {dr.severity.value}"]
            if dr.realisation_pct is not None:
                parts.append(f"({dr.realisation_pct:.0f}% realised)")
            parts.append(f"trend={dr.trend.value}")
            benefit_summaries.append(" ".join(parts))

        return {
            "project_name": project_id,
            "total_benefits": total_planned,
            "realised_benefits": realised,
            "total_benefit_count": report.total_benefits,
            "disbenefit_count": report.total_disbenefits,
            "health_score": report.overall_health_score,
            "aggregate_realisation_pct": report.aggregate_realisation_pct,
            "at_risk_count": report.at_risk_count,
            "stale_count": report.stale_count,
            "by_status": report.by_status,
            "by_financial_type": report.by_financial_type,
            "by_recipient": report.by_recipient,
            "leading_indicator_warnings": report.leading_indicator_warnings,
            "benefit_summaries": "\n".join(benefit_summaries) if benefit_summaries else "No benefits tracked.",
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _classify_drift(self, drift_pct: float) -> DriftSeverity:
        """Classify drift percentage into a severity level.

        Args:
            drift_pct: Absolute drift percentage.

        Returns:
            The :class:`DriftSeverity` for this drift level.
        """
        if drift_pct <= self._config.minor_threshold_pct:
            return DriftSeverity.NONE
        if drift_pct <= self._config.moderate_threshold_pct:
            return DriftSeverity.MINOR
        if drift_pct <= self._config.significant_threshold_pct:
            return DriftSeverity.MODERATE
        if drift_pct <= self._config.significant_threshold_pct * 1.5:
            return DriftSeverity.SIGNIFICANT
        return DriftSeverity.CRITICAL

    def _compute_trend(self, values: list[float]) -> TrendDirection:
        """Compute trend direction from a list of measurement values.

        Uses simple sign of slope from first to last value.

        Args:
            values: Ordered measurement values (oldest first).

        Returns:
            The :class:`TrendDirection`.
        """
        if len(values) < self._config.min_measurements_for_trend:
            return TrendDirection.INSUFFICIENT_DATA

        # Simple: compare last value to first
        first = values[0]
        last = values[-1]
        diff = last - first

        if abs(diff) < 0.01 * abs(first) if first != 0 else abs(diff) < 0.01:
            return TrendDirection.STABLE
        if diff > 0:
            return TrendDirection.IMPROVING
        return TrendDirection.DECLINING

    @staticmethod
    def _compute_realisation_pct_from_values(
        baseline: float | None,
        target: float | None,
        current: float | None,
        is_disbenefit: bool = False,
    ) -> float | None:
        """Compute realisation percentage.

        Args:
            baseline: Baseline value.
            target: Target value.
            current: Current actual value.
            is_disbenefit: Whether this is a dis-benefit.

        Returns:
            Percentage realised (0-100+), or None if not computable.
        """
        if baseline is None or target is None or current is None:
            return None

        total_change = target - baseline
        if total_change == 0:
            return 100.0

        actual_change = current - baseline
        pct = (actual_change / total_change) * 100.0
        return pct

    @staticmethod
    def _has_cycle(adjacency: dict[str, list[str]]) -> bool:
        """Detect cycles in a directed graph using DFS.

        Args:
            adjacency: Adjacency list mapping source -> [targets].

        Returns:
            True if a cycle exists.
        """
        all_nodes: set[str] = set(adjacency.keys())
        for targets in adjacency.values():
            all_nodes.update(targets)

        white, gray, black = 0, 1, 2
        colour: dict[str, int] = {n: white for n in all_nodes}

        def dfs(node: str) -> bool:
            colour[node] = gray
            for neighbour in adjacency.get(node, []):
                if colour[neighbour] == gray:
                    return True
                if colour[neighbour] == white and dfs(neighbour):
                    return True
            colour[node] = black
            return False

        for node in all_nodes:
            if colour[node] == white:
                if dfs(node):
                    return True
        return False
