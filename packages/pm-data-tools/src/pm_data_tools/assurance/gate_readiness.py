"""Gate Readiness Assessor (P14).

Synthesises data from all existing assurance modules (P1-P12) to produce a
composite gate-specific readiness assessment. Reads persisted data — does
not re-execute any module. Supports all 7 IPA review points (Gate 0-5 + PAR)
with gate-specific dimension weighting.

Eight assessment dimensions:

- **ARTEFACT_READINESS** (P1, P3): Are evidence documents current? Are
  review actions closed?
- **DATA_QUALITY** (P2, P4): Is compliance data trending well? Is AI
  extraction reliable?
- **ASSUMPTION_HEALTH** (P11): Are assumptions validated and within tolerance?
- **GOVERNANCE_MATURITY** (P6, P12): Are override patterns healthy? Is
  organisational readiness adequate?
- **REVIEW_TIMING** (P5): Is the review timing appropriate?
- **ASSURANCE_EFFICIENCY** (P8): Is the right assurance effort being applied?
- **OPERATIONAL_LEARNING** (P7): Are lessons being captured and applied?
- **COMPLEXITY_ALIGNMENT** (P10): Is assurance appropriate for the complexity?

Usage::

    from pm_data_tools.assurance.gate_readiness import (
        GateReadinessAssessor,
        GateType,
        ReadinessLevel,
    )
    from pm_data_tools.db.store import AssuranceStore

    store = AssuranceStore()
    assessor = GateReadinessAssessor(store=store)

    result = assessor.assess("PROJ-001", GateType.GATE_3)
    # result.readiness -> ReadinessLevel.CONDITIONALLY_READY
    # result.composite_score -> 0.62
    # result.blocking_issues -> ["3 assumptions with CRITICAL drift"]
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from enum import Enum

import structlog
from pydantic import BaseModel, Field

from ..db.store import AssuranceStore

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class GateType(str, Enum):
    """IPA assurance review points.

    Attributes:
        GATE_0: Opportunity Framing.
        GATE_1: Strategic Outline Case.
        GATE_2: Outline Business Case.
        GATE_3: Full Business Case.
        GATE_4: Readiness for Service / Work to Realise.
        GATE_5: Operations Review & Benefits Realisation.
        PAR: Project Assessment Review (any stage).
    """

    GATE_0 = "GATE_0"
    GATE_1 = "GATE_1"
    GATE_2 = "GATE_2"
    GATE_3 = "GATE_3"
    GATE_4 = "GATE_4"
    GATE_5 = "GATE_5"
    PAR = "PAR"


GATE_LABELS: dict[GateType, str] = {
    GateType.GATE_0: "Gate 0 — Opportunity Framing",
    GateType.GATE_1: "Gate 1 — Strategic Outline Case",
    GateType.GATE_2: "Gate 2 — Outline Business Case",
    GateType.GATE_3: "Gate 3 — Full Business Case",
    GateType.GATE_4: "Gate 4 — Readiness for Service",
    GateType.GATE_5: "Gate 5 — Operations Review & Benefits",
    GateType.PAR: "Project Assessment Review",
}


class ReadinessLevel(str, Enum):
    """Gate readiness classification.

    Attributes:
        READY: All dimensions healthy, no blocking issues.
        CONDITIONALLY_READY: Mostly ready, minor gaps or limited data coverage.
        AT_RISK: Significant gaps in multiple dimensions.
        NOT_READY: Critical blocking issues or widespread deficiencies.
    """

    READY = "READY"
    CONDITIONALLY_READY = "CONDITIONALLY_READY"
    AT_RISK = "AT_RISK"
    NOT_READY = "NOT_READY"


class AssessmentDimension(str, Enum):
    """Eight assessment dimensions mapped to source modules.

    Attributes:
        ARTEFACT_READINESS: P1 + P3 — document currency and action closure.
        DATA_QUALITY: P2 + P4 — compliance trends and AI confidence.
        ASSUMPTION_HEALTH: P11 — assumption drift and staleness.
        GOVERNANCE_MATURITY: P6 + P12 — overrides and organisational readiness.
        REVIEW_TIMING: P5 — review scheduling signals.
        ASSURANCE_EFFICIENCY: P8 — assurance effort effectiveness.
        OPERATIONAL_LEARNING: P7 — lessons learned capture.
        COMPLEXITY_ALIGNMENT: P10 — domain-appropriate assurance.
    """

    ARTEFACT_READINESS = "ARTEFACT_READINESS"
    DATA_QUALITY = "DATA_QUALITY"
    ASSUMPTION_HEALTH = "ASSUMPTION_HEALTH"
    GOVERNANCE_MATURITY = "GOVERNANCE_MATURITY"
    REVIEW_TIMING = "REVIEW_TIMING"
    ASSURANCE_EFFICIENCY = "ASSURANCE_EFFICIENCY"
    OPERATIONAL_LEARNING = "OPERATIONAL_LEARNING"
    COMPLEXITY_ALIGNMENT = "COMPLEXITY_ALIGNMENT"


DIMENSION_LABELS: dict[AssessmentDimension, str] = {
    AssessmentDimension.ARTEFACT_READINESS: "Artefact Readiness",
    AssessmentDimension.DATA_QUALITY: "Data Quality",
    AssessmentDimension.ASSUMPTION_HEALTH: "Assumption Health",
    AssessmentDimension.GOVERNANCE_MATURITY: "Governance & Maturity",
    AssessmentDimension.REVIEW_TIMING: "Review Timing",
    AssessmentDimension.ASSURANCE_EFFICIENCY: "Assurance Efficiency",
    AssessmentDimension.OPERATIONAL_LEARNING: "Operational Learning",
    AssessmentDimension.COMPLEXITY_ALIGNMENT: "Complexity Alignment",
}


class DimensionStatus(str, Enum):
    """Whether a dimension could be scored.

    Attributes:
        SCORED: Full data available from all sources.
        PARTIAL: Some source data missing.
        NO_DATA: No data available for this dimension.
    """

    SCORED = "SCORED"
    PARTIAL = "PARTIAL"
    NO_DATA = "NO_DATA"


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class DimensionScore(BaseModel):
    """Score for a single assessment dimension.

    Attributes:
        dimension: Which dimension was scored.
        score: Raw score (0.0-1.0, where 1.0 = healthy/ready).
        status: Whether full, partial, or no data was available.
        weight: Gate-specific weight for this dimension.
        weighted_score: score * weight (used in composite).
        sources_available: Module codes that had data (e.g. ["P2", "P4"]).
        sources_missing: Module codes with no data.
        detail: Human-readable explanation of the score.
    """

    dimension: AssessmentDimension
    score: float
    status: DimensionStatus
    weight: float
    weighted_score: float
    sources_available: list[str]
    sources_missing: list[str]
    detail: str


class GateRiskSignal(BaseModel):
    """A risk signal generated during gate readiness assessment.

    Attributes:
        dimension: Source dimension.
        source: Module code (e.g. "P11").
        signal_name: Short description of the signal.
        severity: 0.0-1.0 severity score.
        is_blocking: True if severity >= critical threshold.
        detail: Full explanation.
    """

    dimension: AssessmentDimension
    source: str
    signal_name: str
    severity: float
    is_blocking: bool
    detail: str


class GateReadinessAssessment(BaseModel):
    """Full gate readiness assessment result.

    Attributes:
        id: Unique assessment identifier.
        project_id: The assessed project.
        gate: Which IPA gate was assessed.
        assessed_at: UTC timestamp.
        readiness: Overall readiness classification.
        composite_score: Weighted composite (0.0-1.0).
        dimension_scores: Per-dimension breakdown.
        risk_signals: All risk signals generated.
        blocking_issues: Issues that must be resolved before gate.
        recommended_actions: Prioritised improvement recommendations.
        data_availability: Which dimensions had data.
        dimensions_scored: Count of dimensions with data.
        dimensions_total: Total dimensions (always 8).
        executive_summary: Human-readable paragraph.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str
    gate: GateType
    assessed_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )
    readiness: ReadinessLevel
    composite_score: float
    dimension_scores: dict[str, DimensionScore]
    risk_signals: list[GateRiskSignal]
    blocking_issues: list[str]
    recommended_actions: list[str]
    data_availability: dict[str, bool]
    dimensions_scored: int
    dimensions_total: int = 8
    executive_summary: str


