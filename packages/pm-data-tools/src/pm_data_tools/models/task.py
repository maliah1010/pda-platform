"""Task model for project management data.

Tasks represent work items in a project, including activities, milestones,
and summary tasks. This module provides the canonical Task model with
schedule, progress, cost, and work tracking.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from uuid import UUID

from .base import CustomField, Duration, Money, SourceInfo


class TaskStatus(Enum):
    """Universal task status."""

    NOT_STARTED = "not_started"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    ON_HOLD = "on_hold"
    CANCELLED = "cancelled"


class ConstraintType(Enum):
    """Task scheduling constraint types."""

    ASAP = "ASAP"  # As Soon As Possible
    ALAP = "ALAP"  # As Late As Possible
    SNET = "SNET"  # Start No Earlier Than
    SNLT = "SNLT"  # Start No Later Than
    FNET = "FNET"  # Finish No Earlier Than
    FNLT = "FNLT"  # Finish No Later Than
    MSO = "MSO"  # Must Start On
    MFO = "MFO"  # Must Finish On


@dataclass(frozen=True)
class Task:
    """Canonical task/activity model.

    Represents a work item in a project with schedule, progress, cost, and
    work tracking. Supports hierarchical WBS structure, dependencies,
    resource assignments, and extensible custom fields.
    """

    # Identity
    id: UUID
    name: str
    source: SourceInfo

    # Hierarchy
    wbs_code: str | None = None
    outline_level: int = 1
    parent_id: UUID | None = None

    # Schedule
    start_date: datetime | None = None
    finish_date: datetime | None = None
    actual_start: datetime | None = None
    actual_finish: datetime | None = None
    duration: Duration | None = None
    actual_duration: Duration | None = None
    remaining_duration: Duration | None = None

    # Progress
    percent_complete: float = 0.0
    status: TaskStatus = TaskStatus.NOT_STARTED

    # Constraints
    constraint_type: ConstraintType | None = None
    constraint_date: datetime | None = None
    deadline: datetime | None = None

    # Flags
    is_milestone: bool = False
    is_summary: bool = False
    is_critical: bool = False

    # Cost
    budgeted_cost: Money | None = None
    actual_cost: Money | None = None
    remaining_cost: Money | None = None

    # Work
    budgeted_work: Duration | None = None
    actual_work: Duration | None = None
    remaining_work: Duration | None = None

    # Text
    description: str | None = None
    notes: str | None = None

    # Extensions
    custom_fields: list[CustomField] = field(default_factory=list)

    def __str__(self) -> str:
        """String representation."""
        parts = [f"Task({self.name}"]
        if self.wbs_code:
            parts.append(f", WBS={self.wbs_code}")
        if self.is_milestone:
            parts.append(", Milestone")
        if self.is_summary:
            parts.append(", Summary")
        if self.is_critical:
            parts.append(", Critical")
        parts.append(f", {self.percent_complete}% complete")
        return "".join(parts) + ")"

    @property
    def is_complete(self) -> bool:
        """Check if task is 100% complete.

        Returns:
            True if task is fully complete (100% or has actual finish date).
        """
        return self.percent_complete >= 100.0 or self.actual_finish is not None

    @property
    def is_started(self) -> bool:
        """Check if task has started.

        Returns:
            True if task has started (has progress or actual start date).
        """
        return self.percent_complete > 0.0 or self.actual_start is not None

    @property
    def cost_variance(self) -> Money | None:
        """Calculate cost variance (budgeted - actual).

        Returns:
            Cost variance, or None if either budgeted or actual cost is missing.
        """
        if self.budgeted_cost and self.actual_cost:
            return self.budgeted_cost - self.actual_cost
        return None

    @property
    def schedule_variance_days(self) -> float | None:
        """Calculate schedule variance in days (planned finish - actual/forecast finish).

        Returns:
            Schedule variance in days, or None if dates missing.
        """
        if not self.finish_date:
            return None

        comparison_date = self.actual_finish if self.actual_finish else datetime.now()
        delta = self.finish_date - comparison_date
        return delta.total_seconds() / 86400  # Convert to days
