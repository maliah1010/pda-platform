"""Lessons Learned Knowledge Engine for project assurance.

Organisations accumulate lessons from past projects but rarely make them
available at the point of decision-making.  Lessons databases exist but are
unstructured, unsearchable, and disconnected from current project context.
This module ingests structured lesson records with contextual metadata and
provides keyword and semantic search to surface relevant lessons matched to
a project's current situation.

Usage::

    from pm_data_tools.assurance.lessons import (
        LessonsKnowledgeEngine,
        LessonRecord,
        LessonCategory,
        LessonSentiment,
    )

    engine = LessonsKnowledgeEngine()
    engine.ingest(
        LessonRecord(
            project_id="PROJ-001",
            title="Early stakeholder engagement prevented scope creep",
            description="Fortnightly workshops from week 2 identified conflicting "
                        "requirements before architecture was finalised.",
            category=LessonCategory.STAKEHOLDER,
            sentiment=LessonSentiment.POSITIVE,
            project_type="ICT",
            project_phase="Initiation",
        )
    )
    response = engine.search("stakeholder engagement", project_type="ICT")
"""

from __future__ import annotations

import json
import uuid
from collections import Counter
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any

import structlog
from pydantic import BaseModel, Field

from ..db.store import AssuranceStore

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

try:
    import numpy as np
    from sentence_transformers import SentenceTransformer

    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:  # pragma: no cover
    SENTENCE_TRANSFORMERS_AVAILABLE = False


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class LessonCategory(Enum):
    """Root cause or domain classification for a lesson.

    Attributes:
        GOVERNANCE: Lessons related to governance structure and decision-making.
        TECHNICAL: Technical design, architecture, or implementation lessons.
        COMMERCIAL: Procurement, contracts, or supplier management lessons.
        STAKEHOLDER: Stakeholder engagement and communication lessons.
        RESOURCE: Staffing, skills, or capacity lessons.
        REQUIREMENTS: Requirements management and change control lessons.
        ESTIMATION: Schedule or cost estimation lessons.
        RISK_MANAGEMENT: Risk identification or mitigation lessons.
        BENEFITS_REALISATION: Lessons about benefit tracking and delivery.
        OTHER: Lessons that do not fit other categories.
    """

    GOVERNANCE = "GOVERNANCE"
    TECHNICAL = "TECHNICAL"
    COMMERCIAL = "COMMERCIAL"
    STAKEHOLDER = "STAKEHOLDER"
    RESOURCE = "RESOURCE"
    REQUIREMENTS = "REQUIREMENTS"
    ESTIMATION = "ESTIMATION"
    RISK_MANAGEMENT = "RISK_MANAGEMENT"
    BENEFITS_REALISATION = "BENEFITS_REALISATION"
    OTHER = "OTHER"


