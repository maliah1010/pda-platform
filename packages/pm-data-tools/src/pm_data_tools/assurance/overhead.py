"""Assurance Overhead Optimiser for measuring and improving assurance efficiency.

Assurance activities consume project time and budget.  Without measurement,
organisations cannot tell whether they are investing too little (missing real
issues) or too much (redundant checks that add overhead without improving
outcomes).  Common symptoms include the same artefact being reviewed across
multiple gates, low-value reviews persisting because they have always been
done, and review frequency that does not adapt to project risk.

This module tracks assurance effort invested, correlates it with confidence
outcomes, and identifies waste — duplicate checks, zero-finding reviews, and
activities with no measurable effect on project health.

Usage::

    from pm_data_tools.assurance.overhead import (
        AssuranceOverheadOptimiser,
        AssuranceActivity,
        ActivityType,
    )
    from datetime import date

    optimiser = AssuranceOverheadOptimiser()
    activity = AssuranceActivity(
        project_id="PROJ-001",
        activity_type=ActivityType.GATE_REVIEW,
        description="Stage gate 3 — delivery readiness",
        date=date(2026, 3, 20),
        effort_hours=16.0,
        participants=4,
        artefacts_reviewed=["risk-register-v3"],
        findings_count=3,
        confidence_before=72.0,
        confidence_after=78.5,
    )
    optimiser.log_activity(activity)
    analysis = optimiser.analyse("PROJ-001")
"""

from __future__ import annotations

import json
import uuid
from collections import Counter
from datetime import date, datetime, timezone
from enum import Enum

import structlog
from pydantic import BaseModel, Field

from ..db.store import AssuranceStore

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ActivityType(Enum):
    """Classification of an assurance activity.

    Attributes:
        GATE_REVIEW: A formal gate or stage review.
        DOCUMENT_REVIEW: Review of one or more project documents.
        COMPLIANCE_CHECK: A check against a standard or framework.
        RISK_ASSESSMENT: A risk identification or scoring exercise.
        STAKEHOLDER_REVIEW: A review involving external stakeholders.
        AUDIT: A formal audit by an independent party.
        OTHER: Any activity not covered by other categories.
    """

    GATE_REVIEW = "GATE_REVIEW"
    DOCUMENT_REVIEW = "DOCUMENT_REVIEW"
    COMPLIANCE_CHECK = "COMPLIANCE_CHECK"
    RISK_ASSESSMENT = "RISK_ASSESSMENT"
    STAKEHOLDER_REVIEW = "STAKEHOLDER_REVIEW"
    AUDIT = "AUDIT"
    OTHER = "OTHER"


