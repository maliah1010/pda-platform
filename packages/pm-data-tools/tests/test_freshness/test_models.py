"""Unit tests for freshness data models.

Tests cover immutability, serialisation, string representations, and
edge cases such as empty revision history.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from pm_data_tools.freshness.models import (
    DocumentFreshnessResult,
    DocumentMetadata,
    FreshnessAlert,
    FreshnessConfig,
    PackFreshnessResult,
    RevisionEntry,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utc(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, tzinfo=timezone.utc)


def _make_metadata(
    file_path: str = "test.xml",
    modified_at: datetime | None = None,
    author: str | None = None,
    version_count: int | None = None,
) -> DocumentMetadata:
    return DocumentMetadata(
        file_path=file_path,
        extracted_at=_utc(2026, 3, 1),
        modified_at=modified_at,
        author=author,
        version_count=version_count,
    )


def _make_alert(
    alert_type: str = "stale",
    severity: str = "warning",
    score: float = 50.0,
) -> FreshnessAlert:
    return FreshnessAlert(
        document_id="test.xml",
        alert_type=alert_type,
        severity=severity,
        freshness_score=score,
        message="Test alert.",
        details={"key": "value"},
        detected_at=_utc(2026, 3, 1),
    )


# ---------------------------------------------------------------------------
# FreshnessConfig
# ---------------------------------------------------------------------------


class TestFreshnessConfig:
    """Tests for FreshnessConfig."""

    def test_default_values(self) -> None:
        config = FreshnessConfig()
        assert config.fresh_threshold_days == 30
        assert config.stale_threshold_days == 90
        assert config.critical_threshold_days == 180
        assert config.burst_edit_window_days == 7
        assert config.burst_edit_min_count == 5
        assert config.dormancy_threshold_days == 60
        assert config.weight_staleness == 0.5
        assert config.weight_velocity == 0.3
        assert config.weight_provenance == 0.2
        assert config.gate_date is None

    def test_custom_values(self) -> None:
        gate = _utc(2026, 4, 1)
        config = FreshnessConfig(
            fresh_threshold_days=14,
            stale_threshold_days=60,
            gate_date=gate,
        )
        assert config.fresh_threshold_days == 14
        assert config.stale_threshold_days == 60
        assert config.gate_date == gate

    def test_immutable(self) -> None:
        config = FreshnessConfig()
        with pytest.raises((AttributeError, TypeError)):
            config.fresh_threshold_days = 99  # type: ignore[misc]


# ---------------------------------------------------------------------------
# RevisionEntry
# ---------------------------------------------------------------------------


class TestRevisionEntry:
    """Tests for RevisionEntry."""

    def test_minimal_creation(self) -> None:
        ts = _utc(2026, 1, 1)
        entry = RevisionEntry(timestamp=ts)
        assert entry.timestamp == ts
        assert entry.author is None
        assert entry.summary is None

    def test_full_creation(self) -> None:
        ts = _utc(2026, 1, 15)
        entry = RevisionEntry(timestamp=ts, author="Alice", summary="Updated costs")
        assert entry.author == "Alice"
        assert entry.summary == "Updated costs"

    def test_str_minimal(self) -> None:
        ts = _utc(2026, 1, 1)
        entry = RevisionEntry(timestamp=ts)
        assert "2026-01-01" in str(entry)

    def test_str_full(self) -> None:
        ts = _utc(2026, 1, 15)
        entry = RevisionEntry(timestamp=ts, author="Bob", summary="Draft")
        text = str(entry)
        assert "Bob" in text
        assert "Draft" in text

    def test_immutable(self) -> None:
        entry = RevisionEntry(timestamp=_utc(2026, 1, 1))
        with pytest.raises((AttributeError, TypeError)):
            entry.author = "Eve"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# DocumentMetadata
# ---------------------------------------------------------------------------


class TestDocumentMetadata:
    """Tests for DocumentMetadata."""

    def test_minimal_creation(self) -> None:
        extracted = _utc(2026, 3, 1)
        meta = DocumentMetadata(file_path="proj.xml", extracted_at=extracted)
        assert meta.file_path == "proj.xml"
        assert meta.extracted_at == extracted
        assert meta.file_format is None
        assert meta.modified_at is None
        assert meta.revision_history == ()

    def test_full_creation(self) -> None:
        rev = RevisionEntry(timestamp=_utc(2026, 1, 10))
        meta = DocumentMetadata(
            file_path="schedule.mpp",
            extracted_at=_utc(2026, 3, 1),
            file_format="mspdi",
            file_size_bytes=1024,
            created_at=_utc(2025, 6, 1),
            modified_at=_utc(2026, 2, 15),
            author="Project Manager",
            last_modified_by="Deputy PM",
            version_count=12,
            revision_history=(rev,),
            content_hash="abc123",
        )
        assert meta.file_format == "mspdi"
        assert meta.version_count == 12
        assert len(meta.revision_history) == 1

    def test_immutable(self) -> None:
        meta = _make_metadata()
        with pytest.raises((AttributeError, TypeError)):
            meta.file_path = "other.xml"  # type: ignore[misc]

    def test_str(self) -> None:
        meta = _make_metadata("schedule.xml", modified_at=_utc(2026, 2, 1))
        text = str(meta)
        assert "schedule.xml" in text
        assert "2026-02-01" in text


# ---------------------------------------------------------------------------
# FreshnessAlert
# ---------------------------------------------------------------------------


class TestFreshnessAlert:
    """Tests for FreshnessAlert."""

    def test_to_dict(self) -> None:
        alert = _make_alert("stale", "critical", 20.0)
        d = alert.to_dict()
        assert d["alert_type"] == "stale"
        assert d["severity"] == "critical"
        assert d["freshness_score"] == 20.0
        assert "detected_at" in d
        assert isinstance(d["details"], dict)

    def test_str(self) -> None:
        alert = _make_alert("fresh_paint", "warning", 55.0)
        text = str(alert)
        assert "fresh_paint" in text
        assert "WARNING" in text

    def test_score_rounded_to_two_dp(self) -> None:
        alert = _make_alert(score=73.456789)
        d = alert.to_dict()
        assert d["freshness_score"] == 73.46

    def test_immutable(self) -> None:
        alert = _make_alert()
        with pytest.raises((AttributeError, TypeError)):
            alert.severity = "info"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# DocumentFreshnessResult
# ---------------------------------------------------------------------------


class TestDocumentFreshnessResult:
    """Tests for DocumentFreshnessResult."""

    def test_to_dict_structure(self) -> None:
        meta = _make_metadata("proj.xml", modified_at=_utc(2026, 2, 1), author="PM")
        alert = _make_alert()
        result = DocumentFreshnessResult(
            metadata=meta,
            freshness_score=72.5,
            staleness_score=80.0,
            velocity_score=60.0,
            provenance_score=65.0,
            rag_status="amber",
            alerts=(alert,),
        )
        d = result.to_dict()
        assert d["file_path"] == "proj.xml"
        assert d["freshness_score"] == 72.5
        assert d["rag_status"] == "amber"
        assert d["author"] == "PM"
        assert len(d["alerts"]) == 1

    def test_str(self) -> None:
        meta = _make_metadata()
        result = DocumentFreshnessResult(
            metadata=meta,
            freshness_score=45.0,
            staleness_score=40.0,
            velocity_score=50.0,
            provenance_score=50.0,
            rag_status="amber",
            alerts=(),
        )
        text = str(result)
        assert "45.0" in text
        assert "amber" in text

    def test_scores_rounded(self) -> None:
        meta = _make_metadata()
        result = DocumentFreshnessResult(
            metadata=meta,
            freshness_score=72.333,
            staleness_score=80.666,
            velocity_score=60.111,
            provenance_score=65.999,
            rag_status="amber",
            alerts=(),
        )
        d = result.to_dict()
        assert d["freshness_score"] == 72.33
        assert d["staleness_score"] == 80.67


# ---------------------------------------------------------------------------
# PackFreshnessResult
# ---------------------------------------------------------------------------


class TestPackFreshnessResult:
    """Tests for PackFreshnessResult."""

    def _make_doc_result(self, score: float, rag: str) -> DocumentFreshnessResult:
        meta = _make_metadata()
        return DocumentFreshnessResult(
            metadata=meta,
            freshness_score=score,
            staleness_score=score,
            velocity_score=score,
            provenance_score=score,
            rag_status=rag,
            alerts=(),
        )

    def test_to_dict_structure(self) -> None:
        docs = (
            self._make_doc_result(85.0, "green"),
            self._make_doc_result(55.0, "amber"),
            self._make_doc_result(25.0, "red"),
        )
        pack = PackFreshnessResult(
            documents=docs,
            overall_score=55.0,
            minimum_score=25.0,
            rag_status="red",
            green_count=1,
            amber_count=1,
            red_count=1,
            all_alerts=(),
            analysed_at=_utc(2026, 3, 1),
        )
        d = pack.to_dict()
        assert d["document_count"] == 3
        assert d["rag_status"] == "red"
        assert d["green_count"] == 1
        assert d["red_count"] == 1
        assert len(d["documents"]) == 3

    def test_str(self) -> None:
        docs = (self._make_doc_result(90.0, "green"),)
        pack = PackFreshnessResult(
            documents=docs,
            overall_score=90.0,
            minimum_score=90.0,
            rag_status="green",
            green_count=1,
            amber_count=0,
            red_count=0,
            all_alerts=(),
            analysed_at=_utc(2026, 3, 1),
        )
        text = str(pack)
        assert "green" in text
        assert "90.0" in text