class GateComparisonResult(BaseModel):
    """Comparison between two gate readiness assessments.

    Attributes:
        project_id: The project.
        gate: The gate being compared.
        before: Earlier assessment.
        after: Later assessment.
        score_delta: Change in composite score.
        readiness_changed: Whether readiness level changed.
        improved_dimensions: Dimensions that improved.
        degraded_dimensions: Dimensions that degraded.
        resolved_blockers: Blocking issues no longer present.
        new_blockers: New blocking issues.
        message: Human-readable summary.
    """

    project_id: str
    gate: GateType
    before_id: str
    after_id: str
    before_score: float
    after_score: float
    before_readiness: ReadinessLevel
    after_readiness: ReadinessLevel
    score_delta: float
    readiness_changed: bool
    improved_dimensions: list[str]
    degraded_dimensions: list[str]
    resolved_blockers: list[str]
    new_blockers: list[str]
    message: str


class GateReadinessConfig(BaseModel):
    """Configuration for gate readiness assessment.

    Attributes:
        critical_signal_threshold: Severity at which a signal becomes blocking.
        min_dimensions_for_ready: Minimum scored dimensions to be READY.
        ready_threshold: Composite score >= this for READY.
        conditional_threshold: Composite score >= this for CONDITIONALLY_READY.
        at_risk_threshold: Composite score >= this for AT_RISK, below = NOT_READY.
    """

    critical_signal_threshold: float = 0.80
    min_dimensions_for_ready: int = 4
    ready_threshold: float = 0.75
    conditional_threshold: float = 0.50
    at_risk_threshold: float = 0.25


