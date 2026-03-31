"""Agent Readiness Maturity Model (ARMM) — P12.

Implements the ARMM framework for assessing an organisation's readiness to
deploy AI agents in government project delivery contexts.

Four dimensions:

- **TECHNICAL_CONTROLS** (TC): Input validation, model evaluation, security,
  reliability testing, performance monitoring, logging, integration safety.
- **OPERATIONAL_RESILIENCE** (OR): Incident response, business continuity,
  operational monitoring, escalation paths, rollback procedures, disaster
  recovery, SLA management.
- **GOVERNANCE_ACCOUNTABILITY** (GA): Policy framework, ethics review, audit
  trail, risk management, accountability mapping, procurement controls,
  external audit.
- **CAPABILITY_CULTURE** (CC): Skills and training, leadership commitment,
  process adoption, change management, knowledge management, team capability,
  continuous improvement.

Total: 28 topics across four dimensions, 251 criteria.

Five maturity levels (0 = EXPERIMENTING → 4 = MISSION_CRITICAL).

Scoring rule: weakest-link.

- Topic score = percentage of criteria assessed as met (0–100).
- Dimension level = min of constituent topic levels.
- Overall level = min of all four dimension levels.

Usage::

    from pm_data_tools.assurance.armm import (
        ARMMScorer,
        ARMMAssessment,
        ARMMDimension,
        ARMMTopic,
        MaturityLevel,
        CriterionResult,
        ARMMReport,
        ARMMConfig,
    )
    from pm_data_tools.db.store import AssuranceStore

    store = AssuranceStore()
    scorer = ARMMScorer(store=store)

    assessment = scorer.assess(
        project_id="PROJ-001",
        criterion_results=[
            CriterionResult(criterion_id="TC-IV-1", met=True, evidence_ref="DOC-42"),
            CriterionResult(criterion_id="TC-IV-2", met=False, notes="Not yet implemented"),
        ],
        assessed_by="Assurance Lead",
    )
    report = scorer.get_report("PROJ-001")
    # report.overall_level → MaturityLevel.SUPERVISED
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum

import structlog
from pydantic import BaseModel, Field

from ..db.store import AssuranceStore

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Maturity levels
# ---------------------------------------------------------------------------


class MaturityLevel(int, Enum):
    """Five-level ARMM maturity scale (0 = EXPERIMENTING → 4 = MISSION_CRITICAL)."""

    EXPERIMENTING = 0
    SUPERVISED = 1
    RELIABLE = 2
    RESILIENT = 3
    MISSION_CRITICAL = 4


MATURITY_LABELS: dict[MaturityLevel, str] = {
    MaturityLevel.EXPERIMENTING: "Experimenting",
    MaturityLevel.SUPERVISED: "Supervised",
    MaturityLevel.RELIABLE: "Reliable",
    MaturityLevel.RESILIENT: "Resilient",
    MaturityLevel.MISSION_CRITICAL: "Mission-Critical",
}

MATURITY_DESCRIPTIONS: dict[MaturityLevel, str] = {
    MaturityLevel.EXPERIMENTING: (
        "AI agent use is exploratory. No formal controls, policies, or assurance "
        "processes are in place. High dependency on individual effort."
    ),
    MaturityLevel.SUPERVISED: (
        "Basic controls and human oversight are established. AI agents operate "
        "under active supervision with manual review of outputs."
    ),
    MaturityLevel.RELIABLE: (
        "Documented processes and technical safeguards are consistently applied. "
        "AI agents operate predictably within defined boundaries."
    ),
    MaturityLevel.RESILIENT: (
        "Quantitatively managed. The organisation can detect, respond to, and "
        "recover from AI agent failures with minimal service disruption."
    ),
    MaturityLevel.MISSION_CRITICAL: (
        "AI agents support critical public services with continuous improvement, "
        "full auditability, and proactive risk management embedded in culture."
    ),
}


# ---------------------------------------------------------------------------
# Dimensions and topics
# ---------------------------------------------------------------------------


class ARMMDimension(str, Enum):
    """Four ARMM dimensions."""

    TECHNICAL_CONTROLS = "TC"
    OPERATIONAL_RESILIENCE = "OR"
    GOVERNANCE_ACCOUNTABILITY = "GA"
    CAPABILITY_CULTURE = "CC"


DIMENSION_LABELS: dict[ARMMDimension, str] = {
    ARMMDimension.TECHNICAL_CONTROLS: "Technical Controls",
    ARMMDimension.OPERATIONAL_RESILIENCE: "Operational Resilience",
    ARMMDimension.GOVERNANCE_ACCOUNTABILITY: "Governance & Accountability",
    ARMMDimension.CAPABILITY_CULTURE: "Capability & Culture",
}


class ARMMTopic(str, Enum):
    """Twenty-eight ARMM topics across four dimensions.

    Code format: ``{dimension_code}-{topic_code}``.
    """

    # Technical Controls (TC) — 7 topics, 75 criteria
    TC_IV = "TC-IV"   # Input Validation                (10)
    TC_ME = "TC-ME"   # Model Evaluation                (11)
    TC_SC = "TC-SC"   # Security Controls               (10)
    TC_RT = "TC-RT"   # Reliability Testing             (11)
    TC_PM = "TC-PM"   # Performance Monitoring          (12)
    TC_LO = "TC-LO"   # Logging & Observability         (11)
    TC_IS = "TC-IS"   # Integration Safety              (10)

    # Operational Resilience (OR) — 7 topics, 64 criteria
    OR_IR = "OR-IR"   # Incident Response               (9)
    OR_BC = "OR-BC"   # Business Continuity             (9)
    OR_OM = "OR-OM"   # Operational Monitoring          (9)
    OR_EP = "OR-EP"   # Escalation Paths                (9)
    OR_RP = "OR-RP"   # Rollback Procedures             (9)
    OR_DR = "OR-DR"   # Disaster Recovery               (9)
    OR_SL = "OR-SL"   # SLA Management                  (10)

    # Governance & Accountability (GA) — 7 topics, 60 criteria
    GA_PF = "GA-PF"   # Policy Framework                (9)
    GA_ER = "GA-ER"   # Ethics Review                   (8)
    GA_AT = "GA-AT"   # Audit Trail                     (9)
    GA_RM = "GA-RM"   # Risk Management                 (8)
    GA_AM = "GA-AM"   # Accountability Mapping          (9)
    GA_PC = "GA-PC"   # Procurement Controls            (8)
    GA_EA = "GA-EA"   # External Audit                  (9)

    # Capability & Culture (CC) — 7 topics, 52 criteria
    CC_SK = "CC-SK"   # Skills & Training               (8)
    CC_LC = "CC-LC"   # Leadership Commitment           (7)
    CC_PA = "CC-PA"   # Process Adoption                (8)
    CC_CM = "CC-CM"   # Change Management               (7)
    CC_KM = "CC-KM"   # Knowledge Management            (7)
    CC_TC = "CC-TC"   # Team Capability                 (8)
    CC_CI = "CC-CI"   # Continuous Improvement          (7)


TOPIC_LABELS: dict[ARMMTopic, str] = {
    ARMMTopic.TC_IV: "Input Validation",
    ARMMTopic.TC_ME: "Model Evaluation",
    ARMMTopic.TC_SC: "Security Controls",
    ARMMTopic.TC_RT: "Reliability Testing",
    ARMMTopic.TC_PM: "Performance Monitoring",
    ARMMTopic.TC_LO: "Logging & Observability",
    ARMMTopic.TC_IS: "Integration Safety",
    ARMMTopic.OR_IR: "Incident Response",
    ARMMTopic.OR_BC: "Business Continuity",
    ARMMTopic.OR_OM: "Operational Monitoring",
    ARMMTopic.OR_EP: "Escalation Paths",
    ARMMTopic.OR_RP: "Rollback Procedures",
    ARMMTopic.OR_DR: "Disaster Recovery",
    ARMMTopic.OR_SL: "SLA Management",
    ARMMTopic.GA_PF: "Policy Framework",
    ARMMTopic.GA_ER: "Ethics Review",
    ARMMTopic.GA_AT: "Audit Trail",
    ARMMTopic.GA_RM: "Risk Management",
    ARMMTopic.GA_AM: "Accountability Mapping",
    ARMMTopic.GA_PC: "Procurement Controls",
    ARMMTopic.GA_EA: "External Audit",
    ARMMTopic.CC_SK: "Skills & Training",
    ARMMTopic.CC_LC: "Leadership Commitment",
    ARMMTopic.CC_PA: "Process Adoption",
    ARMMTopic.CC_CM: "Change Management",
    ARMMTopic.CC_KM: "Knowledge Management",
    ARMMTopic.CC_TC: "Team Capability",
    ARMMTopic.CC_CI: "Continuous Improvement",
}

# Topics per dimension (in order)
DIMENSION_TOPICS: dict[ARMMDimension, list[ARMMTopic]] = {
    ARMMDimension.TECHNICAL_CONTROLS: [
        ARMMTopic.TC_IV, ARMMTopic.TC_ME, ARMMTopic.TC_SC, ARMMTopic.TC_RT,
        ARMMTopic.TC_PM, ARMMTopic.TC_LO, ARMMTopic.TC_IS,
    ],
    ARMMDimension.OPERATIONAL_RESILIENCE: [
        ARMMTopic.OR_IR, ARMMTopic.OR_BC, ARMMTopic.OR_OM, ARMMTopic.OR_EP,
        ARMMTopic.OR_RP, ARMMTopic.OR_DR, ARMMTopic.OR_SL,
    ],
    ARMMDimension.GOVERNANCE_ACCOUNTABILITY: [
        ARMMTopic.GA_PF, ARMMTopic.GA_ER, ARMMTopic.GA_AT, ARMMTopic.GA_RM,
        ARMMTopic.GA_AM, ARMMTopic.GA_PC, ARMMTopic.GA_EA,
    ],
    ARMMDimension.CAPABILITY_CULTURE: [
        ARMMTopic.CC_SK, ARMMTopic.CC_LC, ARMMTopic.CC_PA, ARMMTopic.CC_CM,
        ARMMTopic.CC_KM, ARMMTopic.CC_TC, ARMMTopic.CC_CI,
    ],
}

# Topic → parent dimension
TOPIC_DIMENSION: dict[ARMMTopic, ARMMDimension] = {
    topic: dim
    for dim, topics in DIMENSION_TOPICS.items()
    for topic in topics
}

# Number of criteria per topic
TOPIC_CRITERIA_COUNT: dict[ARMMTopic, int] = {
    ARMMTopic.TC_IV: 10, ARMMTopic.TC_ME: 11, ARMMTopic.TC_SC: 10,
    ARMMTopic.TC_RT: 11, ARMMTopic.TC_PM: 12, ARMMTopic.TC_LO: 11,
    ARMMTopic.TC_IS: 10,
    ARMMTopic.OR_IR: 9, ARMMTopic.OR_BC: 9, ARMMTopic.OR_OM: 9,
    ARMMTopic.OR_EP: 9, ARMMTopic.OR_RP: 9, ARMMTopic.OR_DR: 9,
    ARMMTopic.OR_SL: 10,
    ARMMTopic.GA_PF: 9, ARMMTopic.GA_ER: 8, ARMMTopic.GA_AT: 9,
    ARMMTopic.GA_RM: 8, ARMMTopic.GA_AM: 9, ARMMTopic.GA_PC: 8,
    ARMMTopic.GA_EA: 9,
    ARMMTopic.CC_SK: 8, ARMMTopic.CC_LC: 7, ARMMTopic.CC_PA: 8,
    ARMMTopic.CC_CM: 7, ARMMTopic.CC_KM: 7, ARMMTopic.CC_TC: 8,
    ARMMTopic.CC_CI: 7,
}

# Level thresholds: minimum % of criteria met to reach a given level
# (applied per topic — weakest-link propagates up)
LEVEL_THRESHOLDS: dict[MaturityLevel, float] = {
    MaturityLevel.EXPERIMENTING: 0.0,    # default — any score qualifies
    MaturityLevel.SUPERVISED: 25.0,      # 25% of criteria met
    MaturityLevel.RELIABLE: 50.0,        # 50%
    MaturityLevel.RESILIENT: 75.0,       # 75%
    MaturityLevel.MISSION_CRITICAL: 90.0,  # 90%
}


def _score_to_level(pct: float) -> MaturityLevel:
    """Map a percentage score (0–100) to a MaturityLevel via threshold table."""
    level = MaturityLevel.EXPERIMENTING
    for ml in (
        MaturityLevel.SUPERVISED,
        MaturityLevel.RELIABLE,
        MaturityLevel.RESILIENT,
        MaturityLevel.MISSION_CRITICAL,
    ):
        if pct >= LEVEL_THRESHOLDS[ml]:
            level = ml
    return level


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class CriterionResult(BaseModel):
    """Assessment result for a single ARMM criterion."""

    criterion_id: str  # e.g. "TC-IV-1", "OR-BC-3"
    met: bool
    evidence_ref: str | None = None  # document ID, URL, or artefact ref
    notes: str = ""


class ARMMTopicResult(BaseModel):
    """Aggregated result for a single ARMM topic."""

    topic: ARMMTopic
    dimension: ARMMDimension
    total_criteria: int
    criteria_met: int
    score_pct: float  # 0–100
    level: MaturityLevel
    blocking: bool = False  # True if this topic is the weakest link


class ARMMDimensionResult(BaseModel):
    """Aggregated result for a single ARMM dimension."""

    dimension: ARMMDimension
    topic_results: dict[str, ARMMTopicResult] = Field(default_factory=dict)
    level: MaturityLevel  # min of constituent topic levels
    score_pct: float  # average topic score within dimension
    blocking_topic: str | None = None  # topic code that is weakest


class ARMMAssessment(BaseModel):
    """Full ARMM assessment for a project."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str
    assessed_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    assessed_by: str = ""
    criterion_results: list[CriterionResult] = Field(default_factory=list)
    topic_results: dict[str, ARMMTopicResult] = Field(default_factory=dict)
    dimension_results: dict[str, ARMMDimensionResult] = Field(default_factory=dict)
    overall_level: MaturityLevel = MaturityLevel.EXPERIMENTING
    overall_score_pct: float = 0.0  # average across all criteria
    criteria_total: int = 0
    criteria_met: int = 0
    notes: str = ""


