"""Assumption Drift Tracker (P11).

Captures project assumptions with baseline values, monitors drift against
current values, detects staleness, and flags cascading impacts through
the assumption dependency graph.

Usage::

    from pm_data_tools.assurance.assumptions import (
        AssumptionTracker,
        Assumption,
        AssumptionCategory,
        AssumptionConfig,
        AssumptionSource,
        DriftSeverity,
    )
    from pm_data_tools.db.store import AssuranceStore

    store = AssuranceStore()
    tracker = AssumptionTracker(store=store)

    assumption = tracker.ingest(
        Assumption(
            project_id="PROJ-001",
            text="CPI inflation will remain below 3% through 2026",
            category=AssumptionCategory.COST,
            baseline_value=2.5,
            unit="%",
            tolerance_pct=20.0,
            source=AssumptionSource.EXTERNAL_API,
            external_ref="ONS_CPI",
        )
    )

    validation = tracker.update_value(
        assumption_id=assumption.id,
        new_value=3.8,
        notes="Updated from latest ONS release",
    )

    report = tracker.analyse_project("PROJ-001")
    # report.overall_drift_score → 0.0 – 1.0
"""

from __future__ import annotations

import json
import uuid
from collections import deque
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any

import structlog
from pydantic import BaseModel, Field

from ..db.store import AssuranceStore

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class AssumptionCategory(Enum):
    """Classification of assumption type.

    Attributes:
        COST: Cost estimates, inflation rates, budget allocations.
        SCHEDULE: Timeline assumptions, milestone dates, lead times.
        RESOURCE: Staff availability, skill availability, contractor rates.
        TECHNICAL: Technology choices, integration assumptions, performance.
        COMMERCIAL: Market conditions, supplier availability, pricing.
        REGULATORY: Policy assumptions, compliance requirements, legal.
        STAKEHOLDER: Stakeholder alignment, decision-making speed.
        EXTERNAL: External factors: inflation, interest rates, exchange rates.
    """

    COST = "COST"
    SCHEDULE = "SCHEDULE"
    RESOURCE = "RESOURCE"
    TECHNICAL = "TECHNICAL"
    COMMERCIAL = "COMMERCIAL"
    REGULATORY = "REGULATORY"
    STAKEHOLDER = "STAKEHOLDER"
    EXTERNAL = "EXTERNAL"


class DriftSeverity(Enum):
    """How severely an assumption has drifted from its baseline.

    Attributes:
        NONE: No drift detected.
        MINOR: Within acceptable tolerance.
        MODERATE: Approaching tolerance boundary.
        SIGNIFICANT: Exceeds tolerance — action needed.
        CRITICAL: Far beyond tolerance — plan integrity at risk.
    """

    NONE = "NONE"
    MINOR = "MINOR"
    MODERATE = "MODERATE"
    SIGNIFICANT = "SIGNIFICANT"
    CRITICAL = "CRITICAL"


class AssumptionSource(Enum):
    """Where the assumption's current value comes from.

    Attributes:
        MANUAL: Manually entered/reviewed by project team.
        EXTERNAL_API: From an external data source (ONS, BoE, etc.).
        DERIVED: Calculated from other assumptions or project data.
    """

    MANUAL = "MANUAL"
    EXTERNAL_API = "EXTERNAL_API"
    DERIVED = "DERIVED"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class AssumptionConfig(BaseModel):
    """Configuration for assumption tracking.

    Attributes:
        staleness_days: Assumptions not validated within this window are stale.
        minor_threshold_pct: Drift below this → MINOR.
        moderate_threshold_pct: Below this → MODERATE.
        significant_threshold_pct: Below this → SIGNIFICANT, above → CRITICAL.
    """

    staleness_days: int = 30
    minor_threshold_pct: float = 5.0
    moderate_threshold_pct: float = 15.0
    significant_threshold_pct: float = 30.0