# ---------------------------------------------------------------------------
# Gate weight matrix — all rows sum to 1.0
# ---------------------------------------------------------------------------

_GATE_WEIGHT_MATRIX: dict[GateType, dict[AssessmentDimension, float]] = {
    GateType.GATE_0: {
        AssessmentDimension.ARTEFACT_READINESS: 0.05,
        AssessmentDimension.DATA_QUALITY: 0.10,
        AssessmentDimension.ASSUMPTION_HEALTH: 0.25,
        AssessmentDimension.GOVERNANCE_MATURITY: 0.20,
        AssessmentDimension.REVIEW_TIMING: 0.10,
        AssessmentDimension.ASSURANCE_EFFICIENCY: 0.05,
        AssessmentDimension.OPERATIONAL_LEARNING: 0.10,
        AssessmentDimension.COMPLEXITY_ALIGNMENT: 0.15,
    },
    GateType.GATE_1: {
        AssessmentDimension.ARTEFACT_READINESS: 0.10,
        AssessmentDimension.DATA_QUALITY: 0.15,
        AssessmentDimension.ASSUMPTION_HEALTH: 0.20,
        AssessmentDimension.GOVERNANCE_MATURITY: 0.15,
        AssessmentDimension.REVIEW_TIMING: 0.10,
        AssessmentDimension.ASSURANCE_EFFICIENCY: 0.05,
        AssessmentDimension.OPERATIONAL_LEARNING: 0.10,
        AssessmentDimension.COMPLEXITY_ALIGNMENT: 0.15,
    },
    GateType.GATE_2: {
        AssessmentDimension.ARTEFACT_READINESS: 0.15,
        AssessmentDimension.DATA_QUALITY: 0.20,
        AssessmentDimension.ASSUMPTION_HEALTH: 0.15,
        AssessmentDimension.GOVERNANCE_MATURITY: 0.10,
        AssessmentDimension.REVIEW_TIMING: 0.10,
        AssessmentDimension.ASSURANCE_EFFICIENCY: 0.05,
        AssessmentDimension.OPERATIONAL_LEARNING: 0.10,
        AssessmentDimension.COMPLEXITY_ALIGNMENT: 0.15,
    },
    GateType.GATE_3: {
        AssessmentDimension.ARTEFACT_READINESS: 0.20,
        AssessmentDimension.DATA_QUALITY: 0.15,
        AssessmentDimension.ASSUMPTION_HEALTH: 0.15,
        AssessmentDimension.GOVERNANCE_MATURITY: 0.10,
        AssessmentDimension.REVIEW_TIMING: 0.10,
        AssessmentDimension.ASSURANCE_EFFICIENCY: 0.05,
        AssessmentDimension.OPERATIONAL_LEARNING: 0.10,
        AssessmentDimension.COMPLEXITY_ALIGNMENT: 0.15,
    },
    GateType.GATE_4: {
        AssessmentDimension.ARTEFACT_READINESS: 0.15,
        AssessmentDimension.DATA_QUALITY: 0.10,
        AssessmentDimension.ASSUMPTION_HEALTH: 0.10,
        AssessmentDimension.GOVERNANCE_MATURITY: 0.20,
        AssessmentDimension.REVIEW_TIMING: 0.10,
        AssessmentDimension.ASSURANCE_EFFICIENCY: 0.10,
        AssessmentDimension.OPERATIONAL_LEARNING: 0.15,
        AssessmentDimension.COMPLEXITY_ALIGNMENT: 0.10,
    },
    GateType.GATE_5: {
        AssessmentDimension.ARTEFACT_READINESS: 0.10,
        AssessmentDimension.DATA_QUALITY: 0.10,
        AssessmentDimension.ASSUMPTION_HEALTH: 0.15,
        AssessmentDimension.GOVERNANCE_MATURITY: 0.10,
        AssessmentDimension.REVIEW_TIMING: 0.10,
        AssessmentDimension.ASSURANCE_EFFICIENCY: 0.15,
        AssessmentDimension.OPERATIONAL_LEARNING: 0.20,
        AssessmentDimension.COMPLEXITY_ALIGNMENT: 0.10,
    },
    GateType.PAR: {
        dim: 0.125 for dim in AssessmentDimension
    },
}


