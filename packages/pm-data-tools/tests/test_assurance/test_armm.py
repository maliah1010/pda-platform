"""Tests for the ARMM Agent Readiness Maturity Model (P12)."""

from __future__ import annotations

from pm_data_tools.assurance.armm import (
    DIMENSION_TOPICS,
    TOPIC_CRITERIA_COUNT,
    TOPIC_DIMENSION,
    ARMMConfig,
    ARMMDimension,
    ARMMScorer,
    ARMMTopic,
    CriterionResult,
    MaturityLevel,
    _criterion_to_topic,
    _score_to_level,
)
from pm_data_tools.db.store import AssuranceStore

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_all_criteria(pct: float) -> list[CriterionResult]:
    """Return criterion results for all 251 criteria with the given met rate (0–1)."""
    results: list[CriterionResult] = []
    for topic in ARMMTopic:
        n = TOPIC_CRITERIA_COUNT[topic]
        for i in range(1, n + 1):
            met = (i / n) <= pct
            results.append(
                CriterionResult(
                    criterion_id=f"{topic.value}-{i}",
                    met=met,
                    evidence_ref=f"DOC-{topic.value}-{i}" if met else None,
                )
            )
    return results


def _make_topic_criteria(topic: ARMMTopic, pct: float) -> list[CriterionResult]:
    """Return criterion results for a single topic at the given met rate."""
    n = TOPIC_CRITERIA_COUNT[topic]
    return [
        CriterionResult(
            criterion_id=f"{topic.value}-{i}",
            met=(i / n) <= pct,
        )
        for i in range(1, n + 1)
    ]


# ---------------------------------------------------------------------------
# 1. Criterion-to-topic resolution
# ---------------------------------------------------------------------------


def test_criterion_to_topic_valid() -> None:
    """Standard criterion IDs resolve to the correct topic."""
    assert _criterion_to_topic("TC-IV-1") == ARMMTopic.TC_IV
    assert _criterion_to_topic("OR-BC-3") == ARMMTopic.OR_BC
    assert _criterion_to_topic("GA-PF-8") == ARMMTopic.GA_PF
    assert _criterion_to_topic("CC-SK-5") == ARMMTopic.CC_SK


def test_criterion_to_topic_unknown() -> None:
    """Unknown criterion IDs return None."""
    assert _criterion_to_topic("XX-ZZ-1") is None
    assert _criterion_to_topic("bad") is None
    assert _criterion_to_topic("") is None


# ---------------------------------------------------------------------------
# 2. Score-to-level threshold mapping
# ---------------------------------------------------------------------------


def test_score_to_level_boundaries() -> None:
    """Level thresholds map correctly to MaturityLevel enum values."""
    assert _score_to_level(0.0) == MaturityLevel.EXPERIMENTING
    assert _score_to_level(24.9) == MaturityLevel.EXPERIMENTING
    assert _score_to_level(25.0) == MaturityLevel.SUPERVISED
    assert _score_to_level(49.9) == MaturityLevel.SUPERVISED
    assert _score_to_level(50.0) == MaturityLevel.RELIABLE
    assert _score_to_level(74.9) == MaturityLevel.RELIABLE
    assert _score_to_level(75.0) == MaturityLevel.RESILIENT
    assert _score_to_level(89.9) == MaturityLevel.RESILIENT
    assert _score_to_level(90.0) == MaturityLevel.MISSION_CRITICAL
    assert _score_to_level(100.0) == MaturityLevel.MISSION_CRITICAL


# ---------------------------------------------------------------------------
# 3. Topic and dimension structure
# ---------------------------------------------------------------------------


def test_total_criteria_count() -> None:
    """Sum of criteria across all 28 topics equals 251."""
    total = sum(TOPIC_CRITERIA_COUNT.values())
    assert total == 251


def test_topic_dimension_coverage() -> None:
    """Every ARMMTopic maps to a dimension and every dimension has exactly 7 topics."""
    for dim in ARMMDimension:
        assert len(DIMENSION_TOPICS[dim]) == 7
    for topic in ARMMTopic:
        assert topic in TOPIC_DIMENSION


def test_dimension_topic_consistency() -> None:
    """DIMENSION_TOPICS and TOPIC_DIMENSION are consistent inverses."""
    for dim, topics in DIMENSION_TOPICS.items():
        for topic in topics:
            assert TOPIC_DIMENSION[topic] == dim


# ---------------------------------------------------------------------------
# 4. Basic assessment — zero criteria
# ---------------------------------------------------------------------------


def test_empty_assessment_gives_experimenting(tmp_path) -> None:
    """Assessment with no criteria gives EXPERIMENTING level."""
    store = AssuranceStore(db_path=tmp_path / "test.db")
    scorer = ARMMScorer(store=store)
    assessment = scorer.assess(
        project_id="PROJ-001",
        criterion_results=[],
        assessed_by="Tester",
    )
    assert assessment.overall_level == MaturityLevel.EXPERIMENTING
    assert assessment.overall_score_pct == 0.0
    assert assessment.criteria_total == 0
    assert assessment.criteria_met == 0


