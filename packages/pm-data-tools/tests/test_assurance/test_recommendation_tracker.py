"""Tests for P3: Assurance Recommendation Tracker.

Covers RecommendationExtractor, RecurrenceDetector, and persistence via the
shared SQLite store.  All ConfidenceExtractor calls are mocked.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pm_data_tools.assurance import (
    Recommendation,
    RecommendationExtractionResult,
    RecommendationExtractor,
    RecommendationStatus,
    RecurrenceDetector,
)
from pm_data_tools.assurance.recurrence import SENTENCE_TRANSFORMERS_AVAILABLE
from pm_data_tools.db.store import AssuranceStore

from .conftest import make_confidence_result

PROJECT = "PROJ-P3-001"


# ---------------------------------------------------------------------------
# test_extraction_from_sample_review_text
# ---------------------------------------------------------------------------


async def test_extraction_from_sample_review_text(
    mock_confidence_extractor: MagicMock,
    store: AssuranceStore,
    sample_review_text: str,
) -> None:
    """Extraction returns populated RecommendationExtractionResult."""
    extractor = RecommendationExtractor(
        extractor=mock_confidence_extractor,
        store=store,
    )

    result = await extractor.extract(
        review_text=sample_review_text,
        review_id="review-q1-2026",
        project_id=PROJECT,
    )

    assert isinstance(result, RecommendationExtractionResult)
    assert len(result.recommendations) >= 1
    assert result.extraction_confidence > 0.0
    assert result.review_level is not None

    rec = result.recommendations[0]
    assert isinstance(rec, Recommendation)
    assert rec.text
    assert rec.source_review_id == "review-q1-2026"
    assert rec.status == RecommendationStatus.OPEN


# ---------------------------------------------------------------------------
# test_low_confidence_flagged_not_rejected
# ---------------------------------------------------------------------------


async def test_low_confidence_flagged_not_rejected(
    mock_extractor_low_confidence: MagicMock,
    store: AssuranceStore,
) -> None:
    """Low-confidence extractions are flagged but still returned."""
    extractor = RecommendationExtractor(
        extractor=mock_extractor_low_confidence,
        store=store,
        min_confidence=0.60,
    )

    result = await extractor.extract(
        review_text="Review governance framework alignment.",
        review_id="review-low",
        project_id=PROJECT,
    )

    assert len(result.recommendations) >= 1
    flagged = [r for r in result.recommendations if r.flagged_for_review]
    assert len(flagged) >= 1
    # Flagged items retain OPEN status — not rejected
    assert all(r.status == RecommendationStatus.OPEN for r in flagged)


# ---------------------------------------------------------------------------
# test_deduplication_within_single_review
# ---------------------------------------------------------------------------


async def test_deduplication_within_single_review(
    store: AssuranceStore,
) -> None:
    """Duplicate actions within one review are deduplicated."""
    duplicate_text = "Implement automated testing pipeline"
    mock = MagicMock()
    mock.extract = AsyncMock(
        return_value=make_confidence_result(
            items=[
                {"action": duplicate_text, "priority": "High"},
                {"action": duplicate_text, "priority": "High"},  # exact duplicate
                {"action": duplicate_text.upper(), "priority": "Medium"},  # case dup
            ]
        )
    )

    extractor = RecommendationExtractor(extractor=mock, store=store)
    result = await extractor.extract(
        review_text="...",
        review_id="review-dedup",
        project_id=PROJECT,
    )

    texts = [r.text for r in result.recommendations]
    assert len(texts) == len(set(t.lower() for t in texts))
    assert len(result.recommendations) == 1


# ---------------------------------------------------------------------------
# test_recurrence_detected_across_review_cycles
# ---------------------------------------------------------------------------


async def test_recurrence_detected_across_review_cycles(
    store: AssuranceStore,
) -> None:
    """A recommendation matching a prior OPEN rec is marked RECURRING."""
    prior_rec_id = "prior-rec-001"
    review_text = "Implement automated regression testing."

    # Pre-seed a prior OPEN recommendation
    store.upsert_recommendation(
        {
            "id": prior_rec_id,
            "project_id": PROJECT,
            "text": review_text,
            "category": "High",
            "source_review_id": "review-q4-2025",
            "review_date": "2025-12-15",
            "status": "OPEN",
            "owner": None,
            "recurrence_of": None,
            "confidence": 0.9,
            "created_at": datetime.now(tz=timezone.utc).isoformat(),
        }
    )

    # Mock extractor returns the same text in the new review
    mock = MagicMock()
    mock.extract = AsyncMock(
        return_value=make_confidence_result(
            items=[{"action": review_text, "priority": "High"}]
        )
    )

    # Build a mock recurrence detector that always flags the first new rec
    mock_detector = MagicMock(spec=RecurrenceDetector)

    def _fake_detect(
        new_recommendations: list[Recommendation],
        prior_recommendations: list[Recommendation],
    ) -> list[Recommendation]:
        updated = []
        for rec in new_recommendations:
            if prior_recommendations:
                rec = rec.model_copy(
                    update={
                        "status": RecommendationStatus.RECURRING,
                        "recurrence_of": prior_recommendations[0].id,
                    }
                )
            updated.append(rec)
        return updated

    mock_detector.detect_recurrences = _fake_detect

    extractor = RecommendationExtractor(
        extractor=mock,
        store=store,
        recurrence_detector=mock_detector,
    )
    result = await extractor.extract(
        review_text=review_text,
        review_id="review-q1-2026",
        project_id=PROJECT,
    )

    recurring = [r for r in result.recommendations if r.status == RecommendationStatus.RECURRING]
    assert len(recurring) >= 1
    assert recurring[0].recurrence_of == prior_rec_id


# ---------------------------------------------------------------------------
# test_recurrence_skipped_gracefully_without_sentence_transformers
# ---------------------------------------------------------------------------


async def test_recurrence_skipped_gracefully_without_sentence_transformers(
    store: AssuranceStore,
) -> None:
    """RecurrenceDetector skips detection and logs a warning when library absent."""
    prior = [
        Recommendation(
            id="prior-001",
            text="Establish testing pipeline",
            category="High",
            source_review_id="review-old",
            review_date=date(2025, 9, 1),
            confidence=0.9,
        )
    ]
    new = [
        Recommendation(
            id="new-001",
            text="Establish testing pipeline",
            category="High",
            source_review_id="review-new",
            review_date=date(2026, 1, 1),
            confidence=0.88,
        )
    ]

    detector = RecurrenceDetector()

    with patch(
        "pm_data_tools.assurance.recurrence.SENTENCE_TRANSFORMERS_AVAILABLE",
        False,
    ):
        result = detector.detect_recurrences(
            new_recommendations=new,
            prior_recommendations=prior,
        )

    # Recommendations returned unchanged (not RECURRING)
    assert result[0].status == RecommendationStatus.OPEN
    assert result[0].recurrence_of is None


# ---------------------------------------------------------------------------
# test_status_update_open_to_closed
# ---------------------------------------------------------------------------


def test_status_update_open_to_closed(store: AssuranceStore) -> None:
    """A recommendation status can be updated from OPEN to CLOSED."""
    rec_id = "update-test-001"
    store.upsert_recommendation(
        {
            "id": rec_id,
            "project_id": PROJECT,
            "text": "Complete data migration",
            "category": "High",
            "source_review_id": "review-x",
            "review_date": "2026-01-15",
            "status": "OPEN",
            "owner": None,
            "recurrence_of": None,
            "confidence": 0.8,
            "created_at": datetime.now(tz=timezone.utc).isoformat(),
        }
    )

    store.update_recommendation_status(rec_id, RecommendationStatus.CLOSED.value)

    rows = store.get_recommendations(PROJECT)
    updated = next(r for r in rows if r["id"] == rec_id)
    assert updated["status"] == "CLOSED"


# ---------------------------------------------------------------------------
# test_status_filter_on_retrieval
# ---------------------------------------------------------------------------


def test_status_filter_on_retrieval(store: AssuranceStore) -> None:
    """get_recommendations respects the status_filter argument."""
    now_iso = datetime.now(tz=timezone.utc).isoformat()
    store.upsert_recommendation(
        {
            "id": "filter-open-001",
            "project_id": PROJECT,
            "text": "Rec A",
            "category": "High",
            "source_review_id": "rev-1",
            "review_date": "2026-02-01",
            "status": "OPEN",
            "owner": None,
            "recurrence_of": None,
            "confidence": 0.9,
            "created_at": now_iso,
        }
    )
    store.upsert_recommendation(
        {
            "id": "filter-closed-001",
            "project_id": PROJECT,
            "text": "Rec B",
            "category": "Medium",
            "source_review_id": "rev-1",
            "review_date": "2026-02-01",
            "status": "CLOSED",
            "owner": None,
            "recurrence_of": None,
            "confidence": 0.85,
            "created_at": now_iso,
        }
    )

    open_recs = store.get_recommendations(PROJECT, status_filter="OPEN")
    closed_recs = store.get_recommendations(PROJECT, status_filter="CLOSED")
    all_recs = store.get_recommendations(PROJECT)

    assert all(r["status"] == "OPEN" for r in open_recs)
    assert all(r["status"] == "CLOSED" for r in closed_recs)
    assert len(all_recs) == len(open_recs) + len(closed_recs)


# ---------------------------------------------------------------------------
# Additional edge cases for coverage
# ---------------------------------------------------------------------------


async def test_empty_items_from_extractor(
    store: AssuranceStore,
) -> None:
    """Extractor returning no items produces an empty result gracefully."""
    mock = MagicMock()
    mock.extract = AsyncMock(return_value=make_confidence_result(items=[]))

    extractor = RecommendationExtractor(extractor=mock, store=store)
    result = await extractor.extract(
        review_text="No recommendations.",
        review_id="review-empty",
        project_id=PROJECT,
    )

    assert result.recommendations == []


async def test_non_dict_items_skipped(store: AssuranceStore) -> None:
    """Non-dict items in the consensus list are silently skipped."""
    mock = MagicMock()
    mock.extract = AsyncMock(
        return_value=make_confidence_result(items=["not-a-dict", 42, None])
    )

    extractor = RecommendationExtractor(extractor=mock, store=store)
    result = await extractor.extract(
        review_text="...",
        review_id="review-bad",
        project_id=PROJECT,
    )

    assert result.recommendations == []


async def test_no_recurrence_detector_skips_prior_check(
    mock_confidence_extractor: MagicMock,
    store: AssuranceStore,
) -> None:
    """When recurrence_detector is None, no prior lookup is performed."""
    extractor = RecommendationExtractor(
        extractor=mock_confidence_extractor,
        store=store,
        recurrence_detector=None,
    )
    result = await extractor.extract(
        review_text="...",
        review_id="review-no-detector",
        project_id=PROJECT,
    )
    # All returned recommendations are OPEN (no recurrence marking)
    assert all(r.status == RecommendationStatus.OPEN for r in result.recommendations)


async def test_recurrence_excludes_same_review_recs(
    store: AssuranceStore,
) -> None:
    """Prior recommendations from the same review_id are excluded from recurrence."""
    same_review_id = "review-same"
    rec_text = "Update project controls"

    # Seed a rec from the SAME review
    store.upsert_recommendation(
        {
            "id": "same-rev-rec",
            "project_id": PROJECT,
            "text": rec_text,
            "category": "High",
            "source_review_id": same_review_id,
            "review_date": "2026-03-01",
            "status": "OPEN",
            "owner": None,
            "recurrence_of": None,
            "confidence": 0.9,
            "created_at": datetime.now(tz=timezone.utc).isoformat(),
        }
    )

    # Mock detector that would mark everything recurring if prior is present
    mock_detector = MagicMock(spec=RecurrenceDetector)

    def _detect(
        new_recommendations: list[Recommendation],
        prior_recommendations: list[Recommendation],
    ) -> list[Recommendation]:
        # Prior should be empty because same review is excluded
        assert prior_recommendations == [], "Same-review recs must be excluded"
        return new_recommendations

    mock_detector.detect_recurrences = _detect

    mock_ce = MagicMock()
    mock_ce.extract = AsyncMock(
        return_value=make_confidence_result(
            items=[{"action": rec_text, "priority": "High"}]
        )
    )

    extractor = RecommendationExtractor(
        extractor=mock_ce,
        store=store,
        recurrence_detector=mock_detector,
    )
    await extractor.extract(
        review_text=rec_text,
        review_id=same_review_id,
        project_id=PROJECT,
    )