class ARMMReport(BaseModel):
    """Summary ARMM report for a project, derived from the latest assessment."""

    project_id: str
    latest_assessment_id: str | None = None
    assessed_at: str | None = None
    overall_level: MaturityLevel = MaturityLevel.EXPERIMENTING
    overall_score_pct: float = 0.0
    criteria_total: int = 0
    criteria_met: int = 0
    dimension_levels: dict[str, int] = Field(default_factory=dict)
    dimension_scores: dict[str, float] = Field(default_factory=dict)
    dimension_blocking_topics: dict[str, str | None] = Field(default_factory=dict)
    topic_levels: dict[str, int] = Field(default_factory=dict)
    topic_scores: dict[str, float] = Field(default_factory=dict)
    blocking_dimension: str | None = None
    history_count: int = 0
    maturity_trend: str = "stable"  # "improving" | "stable" | "declining"


class ARMMConfig(BaseModel):
    """Configuration for the ARMMScorer."""

    # Minimum % criteria met to reach each level (can be overridden)
    level_thresholds: dict[int, float] = Field(
        default_factory=lambda: {int(ml): v for ml, v in LEVEL_THRESHOLDS.items()}
    )


# ---------------------------------------------------------------------------
# Scorer
# ---------------------------------------------------------------------------


class ARMMScorer:
    """Computes and persists ARMM assessments using weakest-link scoring.

    Args:
        store: Shared :class:`~pm_data_tools.db.store.AssuranceStore` instance.
        config: Optional :class:`ARMMConfig` overriding level thresholds.
    """

    def __init__(
        self,
        store: AssuranceStore,
        config: ARMMConfig | None = None,
    ) -> None:
        self.store = store
        self.config = config or ARMMConfig()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def assess(
        self,
        project_id: str,
        criterion_results: list[CriterionResult],
        assessed_by: str = "",
        notes: str = "",
    ) -> ARMMAssessment:
        """Record a new ARMM assessment from a set of criterion results.

        Args:
            project_id: Unique project identifier.
            criterion_results: List of :class:`CriterionResult` for each
                criterion evaluated in this assessment.
            assessed_by: Name / role of the person conducting the assessment.
            notes: Free-text notes for this assessment.

        Returns:
            Fully computed and persisted :class:`ARMMAssessment`.
        """
        topic_results, dimension_results, overall_level, overall_pct = (
            self._compute(criterion_results)
        )
        criteria_met = sum(1 for r in criterion_results if r.met)
        assessment = ARMMAssessment(
            project_id=project_id,
            assessed_by=assessed_by,
            criterion_results=criterion_results,
            topic_results=topic_results,
            dimension_results=dimension_results,
            overall_level=overall_level,
            overall_score_pct=overall_pct,
            criteria_total=len(criterion_results),
            criteria_met=criteria_met,
            notes=notes,
        )
        self.store.upsert_armm_assessment(_assessment_to_dict(assessment))
        logger.info(
            "armm_assessment_recorded",
            project_id=project_id,
            overall_level=overall_level.name,
            overall_score_pct=overall_pct,
            criteria_total=len(criterion_results),
            criteria_met=criteria_met,
        )
        return assessment

    def get_report(self, project_id: str) -> ARMMReport:
        """Return an :class:`ARMMReport` for the latest assessment of a project.

        Args:
            project_id: Unique project identifier.

        Returns:
            :class:`ARMMReport` with overall level, dimension breakdown, and trend.
        """
        import json

        rows = self.store.get_armm_assessments(project_id)
        report = ARMMReport(project_id=project_id, history_count=len(rows))
        if not rows:
            return report

        latest = rows[-1]
        topic_scores_raw: dict[str, float] = json.loads(latest["topic_scores_json"])
        topic_levels_raw: dict[str, int] = json.loads(latest["topic_levels_json"])
        dim_scores_raw: dict[str, float] = json.loads(latest["dimension_scores_json"])
        dim_levels_raw: dict[str, int] = json.loads(latest["dimension_levels_json"])
        dim_blocking_raw: dict[str, str | None] = json.loads(
            latest["dimension_blocking_json"]
        )

        # Identify weakest dimension
        blocking_dim: str | None = None
        if dim_levels_raw:
            blocking_dim = min(dim_levels_raw, key=lambda k: dim_levels_raw[k])

        # Maturity trend
        trend = "stable"
        if len(rows) >= 2:
            prev_pct = rows[-2]["overall_score_pct"]
            delta = latest["overall_score_pct"] - prev_pct
            if delta > 3.0:
                trend = "improving"
            elif delta < -3.0:
                trend = "declining"

        report.latest_assessment_id = latest["id"]
        report.assessed_at = latest["assessed_at"]
        report.overall_level = MaturityLevel(latest["overall_level"])
        report.overall_score_pct = latest["overall_score_pct"]
        report.criteria_total = latest["criteria_total"]
        report.criteria_met = latest["criteria_met"]
        report.dimension_levels = dim_levels_raw
        report.dimension_scores = dim_scores_raw
        report.dimension_blocking_topics = dim_blocking_raw
        report.topic_levels = topic_levels_raw
        report.topic_scores = topic_scores_raw
        report.blocking_dimension = blocking_dim
        report.maturity_trend = trend
        return report

    def get_portfolio_overview(
        self, project_ids: list[str] | None = None
    ) -> list[ARMMReport]:
        """Return :class:`ARMMReport` for multiple projects.

        Args:
            project_ids: Project IDs to include.  ``None`` retrieves all
                projects with ARMM data.

        Returns:
            List of :class:`ARMMReport` objects.
        """
        if project_ids is None:
            project_ids = self.store.get_armm_project_ids()
        return [self.get_report(pid) for pid in project_ids]

    # ------------------------------------------------------------------
    # Scoring engine (weakest-link)
    # ------------------------------------------------------------------

    def _compute(
        self, criterion_results: list[CriterionResult]
    ) -> tuple[
        dict[str, ARMMTopicResult],
        dict[str, ARMMDimensionResult],
        MaturityLevel,
        float,
    ]:
        """Compute topic, dimension, and overall scores from criterion results.

        Scoring rules:
        - Topic score = % criteria met for that topic.
        - Topic level = threshold lookup on topic score.
        - Dimension level = min of constituent topic levels (weakest-link).
        - Overall level = min of all dimension levels.

        Returns:
            Tuple of (topic_results, dimension_results, overall_level, overall_pct).
        """
        # Bucket results by topic
        topic_met: dict[ARMMTopic, int] = {t: 0 for t in ARMMTopic}
        topic_total: dict[ARMMTopic, int] = {t: 0 for t in ARMMTopic}

        for r in criterion_results:
            topic_code = _criterion_to_topic(r.criterion_id)
            if topic_code is None:
                continue
            topic_total[topic_code] += 1
            if r.met:
                topic_met[topic_code] += 1

        # Compute topic results
        topic_results: dict[str, ARMMTopicResult] = {}
        for topic in ARMMTopic:
            total = topic_total[topic]
            met = topic_met[topic]
            if total == 0:
                # No criteria assessed for this topic — use 0%
                pct = 0.0
            else:
                pct = round(met / total * 100, 2)
            level = _score_to_level(pct)
            topic_results[topic.value] = ARMMTopicResult(
                topic=topic,
                dimension=TOPIC_DIMENSION[topic],
                total_criteria=total,
                criteria_met=met,
                score_pct=pct,
                level=level,
            )

        # Compute dimension results (weakest-link on topic levels)
        dimension_results: dict[str, ARMMDimensionResult] = {}
        dim_levels: list[MaturityLevel] = []
        for dim in ARMMDimension:
            dim_topics = DIMENSION_TOPICS[dim]
            d_topic_results = {t.value: topic_results[t.value] for t in dim_topics}
            topic_levels = [d_topic_results[t.value].level for t in dim_topics]
            dim_level = min(topic_levels, key=lambda l: int(l))
            topic_scores = [d_topic_results[t.value].score_pct for t in dim_topics]
            avg_score = round(sum(topic_scores) / len(topic_scores), 2)

            # Mark blocking topic
            min_level = int(dim_level)
            blocking_topic: str | None = None
            for t in dim_topics:
                tr = d_topic_results[t.value]
                if int(tr.level) == min_level:
                    tr.blocking = True
                    if blocking_topic is None:
                        blocking_topic = t.value

            dimension_results[dim.value] = ARMMDimensionResult(
                dimension=dim,
                topic_results=d_topic_results,
                level=dim_level,
                score_pct=avg_score,
                blocking_topic=blocking_topic,
            )
            dim_levels.append(dim_level)

        # Overall (weakest-link across dimensions)
        overall_level = min(dim_levels, key=lambda l: int(l))
        overall_pct = (
            round(
                sum(topic_results[t.value].score_pct for t in ARMMTopic) / len(ARMMTopic),
                2,
            )
            if topic_results
            else 0.0
        )

        return topic_results, dimension_results, overall_level, overall_pct


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _criterion_to_topic(criterion_id: str) -> ARMMTopic | None:
    """Extract the ARMMTopic from a criterion ID (e.g. 'TC-IV-1' → TC_IV).

    Args:
        criterion_id: Criterion identifier with format ``{dim}-{topic}-{n}``.

    Returns:
        :class:`ARMMTopic` or ``None`` if not recognised.
    """
    parts = criterion_id.split("-")
    if len(parts) < 2:
        return None
    topic_code = f"{parts[0]}-{parts[1]}"
    try:
        return ARMMTopic(topic_code)
    except ValueError:
        return None


