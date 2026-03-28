"""Confidence Divergence Monitor for assurance gate reviews.

Detects two failure modes in AI-assisted finding extraction:

1. **High divergence** — individual agent samples disagree significantly,
   indicating the source text is ambiguous or the extraction prompt is under-
   specified.  The consensus score is unreliable when samples are spread wide.

2. **Degrading confidence** — the consensus confidence score has fallen across
   consecutive review cycles for the same project.  This may indicate that
   review quality is declining or that the project situation is becoming harder
   to interpret.

3. **Low consensus** — the overall consensus score is below the configured
   minimum, regardless of variance.

Usage::

    from pm_data_tools.assurance.divergence import (
        DivergenceMonitor,
        DivergenceConfig,
        DivergenceResult,
        DivergenceSnapshot,
        SignalType,
    )

    monitor = DivergenceMonitor()
    result = monitor.check(
        project_id="PROJ-001",
        review_id="review-q1-2026",
        confidence_score=0.55,
        sample_scores=[0.80, 0.30, 0.55, 0.60, 0.50],
    )
    # result.signal.signal_type == SignalType.HIGH_DIVERGENCE
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

import structlog
from pydantic import BaseModel, Field, field_validator

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class SignalType(Enum):
    """Classification of a confidence divergence check.

    Attributes:
        STABLE: Consensus is within configured bounds; no action required.
        HIGH_DIVERGENCE: Individual sample scores are spread beyond the
            divergence threshold, indicating the extraction is unreliable.
        LOW_CONSENSUS: The overall consensus score is below the configured
            minimum, regardless of sample variance.
        DEGRADING_CONFIDENCE: The consensus score has declined across the
            configured number of consecutive review cycles.
    """

    STABLE = "STABLE"
    HIGH_DIVERGENCE = "HIGH_DIVERGENCE"
    LOW_CONSENSUS = "LOW_CONSENSUS"
    DEGRADING_CONFIDENCE = "DEGRADING_CONFIDENCE"


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------


class DivergenceConfig(BaseModel):
    """Configuration for the confidence divergence monitor.

    Attributes:
        divergence_threshold: Maximum acceptable spread between the highest
            and lowest individual sample scores.  A spread above this value
            triggers :attr:`SignalType.HIGH_DIVERGENCE`.
        min_consensus: Minimum acceptable overall consensus score (0–1).
            Scores below this trigger :attr:`SignalType.LOW_CONSENSUS`.
        degradation_window: Number of consecutive historical snapshots that
            must all show a falling consensus score to trigger
            :attr:`SignalType.DEGRADING_CONFIDENCE`.  Requires at least this
            many prior snapshots plus the current check.
    """

    divergence_threshold: float = 0.20
    min_consensus: float = 0.60
    degradation_window: int = 3

    @field_validator("divergence_threshold", "min_consensus")
    @classmethod
    def _between_zero_and_one(cls, v: float) -> float:
        """Validate that fractional thresholds are in [0, 1].

        Args:
            v: The value to validate.

        Returns:
            The validated value.

        Raises:
            ValueError: If value is outside [0, 1].
        """
        if not (0.0 <= v <= 1.0):
            raise ValueError("threshold must be between 0 and 1")
        return v

    @field_validator("degradation_window")
    @classmethod
    def _positive_window(cls, v: int) -> int:
        """Validate that degradation_window is at least 1.

        Args:
            v: The window size.

        Returns:
            The validated value.

        Raises:
            ValueError: If value is less than 1.
        """
        if v < 1:
            raise ValueError("degradation_window must be at least 1")
        return v


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class DivergenceSnapshot(BaseModel):
    """A persisted record of a single divergence check.

    Attributes:
        id: Unique identifier for this snapshot.
        project_id: The project this snapshot belongs to.
        review_id: Identifier of the review that was checked.
        confidence_score: Overall consensus confidence score (0–1).
        sample_scores: Individual per-sample confidence scores.
        signal_type: The signal classification assigned at the time of check.
        timestamp: When this snapshot was recorded (UTC).
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str
    review_id: str
    confidence_score: float
    sample_scores: list[float]
    signal_type: SignalType
    timestamp: datetime = Field(
        default_factory=lambda: datetime.now(tz=timezone.utc)
    )


