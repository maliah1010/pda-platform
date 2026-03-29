"""Tests for P9 — Agentic Assurance Workflow Engine.

Covers:
- All five workflow types
- Each step executor (via completed/not-applicable outcomes)
- Inter-step data flow (P1/P2/P3/P4 → P5)
- Fail-safe behaviour (step exception → FAILED, workflow continues)
- Health classification (HEALTHY / ATTENTION_NEEDED / AT_RISK / CRITICAL)
- Recommended actions generation
- Executive summary generation
- Store persistence and history retrieval
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from pm_data_tools.assurance.workflows import (
    AssuranceWorkflowEngine,
    ProjectHealth,
    WorkflowConfig,
    WorkflowResult,
    WorkflowRiskSignal,
    WorkflowStepResult,
    WorkflowStepStatus,
    WorkflowType,
)
from pm_data_tools.db.store import AssuranceStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_engine(
    store: AssuranceStore | None = None,
    config: WorkflowConfig | None = None,
) -> AssuranceWorkflowEngine:
    return AssuranceWorkflowEngine(config=config, store=store)


def make_artefacts(outdated_count: int = 0, total: int = 3) -> list[dict]:
    """Build a simple artefact list for P1 testing.

    Each dict uses the keys expected by ArtefactCurrencyValidator.check_batch:
    ``id``, ``type``, ``last_modified`` (ISO-8601 string).
    """
    gate = datetime.now(tz=timezone.utc)
    artefacts = []
    for i in range(total):
        if i < outdated_count:
            # Outdated: last modified 200 days ago
            last_modified = (gate - timedelta(days=200)).isoformat()
        else:
            last_modified = (gate - timedelta(days=5)).isoformat()
        artefacts.append({
            "id": f"doc-{i}",
            "type": "document",
            "last_modified": last_modified,
        })
    return artefacts


# ---------------------------------------------------------------------------
# Basic workflow execution
# ---------------------------------------------------------------------------


def test_execute_returns_workflow_result(store: AssuranceStore) -> None:
    engine = make_engine(store=store)
    result = engine.execute("PROJ-001", WorkflowType.FULL_ASSURANCE)
    assert isinstance(result, WorkflowResult)


def test_workflow_result_has_id(store: AssuranceStore) -> None:
    engine = make_engine(store=store)
    result = engine.execute("PROJ-001", WorkflowType.COMPLIANCE_FOCUS)
    assert result.id
    assert len(result.id) == 36  # UUID4


def test_workflow_result_has_timestamps(store: AssuranceStore) -> None:
    engine = make_engine(store=store)
    result = engine.execute("PROJ-001", WorkflowType.COMPLIANCE_FOCUS)
    assert result.started_at <= result.completed_at


def test_workflow_result_positive_duration(store: AssuranceStore) -> None:
    engine = make_engine(store=store)
    result = engine.execute("PROJ-001", WorkflowType.COMPLIANCE_FOCUS)
    assert result.duration_ms >= 0


def test_full_assurance_has_eight_steps(store: AssuranceStore) -> None:
    engine = make_engine(store=store)
    result = engine.execute("PROJ-001", WorkflowType.FULL_ASSURANCE)
    assert len(result.steps) == 8


def test_compliance_focus_has_three_steps(store: AssuranceStore) -> None:
    engine = make_engine(store=store)
    result = engine.execute("PROJ-001", WorkflowType.COMPLIANCE_FOCUS)
    step_names = [s.step_name for s in result.steps]
    assert "p2_compliance_trend" in step_names
    assert "p5_schedule_recommendation" in step_names
    assert "p6_override_analysis" in step_names
    assert len(step_names) == 3


def test_currency_focus_has_two_steps(store: AssuranceStore) -> None:
    engine = make_engine(store=store)
    result = engine.execute("PROJ-001", WorkflowType.CURRENCY_FOCUS)
    assert len(result.steps) == 2


def test_trend_analysis_has_three_steps(store: AssuranceStore) -> None:
    engine = make_engine(store=store)
    result = engine.execute("PROJ-001", WorkflowType.TREND_ANALYSIS)
    step_names = [s.step_name for s in result.steps]
    assert "p2_compliance_trend" in step_names
    assert "p3_review_actions" in step_names
    assert "p5_schedule_recommendation" in step_names


def test_risk_assessment_has_five_steps(store: AssuranceStore) -> None:
    engine = make_engine(store=store)
    result = engine.execute("PROJ-001", WorkflowType.RISK_ASSESSMENT)
    assert len(result.steps) == 5


# ---------------------------------------------------------------------------
# Step status with empty store
# ---------------------------------------------------------------------------


def test_empty_store_p2_step_not_applicable(store: AssuranceStore) -> None:
    engine = make_engine(store=store)
    result = engine.execute("PROJ-001", WorkflowType.COMPLIANCE_FOCUS)
    p2 = next(s for s in result.steps if s.step_name == "p2_compliance_trend")
    assert p2.status == WorkflowStepStatus.NOT_APPLICABLE


def test_empty_store_p6_step_not_applicable(store: AssuranceStore) -> None:
    engine = make_engine(store=store)
    result = engine.execute("PROJ-001", WorkflowType.COMPLIANCE_FOCUS)
    p6 = next(s for s in result.steps if s.step_name == "p6_override_analysis")
    assert p6.status == WorkflowStepStatus.NOT_APPLICABLE


def test_p1_not_applicable_when_no_artefacts(store: AssuranceStore) -> None:
    engine = make_engine(store=store)
    result = engine.execute("PROJ-001", WorkflowType.CURRENCY_FOCUS)
    p1 = next(s for s in result.steps if s.step_name == "p1_currency")
    assert p1.status == WorkflowStepStatus.NOT_APPLICABLE


def test_p5_completes_with_no_signals(store: AssuranceStore) -> None:
    """P5 always completes — it falls back to standard cadence."""
    engine = make_engine(store=store)
    result = engine.execute("PROJ-001", WorkflowType.CURRENCY_FOCUS)
    p5 = next(s for s in result.steps if s.step_name == "p5_schedule_recommendation")
    assert p5.status == WorkflowStepStatus.COMPLETED


# ---------------------------------------------------------------------------
# P1 step with artefacts
# ---------------------------------------------------------------------------


def test_p1_completes_when_artefacts_provided(store: AssuranceStore) -> None:
    engine = make_engine(store=store)
    gate_date = datetime.now(tz=timezone.utc).isoformat()
    artefacts = make_artefacts(outdated_count=0, total=2)
    result = engine.execute(
        "PROJ-001",
        WorkflowType.CURRENCY_FOCUS,
        artefacts=artefacts,
        gate_date=gate_date,
    )
    p1 = next(s for s in result.steps if s.step_name == "p1_currency")
    assert p1.status == WorkflowStepStatus.COMPLETED
    assert p1.output is not None
    assert p1.output["total"] == 2


def test_p1_outdated_artefacts_produce_signal(store: AssuranceStore) -> None:
    engine = make_engine(store=store)
    gate_date = datetime.now(tz=timezone.utc).isoformat()
    artefacts = make_artefacts(outdated_count=3, total=3)
    result = engine.execute(
        "PROJ-001",
        WorkflowType.CURRENCY_FOCUS,
        artefacts=artefacts,
        gate_date=gate_date,
    )
    p1 = next(s for s in result.steps if s.step_name == "p1_currency")
    assert p1.risk_signal is not None
    assert p1.risk_signal.severity > 0


# ---------------------------------------------------------------------------
# Inter-step data flow
# ---------------------------------------------------------------------------


def test_p1_output_flows_to_p5(store: AssuranceStore) -> None:
    """P5's recommended date should reflect the P1 urgency signal."""
    engine = make_engine(store=store)
    gate_date = datetime.now(tz=timezone.utc).isoformat()
    # All outdated → P1 severity = 1.0 → P5 should recommend IMMEDIATE
    artefacts = make_artefacts(outdated_count=3, total=3)
    result = engine.execute(
        "PROJ-001",
        WorkflowType.CURRENCY_FOCUS,
        artefacts=artefacts,
        gate_date=gate_date,
    )
    p5 = next(s for s in result.steps if s.step_name == "p5_schedule_recommendation")
    assert p5.status == WorkflowStepStatus.COMPLETED
    assert p5.output is not None
    # With P1 severity 1.0, scheduler should recommend IMMEDIATE
    assert p5.output["urgency"] == "IMMEDIATE"


