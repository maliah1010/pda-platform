"""Tests for NISTA compliance score history, trend analysis, and alerting.

P2: NISTAScoreHistory
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from pm_data_tools.db.store import AssuranceStore
from pm_data_tools.schemas.nista.history import (
    ConfidenceScoreRecord,
    NISTAScoreHistory,
    NISTAThresholdConfig,
    TrendDirection,
)
from pm_data_tools.schemas.nista.validator import NISTAValidator, StrictnessLevel

from .conftest import make_record

PROJECT = "PROJ-TEST-001"


# ---------------------------------------------------------------------------
# test_first_run_creates_baseline
# ---------------------------------------------------------------------------


def test_first_run_creates_baseline(history: NISTAScoreHistory) -> None:
    """Recording the first run stores exactly one record."""
    record = make_record(project_id=PROJECT, score=75.0, run_id="baseline")
    history.record(record)

    stored = history.get_history(PROJECT)

    assert len(stored) == 1
    assert stored[0].project_id == PROJECT
    assert stored[0].run_id == "baseline"
    assert stored[0].score == 75.0


# ---------------------------------------------------------------------------
# test_improving_trend_detected
# ---------------------------------------------------------------------------


def test_improving_trend_detected(history: NISTAScoreHistory) -> None:
    """Three consecutively higher scores produce an IMPROVING trend."""
    for score, run in [(60.0, "r1"), (70.0, "r2"), (82.0, "r3")]:
        history.record(make_record(PROJECT, score, run_id=run))

    assert history.compute_trend(PROJECT) == TrendDirection.IMPROVING


# ---------------------------------------------------------------------------
# test_degrading_trend_detected
# ---------------------------------------------------------------------------


def test_degrading_trend_detected(history: NISTAScoreHistory) -> None:
    """Three consecutively lower scores produce a DEGRADING trend."""
    for score, run in [(85.0, "r1"), (75.0, "r2"), (62.0, "r3")]:
        history.record(make_record(PROJECT, score, run_id=run))

    assert history.compute_trend(PROJECT) == TrendDirection.DEGRADING


# ---------------------------------------------------------------------------
# test_stagnation_detected
# ---------------------------------------------------------------------------


def test_stagnation_detected(history: NISTAScoreHistory) -> None:
    """Scores within drop_tolerance of each other produce STAGNATING."""
    # Default drop_tolerance is 5.0; all scores within 2 points of each other.
    for score, run in [(72.0, "r1"), (73.0, "r2"), (71.5, "r3")]:
        history.record(make_record(PROJECT, score, run_id=run))

    assert history.compute_trend(PROJECT) == TrendDirection.STAGNATING


# ---------------------------------------------------------------------------
# test_threshold_breach_drop
# ---------------------------------------------------------------------------


def test_threshold_breach_drop(
    history_with_strict_thresholds: NISTAScoreHistory,
) -> None:
    """A drop exceeding drop_tolerance between two consecutive runs raises a breach."""
    hist = history_with_strict_thresholds  # tolerance=3.0
    hist.record(make_record(PROJECT, 80.0, run_id="r1"))
    hist.record(make_record(PROJECT, 72.0, run_id="r2"))  # drop of 8 > 3.0

    breaches = hist.check_thresholds(PROJECT)
    breach_types = {b.breach_type for b in breaches}

    assert "drop" in breach_types
    drop_breach = next(b for b in breaches if b.breach_type == "drop")
    assert drop_breach.previous_score == 80.0
    assert drop_breach.current_score == 72.0


# ---------------------------------------------------------------------------
# test_threshold_breach_floor
# ---------------------------------------------------------------------------


def test_threshold_breach_floor(
    history_with_strict_thresholds: NISTAScoreHistory,
) -> None:
    """A score below the floor threshold raises a floor breach."""
    hist = history_with_strict_thresholds  # floor=70.0
    hist.record(make_record(PROJECT, 65.0, run_id="r1"))

    breaches = hist.check_thresholds(PROJECT)
    breach_types = {b.breach_type for b in breaches}

    assert "floor" in breach_types
    floor_breach = next(b for b in breaches if b.breach_type == "floor")
    assert floor_breach.current_score == 65.0
    assert floor_breach.threshold_value == 70.0


# ---------------------------------------------------------------------------
# test_empty_history_handled_gracefully
# ---------------------------------------------------------------------------


def test_empty_history_handled_gracefully(history: NISTAScoreHistory) -> None:
    """An unknown project returns empty history, STAGNATING trend, no breaches."""
    stored = history.get_history("PROJ-UNKNOWN")
    trend = history.compute_trend("PROJ-UNKNOWN")
    breaches = history.check_thresholds("PROJ-UNKNOWN")

    assert stored == []
    assert trend == TrendDirection.STAGNATING
    assert breaches == []


# ---------------------------------------------------------------------------
# test_validate_signature_unchanged
# ---------------------------------------------------------------------------


def test_validate_signature_unchanged(history: NISTAScoreHistory) -> None:
    """NISTAValidator.validate() without history parameter returns ValidationResult."""
    validator = NISTAValidator(strictness=StrictnessLevel.LENIENT)
    data = {
        "project_id": "PROJ-SIG-TEST",
        "project_name": "Signature Test Project",
        "department": "CDDO",
        "category": "ICT",
        "delivery_confidence_assessment_ipa": "GREEN",
        "start_date_baseline": "2025-01-01",
        "end_date_baseline": "2026-12-31",
        "whole_life_cost_baseline": 5.0,
    }

    # Call without history — must work and return a ValidationResult
    result_no_history = validator.validate(data)
    assert result_no_history.compliant is True
    assert result_no_history.compliance_score == 100.0

    # Call with history — return type must be identical
    result_with_history = validator.validate(
        data,
        project_id="PROJ-SIG-TEST",
        history=history,
    )
    assert result_with_history.compliant is True
    assert result_with_history.compliance_score == 100.0

    # History should now have one record
    stored = history.get_history("PROJ-SIG-TEST")
    assert len(stored) == 1
    assert stored[0].score == 100.0


# ---------------------------------------------------------------------------
# Additional edge cases
# ---------------------------------------------------------------------------


def test_single_record_no_drop_breach(history: NISTAScoreHistory) -> None:
    """A single record above the floor produces no drop breach."""
    history.record(make_record(PROJECT, 80.0, run_id="only"))
    breaches = history.check_thresholds(PROJECT)
    assert all(b.breach_type != "drop" for b in breaches)


def test_score_record_invalid_range() -> None:
    """ConfidenceScoreRecord rejects scores outside 0-100."""
    with pytest.raises(Exception):
        ConfidenceScoreRecord(project_id="p", score=101.0)


def test_threshold_config_invalid_window() -> None:
    """NISTAThresholdConfig rejects stagnation_window < 2."""
    with pytest.raises(Exception):
        NISTAThresholdConfig(stagnation_window=1)


def test_threshold_config_negative_tolerance() -> None:
    """NISTAThresholdConfig rejects negative drop_tolerance."""
    with pytest.raises(Exception):
        NISTAThresholdConfig(drop_tolerance=-1.0)


def test_validate_persists_via_data_project_id(store: AssuranceStore) -> None:
    """validate() uses data['project_id'] when project_id kwarg is omitted."""
    history = NISTAScoreHistory(store=store)
    validator = NISTAValidator(strictness=StrictnessLevel.LENIENT)
    data = {
        "project_id": "AUTO-PID",
        "project_name": "Auto ID Test",
        "department": "HMRC",
        "category": "ICT",
        "delivery_confidence_assessment_ipa": "AMBER",
        "start_date_baseline": "2025-06-01",
        "end_date_baseline": "2027-01-01",
        "whole_life_cost_baseline": 1.5,
    }
    validator.validate(data, history=history)
    stored = history.get_history("AUTO-PID")
    assert len(stored) == 1
