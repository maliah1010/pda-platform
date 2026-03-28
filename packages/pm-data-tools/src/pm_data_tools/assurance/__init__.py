"""Assurance module: artefact currency, compliance tracking, finding analysis.

This module provides four capabilities for assurance gate reviews:

- **P1** — :class:`ArtefactCurrencyValidator`: detect stale and last-minute
  artefact updates against a gate date.
- **P2** — :class:`~pm_data_tools.schemas.nista.LongitudinalComplianceTracker`:
  persist NISTA compliance scores and detect trends (see ``schemas.nista``).
- **P3** — :class:`FindingAnalyzer`: AI-powered extraction, deduplication, and
  cross-cycle recurrence detection for review actions.
- **P4** — :class:`DivergenceMonitor`: monitor AI confidence divergence across
  extraction samples and review cycles.

Public API::

    from pm_data_tools.assurance import (
        # P1
        ArtefactCurrencyValidator,
        CurrencyConfig,
        CurrencyScore,
        CurrencyStatus,
        # P3
        ReviewAction,
        FindingAnalysisResult,
        FindingAnalyzer,
        ReviewActionStatus,
        RecurrenceDetector,
        # P4
        DivergenceMonitor,
        DivergenceConfig,
        DivergenceResult,
        DivergenceSnapshot,
        SignalType,
    )
"""

from .analyzer import FindingAnalyzer
from .currency import (
    ArtefactCurrencyValidator,
    CurrencyConfig,
    CurrencyScore,
    CurrencyStatus,
)
from .divergence import (
    DivergenceConfig,
    DivergenceMonitor,
    DivergenceResult,
    DivergenceSignal,
    DivergenceSnapshot,
    SignalType,
)
from .models import (
    FindingAnalysisResult,
    ReviewAction,
    ReviewActionStatus,
    # Backward-compatibility aliases
    Recommendation,
    RecommendationExtractionResult,
    RecommendationStatus,
)
from .overrides import (
    OverrideDecision,
    OverrideDecisionLogger,
    OverrideOutcome,
    OverridePatternSummary,
    OverrideType,
)
from .recurrence import RecurrenceDetector
from .scheduler import (
    AdaptiveReviewScheduler,
    ReviewUrgency,
    SchedulerConfig,
    SchedulerRecommendation,
    SchedulerSignal,
)

# Backward-compatibility alias for FindingAnalyzer
RecommendationExtractor = FindingAnalyzer

__all__ = [
    # P1 — Artefact Currency Validator
    "ArtefactCurrencyValidator",
    "CurrencyConfig",
    "CurrencyScore",
    "CurrencyStatus",
    # P3 — Finding Analyzer
    "ReviewAction",
    "FindingAnalysisResult",
    "FindingAnalyzer",
    "ReviewActionStatus",
    "RecurrenceDetector",
    # P4 — Divergence Monitor
    "DivergenceMonitor",
    "DivergenceConfig",
    "DivergenceResult",
    "DivergenceSignal",
    "DivergenceSnapshot",
    "SignalType",
    # P5 — Adaptive Review Scheduler
    "AdaptiveReviewScheduler",
    "ReviewUrgency",
    "SchedulerConfig",
    "SchedulerRecommendation",
    "SchedulerSignal",
    # P6 — Override Decision Logger
    "OverrideDecision",
    "OverrideDecisionLogger",
    "OverrideOutcome",
    "OverridePatternSummary",
    "OverrideType",
    # Deprecated aliases — will be removed in v0.5.0
    "Recommendation",
    "RecommendationExtractionResult",
    "RecommendationExtractor",
    "RecommendationStatus",
]