def test_no_artefacts_p5_defaults_to_standard(store: AssuranceStore) -> None:
    engine = make_engine(store=store)
    result = engine.execute("PROJ-001", WorkflowType.CURRENCY_FOCUS)
    p5 = next(s for s in result.steps if s.step_name == "p5_schedule_recommendation")
    assert p5.output is not None
    assert p5.output["urgency"] == "STANDARD"


# ---------------------------------------------------------------------------
# Fail-safe behaviour
# ---------------------------------------------------------------------------


def test_step_exception_does_not_abort_workflow(store: AssuranceStore) -> None:
    """If a step executor raises, the workflow records FAILED and continues."""
    engine = make_engine(store=store)

    original = engine._step_compliance_trend

    def exploding_step(**kwargs):  # type: ignore[no-untyped-def]
        raise RuntimeError("simulated step failure")

    engine._step_compliance_trend = exploding_step  # type: ignore[method-assign]
    result = engine.execute("PROJ-001", WorkflowType.TREND_ANALYSIS)

    p2 = next(s for s in result.steps if s.step_name == "p2_compliance_trend")
    assert p2.status == WorkflowStepStatus.FAILED
    assert "simulated step failure" in str(p2.error_message)

    # Other steps still ran
    remaining = [s for s in result.steps if s.step_name != "p2_compliance_trend"]
    assert len(remaining) >= 1

    engine._step_compliance_trend = original  # type: ignore[method-assign]


