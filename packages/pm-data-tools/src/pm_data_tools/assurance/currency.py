"""Artefact currency validation for assurance gate reviews.

Detects two common failure modes in gate evidence:

1. **Genuinely outdated artefacts** — documents that have not been updated
   within the configured staleness window.
2. **Last-minute compliance updates** — documents updated within a very short
   window immediately before the gate date.  This pattern is consistent with
   superficial gate readiness: timestamps change but substantive content may
   not have been revised.

Usage::

    from pm_data_tools.assurance.currency import (
        ArtefactCurrencyValidator,
        CurrencyConfig,
        CurrencyScore,
        CurrencyStatus,
    )

    validator = ArtefactCurrencyValidator()
    score = validator.check_artefact_currency(
        artefact_id="risk-register-v3",
        artefact_type="risk_register",
        last_modified=datetime(2025, 12, 1, tzinfo=timezone.utc),
        gate_date=datetime(2026, 6, 30, tzinfo=timezone.utc),
    )

    results = validator.check_batch(
        artefacts=[
            {"id": "risk-register-v3", "type": "risk_register",
             "last_modified": datetime(2025, 12, 1, tzinfo=timezone.utc)},
        ],
        gate_date=datetime(2026, 6, 30, tzinfo=timezone.utc),
    )
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

import structlog
from pydantic import BaseModel, Field, field_validator

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums and config
# ---------------------------------------------------------------------------


class CurrencyStatus(Enum):
    """Artefact currency classification.

    Attributes:
        CURRENT: Artefact is within the configured staleness window and was
            not updated suspiciously close to the gate date.
        OUTDATED: Artefact has not been updated within the configured staleness
            window and may not reflect the current state of the project.
        ANOMALOUS_UPDATE: Artefact was updated within the anomaly window
            immediately before the gate date.  This pattern is consistent with
            last-minute compliance updates ahead of a gate review rather than
            a genuine substantive revision.
    """

    CURRENT = "CURRENT"
    OUTDATED = "OUTDATED"
    ANOMALOUS_UPDATE = "ANOMALOUS_UPDATE"


class CurrencyConfig(BaseModel):
    """Configuration for artefact currency checks.

    Attributes:
        max_staleness_days: Artefacts not updated within this many days before
            the gate date are classified as :attr:`CurrencyStatus.OUTDATED`.
        anomaly_window_days: Updates this close to the gate date (inclusive)
            are classified as :attr:`CurrencyStatus.ANOMALOUS_UPDATE`,
            regardless of staleness.
    """

    max_staleness_days: int = 90
    anomaly_window_days: int = 3

    @field_validator("max_staleness_days", "anomaly_window_days")
    @classmethod
    def positive(cls, v: int) -> int:
        """Validate that threshold values are positive.

        Args:
            v: The threshold value.

        Returns:
            The validated value.

        Raises:
            ValueError: If value is not positive.
        """
        if v < 1:
            raise ValueError("threshold values must be at least 1")
        return v


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------


class CurrencyScore(BaseModel):
    """Result of a single artefact currency check.

    Attributes:
        artefact_id: Identifier for the checked artefact.
        artefact_type: Category of artefact (e.g. ``"risk_register"``).
        last_modified: When the artefact was last modified.
        gate_date: The assurance gate date against which currency is assessed.
        status: Currency classification result.
        staleness_days: Days between ``last_modified`` and ``gate_date``.
            Negative values indicate a future-dated ``last_modified``.
        anomaly_window_days: The configured anomaly window that triggered an
            :attr:`~CurrencyStatus.ANOMALOUS_UPDATE` classification.  Zero if
            the status is not :attr:`~CurrencyStatus.ANOMALOUS_UPDATE`.
        message: Human-readable explanation of the result.
    """

    artefact_id: str
    artefact_type: str
    last_modified: datetime
    gate_date: datetime
    status: CurrencyStatus
    staleness_days: int
    anomaly_window_days: int
    message: str


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------


class ArtefactCurrencyValidator:
    """Validate the currency of project artefacts against a gate date.

    Checks each artefact's ``last_modified`` timestamp against the gate date
    and two configurable thresholds:

    - **Staleness window**: artefacts older than ``max_staleness_days`` are
      classified as :attr:`~CurrencyStatus.OUTDATED`.
    - **Anomaly window**: artefacts updated within ``anomaly_window_days``
      of the gate are classified as :attr:`~CurrencyStatus.ANOMALOUS_UPDATE`,
      which may indicate last-minute compliance updates ahead of a gate
      review.

    Example::

        validator = ArtefactCurrencyValidator(
            config=CurrencyConfig(max_staleness_days=60, anomaly_window_days=2)
        )
        score = validator.check_artefact_currency(
            artefact_id="risk-register",
            artefact_type="risk_register",
            last_modified=datetime(2026, 6, 28, tzinfo=timezone.utc),
            gate_date=datetime(2026, 6, 30, tzinfo=timezone.utc),
        )
        # score.status == CurrencyStatus.ANOMALOUS_UPDATE
    """

    def __init__(self, config: Optional[CurrencyConfig] = None) -> None:
        """Initialise the validator.

        Args:
            config: Currency check configuration.  Defaults to
                :class:`CurrencyConfig` defaults (90-day staleness window,
                3-day anomaly window).
        """
        self._config = config or CurrencyConfig()

    # ------------------------------------------------------------------
    # Classification helpers
    # ------------------------------------------------------------------

    def _classify(
        self,
        artefact_id: str,
        artefact_type: str,
        staleness_days: int,
    ) -> tuple[CurrencyStatus, str]:
        """Classify an artefact and build its human-readable message.

        Args:
            artefact_id: Artefact identifier (used in message only).
            artefact_type: Artefact category (used in message only).
            staleness_days: Days between last_modified and gate_date.
                Negative values indicate a future-dated last_modified.

        Returns:
            A ``(status, message)`` tuple.
        """
        # Future-dated last_modified: treat as anomalous
        if staleness_days < 0:
            msg = (
                f"Artefact '{artefact_id}' ({artefact_type}) has a last-modified "
                f"date after the gate date.  This may indicate a data entry error "
                f"or clock skew.  Status: {CurrencyStatus.ANOMALOUS_UPDATE.value}."
            )
            return CurrencyStatus.ANOMALOUS_UPDATE, msg

        # Check staleness first — an old document cannot also be anomalously fresh
        if staleness_days > self._config.max_staleness_days:
            msg = (
                f"Artefact '{artefact_id}' ({artefact_type}) has not been updated "
                f"in {staleness_days} days "
                f"(threshold: {self._config.max_staleness_days}).  "
                f"Status: {CurrencyStatus.OUTDATED.value}."
            )
            return CurrencyStatus.OUTDATED, msg

        # Check for last-minute update
        if staleness_days <= self._config.anomaly_window_days:
            msg = (
                f"Artefact '{artefact_id}' ({artefact_type}) was updated "
                f"{staleness_days} day(s) before the gate date, within the "
                f"anomaly window of {self._config.anomaly_window_days} days.  "
                f"This may indicate a last-minute compliance update rather than "
                f"a genuine substantive revision.  "
                f"Status: {CurrencyStatus.ANOMALOUS_UPDATE.value}."
            )
            return CurrencyStatus.ANOMALOUS_UPDATE, msg

        # Within window and not anomalous
        msg = (
            f"Artefact '{artefact_id}' ({artefact_type}) was last updated "
            f"{staleness_days} days before the gate date.  "
            f"Status: {CurrencyStatus.CURRENT.value}."
        )
        return CurrencyStatus.CURRENT, msg

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def check_artefact_currency(
        self,
        artefact_id: str,
        artefact_type: str,
        last_modified: datetime,
        gate_date: datetime,
    ) -> CurrencyScore:
        """Assess the currency of a single artefact.

        Args:
            artefact_id: Identifier for the artefact.
            artefact_type: Category label (e.g. ``"risk_register"``).
            last_modified: When the artefact was last modified.  May be
                timezone-aware or naive; naive datetimes are compared
                directly.
            gate_date: The assurance gate date to assess against.

        Returns:
            A :class:`CurrencyScore` with the classification result.
        """
        staleness_days = (gate_date - last_modified).days
        status, message = self._classify(artefact_id, artefact_type, staleness_days)

        anomaly_days = (
            self._config.anomaly_window_days
            if status == CurrencyStatus.ANOMALOUS_UPDATE
            else 0
        )

        score = CurrencyScore(
            artefact_id=artefact_id,
            artefact_type=artefact_type,
            last_modified=last_modified,
            gate_date=gate_date,
            status=status,
            staleness_days=staleness_days,
            anomaly_window_days=anomaly_days,
            message=message,
        )

        logger.info(
            "artefact_currency_checked",
            artefact_id=artefact_id,
            artefact_type=artefact_type,
            staleness_days=staleness_days,
            status=status.value,
        )
        return score

    def check_batch(
        self,
        artefacts: list[dict[str, Any]],
        gate_date: datetime,
    ) -> list[CurrencyScore]:
        """Assess the currency of multiple artefacts against a gate date.

        Each dict in ``artefacts`` must contain:

        - ``id`` (``str``): artefact identifier.
        - ``type`` (``str``): artefact category label.
        - ``last_modified`` (:class:`~datetime.datetime` or ISO-8601 ``str``):
          when the artefact was last modified.

        Args:
            artefacts: List of artefact descriptor dicts.
            gate_date: The assurance gate date.

        Returns:
            List of :class:`CurrencyScore` objects in the same order as
            the input ``artefacts`` list.  An empty list is returned when
            ``artefacts`` is empty.
        """
        results: list[CurrencyScore] = []
        for item in artefacts:
            raw_lm = item["last_modified"]
            last_modified: datetime
            if isinstance(raw_lm, str):
                # Parse ISO-8601; assume UTC if no timezone info
                parsed = datetime.fromisoformat(raw_lm)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                last_modified = parsed
            else:
                last_modified = raw_lm

            results.append(
                self.check_artefact_currency(
                    artefact_id=str(item["id"]),
                    artefact_type=str(item["type"]),
                    last_modified=last_modified,
                    gate_date=gate_date,
                )
            )

        logger.info(
            "artefact_currency_batch_complete",
            count=len(results),
            outdated=sum(1 for r in results if r.status == CurrencyStatus.OUTDATED),
            anomalous=sum(
                1 for r in results if r.status == CurrencyStatus.ANOMALOUS_UPDATE
            ),
        )
        return results
