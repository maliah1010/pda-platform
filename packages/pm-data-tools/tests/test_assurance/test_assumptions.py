"""Tests for the Assumption Drift Tracker (P11)."""

from __future__ import annotations

from datetime import date, timedelta

from conftest import make_assumption
from pm_data_tools.assurance.assumptions import (
    Assumption,
    AssumptionCategory,
    AssumptionConfig,
    AssumptionHealthReport,
    AssumptionTracker,
    DriftSeverity,
)

# ---------------------------------------------------------------------------
# 1. Ingest and retrieve
# ---------------------------------------------------------------------------


def test_ingest_assumption(assumption_tracker: AssumptionTracker) -> None:
    """Persisted assumption can be retrieved with all fields intact."""
    a = make_assumption(project_id="PROJ-001", text="Test assumption", baseline_value=100.0, unit="GBP")
    assumption_tracker.ingest(a)
    results = assumption_tracker.get_assumptions("PROJ-001")
    assert len(results) == 1
    r = results[0]
    assert r.id == a.id
    assert r.project_id == "PROJ-001"
    assert r.text == "Test assumption"
    assert r.baseline_value == 100.0
    assert r.unit == "GBP"


def test_ingest_batch(assumption_tracker: AssumptionTracker) -> None:
    """Multiple assumptions ingested; correct count returned."""
    assumptions = [make_assumption(text=f"Assumption {i}") for i in range(5)]
    count = assumption_tracker.ingest_batch(assumptions)
    assert count == 5
    assert len(assumption_tracker.get_assumptions("PROJ-001")) == 5


def test_ingest_generates_id(assumption_tracker: AssumptionTracker) -> None:
    """UUID4 is auto-generated when id is not explicitly set."""
    a = make_assumption()
    assert len(a.id) == 36  # UUID4 length
    assert "-" in a.id


def test_get_assumptions_by_category(assumption_tracker: AssumptionTracker) -> None:
    """Filter by category returns only matching assumptions."""
    assumption_tracker.ingest(make_assumption(category=AssumptionCategory.COST, text="Cost A"))
    assumption_tracker.ingest(make_assumption(category=AssumptionCategory.COST, text="Cost B"))
    assumption_tracker.ingest(make_assumption(category=AssumptionCategory.SCHEDULE, text="Schedule A"))

    cost_only = assumption_tracker.get_assumptions("PROJ-001", category=AssumptionCategory.COST)
    assert len(cost_only) == 2
    assert all(a.category == AssumptionCategory.COST for a in cost_only)


# ---------------------------------------------------------------------------
# 5–6. update_value
# ---------------------------------------------------------------------------


def test_update_value_records_validation(assumption_tracker: AssumptionTracker) -> None:
    """update_value creates a validation record in the store."""
    a = make_assumption(baseline_value=100.0)
    assumption_tracker.ingest(a)
    assumption_tracker.update_value(a.id, new_value=110.0)

    history = assumption_tracker.get_validation_history(a.id)
    assert len(history) == 1
    assert history[0].new_value == 110.0
    assert history[0].assumption_id == a.id


def test_update_value_computes_drift(assumption_tracker: AssumptionTracker) -> None:
    """drift_pct computed correctly: abs((110-100)/100)*100 = 10.0."""
    a = make_assumption(baseline_value=100.0)
    assumption_tracker.ingest(a)
    validation = assumption_tracker.update_value(a.id, new_value=110.0)
    assert abs(validation.drift_pct - 10.0) < 0.01


# ---------------------------------------------------------------------------
# 7–12. Drift severity classification
# ---------------------------------------------------------------------------


def test_drift_none(assumption_tracker: AssumptionTracker) -> None:
    """Value within minor threshold → NONE."""
    a = make_assumption(baseline_value=100.0)
    assumption_tracker.ingest(a)
    v = assumption_tracker.update_value(a.id, new_value=102.0)  # 2% drift
    assert v.severity == DriftSeverity.NONE


def test_drift_minor(assumption_tracker: AssumptionTracker) -> None:
    """Drift between minor and moderate thresholds → MINOR."""
    a = make_assumption(baseline_value=100.0)
    assumption_tracker.ingest(a)
    v = assumption_tracker.update_value(a.id, new_value=108.0)  # 8% drift
    assert v.severity == DriftSeverity.MINOR


