"""Override Decision Logger and Analyser for governance decisions.

Governance boards sometimes proceed against assurance advice — continuing
past a failed gate, dismissing recurring recommendations, or overriding a
risk rating.  These decisions are rarely captured in a structured way,
making it impossible to analyse patterns or track whether overrides led
to predicted consequences.

This module provides structured logging, pattern analysis, and post-override
outcome tracking.

Usage::

    from pm_data_tools.assurance.overrides import (
        OverrideDecisionLogger,
        OverrideDecision,
        OverrideType,
        OverrideOutcome,
    )

    logger_obj = OverrideDecisionLogger()
    decision = logger_obj.log_override(
        OverrideDecision(
            project_id="PROJ-001",
            override_type=OverrideType.GATE_PROGRESSION,
            decision_date=date.today(),
            authoriser="Jane Smith (SRO)",
            rationale="Critical business deadline.",
        )
    )

    # Later, record the outcome
    logger_obj.record_outcome(
        override_id=decision.id,
        outcome=OverrideOutcome.MINOR_IMPACT,
        outcome_notes="Minor schedule slip but manageable.",
    )

    summary = logger_obj.analyse_patterns("PROJ-001")
"""

from __future__ import annotations

import json
import uuid
from collections import Counter
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Optional

import structlog
from pydantic import BaseModel, Field

from ..db.store import AssuranceStore

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class OverrideType(Enum):
    """Category of an override decision.

    Attributes:
        GATE_PROGRESSION: Proceeded past a failed or red-rated gate.
        RECOMMENDATION_DISMISSED: Dismissed an assurance recommendation.
        RAG_OVERRIDE: Changed a RAG rating against assessor advice.
        RISK_ACCEPTANCE: Accepted a risk flagged for mitigation.
        SCHEDULE_OVERRIDE: Overrode a recommended review schedule.
    """

    GATE_PROGRESSION = "GATE_PROGRESSION"
    RECOMMENDATION_DISMISSED = "RECOMMENDATION_DISMISSED"
    RAG_OVERRIDE = "RAG_OVERRIDE"
    RISK_ACCEPTANCE = "RISK_ACCEPTANCE"
    SCHEDULE_OVERRIDE = "SCHEDULE_OVERRIDE"


