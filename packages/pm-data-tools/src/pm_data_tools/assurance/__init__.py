"""Assurance module: cross-cycle finding analysis and recurrence detection.

This module provides tools for extracting, persisting, and tracking review
actions from project review documents across multiple review cycles.  It uses
the ``agent-task-planning`` :class:`~agent_planning.confidence.ConfidenceExtractor`
for reliable AI extraction and stores results in the shared SQLite store.

Public API::

    from pm_data_tools.assurance import (
        ReviewAction,
        FindingAnalysisResult,
        FindingAnalyzer,
        ReviewActionStatus,
        RecurrenceDetector,
    )
"""

from .analyzer import FindingAnalyzer
from .models import (
    FindingAnalysisResult,
    ReviewAction,
    ReviewActionStatus,
    # Backward-compatibility aliases
    Recommendation,
    RecommendationExtractionResult,
    RecommendationStatus,
)
from .recurrence import RecurrenceDetector

# Backward-compatibility alias for FindingAnalyzer
RecommendationExtractor = FindingAnalyzer

__all__ = [
    # Current names
    "ReviewAction",
    "FindingAnalysisResult",
    "FindingAnalyzer",
    "ReviewActionStatus",
    "RecurrenceDetector",
    # Deprecated aliases — will be removed in v0.5.0
    "Recommendation",
    "RecommendationExtractionResult",
    "RecommendationExtractor",
    "RecommendationStatus",
]