class EfficiencyRating(Enum):
    """How efficiently assurance effort is being spent.

    Attributes:
        OPTIMAL: Good confidence outcomes relative to effort invested.
        UNDER_INVESTED: Low effort with poor outcomes — more assurance needed.
        OVER_INVESTED: High effort with no better outcomes — reduce frequency.
        MISALLOCATED: Effort going to the wrong activities (high duplication).
    """

    OPTIMAL = "OPTIMAL"
    UNDER_INVESTED = "UNDER_INVESTED"
    OVER_INVESTED = "OVER_INVESTED"
    MISALLOCATED = "MISALLOCATED"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class AssuranceActivity(BaseModel):
    """A single assurance activity with effort tracking.

    Attributes:
        id: Unique identifier (UUID4 by default).
        project_id: Project this activity belongs to.
        activity_type: Classification of the activity.
        description: What was done.
        date: Calendar date of the activity.
        effort_hours: Person-hours spent on this activity.
        participants: Number of people involved (default 1).
        artefacts_reviewed: Artefact IDs checked during this activity.
        findings_count: Number of findings or actions produced.
        confidence_before: NISTA compliance score before the activity (0–100).
        confidence_after: NISTA compliance score after the activity (0–100).
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str
    activity_type: ActivityType
    description: str
    date: date
    effort_hours: float
    participants: int = 1
    artefacts_reviewed: list[str] = Field(default_factory=list)
    findings_count: int = 0
    confidence_before: float | None = None
    confidence_after: float | None = None


class DuplicateCheckResult(BaseModel):
    """Result of duplicate activity detection.

    Attributes:
        activity_id: The ID of the later activity flagged as a duplicate.
        duplicate_of: ID of the earlier activity this duplicates.
        overlap_type: Classification — ``"same_artefact"``,
            ``"same_type_same_week"``, or ``"no_findings_repeat"``.
        detail: Human-readable explanation of the overlap.
    """

    activity_id: str
    duplicate_of: str
    overlap_type: str
    detail: str


class OverheadAnalysis(BaseModel):
    """Complete overhead analysis for a project.

    Attributes:
        project_id: The analysed project.
        timestamp: When the analysis was generated (UTC).
        total_activities: Total number of logged activities.
        total_effort_hours: Sum of ``effort_hours`` across all activities.
        total_participants_hours: Sum of ``effort_hours × participants``.
        effort_by_type: Total hours per :class:`ActivityType` value.
        activities_with_findings: Activities that produced at least 1 finding.
        activities_without_findings: Activities that produced 0 findings.
        finding_rate: Proportion of activities producing findings (0–1).
        avg_confidence_lift: Average ``(confidence_after − confidence_before)``
            where both values are available.  ``None`` if no paired data.
        duplicate_checks: List of detected :class:`DuplicateCheckResult` objects.
        efficiency_rating: Overall :class:`EfficiencyRating` classification.
        recommendations: Human-readable optimisation suggestions.
        message: One-line summary.
    """

    project_id: str
    timestamp: datetime
    total_activities: int
    total_effort_hours: float
    total_participants_hours: float
    effort_by_type: dict[str, float]
    activities_with_findings: int
    activities_without_findings: int
    finding_rate: float
    avg_confidence_lift: float | None
    duplicate_checks: list[DuplicateCheckResult]
    efficiency_rating: EfficiencyRating
    recommendations: list[str]
    message: str


# ---------------------------------------------------------------------------
# Core class
# ---------------------------------------------------------------------------


class AssuranceOverheadOptimiser:
    """Measure and optimise the efficiency of assurance activities.

    Tracks the effort invested in assurance, correlates it with confidence
    outcomes, and identifies waste patterns: duplicate checks, zero-finding
    reviews, and activities with no measurable impact on project health.

    Example::

        from pm_data_tools.db.store import AssuranceStore

        store = AssuranceStore()
        optimiser = AssuranceOverheadOptimiser(store=store)

        activity = AssuranceActivity(
            project_id="PROJ-001",
            activity_type=ActivityType.GATE_REVIEW,
            description="Stage gate 2",
            date=date(2026, 1, 15),
            effort_hours=8.0,
            participants=3,
            findings_count=2,
        )
        optimiser.log_activity(activity)
        analysis = optimiser.analyse("PROJ-001")
    """

    def __init__(self, store: AssuranceStore | None = None) -> None:
        """Initialise the optimiser.

        Args:
            store: Shared :class:`~pm_data_tools.db.store.AssuranceStore`.
                A default store is created if not provided.
        """
        self._store = store or AssuranceStore()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_activity(row: dict[str, object]) -> AssuranceActivity:
        """Deserialise a database row to an :class:`AssuranceActivity`.

        Args:
            row: A dict with the columns of the ``assurance_activities`` table.

        Returns:
            The reconstructed :class:`AssuranceActivity`.
        """
        cb = row.get("confidence_before")
        ca = row.get("confidence_after")
        return AssuranceActivity(
            id=str(row["id"]),
            project_id=str(row["project_id"]),
            activity_type=ActivityType(str(row["activity_type"])),
            description=str(row["description"]),
            date=date.fromisoformat(str(row["date"])),
            effort_hours=float(row["effort_hours"]),  # type: ignore[arg-type]
            participants=int(row["participants"]),  # type: ignore[arg-type]
            artefacts_reviewed=json.loads(str(row.get("artefacts_reviewed", "[]"))),
            findings_count=int(row["findings_count"]),  # type: ignore[arg-type]
            confidence_before=float(cb) if cb is not None else None,  # type: ignore[arg-type]
            confidence_after=float(ca) if ca is not None else None,  # type: ignore[arg-type]
        )

    # ------------------------------------------------------------------
    # Logging
    # ------------------------------------------------------------------

    def log_activity(self, activity: AssuranceActivity) -> AssuranceActivity:
        """Persist an assurance activity to the store.

        Args:
            activity: The :class:`AssuranceActivity` to log.

        Returns:
            The same activity object (with its auto-generated ``id``).
        """
        self._store.upsert_assurance_activity(
            {
                "id": activity.id,
                "project_id": activity.project_id,
                "activity_type": activity.activity_type.value,
                "description": activity.description,
                "date": activity.date.isoformat(),
                "effort_hours": activity.effort_hours,
                "participants": activity.participants,
                "artefacts_reviewed": json.dumps(activity.artefacts_reviewed),
                "findings_count": activity.findings_count,
                "confidence_before": activity.confidence_before,
                "confidence_after": activity.confidence_after,
                "created_at": datetime.now(tz=timezone.utc).isoformat(),
            }
        )
        logger.info(
            "activity_logged",
            id=activity.id,
            project_id=activity.project_id,
            activity_type=activity.activity_type.value,
        )
        return activity

    # ------------------------------------------------------------------
    # Retrieval
    # ------------------------------------------------------------------

    def get_activities(
        self,
        project_id: str,
        activity_type: ActivityType | None = None,
    ) -> list[AssuranceActivity]:
        """Retrieve activities for a project, optionally filtered by type.

        Args:
            project_id: The project identifier.
            activity_type: Optional :class:`ActivityType` filter.

        Returns:
            List of :class:`AssuranceActivity` objects ordered by date ascending.
        """
        rows = self._store.get_assurance_activities(
            project_id=project_id,
            activity_type=activity_type.value if activity_type is not None else None,
        )
        return [self._row_to_activity(row) for row in rows]

    # ------------------------------------------------------------------
    # Duplicate detection
    # ------------------------------------------------------------------

    def detect_duplicates(self, project_id: str) -> list[DuplicateCheckResult]:
        """Identify duplicate or overlapping assurance activities.

        Three detection rules are applied in order of priority:

        1. **same_artefact**: Two activities reviewing the same artefact
           within 14 days.
        2. **same_type_same_week**: Two activities of the same type within
           7 days.
        3. **no_findings_repeat**: An activity of the same type that produced
           0 findings, following a previous 0-findings activity of the same
           type within 30 days.

        Each later activity is flagged at most once (against the earliest
        overlapping earlier activity).

        Args:
            project_id: The project identifier.

        Returns:
            List of :class:`DuplicateCheckResult` objects.
        """
        activities = self.get_activities(project_id)
        duplicates: list[DuplicateCheckResult] = []
        flagged_ids: set[str] = set()

        for i, earlier in enumerate(activities):
            for later in activities[i + 1 :]:
                if later.id in flagged_ids:
                    continue

                days_apart = abs((later.date - earlier.date).days)

                # Rule 1: same artefact within 14 days
                shared = set(earlier.artefacts_reviewed) & set(later.artefacts_reviewed)
                if shared and days_apart <= 14:
                    duplicates.append(
                        DuplicateCheckResult(
                            activity_id=later.id,
                            duplicate_of=earlier.id,
                            overlap_type="same_artefact",
                            detail=(
                                f"Both activities reviewed artefact(s) "
                                f"{', '.join(sorted(shared))} within {days_apart} day(s)."
                            ),
                        )
                    )
                    flagged_ids.add(later.id)
                    continue

                # Rule 2: same type within 7 days
                if earlier.activity_type == later.activity_type and days_apart <= 7:
                    duplicates.append(
                        DuplicateCheckResult(
                            activity_id=later.id,
                            duplicate_of=earlier.id,
                            overlap_type="same_type_same_week",
                            detail=(
                                f"Two {earlier.activity_type.value} activities "
                                f"within {days_apart} day(s)."
                            ),
                        )
                    )
                    flagged_ids.add(later.id)
                    continue

                # Rule 3: same type, both 0 findings, within 30 days
                if (
                    earlier.activity_type == later.activity_type
                    and earlier.findings_count == 0
                    and later.findings_count == 0
                    and days_apart <= 30
                ):
                    duplicates.append(
                        DuplicateCheckResult(
                            activity_id=later.id,
                            duplicate_of=earlier.id,
                            overlap_type="no_findings_repeat",
                            detail=(
                                f"Both {earlier.activity_type.value} activities produced "
                                f"0 findings within {days_apart} day(s)."
                            ),
                        )
                    )
                    flagged_ids.add(later.id)

        logger.debug(
            "duplicates_detected",
            project_id=project_id,
            count=len(duplicates),
        )
        return duplicates

    # ------------------------------------------------------------------
    # Efficiency classification
    # ------------------------------------------------------------------

    def compute_efficiency(self, project_id: str) -> EfficiencyRating:
        """Classify overall assurance efficiency for a project.

        Classification logic (evaluated in order):

        1. If ``total_effort_hours < 10`` and ``avg_confidence_lift`` is
           ``None`` or negative → :attr:`~EfficiencyRating.UNDER_INVESTED`.
        2. If ``finding_rate < 0.20`` and ``total_effort_hours > 40``
           → :attr:`~EfficiencyRating.OVER_INVESTED`.
        3. If ``duplicate_count > total_activities × 0.30``
           → :attr:`~EfficiencyRating.MISALLOCATED`.
        4. Otherwise → :attr:`~EfficiencyRating.OPTIMAL`.

        Args:
            project_id: The project identifier.

        Returns:
            An :class:`EfficiencyRating`.
        """
        activities = self.get_activities(project_id)
        total = len(activities)

        if total == 0:
            return EfficiencyRating.UNDER_INVESTED

        total_hours = sum(a.effort_hours for a in activities)
        with_findings = sum(1 for a in activities if a.findings_count > 0)
        finding_rate = with_findings / total

        lifts = [
            (a.confidence_after - a.confidence_before)
            for a in activities
            if a.confidence_before is not None and a.confidence_after is not None
        ]
        avg_lift: float | None = sum(lifts) / len(lifts) if lifts else None

        duplicates = self.detect_duplicates(project_id)
        dup_ratio = len(duplicates) / total

        if total_hours < 10 and (avg_lift is None or avg_lift < 0):
            return EfficiencyRating.UNDER_INVESTED
        if finding_rate < 0.20 and total_hours > 40:
            return EfficiencyRating.OVER_INVESTED
        if dup_ratio > 0.30:
            return EfficiencyRating.MISALLOCATED
        return EfficiencyRating.OPTIMAL

    # ------------------------------------------------------------------
    # Recommendations
    # ------------------------------------------------------------------

    def generate_recommendations(self, project_id: str) -> list[str]:
        """Generate human-readable optimisation suggestions.

        Suggestions are based on:

        - Duplicate checks → consolidation advice.
        - Zero-finding activity types → frequency reduction advice.
        - Low or negative confidence lift → activity objective review.
        - High effort concentration → redistribution advice.

        Args:
            project_id: The project identifier.

        Returns:
            List of recommendation strings.
        """
        activities = self.get_activities(project_id)
        recommendations: list[str] = []
        total = len(activities)

        if total == 0:
            return [
                "No assurance activities recorded — consider logging gate reviews "
                "and compliance checks."
            ]

        # Duplicate checks
        duplicates = self.detect_duplicates(project_id)
        if duplicates:
            dup_types: Counter[str] = Counter(d.overlap_type for d in duplicates)
            for overlap_type, count in dup_types.items():
                label = overlap_type.replace("_", " ")
                recommendations.append(
                    f"Consider consolidating {count} overlapping {label} "
                    f"activity/activities."
                )

        # Zero-finding activity types
        type_findings: dict[str, list[int]] = {}
        for a in activities:
            type_findings.setdefault(a.activity_type.value, []).append(a.findings_count)
        for atype, findings in type_findings.items():
            if findings and all(f == 0 for f in findings):
                recommendations.append(
                    f"{atype} has produced no findings across {len(findings)} "
                    f"activity/activities — consider reducing frequency or "
                    f"changing scope."
                )

        # Low confidence lift by type
        type_lifts: dict[str, list[float]] = {}
        for a in activities:
            if a.confidence_before is not None and a.confidence_after is not None:
                lift = a.confidence_after - a.confidence_before
                type_lifts.setdefault(a.activity_type.value, []).append(lift)
        for atype, lifts in type_lifts.items():
            avg = sum(lifts) / len(lifts)
            if avg <= 0:
                recommendations.append(
                    f"{atype} shows no measurable improvement in compliance scores "
                    f"(average lift: {avg:+.1f}) — review activity objectives."
                )

        # High effort concentration
        total_hours = sum(a.effort_hours for a in activities)
        if total_hours > 0:
            type_hours: dict[str, float] = {}
            for a in activities:
                type_hours[a.activity_type.value] = (
                    type_hours.get(a.activity_type.value, 0.0) + a.effort_hours
                )
            for atype, hours in type_hours.items():
                pct = hours / total_hours
                if pct > 0.60:
                    recommendations.append(
                        f"{pct:.0%} of assurance effort is concentrated in "
                        f"{atype} — consider whether to redistribute effort "
                        f"across other activity types."
                    )

        return recommendations

    # ------------------------------------------------------------------
    # Full analysis
    # ------------------------------------------------------------------

    def analyse(self, project_id: str) -> OverheadAnalysis:
        """Run a complete overhead analysis for a project.

        Computes all metrics, detects duplicates, classifies efficiency,
        and generates recommendations.  Persists the result to the store
        when available.

        Args:
            project_id: The project identifier.

        Returns:
            An :class:`OverheadAnalysis` with all fields populated.
        """
        activities = self.get_activities(project_id)
        total = len(activities)
        timestamp = datetime.now(tz=timezone.utc)

        total_hours = sum(a.effort_hours for a in activities)
        total_participant_hours = sum(
            a.effort_hours * a.participants for a in activities
        )

        effort_by_type: dict[str, float] = {}
        for a in activities:
            effort_by_type[a.activity_type.value] = (
                effort_by_type.get(a.activity_type.value, 0.0) + a.effort_hours
            )

        with_findings = sum(1 for a in activities if a.findings_count > 0)
        without_findings = total - with_findings
        finding_rate = with_findings / total if total > 0 else 0.0

        lifts = [
            (a.confidence_after - a.confidence_before)
            for a in activities
            if a.confidence_before is not None and a.confidence_after is not None
        ]
        avg_lift: float | None = sum(lifts) / len(lifts) if lifts else None

        duplicates = self.detect_duplicates(project_id)
        efficiency_rating = self.compute_efficiency(project_id)
        recs = self.generate_recommendations(project_id)

        if total == 0:
            message = f"No assurance activities recorded for project '{project_id}'."
        else:
            message = (
                f"{total} assurance activity/activities recorded for '{project_id}'.  "
                f"Total effort: {total_hours:.1f} hours.  "
                f"Finding rate: {finding_rate:.0%}.  "
                f"Efficiency: {efficiency_rating.value}."
            )

        analysis = OverheadAnalysis(
            project_id=project_id,
            timestamp=timestamp,
            total_activities=total,
            total_effort_hours=total_hours,
            total_participants_hours=total_participant_hours,
            effort_by_type=effort_by_type,
            activities_with_findings=with_findings,
            activities_without_findings=without_findings,
            finding_rate=finding_rate,
            avg_confidence_lift=avg_lift,
            duplicate_checks=duplicates,
            efficiency_rating=efficiency_rating,
            recommendations=recs,
            message=message,
        )

        self._store.insert_overhead_analysis(
            project_id=project_id,
            timestamp=timestamp.isoformat(),
            analysis_json=analysis.model_dump_json(),
        )

        logger.info(
            "overhead_analysed",
            project_id=project_id,
            total=total,
            efficiency=efficiency_rating.value,
            duplicates=len(duplicates),
        )
        return analysis
