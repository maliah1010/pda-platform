"""Tests for P8 — Assurance Overhead Optimiser.

Covers activity logging, retrieval, duplicate detection, efficiency
classification, recommendation generation, and full analysis.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from pm_data_tools.assurance.overhead import (
    ActivityType,
    AssuranceActivity,
    AssuranceOverheadOptimiser,
    EfficiencyRating,
)
from pm_data_tools.db.store import AssuranceStore

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_activity(
    project_id: str = "PROJ-001",
    activity_type: ActivityType = ActivityType.GATE_REVIEW,
    description: str = "Test activity",
    activity_date: date | None = None,
    effort_hours: float = 8.0,
    participants: int = 2,
    artefacts_reviewed: list[str] | None = None,
    findings_count: int = 2,
    confidence_before: float | None = None,
    confidence_after: float | None = None,
) -> AssuranceActivity:
    """Build an AssuranceActivity with sensible defaults."""
    return AssuranceActivity(
        project_id=project_id,
        activity_type=activity_type,
        description=description,
        date=activity_date or date(2026, 3, 1),
        effort_hours=effort_hours,
        participants=participants,
        artefacts_reviewed=artefacts_reviewed or [],
        findings_count=findings_count,
        confidence_before=confidence_before,
        confidence_after=confidence_after,
    )


def _optimiser(tmp_path: Path) -> AssuranceOverheadOptimiser:
    store = AssuranceStore(db_path=tmp_path / "store.db")
    return AssuranceOverheadOptimiser(store=store)


def _populated_optimiser(tmp_path: Path) -> AssuranceOverheadOptimiser:
    """Return an optimiser pre-loaded with 7 diverse activities."""
    opt = _optimiser(tmp_path)
    base = date(2026, 1, 1)
    activities = [
        make_activity(
            activity_type=ActivityType.GATE_REVIEW,
            activity_date=base,
            effort_hours=16.0,
            participants=4,
            artefacts_reviewed=["risk-register-v3", "benefits-profile-v2"],
            findings_count=3,
            confidence_before=65.0,
            confidence_after=72.0,
        ),
        make_activity(
            activity_type=ActivityType.DOCUMENT_REVIEW,
            activity_date=base + timedelta(days=7),
            effort_hours=4.0,
            participants=2,
            artefacts_reviewed=["project-plan-v2"],
            findings_count=1,
            confidence_before=72.0,
            confidence_after=75.0,
        ),
        make_activity(
            activity_type=ActivityType.COMPLIANCE_CHECK,
            activity_date=base + timedelta(days=14),
            effort_hours=6.0,
            participants=2,
            findings_count=0,
        ),
        make_activity(
            activity_type=ActivityType.RISK_ASSESSMENT,
            activity_date=base + timedelta(days=21),
            effort_hours=8.0,
            participants=3,
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
            artefacts_reviewed=["risk-register-v4"],
            findings_count=2,
            confidence_before=75.0,
            confidence_after=80.0,
        ),
        make_activity(
            activity_type=ActivityType.COMPLIANCE_CHECK,
            activity_date=base + timedelta(days=94),
            effort_hours=6.0,
            participants=2,
            findings_count=0,
        ),
    ]
    for a in activities:
        opt.log_activity(a)
    return opt


# ---------------------------------------------------------------------------
# Logging and retrieval
# ---------------------------------------------------------------------------


def test_log_activity_persists(tmp_path: Path) -> None:
    """Log and retrieve an activity; verify all fields are preserved."""
    opt = _optimiser(tmp_path)
    activity = make_activity(
        project_id="PROJ-X",
        activity_type=ActivityType.AUDIT,
        description="External audit",
        activity_date=date(2026, 2, 15),
        effort_hours=24.0,
        participants=3,
        artefacts_reviewed=["doc-1", "doc-2"],
        findings_count=5,
        confidence_before=60.0,
        confidence_after=70.0,
    )
    opt.log_activity(activity)

    retrieved = opt.get_activities("PROJ-X")
    assert len(retrieved) == 1
    r = retrieved[0]
    assert r.activity_type == ActivityType.AUDIT
    assert r.description == "External audit"
    assert r.date == date(2026, 2, 15)
    assert r.effort_hours == 24.0
    assert r.participants == 3
    assert r.artefacts_reviewed == ["doc-1", "doc-2"]
    assert r.findings_count == 5
    assert r.confidence_before == 60.0
    assert r.confidence_after == 70.0


def test_log_activity_generates_id(tmp_path: Path) -> None:
    """Auto-generated id is a UUID4 string."""
    opt = _optimiser(tmp_path)
    activity = make_activity()
    logged = opt.log_activity(activity)
    assert len(logged.id) == 36
    assert logged.id.count("-") == 4


def test_get_activities_unfiltered(tmp_path: Path) -> None:
    """get_activities with no type filter returns all activities."""
    opt = _populated_optimiser(tmp_path)
    activities = opt.get_activities("PROJ-001")
    assert len(activities) == 7


def test_get_activities_by_type(tmp_path: Path) -> None:
    """get_activities filtered by type returns only matching activities."""
    opt = _populated_optimiser(tmp_path)
    gate_reviews = opt.get_activities("PROJ-001", activity_type=ActivityType.GATE_REVIEW)
    assert len(gate_reviews) == 2
    for a in gate_reviews:
        assert a.activity_type == ActivityType.GATE_REVIEW


# ---------------------------------------------------------------------------
# Duplicate detection
# ---------------------------------------------------------------------------


def test_detect_duplicates_same_artefact(tmp_path: Path) -> None:
    """Two activities reviewing the same artefact within 14 days → duplicate."""
    opt = _optimiser(tmp_path)
    opt.log_activity(make_activity(
        activity_date=date(2026, 3, 1),
        artefacts_reviewed=["risk-register-v3"],
    ))
    opt.log_activity(make_activity(
        activity_date=date(2026, 3, 10),  # 9 days later
        artefacts_reviewed=["risk-register-v3"],
    ))
    dupes = opt.detect_duplicates("PROJ-001")
    assert len(dupes) == 1
    assert dupes[0].overlap_type == "same_artefact"
    assert "risk-register-v3" in dupes[0].detail


def test_detect_duplicates_same_type_same_week(tmp_path: Path) -> None:
    """Two activities of the same type within 7 days → duplicate."""
    opt = _optimiser(tmp_path)
    opt.log_activity(make_activity(
        activity_type=ActivityType.COMPLIANCE_CHECK,
        activity_date=date(2026, 3, 1),
    ))
    opt.log_activity(make_activity(
        activity_type=ActivityType.COMPLIANCE_CHECK,
        activity_date=date(2026, 3, 5),  # 4 days later
    ))
    dupes = opt.detect_duplicates("PROJ-001")
    assert len(dupes) == 1
    assert dupes[0].overlap_type == "same_type_same_week"


def test_detect_duplicates_no_findings_repeat(tmp_path: Path) -> None:
    """Same type, both 0 findings, within 30 days → duplicate."""
    opt = _optimiser(tmp_path)
    opt.log_activity(make_activity(
        activity_type=ActivityType.DOCUMENT_REVIEW,
        activity_date=date(2026, 3, 1),
        findings_count=0,
    ))
    opt.log_activity(make_activity(
        activity_type=ActivityType.DOCUMENT_REVIEW,
        activity_date=date(2026, 3, 20),  # 19 days later
        findings_count=0,
    ))
    dupes = opt.detect_duplicates("PROJ-001")
    assert len(dupes) == 1
    assert dupes[0].overlap_type == "no_findings_repeat"


def test_no_duplicates_when_far_apart(tmp_path: Path) -> None:
    """Same artefact but 30+ days apart → no duplicate flagged."""
    opt = _optimiser(tmp_path)
    opt.log_activity(make_activity(
        activity_date=date(2026, 1, 1),
        artefacts_reviewed=["risk-register-v3"],
    ))
    opt.log_activity(make_activity(
        activity_date=date(2026, 3, 1),  # 59 days later
        artefacts_reviewed=["risk-register-v3"],
    ))
    dupes = opt.detect_duplicates("PROJ-001")
    assert len(dupes) == 0


# ---------------------------------------------------------------------------
# Efficiency rating
# ---------------------------------------------------------------------------


def test_efficiency_optimal(tmp_path: Path) -> None:
    """Good finding rate and reasonable effort → OPTIMAL."""
    opt = _optimiser(tmp_path)
    # 4 activities, all with findings, moderate hours
    for i in range(4):
        opt.log_activity(make_activity(
            activity_date=date(2026, 1, 1) + timedelta(days=i * 30),
            effort_hours=10.0,
            findings_count=2,
        ))
    assert opt.compute_efficiency("PROJ-001") == EfficiencyRating.OPTIMAL


def test_efficiency_under_invested(tmp_path: Path) -> None:
    """Very low total effort and no confidence lift → UNDER_INVESTED."""
    opt = _optimiser(tmp_path)
    opt.log_activity(make_activity(effort_hours=2.0, findings_count=0))
    assert opt.compute_efficiency("PROJ-001") == EfficiencyRating.UNDER_INVESTED


def test_efficiency_over_invested(tmp_path: Path) -> None:
    """High effort but very low finding rate → OVER_INVESTED."""
    opt = _optimiser(tmp_path)
    # 6 activities, only 1 with findings, high total hours
    for i in range(5):
        opt.log_activity(make_activity(
            activity_date=date(2026, 1, 1) + timedelta(days=i * 40),
            effort_hours=12.0,
            findings_count=0,
        ))
    opt.log_activity(make_activity(
        activity_date=date(2026, 7, 1),
        effort_hours=12.0,
        findings_count=3,
    ))
    # total_hours = 72 > 40; finding_rate = 1/6 ≈ 0.17 < 0.20
    assert opt.compute_efficiency("PROJ-001") == EfficiencyRating.OVER_INVESTED


def test_efficiency_misallocated(tmp_path: Path) -> None:
    """High duplicate ratio → MISALLOCATED."""
    opt = _optimiser(tmp_path)
    base = date(2026, 1, 1)
    # Create 3 activities with same artefact within 14 days (2 duplicates out of 3 total > 30%)
    # Activity 1: base
    opt.log_activity(make_activity(
        activity_date=base,
        effort_hours=15.0,
        findings_count=3,
        artefacts_reviewed=["doc-a"],
    ))
    # Activity 2: 5 days later, same artefact → duplicate #1
    opt.log_activity(make_activity(
        activity_date=base + timedelta(days=5),
        effort_hours=15.0,
        findings_count=3,
        artefacts_reviewed=["doc-a"],
    ))
    # Activity 3: 10 days later, same artefact → duplicate #2
    opt.log_activity(make_activity(
        activity_date=base + timedelta(days=10),
        effort_hours=15.0,
        findings_count=3,
        artefacts_reviewed=["doc-a"],
    ))
    # 2 duplicates out of 3 activities = 67% > 30% → MISALLOCATED
    assert opt.compute_efficiency("PROJ-001") == EfficiencyRating.MISALLOCATED


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------


def test_recommendations_for_zero_findings(tmp_path: Path) -> None:
    """Activity type with no findings generates a frequency-reduction suggestion."""
    opt = _optimiser(tmp_path)
    for i in range(3):
        opt.log_activity(make_activity(
            activity_type=ActivityType.COMPLIANCE_CHECK,
            activity_date=date(2026, 1, 1) + timedelta(days=i * 45),
            findings_count=0,
        ))
    recs = opt.generate_recommendations("PROJ-001")
    assert any("COMPLIANCE_CHECK" in r for r in recs)
    assert any("no findings" in r.lower() for r in recs)


def test_recommendations_for_duplicates(tmp_path: Path) -> None:
    """Detected duplicates trigger a consolidation recommendation."""
    opt = _optimiser(tmp_path)
    opt.log_activity(make_activity(
        activity_date=date(2026, 3, 1),
        artefacts_reviewed=["risk-register-v3"],
    ))
    opt.log_activity(make_activity(
        activity_date=date(2026, 3, 5),
        artefacts_reviewed=["risk-register-v3"],
    ))
    recs = opt.generate_recommendations("PROJ-001")
    assert any("consolidat" in r.lower() for r in recs)


def test_recommendations_for_effort_concentration(tmp_path: Path) -> None:
    """When >60% of effort is in one type, a redistribution recommendation is generated."""
    opt = _optimiser(tmp_path)
    # 3 gate reviews dominate effort
    for i in range(3):
        opt.log_activity(make_activity(
            activity_type=ActivityType.GATE_REVIEW,
            activity_date=date(2026, 1, 1) + timedelta(days=i * 60),
            effort_hours=30.0,
            findings_count=2,
        ))
    # 1 small compliance check
    opt.log_activity(make_activity(
        activity_type=ActivityType.COMPLIANCE_CHECK,
        activity_date=date(2026, 6, 1),
        effort_hours=2.0,
        findings_count=1,
    ))
    recs = opt.generate_recommendations("PROJ-001")
    assert any("GATE_REVIEW" in r for r in recs)
    assert any("redistribute" in r.lower() for r in recs)


# ---------------------------------------------------------------------------
# Full analysis
# ---------------------------------------------------------------------------


def test_analyse_complete(tmp_path: Path) -> None:
    """Full analysis returns all expected fields populated."""
    opt = _populated_optimiser(tmp_path)
    analysis = opt.analyse("PROJ-001")

    assert analysis.project_id == "PROJ-001"
    assert analysis.total_activities == 7
    assert analysis.total_effort_hours > 0
    assert analysis.total_participants_hours > 0
    assert len(analysis.effort_by_type) > 0
    assert analysis.activities_with_findings + analysis.activities_without_findings == 7
    assert 0.0 <= analysis.finding_rate <= 1.0
    assert analysis.efficiency_rating in EfficiencyRating
    assert isinstance(analysis.recommendations, list)
    assert isinstance(analysis.message, str)


def test_analyse_empty_project(tmp_path: Path) -> None:
    """No activities → UNDER_INVESTED, sensible defaults."""
    opt = _optimiser(tmp_path)
    analysis = opt.analyse("EMPTY-PROJ")

    assert analysis.total_activities == 0
    assert analysis.total_effort_hours == 0.0
    assert analysis.finding_rate == 0.0
    assert analysis.avg_confidence_lift is None
    assert analysis.efficiency_rating == EfficiencyRating.UNDER_INVESTED
    assert len(analysis.recommendations) > 0


def test_confidence_lift_calculation(tmp_path: Path) -> None:
    """avg_confidence_lift is correct average of (after - before)."""
    opt = _optimiser(tmp_path)
    # lift 1: 80 - 70 = 10
    opt.log_activity(make_activity(
        confidence_before=70.0,
        confidence_after=80.0,
        activity_date=date(2026, 1, 1),
    ))
    # lift 2: 75 - 65 = 10
    opt.log_activity(make_activity(
        confidence_before=65.0,
        confidence_after=75.0,
        activity_date=date(2026, 2, 1),
    ))
    analysis = opt.analyse("PROJ-001")
    assert analysis.avg_confidence_lift == pytest.approx(10.0)


def test_confidence_lift_missing_data(tmp_path: Path) -> None:
    """Activities without before/after scores → avg_confidence_lift is None."""
    opt = _optimiser(tmp_path)
    opt.log_activity(make_activity(
        confidence_before=None,
        confidence_after=None,
        effort_hours=20.0,
        findings_count=3,
        activity_date=date(2026, 1, 1),
    ))
    analysis = opt.analyse("PROJ-001")
    assert analysis.avg_confidence_lift is None


def test_analysis_persistence(tmp_path: Path) -> None:
    """Analysis is persisted to the store and retrievable."""
    store = AssuranceStore(db_path=tmp_path / "store.db")
    opt = AssuranceOverheadOptimiser(store=store)
    opt.log_activity(make_activity())
    opt.analyse("PROJ-001")

    history = store.get_overhead_history("PROJ-001")
    assert len(history) == 1
    stored = json.loads(history[0]["analysis_json"])
    assert stored["project_id"] == "PROJ-001"
    assert stored["total_activities"] == 1
