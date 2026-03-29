"""Agentic Assurance Workflow Engine (P9).

Deterministic orchestrator for multi-step assurance sequences across P1–P8.
NOT an AI agent — all decisions are rule-based and fully reproducible.

Sequences the eight assurance capability steps for a given project with
inter-step data flow so that P5 (Adaptive Review Scheduler) automatically
consumes P1–P4 outputs produced earlier in the same execution.

Five workflow types:

- ``FULL_ASSURANCE``: all eight steps (P1–P8) in order.
- ``COMPLIANCE_FOCUS``: P2 trend, P5 schedule, P6 overrides.
- ``CURRENCY_FOCUS``: P1 currency, P5 schedule.
- ``TREND_ANALYSIS``: P2 trend, P3 actions, P5 schedule.
- ``RISK_ASSESSMENT``: P1 currency, P2 trend, P3 actions, P4 divergence, P5 schedule.

Usage::

    from pm_data_tools.assurance.workflows import (
        AssuranceWorkflowEngine,
        WorkflowType,
        WorkflowConfig,
        WorkflowResult,
    )
    from pm_data_tools.db.store import AssuranceStore

    store = AssuranceStore()
    engine = AssuranceWorkflowEngine(store=store)
    result = engine.execute(
        project_id="PROJ-001",
        workflow_type=WorkflowType.RISK_ASSESSMENT,
    )
    # result.health → ProjectHealth.HEALTHY / AT_RISK / CRITICAL …
"""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import structlog
from pydantic import BaseModel, Field

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class WorkflowStepStatus(Enum):
    """Execution status for a single workflow step.

    Attributes:
        COMPLETED: Step ran and produced output.
        SKIPPED: Step was intentionally omitted for this workflow type.
        FAILED: Step raised an exception (workflow continues — fail-safe).
        NOT_APPLICABLE: Required data was unavailable (e.g. empty store).
    """

    COMPLETED = "COMPLETED"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class WorkflowType(Enum):
    """Workflow execution plan selecting which P1–P8 steps to run.

    Attributes:
        FULL_ASSURANCE: All eight steps P1–P8.
        COMPLIANCE_FOCUS: P2, P5, P6 — emphasis on score trends and overrides.
        CURRENCY_FOCUS: P1, P5 — emphasis on artefact freshness.
        TREND_ANALYSIS: P2, P3, P5 — emphasis on trends and action closure.
        RISK_ASSESSMENT: P1–P5 — all input signals for the scheduler.
    """

    FULL_ASSURANCE = "FULL_ASSURANCE"
    COMPLIANCE_FOCUS = "COMPLIANCE_FOCUS"
    CURRENCY_FOCUS = "CURRENCY_FOCUS"
    TREND_ANALYSIS = "TREND_ANALYSIS"
    RISK_ASSESSMENT = "RISK_ASSESSMENT"
    ASSUMPTION_HEALTH_CHECK = "ASSUMPTION_HEALTH_CHECK"


class ProjectHealth(Enum):
    """Overall project health derived from workflow risk signals.

    Attributes:
        HEALTHY: No significant signals detected.
        ATTENTION_NEEDED: Minor signals — monitor closely.
        AT_RISK: Moderate signals — escalation recommended.
        CRITICAL: Severe signal(s) — immediate action required.
    """

    HEALTHY = "HEALTHY"
    ATTENTION_NEEDED = "ATTENTION_NEEDED"
    AT_RISK = "AT_RISK"
    CRITICAL = "CRITICAL"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class WorkflowRiskSignal(BaseModel):
    """A risk signal emitted by a single workflow step.

    Attributes:
        source: Feature code that produced this signal (e.g. ``"P1"``).
        signal_name: Short name for the signal (e.g. ``"outdated_artefacts"``).
        severity: Normalised severity score 0.0 (benign) – 1.0 (critical).
        detail: Human-readable explanation of this severity value.
    """

    source: str
    signal_name: str
    severity: float
    detail: str


class WorkflowStepResult(BaseModel):
    """Result of executing a single step within a workflow.

    Attributes:
        step_name: Internal step identifier (e.g. ``"p1_currency"``).
        status: Whether the step completed, was skipped, failed, or was N/A.
        duration_ms: Wall-clock time taken to execute this step in milliseconds.
        output: Structured output from the step, or ``None``.
        error_message: Exception message if the step failed, or ``None``.
        risk_signal: Risk signal emitted by this step, or ``None``.
    """

    step_name: str
    status: WorkflowStepStatus
    duration_ms: float
    output: dict[str, Any] | None = None
    error_message: str | None = None
    risk_signal: WorkflowRiskSignal | None = None