# ---------------------------------------------------------------------------
# 5. Weakest-link scoring — topic level
# ---------------------------------------------------------------------------


def test_single_topic_at_50pct_gives_reliable(tmp_path) -> None:
    """50% of criteria met for one topic → RELIABLE level for that topic."""
    store = AssuranceStore(db_path=tmp_path / "test.db")
    scorer = ARMMScorer(store=store)
    results = _make_topic_criteria(ARMMTopic.TC_IV, 0.50)
    assessment = scorer.assess("P", results)
    topic_result = assessment.topic_results["TC-IV"]
    assert topic_result.level == MaturityLevel.RELIABLE


def test_single_topic_at_24pct_gives_experimenting(tmp_path) -> None:
    """24% criteria met → EXPERIMENTING."""
    store = AssuranceStore(db_path=tmp_path / "test.db")
    scorer = ARMMScorer(store=store)
    results = _make_topic_criteria(ARMMTopic.OR_BC, 0.24)
    assessment = scorer.assess("P", results)
    assert assessment.topic_results["OR-BC"].level == MaturityLevel.EXPERIMENTING


# ---------------------------------------------------------------------------
# 6. Weakest-link scoring — dimension level
# ---------------------------------------------------------------------------


def test_dimension_level_is_min_of_topics(tmp_path) -> None:
    """Dimension level equals the lowest topic level within that dimension."""
    store = AssuranceStore(db_path=tmp_path / "test.db")
    scorer = ARMMScorer(store=store)

    # All TC topics at 80% (RESILIENT) except TC-SC at 10% (EXPERIMENTING)
    results: list[CriterionResult] = []
    for topic in DIMENSION_TOPICS[ARMMDimension.TECHNICAL_CONTROLS]:
        pct = 0.10 if topic == ARMMTopic.TC_SC else 0.80
        results.extend(_make_topic_criteria(topic, pct))

    assessment = scorer.assess("P", results)
    tc_result = assessment.dimension_results["TC"]
    assert tc_result.level == MaturityLevel.EXPERIMENTING
    assert tc_result.blocking_topic == "TC-SC"


# ---------------------------------------------------------------------------
# 7. Overall weakest-link
# ---------------------------------------------------------------------------


def test_overall_level_is_min_of_dimensions(tmp_path) -> None:
    """Overall level equals the lowest dimension level."""
    store = AssuranceStore(db_path=tmp_path / "test.db")
    scorer = ARMMScorer(store=store)

    # All criteria at 60% (RELIABLE) except all OR topics at 10% (EXPERIMENTING)
    results: list[CriterionResult] = []
    for topic in ARMMTopic:
        dim = TOPIC_DIMENSION[topic]
        pct = 0.10 if dim == ARMMDimension.OPERATIONAL_RESILIENCE else 0.60
        results.extend(_make_topic_criteria(topic, pct))

    assessment = scorer.assess("PROJ-001", results)
    assert assessment.overall_level == MaturityLevel.EXPERIMENTING


def test_all_criteria_met_gives_mission_critical(tmp_path) -> None:
    """All 251 criteria met (100%) → MISSION_CRITICAL overall."""
    store = AssuranceStore(db_path=tmp_path / "test.db")
    scorer = ARMMScorer(store=store)
    # Use explicit met=True for all so rounding doesn't affect the result
    results = [
        CriterionResult(criterion_id=f"{topic.value}-{i}", met=True)
        for topic in ARMMTopic
        for i in range(1, TOPIC_CRITERIA_COUNT[topic] + 1)
    ]
    assessment = scorer.assess("P", results)
    assert assessment.overall_level == MaturityLevel.MISSION_CRITICAL
    assert assessment.overall_score_pct == 100.0


def test_majority_met_gives_reliable(tmp_path) -> None:
    """≥58% criteria met across all topics → RELIABLE overall.

    Using 0.58 as the threshold guarantees ≥50% even for topics with n=7
    criteria (4/7 = 57.1% ≥ 50%) — the smallest step above 50% for the
    smallest topics in the ARMM schema.
    """
    store = AssuranceStore(db_path=tmp_path / "test.db")
    scorer = ARMMScorer(store=store)
    results = _make_all_criteria(0.58)
    assessment = scorer.assess("P", results)
    assert assessment.overall_level == MaturityLevel.RELIABLE


# ---------------------------------------------------------------------------
# 8. Persistence and retrieval
# ---------------------------------------------------------------------------