def test_drift_moderate(assumption_tracker: AssumptionTracker) -> None:
    """Drift between moderate and significant thresholds → MODERATE."""
    a = make_assumption(baseline_value=100.0)
    assumption_tracker.ingest(a)
    v = assumption_tracker.update_value(a.id, new_value=120.0)  # 20% drift
    assert v.severity == DriftSeverity.MODERATE


def test_drift_significant(assumption_tracker: AssumptionTracker) -> None:
    """Drift between significant and 1.5× significant thresholds → SIGNIFICANT."""
    a = make_assumption(baseline_value=100.0)
    assumption_tracker.ingest(a)
    v = assumption_tracker.update_value(a.id, new_value=140.0)  # 40% drift
    assert v.severity == DriftSeverity.SIGNIFICANT


def test_drift_critical(assumption_tracker: AssumptionTracker) -> None:
    """Drift beyond 1.5× significant threshold → CRITICAL."""
    a = make_assumption(baseline_value=100.0)
    assumption_tracker.ingest(a)
    v = assumption_tracker.update_value(a.id, new_value=200.0)  # 100% drift
    assert v.severity == DriftSeverity.CRITICAL


def test_drift_zero_baseline(assumption_tracker: AssumptionTracker) -> None:
    """baseline_value=0 handled without division by zero."""
    a = make_assumption(baseline_value=0.0)
    assumption_tracker.ingest(a)
    v = assumption_tracker.update_value(a.id, new_value=5.0)
    assert v.drift_pct == 5.0  # absolute drift
    assert v.severity in DriftSeverity  # some valid severity


# ---------------------------------------------------------------------------
# 13–15. Cascade analysis
# ---------------------------------------------------------------------------


def test_cascade_impact_direct(assumption_tracker: AssumptionTracker) -> None:
    """Assumption B depends on A → A's cascade impact includes B."""
    a = make_assumption(text="A")
    assumption_tracker.ingest(a)
    b = make_assumption(text="B", dependencies=[a.id])
    assumption_tracker.ingest(b)

    impact = assumption_tracker.get_cascade_impact(a.id)
    assert b.id in impact


def test_cascade_impact_transitive(assumption_tracker: AssumptionTracker) -> None:
    """A→B→C chain: A's cascade impact includes both B and C."""
    a = make_assumption(text="A")
    assumption_tracker.ingest(a)
    b = make_assumption(text="B", dependencies=[a.id])
    assumption_tracker.ingest(b)
    c = make_assumption(text="C", dependencies=[b.id])
    assumption_tracker.ingest(c)

    impact = assumption_tracker.get_cascade_impact(a.id)
    assert b.id in impact
    assert c.id in impact


def test_cascade_handles_cycles(assumption_tracker: AssumptionTracker) -> None:
    """Circular dependency (A→B→A) does not cause an infinite loop."""
    a = make_assumption(text="A")
    assumption_tracker.ingest(a)
    b = make_assumption(text="B", dependencies=[a.id])
    assumption_tracker.ingest(b)

    # Manually create a cycle by updating A to depend on B via ingest
    a_cyclic = Assumption(
        id=a.id,
        project_id="PROJ-001",
        text="A",
        category=AssumptionCategory.COST,
        baseline_value=100.0,
        dependencies=[b.id],
    )
    assumption_tracker.ingest(a_cyclic)

    # Should complete without error
    impact = assumption_tracker.get_cascade_impact(a.id)
    assert isinstance(impact, list)


# ---------------------------------------------------------------------------
# 16–17. Staleness
# ---------------------------------------------------------------------------


def test_stale_assumptions(populated_assumption_tracker: AssumptionTracker) -> None:
    """Assumptions not validated within staleness_days are returned."""
    stale = populated_assumption_tracker.get_stale_assumptions("PROJ-001")
    assert len(stale) > 0


def test_no_stale_when_recently_validated(assumption_tracker: AssumptionTracker) -> None:
    """An assumption validated today is not flagged as stale."""
    a = make_assumption(
        baseline_value=100.0,
        last_validated=date.today(),
        created_date=date.today() - timedelta(days=60),
    )
    assumption_tracker.ingest(a)
    stale = assumption_tracker.get_stale_assumptions("PROJ-001")
    assert all(s.id != a.id for s in stale)


# ---------------------------------------------------------------------------
# 18–20. analyse_project
# ---------------------------------------------------------------------------


