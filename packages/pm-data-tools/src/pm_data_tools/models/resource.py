"""Resource model for project management data.

Resources represent people, equipment, materials, or costs that can be
assigned to tasks. This module provides the canonical Resource model with
capacity, rate, and cost tracking.
"""

from dataclasses import dataclass, field
from enum import Enum
from uuid import UUID

from .base import CustomField, Money, SourceInfo


class ResourceType(Enum):
    """Resource types."""

    WORK = "work"  # People/labour
    MATERIAL = "material"  # Consumables
    COST = "cost"  # Fixed costs
    EQUIPMENT = "equipment"  # Equipment/machinery


@dataclass(frozen=True)
class Resource:
    """Canonical resource model.

    Represents a resource (person, material, equipment, or cost) that can be
    assigned to tasks. Includes capacity, rates, and grouping information.
    """

    # Identity
    id: UUID
    name: str
    source: SourceInfo

    # Type
    resource_type: ResourceType = ResourceType.WORK

    # Capacity
    max_units: float = 1.0  # 1.0 = 100% availability

    # Rates
    standard_rate: Money | None = None  # Per hour for work resources
    overtime_rate: Money | None = None
    cost_per_use: Money | None = None  # One-time cost per assignment

    # Contact
    email: str | None = None

    # Grouping
    group: str | None = None  # Department, team, etc.

    # Extensions
    custom_fields: list[CustomField] = field(default_factory=list)

    def __str__(self) -> str:
        """String representation."""
        return f"Resource({self.name}, {self.resource_type.value}, {self.max_units * 100}% available)"

    @property
    def is_overallocated(self) -> bool:
        """Check if resource is overallocated (> 100%).

        Returns:
            True if max_units > 1.0.
        """
        return self.max_units > 1.0

    @property
    def availability_percent(self) -> float:
        """Get availability as percentage.

        Returns:
            Availability percentage (100 = full-time).
        """
        return self.max_units * 100.0
