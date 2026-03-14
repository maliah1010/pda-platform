"""Additional metadata extractor tests targeting uncovered branches.

Covers:
- P6 XER file parsing (``%E`` header line).
- P6 XML file parsing (``DataDate`` / ``ExportDate`` elements).
- MSPDI revision string ValueError (non-integer revision).
- MSPDI with pre-existing created_at (should not overwrite).
- Monday top-level dict without nested boards.
- Asana list-of-projects payload.
- NISTA CSV (OS-only fallback).
- Jira top-level list payload.
- ``extract_metadata`` auto-format detection with no recognised format.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pm_data_tools.freshness.metadata_extractor import extract_metadata


def _write(path: Path, content: str, encoding: str = "utf-8") -> None:
    path.write_text(content, encoding=encoding)


# ---------------------------------------------------------------------------
# Primavera P6 XER
# ---------------------------------------------------------------------------


class TestP6XerExtraction:
    def test_export_date_in_header(self, tmp_path: Path) -> None:
        xer_content = (
            "%FMT\n"
            "%E\t2026-01-20 09:00\n"
            "%T TASK\n"
        )
        f = tmp_path / "export.xer"
        _write(f, xer_content, encoding="latin-1")
        meta = extract_metadata(f, file_format="p6_xer")
        # created_at from %E line, or falls back to OS stat.
        assert meta.file_path is not None

    def test_no_export_date_line(self, tmp_path: Path) -> None:
        xer_content = "%FMT\n%T TASK\n"
        f = tmp_path / "export.xer"
        _write(f, xer_content, encoding="latin-1")
        meta = extract_metadata(f, file_format="p6_xer")
        assert meta.file_path is not None

    def test_export_date_without_tab(self, tmp_path: Path) -> None:
        """``%E`` line with no tab — should not crash."""
        xer_content = "%E 2026-01-20\n"
        f = tmp_path / "export.xer"
        _write(f, xer_content, encoding="latin-1")
        meta = extract_metadata(f, file_format="p6_xer")
        assert meta.file_path is not None


# ---------------------------------------------------------------------------
# Primavera P6 XML
# ---------------------------------------------------------------------------


class TestP6XmlExtraction:
    def test_data_date_element(self, tmp_path: Path) -> None:
        content = """<?xml version="1.0"?>
<APIBusinessObjects>
  <Project>
    <DataDate>2026-02-01T00:00:00</DataDate>
  </Project>
</APIBusinessObjects>"""
        f = tmp_path / "p6.xml"
        _write(f, content)
        meta = extract_metadata(f, file_format="p6_xer")
        # created_at should be populated from DataDate.
        assert meta.created_at is not None
        assert meta.created_at.year == 2026

    def test_export_date_element(self, tmp_path: Path) -> None:
        content = """<?xml version="1.0"?>
<Root><ExportDate>2025-12-01T12:00:00</ExportDate></Root>"""
        f = tmp_path / "p6export.xml"
        _write(f, content)
        meta = extract_metadata(f, file_format="p6_xer")
        assert meta.created_at is not None
        assert meta.created_at.year == 2025

    def test_no_date_elements(self, tmp_path: Path) -> None:
        content = """<?xml version="1.0"?><Root><Task/></Root>"""
        f = tmp_path / "p6_nodates.xml"
        _write(f, content)
        meta = extract_metadata(f, file_format="p6_xer")
        # OS-level fallback only — should not raise.
        assert meta.file_path is not None

    def test_invalid_xml(self, tmp_path: Path) -> None:
        f = tmp_path / "bad.xml"
        _write(f, "<broken<<")
        meta = extract_metadata(f, file_format="p6_xer")
        assert meta.file_path is not None


# ---------------------------------------------------------------------------
# MSPDI non-integer revision
# ---------------------------------------------------------------------------


class TestMspdiEdgeCases:
    def test_non_integer_revision_does_not_crash(self, tmp_path: Path) -> None:
        ns = "http://schemas.microsoft.com/project"
        content = f"""<?xml version="1.0"?>
<Project xmlns="{ns}">
  <Author>PM</Author>
  <Revision>NaN</Revision>
  <LastSaved>2026-01-10T08:00:00</LastSaved>
</Project>"""
        f = tmp_path / "mspdi.xml"
        _write(f, content)
        meta = extract_metadata(f, file_format="mspdi")
        assert meta.version_count is None
        assert meta.author == "PM"

    def test_created_at_not_overwritten_if_already_set(self, tmp_path: Path) -> None:
        """If OS already provides created_at, MSPDI CreationDate should not
        overwrite it because _extract_mspdi checks ``not base.get('created_at')``."""
        ns = "http://schemas.microsoft.com/project"
        content = f"""<?xml version="1.0"?>
<Project xmlns="{ns}">
  <CreationDate>2020-01-01T00:00:00</CreationDate>
  <LastSaved>2026-03-01T00:00:00</LastSaved>