class DivergenceSignal(BaseModel):
    """The signal produced by a divergence check.

    Attributes:
        signal_type: Classification of the detected condition.
        project_id: The project being checked.
        review_id: The review being checked.
        confidence_score: The consensus confidence score for this check.
        spread: Difference between the highest and lowest sample scores.
            Zero when fewer than two samples are provided.
        previous_confidence: The consensus score from the immediately prior
            snapshot.  ``None`` if no prior history exists.
        message: Human-readable explanation of the signal.
    """

    signal_type: SignalType
    project_id: str
    review_id: str
    confidence_score: float
    spread: float
    previous_confidence: Optional[float]
    message: str


class DivergenceResult(BaseModel):
    """Result of a single divergence monitor check.

    Attributes:
        project_id: The project checked.
        review_id: The review checked.
        confidence_score: Overall consensus confidence score.
        sample_scores: Individual per-sample confidence scores.
        signal: The divergence signal produced.
        snapshot_id: The UUID of the persisted :class:`DivergenceSnapshot`.
    """

    project_id: str
    review_id: str
    confidence_score: float
    sample_scores: list[float]
    signal: DivergenceSignal
    snapshot_id: str


# ---------------------------------------------------------------------------
# Monitor
# ---------------------------------------------------------------------------


class DivergenceMonitor:
    """Monitor confidence divergence across AI extraction samples.

    Each call to :meth:`check` classifies the provided confidence data,
    persists a :class:`DivergenceSnapshot` to the store, and returns a
    :class:`DivergenceResult` containing the signal.

    Classification precedence (highest to lowest):

    1. :attr:`~SignalType.HIGH_DIVERGENCE` — spread of sample scores exceeds
       ``config.divergence_threshold``.
    2. :attr:`~SignalType.LOW_CONSENSUS` — overall score below
       ``config.min_consensus``.
    3. :attr:`~SignalType.DEGRADING_CONFIDENCE` — all of the last
       ``config.degradation_window`` historical snapshots show a strictly
       decreasing confidence score.
    4. :attr:`~SignalType.STABLE` — none of the above apply.

    Example::

        monitor = DivergenceMonitor(config=DivergenceConfig(min_consensus=0.70))
        result = monitor.check(
            project_id="PROJ-001",
            review_id="review-q1-2026",
            confidence_score=0.65,
            sample_scores=[0.60, 0.70, 0.65],
        )
        # result.signal.signal_type == SignalType.STABLE
    """

    def __init__(
        self,
        config: Optional[DivergenceConfig] = None,
        store: Optional[object] = None,
    ) -> None:
        """Initialise the monitor.

        Args:
            config: Divergence configuration.  Defaults to
                :class:`DivergenceConfig` defaults.
            store: :class:`~pm_data_tools.db.store.AssuranceStore` instance.
                When provided, snapshots are persisted; when ``None``, checks
                run in memory-only mode.
        """
        self._config = config or DivergenceConfig()
        self._store = store

    # ------------------------------------------------------------------
    # Classification helpers
    # ------------------------------------------------------------------

    def _compute_spread(self, sample_scores: list[float]) -> float:
        """Return the spread (max − min) of sample_scores.

        Args:
            sample_scores: Individual sample confidence scores.

        Returns:
            Spread value, or 0.0 if fewer than two scores provided.
        """
        if len(sample_scores) < 2:
            return 0.0
        return max(sample_scores) - min(sample_scores)

    def _is_degrading(self, project_id: str) -> bool:
        """Check whether recent snapshots show a strictly declining confidence.

        Retrieves the last ``config.degradation_window`` snapshots from the
        store and returns ``True`` only if each is strictly less than the one
        before it.

        Args:
            project_id: The project to query.

        Returns:
            ``True`` if degradation detected, ``False`` otherwise (including
            when no store is attached or there is insufficient history).
        """
        if self._store is None:
            return False

        history = self._store.get_divergence_history(project_id)  # type: ignore[union-attr]
        if len(history) < self._config.degradation_window:
            return False

        recent = history[-self._config.degradation_window :]
        scores = [r["confidence_score"] for r in recent]
        return all(scores[i] > scores[i + 1] for i in range(len(scores) - 1))

    def _previous_confidence(self, project_id: str) -> Optional[float]:
        """Return the confidence score from the most recent prior snapshot.

        Args:
            project_id: The project to query.

        Returns:
            The previous consensus score, or ``None`` if no history exists.
        """
        if self._store is None:
            return None
        history = self._store.get_divergence_history(project_id)  # type: ignore[union-attr]
        if not history:
            return None
        return float(history[-1]["confidence_score"])

    def _classify(
        self,
        project_id: str,
        review_id: str,
        confidence_score: float,
        spread: float,
    ) -> DivergenceSignal:
        """Classify the divergence check and build a signal.

        Args:
            project_id: The project being checked.
            review_id: The review being checked.
            confidence_score: Overall consensus score.
            spread: Spread of individual sample scores.

        Returns:
            A :class:`DivergenceSignal` with the classification result.
        """
        prev = self._previous_confidence(project_id)

        if spread > self._config.divergence_threshold:
            msg = (
                f"High divergence detected for '{review_id}' (project "
                f"'{project_id}'): sample spread of {spread:.2f} exceeds "
                f"threshold {self._config.divergence_threshold:.2f}.  "
                f"Extraction results may be unreliable.  "
                f"Signal: {SignalType.HIGH_DIVERGENCE.value}."
            )
            return DivergenceSignal(
                signal_type=SignalType.HIGH_DIVERGENCE,
                project_id=project_id,
                review_id=review_id,
                confidence_score=confidence_score,
                spread=spread,
                previous_confidence=prev,
                message=msg,
            )

        if confidence_score < self._config.min_consensus:
            msg = (
                f"Low consensus for '{review_id}' (project '{project_id}'): "
                f"score {confidence_score:.2f} is below minimum "
                f"{self._config.min_consensus:.2f}.  "
                f"Signal: {SignalType.LOW_CONSENSUS.value}."
            )
            return DivergenceSignal(
                signal_type=SignalType.LOW_CONSENSUS,
                project_id=project_id,
                review_id=review_id,
                confidence_score=confidence_score,
                spread=spread,
                previous_confidence=prev,
                message=msg,
            )

        if self._is_degrading(project_id):
            msg = (
                f"Degrading confidence for project '{project_id}': the last "
                f"{self._config.degradation_window} snapshots show a "
                f"consistently falling consensus score.  "
                f"Signal: {SignalType.DEGRADING_CONFIDENCE.value}."
            )
            return DivergenceSignal(
                signal_type=SignalType.DEGRADING_CONFIDENCE,
                project_id=project_id,
                review_id=review_id,
                confidence_score=confidence_score,
                spread=spread,
                previous_confidence=prev,
                message=msg,
            )

        msg = (
            f"Confidence check for '{review_id}' (project '{project_id}'): "
            f"score {confidence_score:.2f}, spread {spread:.2f}.  "
            f"Signal: {SignalType.STABLE.value}."
        )
        return DivergenceSignal(
            signal_type=SignalType.STABLE,
            project_id=project_id,
            review_id=review_id,
            confidence_score=confidence_score,
            spread=spread,
            previous_confidence=prev,
            message=msg,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check(
        self,
        project_id: str,
        review_id: str,
        confidence_score: float,
        sample_scores: list[float],
    ) -> DivergenceResult:
        """Run a divergence check and persist the snapshot.

        Args:
            project_id: The project identifier.
            review_id: Unique identifier for the review being checked.
            confidence_score: Overall consensus confidence score (0–1).
            sample_scores: Individual per-sample confidence scores used to
                compute the consensus.  May be empty.

        Returns:
            A :class:`DivergenceResult` with the signal and snapshot ID.
        """
        spread = self._compute_spread(sample_scores)
        signal = self._classify(project_id, review_id, confidence_score, spread)

        snapshot = DivergenceSnapshot(
            project_id=project_id,
            review_id=review_id,
            confidence_score=confidence_score,
            sample_scores=sample_scores,
            signal_type=signal.signal_type,
        )

        if self._store is not None:
            self._store.insert_divergence_snapshot(  # type: ignore[union-attr]
                snapshot_id=snapshot.id,
                project_id=project_id,
                review_id=review_id,
                confidence_score=confidence_score,
                sample_scores=sample_scores,
                signal_type=signal.signal_type.value,
                timestamp=snapshot.timestamp.isoformat(),
            )

        logger.info(
            "divergence_check_complete",
            project_id=project_id,
            review_id=review_id,
            confidence_score=confidence_score,
            spread=spread,
            signal_type=signal.signal_type.value,
        )

        return DivergenceResult(
            project_id=project_id,
            review_id=review_id,
            confidence_score=confidence_score,
            sample_scores=sample_scores,
            signal=signal,
            snapshot_id=snapshot.id,
        )
