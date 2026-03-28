"""Adaptive review scheduler for assurance gate management.

Analyses outputs from P1 (artefact currency), P2 (compliance trends),
P3 (review action closure), and P4 (confidence divergence) to recommend
WHEN the next project review should happen.

Fixed calendar intervals cause reviews to happen either too early (before
enough has changed) or too late (after problems have escalated).  This
scheduler uses actual project signals to recommend timing: high-risk
projects get reviewed sooner; stable projects can safely wait longer.

Usage::

    from pm_data_tools.assurance.scheduler import (
        AdaptiveReviewScheduler,
        SchedulerConfig,
        SchedulerRecommendation,
        ReviewUrgency,
    )

    scheduler = AdaptiveReviewScheduler()
    rec = scheduler.recommend(
        project_id="PROJ-001",
        trend=TrendDirection.DEGRADING,
        breaches=[],
        open_actions=4,
        total_actions=6,
        recurring_actions=1,
    )
    # rec.urgency == ReviewUrgency.EXPEDITED
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from enum import Enum
from typing import Any, Optional

import structlog
from pydantic import BaseModel, Field, field_validator

from ..assurance.currency import CurrencyScore, CurrencyStatus
from ..assurance.divergence import DivergenceResult, SignalType
from ..schemas.nista.longitudinal import ThresholdBreach, TrendDirection

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ReviewUrgency(Enum):
    """How urgently a review should be scheduled.

    Attributes:
        IMMEDIATE: Within 1 week — multiple critical signals detected.
        EXPEDITED: Within 2 weeks — at least one significant signal detected.
        STANDARD: Normal cadence (default 6-week interval).
        DEFERRED: Can safely extend beyond normal cadence (default 12 weeks).
    """

    IMMEDIATE = "IMMEDIATE"
    EXPEDITED = "EXPEDITED"
    STANDARD = "STANDARD"
    DEFERRED = "DEFERRED"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class SchedulerSignal(BaseModel):
    """A single input signal contributing to the scheduling recommendation.

    Attributes:
        source: Which feature produced this signal (e.g. ``"P1"``, ``"P4"``).
        signal_name: Specific signal (e.g. ``"outdated_artefacts"``).
        severity: 0.0 (benign) to 1.0 (critical).
        detail: Human-readable explanation of why this severity was assigned.
    """

    source: str
    signal_name: str
    severity: float
    detail: str


class SchedulerConfig(BaseModel):
    """Configuration for the adaptive review scheduler.

    Attributes:
        immediate_threshold: Weighted composite score above this
            → :attr:`ReviewUrgency.IMMEDIATE`.
        expedited_threshold: Above this → :attr:`ReviewUrgency.EXPEDITED`.
        deferred_threshold: Below this → :attr:`ReviewUrgency.DEFERRED`,
            otherwise :attr:`ReviewUrgency.STANDARD`.
        source_weights: Per-source contribution weights.  Weights are
            renormalised at scoring time so only present sources contribute.
        min_days_between_reviews: Never recommend a review sooner than this
            many days after ``last_review_date``.
        max_days_between_reviews: Never recommend waiting longer than this
            many days.
        standard_cadence_days: Default review interval for a
            :attr:`ReviewUrgency.STANDARD` recommendation.
    """

    immediate_threshold: float = 0.80
    expedited_threshold: float = 0.50
    deferred_threshold: float = 0.15
    source_weights: dict[str, float] = Field(
        default_factory=lambda: {
            "P1": 0.20,
            "P2": 0.30,
            "P3": 0.25,
            "P4": 0.25,
        }
    )
    min_days_between_reviews: int = 7
    max_days_between_reviews: int = 90
    standard_cadence_days: int = 42

    @field_validator("immediate_threshold", "expedited_threshold", "deferred_threshold")
    @classmethod
    def _between_zero_and_one(cls, v: float) -> float:
        """Validate that fractional thresholds are in [0, 1].

        Args:
            v: The value to validate.

        Returns:
            The validated value.

        Raises:
            ValueError: If value is outside [0, 1].
        """
        if not 0.0 <= v <= 1.0:
            raise ValueError("threshold must be between 0 and 1")
        return v

    @field_validator(
        "min_days_between_reviews",
        "max_days_between_reviews",
        "standard_cadence_days",
    )
    @classmethod
    def _positive(cls, v: int) -> int:
        """Validate that calendar thresholds are positive.

        Args:
            v: The value to validate.

        Returns:
            The validated value.

        Raises:
            ValueError: If value is less than 1.
        """
        if v < 1:
            raise ValueError("day thresholds must be at least 1")
        return v


class SchedulerRecommendation(BaseModel):
    """Output of the adaptive review scheduler.

    Attributes:
        project_id: The project this recommendation applies to.
        timestamp: When the recommendation was generated (UTC).
        urgency: How urgently a review should be scheduled.
        recommended_date: Suggested date for the next review.
        days_until_review: Days from today to ``recommended_date``.
        composite_score: Weighted severity score (0–1).
        signals: All contributing :class:`SchedulerSignal` objects.
        rationale: Human-readable summary of why this urgency was chosen.
    """

    project_id: str
    timestamp: datetime
    urgency: ReviewUrgency
    recommended_date: date
    days_until_review: int
    composite_score: float
    signals: list[SchedulerSignal]
    rationale: str


# ---------------------------------------------------------------------------
# Scheduler
# ---------------------------------------------------------------------------


class AdaptiveReviewScheduler:
    """Recommend optimal review timing based on project assurance signals.

    Consumes outputs from P1 (artefact currency), P2 (compliance trends),
    P3 (review action closure), and P4 (confidence divergence) to compute
    a composite risk signal.  Higher risk → sooner review.

    All signal inputs to :meth:`recommend` are optional.  The scheduler
    works with whatever data is available.

    Example::

        scheduler = AdaptiveReviewScheduler(
            config=SchedulerConfig(standard_cadence_days=30)
        )
        rec = scheduler.recommend(
            project_id="PROJ-001",
            trend=TrendDirection.DEGRADING,
            breaches=[],
        )
        # rec.urgency == ReviewUrgency.EXPEDITED
    """

    def __init__(
        self,
        config: SchedulerConfig | None = None,
        store: Optional[object] = None,
    ) -> None:
        """Initialise the scheduler.

        Args:
            config: Scheduling configuration.  Defaults to
                :class:`SchedulerConfig` defaults.
            store: :class:`~pm_data_tools.db.store.AssuranceStore` instance.
                When provided, recommendations are persisted; when ``None``,
                runs in memory-only mode.
        """
        self._config = config or SchedulerConfig()
        self._store = store

    # ------------------------------------------------------------------
    # Signal extraction
    # ------------------------------------------------------------------

    def _signal_from_currency(
        self,
        currency_scores: list[CurrencyScore],
    ) -> SchedulerSignal | None:
        """Compute a signal from P1 artefact currency results.

        Severity is proportional to the fraction of non-current artefacts,
        with OUTDATED artefacts weighted at 1.0 and ANOMALOUS_UPDATE at 0.5
        per artefact.

        Args:
            currency_scores: List of :class:`~.currency.CurrencyScore`
                objects from ``ArtefactCurrencyValidator``.

        Returns:
            A :class:`SchedulerSignal` with source ``"P1"``, or ``None`` if
            ``currency_scores`` is empty.
        """
        if not currency_scores:
            return None

        total = len(currency_scores)
        weighted_sum = sum(
            1.0 if s.status == CurrencyStatus.OUTDATED
            else 0.5 if s.status == CurrencyStatus.ANOMALOUS_UPDATE
            else 0.0
            for s in currency_scores
        )
        severity = min(weighted_sum / total, 1.0)

        outdated = sum(1 for s in currency_scores if s.status == CurrencyStatus.OUTDATED)
        anomalous = sum(
            1 for s in currency_scores if s.status == CurrencyStatus.ANOMALOUS_UPDATE
        )

        detail = (
            f"{outdated} OUTDATED and {anomalous} ANOMALOUS_UPDATE artefact(s) "
            f"out of {total} total (severity {severity:.2f})."
        )

        logger.debug(
            "scheduler_currency_signal",
            outdated=outdated,
            anomalous=anomalous,
            total=total,
            severity=severity,
        )

        return SchedulerSignal(
            source="P1",
            signal_name="outdated_artefacts",
            severity=severity,
            detail=detail,
        )

    def _signal_from_trend(
        self,
        trend: TrendDirection,
        breaches: list[ThresholdBreach],
    ) -> SchedulerSignal | None:
        """Compute a signal from P2 compliance trend and breach data.

        Severity mapping:

        - IMPROVING with no floor breaches → 0.0
        - STAGNATING → 0.3
        - DEGRADING → 0.7
        - Any floor breach → 1.0 (overrides trend severity)
        - Any drop breach → min(severity + 0.3, 1.0)

        Args:
            trend: :class:`~pm_data_tools.schemas.nista.longitudinal.TrendDirection`
                from ``LongitudinalComplianceTracker``.
            breaches: List of
                :class:`~pm_data_tools.schemas.nista.longitudinal.ThresholdBreach`
                objects from ``check_thresholds()``.

        Returns:
            A :class:`SchedulerSignal` with source ``"P2"``, or ``None`` if
            ``trend`` is ``None``.
        """
        if trend is None:
            return None

        base_severity: dict[TrendDirection, float] = {
            TrendDirection.IMPROVING: 0.0,
            TrendDirection.STAGNATING: 0.3,
            TrendDirection.DEGRADING: 0.7,
        }
        severity = base_severity.get(trend, 0.3)

        has_floor = any(b.breach_type == "floor" for b in breaches)
        has_drop = any(b.breach_type == "drop" for b in breaches)

        if has_floor:
            severity = 1.0
        elif has_drop:
            severity = min(severity + 0.3, 1.0)

        parts = [f"Compliance trend: {trend.value} (base severity {base_severity.get(trend, 0.3):.1f})"]
        if has_floor:
            parts.append("floor breach detected → severity 1.0")
        if has_drop:
            parts.append("drop breach detected → severity boosted")

        detail = ".  ".join(parts) + f".  Final severity {severity:.2f}."

        logger.debug(
            "scheduler_trend_signal",
            trend=trend.value,
            has_floor=has_floor,
            has_drop=has_drop,
            severity=severity,
        )

        return SchedulerSignal(
            source="P2",
            signal_name="compliance_trend",
            severity=severity,
            detail=detail,
        )

    def _signal_from_actions(
        self,
        open_count: int,
        total_count: int,
        recurring_count: int,
    ) -> SchedulerSignal | None:
        """Compute a signal from P3 review action closure rates.

        Severity = (open_count / total_count) + (recurring_count * 0.1),
        capped at 1.0.

        Args:
            open_count: Number of OPEN review actions.
            total_count: Total number of review actions.
            recurring_count: Number of RECURRING review actions.

        Returns:
            A :class:`SchedulerSignal` with source ``"P3"``, or ``None`` if
            ``total_count`` is 0.
        """
        if total_count == 0:
            return None

        base_severity = open_count / total_count
        severity = min(base_severity + recurring_count * 0.1, 1.0)

        detail = (
            f"{open_count}/{total_count} review actions open "
            f"({recurring_count} recurring).  Severity {severity:.2f}."
        )

        logger.debug(
            "scheduler_actions_signal",
            open_count=open_count,
            total_count=total_count,
            recurring_count=recurring_count,
            severity=severity,
        )

        return SchedulerSignal(
            source="P3",
            signal_name="open_review_actions",
            severity=severity,
            detail=detail,
        )

    def _signal_from_divergence(
        self,
        divergence_result: DivergenceResult,
    ) -> SchedulerSignal | None:
        """Compute a signal from P4 confidence divergence results.

        Severity mapping:

        - STABLE → 0.0
        - DEGRADING_CONFIDENCE → 0.5
        - LOW_CONSENSUS → 0.6
        - HIGH_DIVERGENCE → 0.8

        Args:
            divergence_result: :class:`~.divergence.DivergenceResult` from
                ``DivergenceMonitor.check()``.

        Returns:
            A :class:`SchedulerSignal` with source ``"P4"``, or ``None`` if
            ``divergence_result`` is ``None``.
        """
        if divergence_result is None:
            return None

        severity_map: dict[SignalType, float] = {
            SignalType.STABLE: 0.0,
            SignalType.DEGRADING_CONFIDENCE: 0.5,
            SignalType.LOW_CONSENSUS: 0.6,
            SignalType.HIGH_DIVERGENCE: 0.8,
        }
        signal_type = divergence_result.signal.signal_type
        severity = severity_map.get(signal_type, 0.0)

        detail = (
            f"AI extraction divergence signal: {signal_type.value} "
            f"(confidence {divergence_result.confidence_score:.2f}).  "
            f"Severity {severity:.2f}."
        )

        logger.debug(
            "scheduler_divergence_signal",
            signal_type=signal_type.value,
            severity=severity,
        )

        return SchedulerSignal(
            source="P4",
            signal_name="confidence_divergence",
            severity=severity,
            detail=detail,
        )

    # ------------------------------------------------------------------
    # Core recommendation
    # ------------------------------------------------------------------

    def recommend(
        self,
        project_id: str,
        last_review_date: date | None = None,
        currency_scores: list[CurrencyScore] | None = None,
        trend: TrendDirection | None = None,
        breaches: list[ThresholdBreach] | None = None,
        open_actions: int | None = None,
        total_actions: int | None = None,
        recurring_actions: int | None = None,
        divergence_result: DivergenceResult | None = None,
    ) -> SchedulerRecommendation:
        """Generate an adaptive review scheduling recommendation.

        All signal inputs are optional — the scheduler works with whatever
        data is available.  At minimum it will return a
        :attr:`~ReviewUrgency.STANDARD` recommendation based on calendar
        cadence alone.

        Args:
            project_id: The project identifier.
            last_review_date: Date of the most recent review.  The
                recommended date is calculated forward from this date.
                Defaults to today if not provided.
            currency_scores: P1 output — list of
                :class:`~.currency.CurrencyScore` objects.
            trend: P2 output — :class:`~pm_data_tools.schemas.nista.longitudinal.TrendDirection`.
            breaches: P2 output — list of
                :class:`~pm_data_tools.schemas.nista.longitudinal.ThresholdBreach` objects.
            open_actions: P3 output — count of OPEN review actions.
            total_actions: P3 output — total count of review actions.
            recurring_actions: P3 output — count of RECURRING review actions.
            divergence_result: P4 output —
                :class:`~.divergence.DivergenceResult` object.

        Returns:
            A :class:`SchedulerRecommendation` with urgency, recommended date,
            and rationale.
        """
        # ------------------------------------------------------------------
        # Collect signals
        # ------------------------------------------------------------------
        signals: list[SchedulerSignal] = []
        present_weights: dict[str, float] = {}

        if currency_scores is not None:
            sig = self._signal_from_currency(currency_scores)
            if sig is not None:
                signals.append(sig)
                present_weights["P1"] = self._config.source_weights.get("P1", 0.20)

        if trend is not None:
            sig = self._signal_from_trend(trend, breaches or [])
            if sig is not None:
                signals.append(sig)
                present_weights["P2"] = self._config.source_weights.get("P2", 0.30)

        if total_actions is not None:
            sig = self._signal_from_actions(
                open_actions or 0,
                total_actions,
                recurring_actions or 0,
            )
            if sig is not None:
                signals.append(sig)
                present_weights["P3"] = self._config.source_weights.get("P3", 0.25)

        if divergence_result is not None:
            sig = self._signal_from_divergence(divergence_result)
            if sig is not None:
                signals.append(sig)
                present_weights["P4"] = self._config.source_weights.get("P4", 0.25)

        # ------------------------------------------------------------------
        # Compute composite score
        # ------------------------------------------------------------------
        if not signals:
            composite_score = 0.0
            urgency = ReviewUrgency.STANDARD
        else:
            total_weight = sum(
                present_weights.get(s.source, 1.0) for s in signals
            )
            composite_score = (
                sum(
                    s.severity * present_weights.get(s.source, 1.0)
                    for s in signals
                )
                / total_weight
            )

            if composite_score >= self._config.immediate_threshold:
                urgency = ReviewUrgency.IMMEDIATE
            elif composite_score >= self._config.expedited_threshold:
                urgency = ReviewUrgency.EXPEDITED
            elif composite_score <= self._config.deferred_threshold:
                urgency = ReviewUrgency.DEFERRED
            else:
                urgency = ReviewUrgency.STANDARD

        # ------------------------------------------------------------------
        # Map urgency to days
        # ------------------------------------------------------------------
        days_map: dict[ReviewUrgency, int] = {
            ReviewUrgency.IMMEDIATE: self._config.min_days_between_reviews,
            ReviewUrgency.EXPEDITED: self._config.min_days_between_reviews * 2,
            ReviewUrgency.STANDARD: self._config.standard_cadence_days,
            ReviewUrgency.DEFERRED: self._config.max_days_between_reviews,
        }
        days = days_map[urgency]
        # Clamp to configured bounds
        days = max(
            self._config.min_days_between_reviews,
            min(days, self._config.max_days_between_reviews),
        )

        # ------------------------------------------------------------------
        # Compute recommended date
        # ------------------------------------------------------------------
        base = last_review_date or date.today()
        recommended_date = base + timedelta(days=days)
        days_until_review = (recommended_date - date.today()).days

        # ------------------------------------------------------------------
        # Build rationale
        # ------------------------------------------------------------------
        if not signals:
            rationale = (
                f"No project signals available; defaulting to standard "
                f"{self._config.standard_cadence_days}-day cadence."
            )
        else:
            top = max(signals, key=lambda s: s.severity)
            rationale = (
                f"{len(signals)} signal(s) contributed to this recommendation.  "
                f"Top signal: {top.signal_name} (source {top.source}, "
                f"severity {top.severity:.2f}).  "
                f"Composite score {composite_score:.2f} → "
                f"{urgency.value} review in {days} day(s)."
            )

        # ------------------------------------------------------------------
        # Build and persist result
        # ------------------------------------------------------------------
        timestamp = datetime.now(tz=timezone.utc)
        rec = SchedulerRecommendation(
            project_id=project_id,
            timestamp=timestamp,
            urgency=urgency,
            recommended_date=recommended_date,
            days_until_review=days_until_review,
            composite_score=composite_score,
            signals=signals,
            rationale=rationale,
        )

        if self._store is not None:
            signals_json = json.dumps(
                [
                    {
                        "source": s.source,
                        "signal_name": s.signal_name,
                        "severity": s.severity,
                        "detail": s.detail,
                    }
                    for s in signals
                ]
            )
            self._store.insert_schedule_recommendation(  # type: ignore[union-attr]
                project_id=project_id,
                timestamp=timestamp.isoformat(),
                urgency=urgency.value,
                recommended_date=recommended_date.isoformat(),
                composite_score=composite_score,
                signals_json=signals_json,
                rationale=rationale,
            )

        logger.info(
            "review_schedule_recommended",
            project_id=project_id,
            urgency=urgency.value,
            composite_score=composite_score,
            days=days,
            recommended_date=recommended_date.isoformat(),
        )

        return rec
