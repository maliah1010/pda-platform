"""Tests for P7 — Lessons Learned Knowledge Engine.

Covers ingestion, keyword search, filter combinations, pattern analysis,
contextual retrieval, and the semantic-search fallback path.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from pm_data_tools.assurance.lessons import (
    SENTENCE_TRANSFORMERS_AVAILABLE,
    LessonCategory,
    LessonRecord,
    LessonSentiment,
    LessonsKnowledgeEngine,
)
from pm_data_tools.db.store import AssuranceStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_lesson(
    project_id: str = "PROJ-001",
    title: str = "Test lesson title",
    description: str = "A description of the lesson learned.",
    category: LessonCategory = LessonCategory.GOVERNANCE,
    sentiment: LessonSentiment = LessonSentiment.NEGATIVE,
    project_type: str | None = "ICT",
    project_phase: str | None = "Delivery",
    tags: list[str] | None = None,
    **kwargs: object,
) -> LessonRecord:
    """Build a LessonRecord with sensible defaults."""
    return LessonRecord(
        project_id=project_id,
        title=title,
        description=description,
        category=category,
        sentiment=sentiment,
        project_type=project_type,
        project_phase=project_phase,
        tags=tags or [],
        **kwargs,  # type: ignore[arg-type]
    )


def _engine(tmp_path: Path) -> LessonsKnowledgeEngine:
    store = AssuranceStore(db_path=tmp_path / "store.db")
    return LessonsKnowledgeEngine(store=store)


def _populated_engine(tmp_path: Path) -> LessonsKnowledgeEngine:
    """Return an engine pre-loaded with 6 diverse lessons."""
    engine = _engine(tmp_path)
    engine.ingest_batch(
        [
            make_lesson(
                title="Early stakeholder engagement prevented scope creep",
                description="Fortnightly workshops from week 2 identified conflicting requirements.",
                category=LessonCategory.STAKEHOLDER,
                sentiment=LessonSentiment.POSITIVE,
                project_type="ICT",
                project_phase="Initiation",
                tags=["stakeholders", "scope", "requirements"],
            ),
            make_lesson(
                title="Delayed procurement caused 6-week schedule slip",
                description="Contract award took 14 weeks due to challenge period.",
                category=LessonCategory.COMMERCIAL,
                sentiment=LessonSentiment.NEGATIVE,
                project_type="ICT",
                project_phase="Delivery",
                tags=["procurement", "delay", "schedule"],
            ),
            make_lesson(
                title="Risk register not updated after scope change",
                description="When scope expanded in month 4 the risk register was not revisited.",
                category=LessonCategory.RISK_MANAGEMENT,
                sentiment=LessonSentiment.NEGATIVE,
                project_type="Infrastructure",
                project_phase="Delivery",
                tags=["risk", "scope change"],
            ),
            make_lesson(
                title="Weekly stand-ups improved team velocity",
                description="Short daily syncs replaced long weekly meetings and improved delivery pace.",
                category=LessonCategory.GOVERNANCE,
                sentiment=LessonSentiment.POSITIVE,
                project_type="Transformation",
                project_phase="Delivery",
                tags=["governance", "meetings", "velocity"],
            ),
            make_lesson(
                title="Benefits realisation owner not appointed early enough",
                description="Benefits owner was not named until gate 4 causing reporting gaps.",
                category=LessonCategory.BENEFITS_REALISATION,
                sentiment=LessonSentiment.NEGATIVE,
                project_type="ICT",
                project_phase="Initiation",
                tags=["benefits", "ownership"],
            ),
            make_lesson(
                title="Estimation contingency too low for novel technology",
                description="Cost overrun of 35% because no comparable project data was available.",
                category=LessonCategory.ESTIMATION,
                sentiment=LessonSentiment.NEGATIVE,
                project_type="ICT",
                project_phase="Initiation",
                tags=["estimation", "cost", "risk"],
            ),
        ]
    )
    return engine


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------


def test_ingest_single_lesson(tmp_path: Path) -> None:
    """Persist and retrieve a single lesson; verify all fields."""
    engine = _engine(tmp_path)
    lesson = make_lesson(
        project_id="PROJ-A",
        title="My title",
        description="My description",
        category=LessonCategory.TECHNICAL,
        sentiment=LessonSentiment.POSITIVE,
        project_type="Infrastructure",
        project_phase="Closure",
        tags=["tag1", "tag2"],
        recorded_by="Test User",
        impact_description="Saved 2 weeks",
    )
    engine.ingest(lesson)

    retrieved = engine.get_lessons(project_id="PROJ-A")
    assert len(retrieved) == 1
    r = retrieved[0]
    assert r.title == "My title"
    assert r.description == "My description"
    assert r.category == LessonCategory.TECHNICAL
    assert r.sentiment == LessonSentiment.POSITIVE
    assert r.project_type == "Infrastructure"
    assert r.project_phase == "Closure"
    assert r.tags == ["tag1", "tag2"]
    assert r.recorded_by == "Test User"
    assert r.impact_description == "Saved 2 weeks"


def test_ingest_batch(tmp_path: Path) -> None:
    """Multiple lessons ingested; correct count returned."""
    engine = _engine(tmp_path)
    lessons = [make_lesson(title=f"Lesson {i}") for i in range(4)]
    count = engine.ingest_batch(lessons)
    assert count == 4
    assert len(engine.get_lessons(project_id="PROJ-001")) == 4


def test_ingest_generates_id(tmp_path: Path) -> None:
    """Auto-generated id is a non-empty UUID4 string."""
    engine = _engine(tmp_path)
    lesson = make_lesson()
    ingested = engine.ingest(lesson)
    assert len(ingested.id) == 36  # UUID4 canonical form
    assert ingested.id.count("-") == 4


# ---------------------------------------------------------------------------
# Keyword search
# ---------------------------------------------------------------------------


def test_keyword_search_title_match(tmp_path: Path) -> None:
    """Query matching the title produces a high-relevance result."""
    engine = _populated_engine(tmp_path)
    response = engine.search("procurement")
    assert response.search_method == "keyword" or response.search_method == "semantic"
    # Regardless of method, the procurement lesson should be in the top results
    titles = [r.lesson.title for r in response.results]
    assert any("procurement" in t.lower() for t in titles)


def test_keyword_search_description_match(tmp_path: Path) -> None:
    """Query matching only the description produces a moderate-relevance result."""
    engine = _engine(tmp_path)
    engine.ingest(
        make_lesson(
            title="Generic governance lesson",
            description="The contract award process took much longer than planned.",
            category=LessonCategory.COMMERCIAL,
            tags=[],
        )
    )
    response = engine.search("contract award")
    if response.search_method == "keyword":
        assert len(response.results) == 1
        assert response.results[0].relevance_score > 0
        assert "description" in response.results[0].match_reason


def test_keyword_search_tag_match(tmp_path: Path) -> None:
    """Query matching a tag produces a result."""
    engine = _engine(tmp_path)
    engine.ingest(make_lesson(title="Unrelated title", description="Unrelated.", tags=["velocity"]))
    response = engine.search("velocity")
    if response.search_method == "keyword":
        assert len(response.results) == 1
        assert "tag" in response.results[0].match_reason


def test_keyword_search_no_results(tmp_path: Path) -> None:
    """Query matching nothing returns empty results."""
    engine = _populated_engine(tmp_path)
    response = engine.search("xyzzy_nonexistent_term_12345")
    if response.search_method == "keyword":
        assert len(response.results) == 0


def test_keyword_search_case_insensitive(tmp_path: Path) -> None:
    """Search is case-insensitive: 'RISK' matches 'risk management'."""
    engine = _engine(tmp_path)
    engine.ingest(
        make_lesson(
            title="risk management failure",
            description="The risk register was not maintained.",
            category=LessonCategory.RISK_MANAGEMENT,
        )
    )
    response = engine.search("RISK")
    assert len(response.results) > 0


# ---------------------------------------------------------------------------
# Filter tests
# ---------------------------------------------------------------------------


def test_search_filter_by_category(tmp_path: Path) -> None:
    """Only lessons matching the category filter are returned."""
    engine = _populated_engine(tmp_path)
    response = engine.search(
        "lesson",
        category=LessonCategory.COMMERCIAL,
    )
    # With populated engine, only commercial lessons can appear
    for r in response.results:
        assert r.lesson.category == LessonCategory.COMMERCIAL


def test_search_filter_by_sentiment(tmp_path: Path) -> None:
    """Only NEGATIVE lessons are returned when sentiment filter applied."""
    engine = _populated_engine(tmp_path)
    response = engine.search(
        "delay",
        sentiment=LessonSentiment.NEGATIVE,
    )
    for r in response.results:
        assert r.lesson.sentiment == LessonSentiment.NEGATIVE


def test_search_filter_by_project_type(tmp_path: Path) -> None:
    """Only lessons matching project_type are returned."""
    engine = _populated_engine(tmp_path)
    response = engine.search(
        "lesson",
        project_type="Infrastructure",
    )
    for r in response.results:
        assert r.lesson.project_type == "Infrastructure"


def test_search_limit_respected(tmp_path: Path) -> None:
    """Limit parameter caps the number of results returned."""
    engine = _populated_engine(tmp_path)
    # Use a broad query that matches many lessons
    response = engine.search("lesson", limit=2)
    assert len(response.results) <= 2


def test_search_method_reports_keyword(tmp_path: Path) -> None:
    """When sentence-transformers unavailable, search_method is 'keyword'."""
    engine = _populated_engine(tmp_path)
    response = engine.search("procurement")
    if not SENTENCE_TRANSFORMERS_AVAILABLE:
        assert response.search_method == "keyword"


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------


def test_get_lessons_unfiltered(tmp_path: Path) -> None:
    """get_lessons with no filters returns all lessons for the project."""
    engine = _engine(tmp_path)
    for i in range(3):
        engine.ingest(make_lesson(project_id="PROJ-X", title=f"Lesson {i}"))
    lessons = engine.get_lessons(project_id="PROJ-X")
    assert len(lessons) == 3


def test_get_lessons_by_category(tmp_path: Path) -> None:
    """get_lessons filters correctly by category."""
    engine = _engine(tmp_path)
    engine.ingest(make_lesson(category=LessonCategory.TECHNICAL))
    engine.ingest(make_lesson(category=LessonCategory.COMMERCIAL))
    result = engine.get_lessons(project_id="PROJ-001", category=LessonCategory.TECHNICAL)
    assert len(result) == 1
    assert result[0].category == LessonCategory.TECHNICAL


# ---------------------------------------------------------------------------
# Pattern analysis
# ---------------------------------------------------------------------------


def test_analyse_patterns_empty(tmp_path: Path) -> None:
    """Empty corpus → total_lessons=0 and empty collections."""
    engine = _engine(tmp_path)
    summary = engine.analyse_patterns()
    assert summary.total_lessons == 0
    assert summary.by_category == {}
    assert summary.by_sentiment == {}
    assert summary.top_tags == []
    assert summary.most_common_negative_categories == []


def test_analyse_patterns_populated(tmp_path: Path) -> None:
    """Populated corpus → correct counts by category, sentiment, and tags."""
    engine = _populated_engine(tmp_path)
    summary = engine.analyse_patterns()
    assert summary.total_lessons == 6
    # 2 positive, 4 negative
    assert summary.by_sentiment.get("POSITIVE", 0) == 2
    assert summary.by_sentiment.get("NEGATIVE", 0) == 4
    # At least one category entry
    assert len(summary.by_category) > 0
    # Tags should include at least some entries
    assert len(summary.top_tags) > 0


def test_most_common_negative_categories(tmp_path: Path) -> None:
    """most_common_negative_categories identifies categories with most NEGATIVE lessons."""
    engine = _populated_engine(tmp_path)
    summary = engine.analyse_patterns()
    # populated engine has 4 negative lessons
    assert len(summary.most_common_negative_categories) > 0
    # Each entry has category and count keys
    for entry in summary.most_common_negative_categories:
        assert "category" in entry
        assert "count" in entry
        assert entry["count"] > 0


# ---------------------------------------------------------------------------
# Contextual retrieval
# ---------------------------------------------------------------------------


def test_contextual_lessons_prioritises_negative(tmp_path: Path) -> None:
    """NEGATIVE lessons appear before POSITIVE lessons in contextual results."""
    engine = _populated_engine(tmp_path)
    results = engine.get_contextual_lessons(project_type="ICT")
    assert len(results) > 0
    # All returned lessons must be ICT type
    for lesson in results:
        assert lesson.project_type == "ICT"
    # If both positive and negative are present, negatives come first
    sentiments = [r.sentiment for r in results]
    neg_indices = [i for i, s in enumerate(sentiments) if s == LessonSentiment.NEGATIVE]
    pos_indices = [i for i, s in enumerate(sentiments) if s == LessonSentiment.POSITIVE]
    if neg_indices and pos_indices:
        assert max(neg_indices) < min(pos_indices)


def test_contextual_lessons_filters_by_type(tmp_path: Path) -> None:
    """get_contextual_lessons only returns lessons of the matching project_type."""
    engine = _populated_engine(tmp_path)
    results = engine.get_contextual_lessons(project_type="Transformation")
    for lesson in results:
        assert lesson.project_type == "Transformation"


# ---------------------------------------------------------------------------
# Semantic fallback
# ---------------------------------------------------------------------------


def test_semantic_search_fallback(tmp_path: Path) -> None:
    """When sentence-transformers unavailable, search falls back to keyword without error."""
    engine = _populated_engine(tmp_path)
    # The search() method should NEVER raise regardless of whether
    # sentence-transformers is installed — it always falls back.
    response = engine.search("procurement delays")
    assert response.search_method in ("keyword", "semantic")
    assert isinstance(response.results, list)
    assert response.total_in_corpus == 6


@pytest.mark.skipif(
    not SENTENCE_TRANSFORMERS_AVAILABLE,
    reason="sentence-transformers not installed",
)
def test_semantic_search_when_available(tmp_path: Path) -> None:
    """When sentence-transformers is installed, semantic search is used."""
    engine = _populated_engine(tmp_path)
    response = engine.search("stakeholder workshops requirements")
    assert response.search_method == "semantic"
    assert len(response.results) > 0