# ---------------------------------------------------------------------------
# Assessor
# ---------------------------------------------------------------------------


class GateReadinessAssessor:
    """Synthesise data from P1-P12 into a composite gate readiness assessment.

    Reads persisted data from the shared AssuranceStore — does not re-execute
    any module. Supports all 7 IPA review points with gate-specific dimension
    weighting.

    Example::

        store = AssuranceStore()
        assessor = GateReadinessAssessor(store=store)

        result = assessor.assess("PROJ-001", GateType.GATE_3)
        print(f"Readiness: {result.readiness.value}")
        print(f"Score: {result.composite_score:.0%}")
        for issue in result.blocking_issues:
            print(f"  BLOCKING: {issue}")
    """

    def __init__(
        self,
        store: AssuranceStore | None = None,
        config: GateReadinessConfig | None = None,
    ) -> None:
        self._store = store or AssuranceStore()
        self._config = config or GateReadinessConfig()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def assess(
        self, project_id: str, gate: GateType
    ) -> GateReadinessAssessment:
        """Run a full gate readiness assessment.

        Scores all 8 dimensions using persisted data from P1-P12, applies
        gate-specific weights, identifies blocking issues, and generates
        prioritised recommendations.

        Args:
            project_id: The project identifier.
            gate: Which IPA gate to assess for.

        Returns:
            A :class:`GateReadinessAssessment` with full results.
        """
        now = datetime.now(tz=timezone.utc)
        weights = _GATE_WEIGHT_MATRIX[gate]

        # Score each dimension
        scorers = {
            AssessmentDimension.ARTEFACT_READINESS: self._score_artefact_readiness,
            AssessmentDimension.DATA_QUALITY: self._score_data_quality,
            AssessmentDimension.ASSUMPTION_HEALTH: self._score_assumption_health,
            AssessmentDimension.GOVERNANCE_MATURITY: self._score_governance_maturity,
            AssessmentDimension.REVIEW_TIMING: self._score_review_timing,
            AssessmentDimension.ASSURANCE_EFFICIENCY: self._score_assurance_efficiency,
            AssessmentDimension.OPERATIONAL_LEARNING: self._score_operational_learning,
            AssessmentDimension.COMPLEXITY_ALIGNMENT: self._score_complexity_alignment,
        }

        dimension_scores: dict[str, DimensionScore] = {}
        for dim, scorer in scorers.items():
            ds = scorer(project_id)
            ds.weight = weights[dim]
            ds.weighted_score = ds.score * ds.weight if ds.status != DimensionStatus.NO_DATA else 0.0
            dimension_scores[dim.value] = ds

        # Composite score
        composite_score = self._compute_composite(dimension_scores, weights)

        # Data availability
        data_availability = {
            dim_key: ds.status != DimensionStatus.NO_DATA
            for dim_key, ds in dimension_scores.items()
        }
        dimensions_scored = sum(1 for v in data_availability.values() if v)

        # Risk signals
        signals = self._generate_signals(dimension_scores)

        # Blocking issues
        blocking_issues = [s.detail for s in signals if s.is_blocking]

        # Readiness classification
        readiness = self._classify_readiness(
            composite_score, signals, dimensions_scored
        )

        # Recommended actions
        recommended_actions = self._generate_actions(signals, dimension_scores)

        # Executive summary
        gate_label = GATE_LABELS.get(gate, gate.value)
        summary = (
            f"Gate readiness assessment for {gate_label}: "
            f"{readiness.value} (score: {composite_score:.0%}). "
            f"{dimensions_scored}/8 dimensions assessed. "
            f"{len(blocking_issues)} blocking issue(s). "
            f"{len(recommended_actions)} recommendation(s)."
        )

        assessment = GateReadinessAssessment(
            project_id=project_id,
            gate=gate,
            assessed_at=now,
            readiness=readiness,
            composite_score=composite_score,
            dimension_scores=dimension_scores,
            risk_signals=signals,
            blocking_issues=blocking_issues,
            recommended_actions=recommended_actions,
            data_availability=data_availability,
            dimensions_scored=dimensions_scored,
            executive_summary=summary,
        )

        # Persist
        self._store.insert_gate_readiness_assessment(
            {
                "id": assessment.id,
                "project_id": project_id,
                "gate": gate.value,
                "readiness": readiness.value,
                "composite_score": composite_score,
                "assessed_at": now.isoformat(),
                "result_json": assessment.model_dump_json(),
            }
        )

        logger.info(
            "gate_readiness_assessed",
            project_id=project_id,
            gate=gate.value,
            readiness=readiness.value,
            composite_score=composite_score,
            dimensions_scored=dimensions_scored,
        )

        return assessment

    def get_history(
        self,
        project_id: str,
        gate: GateType | None = None,
    ) -> list[GateReadinessAssessment]:
        """Retrieve past gate readiness assessments.

        Args:
            project_id: The project identifier.
            gate: Optional gate filter.

        Returns:
            List of assessments, oldest first.
        """
        rows = self._store.get_gate_readiness_history(
            project_id=project_id,
            gate=gate.value if gate else None,
        )
        results: list[GateReadinessAssessment] = []
        for row in rows:
            raw = row.get("result_json", "{}")
            results.append(
                GateReadinessAssessment.model_validate_json(str(raw))
            )
        return results

    def compare(
        self,
        assessment_id_before: str,
        assessment_id_after: str,
    ) -> GateComparisonResult:
        """Compare two gate readiness assessments.

        Args:
            assessment_id_before: ID of the earlier assessment.
            assessment_id_after: ID of the later assessment.

        Returns:
            A :class:`GateComparisonResult` with deltas.

        Raises:
            ValueError: If either assessment is not found.
        """
        before_row = self._store.get_gate_readiness_assessment_by_id(
            assessment_id_before
        )
        after_row = self._store.get_gate_readiness_assessment_by_id(
            assessment_id_after
        )

        if before_row is None:
            raise ValueError(f"Assessment {assessment_id_before!r} not found")
        if after_row is None:
            raise ValueError(f"Assessment {assessment_id_after!r} not found")

        before = GateReadinessAssessment.model_validate_json(
            str(before_row["result_json"])
        )
        after = GateReadinessAssessment.model_validate_json(
            str(after_row["result_json"])
        )

        # Dimension comparison
        improved: list[str] = []
        degraded: list[str] = []
        for dim_key in before.dimension_scores:
            if dim_key in after.dimension_scores:
                b_score = before.dimension_scores[dim_key].score
                a_score = after.dimension_scores[dim_key].score
                if a_score > b_score + 0.05:
                    improved.append(dim_key)
                elif a_score < b_score - 0.05:
                    degraded.append(dim_key)

        # Blocker comparison
        before_blockers = set(before.blocking_issues)
        after_blockers = set(after.blocking_issues)
        resolved = list(before_blockers - after_blockers)
        new = list(after_blockers - before_blockers)

        delta = after.composite_score - before.composite_score
        direction = "improved" if delta > 0 else "declined" if delta < 0 else "unchanged"

        message = (
            f"Gate readiness {direction} by {abs(delta):.0%} "
            f"({before.composite_score:.0%} -> {after.composite_score:.0%}). "
            f"{len(improved)} dimension(s) improved, {len(degraded)} degraded. "
            f"{len(resolved)} blocker(s) resolved, {len(new)} new."
        )

        return GateComparisonResult(
            project_id=after.project_id,
            gate=after.gate,
            before_id=before.id,
            after_id=after.id,
            before_score=before.composite_score,
            after_score=after.composite_score,
            before_readiness=before.readiness,
            after_readiness=after.readiness,
            score_delta=delta,
            readiness_changed=before.readiness != after.readiness,
            improved_dimensions=improved,
            degraded_dimensions=degraded,
            resolved_blockers=resolved,
            new_blockers=new,
            message=message,
        )

    # ------------------------------------------------------------------
    # Dimension scorers
    # ------------------------------------------------------------------

    def _score_artefact_readiness(
        self, project_id: str
    ) -> DimensionScore:
        """Score ARTEFACT_READINESS from P1 (currency) + P3 (actions)."""
        available: list[str] = []
        missing: list[str] = []
        scores: list[float] = []

        # P3: Review action closure rate
        recs = self._store.get_recommendations(project_id)
        if recs:
            available.append("P3")
            total = len(recs)
            closed = sum(
                1 for r in recs if str(r.get("status", "")) == "CLOSED"
            )
            closure_rate = closed / total if total > 0 else 1.0
            scores.append(closure_rate)
        else:
            missing.append("P3")

        # P1: Check latest workflow for currency data
        workflows = self._store.get_workflow_history(project_id)
        if workflows:
            latest = workflows[-1]
            result_raw = latest.get("result_json", "{}")
            try:
                result = json.loads(str(result_raw)) if isinstance(result_raw, str) else {}
                steps = result.get("steps", [])
                for step in steps:
                    if "currency" in str(step.get("step_name", "")).lower():
                        sev = step.get("risk_signal", {}).get("severity", 0.5)
                        scores.append(max(0.0, 1.0 - float(sev)))
                        available.append("P1")
                        break
                else:
                    missing.append("P1")
            except (json.JSONDecodeError, TypeError):
                missing.append("P1")
        else:
            missing.append("P1")

        return self._build_dimension_score(
            AssessmentDimension.ARTEFACT_READINESS,
            scores, available, missing,
            "Artefact currency and review action closure",
        )

    def _score_data_quality(self, project_id: str) -> DimensionScore:
        """Score DATA_QUALITY from P2 (compliance) + P4 (divergence)."""
        available: list[str] = []
        missing: list[str] = []
        scores: list[float] = []

        # P2: Latest NISTA compliance score
        compliance_rows = self._store.get_confidence_scores(project_id)
        if compliance_rows:
            available.append("P2")
            latest_score = float(compliance_rows[-1].get("score", 50))
            scores.append(min(latest_score / 100.0, 1.0))
        else:
            missing.append("P2")

        # P4: Latest divergence signal
        divergence_rows = self._store.get_divergence_history(project_id)
        if divergence_rows:
            available.append("P4")
            latest = divergence_rows[-1]
            signal_type = str(latest.get("signal_type", "STABLE"))
            signal_map = {
                "STABLE": 1.0,
                "LOW_CONSENSUS": 0.5,
                "HIGH_DIVERGENCE": 0.3,
                "DEGRADING_CONFIDENCE": 0.2,
            }
            scores.append(signal_map.get(signal_type, 0.5))
        else:
            missing.append("P4")

        return self._build_dimension_score(
            AssessmentDimension.DATA_QUALITY,
            scores, available, missing,
            "NISTA compliance trends and AI extraction confidence",
        )

    def _score_assumption_health(self, project_id: str) -> DimensionScore:
        """Score ASSUMPTION_HEALTH from P11."""
        available: list[str] = []
        missing: list[str] = []
        scores: list[float] = []

        assumptions = self._store.get_assumptions(project_id)
        if assumptions:
            available.append("P11")
            total = len(assumptions)
            # Count by severity from validations
            critical_count = 0
            significant_count = 0
            stale_count = 0
            for a in assumptions:
                validations = self._store.get_assumption_validations(
                    str(a["id"])
                )
                if validations:
                    latest = validations[-1]
                    sev = str(latest.get("severity", "NONE"))
                    if sev == "CRITICAL":
                        critical_count += 1
                    elif sev == "SIGNIFICANT":
                        significant_count += 1
                else:
                    stale_count += 1

            # Score: penalise critical/significant/stale
            penalty = (
                critical_count * 0.3
                + significant_count * 0.15
                + stale_count * 0.1
            ) / max(total, 1)
            scores.append(max(0.0, 1.0 - min(penalty, 1.0)))
        else:
            missing.append("P11")

        return self._build_dimension_score(
            AssessmentDimension.ASSUMPTION_HEALTH,
            scores, available, missing,
            "Assumption drift severity and staleness",
        )

    def _score_governance_maturity(self, project_id: str) -> DimensionScore:
        """Score GOVERNANCE_MATURITY from P6 (overrides) + P12 (ARMM)."""
        available: list[str] = []
        missing: list[str] = []
        scores: list[float] = []

        # P6: Override impact rate
        overrides = self._store.get_override_decisions(project_id)
        if overrides:
            available.append("P6")
            total = len(overrides)
            negative = sum(
                1
                for o in overrides
                if str(o.get("outcome", "")) in ("NEGATIVE", "WORSE_THAN_EXPECTED")
            )
            impact_rate = negative / total if total > 0 else 0.0
            scores.append(max(0.0, 1.0 - impact_rate))
        else:
            missing.append("P6")

        # P12: ARMM maturity level (0-4 normalised to 0-1)
        armm_assessments = self._store.get_armm_assessments(project_id)
        if armm_assessments:
            available.append("P12")
            armm_assessment = armm_assessments[-1]  # Latest
            level = int(armm_assessment.get("overall_level", 0))
            scores.append(level / 4.0)
        else:
            missing.append("P12")

        return self._build_dimension_score(
            AssessmentDimension.GOVERNANCE_MATURITY,
            scores, available, missing,
            "Governance override patterns and organisational maturity",
        )

    def _score_review_timing(self, project_id: str) -> DimensionScore:
        """Score REVIEW_TIMING from P5 (scheduler)."""
        available: list[str] = []
        missing: list[str] = []
        scores: list[float] = []

        schedule_rows = self._store.get_schedule_history(project_id)
        if schedule_rows:
            available.append("P5")
            latest = schedule_rows[-1]
            composite = float(latest.get("composite_score", 0.5))
            # P5 composite_score is severity (0=good, 1=bad), invert
            scores.append(max(0.0, 1.0 - composite))
        else:
            missing.append("P5")

        return self._build_dimension_score(
            AssessmentDimension.REVIEW_TIMING,
            scores, available, missing,
            "Review scheduling urgency signals from P1-P4",
        )

    def _score_assurance_efficiency(self, project_id: str) -> DimensionScore:
        """Score ASSURANCE_EFFICIENCY from P8 (overhead)."""
        available: list[str] = []
        missing: list[str] = []
        scores: list[float] = []

        activities = self._store.get_assurance_activities(project_id)
        if activities:
            available.append("P8")
            total = len(activities)
            # Check for zero-finding activities (waste)
            zero_findings = sum(
                1 for a in activities if int(a.get("findings_count", 0)) == 0
            )
            waste_rate = zero_findings / total if total > 0 else 0.0
            scores.append(max(0.0, 1.0 - waste_rate))
        else:
            missing.append("P8")

        return self._build_dimension_score(
            AssessmentDimension.ASSURANCE_EFFICIENCY,
            scores, available, missing,
            "Assurance activity effectiveness and waste rate",
        )

    def _score_operational_learning(self, project_id: str) -> DimensionScore:
        """Score OPERATIONAL_LEARNING from P7 (lessons)."""
        available: list[str] = []
        missing: list[str] = []
        scores: list[float] = []

        lessons = self._store.get_lessons(project_id)
        if lessons:
            available.append("P7")
            total = len(lessons)
            negative = sum(
                1 for l in lessons if str(l.get("sentiment", "")) == "NEGATIVE"
            )
            positive = sum(
                1 for l in lessons if str(l.get("sentiment", "")) == "POSITIVE"
            )
            # Score based on lessons captured (having lessons = good)
            # and sentiment balance
            if total > 0:
                sentiment_score = (positive + 0.5 * (total - positive - negative)) / total
            else:
                sentiment_score = 0.5
            # Bonus for having lessons at all (culture of learning)
            capture_score = min(1.0, total / 5.0)  # 5+ lessons = full credit
            scores.append(0.6 * capture_score + 0.4 * sentiment_score)
        else:
            missing.append("P7")

        return self._build_dimension_score(
            AssessmentDimension.OPERATIONAL_LEARNING,
            scores, available, missing,
            "Lessons learned capture and sentiment balance",
        )

    def _score_complexity_alignment(self, project_id: str) -> DimensionScore:
        """Score COMPLEXITY_ALIGNMENT from P10 (domain classifier)."""
        available: list[str] = []
        missing: list[str] = []
        scores: list[float] = []

        classifications = self._store.get_domain_classifications(project_id)
        if classifications:
            available.append("P10")
            latest = classifications[-1]
            domain = str(latest.get("domain", "COMPLICATED"))
            # Having a classification = good (self-awareness)
            # Simpler domains = higher readiness (less inherent risk)
            domain_scores = {
                "CLEAR": 1.0,
                "COMPLICATED": 0.75,
                "COMPLEX": 0.50,
                "CHAOTIC": 0.25,
            }
            scores.append(domain_scores.get(domain, 0.5))
        else:
            missing.append("P10")

        return self._build_dimension_score(
            AssessmentDimension.COMPLEXITY_ALIGNMENT,
            scores, available, missing,
            "Project complexity domain and assurance alignment",
        )

    # ------------------------------------------------------------------
    # Aggregation helpers
    # ------------------------------------------------------------------

    def _build_dimension_score(
        self,
        dimension: AssessmentDimension,
        scores: list[float],
        available: list[str],
        missing_sources: list[str],
        base_detail: str,
    ) -> DimensionScore:
        """Build a DimensionScore from sub-scores."""
        if not scores:
            return DimensionScore(
                dimension=dimension,
                score=0.0,
                status=DimensionStatus.NO_DATA,
                weight=0.0,
                weighted_score=0.0,
                sources_available=[],
                sources_missing=missing_sources,
                detail=f"{base_detail}: no data available.",
            )

        avg_score = sum(scores) / len(scores)
        status = (
            DimensionStatus.SCORED if not missing_sources
            else DimensionStatus.PARTIAL
        )
        detail = (
            f"{base_detail}: score {avg_score:.0%} "
            f"(sources: {', '.join(available)}"
            + (f"; missing: {', '.join(missing_sources)}" if missing_sources else "")
            + ")."
        )

        return DimensionScore(
            dimension=dimension,
            score=avg_score,
            status=status,
            weight=0.0,  # Set by caller
            weighted_score=0.0,  # Set by caller
            sources_available=available,
            sources_missing=missing_sources,
            detail=detail,
        )

    def _compute_composite(
        self,
        dimension_scores: dict[str, DimensionScore],
        weights: dict[AssessmentDimension, float],
    ) -> float:
        """Compute gate-weighted composite score, excluding NO_DATA dimensions."""
        total_weight = 0.0
        weighted_sum = 0.0

        for _dim_key, ds in dimension_scores.items():
            if ds.status != DimensionStatus.NO_DATA:
                total_weight += ds.weight
                weighted_sum += ds.weighted_score

        if total_weight == 0.0:
            return 0.0

        # Renormalise to account for excluded dimensions
        return weighted_sum / total_weight

    def _classify_readiness(
        self,
        composite: float,
        signals: list[GateRiskSignal],
        dimensions_scored: int,
    ) -> ReadinessLevel:
        """Classify readiness from composite score and blocking signals."""
        # Any blocking signal → NOT_READY
        if any(s.is_blocking for s in signals):
            return ReadinessLevel.NOT_READY

        # Insufficient data coverage → cap at CONDITIONALLY_READY
        if dimensions_scored < self._config.min_dimensions_for_ready:
            if composite >= self._config.conditional_threshold:
                return ReadinessLevel.CONDITIONALLY_READY
            if composite >= self._config.at_risk_threshold:
                return ReadinessLevel.AT_RISK
            return ReadinessLevel.NOT_READY

        # Score-based classification
        if composite >= self._config.ready_threshold:
            return ReadinessLevel.READY
        if composite >= self._config.conditional_threshold:
            return ReadinessLevel.CONDITIONALLY_READY
        if composite >= self._config.at_risk_threshold:
            return ReadinessLevel.AT_RISK
        return ReadinessLevel.NOT_READY

    def _generate_signals(
        self, dimension_scores: dict[str, DimensionScore]
    ) -> list[GateRiskSignal]:
        """Generate risk signals from dimension scores."""
        signals: list[GateRiskSignal] = []

        for _dim_key, ds in dimension_scores.items():
            if ds.status == DimensionStatus.NO_DATA:
                continue

            # Low score → generate signal
            if ds.score < 0.5:
                severity = 1.0 - ds.score
                signals.append(
                    GateRiskSignal(
                        dimension=ds.dimension,
                        source=", ".join(ds.sources_available),
                        signal_name=f"{DIMENSION_LABELS[ds.dimension]} below threshold",
                        severity=severity,
                        is_blocking=severity >= self._config.critical_signal_threshold,
                        detail=(
                            f"{DIMENSION_LABELS[ds.dimension]} scored {ds.score:.0%} "
                            f"(severity: {severity:.0%}). "
                            f"Sources: {', '.join(ds.sources_available)}."
                        ),
                    )
                )

        # Sort by severity descending
        signals.sort(key=lambda s: s.severity, reverse=True)
        return signals

    def _generate_actions(
        self,
        signals: list[GateRiskSignal],
        dimension_scores: dict[str, DimensionScore],
    ) -> list[str]:
        """Generate prioritised recommended actions."""
        actions: list[str] = []

        # Actions for signals (worst first)
        action_templates: dict[str, str] = {
            AssessmentDimension.ARTEFACT_READINESS.value: (
                "Close open review actions and ensure all gate artefacts "
                "are current before proceeding."
            ),
            AssessmentDimension.DATA_QUALITY.value: (
                "Investigate declining NISTA compliance scores and resolve "
                "AI extraction divergence issues."
            ),
            AssessmentDimension.ASSUMPTION_HEALTH.value: (
                "Validate stale assumptions and develop mitigation plans "
                "for assumptions with critical drift."
            ),
            AssessmentDimension.GOVERNANCE_MATURITY.value: (
                "Review override decision patterns and address ARMM maturity "
                "gaps before gate review."
            ),
            AssessmentDimension.REVIEW_TIMING.value: (
                "Address P1-P4 signals driving review urgency before "
                "scheduling the gate review."
            ),
            AssessmentDimension.ASSURANCE_EFFICIENCY.value: (
                "Review assurance activities for waste — zero-finding reviews "
                "may indicate misallocated effort."
            ),
            AssessmentDimension.OPERATIONAL_LEARNING.value: (
                "Capture lessons learned from recent project phases and "
                "address negative-sentiment patterns."
            ),
            AssessmentDimension.COMPLEXITY_ALIGNMENT.value: (
                "Ensure assurance approach is calibrated to the project's "
                "complexity domain classification."
            ),
        }

        for signal in signals:
            dim_key = signal.dimension.value
            if dim_key in action_templates:
                action = action_templates[dim_key]
                if action not in actions:
                    actions.append(action)

        # Add actions for NO_DATA dimensions
        for dim_key, ds in dimension_scores.items():
            if ds.status == DimensionStatus.NO_DATA:
                label = DIMENSION_LABELS.get(
                    AssessmentDimension(dim_key), dim_key
                )
                action = (
                    f"Run {', '.join(ds.sources_missing)} assurance checks "
                    f"to establish {label} baseline data."
                )
                if action not in actions:
                    actions.append(action)

        return actions