class LessonSentiment(Enum):
    """Whether the lesson describes what went well or what went wrong.

    Attributes:
        POSITIVE: What went well — replicate this on future projects.
        NEGATIVE: What went wrong — avoid this on future projects.
    """

    POSITIVE = "POSITIVE"
    NEGATIVE = "NEGATIVE"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class LessonRecord(BaseModel):
    """A single lessons learned entry with contextual metadata.

    Attributes:
        id: Unique identifier (UUID4 by default).
        project_id: Identifier of the source project.
        title: Short summary of the lesson.
        description: Full lesson narrative.
        category: Domain classification (:class:`LessonCategory`).
        sentiment: Whether the lesson is positive or negative
            (:class:`LessonSentiment`).
        project_type: Optional project type (e.g. ``"ICT"``, ``"Infrastructure"``).
        project_phase: Optional phase (e.g. ``"Initiation"``, ``"Delivery"``).
        department: Originating department.
        tags: Free-form tags for keyword discovery.
        date_recorded: Date the lesson was recorded (defaults to today).
        recorded_by: Name or role of the person recording the lesson.
        impact_description: What happened as a result of this lesson.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str
    title: str
    description: str
    category: LessonCategory
    sentiment: LessonSentiment
    project_type: str | None = None
    project_phase: str | None = None
    department: str | None = None
    tags: list[str] = Field(default_factory=list)
    date_recorded: date = Field(default_factory=date.today)
    recorded_by: str | None = None
    impact_description: str | None = None


class LessonSearchResult(BaseModel):
    """A single search result with relevance scoring.

    Attributes:
        lesson: The matched :class:`LessonRecord`.
        relevance_score: Score between 0.0 and 1.0 indicating match quality.
        match_reason: Why this lesson matched (e.g. ``"keyword match in title"``).
    """

    lesson: LessonRecord
    relevance_score: float
    match_reason: str


class LessonSearchResponse(BaseModel):
    """Response from a lessons search query.

    Attributes:
        query: The original search query.
        results: Ranked list of :class:`LessonSearchResult` objects.
        total_in_corpus: Total lessons in the store (before filtering).
        search_method: Which method was used — ``"keyword"`` or ``"semantic"``.
    """

    query: str
    results: list[LessonSearchResult]
    total_in_corpus: int
    search_method: str


class LessonPatternSummary(BaseModel):
    """Aggregate patterns across the lessons corpus.

    Attributes:
        total_lessons: Total lessons in the corpus.
        by_category: Count per :class:`LessonCategory` value.
        by_sentiment: Count per :class:`LessonSentiment` value.
        by_project_type: Count per project type string.
        top_tags: Top-10 tags by frequency as
            ``[{"tag": str, "count": int}]``.
        most_common_negative_categories: Categories with most
            :attr:`~LessonSentiment.NEGATIVE` lessons, as
            ``[{"category": str, "count": int}]``.
        message: Human-readable summary.
    """

    total_lessons: int
    by_category: dict[str, int]
    by_sentiment: dict[str, int]
    by_project_type: dict[str, int]
    top_tags: list[dict[str, Any]]
    most_common_negative_categories: list[dict[str, Any]]
    message: str


# ---------------------------------------------------------------------------
# Core class
# ---------------------------------------------------------------------------


class LessonsKnowledgeEngine:
    """Ingest, search, and analyse lessons learned from project history.

    Supports two search modes:

    - **Keyword search**: Fast, always available.  Matches against title,
      description, tags, and category using case-insensitive substring
      matching.
    - **Semantic search**: Uses sentence-transformer embeddings for
      meaning-based retrieval.  Requires ``sentence-transformers``
      (optional dependency).  Falls back to keyword search when unavailable.

    The engine follows the same optional-dependency pattern as
    :class:`~pm_data_tools.assurance.recurrence.RecurrenceDetector`.

    Example::

        engine = LessonsKnowledgeEngine()
        engine.ingest(LessonRecord(
            project_id="PROJ-001",
            title="Delayed procurement caused 6-week slip",
            description="...",
            category=LessonCategory.COMMERCIAL,
            sentiment=LessonSentiment.NEGATIVE,
        ))
        response = engine.search("procurement delays", sentiment=LessonSentiment.NEGATIVE)
    """

    def __init__(
        self,
        store: AssuranceStore | None = None,
        model_name: str = "all-MiniLM-L6-v2",
        similarity_threshold: float = 0.40,
    ) -> None:
        """Initialise the engine.

        Args:
            store: :class:`~pm_data_tools.db.store.AssuranceStore` for
                persistence.  A default store is used if not provided.
            model_name: Sentence-transformer model name for semantic search.
            similarity_threshold: Minimum cosine similarity to include a lesson
                in semantic search results (default 0.40).
        """
        self._store = store or AssuranceStore()
        self._model_name = model_name
        self._similarity_threshold = similarity_threshold
        self._model: object | None = None  # lazy-loaded

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_model(self) -> SentenceTransformer:
        """Lazily load the sentence-transformer model.

        Returns:
            The loaded :class:`~sentence_transformers.SentenceTransformer`.
        """
        if self._model is None:
            self._model = SentenceTransformer(self._model_name)
        return self._model  # type: ignore[return-value]

    @staticmethod
    def _row_to_lesson(row: dict[str, object]) -> LessonRecord:
        """Deserialise a database row to a :class:`LessonRecord`.

        Args:
            row: A dict with the columns of the ``lessons_learned`` table.

        Returns:
            The reconstructed :class:`LessonRecord`.
        """
        return LessonRecord(
            id=str(row["id"]),
            project_id=str(row["project_id"]),
            title=str(row["title"]),
            description=str(row["description"]),
            category=LessonCategory(str(row["category"])),
            sentiment=LessonSentiment(str(row["sentiment"])),
            project_type=str(row["project_type"]) if row.get("project_type") else None,
            project_phase=str(row["project_phase"]) if row.get("project_phase") else None,
            department=str(row["department"]) if row.get("department") else None,
            tags=json.loads(str(row.get("tags_json", "[]"))),
            date_recorded=date.fromisoformat(str(row["date_recorded"])),
            recorded_by=str(row["recorded_by"]) if row.get("recorded_by") else None,
            impact_description=(
                str(row["impact_description"]) if row.get("impact_description") else None
            ),
        )

    # ------------------------------------------------------------------
    # Ingestion
    # ------------------------------------------------------------------

    def ingest(self, lesson: LessonRecord) -> LessonRecord:
        """Persist a lesson to the store.

        Args:
            lesson: The :class:`LessonRecord` to persist.

        Returns:
            The same lesson object (with its auto-generated ``id`` if not set).
        """
        self._store.upsert_lesson(
            {
                "id": lesson.id,
                "project_id": lesson.project_id,
                "title": lesson.title,
                "description": lesson.description,
                "category": lesson.category.value,
                "sentiment": lesson.sentiment.value,
                "project_type": lesson.project_type,
                "project_phase": lesson.project_phase,
                "department": lesson.department,
                "tags_json": json.dumps(lesson.tags),
                "date_recorded": lesson.date_recorded.isoformat(),
                "recorded_by": lesson.recorded_by,
                "impact_description": lesson.impact_description,
                "created_at": datetime.now(tz=timezone.utc).isoformat(),
            }
        )
        logger.info(
            "lesson_ingested",
            id=lesson.id,
            project_id=lesson.project_id,
            category=lesson.category.value,
            sentiment=lesson.sentiment.value,
        )
        return lesson

    def ingest_batch(self, lessons: list[LessonRecord]) -> int:
        """Ingest multiple lessons.

        Args:
            lessons: List of :class:`LessonRecord` objects to ingest.

        Returns:
            Count of successfully ingested lessons.
        """
        count = 0
        for lesson in lessons:
            self.ingest(lesson)
            count += 1
        logger.info("lesson_batch_ingested", count=count)
        return count

    # ------------------------------------------------------------------
    # Search
    # ------------------------------------------------------------------

    def search(
        self,
        query: str,
        project_type: str | None = None,
        category: LessonCategory | None = None,
        sentiment: LessonSentiment | None = None,
        limit: int = 10,
    ) -> LessonSearchResponse:
        """Search the lessons corpus.

        Attempts semantic search first if ``sentence-transformers`` is
        available.  Falls back to keyword search otherwise.  Results are
        filtered by ``project_type``, ``category``, and ``sentiment`` before
        scoring.

        Args:
            query: Free-text search query.
            project_type: Optional project type filter.
            category: Optional :class:`LessonCategory` filter.
            sentiment: Optional :class:`LessonSentiment` filter.
            limit: Maximum number of results to return (default 10).

        Returns:
            :class:`LessonSearchResponse` with ranked results and metadata.
        """
        all_rows = self._store.get_all_lessons()
        all_lessons = [self._row_to_lesson(row) for row in all_rows]
        total = len(all_lessons)

        candidates = all_lessons
        if project_type is not None:
            candidates = [lsn for lsn in candidates if lsn.project_type == project_type]
        if category is not None:
            candidates = [lsn for lsn in candidates if lsn.category == category]
        if sentiment is not None:
            candidates = [lsn for lsn in candidates if lsn.sentiment == sentiment]

        if SENTENCE_TRANSFORMERS_AVAILABLE:
            results = self._semantic_search(query, candidates, limit)
            method = "semantic"
        else:
            results = self._keyword_search(query, candidates, limit)
            method = "keyword"

        logger.info(
            "lessons_searched",
            query=query[:60],
            method=method,
            results=len(results),
            total_in_corpus=total,
        )
        return LessonSearchResponse(
            query=query,
            results=results,
            total_in_corpus=total,
            search_method=method,
        )

    def _keyword_search(
        self,
        query: str,
        candidates: list[LessonRecord],
        limit: int,
    ) -> list[LessonSearchResult]:
        """Keyword-based search with simple relevance scoring.

        Scoring per lesson:

        - +1.0 for a match in ``title``
        - +0.5 for a match in ``description``
        - +0.3 for a match in any ``tag``
        - +0.2 for a match in ``category`` name

        Score is normalised by dividing by the maximum possible (2.0).

        Args:
            query: The search string (matched case-insensitively).
            candidates: Lessons to search.
            limit: Maximum results to return.

        Returns:
            Sorted list of :class:`LessonSearchResult` objects.
        """
        q = query.lower()
        scored: list[LessonSearchResult] = []

        for lesson in candidates:
            score = 0.0
            reasons: list[str] = []

            if q in lesson.title.lower():
                score += 1.0
                reasons.append("keyword match in title")
            if q in lesson.description.lower():
                score += 0.5
                reasons.append("keyword match in description")
            for tag in lesson.tags:
                if q in tag.lower():
                    score += 0.3
                    reasons.append(f"keyword match in tag: {tag}")
                    break
            if q in lesson.category.value.lower():
                score += 0.2
                reasons.append("keyword match in category")

            if score > 0:
                normalized = min(score / 2.0, 1.0)
                scored.append(
                    LessonSearchResult(
                        lesson=lesson,
                        relevance_score=normalized,
                        match_reason="; ".join(reasons),
                    )
                )

        scored.sort(key=lambda r: r.relevance_score, reverse=True)
        return scored[:limit]

    def _semantic_search(
        self,
        query: str,
        candidates: list[LessonRecord],
        limit: int,
    ) -> list[LessonSearchResult]:
        """Semantic search using sentence-transformer embeddings.

        Embeds the query and each candidate's ``title + description``,
        computes cosine similarity, and returns those above
        :attr:`_similarity_threshold`.  Falls back to keyword search
        if ``sentence-transformers`` is unavailable.

        Args:
            query: The search query.
            candidates: Lessons to search.
            limit: Maximum results to return.

        Returns:
            Sorted list of :class:`LessonSearchResult` objects.
        """
        if not SENTENCE_TRANSFORMERS_AVAILABLE:
            logger.warning(
                "semantic_search_unavailable",
                reason="sentence-transformers not installed",
            )
            return self._keyword_search(query, candidates, limit)

        if not candidates:
            return []

        model = self._get_model()

        query_embedding = np.array(model.encode([query]))  # type: ignore[attr-defined]
        corpus_texts = [f"{lsn.title} {lsn.description}" for lsn in candidates]
        corpus_embeddings = np.array(model.encode(corpus_texts))  # type: ignore[attr-defined]

        q_norm = np.linalg.norm(query_embedding, axis=1, keepdims=True)
        c_norm = np.linalg.norm(corpus_embeddings, axis=1, keepdims=True)
        q_normed = query_embedding / np.where(q_norm == 0, 1, q_norm)
        c_normed = corpus_embeddings / np.where(c_norm == 0, 1, c_norm)
        similarities = (c_normed @ q_normed.T).flatten()

        results: list[LessonSearchResult] = []
        for idx, lesson in enumerate(candidates):
            sim = float(similarities[idx])
            if sim >= self._similarity_threshold:
                results.append(
                    LessonSearchResult(
                        lesson=lesson,
                        relevance_score=sim,
                        match_reason=f"semantic similarity {sim:.2f}",
                    )
                )

        results.sort(key=lambda r: r.relevance_score, reverse=True)
        return results[:limit]

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def get_lessons(
        self,
        project_id: str | None = None,
        category: LessonCategory | None = None,
        sentiment: LessonSentiment | None = None,
    ) -> list[LessonRecord]:
        """Retrieve lessons, optionally filtered.

        Args:
            project_id: Optional project identifier filter.
            category: Optional :class:`LessonCategory` filter.
            sentiment: Optional :class:`LessonSentiment` filter.

        Returns:
            List of :class:`LessonRecord` objects ordered by
            ``date_recorded`` descending.
        """
        rows = self._store.get_lessons(
            project_id=project_id,
            category=category.value if category is not None else None,
            sentiment=sentiment.value if sentiment is not None else None,
        )
        return [self._row_to_lesson(row) for row in rows]

    def get_contextual_lessons(
        self,
        project_type: str,
        project_phase: str | None = None,
        category: LessonCategory | None = None,
        limit: int = 5,
    ) -> list[LessonRecord]:
        """Retrieve lessons most relevant to a project's current context.

        Filters by ``project_type`` and optionally ``project_phase`` and
        ``category``.  Prioritises :attr:`~LessonSentiment.NEGATIVE`
        sentiment, as warnings are more immediately actionable.

        Args:
            project_type: Project type to match (e.g. ``"ICT"``).
            project_phase: Optional phase to match (e.g. ``"Delivery"``).
            category: Optional :class:`LessonCategory` filter.
            limit: Maximum results to return.

        Returns:
            List of :class:`LessonRecord` objects, NEGATIVE-sentiment first.
        """
        all_rows = self._store.get_all_lessons()
        all_lessons = [self._row_to_lesson(row) for row in all_rows]

        filtered = [lsn for lsn in all_lessons if lsn.project_type == project_type]
        if project_phase is not None:
            filtered = [lsn for lsn in filtered if lsn.project_phase == project_phase]
        if category is not None:
            filtered = [lsn for lsn in filtered if lsn.category == category]

        negative = [lsn for lsn in filtered if lsn.sentiment == LessonSentiment.NEGATIVE]
        positive = [lsn for lsn in filtered if lsn.sentiment == LessonSentiment.POSITIVE]
        ranked = negative + positive

        logger.debug(
            "contextual_lessons_retrieved",
            project_type=project_type,
            project_phase=project_phase,
            count=min(limit, len(ranked)),
        )
        return ranked[:limit]

    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------

    def analyse_patterns(self) -> LessonPatternSummary:
        """Compute aggregate patterns across the entire lessons corpus.

        Returns:
            :class:`LessonPatternSummary` with breakdowns by category,
            sentiment, project type, top tags, and most common negative
            categories.
        """
        all_rows = self._store.get_all_lessons()
        all_lessons = [self._row_to_lesson(row) for row in all_rows]
        total = len(all_lessons)

        if total == 0:
            return LessonPatternSummary(
                total_lessons=0,
                by_category={},
                by_sentiment={},
                by_project_type={},
                top_tags=[],
                most_common_negative_categories=[],
                message="No lessons recorded in the corpus.",
            )

        by_category: dict[str, int] = {}
        for lc in LessonCategory:
            count = sum(1 for lsn in all_lessons if lsn.category == lc)
            if count:
                by_category[lc.value] = count

        by_sentiment: dict[str, int] = {}
        for ls in LessonSentiment:
            count = sum(1 for lsn in all_lessons if lsn.sentiment == ls)
            if count:
                by_sentiment[ls.value] = count

        pt_counter: Counter[str] = Counter(
            lsn.project_type for lsn in all_lessons if lsn.project_type
        )
        by_project_type = dict(pt_counter.most_common())

        all_tags: list[str] = []
        for lesson in all_lessons:
            all_tags.extend(lesson.tags)
        tag_counter: Counter[str] = Counter(all_tags)
        top_tags = [{"tag": t, "count": c} for t, c in tag_counter.most_common(10)]

        negative_lessons = [
            lsn for lsn in all_lessons if lsn.sentiment == LessonSentiment.NEGATIVE
        ]
        neg_cat_counter: Counter[str] = Counter(lsn.category.value for lsn in negative_lessons)
        most_common_negative_categories = [
            {"category": cat, "count": cnt}
            for cat, cnt in neg_cat_counter.most_common()
        ]

        pos_count = by_sentiment.get("POSITIVE", 0)
        neg_count = by_sentiment.get("NEGATIVE", 0)
        message = (
            f"{total} lesson(s) in corpus.  "
            f"Positive: {pos_count}, Negative: {neg_count}."
        )

        logger.info("lessons_patterns_analysed", total=total)
        return LessonPatternSummary(
            total_lessons=total,
            by_category=by_category,
            by_sentiment=by_sentiment,
            by_project_type=by_project_type,
            top_tags=top_tags,
            most_common_negative_categories=most_common_negative_categories,
            message=message,
        )
