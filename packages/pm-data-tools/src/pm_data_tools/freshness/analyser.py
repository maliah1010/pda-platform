"""Freshness scoring engine and alert system.

This module implements ``FreshnessAnalyser``, which takes ``DocumentMetadata``
objects (or file paths) and produces ``DocumentFreshnessResult`` and
``PackFreshnessResult`` instances containing freshness scores, RAG statuses,
and structured alerts.

Scoring model
-------------
Each document receives three sub-scores (0–100):

* **staleness_score** — derived from time since last modification.
* **velocity_score** — derived from edit frequency patterns; detects both
  burst editing (fresh paint) and long dormancy.
* **provenance_score** — derived from metadata completeness; a rich audit
  trail scores higher.

The **composite freshness_score** is a weighted average of the three
sub-scores, with weights configurable via :class:`FreshnessConfig`.

RAG thresholds (default):

* Green  80–100 : modified within ``fresh_threshold_days`` (30 days).
* Amber  40–79  : modified within ``stale_threshold_days`` (90 days).
* Red     0–39  : not modified beyond ``stale_threshold_days``.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from .metadata_extractor import extract_metadata
from .models import (
    DocumentFreshnessResult,
    DocumentMetadata,
    FreshnessAlert,
    FreshnessConfig,
    PackFreshnessResult,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

# File extensions recognised as PM documents when scanning a directory.
_PM_EXTENSIONS = {
    ".xml",
    ".mpp",
    ".xer",
    ".p6xml",
    ".json",
    ".xlsx",
    ".xls",
    ".csv",
}


def _days_since(dt: Optional[datetime], reference: datetime) -> Optional[float]:
    """Return calendar days between *dt* and *reference*, or ``None``.

    Args:
        dt: The earlier datetime (e.g. ``modified_at``).
        reference: The reference point (usually ``now``).

    Returns:
        Positive float representing elapsed days, or ``None`` if *dt* is
        ``None``.
    """
    if dt is None:
        return None
    # Ensure both datetimes are timezone-aware for comparison.
    ref = reference
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)
    cmp_dt = dt
    if cmp_dt.tzinfo is None:
        cmp_dt = cmp_dt.replace(tzinfo=timezone.utc)
    delta = ref - cmp_dt
    return max(delta.total_seconds() / 86400.0, 0.0)


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    """Clamp *value* to [*lo*, *hi*].

    Args:
        value: Input value.
        lo: Lower bound (default 0).
        hi: Upper bound (default 100).

    Returns:
        Clamped value.
    """
    return max(lo, min(hi, value))


# ---------------------------------------------------------------------------
# Sub-score calculators
# ---------------------------------------------------------------------------


def _compute_staleness_score(
    days_old: Optional[float],
    config: FreshnessConfig,
) -> float:
    """Compute the staleness sub-score (0–100).

    Uses a piecewise linear decay curve between the configured thresholds:

    * ``days_old`` ≤ ``fresh_threshold_days``  → 100 (green)
    * ``fresh_threshold_days`` < ``days_old`` ≤ ``stale_threshold_days``
      → linearly interpolated between 80 and 40 (amber)
    * ``stale_threshold_days`` < ``days_old`` ≤ ``critical_threshold_days``
      → linearly interpolated between 40 and 0 (red)
    * ``days_old`` > ``critical_threshold_days``  → 0 (deep red)

    When ``days_old`` is ``None`` (modification date unknown) the score is
    set to 0 to be conservative.

    Args:
        days_old: Calendar days since last modification, or ``None``.
        config: Freshness configuration containing threshold values.

    Returns:
        Staleness score in [0, 100].
    """
    if days_old is None:
        return 0.0

    fresh = float(config.fresh_threshold_days)
    stale = float(config.stale_threshold_days)
    critical = float(config.critical_threshold_days)

    if days_old <= fresh:
        return 100.0
    if days_old <= stale:
        # Linear interpolation: 100→80 over [fresh, stale]
        t = (days_old - fresh) / max(stale - fresh, 1.0)
        return _clamp(100.0 - t * 60.0)
    if days_old <= critical:
        # Linear interpolation: 40→0 over [stale, critical]
        t = (days_old - stale) / max(critical - stale, 1.0)
        return _clamp(40.0 - t * 40.0)
    return 0.0


def _compute_velocity_score(
    metadata: DocumentMetadata,
    config: FreshnessConfig,
    reference: datetime,
) -> float:
    """Compute the velocity sub-score (0–100).

    The velocity score rewards steady, regular editing and penalises:

    * **Burst editing**: many edits concentrated in a short window just
      before the gate date (the "fresh paint" pattern).
    * **Long dormancy**: no edits for an extended period where edits were
      expected.

    When no revision history is available the score is 50 (neutral) so
    that missing history does not unduly penalise documents whose format
    does not expose it.

    Args:
        metadata: Document metadata containing ``revision_history`` and
            ``version_count``.
        config: Freshness configuration.
        reference: Reference date (usually ``now`` or ``gate_date``).

    Returns:
        Velocity score in [0, 100].
    """
    history = metadata.revision_history
    version_count = metadata.version_count

    if not history and not version_count:
        # No velocity information available — neutral score.
        return 50.0

    if not history:
        # We know the version count but have no per-revision timestamps.
        # A single version (never iterated) scores lower; many versions neutral.
        if version_count == 1:
            return 30.0
        return 60.0

    # We have timestamped revision history.
    # Ensure datetimes are comparable.
    ref = reference
    if ref.tzinfo is None:
        ref = ref.replace(tzinfo=timezone.utc)

    gate = config.gate_date or ref
    if gate.tzinfo is None:
        gate = gate.replace(tzinfo=timezone.utc)

    burst_window_start = gate - __import__("datetime").timedelta(
        days=config.burst_edit_window_days
    )

    revisions_in_burst = [
        r for r in history if burst_window_start <= r.timestamp <= gate
    ]
    total_revisions = len(history)
    burst_count = len(revisions_in_burst)

    score = 80.0  # Start at a healthy baseline.

    # Penalise burst editing pattern.
    if burst_count >= config.burst_edit_min_count:
        # How much of editing happened in the burst window?
        burst_ratio = burst_count / max(total_revisions, 1)
        # Severe penalty when >50% of all edits are in the burst window.
        penalty = _clamp(burst_ratio * 60.0)
        score -= penalty

    # Check for long dormancy: sort timestamps and find the longest gap.
    sorted_times = sorted(r.timestamp for r in history)
    max_gap_days = 0.0
    for i in range(1, len(sorted_times)):
        gap = (sorted_times[i] - sorted_times[i - 1]).total_seconds() / 86400.0
        max_gap_days = max(max_gap_days, gap)

    if max_gap_days > config.dormancy_threshold_days:
        # Subtract up to 20 points for extended dormancy.
        dormancy_penalty = _clamp(
            (max_gap_days / max(config.dormancy_threshold_days, 1)) * 10.0,
            0.0,
            20.0,
        )
        score -= dormancy_penalty

    return _clamp(score)


def _compute_provenance_score(metadata: DocumentMetadata) -> float:
    """Compute the provenance sub-score (0–100).

    Rewards completeness of the audit trail: the more metadata fields are
    populated and the richer the revision history, the higher the score.

    Scoring breakdown:
    * ``modified_at`` present: +30 pts (critical)
    * ``author`` present: +20 pts
    * ``created_at`` present: +15 pts
    * ``last_modified_by`` present: +15 pts
    * ``version_count`` > 0: +10 pts
    * ``revision_history`` non-empty: +10 pts

    Args:
        metadata: Document metadata to evaluate.

    Returns:
        Provenance score in [0, 100].
    """
    score = 0.0
    if metadata.modified_at is not None:
        score += 30.0
    if metadata.author is not None:
        score += 20.0
    if metadata.created_at is not None:
        score += 15.0
    if metadata.last_modified_by is not None:
        score += 15.0
    if metadata.version_count is not None and metadata.version_count > 0:
        score += 10.0
    if metadata.revision_history:
        score += 10.0
    return _clamp(score)


# ---------------------------------------------------------------------------
# Alert generation
# ---------------------------------------------------------------------------


def _generate_alerts(
    metadata: DocumentMetadata,
    staleness_score: float,
    velocity_score: float,
    freshness_score: float,
    days_old: Optional[float],
    config: FreshnessConfig,
    reference: datetime,
) -> list[FreshnessAlert]:
    """Generate structured alerts for a document.

    Args:
        metadata: Document metadata.
        staleness_score: Computed staleness sub-score.
        velocity_score: Computed velocity sub-score.
        freshness_score: Composite freshness score.
        days_old: Calendar days since last modification.
        config: Freshness configuration.
        reference: Reference datetime for burst detection.

    Returns:
        List of ``FreshnessAlert`` instances.
    """
    alerts: list[FreshnessAlert] = []
    now = datetime.now(tz=timezone.utc)
    doc_id = metadata.file_path

    # --- Stale alert ---
    if days_old is not None and days_old > config.stale_threshold_days:
        severity = (
            "critical"
            if days_old > config.critical_threshold_days
            else "warning"
        )
        alerts.append(
            FreshnessAlert(
                document_id=doc_id,
                alert_type="stale",
                severity=severity,
                freshness_score=freshness_score,
                message=(
                    f"Document has not been modified in {days_old:.0f} days "
                    f"(threshold: {config.stale_threshold_days} days)."
                ),
                details={
                    "days_since_modification": round(days_old, 1),
                    "stale_threshold_days": config.stale_threshold_days,
                    "critical_threshold_days": config.critical_threshold_days,
                },
                detected_at=now,
            )
        )

    # --- Fresh paint alert ---
    history = metadata.revision_history
    if history:
        ref = reference
        if ref.tzinfo is None:
            ref = ref.replace(tzinfo=timezone.utc)
        gate = config.gate_date or ref
        if gate.tzinfo is None:
            gate = gate.replace(tzinfo=timezone.utc)

        burst_window_start = gate - __import__("datetime").timedelta(
            days=config.burst_edit_window_days
        )
        burst_revisions = [
            r for r in history if burst_window_start <= r.timestamp <= gate
        ]
        total_revisions = len(history)
        burst_count = len(burst_revisions)

        if burst_count >= config.burst_edit_min_count:
            burst_ratio = burst_count / max(total_revisions, 1)
            alerts.append(
                FreshnessAlert(
                    document_id=doc_id,
                    alert_type="fresh_paint",
                    severity="warning" if burst_ratio < 0.7 else "critical",
                    freshness_score=freshness_score,
                    message=(
                        f"Suspicious burst editing detected: {burst_count} "
                        f"revisions in the {config.burst_edit_window_days}-day "
                        f"window before the gate date "
                        f"({burst_ratio:.0%} of all revisions)."
                    ),
                    details={
                        "burst_edit_count": burst_count,
                        "total_revisions": total_revisions,
                        "burst_ratio": round(burst_ratio, 3),
                        "burst_window_days": config.burst_edit_window_days,
                        "gate_date": gate.isoformat(),
                    },
                    detected_at=now,
                )
            )

    # --- Incomplete provenance alert ---
    missing_fields: list[str] = []
    if metadata.modified_at is None:
        missing_fields.append("modified_at")
    if metadata.author is None:
        missing_fields.append("author")
    if metadata.created_at is None:
        missing_fields.append("created_at")

    if missing_fields:
        severity = "warning" if len(missing_fields) < 2 else "critical"
        # Only critical when the most important field (modified_at) is absent.
        if "modified_at" in missing_fields:
            severity = "critical"
        alerts.append(
            FreshnessAlert(
                document_id=doc_id,
                alert_type="incomplete_provenance",
                severity=severity,
                freshness_score=freshness_score,
                message=(
                    f"Metadata incomplete — cannot establish full audit trail. "
                    f"Missing: {', '.join(missing_fields)}."
                ),
                details={"missing_fields": missing_fields},
                detected_at=now,
            )
        )

    # --- Never updated alert ---
    is_at_version_one = (
        metadata.version_count is not None and metadata.version_count <= 1
    )
    has_no_history = not metadata.revision_history
    if is_at_version_one and has_no_history:
        alerts.append(
            FreshnessAlert(
                document_id=doc_id,
                alert_type="never_updated",
                severity="info",
                freshness_score=freshness_score,
                message=(
                    "Document is at version 1 with no recorded revision "
                    "history — no evidence of iterative development."
                ),
                details={"version_count": metadata.version_count},
                detected_at=now,
            )
        )

    return alerts


# ---------------------------------------------------------------------------
# RAG status helper
# ---------------------------------------------------------------------------


def _rag_from_score(score: float) -> str:
    """Map a freshness score to a RAG status string.

    Args:
        score: Composite freshness score in [0, 100].

    Returns:
        ``"green"``, ``"amber"``, or ``"red"``.
    """
    if score >= 80.0:
        return "green"
    if score >= 40.0:
        return "amber"
    return "red"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class FreshnessAnalyser:
    """Analyses the evidence freshness of project management documents.

    Computes per-document freshness scores (staleness, velocity, provenance)
    and aggregates them into pack-level results for collections of documents.

    Args:
        config: Freshness configuration controlling thresholds and weights.
            Defaults to :class:`~pm_data_tools.freshness.models.FreshnessConfig`
            with standard values.

    Example:
        >>> from pm_data_tools.freshness import FreshnessAnalyser, FreshnessConfig
        >>> analyser = FreshnessAnalyser(config=FreshnessConfig(stale_threshold_days=60))
        >>> result = analyser.analyse_file("schedule.xml")
        >>> print(result.freshness_score)
        72.5
        >>> print(result.rag_status)
        'amber'
    """

    def __init__(self, config: Optional[FreshnessConfig] = None) -> None:
        self._config = config or FreshnessConfig()

    @property
    def config(self) -> FreshnessConfig:
        """The active freshness configuration."""
        return self._config

    def score_metadata(self, metadata: DocumentMetadata) -> DocumentFreshnessResult:
        """Compute a freshness result for a pre-extracted ``DocumentMetadata``.

        This method is the core of the scoring engine and is decoupled from
        file I/O, making it easy to unit-test with synthetic metadata.

        Args:
            metadata: The document metadata to score.

        Returns:
            A ``DocumentFreshnessResult`` with all sub-scores, composite score,
            RAG status, and alerts.
        """
        reference = metadata.extracted_at
        if reference.tzinfo is None:
            reference = reference.replace(tzinfo=timezone.utc)

        days_old = _days_since(metadata.modified_at, reference)

        staleness = _compute_staleness_score(days_old, self._config)
        velocity = _compute_velocity_score(metadata, self._config, reference)
        provenance = _compute_provenance_score(metadata)

        composite = (
            staleness * self._config.weight_staleness
            + velocity * self._config.weight_velocity
            + provenance * self._config.weight_provenance
        )
        composite = _clamp(composite)

        alerts = _generate_alerts(
            metadata=metadata,
            staleness_score=staleness,
            velocity_score=velocity,
            freshness_score=composite,
            days_old=days_old,
            config=self._config,
            reference=reference,
        )

        return DocumentFreshnessResult(
            metadata=metadata,
            freshness_score=composite,
            staleness_score=staleness,
            velocity_score=velocity,
            provenance_score=provenance,
            rag_status=_rag_from_score(composite),
            alerts=tuple(alerts),
        )

    def analyse_file(
        self,
        file_path: str | Path,
        file_format: Optional[str] = None,
    ) -> DocumentFreshnessResult:
        """Analyse the evidence freshness of a single file.

        Extracts metadata from the file then scores it.

        Args:
            file_path: Path to the project management file.
            file_format: Optional format override. When ``None``, the format
                is auto-detected from the file extension and content.

        Returns:
            ``DocumentFreshnessResult`` for the file.

        Raises:
            FileNotFoundError: If *file_path* does not exist.

        Example:
            >>> result = analyser.analyse_file("project.xml")
            >>> print(result.freshness_score)
            85.0
        """
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        metadata = extract_metadata(path, file_format=file_format)
        return self.score_metadata(metadata)

    def analyse_pack(
        self,
        directory: str | Path,
        recursive: bool = False,
        file_format: Optional[str] = None,
    ) -> PackFreshnessResult:
        """Analyse the evidence freshness of an entire directory (evidence pack).

        Scans *directory* for supported PM file formats and computes
        per-document results, then aggregates them into a
        ``PackFreshnessResult`` with pack-level scoring and RAG status.

        The pack's ``rag_status`` reflects the weakest document:

        * ``"red"``   if any document is red.
        * ``"amber"`` if any document is amber (and none are red).
        * ``"green"`` if all documents are green.

        Args:
            directory: Path to the evidence pack directory.
            recursive: When ``True``, sub-directories are also scanned.
                Default is ``False``.
            file_format: Optional format override applied to all files.
                When ``None``, each file is auto-detected independently.

        Returns:
            ``PackFreshnessResult`` aggregating all per-document results.

        Raises:
            FileNotFoundError: If *directory* does not exist.
            ValueError: If *directory* is not a directory.

        Example:
            >>> pack = analyser.analyse_pack("/path/to/evidence/")
            >>> print(pack.overall_score)
            68.3
            >>> print(pack.rag_status)
            'amber'
        """
        dir_path = Path(directory)
        if not dir_path.exists():
            raise FileNotFoundError(f"Directory not found: {directory}")
        if not dir_path.is_dir():
            raise ValueError(f"Path is not a directory: {directory}")

        glob_pattern = "**/*" if recursive else "*"
        candidates = sorted(dir_path.glob(glob_pattern))
        files = [
            p
            for p in candidates
            if p.is_file() and p.suffix.lower() in _PM_EXTENSIONS
        ]

        doc_results: list[DocumentFreshnessResult] = []
        for file in files:
            try:
                metadata = extract_metadata(file, file_format=file_format)
                result = self.score_metadata(metadata)
                doc_results.append(result)
            except Exception:
                logger.warning("Failed to analyse %s", file, exc_info=True)

        analysed_at = datetime.now(tz=timezone.utc)

        if not doc_results:
            # Return an empty pack result rather than raising.
            return PackFreshnessResult(
                documents=(),
                overall_score=0.0,
                minimum_score=0.0,
                rag_status="red",
                green_count=0,
                amber_count=0,
                red_count=0,
                all_alerts=(),
                analysed_at=analysed_at,
            )

        scores = [r.freshness_score for r in doc_results]
        overall = sum(scores) / len(scores)
        minimum = min(scores)

        green_count = sum(1 for r in doc_results if r.rag_status == "green")
        amber_count = sum(1 for r in doc_results if r.rag_status == "amber")
        red_count = sum(1 for r in doc_results if r.rag_status == "red")

        if red_count > 0:
            pack_rag = "red"
        elif amber_count > 0:
            pack_rag = "amber"
        else:
            pack_rag = "green"

        all_alerts = tuple(
            alert for result in doc_results for alert in result.alerts
        )

        return PackFreshnessResult(
            documents=tuple(doc_results),
            overall_score=overall,
            minimum_score=minimum,
            rag_status=pack_rag,
            green_count=green_count,
            amber_count=amber_count,
            red_count=red_count,
            all_alerts=all_alerts,
            analysed_at=analysed_at,
        )
