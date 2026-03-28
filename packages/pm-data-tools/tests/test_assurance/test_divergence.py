"""Tests for P4 — Confidence Divergence Monitor.

Covers classification logic, degradation detection, persistence, edge cases,
and message content for each SignalType branch.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pm_data_tools.assurance.divergence import (
    DivergenceConfig,
    DivergenceMonitor,
    DivergenceResult,
    SignalType,
)
from pm_data_tools.db.store import AssuranceStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _monitor(
    *,
    divergence_threshold: float = 0.20,
    min_consensus: float = 0.60,
    degradation_window: int = 3,
    store: AssuranceStore | None = None,
) -> DivergenceMonitor:
    config = DivergenceConfig(
        divergence_threshold=divergence_threshold,
        min_consensus=min_consensus,
        degradation_window=degradation_window,
    )
    return DivergenceMonitor(config=config, store=store)


def _check(
    confidence_score: float,
    sample_scores: list[float],
    *,
    monitor: DivergenceMonitor | None = None,
    project_id: str = "PROJ-001",
    review_id: str = "review-q1",
) -> DivergenceResult:
    m = monitor or _monitor()
    return m.check(
        project_id=project_id,
        review_id=review_id,
        confidence_score=confidence_score,
        sample_scores=sample_scores,
    )


# ---------------------------------------------------------------------------
# Signal classification
# ---------------------------------------------------------------------------


def test_stable_result() -> None:
    """Scores within all bounds produce STABLE signal."""
    result = _check(0.85, [0.80, 0.85, 0.90])
    assert result.signal.signal_type == SignalType.STABLE
    assert result.confidence_score == 0.85


def test_high_divergence() -> None:
    """Spread above divergence_threshold produces HIGH_DIVERGENCE."""
    # spread = 0.90 - 0.30 = 0.60, threshold default = 0.20
    result = _check(0.55, [0.90, 0.30, 0.55, 0.60, 0.50])
    assert result.signal.signal_type == SignalType.HIGH_DIVERGENCE
    assert result.signal.spread > 0.20


def test_low_consensus() -> None:
    """Consensus below min_consensus produces LOW_CONSENSUS."""
    # spread within threshold (all close), but score below 0.60
    result = _check(0.50, [0.48, 0.50, 0.52])
    assert result.signal.signal_type == SignalType.LOW_CONSENSUS


def test_high_divergence_takes_precedence_over_low_consensus(
    tmp_path: Path,
) -> None:
    """HIGH_DIVERGENCE is classified before LOW_CONSENSUS when both apply."""
    # score below min AND spread above threshold
    result = _check(0.40, [0.80, 0.10])
    assert result.signal.signal_type == SignalType.HIGH_DIVERGENCE


def test_degrading_confidence(tmp_path: Path) -> None:
    """Consecutive falling scores in history produce DEGRADING_CONFIDENCE."""
    store = AssuranceStore(db_path=tmp_path / "store.db")
    mon = _monitor(degradation_window=3, store=store)

    # Seed three declining snapshots directly into the store
    for score, ts in [(0.85, "2026-01-01T00:00:00"), (0.75, "2026-02-01T00:00:00"), (0.65, "2026-03-01T00:00:00")]:
        store.insert_divergence_snapshot(
            snapshot_id=f"seed-{score}",
            project_id="PROJ-001",
            review_id=f"review-seed-{score}",
            confidence_score=score,
            sample_scores=[score],
            signal_type="STABLE",
            timestamp=ts,
        )

    # Now a check with another high score — the degradation is in history
    result = mon.check(
        project_id="PROJ-001",
        review_id="review-current",
        confidence_score=0.80,
        sample_scores=[0.80, 0.80],
    )
    assert result.signal.signal_type == SignalType.DEGRADING_CONFIDENCE


def test_degradation_insufficient_history(tmp_path: Path) -> None:
    """Fewer snapshots than degradation_window does not trigger degradation."""
    store = AssuranceStore(db_path=tmp_path / "store.db")
    mon = _monitor(degradation_window=3, store=store)

    # Only one prior snapshot — not enough history
    store.insert_divergence_snapshot(
        snapshot_id="seed-1",
        project_id="PROJ-001",
        review_id="review-seed",
        confidence_score=0.80,
        sample_scores=[0.80],
        signal_type="STABLE",
        timestamp="2026-01-01T00:00:00",
    )

    result = mon.check(
        project_id="PROJ-001",
        review_id="review-current",
        confidence_score=0.75,
        sample_scores=[0.75],
    )
    assert result.signal.signal_type != SignalType.DEGRADING_CONFIDENCE


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def test_snapshot_persisted(tmp_path: Path) -> None:
    """check() saves a snapshot to the store."""
    store = AssuranceStore(db_path=tmp_path / "store.db")
    mon = _monitor(store=store)

    _check(0.85, [0.85], monitor=mon)

    history = store.get_divergence_history("PROJ-001")
    assert len(history) == 1
    assert history[0]["review_id"] == "review-q1"
    assert history[0]["confidence_score"] == pytest.approx(0.85)


def test_snapshot_not_persisted_without_store() -> None:
    """check() in memory-only mode does not raise and returns a result."""
    mon = _monitor(store=None)
    result = _check(0.85, [0.85], monitor=mon)
    assert result.snapshot_id  # UUID was still generated


def test_get_history_empty(tmp_path: Path) -> None:
    """get_divergence_history returns [] when no snapshots exist."""
    store = AssuranceStore(db_path=tmp_path / "store.db")
    assert store.get_divergence_history("PROJ-EMPTY") == []


def test_get_history_multiple_ordered(tmp_path: Path) -> None:
    """get_divergence_history returns snapshots ordered by timestamp ASC."""
    store = AssuranceStore(db_path=tmp_path / "store.db")
    mon = _monitor(store=store)

    for i, ts in enumerate(["2026-01-01T00:00:00", "2026-02-01T00:00:00"]):
        store.insert_divergence_snapshot(
            snapshot_id=f"snap-{i}",
            project_id="PROJ-001",
            review_id=f"review-{i}",
            confidence_score=0.80,
            sample_scores=[0.80],
            signal_type="STABLE",
            timestamp=ts,
        )

    history = store.get_divergence_history("PROJ-001")
    assert len(history) == 2
    assert history[0]["review_id"] == "review-0"
    assert history[1]["review_id"] == "review-1"


def test_sample_scores_round_tripped(tmp_path: Path) -> None:
    """Sample scores are deserialised correctly from the store."""
    store = AssuranceStore(db_path=tmp_path / "store.db")
    mon = _monitor(store=store)

    original = [0.70, 0.80, 0.90]
    _check(0.80, original, monitor=mon)

    history = store.get_divergence_history("PROJ-001")
    assert history[0]["sample_scores"] == original


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


def test_single_sample_score() -> None:
    """A single sample score produces a spread of 0.0."""
    result = _check(0.85, [0.85])
    assert result.signal.spread == 0.0
    assert result.signal.signal_type == SignalType.STABLE


def test_empty_sample_scores() -> None:
    """Empty sample_scores list is handled gracefully."""
    result = _check(0.85, [])
    assert result.signal.spread == 0.0


def test_confidence_score_boundary_at_min() -> None:
    """Score exactly equal to min_consensus is not LOW_CONSENSUS."""
    # min_consensus default = 0.60; spread within threshold
    result = _check(0.60, [0.58, 0.60, 0.62])
    # spread = 0.04, below 0.20 threshold; score == min so not below
    assert result.signal.signal_type == SignalType.STABLE


# ---------------------------------------------------------------------------
# Message content
# ---------------------------------------------------------------------------


def test_message_content_stable() -> None:
    """STABLE message contains the project and review IDs."""
    result = _check(0.85, [0.84, 0.85, 0.86])
    assert "PROJ-001" in result.signal.message
    assert SignalType.STABLE.value in result.signal.message


def test_message_content_high_divergence() -> None:
    """HIGH_DIVERGENCE message mentions the spread and threshold."""
    result = _check(0.55, [0.90, 0.30])
    assert SignalType.HIGH_DIVERGENCE.value in result.signal.message
    assert "0.20" in result.signal.message


# ---------------------------------------------------------------------------
# Custom config
# ---------------------------------------------------------------------------


def test_custom_divergence_threshold() -> None:
    """Custom divergence_threshold is respected."""
    # spread = 0.90 - 0.80 = 0.10; with threshold 0.05, this is HIGH_DIVERGENCE
    mon = _monitor(divergence_threshold=0.05)
    result = _check(0.85, [0.80, 0.90], monitor=mon)
    assert result.signal.signal_type == SignalType.HIGH_DIVERGENCE


def test_custom_min_consensus() -> None:
    """Custom min_consensus is respected."""
    # score 0.75 with min 0.80 → LOW_CONSENSUS
    mon = _monitor(min_consensus=0.80)
    result = _check(0.75, [0.73, 0.75, 0.77], monitor=mon)
    assert result.signal.signal_type == SignalType.LOW_CONSENSUS


# ---------------------------------------------------------------------------
# Config validation
# ---------------------------------------------------------------------------


def test_config_rejects_threshold_above_one() -> None:
    """DivergenceConfig raises ValueError when divergence_threshold > 1."""
    with pytest.raises(ValueError):
        DivergenceConfig(divergence_threshold=1.5)


def test_config_rejects_negative_degradation_window() -> None:
    """DivergenceConfig raises ValueError when degradation_window < 1."""
    with pytest.raises(ValueError):
        DivergenceConfig(degradation_window=0)
