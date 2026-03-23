"""Data models for the assurance recommendation tracker.

These models represent the lifecycle of an assurance recommendation from
initial extraction through to closure or recurrence detection.
"""

from __future__ import annotations

import uuid
from datetime import date
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class RecommendationStatus(Enum):
    """Lifecycle status of a tracked recommendation.

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


class Recommendation(BaseModel):
    """A single assurance recommendation extracted from a project review.

    Attributes:
        id: Unique identifier (UUID4 by default).
        text: The recommended action text.
        category: Classification of the recommendation (e.g. priority level).
        source_review_id: Identifier of the review document this came from.
        review_date: Date of the source review.
        status: Current lifecycle status.
        owner: Optional responsible party.
        recurrence_of: Optional ID of a prior recommendation this recurs from.
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
    status: RecommendationStatus = RecommendationStatus.OPEN
    owner: Optional[str] = None
    recurrence_of: Optional[str] = None
    confidence: float
    flagged_for_review: bool = False


class RecommendationExtractionResult(BaseModel):
    """The output of a single recommendation extraction run.

    Attributes:
        recommendations: All extracted :class:`Recommendation` objects.
        extraction_confidence: Overall confidence score for the extraction.
        review_level: Recommended human review level (from
            :class:`~agent_planning.confidence.models.ReviewLevel`).
        cost_usd: Estimated LLM cost for this extraction.
    """

    recommendations: list[Recommendation]
    extraction_confidence: float
    review_level: str
    cost_usd: float
