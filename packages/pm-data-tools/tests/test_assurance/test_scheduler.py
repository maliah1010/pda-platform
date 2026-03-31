"""Tests for P5 — Adaptive Review Scheduler.

Covers signal extraction from P1/P2/P3/P4 outputs, composite score
calculation, urgency classification, date calculation, persistence, and
edge cases.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from pm_data_tools.assurance.currency import CurrencyScore, CurrencyStatus
from pm_data_tools.assurance.divergence import (
    DivergenceResult,
    DivergenceSignal,
    SignalType,
)
from pm_data_tools.assurance.scheduler import (
    AdaptiveReviewScheduler,
    ReviewUrgency,
    SchedulerConfig,
)
from pm_data_tools.db.store import AssuranceStore
from pm_data_tools.schemas.nista.longitudinal import (
    ThresholdBreach,
    TrendDirection,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_GATE = datetime(2026, 6, 30, tzinfo=timezone.utc)


def _make_currency(status: CurrencyStatus) -> CurrencyScore:
    """Build a CurrencyScore with the given status."""
    return CurrencyScore(
        artefact_id="doc",
        artefact_type="plan",
        last_modified=datetime(2026, 1, 1, tzinfo=timezone.utc),
        gate_date=_GATE,
        status=status,
        staleness_days=180 if status == CurrencyStatus.OUTDATED else 2,
        anomaly_window_days=3 if status == CurrencyStatus.ANOMALOUS_UPDATE else 0,
        message="test",
    )


def _make_divergence(signal_type: SignalType) -> DivergenceResult:
    """Build a DivergenceResult with the given signal type."""
    return DivergenceResult(
        project_id="PROJ-001",
        review_id="review-test",
        confidence_score=0.85,
        sample_scores=[0.85],
        signal=DivergenceSignal(
            signal_type=signal_type,
            project_id="PROJ-001",
            review_id="review-test",
            confidence_score=0.85,
            spread=0.0,
            previous_confidence=None,
            message="test",
        ),
        snapshot_id="snap-test",
    )


def _floor_breach() -> ThresholdBreach:
    return ThresholdBreach(
        breach_type="floor",
        project_id="PROJ-001",
        current_score=50.0,
        threshold_value=60.0,
        message="Below floor.",
    )


def _drop_breach() -> ThresholdBreach:
    return ThresholdBreach(
        breach_type="drop",
        project_id="PROJ-001",
        current_score=65.0,
        previous_score=75.0,
        threshold_value=5.0,
        message="Drop detected.",
    )


# ---------------------------------------------------------------------------
# No-signal baseline
# ---------------------------------------------------------------------------


def test_standard_recommendation_no_signals() -> None:
    """No inputs → STANDARD urgency with default cadence."""
    scheduler = AdaptiveReviewScheduler()
    rec = scheduler.recommend(project_id="PROJ-001")

    assert rec.urgency == ReviewUrgency.STANDARD
    assert rec.composite_score == 0.0
    assert rec.signals == []
    # Recommended date should be standard_cadence_days (42) from today
    expected = date.today() + timedelta(days=42)
    assert rec.recommended_date == expected


# ---------------------------------------------------------------------------
# Multi-signal urgency classification
# ---------------------------------------------------------------------------


def test_immediate_from_critical_signals() -> None:
    """Bad currency + degrading compliance + high divergence → IMMEDIATE."""
    scheduler = AdaptiveReviewScheduler()
    rec = scheduler.recommend(
        project_id="PROJ-001",
        currency_scores=[_make_currency(CurrencyStatus.OUTDATED)] * 2,
        trend=TrendDirection.DEGRADING,
        breaches=[_floor_breach()],  # severity → 1.0 for P2
        divergence_result=_make_divergence(SignalType.HIGH_DIVERGENCE),
    )

    assert rec.urgency == ReviewUrgency.IMMEDIATE
    assert rec.composite_score >= 0.80
    assert len(rec.signals) == 3


def test_expedited_from_moderate_signals() -> None:
    """Degrading trend + 60% open actions → EXPEDITED."""
    scheduler = AdaptiveReviewScheduler()
    rec = scheduler.recommend(
        project_id="PROJ-001",
        trend=TrendDirection.DEGRADING,
        breaches=[],
        open_actions=3,
        total_actions=5,
        recurring_actions=0,
    )

    assert rec.urgency == ReviewUrgency.EXPEDITED
    assert rec.composite_score >= 0.50
    assert len(rec.signals) == 2


def test_deferred_from_healthy_signals() -> None:
    """All-green signals → DEFERRED."""
    scheduler = AdaptiveReviewScheduler()
    rec = scheduler.recommend(
        project_id="PROJ-001",
        currency_scores=[_make_currency(CurrencyStatus.CURRENT)] * 3,
        trend=TrendDirection.IMPROVING,
        breaches=[],
        open_actions=0,
        total_actions=5,
        recurring_actions=0,
        divergence_result=_make_divergence(SignalType.STABLE),
    )

    assert rec.urgency == ReviewUrgency.DEFERRED
    assert rec.composite_score <= 0.15


# ---------------------------------------------------------------------------
# Single-signal cases (weight normalisation)
# ---------------------------------------------------------------------------


def test_single_signal_currency_only() -> None:
    """Only P1 data; weight normalises to 1.0."""
    scheduler = AdaptiveReviewScheduler()
    # 1 OUTDATED, 1 CURRENT → severity = 0.5; 0.5 >= expedited_threshold (0.50) → EXPEDITED
    rec = scheduler.recommend(
        project_id="PROJ-001",
        currency_scores=[
            _make_currency(CurrencyStatus.OUTDATED),
            _make_currency(CurrencyStatus.CURRENT),
        ],
    )

    assert len(rec.signals) == 1
    assert rec.signals[0].source == "P1"
    # Weight is P1 only, normalised to 1.0 → composite == P1 severity
    assert rec.composite_score == pytest.approx(0.50)
    assert rec.urgency == ReviewUrgency.EXPEDITED


def test_single_signal_trend_only() -> None:
    """Only P2 data; STAGNATING → severity 0.3."""
    scheduler = AdaptiveReviewScheduler()
    rec = scheduler.recommend(
        project_id="PROJ-001",
        trend=TrendDirection.STAGNATING,
        breaches=[],
    )

    assert len(rec.signals) == 1
    assert rec.signals[0].source == "P2"
    assert rec.composite_score == pytest.approx(0.30)
    assert rec.urgency == ReviewUrgency.STANDARD


def test_single_signal_actions_only() -> None:
    """Only P3 data; 3/5 open → severity 0.6 → EXPEDITED."""
    scheduler = AdaptiveReviewScheduler()
    rec = scheduler.recommend(
        project_id="PROJ-001",
        open_actions=3,
        total_actions=5,
        recurring_actions=0,
    )

    assert len(rec.signals) == 1
    assert rec.signals[0].source == "P3"
    assert rec.composite_score == pytest.approx(0.60)
    assert rec.urgency == ReviewUrgency.EXPEDITED


def test_single_signal_divergence_only() -> None:
    """Only P4 data; LOW_CONSENSUS → severity 0.6."""
    scheduler = AdaptiveReviewScheduler()
    rec = scheduler.recommend(
        project_id="PROJ-001",
        divergence_result=_make_divergence(SignalType.LOW_CONSENSUS),
    )

    assert len(rec.signals) == 1
    assert rec.signals[0].source == "P4"
    assert rec.composite_score == pytest.approx(0.60)
    assert rec.urgency == ReviewUrgency.EXPEDITED


# ---------------------------------------------------------------------------
# P2 breach overrides
# ---------------------------------------------------------------------------


def test_floor_breach_overrides_trend() -> None:
    """IMPROVING trend but floor breach → P2 severity 1.0 → IMMEDIATE."""
    scheduler = AdaptiveReviewScheduler()
    rec = scheduler.recommend(
        project_id="PROJ-001",
        trend=TrendDirection.IMPROVING,
        breaches=[_floor_breach()],
    )

    p2_signal = next(s for s in rec.signals if s.source == "P2")
    assert p2_signal.severity == pytest.approx(1.0)
    assert rec.urgency == ReviewUrgency.IMMEDIATE


def test_drop_breach_boosts_severity() -> None:
    """STAGNATING trend + drop breach → severity 0.3 + 0.3 = 0.6."""
    scheduler = AdaptiveReviewScheduler()
    rec = scheduler.recommend(
        project_id="PROJ-001",
        trend=TrendDirection.STAGNATING,
        breaches=[_drop_breach()],
    )

    p2_signal = next(s for s in rec.signals if s.source == "P2")
    assert p2_signal.severity == pytest.approx(0.6)


# ---------------------------------------------------------------------------
# P3 recurring action boost
# ---------------------------------------------------------------------------


def test_recurring_actions_boost_severity() -> None:
    """Each recurring action adds 0.1 to base severity."""
    scheduler = AdaptiveReviewScheduler()
    # 2/5 open = 0.4 base; 3 recurring → +0.3 = 0.7
    rec = scheduler.recommend(
        project_id="PROJ-001",
        open_actions=2,
        total_actions=5,
        recurring_actions=3,
    )

    p3_signal = next(s for s in rec.signals if s.source == "P3")
    assert p3_signal.severity == pytest.approx(0.70)


def test_recurring_actions_severity_capped_at_one() -> None:
    """Severity is capped at 1.0 regardless of recurring count."""
    scheduler = AdaptiveReviewScheduler()
    # 5/5 open = 1.0 base + lots of recurring → still 1.0
    rec = scheduler.recommend(
        project_id="PROJ-001",
        open_actions=5,
        total_actions=5,
        recurring_actions=10,
    )

    p3_signal = next(s for s in rec.signals if s.source == "P3")
    assert p3_signal.severity == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Custom config
# ---------------------------------------------------------------------------


def test_custom_config_thresholds() -> None:
    """Custom thresholds change urgency classification."""
    # Lower immediate_threshold so a moderate score triggers IMMEDIATE
    config = SchedulerConfig(
        immediate_threshold=0.40,
        expedited_threshold=0.20,
        deferred_threshold=0.05,
    )
    scheduler = AdaptiveReviewScheduler(config=config)
    # STAGNATING alone → severity 0.3, with only P2: composite = 0.3 >= 0.20 → EXPEDITED
    # but with our custom immediate_threshold=0.40, 0.3 < 0.40 → EXPEDITED (not IMMEDIATE)
    rec = scheduler.recommend(
        project_id="PROJ-001",
        trend=TrendDirection.STAGNATING,
        breaches=[],
    )
    assert rec.urgency == ReviewUrgency.EXPEDITED


def test_custom_source_weights() -> None:
    """Custom source weights change the composite score."""
    # Give P3 100% weight and everything else 0
    config = SchedulerConfig(
        source_weights={"P1": 0.0, "P2": 0.0, "P3": 1.0, "P4": 0.0}
    )
    scheduler = AdaptiveReviewScheduler(config=config)
    # P3: 3/5 open = 0.6; P2: DEGRADING = 0.7
    # With P3 weight = 1.0 and P2 weight = 0.0: only P3 contributes
    rec = scheduler.recommend(
        project_id="PROJ-001",
        trend=TrendDirection.DEGRADING,
        breaches=[],
        open_actions=3,
        total_actions=5,
        recurring_actions=0,
    )

    next(s for s in rec.signals if s.source == "P3")
    # composite = P3.severity * 1.0 / (0.0 + 1.0) = 0.6
    assert rec.composite_score == pytest.approx(0.60)


# ---------------------------------------------------------------------------
# Date calculation
# ---------------------------------------------------------------------------


def test_last_review_date_respected() -> None:
    """Recommended date is calculated from last_review_date, not today."""
    scheduler = AdaptiveReviewScheduler()
    last = date(2026, 1, 1)
    rec = scheduler.recommend(
        project_id="PROJ-001",
        last_review_date=last,
    )

    # STANDARD → 42 days from last_review_date
    assert rec.recommended_date == last + timedelta(days=42)


def test_no_last_review_date_defaults_to_today() -> None:
    """When last_review_date is None, calculation is from today."""
    scheduler = AdaptiveReviewScheduler()
    rec = scheduler.recommend(project_id="PROJ-001")
    expected = date.today() + timedelta(days=42)
    assert rec.recommended_date == expected


def test_recommended_date_clamped_to_max() -> None:
    """standard_cadence_days > max_days_between_reviews is clamped to max."""
    config = SchedulerConfig(
        standard_cadence_days=200,  # above default max of 90
        min_days_between_reviews=7,
        max_days_between_reviews=90,
    )
    scheduler = AdaptiveReviewScheduler(config=config)
    rec = scheduler.recommend(project_id="PROJ-001")

    # STANDARD days would be 200, clamped to 90
    assert rec.recommended_date == date.today() + timedelta(days=90)


def test_immediate_uses_min_days() -> None:
    """IMMEDIATE urgency maps to min_days_between_reviews (7 days)."""
    scheduler = AdaptiveReviewScheduler()
    rec = scheduler.recommend(
        project_id="PROJ-001",
        trend=TrendDirection.IMPROVING,
        breaches=[_floor_breach()],  # floor breach → P2 severity 1.0 → IMMEDIATE
    )
    assert rec.urgency == ReviewUrgency.IMMEDIATE
    assert rec.days_until_review <= 7 + 1  # allow for date.today() edge


# ---------------------------------------------------------------------------
# Rationale content
# ---------------------------------------------------------------------------


def test_rationale_contains_key_info() -> None:
    """Rationale mentions top signal, composite score, and urgency."""
    scheduler = AdaptiveReviewScheduler()
    rec = scheduler.recommend(
        project_id="PROJ-001",
        trend=TrendDirection.DEGRADING,
        breaches=[_floor_breach()],
    )

    assert rec.urgency.value in rec.rationale
    # Top signal name or source should appear
    assert "P2" in rec.rationale or "compliance_trend" in rec.rationale


def test_rationale_no_signals() -> None:
    """With no signals, rationale explains the default cadence."""
    rec = AdaptiveReviewScheduler().recommend(project_id="PROJ-001")
    assert "standard" in rec.rationale.lower() or "42" in rec.rationale


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def test_persistence(tmp_path: Path) -> None:
    """Recommendation is persisted and retrievable from the store."""

    store = AssuranceStore(db_path=tmp_path / "store.db")
    scheduler = AdaptiveReviewScheduler(store=store)

    scheduler.recommend(project_id="PROJ-001")

    history = store.get_schedule_history("PROJ-001")
    assert len(history) == 1
    assert history[0]["urgency"] == ReviewUrgency.STANDARD.value


def test_memory_only_mode() -> None:
    """Scheduler without a store runs in memory-only mode without error."""
    scheduler = AdaptiveReviewScheduler(store=None)
    rec = scheduler.recommend(project_id="PROJ-001")
    assert rec.urgency == ReviewUrgency.STANDARD
