"""Tests for P6 — Override Decision Logger and Analyser.

Covers logging, outcome recording, filtering, pattern analysis, and
field-level persistence (conditions, evidence_refs, links to P3 findings).
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from pm_data_tools.assurance.overrides import (
    OverrideDecision,
    OverrideDecisionLogger,
    OverrideOutcome,
    OverridePatternSummary,
    OverrideType,
)
from pm_data_tools.db.store import AssuranceStore


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_override(
    project_id: str = "PROJ-001",
    override_type: OverrideType = OverrideType.GATE_PROGRESSION,
    authoriser: str = "Test User",
    decision_date: date | None = None,
    **kwargs: object,
) -> OverrideDecision:
    return OverrideDecision(
        project_id=project_id,
        override_type=override_type,
        decision_date=decision_date or date(2026, 3, 1),
        authoriser=authoriser,
        rationale="Test rationale.",
        **kwargs,
    )


def _logger(tmp_path: Path) -> OverrideDecisionLogger:
    store = AssuranceStore(db_path=tmp_path / "store.db")
    return OverrideDecisionLogger(store=store)


# ---------------------------------------------------------------------------
# Logging and retrieval
# ---------------------------------------------------------------------------


def test_log_override_persists(tmp_path: Path) -> None:
    """Logged override is retrievable with all fields intact."""
    log = _logger(tmp_path)
    decision = _make_override(
        project_id="PROJ-001",
        override_type=OverrideType.RAG_OVERRIDE,
        authoriser="Jane Smith (SRO)",
        overridden_value="RED",
        override_value="AMBER",
    )
    log.log_override(decision)

    retrieved = log.get_overrides("PROJ-001")
    assert len(retrieved) == 1
    r = retrieved[0]
    assert r.project_id == "PROJ-001"
    assert r.override_type == OverrideType.RAG_OVERRIDE
    assert r.authoriser == "Jane Smith (SRO)"
    assert r.overridden_value == "RED"
    assert r.override_value == "AMBER"
    assert r.outcome == OverrideOutcome.PENDING


def test_log_override_generates_id(tmp_path: Path) -> None:
    """Auto-generated id is a non-empty UUID-format string."""
    log = _logger(tmp_path)
    d = _make_override()
    returned = log.log_override(d)
    assert returned.id
    # Confirm it is a valid UUID-format string
    import uuid
    uuid.UUID(returned.id)


def test_log_override_preserves_explicit_id(tmp_path: Path) -> None:
    """An explicitly set id is preserved."""
    log = _logger(tmp_path)
    d = OverrideDecision(
        id="fixed-uuid-001",
        project_id="PROJ-001",
        override_type=OverrideType.RISK_ACCEPTANCE,
        decision_date=date(2026, 3, 1),
        authoriser="Alice",
        rationale="Test.",
    )
    log.log_override(d)
    retrieved = log.get_overrides("PROJ-001")
    assert retrieved[0].id == "fixed-uuid-001"


# ---------------------------------------------------------------------------
# Outcome recording
# ---------------------------------------------------------------------------


def test_record_outcome_updates(tmp_path: Path) -> None:
    """Record a SIGNIFICANT_IMPACT outcome on a PENDING override."""
    log = _logger(tmp_path)
    d = log.log_override(_make_override())

    log.record_outcome(
        override_id=d.id,
        outcome=OverrideOutcome.SIGNIFICANT_IMPACT,
        outcome_date=date(2026, 6, 1),
        outcome_notes="Schedule slipped 6 months.",
    )

    retrieved = log.get_overrides("PROJ-001")[0]
    assert retrieved.outcome == OverrideOutcome.SIGNIFICANT_IMPACT
    assert retrieved.outcome_date == date(2026, 6, 1)
    assert retrieved.outcome_notes == "Schedule slipped 6 months."


def test_record_outcome_defaults_to_today(tmp_path: Path) -> None:
    """When outcome_date is not supplied it defaults to today."""
    log = _logger(tmp_path)
    d = log.log_override(_make_override())
    log.record_outcome(override_id=d.id, outcome=OverrideOutcome.NO_IMPACT)

    retrieved = log.get_overrides("PROJ-001")[0]
    assert retrieved.outcome == OverrideOutcome.NO_IMPACT
    assert retrieved.outcome_date == date.today()


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------


def test_get_overrides_unfiltered(tmp_path: Path) -> None:
    """Unfiltered retrieval returns all overrides for the project."""
    log = _logger(tmp_path)
    log.log_override(_make_override(override_type=OverrideType.GATE_PROGRESSION))
    log.log_override(_make_override(override_type=OverrideType.RISK_ACCEPTANCE))
    log.log_override(_make_override(override_type=OverrideType.RAG_OVERRIDE))

    result = log.get_overrides("PROJ-001")
    assert len(result) == 3


def test_get_overrides_by_type(tmp_path: Path) -> None:
    """Filtering by override_type returns only matching overrides."""
    log = _logger(tmp_path)
    log.log_override(_make_override(override_type=OverrideType.GATE_PROGRESSION))
    log.log_override(_make_override(override_type=OverrideType.RISK_ACCEPTANCE))

    result = log.get_overrides("PROJ-001", override_type=OverrideType.GATE_PROGRESSION)
    assert len(result) == 1
    assert result[0].override_type == OverrideType.GATE_PROGRESSION


def test_get_overrides_by_outcome(tmp_path: Path) -> None:
    """Filtering by outcome returns only matching overrides."""
    log = _logger(tmp_path)
    d1 = log.log_override(_make_override())
    d2 = log.log_override(_make_override())
    log.record_outcome(d1.id, OverrideOutcome.NO_IMPACT)

    pending = log.get_overrides("PROJ-001", outcome=OverrideOutcome.PENDING)
    assert len(pending) == 1
    assert pending[0].id == d2.id


def test_get_overrides_empty_project(tmp_path: Path) -> None:
    """Returns empty list for a project with no overrides."""
    log = _logger(tmp_path)
    assert log.get_overrides("PROJ-NONE") == []


# ---------------------------------------------------------------------------
# Pattern analysis
# ---------------------------------------------------------------------------


def test_analyse_patterns_empty(tmp_path: Path) -> None:
    """No overrides → total=0, impact_rate=0.0, empty breakdowns."""
    log = _logger(tmp_path)
    summary = log.analyse_patterns("PROJ-EMPTY")

    assert summary.total_overrides == 0
    assert summary.impact_rate == 0.0
    assert summary.pending_outcomes == 0
    assert summary.by_type == {}
    assert summary.top_authorisers == []


def test_analyse_patterns_all_pending(tmp_path: Path) -> None:
    """All PENDING overrides → impact_rate = 0.0 (no resolved)."""
    log = _logger(tmp_path)
    log.log_override(_make_override())
    log.log_override(_make_override())

    summary = log.analyse_patterns("PROJ-001")
    assert summary.impact_rate == 0.0
    assert summary.pending_outcomes == 2
    assert summary.total_overrides == 2


def test_analyse_patterns_mixed_outcomes(tmp_path: Path) -> None:
    """Correct impact_rate computed from mixed outcome set."""
    log = _logger(tmp_path)
    d1 = log.log_override(_make_override())
    d2 = log.log_override(_make_override())
    d3 = log.log_override(_make_override())
    d4 = log.log_override(_make_override())

    log.record_outcome(d1.id, OverrideOutcome.NO_IMPACT)
    log.record_outcome(d2.id, OverrideOutcome.MINOR_IMPACT)
    log.record_outcome(d3.id, OverrideOutcome.SIGNIFICANT_IMPACT)
    # d4 stays PENDING

    summary = log.analyse_patterns("PROJ-001")
    # resolved = 3, impactful = MINOR_IMPACT + SIGNIFICANT_IMPACT = 2
    assert summary.impact_rate == pytest.approx(2 / 3)
    assert summary.pending_outcomes == 1
    assert summary.total_overrides == 4


def test_analyse_patterns_escalated_counts_as_impact(tmp_path: Path) -> None:
    """ESCALATED outcome is counted in impact_rate."""
    log = _logger(tmp_path)
    d = log.log_override(_make_override())
    log.record_outcome(d.id, OverrideOutcome.ESCALATED)

    summary = log.analyse_patterns("PROJ-001")
    assert summary.impact_rate == pytest.approx(1.0)


def test_analyse_patterns_top_authorisers(tmp_path: Path) -> None:
    """top_authorisers is sorted by count descending, max 5 entries."""
    log = _logger(tmp_path)
    for _ in range(3):
        log.log_override(_make_override(authoriser="Alice"))
    for _ in range(2):
        log.log_override(_make_override(authoriser="Bob"))
    log.log_override(_make_override(authoriser="Charlie"))

    summary = log.analyse_patterns("PROJ-001")
    assert summary.top_authorisers[0]["authoriser"] == "Alice"
    assert summary.top_authorisers[0]["count"] == 3
    assert summary.top_authorisers[1]["authoriser"] == "Bob"
    assert len(summary.top_authorisers) <= 5


def test_analyse_patterns_by_type_breakdown(tmp_path: Path) -> None:
    """by_type correctly counts each OverrideType."""
    log = _logger(tmp_path)
    log.log_override(_make_override(override_type=OverrideType.GATE_PROGRESSION))
    log.log_override(_make_override(override_type=OverrideType.GATE_PROGRESSION))
    log.log_override(_make_override(override_type=OverrideType.RISK_ACCEPTANCE))

    summary = log.analyse_patterns("PROJ-001")
    assert summary.by_type[OverrideType.GATE_PROGRESSION.value] == 2
    assert summary.by_type[OverrideType.RISK_ACCEPTANCE.value] == 1


# ---------------------------------------------------------------------------
# Field-level persistence
# ---------------------------------------------------------------------------


def test_override_with_conditions(tmp_path: Path) -> None:
    """Conditions list is persisted and retrieved correctly."""
    log = _logger(tmp_path)
    conditions = ["Weekly risk review", "Escalation if SPI < 0.8"]
    log.log_override(_make_override(conditions=conditions))

    retrieved = log.get_overrides("PROJ-001")[0]
    assert retrieved.conditions == conditions


def test_override_with_evidence_refs(tmp_path: Path) -> None:
    """evidence_refs list is persisted and retrieved correctly."""
    log = _logger(tmp_path)
    refs = ["board-minutes-2026-03-15.pdf", "risk-register-v4.xlsx"]
    log.log_override(_make_override(evidence_refs=refs))

    retrieved = log.get_overrides("PROJ-001")[0]
    assert retrieved.evidence_refs == refs


def test_override_links_to_finding(tmp_path: Path) -> None:
    """overridden_finding_id links the override to a P3 ReviewAction."""
    log = _logger(tmp_path)
    finding_id = "rec-uuid-1234-abcd"
    log.log_override(
        _make_override(
            override_type=OverrideType.RECOMMENDATION_DISMISSED,
            overridden_finding_id=finding_id,
        )
    )

    retrieved = log.get_overrides("PROJ-001")[0]
    assert retrieved.overridden_finding_id == finding_id


def test_pattern_message_content(tmp_path: Path) -> None:
    """Summary message contains impact_rate and total overrides."""
    log = _logger(tmp_path)
    d = log.log_override(_make_override())
    log.record_outcome(d.id, OverrideOutcome.SIGNIFICANT_IMPACT)

    summary = log.analyse_patterns("PROJ-001")
    # impact_rate = 1/1 = 100%
    assert "100%" in summary.message or "1" in summary.message
    # total overrides
    assert "1" in summary.message
