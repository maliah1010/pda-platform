"""Outlier mining module for diverse approach discovery."""

from .config import (
    MiningConfig,
    PromptDiversification,
    SaturationMethod,
    TemperatureSchedule,
)
from .miner import OutlierMiner, mine, mine_batch
from .models import (
    AssumptionReport,
    BatchMiningResult,
    ClusterInfo,
    DifferenceReport,
    DifferenceType,
    MiningCandidate,
    MiningResult,
    QualityScore,
    SaturationSignal,
)

__all__ = [
    # Main classes
    "OutlierMiner",

    # Convenience functions
    "mine",
    "mine_batch",

    # Configuration
    "MiningConfig",
    "TemperatureSchedule",
    "PromptDiversification",
    "SaturationMethod",

    # Result models
    "MiningCandidate",
    "MiningResult",
    "BatchMiningResult",
    "ClusterInfo",
    "DifferenceReport",
    "DifferenceType",
    "AssumptionReport",
    "QualityScore",
    "SaturationSignal",
]