def test_assessment_persisted_and_retrievable(tmp_path) -> None:
    """Assessment is stored and the report reflects it correctly."""
    store = AssuranceStore(db_path=tmp_path / "test.db")
    scorer = ARMMScorer(store=store)
    results = _make_all_criteria(0.60)
    assessment = scorer.assess("PROJ-001", results, assessed_by="IPA Reviewer")

    report = scorer.get_report("PROJ-001")
    assert report.latest_assessment_id == assessment.id
    assert report.overall_level == assessment.overall_level
    assert report.criteria_total == 251
    assert report.criteria_met == assessment.criteria_met
    assert len(report.dimension_levels) == 4
    assert len(report.topic_levels) == 28


def test_report_for_unknown_project_is_empty(tmp_path) -> None:
    """Report for a project with no assessments has no assessment ID."""
    store = AssuranceStore(db_path=tmp_path / "test.db")
    scorer = ARMMScorer(store=store)
    report = scorer.get_report("NO-SUCH-PROJECT")
    assert report.latest_assessment_id is None
    assert report.overall_level == MaturityLevel.EXPERIMENTING


# ---------------------------------------------------------------------------
# 9. Multiple assessments — trend detection
# ---------------------------------------------------------------------------


def test_maturity_trend_improving(tmp_path) -> None:
    """Two assessments with improving score → 'improving' trend."""
    store = AssuranceStore(db_path=tmp_path / "test.db")
    scorer = ARMMScorer(store=store)
    scorer.assess("P", _make_all_criteria(0.30))
    scorer.assess("P", _make_all_criteria(0.70))  # > 3% improvement
    report = scorer.get_report("P")
    assert report.maturity_trend == "improving"


def test_maturity_trend_stable(tmp_path) -> None:
    """Two assessments with nearly identical score → 'stable' trend."""
    store = AssuranceStore(db_path=tmp_path / "test.db")
    scorer = ARMMScorer(store=store)
    scorer.assess("P", _make_all_criteria(0.50))
    scorer.assess("P", _make_all_criteria(0.505))
    report = scorer.get_report("P")
    assert report.maturity_trend == "stable"


# ---------------------------------------------------------------------------
# 10. Portfolio overview
# ---------------------------------------------------------------------------


def test_portfolio_overview_multiple_projects(tmp_path) -> None:
    """Portfolio overview returns one report per project."""
    store = AssuranceStore(db_path=tmp_path / "test.db")
    scorer = ARMMScorer(store=store)
    scorer.assess("PROJ-A", _make_all_criteria(0.80))
    scorer.assess("PROJ-B", _make_all_criteria(0.30))
    scorer.assess("PROJ-C", _make_all_criteria(0.50))

    reports = scorer.get_portfolio_overview()
    project_ids = {r.project_id for r in reports}
    assert project_ids == {"PROJ-A", "PROJ-B", "PROJ-C"}
    levels = {r.project_id: int(r.overall_level) for r in reports}
    assert levels["PROJ-A"] > levels["PROJ-B"]  # PROJ-A should be higher


# ---------------------------------------------------------------------------
# 11. Criterion-level drill-through persistence
# ---------------------------------------------------------------------------


def test_criterion_results_persisted(tmp_path) -> None:
    """Criterion results can be retrieved from the store after assessment."""
    store = AssuranceStore(db_path=tmp_path / "test.db")
    scorer = ARMMScorer(store=store)
    results = _make_topic_criteria(ARMMTopic.TC_IV, 0.60)
    assessment = scorer.assess("PROJ-001", results)

    # Persist criterion results manually (as the generator does)
    store.insert_armm_criterion_results(
        assessment_id=assessment.id,
        project_id="PROJ-001",
        results=[
            {
                "criterion_id": r.criterion_id,
                "topic_code": "-".join(r.criterion_id.split("-")[:2]),
                "dimension_code": r.criterion_id.split("-")[0],
                "met": r.met,
                "evidence_ref": r.evidence_ref or "",
                "notes": "",
            }
            for r in results
        ],
    )

    rows = store.get_armm_criterion_results(assessment_id=assessment.id)
    assert len(rows) == TOPIC_CRITERIA_COUNT[ARMMTopic.TC_IV]
    met_count = sum(1 for r in rows if r["met"])
    assert met_count == assessment.topic_results["TC-IV"].criteria_met


# ---------------------------------------------------------------------------
# 12. ARMMConfig — custom thresholds respected
# ---------------------------------------------------------------------------


def test_custom_threshold_config(tmp_path) -> None:
    """Custom level thresholds are applied in scoring."""
    # Raise SUPERVISED threshold to 40% — so 30% met should be EXPERIMENTING
    config = ARMMConfig(level_thresholds={0: 0.0, 1: 40.0, 2: 60.0, 3: 80.0, 4: 95.0})
    store = AssuranceStore(db_path=tmp_path / "test.db")
    scorer = ARMMScorer(store=store, config=config)
    results = _make_all_criteria(0.30)
    assessment = scorer.assess("P", results)
    # With default thresholds 30% → SUPERVISED; with custom → EXPERIMENTING
    assert assessment.overall_level == MaturityLevel.EXPERIMENTING
