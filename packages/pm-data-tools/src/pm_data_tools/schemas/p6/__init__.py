"""Primavera P6 schema support.

This module provides parsers and writers for Primavera P6 project data
in both XER (text) and PMXML (XML) formats.
"""

from .constants import (
    ActivityStatus,
    ActivityType,
    RelationshipType,
    ResourceType,
)

__all__ = [
    "ActivityType",
    "ActivityStatus",
    "RelationshipType",
    "ResourceType",
]
