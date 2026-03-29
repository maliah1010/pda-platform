"""Shared fixtures for assurance module tests.

Provides in-memory SQLite stores, mock ConfidenceExtractor instances, and
sample review text for P1 (artefact currency), P2 (longitudinal compliance
tracking), P3 (finding analyzer), and P4 (confidence divergence) tests.
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

from pm_data_tools.assurance.currency import ArtefactCurrencyValidator, CurrencyConfig
from pm_data_tools.assurance.divergence import DivergenceConfig, DivergenceMonitor
from pm_data_tools.assurance.lessons import (
    LessonCategory,
    LessonRecord,
    LessonSentiment,
    LessonsKnowledgeEngine,
)
from pm_data_tools.assurance.classifier import (
    ClassificationInput,
    ClassifierConfig,
    ProjectDomainClassifier,
)
from pm_data_tools.assurance.overhead import (
    ActivityType,
    AssuranceActivity,
    AssuranceOverheadOptimiser,
)
from pm_data_tools.assurance.overrides import (
    OverrideDecision,
    OverrideDecisionLogger,
    OverrideOutcome,
    OverrideType,
)
from pm_data_tools.assurance.scheduler import AdaptiveReviewScheduler
from pm_data_tools.assurance.workflows import (
    AssuranceWorkflowEngine,
    WorkflowConfig,
)
from pm_data_tools.db.store import AssuranceStore
from pm_data_tools.schemas.nista.longitudinal import (
    ConfidenceScoreRecord,
    ComplianceThresholdConfig,
    LongitudinalComplianceTracker,
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
# Longitudinal compliance tracker fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def history(store: AssuranceStore) -> LongitudinalComplianceTracker:
    """LongitudinalComplianceTracker backed by the isolated temp store."""
    return LongitudinalComplianceTracker(store=store)


@pytest.fixture()
def history_with_strict_thresholds(store: AssuranceStore) -> LongitudinalComplianceTracker:
    """LongitudinalComplianceTracker with tight thresholds for breach testing."""
    thresholds = ComplianceThresholdConfig(drop_tolerance=3.0, floor=70.0, stagnation_window=2)
    return LongitudinalComplianceTracker(store=store, thresholds=thresholds)


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
# Artefact currency validator fixture (P1)
# ---------------------------------------------------------------------------


@pytest.fixture()
def currency_validator() -> ArtefactCurrencyValidator:
    """ArtefactCurrencyValidator with default config."""
    return ArtefactCurrencyValidator()


# ---------------------------------------------------------------------------
# Adaptive review scheduler fixture (P5)
# ---------------------------------------------------------------------------


@pytest.fixture()
def scheduler(store: AssuranceStore) -> AdaptiveReviewScheduler:
    """AdaptiveReviewScheduler backed by the isolated temp store."""
    return AdaptiveReviewScheduler(store=store)


# ---------------------------------------------------------------------------
# Override decision logger fixtures (P6)
# ---------------------------------------------------------------------------


@pytest.fixture()
def override_logger(store: AssuranceStore) -> OverrideDecisionLogger:
    """OverrideDecisionLogger backed by the isolated temp store."""
    return OverrideDecisionLogger(store=store)


def make_override(
    project_id: str = "PROJ-001",
    override_type: OverrideType = OverrideType.GATE_PROGRESSION,
    decision_date: date | None = None,
    authoriser: str = "Test User",
    rationale: str = "Test rationale.",
    **kwargs: object,
) -> OverrideDecision:
    """Helper to build an OverrideDecision with sensible defaults."""
    return OverrideDecision(
        project_id=project_id,
        override_type=override_type,
        decision_date=decision_date or date.today(),
        authoriser=authoriser,
        rationale=rationale,
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Divergence monitor fixtures (P4)
# ---------------------------------------------------------------------------


@pytest.fixture()
def divergence_monitor(store: AssuranceStore) -> DivergenceMonitor:
    """DivergenceMonitor backed by the isolated temp store."""
    return DivergenceMonitor(store=store)


@pytest.fixture()
def divergence_monitor_strict(store: AssuranceStore) -> DivergenceMonitor:
    """DivergenceMonitor with tight thresholds for signal detection testing."""
    config = DivergenceConfig(
        divergence_threshold=0.10,
        min_consensus=0.75,
        degradation_window=2,
    )
    return DivergenceMonitor(config=config, store=store)


# ---------------------------------------------------------------------------
# Lessons knowledge engine fixtures (P7)
# ---------------------------------------------------------------------------


@pytest.fixture()
def lessons_engine(store: AssuranceStore) -> LessonsKnowledgeEngine:
    """LessonsKnowledgeEngine backed by the isolated temp store."""
    return LessonsKnowledgeEngine(store=store)


def make_lesson(
    project_id: str = "PROJ-001",
    title: str = "Test lesson title",
    description: str = "A description of the lesson learned.",
    category: LessonCategory = LessonCategory.GOVERNANCE,
    sentiment: LessonSentiment = LessonSentiment.NEGATIVE,
    project_type: str | None = "ICT",
    **kwargs: object,
) -> LessonRecord:
    """Helper to build a LessonRecord with sensible defaults."""
    return LessonRecord(
        project_id=project_id,
        title=title,
        description=description,
        category=category,
        sentiment=sentiment,
        project_type=project_type,
        **kwargs,  # type: ignore[arg-type]
    )


@pytest.fixture()
def populated_lessons_engine(store: AssuranceStore) -> LessonsKnowledgeEngine:
    """LessonsKnowledgeEngine pre-loaded with 5 diverse lessons."""
    engine = LessonsKnowledgeEngine(store=store)
    engine.ingest_batch(
        [
            make_lesson(
                title="Early stakeholder engagement prevented scope creep",
                description="Fortnightly workshops from week 2 identified conflicting requirements.",
                category=LessonCategory.STAKEHOLDER,
                sentiment=LessonSentiment.POSITIVE,
                tags=["stakeholders", "scope"],
            ),
            make_lesson(
                title="Delayed procurement caused schedule slip",
                description="Contract award took 14 weeks due to challenge period.",
                category=LessonCategory.COMMERCIAL,
                sentiment=LessonSentiment.NEGATIVE,
                tags=["procurement", "delay"],
            ),
            make_lesson(
                title="Risk register not updated after scope change",
                description="Risk register was not revisited when scope expanded.",
                category=LessonCategory.RISK_MANAGEMENT,
                sentiment=LessonSentiment.NEGATIVE,
                tags=["risk", "scope"],
            ),
            make_lesson(
                title="Benefits owner not appointed early enough",
                description="Benefits owner not named until gate 4.",
                category=LessonCategory.BENEFITS_REALISATION,
                sentiment=LessonSentiment.NEGATIVE,
                tags=["benefits", "ownership"],
            ),
            make_lesson(
                title="Weekly stand-ups improved delivery pace",
                description="Short syncs replaced long meetings and improved velocity.",
                category=LessonCategory.GOVERNANCE,
                sentiment=LessonSentiment.POSITIVE,
                tags=["meetings", "velocity"],
            ),
        ]
    )
    return engine


# ---------------------------------------------------------------------------
# Workflow engine fixtures (P9)
# ---------------------------------------------------------------------------


@pytest.fixture()
def workflow_engine(store: AssuranceStore) -> AssuranceWorkflowEngine:
    """AssuranceWorkflowEngine backed by the isolated temp store."""
    return AssuranceWorkflowEngine(store=store)


# ---------------------------------------------------------------------------
# Domain classifier fixtures (P10)
# ---------------------------------------------------------------------------


@pytest.fixture()
def domain_classifier(store: AssuranceStore) -> ProjectDomainClassifier:
    """ProjectDomainClassifier backed by the isolated temp store."""
    return ProjectDomainClassifier(store=store)


def make_classification_input(
    project_id: str = "PROJ-001",
    technical_complexity: float | None = 0.3,
    stakeholder_complexity: float | None = 0.3,
    requirement_clarity: float | None = 0.7,
    delivery_track_record: float | None = 0.7,
    organisational_change: float | None = 0.2,
    regulatory_exposure: float | None = 0.2,
    dependency_count: float | None = 0.2,
) -> ClassificationInput:
    """Helper to build a ClassificationInput with CLEAR-domain defaults."""
    return ClassificationInput(
        project_id=project_id,
        technical_complexity=technical_complexity,
        stakeholder_complexity=stakeholder_complexity,
        requirement_clarity=requirement_clarity,
        delivery_track_record=delivery_track_record,
        organisational_change=organisational_change,
        regulatory_exposure=regulatory_exposure,
        dependency_count=dependency_count,
    )


# ---------------------------------------------------------------------------
# Overhead optimiser fixtures (P8)
# ---------------------------------------------------------------------------


@pytest.fixture()
def overhead_optimiser(store: AssuranceStore) -> AssuranceOverheadOptimiser:
    """AssuranceOverheadOptimiser backed by the isolated temp store."""
    return AssuranceOverheadOptimiser(store=store)


def make_activity(
    project_id: str = "PROJ-001",
    activity_type: ActivityType = ActivityType.GATE_REVIEW,
    description: str = "Test activity",
    activity_date: "date | None" = None,
    effort_hours: float = 8.0,
    participants: int = 2,
    findings_count: int = 2,
    **kwargs: object,
) -> AssuranceActivity:
    """Helper to build an AssuranceActivity with sensible defaults."""
    from datetime import date

    return AssuranceActivity(
        project_id=project_id,
        activity_type=activity_type,
        description=description,
        date=activity_date or date(2026, 3, 1),
        effort_hours=effort_hours,
        participants=participants,
        findings_count=findings_count,
        **kwargs,  # type: ignore[arg-type]
    )


@pytest.fixture()
def populated_overhead_optimiser(store: AssuranceStore) -> AssuranceOverheadOptimiser:
    """AssuranceOverheadOptimiser pre-loaded with 7 diverse activities."""
    from datetime import date, timedelta

    opt = AssuranceOverheadOptimiser(store=store)
    base = date(2026, 1, 1)
    activities = [
        make_activity(
            activity_type=ActivityType.GATE_REVIEW,
            activity_date=base,
            effort_hours=16.0,
            participants=4,
            findings_count=3,
            confidence_before=65.0,
            confidence_after=72.0,
        ),
        make_activity(
            activity_type=ActivityType.DOCUMENT_REVIEW,
            activity_date=base + timedelta(days=7),
            effort_hours=4.0,
            findings_count=1,
        ),
        make_activity(
            activity_type=ActivityType.COMPLIANCE_CHECK,
            activity_date=base + timedelta(days=14),
            effort_hours=6.0,
            findings_count=0,
        ),
        make_activity(
            activity_type=ActivityType.RISK_ASSESSMENT,
            activity_date=base + timedelta(days=21),
            effort_hours=8.0,
            findings_count=2,
        ),
        make_activity(
            activity_type=ActivityType.STAKEHOLDER_REVIEW,
            activity_date=base + timedelta(days=28),
            effort_hours=3.0,
            participants=5,
            findings_count=1,
        ),
        make_activity(
            activity_type=ActivityType.GATE_REVIEW,
            activity_date=base + timedelta(days=90),
            effort_hours=16.0,
            participants=4,
            findings_count=2,
            confidence_before=75.0,
            confidence_after=80.0,
        ),
        make_activity(
            activity_type=ActivityType.COMPLIANCE_CHECK,
            activity_date=base + timedelta(days=94),
            effort_hours=6.0,
            findings_count=0,
        ),
    ]
    for a in activities:
        opt.log_activity(a)
    return opt


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
