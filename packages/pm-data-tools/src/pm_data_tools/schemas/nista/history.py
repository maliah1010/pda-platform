"""Deprecated: use ``pm_data_tools.schemas.nista.longitudinal`` instead.

This module is retained for backward compatibility only and will be removed
in v0.5.0.  All symbols have been moved to :mod:`.longitudinal`.
"""

from .longitudinal import (  # noqa: F401
    ComplianceThresholdConfig,
    ComplianceThresholdConfig as NISTAThresholdConfig,
    ConfidenceScoreRecord,
    LongitudinalComplianceTracker,
    LongitudinalComplianceTracker as NISTAScoreHistory,
    ThresholdBreach,
    TrendDirection,
)

__all__ = [
    "ConfidenceScoreRecord",
    "LongitudinalComplianceTracker",
    "NISTAScoreHistory",
    "ComplianceThresholdConfig",
    "NISTAThresholdConfig",
    "ThresholdBreach",
    "TrendDirection",
]