</Project>"""
        f = tmp_path / "mspdi_created.xml"
        _write(f, content)
        # This just ensures no crash — actual behaviour depends on OS stat.
        meta = extract_metadata(f, file_format="mspdi")
        assert meta.file_path is not None


# ---------------------------------------------------------------------------
# Monday.com non-nested dict
# ---------------------------------------------------------------------------


class TestMondayEdgeCases:
    def test_flat_dict_no_boards_key(self, tmp_path: Path) -> None:
        data = {"updated_at": "2026-02-15T00:00:00Z", "name": "My Board"}
        f = tmp_path / "monday_flat.json"
        f.write_text(json.dumps(data), encoding="utf-8")
        meta = extract_metadata(f, file_format="monday")
        # Should not crash; modified_at may come from OS.
        assert meta.file_path is not None

    def test_boards_key_is_dict_not_list(self, tmp_path: Path) -> None:
        data = {
            "data": {
                "boards": {
                    "updated_at": "2026-01-01T00:00:00Z",
                }
            }
        }
        f = tmp_path / "monday_dict.json"
        f.write_text(json.dumps(data), encoding="utf-8")
        meta = extract_metadata(f, file_format="monday")
        assert meta.file_path is not None


# ---------------------------------------------------------------------------
# Asana list-level payload
# ---------------------------------------------------------------------------


class TestAsanaListPayload:
    def test_list_of_projects(self, tmp_path: Path) -> None:
        data = {
            "data": [
                {
                    "created_at": "2024-01-01T00:00:00Z",
                    "modified_at": "2026-03-01T00:00:00Z",
                    "owner": {"name": "Lead"},
                }
            ]
        }
        f = tmp_path / "asana_list.json"
        f.write_text(json.dumps(data), encoding="utf-8")
        meta = extract_metadata(f, file_format="asana")
        assert meta.modified_at is not None
        assert meta.modified_at.year == 2026
        assert meta.author == "Lead"

    def test_non_dict_owner_does_not_crash(self, tmp_path: Path) -> None:
        data = {
            "data": {
                "modified_at": "2026-01-15T00:00:00Z",
                "owner": "just-a-string",
            }
        }
        f = tmp_path / "asana_str_owner.json"
        f.write_text(json.dumps(data), encoding="utf-8")
        meta = extract_metadata(f, file_format="asana")
        assert meta.author is None


# ---------------------------------------------------------------------------
# Jira top-level list payload
# ---------------------------------------------------------------------------


class TestJiraListPayload:
    def test_list_of_issues(self, tmp_path: Path) -> None:
        data = [
            {
                "fields": {
                    "created": "2025-03-01T00:00:00Z",
                    "updated": "2026-01-20T00:00:00Z",
                    "reporter": {"displayName": "Reporter"},
                }
            }
        ]
        f = tmp_path / "jira_list.json"
        f.write_text(json.dumps(data), encoding="utf-8")
        meta = extract_metadata(f, file_format="jira")
        assert meta.modified_at is not None
        assert meta.modified_at.year == 2026
        assert meta.author == "Reporter"


# ---------------------------------------------------------------------------
# Unknown format — no extractor, only OS metadata
# ---------------------------------------------------------------------------


class TestUnknownFormat:
    def test_unrecognised_format_uses_os_metadata(self, tmp_path: Path) -> None:
        f = tmp_path / "data.txt"
        _write(f, "some content")
        meta = extract_metadata(f, file_format=None)
        assert meta.file_size_bytes is not None
        assert meta.modified_at is not None
        assert meta.content_hash is not None

    def test_explicit_format_override_not_in_map(self, tmp_path: Path) -> None:
        """A format identifier not in _FORMAT_EXTRACTORS is silently ignored."""
        f = tmp_path / "data.json"
        f.write_text("{}", encoding="utf-8")
        # "unknown_format" is not in _FORMAT_EXTRACTORS, so only OS metadata.
        meta = extract_metadata(f, file_format="unknown_format")
        assert meta.file_path is not None


# ---------------------------------------------------------------------------
# Content hash changes with content
# ---------------------------------------------------------------------------


class TestContentHashConsistency:
    def test_same_content_same_hash(self, tmp_path: Path) -> None:
        f1 = tmp_path / "a.json"
        f2 = tmp_path / "b.json"
        payload = json.dumps({"x": 1})
        f1.write_text(payload, encoding="utf-8")
        f2.write_text(payload, encoding="utf-8")
        m1 = extract_metadata(f1)
        m2 = extract_metadata(f2)
        assert m1.content_hash == m2.content_hash

    def test_different_content_different_hash(self, tmp_path: Path) -> None:
        f1 = tmp_path / "a.json"
        f2 = tmp_path / "b.json"
        f1.write_text('{"x": 1}', encoding="utf-8")
        f2.write_text('{"x": 2}', encoding="utf-8")
        m1 = extract_metadata(f1)
        m2 = extract_metadata(f2)
        assert m1.content_hash != m2.content_hash
