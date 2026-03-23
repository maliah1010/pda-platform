"""Assurance module: recommendation extraction, tracking, and recurrence detection.

This module provides tools for extracting, persisting, and tracking assurance
recommendations from project review documents.  It uses the
``agent-task-planning`` :class:`~agent_planning.confidence.ConfidenceExtractor`
for reliable AI extraction and stores results in the shared SQLite store.

Public API::

    from pm_data_tools.assurance import (
        Recommendation,
        RecommendationExtractionResult,
        RecommendationExtractor,
        RecommendationStatus,
        RecurrenceDetector,
    )
"""

from .extractor import RecommendationExtractor
from .models import (
    Recommendation,
    RecommendationExtractionResult,
    RecommendationStatus,
)
from .recurrence import RecurrenceDetector

__all__ = [
    "Recommendation",
    "RecommendationExtractionResult",
    "RecommendationExtractor",
    "RecommendationStatus",
    "RecurrenceDetector",
]
