"""Deprecated: use ``pm_data_tools.assurance.analyzer`` instead.

This module is retained for backward compatibility only and will be removed
in v0.5.0.  All symbols have been moved to :mod:`.analyzer`.
"""

from .analyzer import FindingAnalyzer  # noqa: F401
from .analyzer import FindingAnalyzer as RecommendationExtractor  # noqa: F401

__all__ = ["FindingAnalyzer", "RecommendationExtractor"]