def test_analyse_project_complete(populated_assumption_tracker: AssumptionTracker) -> None:
    """Full health report has correct counts and structure."""
    report = populated_assumption_tracker.analyse_project("PROJ-001")
    assert isinstance(report, AssumptionHealthReport)
    assert report.project_id == "PROJ-001"
    assert report.total_assumptions > 0
    assert len(report.drift_results) == report.total_assumptions
    assert 0.0 <= report.overall_drift_score <= 1.0
    assert report.by_severity
    assert report.by_category


def test_analyse_project_empty(assumption_tracker: AssumptionTracker) -> None:
    """No assumptions → sensible defaults returned."""
    report = assumption_tracker.analyse_project("PROJ-EMPTY")
    assert report.total_assumptions == 0
    assert report.overall_drift_score == 0.0
    assert report.drift_results == []


def test_overall_drift_score(assumption_tracker: AssumptionTracker) -> None:
    """Weighted average computed correctly for known severities."""
    # NONE=0.0, MINOR=0.2 → avg=0.1
    a1 = make_assumption(baseline_value=100.0, text="A1")
    a2 = make_assumption(baseline_value=100.0, text="A2")
    assumption_tracker.ingest(a1)
    assumption_tracker.ingest(a2)
    # a1 stays at baseline (NONE), a2 gets 8% drift (MINOR)
    assumption_tracker.update_value(a1.id, new_value=100.0)
    assumption_tracker.update_value(a2.id, new_value=108.0)
    report = assumption_tracker.analyse_project("PROJ-001")
    assert abs(report.overall_drift_score - 0.1) < 0.05


# ---------------------------------------------------------------------------
# 21–22. History and graph
# ---------------------------------------------------------------------------


def test_validation_history_ordered(assumption_tracker: AssumptionTracker) -> None:
    """Validation history is returned oldest first."""
    a = make_assumption(baseline_value=100.0)
    assumption_tracker.ingest(a)
    assumption_tracker.update_value(a.id, new_value=105.0)
    assumption_tracker.update_value(a.id, new_value=115.0)
    assumption_tracker.update_value(a.id, new_value=130.0)

    history = assumption_tracker.get_validation_history(a.id)
    assert len(history) == 3
    drift_pcts = [h.drift_pct for h in history]
    assert drift_pcts == sorted(drift_pcts)


def test_dependency_graph(assumption_tracker: AssumptionTracker) -> None:
    """Dependency graph has correct reverse adjacency structure."""
    a = make_assumption(text="A")
    assumption_tracker.ingest(a)
    b = make_assumption(text="B", dependencies=[a.id])
    assumption_tracker.ingest(b)
    c = make_assumption(text="C", dependencies=[a.id])
    assumption_tracker.ingest(c)

    graph = assumption_tracker.get_dependency_graph("PROJ-001")
    assert b.id in graph[a.id]
    assert c.id in graph[a.id]
    assert graph[b.id] == []
    assert graph[c.id] == []


# ---------------------------------------------------------------------------
# 23–24. Config and persistence
# ---------------------------------------------------------------------------


def test_custom_config_thresholds(store) -> None:
    """Non-default thresholds change severity classification."""
    strict_config = AssumptionConfig(
        minor_threshold_pct=1.0,
        moderate_threshold_pct=3.0,
        significant_threshold_pct=5.0,
    )
    tracker = AssumptionTracker(store=store, config=strict_config)
    a = make_assumption(baseline_value=100.0)
    tracker.ingest(a)
    v = tracker.update_value(a.id, new_value=104.0)  # 4% drift
    # With strict config: 4% > moderate(3%) but <= significant(5%) → MODERATE
    assert v.severity == DriftSeverity.MODERATE


def test_assumption_with_dependencies_persists(assumption_tracker: AssumptionTracker) -> None:
    """Dependencies list round-trips correctly through the store."""
    a = make_assumption(text="Parent")
    assumption_tracker.ingest(a)
    child = make_assumption(text="Child", dependencies=[a.id, "some-other-id"])
    assumption_tracker.ingest(child)

    results = assumption_tracker.get_assumptions("PROJ-001")
    child_retrieved = next(r for r in results if r.text == "Child")
    assert a.id in child_retrieved.dependencies
    assert "some-other-id" in child_retrieved.dependencies
