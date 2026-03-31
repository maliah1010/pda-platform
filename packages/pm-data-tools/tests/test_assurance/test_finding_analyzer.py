"""Tests for P3: Cross-Cycle Finding Analyzer.

Covers FindingAnalyzer, RecurrenceDetector, and persistence via the shared
SQLite store.  All ConfidenceExtractor calls are mocked.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from pm_data_tools.assurance import (
    FindingAnalysisResult,
    FindingAnalyzer,
    RecurrenceDetector,
    ReviewAction,
    ReviewActionStatus,
)
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
    """Extraction returns populated FindingAnalysisResult."""
    analyzer = FindingAnalyzer(
        extractor=mock_confidence_extractor,
        store=store,
    )

    result = await analyzer.extract(
        review_text=sample_review_text,
        review_id="review-q1-2026",
        project_id=PROJECT,
    )

    assert isinstance(result, FindingAnalysisResult)
    assert len(result.recommendations) >= 1
    assert result.extraction_confidence > 0.0
    assert result.review_level is not None

    action = result.recommendations[0]
    assert isinstance(action, ReviewAction)
    assert action.text
    assert action.source_review_id == "review-q1-2026"
    assert action.status == ReviewActionStatus.OPEN


# ---------------------------------------------------------------------------
# test_low_confidence_flagged_not_rejected
# ---------------------------------------------------------------------------


async def test_low_confidence_flagged_not_rejected(
    mock_extractor_low_confidence: MagicMock,
    store: AssuranceStore,
) -> None:
    """Low-confidence extractions are flagged but still returned."""
    analyzer = FindingAnalyzer(
        extractor=mock_extractor_low_confidence,
        store=store,
        min_confidence=0.60,
    )

    result = await analyzer.extract(
        review_text="Review governance framework alignment.",
        review_id="review-low",
        project_id=PROJECT,
    )

    assert len(result.recommendations) >= 1
    flagged = [r for r in result.recommendations if r.flagged_for_review]
    assert len(flagged) >= 1
    # Flagged items retain OPEN status — not rejected
    assert all(r.status == ReviewActionStatus.OPEN for r in flagged)


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

    analyzer = FindingAnalyzer(extractor=mock, store=store)
    result = await analyzer.extract(
        review_text="...",
        review_id="review-dedup",
        project_id=PROJECT,
    )

    texts = [r.text for r in result.recommendations]
    assert len(texts) == len({t.lower() for t in texts})
    assert len(result.recommendations) == 1


# ---------------------------------------------------------------------------
# test_recurrence_detected_across_review_cycles
# ---------------------------------------------------------------------------


async def test_recurrence_detected_across_review_cycles(
    store: AssuranceStore,
) -> None:
    """A review action matching a prior OPEN action is marked RECURRING."""
    prior_action_id = "prior-rec-001"
    review_text = "Implement automated regression testing."

    # Pre-seed a prior OPEN review action
    store.upsert_recommendation(
        {
            "id": prior_action_id,
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

    # Build a mock recurrence detector that always flags the first new action
    mock_detector = MagicMock(spec=RecurrenceDetector)

    def _fake_detect(
        new_recommendations: list[ReviewAction],
        prior_recommendations: list[ReviewAction],
    ) -> list[ReviewAction]:
        updated = []
        for action in new_recommendations:
            if prior_recommendations:
                action = action.model_copy(
                    update={
                        "status": ReviewActionStatus.RECURRING,
                        "recurrence_of": prior_recommendations[0].id,
                    }
                )
            updated.append(action)
        return updated

    mock_detector.detect_recurrences = _fake_detect

    analyzer = FindingAnalyzer(
        extractor=mock,
        store=store,
        recurrence_detector=mock_detector,
    )
    result = await analyzer.extract(
        review_text=review_text,
        review_id="review-q1-2026",
        project_id=PROJECT,
    )

    recurring = [r for r in result.recommendations if r.status == ReviewActionStatus.RECURRING]
    assert len(recurring) >= 1
    assert recurring[0].recurrence_of == prior_action_id


# ---------------------------------------------------------------------------
# test_recurrence_skipped_gracefully_without_sentence_transformers
# ---------------------------------------------------------------------------


async def test_recurrence_skipped_gracefully_without_sentence_transformers(
    store: AssuranceStore,
) -> None:
    """RecurrenceDetector skips detection and logs a warning when library absent."""
    prior = [
        ReviewAction(
            id="prior-001",
            text="Establish testing pipeline",
            category="High",
            source_review_id="review-old",
            review_date=date(2025, 9, 1),
            confidence=0.9,
        )
    ]
    new = [
        ReviewAction(
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

    # Actions returned unchanged (not RECURRING)
    assert result[0].status == ReviewActionStatus.OPEN
    assert result[0].recurrence_of is None


# ---------------------------------------------------------------------------
# test_status_update_open_to_closed
# ---------------------------------------------------------------------------


def test_status_update_open_to_closed(store: AssuranceStore) -> None:
    """A review action status can be updated from OPEN to CLOSED."""
    action_id = "update-test-001"
    store.upsert_recommendation(
        {
            "id": action_id,
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

    store.update_recommendation_status(action_id, ReviewActionStatus.CLOSED.value)

    rows = store.get_recommendations(PROJECT)
    updated = next(r for r in rows if r["id"] == action_id)
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
            "text": "Action A",
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
            "text": "Action B",
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

    open_actions = store.get_recommendations(PROJECT, status_filter="OPEN")
    closed_actions = store.get_recommendations(PROJECT, status_filter="CLOSED")
    all_actions = store.get_recommendations(PROJECT)

    assert all(r["status"] == "OPEN" for r in open_actions)
    assert all(r["status"] == "CLOSED" for r in closed_actions)
    assert len(all_actions) == len(open_actions) + len(closed_actions)


# ---------------------------------------------------------------------------
# Additional edge cases for coverage
# ---------------------------------------------------------------------------


async def test_empty_items_from_extractor(
    store: AssuranceStore,
) -> None:
    """Extractor returning no items produces an empty result gracefully."""
    mock = MagicMock()
    mock.extract = AsyncMock(return_value=make_confidence_result(items=[]))

    analyzer = FindingAnalyzer(extractor=mock, store=store)
    result = await analyzer.extract(
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

    analyzer = FindingAnalyzer(extractor=mock, store=store)
    result = await analyzer.extract(
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
    analyzer = FindingAnalyzer(
        extractor=mock_confidence_extractor,
        store=store,
        recurrence_detector=None,
    )
    result = await analyzer.extract(
        review_text="...",
        review_id="review-no-detector",
        project_id=PROJECT,
    )
    # All returned actions are OPEN (no recurrence marking)
    assert all(r.status == ReviewActionStatus.OPEN for r in result.recommendations)


async def test_recurrence_excludes_same_review_actions(
    store: AssuranceStore,
) -> None:
    """Prior actions from the same review_id are excluded from recurrence."""
    same_review_id = "review-same"
    action_text = "Update project controls"

    # Seed an action from the SAME review
    store.upsert_recommendation(
        {
            "id": "same-rev-rec",
            "project_id": PROJECT,
            "text": action_text,
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
        new_recommendations: list[ReviewAction],
        prior_recommendations: list[ReviewAction],
    ) -> list[ReviewAction]:
        # Prior should be empty because same review is excluded
        assert prior_recommendations == [], "Same-review actions must be excluded"
        return new_recommendations

    mock_detector.detect_recurrences = _detect

    mock_ce = MagicMock()
    mock_ce.extract = AsyncMock(
        return_value=make_confidence_result(
            items=[{"action": action_text, "priority": "High"}]
        )
    )

    analyzer = FindingAnalyzer(
        extractor=mock_ce,
        store=store,
        recurrence_detector=mock_detector,
    )
    await analyzer.extract(
        review_text=action_text,
        review_id=same_review_id,
        project_id=PROJECT,
    )
