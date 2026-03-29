"""Longitudinal compliance score tracking, trend analysis, and threshold alerting.

This module extends the NISTAValidator to persist compliance scores over time
and expose trend direction and threshold breach detection.

Usage::

    from pm_data_tools.schemas.nista.longitudinal import (
        LongitudinalComplianceTracker,
        ComplianceThresholdConfig,
        ConfidenceScoreRecord,
        TrendDirection,
    )
    from pm_data_tools.db import AssuranceStore

    store = AssuranceStore()
    tracker = LongitudinalComplianceTracker(store=store)

    # Pass to NISTAValidator.validate() — persistence is a side effect
    validator = NISTAValidator()
    result = validator.validate(data, project_id="PROJ-001", history=tracker)

    trend = tracker.compute_trend("PROJ-001")
    breaches = tracker.check_thresholds("PROJ-001")
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

import structlog
from pydantic import BaseModel, Field, field_validator

from ...db.store import AssuranceStore

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


class TrendDirection(Enum):
    """Direction of a project's NISTA compliance score over recent runs."""

    IMPROVING = "IMPROVING"
    STAGNATING = "STAGNATING"
    DEGRADING = "DEGRADING"


class ConfidenceScoreRecord(BaseModel):
    """A single persisted NISTA compliance score from one validation run.

    Attributes:
        project_id: Identifier for the validated project.
        run_id: Unique identifier for this validation run.
        timestamp: When the validation was performed.
        score: Overall compliance score (0-100).
        dimension_scores: Per-dimension compliance scores.
    """

    project_id: str
    run_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )
    score: float
    dimension_scores: dict[str, float] = Field(default_factory=dict)

    @field_validator("score")
    @classmethod
    def score_in_range(cls, v: float) -> float:
        """Validate score is within 0-100.

        Args:
            v: The score value to validate.

        Returns:
            The validated score.

        Raises:
            ValueError: If score is outside 0-100.
        """
        if not 0.0 <= v <= 100.0:
            raise ValueError(f"score must be between 0 and 100, got {v}")
        return v


class ComplianceThresholdConfig(BaseModel):
    """Configurable thresholds for NISTA compliance alerting.

    Attributes:
        drop_tolerance: Maximum acceptable score drop between consecutive runs
            before a breach is raised (in compliance-score points).
        floor: Minimum acceptable compliance score.  Scores below this value
            trigger a floor breach.
        stagnation_window: Number of consecutive runs to examine when
            determining whether a score is stagnating.
    """

    drop_tolerance: float = 5.0
    floor: float = 60.0
    stagnation_window: int = 3

    @field_validator("drop_tolerance", "floor")
    @classmethod
    def non_negative(cls, v: float) -> float:
        """Validate threshold values are non-negative.

        Args:
            v: The threshold value.

        Returns:
            The validated value.

        Raises:
            ValueError: If value is negative.
        """
        if v < 0:
            raise ValueError("threshold values must be non-negative")
        return v

    @field_validator("stagnation_window")
    @classmethod
    def window_positive(cls, v: int) -> int:
        """Validate stagnation window is at least 2.

        Args:
            v: The window size.

        Returns:
            The validated window size.

        Raises:
            ValueError: If window is less than 2.
        """
        if v < 2:
            raise ValueError("stagnation_window must be at least 2")
        return v


class ThresholdBreach(BaseModel):
    """A detected breach of a configured NISTA compliance threshold.

    Attributes:
        breach_type: Either ``"drop"`` (score fell more than drop_tolerance
            between two consecutive runs) or ``"floor"`` (score is below the
            configured floor).
        project_id: The affected project.
        current_score: The score at the time of breach detection.
        previous_score: The preceding score (only set for ``"drop"`` breaches).
        threshold_value: The threshold that was breached.
        message: Human-readable description of the breach.
    """

    breach_type: str  # "drop" or "floor"
    project_id: str
    current_score: float
    previous_score: Optional[float] = None
    threshold_value: float
    message: str


