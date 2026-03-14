"""Data models for the Evidence Freshness Detector.

This module defines the core data structures used throughout the freshness
analysis pipeline: configuration, document metadata, alerts, and results.

The design is motivated by the "Confidence and Fresh Paint" problem described
in *Next Gen Project Assurance* (Murray, Paver & Steinberg, 2026), where
documents are polished immediately before reviews whilst underlying reality
has diverged.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class FreshnessConfig:
    """Configuration for freshness scoring thresholds and weights.

    All time-based thresholds are in calendar days. Weights for the composite
    score must sum to 1.0 — validation is the caller's responsibility.

    Args:
        fresh_threshold_days: Documents modified within this window score
            green on staleness (default 30 days).
        stale_threshold_days: Documents not modified beyond this window score
            red on staleness (default 90 days).
        critical_threshold_days: Threshold at which staleness is considered
            critical for alerting purposes (default 180 days).
        burst_edit_window_days: Window (in days before the gate date) used to
            detect suspicious burst editing (default 7 days).
        burst_edit_min_count: Minimum number of edits within the burst window
            to trigger a fresh_paint alert (default 5).
        dormancy_threshold_days: A document with no edits for this many days
            during an expected-edit period is flagged for long dormancy
            (default 60 days).
        weight_staleness: Weight applied to the staleness sub-score in the
            composite freshness score (default 0.5).
        weight_velocity: Weight applied to the velocity sub-score (default 0.3).
        weight_provenance: Weight applied to the provenance sub-score
            (default 0.2).
        gate_date: Optional reference date for "fresh paint" detection. When
            set, burst editing in the ``burst_edit_window_days`` before this
            date is flagged as suspicious.
    """

    fresh_threshold_days: int = 30
    stale_threshold_days: int = 90
    critical_threshold_days: int = 180
    burst_edit_window_days: int = 7
    burst_edit_min_count: int = 5
    dormancy_threshold_days: int = 60
    weight_staleness: float = 0.5
    weight_velocity: float = 0.3
    weight_provenance: float = 0.2
    gate_date: Optional[datetime] = None


@dataclass(frozen=True)
class RevisionEntry:
    """A single entry in a document's revision history.

    Args:
        timestamp: When this revision was made.
        author: Who made this revision, or ``None`` if unknown.
        summary: Brief description of the change, or ``None`` if unavailable.
    """

    timestamp: datetime
    author: Optional[str] = None
    summary: Optional[str] = None

    def __str__(self) -> str:
        """Return human-readable representation."""
        parts = [self.timestamp.isoformat()]
        if self.author:
            parts.append(f"by {self.author}")
        if self.summary:
            parts.append(f'— "{self.summary}"')
        return " ".join(parts)


@dataclass(frozen=True)
class DocumentMetadata:
    """Metadata extracted from a project management document.

    Combines OS-level file metadata with format-specific provenance
    information where available. Fields are ``None`` when the information
    cannot be obtained from either source.

    Args:
        file_path: Original file path or identifier.
        file_format: One of the eight supported format identifiers
            (``mspdi``, ``p6_xer``, ``nista``, ``jira``, ``monday``,
            ``asana``, ``smartsheet``, ``gmpp``), or ``None`` for unknown.
        file_size_bytes: File size in bytes, or ``None``.
        created_at: File creation timestamp, or ``None``.
        modified_at: Last modification timestamp.  This is the most critical
            field for freshness assessment; ``None`` means it cannot be
            determined.
        accessed_at: Last access timestamp, or ``None``.
        author: Document author from file or format metadata, or ``None``.
        last_modified_by: Last modifier from format metadata, or ``None``.
        version_count: Number of revisions/versions recorded by the format,
            or ``None`` when unavailable.
        revision_history: Ordered list of revision entries (oldest first),
            where the format exposes this information.
        content_hash: SHA-256 hex digest of file contents for change
            detection across runs, or ``None`` if the file could not be
            read.
        extracted_at: Timestamp at which we extracted this metadata (our
            processing time, always populated).
    """

    file_path: str
    extracted_at: datetime
    file_format: Optional[str] = None
    file_size_bytes: Optional[int] = None
    created_at: Optional[datetime] = None
    modified_at: Optional[datetime] = None
    accessed_at: Optional[datetime] = None
    author: Optional[str] = None
    last_modified_by: Optional[str] = None
    version_count: Optional[int] = None
    revision_history: tuple[RevisionEntry, ...] = field(default_factory=tuple)
    content_hash: Optional[str] = None

    def __str__(self) -> str:
        """Return human-readable representation."""
        fmt = self.file_format or "unknown"
        mod = self.modified_at.isoformat() if self.modified_at else "unknown"
        return f"DocumentMetadata({self.file_path!r}, format={fmt}, modified={mod})"


@dataclass(frozen=True)
class FreshnessAlert:
    """A structured alert produced by the freshness analyser.

    Args:
        document_id: File path or identifier of the affected document.
        alert_type: One of ``"stale"``, ``"fresh_paint"``,
            ``"incomplete_provenance"``, or ``"never_updated"``.
        severity: One of ``"info"``, ``"warning"``, or ``"critical"``.
        freshness_score: The composite freshness score for this document
            at the time of detection (0–100).
        message: Human-readable description of the alert.
        details: Format-specific contextual information (e.g. days since
            last edit, number of burst edits).
        detected_at: Timestamp at which this alert was generated.
    """

    document_id: str
    alert_type: str
    severity: str
    freshness_score: float
    message: str
    details: dict
    detected_at: datetime

    def to_dict(self) -> dict:
        """Serialise to a plain dictionary for JSON output.

        Returns:
            Dictionary representation with ``detected_at`` as ISO string.
        """
        return {
            "document_id": self.document_id,
            "alert_type": self.alert_type,
            "severity": self.severity,
            "freshness_score": round(self.freshness_score, 2),
            "message": self.message,
            "details": self.details,
            "detected_at": self.detected_at.isoformat(),
        }

    def __str__(self) -> str:
        """Return human-readable representation."""
        return (
            f"[{self.severity.upper()}] {self.alert_type}: "
            f"{self.message} (score={self.freshness_score:.1f})"
        )


@dataclass(frozen=True)
class DocumentFreshnessResult:
    """Freshness analysis result for a single document.

    Args:
        metadata: The underlying document metadata used for analysis.
        freshness_score: Composite score in [0, 100] where 100 is perfectly
            fresh.
        staleness_score: Sub-score measuring time since last modification
            (0–100).
        velocity_score: Sub-score measuring edit frequency patterns (0–100).
        provenance_score: Sub-score measuring metadata completeness (0–100).
        rag_status: Traffic-light status derived from the composite score:
            ``"green"``, ``"amber"``, or ``"red"``.
        alerts: Alerts raised during analysis.
    """

    metadata: DocumentMetadata
    freshness_score: float
    staleness_score: float
    velocity_score: float
    provenance_score: float
    rag_status: str
    alerts: tuple[FreshnessAlert, ...]

    def to_dict(self) -> dict:
        """Serialise to a plain dictionary for JSON output.

        Returns:
            Nested dictionary representation suitable for JSON serialisation.
        """
        return {
            "file_path": self.metadata.file_path,
            "file_format": self.metadata.file_format,
            "freshness_score": round(self.freshness_score, 2),
            "staleness_score": round(self.staleness_score, 2),
            "velocity_score": round(self.velocity_score, 2),
            "provenance_score": round(self.provenance_score, 2),
            "rag_status": self.rag_status,
            "modified_at": (
                self.metadata.modified_at.isoformat()
                if self.metadata.modified_at
                else None
            ),
            "version_count": self.metadata.version_count,
            "author": self.metadata.author,
            "last_modified_by": self.metadata.last_modified_by,
            "alerts": [a.to_dict() for a in self.alerts],
        }

    def __str__(self) -> str:
        """Return human-readable representation."""
        return (
            f"DocumentFreshnessResult({self.metadata.file_path!r}, "
            f"score={self.freshness_score:.1f}, rag={self.rag_status})"
        )


@dataclass(frozen=True)
class PackFreshnessResult:
    """Aggregated freshness analysis result for an evidence pack (collection of
    documents).

    Args:
        documents: Per-document results, one per analysed file.
        overall_score: Mean freshness score across all documents.
        minimum_score: Freshness score of the weakest-link document.
        rag_status: Pack-level traffic-light status based on configurable
            rules (worst-of-pack when any document is red; amber when any
            amber; green otherwise).
        green_count: Number of documents with green status.
        amber_count: Number of documents with amber status.
        red_count: Number of documents with red status.
        all_alerts: All alerts raised across all documents.
        analysed_at: Timestamp of the pack analysis.
    """

    documents: tuple[DocumentFreshnessResult, ...]
    overall_score: float
    minimum_score: float
    rag_status: str
    green_count: int
    amber_count: int
    red_count: int
    all_alerts: tuple[FreshnessAlert, ...]
    analysed_at: datetime

    def to_dict(self) -> dict:
        """Serialise to a plain dictionary for JSON output.

        Returns:
            Nested dictionary representation suitable for JSON serialisation.
        """
        return {
            "overall_score": round(self.overall_score, 2),
            "minimum_score": round(self.minimum_score, 2),
            "rag_status": self.rag_status,
            "document_count": len(self.documents),
            "green_count": self.green_count,
            "amber_count": self.amber_count,
            "red_count": self.red_count,
            "alert_count": len(self.all_alerts),
            "analysed_at": self.analysed_at.isoformat(),
            "documents": [d.to_dict() for d in self.documents],
            "alerts": [a.to_dict() for a in self.all_alerts],
        }

    def __str__(self) -> str:
        """Return human-readable representation."""
        return (
            f"PackFreshnessResult("
            f"{len(self.documents)} docs, "
            f"score={self.overall_score:.1f}, "
            f"rag={self.rag_status}, "
            f"alerts={len(self.all_alerts)})"
        )
