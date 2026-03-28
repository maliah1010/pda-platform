"""Tests for P1 — Artefact Currency Validator.

Covers classification logic, batch processing, edge cases, and
the human-readable message content for each status branch.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from pm_data_tools.assurance.currency import (
    ArtefactCurrencyValidator,
    CurrencyConfig,
    CurrencyScore,
    CurrencyStatus,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

GATE = datetime(2026, 6, 30, tzinfo=timezone.utc)


def _validator(max_staleness: int = 90, anomaly_window: int = 3) -> ArtefactCurrencyValidator:
    return ArtefactCurrencyValidator(
        config=CurrencyConfig(
            max_staleness_days=max_staleness,
            anomaly_window_days=anomaly_window,
        )
    )


def _check(
    last_modified: datetime,
    *,
    max_staleness: int = 90,
    anomaly_window: int = 3,
) -> CurrencyScore:
    return _validator(max_staleness, anomaly_window).check_artefact_currency(
        artefact_id="test-doc",
        artefact_type="risk_register",
        last_modified=last_modified,
        gate_date=GATE,
    )


# ---------------------------------------------------------------------------
# Single-artefact checks
# ---------------------------------------------------------------------------


def test_current_artefact() -> None:
    """Artefact updated 30 days before gate is CURRENT."""
    last_modified = datetime(2026, 5, 31, tzinfo=timezone.utc)  # 30 days before
    score = _check(last_modified)
    assert score.status == CurrencyStatus.CURRENT
    assert score.staleness_days == 30
    assert score.anomaly_window_days == 0


def test_outdated_artefact() -> None:
    """Artefact not updated within the staleness window is OUTDATED."""
    last_modified = datetime(2026, 3, 1, tzinfo=timezone.utc)  # 121 days before
    score = _check(last_modified)
    assert score.status == CurrencyStatus.OUTDATED
    assert score.staleness_days == 121
    assert score.anomaly_window_days == 0


def test_anomalous_update() -> None:
    """Artefact updated 2 days before gate is ANOMALOUS_UPDATE."""
    last_modified = datetime(2026, 6, 28, tzinfo=timezone.utc)  # 2 days before
    score = _check(last_modified)
    assert score.status == CurrencyStatus.ANOMALOUS_UPDATE
    assert score.staleness_days == 2
    assert score.anomaly_window_days == 3


def test_same_day_update_is_anomalous() -> None:
    """Artefact updated on the gate date itself (0 days) is ANOMALOUS_UPDATE."""
    score = _check(GATE)
    assert score.status == CurrencyStatus.ANOMALOUS_UPDATE
    assert score.staleness_days == 0


def test_future_dated_is_anomalous() -> None:
    """last_modified after gate_date (negative staleness) is ANOMALOUS_UPDATE."""
    last_modified = datetime(2026, 7, 1, tzinfo=timezone.utc)  # 1 day after gate
    score = _check(last_modified)
    assert score.status == CurrencyStatus.ANOMALOUS_UPDATE
    assert score.staleness_days == -1


# ---------------------------------------------------------------------------
# Custom config
# ---------------------------------------------------------------------------


def test_custom_config_staleness() -> None:
    """Custom max_staleness_days is respected."""
    last_modified = datetime(2026, 5, 31, tzinfo=timezone.utc)  # 30 days before
    # With a 20-day window, 30 days is OUTDATED
    score = _check(last_modified, max_staleness=20, anomaly_window=3)
    assert score.status == CurrencyStatus.OUTDATED


def test_custom_config_anomaly_window() -> None:
    """Custom anomaly_window_days is respected."""
    last_modified = datetime(2026, 6, 20, tzinfo=timezone.utc)  # 10 days before
    # With a 14-day anomaly window, 10 days before is ANOMALOUS_UPDATE
    score = _check(last_modified, max_staleness=90, anomaly_window=14)
    assert score.status == CurrencyStatus.ANOMALOUS_UPDATE
    assert score.anomaly_window_days == 14


# ---------------------------------------------------------------------------
# Staleness calculation
# ---------------------------------------------------------------------------


def test_staleness_days_calculation() -> None:
    """staleness_days equals the integer difference gate_date - last_modified."""
    last_modified = datetime(2026, 4, 1, tzinfo=timezone.utc)
    score = _check(last_modified)
    expected = (GATE - last_modified).days
    assert score.staleness_days == expected


# ---------------------------------------------------------------------------
# Message content
# ---------------------------------------------------------------------------


def test_message_content_current() -> None:
    """CURRENT message contains artefact ID and type."""
    last_modified = datetime(2026, 5, 1, tzinfo=timezone.utc)
    score = _check(last_modified)
    assert "test-doc" in score.message
    assert "risk_register" in score.message
    assert CurrencyStatus.CURRENT.value in score.message


def test_message_content_outdated() -> None:
    """OUTDATED message mentions the threshold."""
    last_modified = datetime(2026, 1, 1, tzinfo=timezone.utc)
    score = _check(last_modified)
    assert CurrencyStatus.OUTDATED.value in score.message
    assert "90" in score.message  # default max_staleness_days


def test_message_content_anomalous() -> None:
    """ANOMALOUS_UPDATE message mentions the anomaly window."""
    last_modified = datetime(2026, 6, 28, tzinfo=timezone.utc)
    score = _check(last_modified)
    assert CurrencyStatus.ANOMALOUS_UPDATE.value in score.message
    assert "3" in score.message  # default anomaly_window_days


# ---------------------------------------------------------------------------
# Batch processing
# ---------------------------------------------------------------------------


def test_batch_check() -> None:
    """check_batch returns one CurrencyScore per artefact in input order."""
    validator = _validator()
    artefacts = [
        {
            "id": "doc-a",
            "type": "plan",
            "last_modified": datetime(2026, 5, 1, tzinfo=timezone.utc),
        },
        {
            "id": "doc-b",
            "type": "risk_register",
            "last_modified": datetime(2026, 1, 1, tzinfo=timezone.utc),
        },
        {
            "id": "doc-c",
            "type": "business_case",
            "last_modified": datetime(2026, 6, 29, tzinfo=timezone.utc),
        },
    ]
    results = validator.check_batch(artefacts=artefacts, gate_date=GATE)

    assert len(results) == 3
    assert results[0].artefact_id == "doc-a"
    assert results[0].status == CurrencyStatus.CURRENT
    assert results[1].artefact_id == "doc-b"
    assert results[1].status == CurrencyStatus.OUTDATED
    assert results[2].artefact_id == "doc-c"
    assert results[2].status == CurrencyStatus.ANOMALOUS_UPDATE


def test_batch_empty_list() -> None:
    """check_batch with an empty list returns an empty list."""
    validator = _validator()
    results = validator.check_batch(artefacts=[], gate_date=GATE)
    assert results == []


def test_batch_iso_string_last_modified() -> None:
    """check_batch accepts ISO-8601 strings for last_modified."""
    validator = _validator()
    artefacts = [
        {
            "id": "doc-iso",
            "type": "plan",
            "last_modified": "2026-05-01T00:00:00",  # naive ISO string → UTC
        },
    ]
    results = validator.check_batch(artefacts=artefacts, gate_date=GATE)
    assert len(results) == 1
    assert results[0].status == CurrencyStatus.CURRENT


# ---------------------------------------------------------------------------
# Config validation
# ---------------------------------------------------------------------------


def test_config_rejects_zero_staleness() -> None:
    """CurrencyConfig raises ValueError when max_staleness_days < 1."""
    with pytest.raises(ValueError):
        CurrencyConfig(max_staleness_days=0)


def test_config_rejects_zero_anomaly_window() -> None:
    """CurrencyConfig raises ValueError when anomaly_window_days < 1."""
    with pytest.raises(ValueError):
        CurrencyConfig(anomaly_window_days=0)
