"""Cross-cycle finding analysis using agent-task-planning's ConfidenceExtractor.

This module wraps :class:`~agent_planning.confidence.ConfidenceExtractor`
with the :data:`~agent_planning.confidence.SchemaType.RECOMMENDATION` schema
to extract, deduplicate, and persist review actions from project review text
across multiple review cycles.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

import structlog
from agent_planning.confidence import ConfidenceExtractor, SchemaType

from ..db.store import AssuranceStore
from .models import FindingAnalysisResult, ReviewAction, ReviewActionStatus
from .recurrence import RecurrenceDetector

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

_EXTRACT_QUERY = (
    "Extract all assurance recommendations from the project review text. "
    "Include every distinct recommended action with its rationale and priority."
)


class FindingAnalyzer:
    """Extract and deduplicate review actions from project review text.

    Uses :class:`~agent_planning.confidence.ConfidenceExtractor` with the
    :data:`~agent_planning.confidence.SchemaType.RECOMMENDATION` schema for
    reliable multi-sample extraction.  Results are persisted to the shared
    SQLite store and optionally checked for recurrence against prior cycles.

    Review actions with extraction confidence below ``min_confidence`` are
    **flagged** for human review but not rejected.

    Example::

        from agent_planning.confidence import ConfidenceExtractor
        from agent_planning.providers.anthropic import AnthropicProvider

        provider = AnthropicProvider(api_key="...")
        ce = ConfidenceExtractor(provider)

        analyzer = FindingAnalyzer(extractor=ce)
        result = await analyzer.extract(
            review_text="...",
            review_id="review-2026-Q1",
            project_id="PROJ-001",
        )
    """

    def __init__(
        self,
        extractor: ConfidenceExtractor,
        min_confidence: float = 0.60,
        store: AssuranceStore | None = None,
        recurrence_detector: RecurrenceDetector | None = None,
    ) -> None:
        """Initialise the finding analyzer.

        Args:
            extractor: Configured :class:`~agent_planning.confidence.ConfidenceExtractor`
                instance.
            min_confidence: Confidence threshold below which review actions are
                flagged for human review (default 0.60).  Items below this
                threshold are retained, not discarded.
            store: Shared :class:`~pm_data_tools.db.store.AssuranceStore`.
                A default store is created if not provided.
            recurrence_detector: Optional :class:`~.recurrence.RecurrenceDetector`.
                When supplied, new review actions are checked for recurrence
                against prior OPEN actions for the same project.
        """
        self._extractor = extractor
        self._min_confidence = min_confidence
        self._store = store or AssuranceStore()
        self._recurrence_detector = recurrence_detector

    async def extract(
        self,
        review_text: str,
        review_id: str,
        project_id: str,
    ) -> FindingAnalysisResult:
        """Extract review actions from a project review document.

        Runs multi-sample extraction via :class:`ConfidenceExtractor`, maps
        results to :class:`~.models.ReviewAction` objects, deduplicates
        within the current review, detects recurrences against prior cycles,
        and persists all results to the store.

        Args:
            review_text: Raw text of the project review document.
            review_id: Unique identifier for this review (used as
                ``source_review_id`` on resulting review actions).
            project_id: Project identifier for persistence and recurrence
                lookup.

        Returns:
            :class:`~.models.FindingAnalysisResult` containing all
            extracted review actions and extraction metadata.
        """
        logger.info(
            "finding_analysis_started",
            review_id=review_id,
            project_id=project_id,
        )

        result = await self._extractor.extract(
            query=_EXTRACT_QUERY,
            context=review_text,
            schema=SchemaType.RECOMMENDATION,
        )

        overall_confidence = result.confidence
        review_level = result.review_level.value
        cost_usd = result.cost_usd

        # Convert consensus items to ReviewAction objects
        raw_items = result.consensus.get("items", [])
        if not isinstance(raw_items, list):
            raw_items = []

        today = date.today()
        seen_texts: set[str] = set()
        review_actions: list[ReviewAction] = []

        for item in raw_items:
            if not isinstance(item, dict):
                continue

            text = str(item.get("action", "")).strip()
            if not text:
                continue

            # Deduplicate within the current review
            normalised = text.lower()
            if normalised in seen_texts:
                logger.debug(
                    "review_action_deduplicated",
                    text=text[:60],
                    review_id=review_id,
                )
                continue
            seen_texts.add(normalised)

            category = str(item.get("priority", "Medium"))
            owner = item.get("owner")

            action = ReviewAction(
                text=text,
                category=category,
                source_review_id=review_id,
                review_date=today,
                status=ReviewActionStatus.OPEN,
                owner=str(owner) if owner else None,
                confidence=overall_confidence,
                flagged_for_review=overall_confidence < self._min_confidence,
            )
            review_actions.append(action)

        # Recurrence detection across prior review cycles
        if self._recurrence_detector is not None and review_actions:
            prior_rows = self._store.get_recommendations(
                project_id=project_id,
                status_filter=ReviewActionStatus.OPEN.value,
            )
            prior = [
                ReviewAction(
                    id=str(r["id"]),
                    text=str(r["text"]),
                    category=str(r["category"]),
                    source_review_id=str(r["source_review_id"]),
                    review_date=date.fromisoformat(str(r["review_date"])),
                    status=ReviewActionStatus(str(r["status"])),
                    owner=str(r["owner"]) if r.get("owner") else None,
                    recurrence_of=(
                        str(r["recurrence_of"]) if r.get("recurrence_of") else None
                    ),
                    confidence=float(r["confidence"]),  # type: ignore[arg-type]
                )
                for r in prior_rows
                # Exclude actions from the current review to avoid self-matching
                if r["source_review_id"] != review_id
            ]
            review_actions = self._recurrence_detector.detect_recurrences(
                new_recommendations=review_actions,
                prior_recommendations=prior,
            )

        # Persist to store
        now_iso = datetime.now(tz=timezone.utc).isoformat()
        for action in review_actions:
            self._store.upsert_recommendation(
                {
                    "id": action.id,
                    "project_id": project_id,
                    "text": action.text,
                    "category": action.category,
                    "source_review_id": action.source_review_id,
                    "review_date": action.review_date.isoformat(),
                    "status": action.status.value,
                    "owner": action.owner,
                    "recurrence_of": action.recurrence_of,
                    "confidence": action.confidence,
                    "created_at": now_iso,
                }
            )

        logger.info(
            "finding_analysis_complete",
            review_id=review_id,
            project_id=project_id,
            count=len(review_actions),
            confidence=overall_confidence,
        )

        return FindingAnalysisResult(
            recommendations=review_actions,
            extraction_confidence=overall_confidence,
            review_level=review_level,
            cost_usd=cost_usd,
        )