# ---------------------------------------------------------------------------
# Health classification
# ---------------------------------------------------------------------------


def test_health_healthy_when_no_signals() -> None:
    engine = make_engine()
    assert engine._classify_health([]) == ProjectHealth.HEALTHY


def test_health_attention_low_severity() -> None:
    engine = make_engine()
    signals = [WorkflowRiskSignal(source="P1", signal_name="x", severity=0.25, detail="")]
    assert engine._classify_health(signals) == ProjectHealth.ATTENTION_NEEDED


def test_health_at_risk_moderate_severity() -> None:
    engine = make_engine()
    signals = [WorkflowRiskSignal(source="P2", signal_name="x", severity=0.60, detail="")]
    assert engine._classify_health(signals) == ProjectHealth.AT_RISK


def test_health_critical_high_severity() -> None:
    engine = make_engine()
    signals = [WorkflowRiskSignal(source="P2", signal_name="x", severity=0.90, detail="")]
    assert engine._classify_health(signals) == ProjectHealth.CRITICAL


def test_health_at_risk_high_average() -> None:
    """Average >= 0.40 triggers AT_RISK even if no single signal is >= 0.50."""
    engine = make_engine()
    signals = [
        WorkflowRiskSignal(source="P1", signal_name="a", severity=0.45, detail=""),
        WorkflowRiskSignal(source="P3", signal_name="b", severity=0.45, detail=""),
    ]
    assert engine._classify_health(signals) == ProjectHealth.AT_RISK


# ---------------------------------------------------------------------------
# Recommended actions
# ---------------------------------------------------------------------------


def test_recommended_actions_critical_health() -> None:
    engine = make_engine()
    signals = [WorkflowRiskSignal(source="P2", signal_name="compliance_trend", severity=0.9, detail="")]
    actions = engine._generate_recommended_actions(ProjectHealth.CRITICAL, signals)
    assert any("immediate" in a.lower() for a in actions)


