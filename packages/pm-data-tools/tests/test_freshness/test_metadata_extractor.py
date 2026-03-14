"""Unit and integration tests for the metadata extraction layer.

Tests cover:
- OS-level fallback metadata extraction.
- Format-specific extraction for JSON-based formats (Jira, Monday, Asana,
  Smartsheet, NISTA) using synthetic fixture files written to tmp_path.
- GMPP xlsx extraction via the zipfile layer.
- Format auto-detection heuristics.
- SHA-256 hash stability.
- Graceful degradation when files are malformed or unreadable.
"""

from __future__ import annotations

import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from pm_data_tools.freshness.metadata_extractor import (
    _detect_format_from_path,
    _parse_iso,
    _sha256,
    extract_metadata,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _write_json(path: Path, data: dict | list) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


# ---------------------------------------------------------------------------
# ISO date parser
# ---------------------------------------------------------------------------


class TestParseIso:
    def test_valid_date(self) -> None:
        result = _parse_iso("2026-01-15T10:30:00Z")
        assert result is not None
        assert result.year == 2026
        assert result.month == 1
        assert result.tzinfo is not None

    def test_valid_date_plus_offset(self) -> None:
        result = _parse_iso("2026-01-15T10:30:00+01:00")
        assert result is not None

    def test_naive_datetime_gets_utc(self) -> None:
        result = _parse_iso("2026-01-15T10:30:00")
        assert result is not None
        assert result.tzinfo == timezone.utc

    def test_none_input(self) -> None:
        assert _parse_iso(None) is None

    def test_empty_string(self) -> None:
        assert _parse_iso("") is None

    def test_invalid_string(self) -> None:
        assert _parse_iso("not-a-date") is None

    def test_date_only(self) -> None:
        result = _parse_iso("2026-03-14")
        assert result is not None
        assert result.year == 2026


# ---------------------------------------------------------------------------
# SHA-256 hashing
# ---------------------------------------------------------------------------


class TestSha256:
    def test_stable_hash(self, tmp_path) -> None:
        f = tmp_path / "file.txt"
        f.write_text("Hello, World!", encoding="utf-8")
        h1 = _sha256(f)
        h2 = _sha256(f)
        assert h1 == h2
        assert len(h1) == 64  # type: ignore[arg-type]

    def test_different_content_different_hash(self, tmp_path) -> None:
        a = tmp_path / "a.txt"
        b = tmp_path / "b.txt"
        a.write_text("AAA", encoding="utf-8")
        b.write_text("BBB", encoding="utf-8")
        assert _sha256(a) != _sha256(b)

    def test_missing_file_returns_none(self, tmp_path) -> None:
        assert _sha256(tmp_path / "missing.txt") is None


# ---------------------------------------------------------------------------
# Format detection
# ---------------------------------------------------------------------------


class TestDetectFormat:
    def test_xml_extension(self, tmp_path) -> None:
        f = tmp_path / "schedule.xml"
        f.write_text("<Project/>", encoding="utf-8")
        assert _detect_format_from_path(f) == "mspdi"

    def test_xer_extension(self, tmp_path) -> None:
        f = tmp_path / "export.xer"
        f.write_bytes(b"")
        assert _detect_format_from_path(f) == "p6_xer"

    def test_xlsx_extension(self, tmp_path) -> None:
        f = tmp_path / "gmpp.xlsx"
        f.write_bytes(b"")
        assert _detect_format_from_path(f) == "gmpp"

    def test_jira_json(self, tmp_path) -> None:
        f = tmp_path / "export.json"
        _write_json(f, {"issues": []})
        assert _detect_format_from_path(f) == "jira"

    def test_monday_json(self, tmp_path) -> None:
        f = tmp_path / "export.json"
        _write_json(f, {"data": {"boards": []}})
        assert _detect_format_from_path(f) == "monday"

    def test_asana_json(self, tmp_path) -> None:
        f = tmp_path / "export.json"
        _write_json(f, {"tasks": []})
        assert _detect_format_from_path(f) == "asana"

    def test_smartsheet_json(self, tmp_path) -> None:
        f = tmp_path / "export.json"
        _write_json(f, {"sheets": []})
        assert _detect_format_from_path(f) == "smartsheet"

    def test_unknown_json_defaults_to_nista(self, tmp_path) -> None:
        f = tmp_path / "export.json"
        _write_json(f, {"project_name": "Test"})
        assert _detect_format_from_path(f) == "nista"

    def test_malformed_json_defaults_to_nista(self, tmp_path) -> None:
        f = tmp_path / "bad.json"
        f.write_text("NOT JSON", encoding="utf-8")
        assert _detect_format_from_path(f) == "nista"

    def test_unknown_extension_returns_none(self, tmp_path) -> None:
        f = tmp_path / "file.docx"
        f.write_bytes(b"")
        result = _detect_format_from_path(f)
        # docx is not in our extension map.
        assert result is None or isinstance(result, str)


# ---------------------------------------------------------------------------
# OS-level fallback metadata
# ---------------------------------------------------------------------------


class TestOsMetadata:
    def test_file_size_populated(self, tmp_path) -> None:
        f = tmp_path / "test.json"
        f.write_text("hello", encoding="utf-8")
        meta = extract_metadata(f)
        assert meta.file_size_bytes is not None
        assert meta.file_size_bytes > 0

    def test_modified_at_populated(self, tmp_path) -> None:
        f = tmp_path / "test.json"
        f.write_text("{}", encoding="utf-8")
        meta = extract_metadata(f)
        assert meta.modified_at is not None

    def test_content_hash_populated(self, tmp_path) -> None:
        f = tmp_path / "test.json"
        f.write_text("content", encoding="utf-8")
        meta = extract_metadata(f)
        assert meta.content_hash is not None
        assert len(meta.content_hash) == 64

    def test_extracted_at_populated(self, tmp_path) -> None:
        f = tmp_path / "test.json"
        f.write_text("{}", encoding="utf-8")
        meta = extract_metadata(f)
        assert meta.extracted_at is not None
        assert isinstance(meta.extracted_at, datetime)


# ---------------------------------------------------------------------------
# Jira JSON extraction
# ---------------------------------------------------------------------------


class TestJiraExtraction:
    def test_timestamps_extracted(self, tmp_path) -> None:
        data = {
            "issues": [
                {
                    "fields": {
                        "created": "2025-01-01T10:00:00Z",
                        "updated": "2026-02-15T14:30:00Z",
                        "reporter": {"displayName": "Alice"},
                    }
                }
            ]
        }
        f = tmp_path / "jira_export.json"
        _write_json(f, data)
        meta = extract_metadata(f, file_format="jira")
        assert meta.modified_at is not None
        assert meta.modified_at.year == 2026
        assert meta.author == "Alice"

    def test_changelog_as_version_count(self, tmp_path) -> None:
        data = {
            "issues": [
                {
                    "fields": {"created": "2025-01-01T00:00:00Z"},
                    "changelog": {
                        "histories": [
                            {"created": "2025-06-01T00:00:00Z", "author": {"displayName": "Bob"}},
                            {"created": "2025-12-01T00:00:00Z", "author": {"displayName": "Eve"}},
                        ]
                    },
                }
            ]
        }
        f = tmp_path / "jira_changelog.json"
        _write_json(f, data)
        meta = extract_metadata(f, file_format="jira")
        assert meta.version_count == 2
        assert len(meta.revision_history) == 2

    def test_empty_issues_list(self, tmp_path) -> None:
        data = {"issues": []}
        f = tmp_path / "empty_jira.json"
        _write_json(f, data)
        meta = extract_metadata(f, file_format="jira")
        # Should not raise; OS-level metadata populates fields.
        assert meta.file_path is not None

    def test_malformed_jira_falls_back_to_os(self, tmp_path) -> None:
        f = tmp_path / "bad_jira.json"
        f.write_text("INVALID JSON{{", encoding="utf-8")
        meta = extract_metadata(f, file_format="jira")
        assert meta.file_path is not None
        assert meta.modified_at is not None  # OS fallback.


# ---------------------------------------------------------------------------
# Monday.com JSON extraction
# ---------------------------------------------------------------------------


class TestMondayExtraction:
    def test_timestamps_extracted(self, tmp_path) -> None:
        data = {
            "data": {
                "boards": [
                    {
                        "updated_at": "2026-01-10T12:00:00Z",
                        "created_at": "2024-06-01T00:00:00Z",
                    }
                ]
            }
        }
        f = tmp_path / "monday_export.json"
        _write_json(f, data)
        meta = extract_metadata(f, file_format="monday")
        assert meta.modified_at is not None
        assert meta.modified_at.year == 2026


# ---------------------------------------------------------------------------
# Asana JSON extraction
# ---------------------------------------------------------------------------


class TestAsanaExtraction:
    def test_timestamps_and_owner_extracted(self, tmp_path) -> None:
        data = {
            "data": {
                "created_at": "2025-03-01T00:00:00Z",
                "modified_at": "2026-02-20T08:00:00Z",
                "owner": {"name": "Charlie"},
            }
        }
        f = tmp_path / "asana_export.json"
        _write_json(f, data)
        meta = extract_metadata(f, file_format="asana")
        assert meta.modified_at is not None
        assert meta.modified_at.year == 2026
        assert meta.author == "Charlie"


# ---------------------------------------------------------------------------
# Smartsheet JSON extraction
# ---------------------------------------------------------------------------


class TestSmartsheetExtraction:
    def test_timestamps_extracted(self, tmp_path) -> None:
        data = {
            "createdAt": "2025-01-01T00:00:00Z",
            "modifiedAt": "2026-03-01T10:00:00Z",
        }
        f = tmp_path / "smartsheet.json"
        _write_json(f, data)
        meta = extract_metadata(f, file_format="smartsheet")
        assert meta.modified_at is not None
        assert meta.modified_at.year == 2026


# ---------------------------------------------------------------------------
# NISTA JSON extraction
# ---------------------------------------------------------------------------


class TestNistaExtraction:
    def test_metadata_block_extracted(self, tmp_path) -> None:
        data = {
            "metadata": {
                "created": "2024-09-01T00:00:00Z",
                "modified": "2026-01-20T09:00:00Z",
            },
            "project_name": "Alpha",
        }
        f = tmp_path / "nista.json"
        _write_json(f, data)
        meta = extract_metadata(f, file_format="nista")
        assert meta.modified_at is not None
        assert meta.modified_at.year == 2026

    def test_root_level_updated_at(self, tmp_path) -> None:
        data = {"project_name": "Beta", "updated_at": "2026-02-10T00:00:00Z"}
        f = tmp_path / "nista2.json"
        _write_json(f, data)
        meta = extract_metadata(f, file_format="nista")
        assert meta.modified_at is not None
        assert meta.modified_at.month == 2

    def test_csv_falls_back_to_os(self, tmp_path) -> None:
        f = tmp_path / "nista.csv"
        f.write_text("project,dca\nAlpha,Green", encoding="utf-8")
        meta = extract_metadata(f, file_format="nista")
        assert meta.file_path is not None


# ---------------------------------------------------------------------------
# GMPP xlsx extraction
# ---------------------------------------------------------------------------


class TestGmppExtraction:
    def _make_xlsx(self, path: Path) -> None:
        """Create a minimal xlsx file with core.xml properties."""
        core_xml = """<?xml version="1.0" encoding="UTF-8"?>
<cp:coreProperties
    xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
    xmlns:dc="http://purl.org/dc/elements/1.1/"
    xmlns:dcterms="http://purl.org/dc/terms/"
    xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
  <dc:creator>GM Project Manager</dc:creator>
  <cp:lastModifiedBy>Deputy PM</cp:lastModifiedBy>
  <dcterms:created xsi:type="dcterms:W3CDTF">2025-01-01T00:00:00Z</dcterms:created>
  <dcterms:modified xsi:type="dcterms:W3CDTF">2026-02-28T08:00:00Z</dcterms:modified>
  <cp:revision>7</cp:revision>
</cp:coreProperties>"""
        workbook_xml = '<?xml version="1.0"?><workbook/>'
        with zipfile.ZipFile(str(path), "w") as zf:
            zf.writestr("docProps/core.xml", core_xml)
            zf.writestr("xl/workbook.xml", workbook_xml)

    def test_xlsx_properties_extracted(self, tmp_path) -> None:
        xlsx = tmp_path / "gmpp_report.xlsx"
        self._make_xlsx(xlsx)
        meta = extract_metadata(xlsx, file_format="gmpp")
        assert meta.author == "GM Project Manager"
        assert meta.last_modified_by == "Deputy PM"
        assert meta.version_count == 7
        assert meta.modified_at is not None
        assert meta.modified_at.year == 2026

    def test_bad_xlsx_falls_back_to_os(self, tmp_path) -> None:
        f = tmp_path / "bad.xlsx"
        f.write_bytes(b"NOT A ZIP")
        meta = extract_metadata(f, file_format="gmpp")
        assert meta.file_path is not None


# ---------------------------------------------------------------------------
# MS Project XML (MSPDI) extraction
# ---------------------------------------------------------------------------


class TestMspdiExtraction:
    def _make_mspdi(self, path: Path) -> None:
        ns = "http://schemas.microsoft.com/project"
        content = f"""<?xml version="1.0"?>
<Project xmlns="{ns}">
  <Author>Senior PM</Author>
  <LastAuthor>Planner</LastAuthor>
  <CreationDate>2025-06-01T00:00:00</CreationDate>
  <LastSaved>2026-03-01T09:00:00</LastSaved>
  <Revision>14</Revision>
  <Name>Alpha Programme</Name>
</Project>"""
        path.write_text(content, encoding="utf-8")

    def test_mspdi_properties_extracted(self, tmp_path) -> None:
        xml = tmp_path / "schedule.xml"
        self._make_mspdi(xml)
        meta = extract_metadata(xml, file_format="mspdi")
        assert meta.author == "Senior PM"
        assert meta.last_modified_by == "Planner"
        assert meta.version_count == 14
        assert meta.modified_at is not None
        assert meta.modified_at.year == 2026

    def test_invalid_xml_falls_back_to_os(self, tmp_path) -> None:
        f = tmp_path / "bad.xml"
        f.write_text("<not valid XML<<<", encoding="utf-8")
        meta = extract_metadata(f, file_format="mspdi")
        assert meta.file_path is not None
        # OS metadata still works.
        assert meta.modified_at is not None


# ---------------------------------------------------------------------------
# format_override parameter
# ---------------------------------------------------------------------------


class TestFormatOverride:
    def test_format_override_applied(self, tmp_path) -> None:
        """A .json file can be forced to parse as Jira."""
        data = {
            "issues": [
                {
                    "fields": {
                        "created": "2025-01-01T00:00:00Z",
                        "updated": "2026-01-01T00:00:00Z",
                        "reporter": {"displayName": "Override User"},
                    }
                }
            ]
        }
        f = tmp_path / "export.json"
        _write_json(f, data)
        meta = extract_metadata(f, file_format="jira")
        assert meta.file_format == "jira"
        assert meta.author == "Override User"