class LongitudinalComplianceTracker:
    """Persist and analyse NISTA compliance scores over time.

    This class wraps an :class:`~pm_data_tools.db.store.AssuranceStore` and
    provides methods to record validation runs, retrieve history, compute
    trend direction, and detect threshold breaches.

    Example::

        tracker = LongitudinalComplianceTracker()
        tracker.record(ConfidenceScoreRecord(
            project_id="PROJ-001",
            score=78.5,
        ))
        trend = tracker.compute_trend("PROJ-001")
        breaches = tracker.check_thresholds("PROJ-001")
    """

    def __init__(
        self,
        store: Optional[AssuranceStore] = None,
        thresholds: Optional[ComplianceThresholdConfig] = None,
    ) -> None:
        """Initialise the longitudinal compliance tracker.

        Args:
            store: Shared SQLite store.  A default store is created if not
                provided.
            thresholds: Threshold configuration for breach detection.
                Defaults to :class:`ComplianceThresholdConfig` defaults.
        """
        self._store = store or AssuranceStore()
        self._thresholds = thresholds or ComplianceThresholdConfig()

    def record(self, record: ConfidenceScoreRecord) -> None:
        """Persist a new compliance score record.

        Args:
            record: The :class:`ConfidenceScoreRecord` to store.
        """
        self._store.insert_confidence_score(
            project_id=record.project_id,
            run_id=record.run_id,
            timestamp=record.timestamp.isoformat(),
            score=record.score,
            dimension_scores=record.dimension_scores,
        )
        logger.info(
            "compliance_score_recorded",
            project_id=record.project_id,
            run_id=record.run_id,
            score=record.score,
        )

    def get_history(self, project_id: str) -> list[ConfidenceScoreRecord]:
        """Return all score records for a project, ordered oldest first.

        Args:
            project_id: The project identifier.

        Returns:
            List of :class:`ConfidenceScoreRecord` objects.
        """
        rows = self._store.get_confidence_scores(project_id)
        records: list[ConfidenceScoreRecord] = []
        for row in rows:
            dim: dict[str, float] = {}
            raw_dim = row.get("dimension_scores", {})
            if isinstance(raw_dim, dict):
                dim = {k: float(v) for k, v in raw_dim.items()}  # type: ignore[union-attr]
            records.append(
                ConfidenceScoreRecord(
                    project_id=str(row["project_id"]),
                    run_id=str(row["run_id"]),
                    timestamp=datetime.fromisoformat(str(row["timestamp"])),
                    score=float(row["score"]),  # type: ignore[arg-type]
                    dimension_scores=dim,
                )
            )
        return records

    def compute_trend(self, project_id: str) -> TrendDirection:
        """Determine the compliance score trend for a project.

        Examines the last ``stagnation_window`` records.  If there are fewer
        than two records the trend is :attr:`TrendDirection.STAGNATING`.

        The trend is:

        - ``IMPROVING`` if the latest score exceeds the oldest score in the
          window by more than ``drop_tolerance`` points.
        - ``DEGRADING`` if the latest score is more than ``drop_tolerance``
          points below the oldest score in the window.
        - ``STAGNATING`` otherwise.

        Args:
            project_id: The project identifier.

        Returns:
            A :class:`TrendDirection` value.
        """
        history = self.get_history(project_id)
        if len(history) < 2:
            logger.debug(
                "trend_insufficient_data",
                project_id=project_id,
                records=len(history),
            )
            return TrendDirection.STAGNATING

        window = history[-self._thresholds.stagnation_window :]
        oldest_score = window[0].score
        latest_score = window[-1].score
        delta = latest_score - oldest_score

        if delta > self._thresholds.drop_tolerance:
            trend = TrendDirection.IMPROVING
        elif delta < -self._thresholds.drop_tolerance:
            trend = TrendDirection.DEGRADING
        else:
            trend = TrendDirection.STAGNATING

        logger.debug(
            "trend_computed",
            project_id=project_id,
            oldest=oldest_score,
            latest=latest_score,
            delta=delta,
            trend=trend.value,
        )
        return trend

    def check_thresholds(self, project_id: str) -> list[ThresholdBreach]:
        """Detect active threshold breaches for a project.

        Checks two breach types against the latest score:

        - **drop**: The most recent score dropped by more than
          ``drop_tolerance`` compared to the previous score.
        - **floor**: The most recent score is below the configured ``floor``.

        Args:
            project_id: The project identifier.

        Returns:
            List of :class:`ThresholdBreach` objects (empty if no breaches).
        """
        history = self.get_history(project_id)
        breaches: list[ThresholdBreach] = []

        if not history:
            return breaches

        latest = history[-1]

        # Floor breach
        if latest.score < self._thresholds.floor:
            breaches.append(
                ThresholdBreach(
                    breach_type="floor",
                    project_id=project_id,
                    current_score=latest.score,
                    threshold_value=self._thresholds.floor,
                    message=(
                        f"Compliance score {latest.score:.1f} is below the "
                        f"floor threshold of {self._thresholds.floor:.1f}."
                    ),
                )
            )

        # Drop breach (requires at least two records)
        if len(history) >= 2:
            previous = history[-2]
            drop = previous.score - latest.score
            if drop > self._thresholds.drop_tolerance:
                breaches.append(
                    ThresholdBreach(
                        breach_type="drop",
                        project_id=project_id,
                        current_score=latest.score,
                        previous_score=previous.score,
                        threshold_value=self._thresholds.drop_tolerance,
                        message=(
                            f"Compliance score dropped {drop:.1f} points "
                            f"(from {previous.score:.1f} to {latest.score:.1f}), "
                            f"exceeding tolerance of "
                            f"{self._thresholds.drop_tolerance:.1f}."
                        ),
                    )
                )

        logger.info(
            "thresholds_checked",
            project_id=project_id,
            breach_count=len(breaches),
        )
        return breaches


# ---------------------------------------------------------------------------
# Backward-compatibility aliases (deprecated — will be removed in v0.5.0)
# ---------------------------------------------------------------------------

#: Deprecated alias for :class:`LongitudinalComplianceTracker`.
NISTAScoreHistory = LongitudinalComplianceTracker

#: Deprecated alias for :class:`ComplianceThresholdConfig`.
NISTAThresholdConfig = ComplianceThresholdConfig