def test_recommended_actions_p1_signal_triggers_artefact_action() -> None:
    engine = make_engine()
    signals = [WorkflowRiskSignal(source="P1", signal_name="outdated_artefacts", severity=0.8, detail="")]
    actions = engine._generate_recommended_actions(ProjectHealth.CRITICAL, signals)
    assert any("artefact" in a.lower() for a in actions)


def test_recommended_actions_deduplicated() -> None:
    engine = make_engine()
    signals = [
        WorkflowRiskSignal(source="P2", signal_name="compliance_trend", severity=0.6, detail=""),
        WorkflowRiskSignal(source="P2", signal_name="compliance_trend", severity=0.6, detail=""),
    ]
    actions = engine._generate_recommended_actions(ProjectHealth.AT_RISK, signals)
    assert len(actions) == len(set(actions))


def test_recommended_actions_empty_when_healthy() -> None:
    engine = make_engine()
    # No signals above threshold → no signal-level actions
    actions = engine._generate_recommended_actions(ProjectHealth.HEALTHY, [])
    assert actions == []


# ---------------------------------------------------------------------------
# Executive summary
# ---------------------------------------------------------------------------


def test_executive_summary_contains_project_id(store: AssuranceStore) -> None:
    engine = make_engine(store=store)
    result = engine.execute("PROJ-XYZ", WorkflowType.COMPLIANCE_FOCUS)
    assert "PROJ-XYZ" in result.executive_summary


def test_executive_summary_contains_health(store: AssuranceStore) -> None:
    engine = make_engine(store=store)
    result = engine.execute("PROJ-001", WorkflowType.COMPLIANCE_FOCUS)
    assert result.health.value in result.executive_summary


def test_executive_summary_contains_workflow_type(store: AssuranceStore) -> None:
    engine = make_engine(store=store)
    result = engine.execute("PROJ-001", WorkflowType.TREND_ANALYSIS)
    assert "TREND_ANALYSIS" in result.executive_summary


# ---------------------------------------------------------------------------
# Store persistence and history
# ---------------------------------------------------------------------------


def test_workflow_persisted_to_store(store: AssuranceStore) -> None:
    engine = make_engine(store=store)
    result = engine.execute("PROJ-001", WorkflowType.COMPLIANCE_FOCUS)
    rows = store.get_workflow_history("PROJ-001")
    assert len(rows) == 1
    assert rows[0]["id"] == result.id
    assert rows[0]["health"] == result.health.value


def test_workflow_history_accumulates(store: AssuranceStore) -> None:
    engine = make_engine(store=store)
    engine.execute("PROJ-001", WorkflowType.COMPLIANCE_FOCUS)
    engine.execute("PROJ-001", WorkflowType.TREND_ANALYSIS)
    rows = store.get_workflow_history("PROJ-001")
    assert len(rows) == 2


def test_get_workflow_history_returns_results(store: AssuranceStore) -> None:
    engine = make_engine(store=store)
    engine.execute("PROJ-001", WorkflowType.RISK_ASSESSMENT)
    history = engine.get_workflow_history("PROJ-001")
    assert len(history) == 1
    assert isinstance(history[0], WorkflowResult)


def test_workflow_history_empty(store: AssuranceStore) -> None:
    engine = make_engine(store=store)
    assert engine.get_workflow_history("PROJ-UNKNOWN") == []


def test_no_store_history_returns_empty() -> None:
    engine = make_engine(store=None)
    assert engine.get_workflow_history("PROJ-001") == []


def test_no_store_result_not_persisted() -> None:
    """Engine without store should not raise on execute."""
    engine = make_engine(store=None)
    result = engine.execute("PROJ-001", WorkflowType.CURRENCY_FOCUS)
    assert isinstance(result, WorkflowResult)


def test_store_results_false_skips_persistence(store: AssuranceStore) -> None:
    config = WorkflowConfig(store_results=False)
    engine = make_engine(store=store, config=config)
    engine.execute("PROJ-001", WorkflowType.COMPLIANCE_FOCUS)
    rows = store.get_workflow_history("PROJ-001")
    assert len(rows) == 0
