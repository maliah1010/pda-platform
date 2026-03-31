"""Data models for the cross-cycle finding analyzer.

These models represent the lifecycle of a review action from initial
extraction through to closure or recurrence detection.
"""

from __future__ import annotations

import uuid
from datetime import date
from enum import Enum

from pydantic import BaseModel, Field


class ReviewActionStatus(Enum):
    """Lifecycle status of a tracked review action.

    Attributes:
        OPEN: Newly extracted; no action taken yet.
        IN_PROGRESS: Being actively addressed.
        CLOSED: Resolved and closed.
        RECURRING: Identified as recurring from a prior review cycle.
    """

    OPEN = "OPEN"
    IN_PROGRESS = "IN_PROGRESS"
    CLOSED = "CLOSED"
    RECURRING = "RECURRING"


class ReviewAction(BaseModel):
    """A single review action extracted from a project review.

    Attributes:
        id: Unique identifier (UUID4 by default).
        text: The recommended action text.
        category: Classification of the action (e.g. priority level).
        source_review_id: Identifier of the review document this came from.
        review_date: Date of the source review.
        status: Current lifecycle status.
        owner: Optional responsible party.
        recurrence_of: Optional ID of a prior action this recurs from.
        confidence: Extraction confidence score (0.0-1.0) from
            :class:`~agent_planning.confidence.ConfidenceExtractor`.
        flagged_for_review: Whether confidence was below the auto-accept
            threshold.  Low-confidence items are flagged, not rejected.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    text: str
    category: str
    source_review_id: str
    review_date: date
    status: ReviewActionStatus = ReviewActionStatus.OPEN
    owner: str | None = None
    recurrence_of: str | None = None
    confidence: float
    flagged_for_review: bool = False


class FindingAnalysisResult(BaseModel):
    """The output of a single finding analysis run.

    Attributes:
        recommendations: All extracted :class:`ReviewAction` objects.
        extraction_confidence: Overall confidence score for the extraction.
        review_level: Recommended human review level (from
            :class:`~agent_planning.confidence.models.ReviewLevel`).
        cost_usd: Estimated LLM cost for this extraction.
    """

    recommendations: list[ReviewAction]
    extraction_confidence: float
    review_level: str
    cost_usd: float


# ---------------------------------------------------------------------------
# Backward-compatibility aliases (deprecated — will be removed in v0.5.0)
# ---------------------------------------------------------------------------

#: Deprecated alias for :class:`ReviewActionStatus`.
RecommendationStatus = ReviewActionStatus

#: Deprecated alias for :class:`ReviewAction`.
Recommendation = ReviewAction

#: Deprecated alias for :class:`FindingAnalysisResult`.
RecommendationExtractionResult = FindingAnalysisResult