class WorkflowConfig(BaseModel):
    """Configuration for the workflow engine.

    Attributes:
        critical_severity_threshold: Any signal at or above this → CRITICAL.
        at_risk_severity_threshold: Any signal at or above this → AT_RISK
            (unless critical threshold already triggered).
        attention_severity_threshold: Any signal at or above this →
            ATTENTION_NEEDED.
        store_results: Whether to persist each workflow result to the store.
    """

    critical_severity_threshold: float = 0.80
    at_risk_severity_threshold: float = 0.50
    attention_severity_threshold: float = 0.20
    store_results: bool = True


class WorkflowResult(BaseModel):
    """Complete result of a workflow execution.

    Attributes:
        id: UUID4 identifier for this execution.
        workflow_type: Which workflow plan was executed.
        project_id: The project this workflow was run against.
        started_at: UTC timestamp when execution began.
        completed_at: UTC timestamp when execution finished.
        duration_ms: Total wall-clock time in milliseconds.
        health: Overall project health classification.
        steps: Ordered list of step results.
        aggregated_risk_signals: All non-None signals from completed steps.
        recommended_actions: Ordered list of actionable recommendations.
        executive_summary: Human-readable single-paragraph summary.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    workflow_type: WorkflowType
    project_id: str
    started_at: datetime
    completed_at: datetime
    duration_ms: float
    health: ProjectHealth
    steps: list[WorkflowStepResult]
    aggregated_risk_signals: list[WorkflowRiskSignal]
    recommended_actions: list[str]
    executive_summary: str


# ---------------------------------------------------------------------------
# Step plan
# ---------------------------------------------------------------------------

_WORKFLOW_STEPS: dict[str, list[str]] = {
    "FULL_ASSURANCE": [
        "p1_currency",
        "p2_compliance_trend",
        "p3_review_actions",
        "p4_confidence_divergence",
        "p5_schedule_recommendation",
        "p6_override_analysis",
        "p7_lessons_summary",
        "p8_overhead_analysis",
        "p11_assumption_drift",
    ],
    "ASSUMPTION_HEALTH_CHECK": [
        "p11_assumption_drift",
        "p2_compliance_trend",
        "p5_schedule_recommendation",
    ],
    "COMPLIANCE_FOCUS": [
        "p2_compliance_trend",
        "p5_schedule_recommendation",
        "p6_override_analysis",
    ],
    "CURRENCY_FOCUS": [
        "p1_currency",
        "p5_schedule_recommendation",
    ],
    "TREND_ANALYSIS": [
        "p2_compliance_trend",
        "p3_review_actions",
        "p5_schedule_recommendation",
    ],
    "RISK_ASSESSMENT": [
        "p1_currency",
        "p2_compliance_trend",
        "p3_review_actions",
        "p4_confidence_divergence",
        "p5_schedule_recommendation",
    ],
}


# ---------------------------------------------------------------------------
# Workflow engine
# ---------------------------------------------------------------------------


class AssuranceWorkflowEngine:
    """Deterministic multi-step assurance workflow orchestrator.

    Runs the appropriate subset of P1–P8 steps for the chosen
    :class:`WorkflowType`, accumulates inter-step data (P1–P4 → P5), and
    produces a :class:`WorkflowResult` with health classification, aggregated
    risk signals, recommended actions, and an executive summary.

    Individual step failures do NOT abort the workflow (fail-safe behaviour).
    Failed steps are recorded with status :attr:`~WorkflowStepStatus.FAILED`
    and execution continues with the next step.

    Example::

        engine = AssuranceWorkflowEngine(store=store)
        result = engine.execute(
            project_id="PROJ-001",
            workflow_type=WorkflowType.FULL_ASSURANCE,
        )
        print(result.health.value)     # "HEALTHY" | "AT_RISK" | …
        print(result.executive_summary)
    """

    def __init__(
        self,
        config: WorkflowConfig | None = None,
        store: object | None = None,
    ) -> None:
        """Initialise the workflow engine.

        Args:
            config: Workflow configuration.  Defaults to
                :class:`WorkflowConfig` defaults.
            store: :class:`~pm_data_tools.db.store.AssuranceStore` instance.
                Required for steps that read from persisted data (P2–P8).
                When ``None``, those steps return
                :attr:`~WorkflowStepStatus.NOT_APPLICABLE`.
        """
        self._config = config or WorkflowConfig()
        self._store = store

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def execute(
        self,
        project_id: str,
        workflow_type: WorkflowType,
        artefacts: list[dict[str, Any]] | None = None,
        gate_date: str | datetime | None = None,
    ) -> WorkflowResult:
        """Execute the workflow and return a complete result.

        Args:
            project_id: The project identifier.
            workflow_type: Which workflow plan to execute.
            artefacts: Optional list of artefact dicts for P1 (currency check).
                Each dict must have ``"name"`` and ``"last_updated"`` keys.
                When ``None``, the P1 step returns
                :attr:`~WorkflowStepStatus.NOT_APPLICABLE`.
            gate_date: Optional gate date for P1 (ISO-8601 string or
                :class:`datetime`).  Required with ``artefacts``.

        Returns:
            A :class:`WorkflowResult` with full execution details.
        """
        started_at = datetime.now(tz=timezone.utc)
        t0 = time.perf_counter()

        step_names = _WORKFLOW_STEPS.get(workflow_type.value, [])
        steps: list[WorkflowStepResult] = []
        intermediate: dict[str, Any] = {}  # inter-step data bus

        for step_name in step_names:
            step_result = self._execute_step(
                step_name=step_name,
                project_id=project_id,
                artefacts=artefacts,
                gate_date=gate_date,
                intermediate=intermediate,
            )
            steps.append(step_result)
            if step_result.output and step_result.status == WorkflowStepStatus.COMPLETED:
                intermediate[step_name] = step_result.output

        signals: list[WorkflowRiskSignal] = [
            s.risk_signal for s in steps if s.risk_signal is not None
        ]

        health = self._classify_health(signals)
        recommended_actions = self._generate_recommended_actions(health, signals)
        completed_at = datetime.now(tz=timezone.utc)
        total_ms = (time.perf_counter() - t0) * 1000

        executive_summary = self._build_executive_summary(
            project_id=project_id,
            workflow_type=workflow_type,
            health=health,
            signals=signals,
            steps=steps,
            recommended_actions=recommended_actions,
        )

        result = WorkflowResult(
            workflow_type=workflow_type,
            project_id=project_id,
            started_at=started_at,
            completed_at=completed_at,
            duration_ms=total_ms,
            health=health,
            steps=steps,
            aggregated_risk_signals=signals,
            recommended_actions=recommended_actions,
            executive_summary=executive_summary,
        )

        if self._store is not None and self._config.store_results:
            self._persist(result)

        logger.info(
            "workflow_executed",
            project_id=project_id,
            workflow_type=workflow_type.value,
            health=health.value,
            steps_total=len(steps),
            steps_completed=sum(
                1 for s in steps if s.status == WorkflowStepStatus.COMPLETED
            ),
            duration_ms=round(total_ms, 1),
        )

        return result

    def get_workflow_history(self, project_id: str) -> list[WorkflowResult]:
        """Retrieve workflow execution history for a project.

        Args:
            project_id: The project identifier.

        Returns:
            List of :class:`WorkflowResult` objects ordered by
            ``started_at`` ascending.  Returns an empty list when no
            store is configured or no history exists.
        """
        if self._store is None:
            return []

        rows = self._store.get_workflow_history(project_id)  # type: ignore[union-attr]
        results: list[WorkflowResult] = []
        for row in rows:
            raw = row.get("result_json")
            if raw:
                try:
                    data = json.loads(str(raw))
                    results.append(WorkflowResult(**data))
                except Exception as exc:
                    logger.warning(
                        "workflow_result_deserialisation_failed",
                        project_id=project_id,
                        error=str(exc),
                    )
        return results

    # ------------------------------------------------------------------
    # Step dispatcher
    # ------------------------------------------------------------------

    def _execute_step(
        self,
        step_name: str,
        project_id: str,
        artefacts: list[dict[str, Any]] | None,
        gate_date: str | datetime | None,
        intermediate: dict[str, Any],
    ) -> WorkflowStepResult:
        """Dispatch a single step by name, measuring wall-clock time.

        Exceptions are caught here so that one step failure does not abort
        the rest of the workflow.

        Args:
            step_name: Internal step identifier.
            project_id: The project identifier.
            artefacts: Optional P1 input artefacts.
            gate_date: Optional P1 gate date.
            intermediate: Shared inter-step data dict (mutated in-place by
                steps that produce data for downstream steps).

        Returns:
            A :class:`WorkflowStepResult` with timing and status.
        """
        _executor_map: dict[str, Any] = {
            "p1_currency": self._step_artefact_currency,
            "p2_compliance_trend": self._step_compliance_trend,
            "p3_review_actions": self._step_review_actions,
            "p4_confidence_divergence": self._step_confidence_divergence,
            "p5_schedule_recommendation": self._step_schedule_recommendation,
            "p6_override_analysis": self._step_override_analysis,
            "p7_lessons_summary": self._step_lessons_summary,
            "p8_overhead_analysis": self._step_overhead_analysis,
            "p11_assumption_drift": self._step_assumption_drift,
        }

        executor = _executor_map.get(step_name)
        if executor is None:
            return WorkflowStepResult(
                step_name=step_name,
                status=WorkflowStepStatus.FAILED,
                duration_ms=0.0,
                error_message=f"Unknown step: {step_name}",
            )

        t0 = time.perf_counter()
        try:
            inner = executor(
                project_id=project_id,
                artefacts=artefacts,
                gate_date=gate_date,
                intermediate=intermediate,
            )
            duration_ms = (time.perf_counter() - t0) * 1000
            return WorkflowStepResult(
                step_name=inner.step_name,
                status=inner.status,
                duration_ms=duration_ms,
                output=inner.output,
                error_message=inner.error_message,
                risk_signal=inner.risk_signal,
            )
        except Exception as exc:
            duration_ms = (time.perf_counter() - t0) * 1000
            logger.warning(
                "workflow_step_exception",
                step=step_name,
                project_id=project_id,
                error=str(exc),
            )
            return WorkflowStepResult(
                step_name=step_name,
                status=WorkflowStepStatus.FAILED,
                duration_ms=duration_ms,
                error_message=str(exc),
            )

    # ------------------------------------------------------------------
    # Step executors
    # ------------------------------------------------------------------

    def _step_artefact_currency(
        self,
        project_id: str,
        artefacts: list[dict[str, Any]] | None,
        gate_date: str | datetime | None,
        intermediate: dict[str, Any],
    ) -> WorkflowStepResult:
        """P1: Assess artefact currency against the gate date."""
        if not artefacts or gate_date is None:
            return WorkflowStepResult(
                step_name="p1_currency",
                status=WorkflowStepStatus.NOT_APPLICABLE,
                duration_ms=0.0,
                output={"reason": "No artefacts or gate_date provided."},
            )

        from datetime import datetime, timezone

        from .currency import ArtefactCurrencyValidator, CurrencyStatus

        gd = gate_date
        if isinstance(gd, str):
            gd = datetime.fromisoformat(gd)
        if gd.tzinfo is None:
            gd = gd.replace(tzinfo=timezone.utc)

        validator = ArtefactCurrencyValidator()
        scores = validator.check_batch(artefacts=artefacts, gate_date=gd)

        total = len(scores)
        outdated = sum(1 for s in scores if s.status == CurrencyStatus.OUTDATED)
        anomalous = sum(
            1 for s in scores if s.status == CurrencyStatus.ANOMALOUS_UPDATE
        )
        severity = (
            min((outdated * 1.0 + anomalous * 0.5) / total, 1.0) if total else 0.0
        )

        # Inter-step data for P5
        intermediate["currency_scores"] = scores

        return WorkflowStepResult(
            step_name="p1_currency",
            status=WorkflowStepStatus.COMPLETED,
            duration_ms=0.0,
            output={
                "total": total,
                "outdated": outdated,
                "anomalous_update": anomalous,
                "severity": severity,
            },
            risk_signal=WorkflowRiskSignal(
                source="P1",
                signal_name="outdated_artefacts",
                severity=severity,
                detail=(
                    f"{outdated} OUTDATED, {anomalous} ANOMALOUS_UPDATE "
                    f"of {total} artefact(s) (severity {severity:.2f})."
                ),
            ),
        )

    def _step_compliance_trend(
        self,
        project_id: str,
        artefacts: list[dict[str, Any]] | None,
        gate_date: str | datetime | None,
        intermediate: dict[str, Any],
    ) -> WorkflowStepResult:
        """P2: NISTA compliance trend and breach analysis."""
        if self._store is None:
            return WorkflowStepResult(
                step_name="p2_compliance_trend",
                status=WorkflowStepStatus.NOT_APPLICABLE,
                duration_ms=0.0,
                output={"reason": "No store configured."},
            )

        from ..schemas.nista.longitudinal import (
            LongitudinalComplianceTracker,
            TrendDirection,
        )

        tracker = LongitudinalComplianceTracker(store=self._store)
        records = tracker.get_history(project_id)

        if not records:
            return WorkflowStepResult(
                step_name="p2_compliance_trend",
                status=WorkflowStepStatus.NOT_APPLICABLE,
                duration_ms=0.0,
                output={"reason": "No compliance score history available."},
            )

        trend = tracker.compute_trend(project_id)
        breaches = tracker.check_thresholds(project_id)

        severity_map: dict[TrendDirection, float] = {
            TrendDirection.IMPROVING: 0.0,
            TrendDirection.STAGNATING: 0.3,
            TrendDirection.DEGRADING: 0.7,
        }
        severity = severity_map.get(trend, 0.3)
        has_floor = any(b.breach_type == "floor" for b in breaches)
        has_drop = any(b.breach_type == "drop" for b in breaches)
        if has_floor:
            severity = 1.0
        elif has_drop:
            severity = min(severity + 0.3, 1.0)

        # Inter-step data for P5
        intermediate["trend"] = trend
        intermediate["breaches"] = breaches

        return WorkflowStepResult(
            step_name="p2_compliance_trend",
            status=WorkflowStepStatus.COMPLETED,
            duration_ms=0.0,
            output={
                "trend": trend.value,
                "score_count": len(records),
                "latest_score": records[-1].score,
                "breaches": len(breaches),
                "severity": severity,
            },
            risk_signal=WorkflowRiskSignal(
                source="P2",
                signal_name="compliance_trend",
                severity=severity,
                detail=(
                    f"Trend: {trend.value}.  "
                    f"{len(breaches)} threshold breach(es).  "
                    f"Severity {severity:.2f}."
                ),
            ),
        )

    def _step_review_actions(
        self,
        project_id: str,
        artefacts: list[dict[str, Any]] | None,
        gate_date: str | datetime | None,
        intermediate: dict[str, Any],
    ) -> WorkflowStepResult:
        """P3: Review action closure rate and recurrence analysis."""
        if self._store is None:
            return WorkflowStepResult(
                step_name="p3_review_actions",
                status=WorkflowStepStatus.NOT_APPLICABLE,
                duration_ms=0.0,
                output={"reason": "No store configured."},
            )

        recs = self._store.get_recommendations(project_id)  # type: ignore[union-attr]

        if not recs:
            return WorkflowStepResult(
                step_name="p3_review_actions",
                status=WorkflowStepStatus.NOT_APPLICABLE,
                duration_ms=0.0,
                output={"reason": "No review actions found."},
            )

        total = len(recs)
        open_count = sum(1 for r in recs if r.get("status") == "OPEN")
        recurring_count = sum(
            1 for r in recs if r.get("recurrence_of") is not None
        )
        severity = min(open_count / total + recurring_count * 0.1, 1.0)

        # Inter-step data for P5
        intermediate["open_actions"] = open_count
        intermediate["total_actions"] = total
        intermediate["recurring_actions"] = recurring_count

        return WorkflowStepResult(
            step_name="p3_review_actions",
            status=WorkflowStepStatus.COMPLETED,
            duration_ms=0.0,
            output={
                "total_actions": total,
                "open_actions": open_count,
                "recurring_actions": recurring_count,
                "severity": severity,
            },
            risk_signal=WorkflowRiskSignal(
                source="P3",
                signal_name="open_review_actions",
                severity=severity,
                detail=(
                    f"{open_count}/{total} actions open, "
                    f"{recurring_count} recurring.  "
                    f"Severity {severity:.2f}."
                ),
            ),
        )

    def _step_confidence_divergence(
        self,
        project_id: str,
        artefacts: list[dict[str, Any]] | None,
        gate_date: str | datetime | None,
        intermediate: dict[str, Any],
    ) -> WorkflowStepResult:
        """P4: AI confidence divergence — latest snapshot from store."""
        if self._store is None:
            return WorkflowStepResult(
                step_name="p4_confidence_divergence",
                status=WorkflowStepStatus.NOT_APPLICABLE,
                duration_ms=0.0,
                output={"reason": "No store configured."},
            )

        history = self._store.get_divergence_history(project_id)  # type: ignore[union-attr]

        if not history:
            return WorkflowStepResult(
                step_name="p4_confidence_divergence",
                status=WorkflowStepStatus.NOT_APPLICABLE,
                duration_ms=0.0,
                output={"reason": "No divergence snapshots available."},
            )

        latest = history[-1]
        signal_type_str: str = str(latest.get("signal_type", "STABLE"))
        confidence_score: float = float(latest.get("confidence_score", 1.0))
        sample_scores: list[float] = latest.get("sample_scores", [])  # type: ignore[assignment]
        if not isinstance(sample_scores, list):
            sample_scores = []

        severity_map: dict[str, float] = {
            "STABLE": 0.0,
            "DEGRADING_CONFIDENCE": 0.5,
            "LOW_CONSENSUS": 0.6,
            "HIGH_DIVERGENCE": 0.8,
        }
        severity = severity_map.get(signal_type_str, 0.0)

        # Reconstruct DivergenceResult for P5 inter-step data flow
        try:
            from .divergence import DivergenceResult, DivergenceSignal, SignalType

            sig_enum = SignalType(signal_type_str)
            spread = (
                max(sample_scores) - min(sample_scores) if len(sample_scores) >= 2 else 0.0
            )
            divergence_signal = DivergenceSignal(
                signal_type=sig_enum,
                project_id=project_id,
                review_id=str(latest.get("review_id", "")),
                confidence_score=confidence_score,
                spread=spread,
                previous_confidence=None,
                message=f"Reconstructed from store snapshot: {signal_type_str}",
            )
            divergence_result = DivergenceResult(
                project_id=project_id,
                review_id=str(latest.get("review_id", "")),
                confidence_score=confidence_score,
                sample_scores=sample_scores,
                signal=divergence_signal,
                snapshot_id=str(latest.get("id", "")),
            )
            intermediate["divergence_result"] = divergence_result
        except Exception as exc:
            logger.warning(
                "workflow_p4_divergence_reconstruction_failed",
                error=str(exc),
            )

        return WorkflowStepResult(
            step_name="p4_confidence_divergence",
            status=WorkflowStepStatus.COMPLETED,
            duration_ms=0.0,
            output={
                "signal_type": signal_type_str,
                "confidence_score": confidence_score,
                "snapshots_count": len(history),
                "severity": severity,
            },
            risk_signal=WorkflowRiskSignal(
                source="P4",
                signal_name="confidence_divergence",
                severity=severity,
                detail=(
                    f"AI extraction divergence: {signal_type_str} "
                    f"(confidence {confidence_score:.2f}).  "
                    f"Severity {severity:.2f}."
                ),
            ),
        )

    def _step_schedule_recommendation(
        self,
        project_id: str,
        artefacts: list[dict[str, Any]] | None,
        gate_date: str | datetime | None,
        intermediate: dict[str, Any],
    ) -> WorkflowStepResult:
        """P5: Adaptive review schedule — consumes P1–P4 inter-step data."""
        from .scheduler import AdaptiveReviewScheduler

        scheduler = AdaptiveReviewScheduler(store=self._store)
        rec = scheduler.recommend(
            project_id=project_id,
            currency_scores=intermediate.get("currency_scores"),
            trend=intermediate.get("trend"),
            breaches=intermediate.get("breaches"),
            open_actions=intermediate.get("open_actions"),
            total_actions=intermediate.get("total_actions"),
            recurring_actions=intermediate.get("recurring_actions"),
            divergence_result=intermediate.get("divergence_result"),
        )

        urgency_severity: dict[str, float] = {
            "IMMEDIATE": 1.0,
            "EXPEDITED": 0.6,
            "STANDARD": 0.2,
            "DEFERRED": 0.0,
        }
        severity = urgency_severity.get(rec.urgency.value, 0.2)

        return WorkflowStepResult(
            step_name="p5_schedule_recommendation",
            status=WorkflowStepStatus.COMPLETED,
            duration_ms=0.0,
            output={
                "urgency": rec.urgency.value,
                "recommended_date": rec.recommended_date.isoformat(),
                "days_until_review": rec.days_until_review,
                "composite_score": rec.composite_score,
                "rationale": rec.rationale,
            },
            risk_signal=WorkflowRiskSignal(
                source="P5",
                signal_name="review_urgency",
                severity=severity,
                detail=(
                    f"Next review: {rec.urgency.value} on "
                    f"{rec.recommended_date.isoformat()}.  "
                    f"Composite score {rec.composite_score:.2f}.  "
                    f"Severity {severity:.2f}."
                ),
            ),
        )

    def _step_override_analysis(
        self,
        project_id: str,
        artefacts: list[dict[str, Any]] | None,
        gate_date: str | datetime | None,
        intermediate: dict[str, Any],
    ) -> WorkflowStepResult:
        """P6: Governance override pattern analysis."""
        if self._store is None:
            return WorkflowStepResult(
                step_name="p6_override_analysis",
                status=WorkflowStepStatus.NOT_APPLICABLE,
                duration_ms=0.0,
                output={"reason": "No store configured."},
            )

        from .overrides import OverrideDecisionLogger

        log_obj = OverrideDecisionLogger(store=self._store)
        summary = log_obj.analyse_patterns(project_id)

        if summary.total_overrides == 0:
            return WorkflowStepResult(
                step_name="p6_override_analysis",
                status=WorkflowStepStatus.NOT_APPLICABLE,
                duration_ms=0.0,
                output={"reason": "No override decisions recorded."},
            )

        severity = min(summary.impact_rate, 1.0)

        return WorkflowStepResult(
            step_name="p6_override_analysis",
            status=WorkflowStepStatus.COMPLETED,
            duration_ms=0.0,
            output={
                "total_overrides": summary.total_overrides,
                "impact_rate": summary.impact_rate,
                "pending_outcomes": summary.pending_outcomes,
                "message": summary.message,
            },
            risk_signal=WorkflowRiskSignal(
                source="P6",
                signal_name="override_impact_rate",
                severity=severity,
                detail=(
                    f"{summary.total_overrides} override(s), "
                    f"impact rate {summary.impact_rate:.2f}.  "
                    f"Severity {severity:.2f}."
                ),
            ),
        )

    def _step_lessons_summary(
        self,
        project_id: str,
        artefacts: list[dict[str, Any]] | None,
        gate_date: str | datetime | None,
        intermediate: dict[str, Any],
    ) -> WorkflowStepResult:
        """P7: Lessons learned sentiment distribution."""
        if self._store is None:
            return WorkflowStepResult(
                step_name="p7_lessons_summary",
                status=WorkflowStepStatus.NOT_APPLICABLE,
                duration_ms=0.0,
                output={"reason": "No store configured."},
            )

        lessons = self._store.get_lessons(project_id=project_id)  # type: ignore[union-attr]

        if not lessons:
            return WorkflowStepResult(
                step_name="p7_lessons_summary",
                status=WorkflowStepStatus.NOT_APPLICABLE,
                duration_ms=0.0,
                output={"reason": "No lessons recorded for this project."},
            )

        total = len(lessons)
        negative_count = sum(
            1 for le in lessons if le.get("sentiment") == "NEGATIVE"
        )
        negative_rate = negative_count / total
        # Lessons alone max out at 0.8 severity
        severity = min(negative_rate * 0.8, 0.8)

        return WorkflowStepResult(
            step_name="p7_lessons_summary",
            status=WorkflowStepStatus.COMPLETED,
            duration_ms=0.0,
            output={
                "total_lessons": total,
                "negative_lessons": negative_count,
                "negative_rate": negative_rate,
                "severity": severity,
            },
            risk_signal=WorkflowRiskSignal(
                source="P7",
                signal_name="lesson_sentiment",
                severity=severity,
                detail=(
                    f"{negative_count}/{total} lessons are NEGATIVE "
                    f"(rate {negative_rate:.2f}).  "
                    f"Severity {severity:.2f}."
                ),
            ),
        )

    def _step_overhead_analysis(
        self,
        project_id: str,
        artefacts: list[dict[str, Any]] | None,
        gate_date: str | datetime | None,
        intermediate: dict[str, Any],
    ) -> WorkflowStepResult:
        """P8: Assurance overhead efficiency analysis."""
        if self._store is None:
            return WorkflowStepResult(
                step_name="p8_overhead_analysis",
                status=WorkflowStepStatus.NOT_APPLICABLE,
                duration_ms=0.0,
                output={"reason": "No store configured."},
            )

        from .overhead import AssuranceOverheadOptimiser, EfficiencyRating

        opt = AssuranceOverheadOptimiser(store=self._store)
        analysis = opt.analyse(project_id)

        if analysis.total_activities == 0:
            return WorkflowStepResult(
                step_name="p8_overhead_analysis",
                status=WorkflowStepStatus.NOT_APPLICABLE,
                duration_ms=0.0,
                output={"reason": "No assurance activities recorded."},
            )

        severity_map: dict[EfficiencyRating, float] = {
            EfficiencyRating.OPTIMAL: 0.0,
            EfficiencyRating.UNDER_INVESTED: 0.5,
            EfficiencyRating.OVER_INVESTED: 0.4,
            EfficiencyRating.MISALLOCATED: 0.7,
        }
        severity = severity_map.get(analysis.efficiency_rating, 0.0)

        return WorkflowStepResult(
            step_name="p8_overhead_analysis",
            status=WorkflowStepStatus.COMPLETED,
            duration_ms=0.0,
            output={
                "total_activities": analysis.total_activities,
                "total_effort_hours": analysis.total_effort_hours,
                "efficiency_rating": analysis.efficiency_rating.value,
                "duplicate_count": analysis.duplicate_activity_count,
                "recommendations_count": len(analysis.recommendations),
            },
            risk_signal=WorkflowRiskSignal(
                source="P8",
                signal_name="assurance_efficiency",
                severity=severity,
                detail=(
                    f"Efficiency: {analysis.efficiency_rating.value}.  "
                    f"{analysis.total_effort_hours:.1f}h across "
                    f"{analysis.total_activities} activities.  "
                    f"Severity {severity:.2f}."
                ),
            ),
        )

    # ------------------------------------------------------------------
    # Health, recommendations, summary
    # ------------------------------------------------------------------

    def _classify_health(
        self,
        signals: list[WorkflowRiskSignal],
    ) -> ProjectHealth:
        """Classify overall project health from aggregated risk signals.

        Args:
            signals: All risk signals emitted by completed steps.

        Returns:
            A :class:`ProjectHealth` classification.
        """
        if not signals:
            return ProjectHealth.HEALTHY

        max_sev = max(s.severity for s in signals)
        avg_sev = sum(s.severity for s in signals) / len(signals)

        if max_sev >= self._config.critical_severity_threshold:
            return ProjectHealth.CRITICAL
        if max_sev >= self._config.at_risk_severity_threshold or avg_sev >= 0.40:
            return ProjectHealth.AT_RISK
        if max_sev >= self._config.attention_severity_threshold or avg_sev >= 0.15:
            return ProjectHealth.ATTENTION_NEEDED
        return ProjectHealth.HEALTHY

    def _generate_recommended_actions(
        self,
        health: ProjectHealth,
        signals: list[WorkflowRiskSignal],
    ) -> list[str]:
        """Generate an ordered list of recommended actions.

        Args:
            health: Overall project health classification.
            signals: All risk signals from completed steps.

        Returns:
            Deduplicated list of actionable recommendation strings, highest
            priority first.
        """
        actions: list[str] = []

        if health == ProjectHealth.CRITICAL:
            actions.append(
                "Schedule an immediate project review within 7 days."
            )
        elif health == ProjectHealth.AT_RISK:
            actions.append(
                "Escalate project status to senior stakeholders within 2 weeks."
            )

        threshold = self._config.attention_severity_threshold
        for signal in sorted(signals, key=lambda s: s.severity, reverse=True):
            if signal.severity < threshold:
                continue
            if signal.source == "P1":
                actions.append(
                    "Update stale project artefacts before the next gate review."
                )
            elif signal.source == "P2":
                actions.append(
                    "Investigate compliance score decline and agree a remediation plan."
                )
            elif signal.source == "P3":
                actions.append(
                    "Close or escalate overdue review actions before the next cycle."
                )
            elif signal.source == "P4":
                actions.append(
                    "Increase AI extraction sample size to resolve confidence divergence."
                )
            elif signal.source == "P5" and signal.severity >= 0.6:
                actions.append(
                    "Bring forward the next assurance gate review."
                )
            elif signal.source == "P6":
                actions.append(
                    "Review the pattern of governance overrides with the SRO."
                )
            elif signal.source == "P7":
                actions.append(
                    "Conduct a lessons learned workshop to address recurring negative findings."
                )
            elif signal.source == "P8":
                actions.append(
                    "Rebalance assurance activities to improve efficiency and findings yield."
                )
            elif signal.source == "P11":
                actions.append(
                    "Review and re-validate stale or drifting assumptions before the next gate review."
                )

        # Deduplicate while preserving insertion order
        seen: set[str] = set()
        unique: list[str] = []
        for action in actions:
            if action not in seen:
                seen.add(action)
                unique.append(action)
        return unique

    def _step_assumption_drift(
        self,
        project_id: str,
        artefacts: list[dict[str, Any]] | None,
        gate_date: str | datetime | None,
        intermediate: dict[str, Any],
    ) -> WorkflowStepResult:
        """P11: Assumption drift analysis."""
        if self._store is None:
            return WorkflowStepResult(
                step_name="p11_assumption_drift",
                status=WorkflowStepStatus.NOT_APPLICABLE,
                duration_ms=0.0,
                output={"reason": "No store configured."},
            )

        from .assumptions import AssumptionTracker

        tracker = AssumptionTracker(store=self._store)
        report = tracker.analyse_project(project_id)

        if report.total_assumptions == 0:
            return WorkflowStepResult(
                step_name="p11_assumption_drift",
                status=WorkflowStepStatus.NOT_APPLICABLE,
                duration_ms=0.0,
                output={"reason": "No assumptions tracked for this project."},
            )

        severity = report.overall_drift_score

        return WorkflowStepResult(
            step_name="p11_assumption_drift",
            status=WorkflowStepStatus.COMPLETED,
            duration_ms=0.0,
            output={
                "total_assumptions": report.total_assumptions,
                "stale_count": report.stale_count,
                "overall_drift_score": report.overall_drift_score,
                "by_severity": report.by_severity,
                "cascade_warnings": report.cascade_warnings,
                "message": report.message,
            },
            risk_signal=WorkflowRiskSignal(
                source="P11",
                signal_name="assumption_drift",
                severity=severity,
                detail=(
                    f"{report.total_assumptions} assumption(s), "
                    f"{report.stale_count} stale.  "
                    f"Overall drift score {severity:.2f}.  "
                    f"{len(report.cascade_warnings)} cascade warning(s)."
                ),
            ),
        )

    def _build_executive_summary(
        self,
        project_id: str,
        workflow_type: WorkflowType,
        health: ProjectHealth,
        signals: list[WorkflowRiskSignal],
        steps: list[WorkflowStepResult],
        recommended_actions: list[str],
    ) -> str:
        """Build a concise executive summary paragraph.

        Args:
            project_id: The project identifier.
            workflow_type: The workflow plan executed.
            health: Overall health classification.
            signals: All risk signals from completed steps.
            steps: All step results.
            recommended_actions: Ordered recommended actions list.

        Returns:
            A human-readable summary string.
        """
        completed = sum(
            1 for s in steps if s.status == WorkflowStepStatus.COMPLETED
        )
        total = len(steps)
        threshold = self._config.attention_severity_threshold
        active = [s for s in signals if s.severity >= threshold]

        parts: list[str] = [
            f"{workflow_type.value} workflow completed for project {project_id}.",
            f"Overall health: {health.value}.",
            f"{completed}/{total} steps completed successfully.",
        ]

        if active:
            top = max(active, key=lambda s: s.severity)
            parts.append(
                f"{len(active)} active risk signal(s).  "
                f"Highest severity: {top.source} — {top.signal_name} "
                f"({top.severity:.2f})."
            )
        else:
            parts.append("No significant risk signals detected.")

        if recommended_actions:
            parts.append(f"Priority action: {recommended_actions[0]}")

        return "  ".join(parts)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _persist(self, result: WorkflowResult) -> None:
        """Persist a workflow result to the store.

        Args:
            result: The :class:`WorkflowResult` to persist.
        """
        self._store.insert_workflow_execution(  # type: ignore[union-attr]
            workflow_id=result.id,
            project_id=result.project_id,
            workflow_type=result.workflow_type.value,
            started_at=result.started_at.isoformat(),
            completed_at=result.completed_at.isoformat(),
            duration_ms=result.duration_ms,
            health=result.health.value,
            result_json=json.dumps(result.model_dump(mode="json"), default=str),
        )
        logger.debug(
            "workflow_result_persisted",
            workflow_id=result.id,
            project_id=result.project_id,
            health=result.health.value,
        )