def _assessment_to_dict(assessment: ARMMAssessment) -> dict[str, object]:
    """Serialise an ARMMAssessment to a store-ready dict."""
    import json

    topic_scores = {k: v.score_pct for k, v in assessment.topic_results.items()}
    topic_levels = {k: int(v.level) for k, v in assessment.topic_results.items()}
    dim_scores = {k: v.score_pct for k, v in assessment.dimension_results.items()}
    dim_levels = {k: int(v.level) for k, v in assessment.dimension_results.items()}
    dim_blocking = {k: v.blocking_topic for k, v in assessment.dimension_results.items()}

    return {
        "id": assessment.id,
        "project_id": assessment.project_id,
        "assessed_at": assessment.assessed_at,
        "assessed_by": assessment.assessed_by,
        "overall_level": int(assessment.overall_level),
        "overall_score_pct": assessment.overall_score_pct,
        "criteria_total": assessment.criteria_total,
        "criteria_met": assessment.criteria_met,
        "topic_scores_json": json.dumps(topic_scores),
        "topic_levels_json": json.dumps(topic_levels),
        "dimension_scores_json": json.dumps(dim_scores),
        "dimension_levels_json": json.dumps(dim_levels),
        "dimension_blocking_json": json.dumps(dim_blocking),
        "notes": assessment.notes,
    }