class OverrideOutcome(Enum):
    """Tracked outcome after an override decision.

    Attributes:
        PENDING: Outcome not yet determined.
        NO_IMPACT: Override had no measurable negative effect.
        MINOR_IMPACT: Some negative effect but manageable.
        SIGNIFICANT_IMPACT: Predicted consequences materialised.
        ESCALATED: Worse than predicted — escalation was required.
    """

    PENDING = "PENDING"
    NO_IMPACT = "NO_IMPACT"
    MINOR_IMPACT = "MINOR_IMPACT"
    SIGNIFICANT_IMPACT = "SIGNIFICANT_IMPACT"
    ESCALATED = "ESCALATED"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class OverrideDecision(BaseModel):
    """A structured record of a governance override decision.

    Attributes:
        id: Unique identifier (UUID4 by default).
        project_id: Project this decision applies to.
        override_type: Category of the override.
        decision_date: When the override was authorised.
        authoriser: Who authorised the override.
        rationale: Why the override was approved.
        overridden_finding_id: Optional link to a :class:`~.models.ReviewAction`
            id from P3, a gate reference, or a RAG rating reference.
        overridden_value: What the assurance advice was (e.g. ``"RED"``).
        override_value: What was decided instead (e.g. ``"Proceed with conditions"``).
        conditions: Any conditions attached to the override decision.
        evidence_refs: Document references supporting the decision.
        outcome: Observed outcome.  Defaults to :attr:`OverrideOutcome.PENDING`.
        outcome_date: When the outcome was observed.
        outcome_notes: Human-readable notes about the outcome.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str
    override_type: OverrideType
    decision_date: date
    authoriser: str
    rationale: str
    overridden_finding_id: Optional[str] = None
    overridden_value: Optional[str] = None
    override_value: Optional[str] = None
    conditions: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list)
    outcome: OverrideOutcome = OverrideOutcome.PENDING
    outcome_date: Optional[date] = None
    outcome_notes: Optional[str] = None


class OverridePatternSummary(BaseModel):
    """Summary statistics for a project's override history.

    Attributes:
        project_id: The analysed project.
        total_overrides: Total number of logged overrides.
        by_type: Count per :class:`OverrideType` value.
        by_outcome: Count per :class:`OverrideOutcome` value.
        pending_outcomes: How many overrides still have a
            :attr:`~OverrideOutcome.PENDING` outcome.
        impact_rate: Proportion of **resolved** overrides with
            :attr:`~OverrideOutcome.MINOR_IMPACT` or worse (0–1).
            Zero when no overrides have been resolved.
        top_authorisers: Top-5 authorisers by override count,
            as ``[{"authoriser": str, "count": int}]``.
        message: Human-readable summary of the pattern.
    """

    project_id: str
    total_overrides: int
    by_type: dict[str, int]
    by_outcome: dict[str, int]
    pending_outcomes: int
    impact_rate: float
    top_authorisers: list[dict[str, Any]]
    message: str


# ---------------------------------------------------------------------------
# Logger / analyser
# ---------------------------------------------------------------------------


class OverrideDecisionLogger:
    """Structured logging and analysis of governance override decisions.

    Captures the full lifecycle of an override: the initial decision with
    its rationale and conditions, and the eventual outcome once it is known.
    Provides pattern analysis to surface whether overrides are leading to
    negative consequences.

    Example::

        from pm_data_tools.db.store import AssuranceStore

        store = AssuranceStore()
        logger_obj = OverrideDecisionLogger(store=store)

        decision = logger_obj.log_override(
            OverrideDecision(
                project_id="PROJ-001",
                override_type=OverrideType.GATE_PROGRESSION,
                decision_date=date(2026, 3, 15),
                authoriser="Jane Smith (SRO)",
                rationale="Critical deadline.",
            )
        )

        summary = logger_obj.analyse_patterns("PROJ-001")
    """

    def __init__(
        self,
        store: AssuranceStore | None = None,
    ) -> None:
        """Initialise the override decision logger.

        Args:
            store: Shared :class:`~pm_data_tools.db.store.AssuranceStore`.
                A default store is created if not provided.
        """
        self._store = store or AssuranceStore()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_decision(row: dict[str, object]) -> OverrideDecision:
        """Deserialise a database row to an :class:`OverrideDecision`.

        Args:
            row: A dict with the columns of the ``override_decisions`` table.

        Returns:
            The reconstructed :class:`OverrideDecision`.
        """
        return OverrideDecision(
            id=str(row["id"]),
            project_id=str(row["project_id"]),
            override_type=OverrideType(str(row["override_type"])),
            decision_date=date.fromisoformat(str(row["decision_date"])),
            authoriser=str(row["authoriser"]),
            rationale=str(row["rationale"]),
            overridden_finding_id=(
                str(row["overridden_finding_id"])
                if row.get("overridden_finding_id")
                else None
            ),
            overridden_value=(
                str(row["overridden_value"]) if row.get("overridden_value") else None
            ),
            override_value=(
                str(row["override_value"]) if row.get("override_value") else None
            ),
            conditions=json.loads(str(row.get("conditions_json", "[]"))),
            evidence_refs=json.loads(str(row.get("evidence_refs_json", "[]"))),
            outcome=OverrideOutcome(str(row["outcome"])),
            outcome_date=(
                date.fromisoformat(str(row["outcome_date"]))
                if row.get("outcome_date")
                else None
            ),
            outcome_notes=(
                str(row["outcome_notes"]) if row.get("outcome_notes") else None
            ),
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def log_override(self, decision: OverrideDecision) -> OverrideDecision:
        """Persist an override decision to the store.

        Args:
            decision: The :class:`OverrideDecision` to log.

        Returns:
            The same decision object (with its auto-generated ``id`` if it
            was not set explicitly).
        """
        self._store.upsert_override_decision(
            {
                "id": decision.id,
                "project_id": decision.project_id,
                "override_type": decision.override_type.value,
                "decision_date": decision.decision_date.isoformat(),
                "authoriser": decision.authoriser,
                "rationale": decision.rationale,
                "overridden_finding_id": decision.overridden_finding_id,
                "overridden_value": decision.overridden_value,
                "override_value": decision.override_value,
                "conditions_json": json.dumps(decision.conditions),
                "evidence_refs_json": json.dumps(decision.evidence_refs),
                "outcome": decision.outcome.value,
                "outcome_date": (
                    decision.outcome_date.isoformat()
                    if decision.outcome_date
                    else None
                ),
                "outcome_notes": decision.outcome_notes,
                "created_at": datetime.now(tz=timezone.utc).isoformat(),
            }
        )

        logger.info(
            "override_logged",
            id=decision.id,
            project_id=decision.project_id,
            override_type=decision.override_type.value,
        )
        return decision

    def record_outcome(
        self,
        override_id: str,
        outcome: OverrideOutcome,
        outcome_date: date | None = None,
        outcome_notes: str | None = None,
    ) -> None:
        """Update the outcome of a previously logged override decision.

        Args:
            override_id: The ``id`` of the :class:`OverrideDecision` to update.
            outcome: The observed :class:`OverrideOutcome`.
            outcome_date: When the outcome was observed.  Defaults to today.
            outcome_notes: Optional notes describing the outcome.
        """
        resolved_date = outcome_date or date.today()
        self._store.update_override_outcome(
            override_id=override_id,
            outcome=outcome.value,
            outcome_date=resolved_date.isoformat(),
            outcome_notes=outcome_notes,
        )

        logger.info(
            "override_outcome_recorded",
            id=override_id,
            outcome=outcome.value,
        )

    def get_overrides(
        self,
        project_id: str,
        override_type: OverrideType | None = None,
        outcome: OverrideOutcome | None = None,
    ) -> list[OverrideDecision]:
        """Retrieve override decisions for a project, optionally filtered.

        Args:
            project_id: The project identifier.
            override_type: Optional :class:`OverrideType` filter.
            outcome: Optional :class:`OverrideOutcome` filter.

        Returns:
            List of :class:`OverrideDecision` objects ordered by
            ``decision_date`` ascending.
        """
        rows = self._store.get_override_decisions(
            project_id=project_id,
            override_type=override_type.value if override_type is not None else None,
            outcome=outcome.value if outcome is not None else None,
        )
        return [self._row_to_decision(row) for row in rows]

    def analyse_patterns(self, project_id: str) -> OverridePatternSummary:
        """Compute pattern statistics for a project's override history.

        Calculates:

        - Total overrides and breakdown by type and outcome.
        - Impact rate: proportion of **resolved** (non-PENDING) overrides
          with :attr:`~OverrideOutcome.MINOR_IMPACT` or worse.
        - Top-5 authorisers by override count.
        - Human-readable summary message.

        Args:
            project_id: The project identifier.

        Returns:
            An :class:`OverridePatternSummary`.
        """
        overrides = self.get_overrides(project_id)
        total = len(overrides)

        if total == 0:
            return OverridePatternSummary(
                project_id=project_id,
                total_overrides=0,
                by_type={},
                by_outcome={},
                pending_outcomes=0,
                impact_rate=0.0,
                top_authorisers=[],
                message="No override decisions recorded for this project.",
            )

        # Breakdowns
        by_type: dict[str, int] = {}
        for ot in OverrideType:
            count = sum(1 for o in overrides if o.override_type == ot)
            if count:
                by_type[ot.value] = count

        by_outcome: dict[str, int] = {}
        for oo in OverrideOutcome:
            count = sum(1 for o in overrides if o.outcome == oo)
            if count:
                by_outcome[oo.value] = count

        pending = sum(1 for o in overrides if o.outcome == OverrideOutcome.PENDING)
        resolved = total - pending

        _negative_outcomes = {
            OverrideOutcome.MINOR_IMPACT,
            OverrideOutcome.SIGNIFICANT_IMPACT,
            OverrideOutcome.ESCALATED,
        }
        impactful = sum(1 for o in overrides if o.outcome in _negative_outcomes)
        impact_rate = impactful / resolved if resolved > 0 else 0.0

        # Top authorisers
        auth_counts = Counter(o.authoriser for o in overrides)
        top_authorisers = [
            {"authoriser": auth, "count": cnt}
            for auth, cnt in auth_counts.most_common(5)
        ]

        message = (
            f"{total} override(s) recorded for project '{project_id}'.  "
            f"Impact rate: {impact_rate:.0%} ({impactful}/{resolved} resolved).  "
            f"{pending} outcome(s) still pending."
        )

        logger.info(
            "override_patterns_analysed",
            project_id=project_id,
            total=total,
            impact_rate=impact_rate,
            pending=pending,
        )

        return OverridePatternSummary(
            project_id=project_id,
            total_overrides=total,
            by_type=by_type,
            by_outcome=by_outcome,
            pending_outcomes=pending,
            impact_rate=impact_rate,
            top_authorisers=top_authorisers,
            message=message,
        )
