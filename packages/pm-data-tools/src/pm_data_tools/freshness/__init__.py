"""Evidence Freshness Detector for the PM Data Tools library.

This sub-package implements the freshness analysis capability described in
*Next Gen Project Assurance* (Murray, Paver & Steinberg, 2026), providing
tools to detect stale evidence and suspicious "fresh paint" editing patterns
in project management documents.

Quick start
-----------
Analyse a single file::

    from pm_data_tools.freshness import FreshnessAnalyser, FreshnessConfig

    analyser = FreshnessAnalyser()
    result = analyser.analyse_file("schedule.xml")
    print(result.freshness_score)   # 0–100
    print(result.rag_status)        # "green", "amber", or "red"
    for alert in result.alerts:
        print(alert)

Analyse an evidence pack (directory)::

    pack = analyser.analyse_pack("/path/to/evidence/")
    print(pack.overall_score)
    print(pack.rag_status)

Detect fresh paint with a gate date::

    from datetime import datetime
    from pm_data_tools.freshness import FreshnessAnalyser, FreshnessConfig

    analyser = FreshnessAnalyser(
        config=FreshnessConfig(gate_date=datetime(2026, 4, 1))
    )
    result = analyser.analyse_file("schedule.xml")
"""

from .analyser import FreshnessAnalyser
from .metadata_extractor import extract_metadata
from .models import (
    DocumentFreshnessResult,
    DocumentMetadata,
    FreshnessAlert,
    FreshnessConfig,
    PackFreshnessResult,
    RevisionEntry,
)

__all__ = [
    # Primary API
    "FreshnessAnalyser",
    "extract_metadata",
    # Models
    "FreshnessConfig",
    "DocumentMetadata",
    "RevisionEntry",
    "FreshnessAlert",
    "DocumentFreshnessResult",
    "PackFreshnessResult",
]