class Assumption(BaseModel):
    """A single project assumption with drift tracking.

    Attributes:
        id: Unique identifier (UUID4 by default).
        project_id: Project this assumption belongs to.
        text: Human-readable assumption statement.
        category: Classification of the assumption type.
        baseline_value: The original assumed value.
        current_value: Latest known value (None if not yet validated).
        unit: Measurement unit (e.g. "GBP", "%", "days", "FTE").
        tolerance_pct: Acceptable drift percentage before flagging.
        source: Where the current value comes from.
        external_ref: External data source identifier (e.g. "ONS_CPI").
        dependencies: IDs of assumptions this depends on.
        owner: Name or role responsible for this assumption.
        last_validated: Date of most recent validation.
        created_date: Date the assumption was first recorded.
        notes: Optional free-text notes.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str
    text: str
    category: AssumptionCategory
    baseline_value: float
    current_value: float | None = None
    unit: str = ""
    tolerance_pct: float = 10.0
    source: AssumptionSource = AssumptionSource.MANUAL
    external_ref: str | None = None
    dependencies: list[str] = Field(default_factory=list)
    owner: str | None = None
    last_validated: date | None = None
    created_date: date = Field(default_factory=date.today)
    notes: str | None = None


class AssumptionValidation(BaseModel):
    """Record of a single validation check against an assumption.

    Attributes:
        id: Unique identifier (UUID4 by default).
        assumption_id: The assumption being validated.
        validated_at: UTC timestamp of the validation.
        previous_value: Value prior to this update.
        new_value: The updated value.
        source: Where the new value came from.
        drift_pct: Percentage drift from the baseline value.
        severity: DriftSeverity classification for this update.
        notes: Optional notes about the validation.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    assumption_id: str
    validated_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )
    previous_value: float | None = None
    new_value: float
    source: AssumptionSource
    drift_pct: float
    severity: DriftSeverity
    notes: str | None = None


class DriftResult(BaseModel):
    """Result of a drift analysis for a single assumption.

    Attributes:
        assumption: The assumption being analysed.
        drift_pct: Absolute percentage drift from baseline.
        severity: Drift severity classification.
        days_since_validation: Days since last validation, or None.
        cascade_impact: IDs of downstream dependent assumptions.
        message: Human-readable description of the drift.
    """

    assumption: Assumption
    drift_pct: float
    severity: DriftSeverity
    days_since_validation: int | None
    cascade_impact: list[str]
    message: str


class AssumptionHealthReport(BaseModel):
    """Aggregate assumption health for a project.

    Attributes:
        project_id: The analysed project.
        timestamp: UTC timestamp of the analysis.
        total_assumptions: Total number of tracked assumptions.
        validated_count: Assumptions with at least one validation.
        stale_count: Assumptions not validated within staleness window.
        drift_results: Per-assumption drift analysis results.
        by_severity: Count per DriftSeverity value.
        by_category: Count per AssumptionCategory value.
        cascade_warnings: Human-readable cascade impact warnings.
        overall_drift_score: Composite drift severity (0–1).
        message: Human-readable report summary.
    """

    project_id: str
    timestamp: datetime
    total_assumptions: int
    validated_count: int
    stale_count: int
    drift_results: list[DriftResult]
    by_severity: dict[str, int]
    by_category: dict[str, int]
    cascade_warnings: list[str]
    overall_drift_score: float
    message: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_SEVERITY_WEIGHTS: dict[DriftSeverity, float] = {
    DriftSeverity.NONE: 0.0,
    DriftSeverity.MINOR: 0.2,
    DriftSeverity.MODERATE: 0.5,
    DriftSeverity.SIGNIFICANT: 0.8,
    DriftSeverity.CRITICAL: 1.0,
}


def _row_to_assumption(row: dict[str, Any]) -> Assumption:
    """Deserialise a database row to an :class:`Assumption`.

    Args:
        row: Dict from the ``assumptions`` table.

    Returns:
        Reconstructed :class:`Assumption`.
    """
    deps_raw = row.get("dependencies", "[]")
    deps = json.loads(str(deps_raw)) if isinstance(deps_raw, str) else []
    last_validated = None
    if row.get("last_validated"):
        last_validated = date.fromisoformat(str(row["last_validated"]))
    return Assumption(
        id=str(row["id"]),
        project_id=str(row["project_id"]),
        text=str(row["text"]),
        category=AssumptionCategory(str(row["category"])),
        baseline_value=float(row["baseline_value"]),
        current_value=float(row["current_value"]) if row.get("current_value") is not None else None,
        unit=str(row.get("unit", "")),
        tolerance_pct=float(row.get("tolerance_pct", 10.0)),
        source=AssumptionSource(str(row["source"])),
        external_ref=str(row["external_ref"]) if row.get("external_ref") else None,
        dependencies=deps,
        owner=str(row["owner"]) if row.get("owner") else None,
        last_validated=last_validated,
        created_date=date.fromisoformat(str(row["created_date"])),
        notes=str(row["notes"]) if row.get("notes") else None,
    )


