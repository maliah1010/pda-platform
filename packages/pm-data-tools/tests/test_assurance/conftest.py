"""Shared fixtures for assurance module tests.

Provides in-memory SQLite stores, mock ConfidenceExtractor instances, and
sample review text for P2 (NISTA history) and P3 (recommendation tracker)
tests.
"""

from __future__ import annotations

import json
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from agent_planning.confidence.models import ConfidenceResult, ReviewLevel

from pm_data_tools.db.store import AssuranceStore
from pm_data_tools.schemas.nista.history import (
    ConfidenceScoreRecord,
    NISTAScoreHistory,
    NISTAThresholdConfig,
)


# ---------------------------------------------------------------------------
# SQLite store (temp file per test)
# ---------------------------------------------------------------------------


@pytest.fixture()
def tmp_db_path(tmp_path: Path) -> Path:
    """A temporary SQLite database path."""
    return tmp_path / "test_store.db"


@pytest.fixture()
def store(tmp_db_path: Path) -> AssuranceStore:
    """An isolated AssuranceStore backed by a temp file."""
    return AssuranceStore(db_path=tmp_db_path)


# ---------------------------------------------------------------------------
# NISTA history fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def history(store: AssuranceStore) -> NISTAScoreHistory:
    """NISTAScoreHistory backed by the isolated temp store."""
    return NISTAScoreHistory(store=store)


@pytest.fixture()
def history_with_strict_thresholds(store: AssuranceStore) -> NISTAScoreHistory:
    """NISTAScoreHistory with tight thresholds for breach testing."""
    thresholds = NISTAThresholdConfig(drop_tolerance=3.0, floor=70.0, stagnation_window=2)
    return NISTAScoreHistory(store=store, thresholds=thresholds)


def make_record(
    project_id: str,
    score: float,
    run_id: str | None = None,
    ts: str | None = None,
) -> ConfidenceScoreRecord:
    """Helper to build a ConfidenceScoreRecord with sensible defaults."""
    return ConfidenceScoreRecord(
        project_id=project_id,
        run_id=run_id or f"run-{score}",
        timestamp=datetime.fromisoformat(ts) if ts else datetime.now(tz=timezone.utc),
        score=score,
    )


# ---------------------------------------------------------------------------
# ConfidenceExtractor mock
# ---------------------------------------------------------------------------


def make_confidence_result(
    items: list[dict[str, Any]],
    confidence: float = 0.85,
    review_level: ReviewLevel = ReviewLevel.NONE,
    cost_usd: float = 0.002,
) -> ConfidenceResult:
    """Build a ConfidenceResult with the given extracted items."""
    return ConfidenceResult(
        query="test",
        consensus={"items": items},
        confidence=confidence,
        field_confidence={},
        outliers=[],
        raw_responses=[],
        samples_used=5,
        samples_requested=5,
        early_stopped=False,
        cost_usd=cost_usd,
        cost_saved_usd=0.0,
        tokens_used=500,
        latency_ms=200,
        review_level=review_level,
        review_reason=None,
    )


@pytest.fixture()
def mock_confidence_extractor() -> MagicMock:
    """A mock ConfidenceExtractor with a configurable extract() return value."""
    mock = MagicMock()
    mock.extract = AsyncMock(
        return_value=make_confidence_result(
            items=[
                {
                    "action": "Implement automated testing pipeline",
                    "rationale": "Reduce manual QA overhead",
                    "priority": "High",
                    "owner": "Tech Lead",
                }
            ]
        )
    )
    return mock


@pytest.fixture()
def mock_extractor_low_confidence() -> MagicMock:
    """Mock extractor returning a low-confidence result."""
    mock = MagicMock()
    mock.extract = AsyncMock(
        return_value=make_confidence_result(
            items=[
                {
                    "action": "Review governance framework",
                    "rationale": "Unclear alignment",
                    "priority": "Medium",
                }
            ],
            confidence=0.45,
            review_level=ReviewLevel.DETAILED_REVIEW,
        )
    )
    return mock


# ---------------------------------------------------------------------------
# Sample review text
# ---------------------------------------------------------------------------


@pytest.fixture()
def sample_review_text() -> str:
    """Realistic project review excerpt with clear recommendations."""
    return """
    Project Delivery Review — Q1 2026

    The review panel identified the following recommendations:

    1. Implement automated regression testing to reduce the current 40% manual
       QA overhead. Owner: Technical Lead. Priority: High.

    2. Establish a weekly steering group with senior stakeholders to improve
       decision turnaround time from 3 weeks to 5 days. Priority: High.

    3. Update the benefits realisation framework to align with the revised
       Green Book guidance. Owner: PMO. Priority: Medium.
    """