def _row_to_validation(row: dict[str, Any]) -> AssumptionValidation:
    """Deserialise a database row to an :class:`AssumptionValidation`.

    Args:
        row: Dict from the ``assumption_validations`` table.

    Returns:
        Reconstructed :class:`AssumptionValidation`.
    """
    return AssumptionValidation(
        id=str(row["id"]),
        assumption_id=str(row["assumption_id"]),
        validated_at=datetime.fromisoformat(str(row["validated_at"])),
        previous_value=float(row["previous_value"]) if row.get("previous_value") is not None else None,
        new_value=float(row["new_value"]),
        source=AssumptionSource(str(row["source"])),
        drift_pct=float(row["drift_pct"]),
        severity=DriftSeverity(str(row["severity"])),
        notes=str(row["notes"]) if row.get("notes") else None,
    )


# ---------------------------------------------------------------------------
# Tracker
# ---------------------------------------------------------------------------


class AssumptionTracker:
    """Track, validate, and analyse assumption drift across projects.

    Captures project assumptions with baseline values, monitors drift
    against current values (manual or external), detects staleness,
    and flags cascading impacts through the assumption dependency graph.

    Example::

        store = AssuranceStore()
        tracker = AssumptionTracker(store=store)

        a = tracker.ingest(
            Assumption(
                project_id="PROJ-001",
                text="Inflation will stay below 3%",
                category=AssumptionCategory.COST,
                baseline_value=2.5,
                unit="%",
            )
        )
        tracker.update_value(a.id, new_value=3.8)
        report = tracker.analyse_project("PROJ-001")
    """

    def __init__(
        self,
        store: AssuranceStore | None = None,
        config: AssumptionConfig | None = None,
    ) -> None:
        """Initialise the assumption tracker.

        Args:
            store: Shared :class:`~pm_data_tools.db.store.AssuranceStore`.
                A default store is created if not provided.
            config: Tracking configuration.  Uses defaults if not provided.
        """
        self._store = store or AssuranceStore()
        self._config = config or AssumptionConfig()

    # ------------------------------------------------------------------
    # CRUD operations
    # ------------------------------------------------------------------

    def ingest(self, assumption: Assumption) -> Assumption:
        """Persist an assumption. Returns the assumption with its ID.

        Args:
            assumption: The :class:`Assumption` to persist.

        Returns:
            The same assumption object (with auto-generated ``id`` if unset).
        """
        self._store.upsert_assumption(
            {
                "id": assumption.id,
                "project_id": assumption.project_id,
                "text": assumption.text,
                "category": assumption.category.value,
                "baseline_value": assumption.baseline_value,
                "current_value": assumption.current_value,
                "unit": assumption.unit,
                "tolerance_pct": assumption.tolerance_pct,
                "source": assumption.source.value,
                "external_ref": assumption.external_ref,
                "dependencies": json.dumps(assumption.dependencies),
                "owner": assumption.owner,
                "last_validated": assumption.last_validated.isoformat() if assumption.last_validated else None,
                "created_date": assumption.created_date.isoformat(),
                "notes": assumption.notes,
            }
        )
        logger.info(
            "assumption_ingested",
            id=assumption.id,
            project_id=assumption.project_id,
            category=assumption.category.value,
        )
        return assumption

    def ingest_batch(self, assumptions: list[Assumption]) -> int:
        """Ingest multiple assumptions. Returns count ingested.

        Args:
            assumptions: List of :class:`Assumption` objects to persist.

        Returns:
            Number of assumptions successfully ingested.
        """
        count = 0
        for assumption in assumptions:
            self.ingest(assumption)
            count += 1
        logger.info("assumption_batch_ingested", count=count)
        return count

    def get_assumptions(
        self,
        project_id: str,
        category: AssumptionCategory | None = None,
    ) -> list[Assumption]:
        """Retrieve assumptions for a project, optionally filtered by category.

        Args:
            project_id: The project identifier.
            category: Optional :class:`AssumptionCategory` filter.

        Returns:
            List of :class:`Assumption` objects.
        """
        rows = self._store.get_assumptions(
            project_id=project_id,
            category=category.value if category is not None else None,
        )
        return [_row_to_assumption(r) for r in rows]

    def update_value(
        self,
        assumption_id: str,
        new_value: float,
        source: AssumptionSource = AssumptionSource.MANUAL,
        notes: str | None = None,
    ) -> AssumptionValidation:
        """Update an assumption's current value, record the validation, and compute drift.

        Args:
            assumption_id: ID of the :class:`Assumption` to update.
            new_value: The new current value.
            source: Where the new value came from.
            notes: Optional notes about this update.

        Returns:
            The created :class:`AssumptionValidation` record.

        Raises:
            ValueError: If no assumption with the given ID exists.
        """
        row = self._store.get_assumption_by_id(assumption_id)
        if row is None:
            raise ValueError(f"Assumption {assumption_id!r} not found")

        assumption = _row_to_assumption(row)
        previous_value = assumption.current_value

        # Compute drift
        if assumption.baseline_value != 0.0:
            drift_pct = abs((new_value - assumption.baseline_value) / assumption.baseline_value) * 100.0
        else:
            drift_pct = abs(new_value - assumption.baseline_value)

        severity = self._classify_drift(drift_pct)
        now = datetime.now(tz=timezone.utc)

        validation = AssumptionValidation(
            assumption_id=assumption_id,
            validated_at=now,
            previous_value=previous_value,
            new_value=new_value,
            source=source,
            drift_pct=drift_pct,
            severity=severity,
            notes=notes,
        )

        self._store.insert_assumption_validation(
            {
                "id": validation.id,
                "assumption_id": assumption_id,
                "validated_at": now.isoformat(),
                "previous_value": previous_value,
                "new_value": new_value,
                "source": source.value,
                "drift_pct": drift_pct,
                "severity": severity.value,
                "notes": notes,
            }
        )

        # Update the assumption's current_value and last_validated
        self._store.update_assumption_value(
            assumption_id=assumption_id,
            current_value=new_value,
            last_validated=now.date().isoformat(),
        )

        logger.info(
            "assumption_validated",
            assumption_id=assumption_id,
            drift_pct=round(drift_pct, 2),
            severity=severity.value,
        )
        return validation

    # ------------------------------------------------------------------
    # Drift analysis
    # ------------------------------------------------------------------

    def compute_drift(self, assumption: Assumption) -> DriftResult:
        """Compute drift for a single assumption.

        ``drift_pct = abs((current_value - baseline_value) / baseline_value) * 100``
        If ``baseline_value`` is 0, uses absolute difference instead.

        Severity mapping (using configured thresholds):

        - ``drift_pct <= minor_threshold`` → ``NONE``
        - ``drift_pct <= moderate_threshold`` → ``MINOR``
        - ``drift_pct <= significant_threshold`` → ``MODERATE``
        - ``drift_pct <= significant_threshold * 1.5`` → ``SIGNIFICANT``
        - above → ``CRITICAL``

        Args:
            assumption: The :class:`Assumption` to analyse.

        Returns:
            A :class:`DriftResult` with drift percentage, severity, and cascade impact.
        """
        if assumption.current_value is None:
            drift_pct = 0.0
            severity = DriftSeverity.NONE
        elif assumption.baseline_value != 0.0:
            drift_pct = abs(
                (assumption.current_value - assumption.baseline_value) / assumption.baseline_value
            ) * 100.0
        else:
            drift_pct = abs(assumption.current_value - assumption.baseline_value)
            severity = DriftSeverity.NONE  # will be overwritten below

        if assumption.current_value is not None:
            severity = self._classify_drift(drift_pct)

        # Cascade impact
        cascade = self.get_cascade_impact(assumption.id)

        # Staleness
        days_since: int | None = None
        if assumption.last_validated is not None:
            days_since = (date.today() - assumption.last_validated).days

        if assumption.current_value is None:
            msg = (
                f"Assumption '{assumption.text[:60]}' has not been validated yet."
            )
        else:
            msg = (
                f"Assumption '{assumption.text[:60]}' has drifted "
                f"{drift_pct:.1f}% from baseline "
                f"({assumption.baseline_value} → {assumption.current_value} "
                f"{assumption.unit}).  Severity: {severity.value}."
            )
            if cascade:
                msg += f"  {len(cascade)} downstream assumption(s) may be affected."

        return DriftResult(
            assumption=assumption,
            drift_pct=round(drift_pct, 2),
            severity=severity,
            days_since_validation=days_since,
            cascade_impact=cascade,
            message=msg,
        )

    def analyse_project(self, project_id: str) -> AssumptionHealthReport:
        """Run a complete assumption health analysis for a project.

        Computes drift for all assumptions, detects stale assumptions,
        builds cascade warnings, and produces an overall drift score.

        ``overall_drift_score`` is the weighted average of individual drift
        severities (NONE=0, MINOR=0.2, MODERATE=0.5, SIGNIFICANT=0.8, CRITICAL=1.0).

        Args:
            project_id: The project identifier.

        Returns:
            An :class:`AssumptionHealthReport` with full per-assumption detail.
        """
        now = datetime.now(tz=timezone.utc)
        assumptions = self.get_assumptions(project_id)

        if not assumptions:
            return AssumptionHealthReport(
                project_id=project_id,
                timestamp=now,
                total_assumptions=0,
                validated_count=0,
                stale_count=0,
                drift_results=[],
                by_severity={},
                by_category={},
                cascade_warnings=[],
                overall_drift_score=0.0,
                message=f"No assumptions tracked for project '{project_id}'.",
            )

        drift_results = [self.compute_drift(a) for a in assumptions]
        stale = self.get_stale_assumptions(project_id)

        validated_count = sum(1 for a in assumptions if a.last_validated is not None)

        # Counts
        by_severity: dict[str, int] = {s.value: 0 for s in DriftSeverity}
        by_category: dict[str, int] = {c.value: 0 for c in AssumptionCategory}
        for dr in drift_results:
            by_severity[dr.severity.value] += 1
            by_category[dr.assumption.category.value] += 1

        # Cascade warnings
        cascade_warnings: list[str] = []
        for dr in drift_results:
            if dr.severity in (DriftSeverity.SIGNIFICANT, DriftSeverity.CRITICAL) and dr.cascade_impact:
                cascade_warnings.append(
                    f"'{dr.assumption.text[:60]}' ({dr.severity.value}) "
                    f"affects {len(dr.cascade_impact)} downstream assumption(s): "
                    f"{', '.join(dr.cascade_impact[:3])}{'...' if len(dr.cascade_impact) > 3 else ''}."
                )

        # Overall drift score — weighted average
        if drift_results:
            weights = [_SEVERITY_WEIGHTS[dr.severity] for dr in drift_results]
            overall_drift_score = round(sum(weights) / len(weights), 3)
        else:
            overall_drift_score = 0.0

        critical_count = by_severity.get(DriftSeverity.CRITICAL.value, 0)
        significant_count = by_severity.get(DriftSeverity.SIGNIFICANT.value, 0)

        message = (
            f"{len(assumptions)} assumption(s) tracked for project '{project_id}'.  "
            f"{critical_count} CRITICAL, {significant_count} SIGNIFICANT.  "
            f"{len(stale)} stale.  "
            f"Overall drift score: {overall_drift_score:.3f}."
        )

        logger.info(
            "assumption_health_analysed",
            project_id=project_id,
            total=len(assumptions),
            overall_drift_score=overall_drift_score,
            critical=critical_count,
            stale=len(stale),
        )

        return AssumptionHealthReport(
            project_id=project_id,
            timestamp=now,
            total_assumptions=len(assumptions),
            validated_count=validated_count,
            stale_count=len(stale),
            drift_results=drift_results,
            by_severity=by_severity,
            by_category=by_category,
            cascade_warnings=cascade_warnings,
            overall_drift_score=overall_drift_score,
            message=message,
        )

    # ------------------------------------------------------------------
    # Cascade analysis
    # ------------------------------------------------------------------

    def get_cascade_impact(self, assumption_id: str) -> list[str]:
        """Find all assumptions that depend on the given assumption (direct + transitive).

        Walks the dependency graph breadth-first. Returns IDs of all
        assumptions that would be affected if this assumption drifts.
        Handles cycles by tracking visited nodes.

        Args:
            assumption_id: The source assumption ID.

        Returns:
            List of affected assumption IDs (excluding the source itself).
        """
        # Build reverse map: which assumptions list assumption_id in their deps?
        # We need all assumptions, so use the store directly for efficiency.
        # First, get project_id from the assumption.
        row = self._store.get_assumption_by_id(assumption_id)
        if row is None:
            return []

        project_id = str(row["project_id"])
        all_assumptions = self.get_assumptions(project_id)

        # Build reverse adjacency: assumption_id -> [assumptions that depend on it]
        reverse_graph: dict[str, list[str]] = {a.id: [] for a in all_assumptions}
        for a in all_assumptions:
            for dep_id in a.dependencies:
                if dep_id in reverse_graph:
                    reverse_graph[dep_id].append(a.id)

        # BFS from assumption_id
        visited: set[str] = set()
        queue: deque[str] = deque([assumption_id])
        visited.add(assumption_id)

        while queue:
            current = queue.popleft()
            for dependent_id in reverse_graph.get(current, []):
                if dependent_id not in visited:
                    visited.add(dependent_id)
                    queue.append(dependent_id)

        # Exclude the source itself
        visited.discard(assumption_id)
        return list(visited)

    def get_dependency_graph(self, project_id: str) -> dict[str, list[str]]:
        """Build the full dependency graph for a project.

        Returns ``{assumption_id: [list of assumptions that depend on it]}``.

        Args:
            project_id: The project identifier.

        Returns:
            Reverse adjacency dict mapping each assumption to its dependents.
        """
        assumptions = self.get_assumptions(project_id)
        graph: dict[str, list[str]] = {a.id: [] for a in assumptions}

        for a in assumptions:
            for dep_id in a.dependencies:
                if dep_id in graph:
                    graph[dep_id].append(a.id)

        return graph

    # ------------------------------------------------------------------
    # Staleness detection
    # ------------------------------------------------------------------

    def get_stale_assumptions(self, project_id: str) -> list[Assumption]:
        """Find assumptions not validated within the configured staleness window.

        Args:
            project_id: The project identifier.

        Returns:
            List of stale :class:`Assumption` objects.
        """
        assumptions = self.get_assumptions(project_id)
        cutoff = date.today()
        stale: list[Assumption] = []

        for a in assumptions:
            if a.last_validated is None:
                # Never validated — always stale if assumption is more than
                # staleness_days old
                days_old = (cutoff - a.created_date).days
                if days_old >= self._config.staleness_days:
                    stale.append(a)
            else:
                days_since = (cutoff - a.last_validated).days
                if days_since >= self._config.staleness_days:
                    stale.append(a)

        return stale

    # ------------------------------------------------------------------
    # Validation history
    # ------------------------------------------------------------------

    def get_validation_history(self, assumption_id: str) -> list[AssumptionValidation]:
        """Retrieve all validation records for an assumption, oldest first.

        Args:
            assumption_id: The assumption identifier.

        Returns:
            List of :class:`AssumptionValidation` objects ordered oldest first.
        """
        rows = self._store.get_assumption_validations(assumption_id)
        return [_row_to_validation(r) for r in rows]

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _classify_drift(self, drift_pct: float) -> DriftSeverity:
        """Map a drift percentage to a :class:`DriftSeverity` using configured thresholds.

        Args:
            drift_pct: Absolute drift percentage (0–∞).

        Returns:
            The appropriate :class:`DriftSeverity`.
        """
        c = self._config
        if drift_pct <= c.minor_threshold_pct:
            return DriftSeverity.NONE
        if drift_pct <= c.moderate_threshold_pct:
            return DriftSeverity.MINOR
        if drift_pct <= c.significant_threshold_pct:
            return DriftSeverity.MODERATE
        if drift_pct <= c.significant_threshold_pct * 1.5:
            return DriftSeverity.SIGNIFICANT
        return DriftSeverity.CRITICAL
