"""Metadata extraction layer for the Evidence Freshness Detector.

Extracts ``DocumentMetadata`` from every supported PM file format, falling back
to OS-level file metadata when format-specific information is unavailable.

Supported formats and their metadata capabilities:

+----------------+--------+--------+----------+--------+---------+
| Format         | author | lm_by  | versions | revs   | created |
+================+========+========+==========+========+=========+
| MS Project XML | yes    | yes    | yes      | no     | yes     |
| Primavera P6   | no     | no     | no       | no     | yes     |
| Jira JSON      | yes    | yes    | yes      | yes    | yes     |
| Monday JSON    | no     | no     | no       | no     | yes     |
| Asana JSON     | yes    | no     | no       | no     | yes     |
| Smartsheet     | no     | no     | no       | no     | yes     |
| GMPP (xlsx)    | yes    | yes    | no       | no     | yes     |
| NISTA JSON     | no     | no     | no       | no     | yes     |
+----------------+--------+--------+----------+--------+---------+

OS-level fallback provides: ``file_size_bytes``, ``created_at``,
``modified_at``, ``accessed_at``, and ``content_hash`` for all formats.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
from xml.etree import ElementTree as ET

from .models import DocumentMetadata, RevisionEntry

logger = logging.getLogger(__name__)

# Namespace used in MS Project MSPDI XML files.
_MSPDI_NS = "http://schemas.microsoft.com/project"


def _sha256(path: Path) -> Optional[str]:
    """Compute SHA-256 hex digest of a file's contents.

    Args:
        path: Path to the file.

    Returns:
        Hex digest string, or ``None`` if the file cannot be read.
    """
    try:
        h = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                h.update(chunk)
        return h.hexdigest()
    except OSError:
        logger.debug("Could not compute hash for %s", path)
        return None


def _os_metadata(path: Path) -> dict:
    """Extract OS-level file metadata.

    Args:
        path: Path to the file.

    Returns:
        Dictionary with keys ``file_size_bytes``, ``created_at``,
        ``modified_at``, and ``accessed_at``.  Values may be ``None`` on
        platforms that do not expose the relevant stat fields.
    """
    try:
        stat = path.stat()
        created: Optional[datetime] = None
        # st_birthtime is available on macOS and Windows; Linux uses st_ctime
        # which is the inode-change time, not creation time.
        if hasattr(stat, "st_birthtime"):
            created = datetime.fromtimestamp(stat.st_birthtime, tz=timezone.utc)
        return {
            "file_size_bytes": stat.st_size,
            "created_at": created,
            "modified_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
            "accessed_at": datetime.fromtimestamp(stat.st_atime, tz=timezone.utc),
        }
    except OSError:
        logger.debug("Could not stat %s", path)
        return {
            "file_size_bytes": None,
            "created_at": None,
            "modified_at": None,
            "accessed_at": None,
        }


def _parse_iso(value: Optional[str]) -> Optional[datetime]:
    """Parse an ISO-8601 string to a timezone-aware ``datetime``.

    Args:
        value: ISO-8601 date/time string, or ``None``.

    Returns:
        Parsed ``datetime`` (UTC if no timezone present), or ``None``.
    """
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, AttributeError):
        return None


# ---------------------------------------------------------------------------
# Format-specific extractors
# ---------------------------------------------------------------------------


def _extract_mspdi(path: Path, base: dict) -> dict:
    """Extract metadata from a Microsoft Project XML (MSPDI) file.

    Reads the ``<Project>`` element's ``Author``, ``LastAuthor``,
    ``CreationDate``, ``LastSaved``, ``Revision``, and ``Name`` properties.

    Args:
        path: Path to the ``.xml`` file.
        base: OS-level metadata dictionary to augment.

    Returns:
        Updated metadata dictionary.
    """
    try:
        tree = ET.parse(str(path))
        root = tree.getroot()
        ns = {"ms": _MSPDI_NS}

        def _text(tag: str) -> Optional[str]:
            el = root.find(f"ms:{tag}", ns)
            return el.text.strip() if el is not None and el.text else None

        author = _text("Author")
        last_author = _text("LastAuthor")
        revision_str = _text("Revision")
        creation_str = _text("CreationDate")
        saved_str = _text("LastSaved")

        version_count: Optional[int] = None
        if revision_str is not None:
            try:
                version_count = int(revision_str)
            except ValueError:
                pass

        if creation_str and not base.get("created_at"):
            base["created_at"] = _parse_iso(creation_str)
        if saved_str:
            base["modified_at"] = _parse_iso(saved_str)

        base["author"] = author
        base["last_modified_by"] = last_author
        base["version_count"] = version_count
    except ET.ParseError:
        logger.debug("Could not parse MSPDI XML from %s", path)
    except OSError:
        logger.debug("Could not read MSPDI file %s", path)
    return base


def _extract_p6(path: Path, base: dict) -> dict:
    """Extract metadata from a Primavera P6 XER or XML file.

    P6 XER exports carry limited metadata. We attempt to read the export
    date from the first ``%E`` (export) record in XER files and project
    dates from ``start_date``/``last_recalc_date`` fields.

    Args:
        path: Path to the ``.xer`` or ``.xml`` file.
        base: OS-level metadata dictionary to augment.

    Returns:
        Updated metadata dictionary.
    """
    suffix = path.suffix.lower()
    if suffix == ".xer":
        try:
            with open(path, encoding="latin-1", errors="replace") as fh:
                for line in fh:
                    line = line.strip()
                    if line.startswith("%E"):
                        # Export date in header: "%E\tYYYY-MM-DD HH:MM"
                        parts = line.split("\t")
                        if len(parts) >= 2:
                            base["created_at"] = _parse_iso(
                                parts[1].replace(" ", "T")
                            )
                        break
        except OSError:
            logger.debug("Could not read P6 XER file %s", path)
    elif suffix == ".xml":
        try:
            tree = ET.parse(str(path))
            root = tree.getroot()
            # P6 XML has varying schemas; try common element names.
            for tag in ("DataDate", "ExportDate", "CreateDate"):
                el = root.find(f".//{tag}")
                if el is not None and el.text:
                    base["created_at"] = _parse_iso(el.text.strip())
                    break
        except ET.ParseError:
            logger.debug("Could not parse P6 XML from %s", path)
        except OSError:
            logger.debug("Could not read P6 XML file %s", path)
    return base


def _extract_jira(path: Path, base: dict) -> dict:
    """Extract metadata from a Jira JSON export file.

    Reads the ``created``, ``updated`` timestamps from the first issue
    found, counts changelog entries for version tracking, and gathers a
    revision history from the changelog.

    Args:
        path: Path to the Jira JSON export.
        base: OS-level metadata dictionary to augment.

    Returns:
        Updated metadata dictionary.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        logger.debug("Could not parse Jira JSON from %s", path)
        return base

    # Jira exports can be a single issue dict or a list / wrapper object.
    issues: list[dict] = []
    if isinstance(data, list):
        issues = data
    elif isinstance(data, dict):
        issues = data.get("issues", [data])

    if not issues:
        return base

    # Use the first issue's timestamps as document-level proxies.
    first = issues[0]
    fields = first.get("fields", {})
    created_str = fields.get("created") or first.get("created")
    updated_str = fields.get("updated") or first.get("updated")

    if created_str and not base.get("created_at"):
        base["created_at"] = _parse_iso(created_str)
    if updated_str:
        base["modified_at"] = _parse_iso(updated_str)

    # Reporter = author-like concept.
    reporter = fields.get("reporter")
    if isinstance(reporter, dict):
        base["author"] = reporter.get("displayName") or reporter.get("name")

    # Aggregate changelog entries across all issues for version count + history.
    all_histories: list[dict] = []
    for issue in issues:
        changelog = issue.get("changelog", {})
        if isinstance(changelog, dict):
            all_histories.extend(changelog.get("histories", []))

    if all_histories:
        base["version_count"] = len(all_histories)
        revisions: list[RevisionEntry] = []
        for entry in all_histories:
            ts = _parse_iso(entry.get("created", ""))
            author_info = entry.get("author", {})
            author_name = (
                author_info.get("displayName") or author_info.get("name")
                if isinstance(author_info, dict)
                else None
            )
            if ts:
                revisions.append(RevisionEntry(timestamp=ts, author=author_name))
        base["revision_history"] = tuple(
            sorted(revisions, key=lambda r: r.timestamp)
        )

    return base


def _extract_monday(path: Path, base: dict) -> dict:
    """Extract metadata from a Monday.com JSON export file.

    Monday exports are typically API responses. We use the ``updated_at``
    field on boards/items as the document's modification time.

    Args:
        path: Path to the Monday.com JSON export.
        base: OS-level metadata dictionary to augment.

    Returns:
        Updated metadata dictionary.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        logger.debug("Could not parse Monday JSON from %s", path)
        return base

    # Monday API responses often nest under "data" → "boards"
    if isinstance(data, dict):
        boards = data.get("data", {}).get("boards", [data])
        if boards:
            board = boards[0] if isinstance(boards, list) else boards
            if isinstance(board, dict):
                updated = board.get("updated_at")
                if updated:
                    base["modified_at"] = _parse_iso(updated)
                created = board.get("created_at")
                if created and not base.get("created_at"):
                    base["created_at"] = _parse_iso(created)
    return base


def _extract_asana(path: Path, base: dict) -> dict:
    """Extract metadata from an Asana JSON export file.

    Args:
        path: Path to the Asana JSON export.
        base: OS-level metadata dictionary to augment.

    Returns:
        Updated metadata dictionary.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        logger.debug("Could not parse Asana JSON from %s", path)
        return base

    # Asana exports nest under "data" which may be a project dict or list.
    project_data = data.get("data", data) if isinstance(data, dict) else data
    if isinstance(project_data, list) and project_data:
        project_data = project_data[0]

    if isinstance(project_data, dict):
        created = project_data.get("created_at")
        modified = project_data.get("modified_at")
        owner = project_data.get("owner", {})

        if created and not base.get("created_at"):
            base["created_at"] = _parse_iso(created)
        if modified:
            base["modified_at"] = _parse_iso(modified)
        if isinstance(owner, dict):
            base["author"] = owner.get("name")
    return base


def _extract_smartsheet(path: Path, base: dict) -> dict:
    """Extract metadata from a Smartsheet JSON export file.

    Args:
        path: Path to the Smartsheet JSON export.
        base: OS-level metadata dictionary to augment.

    Returns:
        Updated metadata dictionary.
    """
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        logger.debug("Could not parse Smartsheet JSON from %s", path)
        return base

    if isinstance(data, dict):
        created = data.get("createdAt")
        modified = data.get("modifiedAt")
        if created and not base.get("created_at"):
            base["created_at"] = _parse_iso(created)
        if modified:
            base["modified_at"] = _parse_iso(modified)
    return base


def _extract_gmpp(path: Path, base: dict) -> dict:
    """Extract metadata from a GMPP spreadsheet (xlsx or csv).

    For xlsx files we attempt to read core document properties via the
    ``zipfile`` module (xlsx is a ZIP archive containing XML parts). For
    csv we rely on OS-level metadata only.

    Args:
        path: Path to the GMPP file.
        base: OS-level metadata dictionary to augment.

    Returns:
        Updated metadata dictionary.
    """
    if path.suffix.lower() != ".xlsx":
        return base

    import zipfile

    try:
        with zipfile.ZipFile(str(path)) as zf:
            # Read core document properties (Dublin Core / OPC).
            if "docProps/core.xml" in zf.namelist():
                with zf.open("docProps/core.xml") as fh:
                    root = ET.parse(fh).getroot()
                ns_cp = "http://schemas.openxmlformats.org/package/2006/metadata/core-properties"
                ns_dc = "http://purl.org/dc/elements/1.1/"
                ns_dcterms = "http://purl.org/dc/terms/"

                def _find(tag: str, ns: str) -> Optional[str]:
                    el = root.find(f"{{{ns}}}{tag}")
                    return el.text.strip() if el is not None and el.text else None

                creator = _find("creator", ns_dc)
                last_mod_by = _find("lastModifiedBy", ns_cp)
                created = _find("created", ns_dcterms)
                modified = _find("modified", ns_dcterms)
                revision = _find("revision", ns_cp)

                base["author"] = creator
                base["last_modified_by"] = last_mod_by
                if created and not base.get("created_at"):
                    base["created_at"] = _parse_iso(created)
                if modified:
                    base["modified_at"] = _parse_iso(modified)
                if revision:
                    try:
                        base["version_count"] = int(revision)
                    except ValueError:
                        pass
    except (zipfile.BadZipFile, KeyError, ET.ParseError, OSError):
        logger.debug("Could not extract GMPP xlsx metadata from %s", path)

    return base


def _extract_nista(path: Path, base: dict) -> dict:
    """Extract metadata from a NISTA JSON file.

    NISTA JSON files may carry a top-level ``metadata`` block or
    project-level ``created``/``updated`` fields; these are used when
    present, with OS-level metadata as fallback.

    Args:
        path: Path to the NISTA JSON file.
        base: OS-level metadata dictionary to augment.

    Returns:
        Updated metadata dictionary.
    """
    if path.suffix.lower() not in (".json", ".csv"):
        return base

    if path.suffix.lower() == ".json":
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError):
            logger.debug("Could not parse NISTA JSON from %s", path)
            return base

        metadata_block = data.get("metadata", {}) if isinstance(data, dict) else {}
        if isinstance(metadata_block, dict):
            created = metadata_block.get("created") or metadata_block.get(
                "created_at"
            )
            modified = metadata_block.get("modified") or metadata_block.get(
                "updated_at"
            )
            if created and not base.get("created_at"):
                base["created_at"] = _parse_iso(created)
            if modified:
                base["modified_at"] = _parse_iso(modified)

        # Also check root-level project timestamps.
        if isinstance(data, dict):
            for key in ("last_updated", "updated_at", "modified_at"):
                if data.get(key):
                    base["modified_at"] = _parse_iso(data[key])
                    break

    return base


# ---------------------------------------------------------------------------
# Format detection helper (mirrors parsers.py logic but lightweight)
# ---------------------------------------------------------------------------

_EXTENSION_FORMAT_MAP: dict[str, str] = {
    ".xml": "mspdi",
    ".mpp": "mspdi",
    ".xer": "p6_xer",
    ".p6xml": "p6_xer",
}

_JSON_FORMAT_HINTS: list[tuple[str, str]] = [
    ("issues", "jira"),
    ("boards", "monday"),
    ("workspaces", "monday"),
    ("tasks", "asana"),
    ("rows", "smartsheet"),
    ("sheets", "smartsheet"),
]


def _detect_format_from_path(path: Path) -> Optional[str]:
    """Heuristically detect the PM file format from the path and content.

    This is a lightweight duplicate of ``parsers.detect_format`` that avoids
    importing heavy dependencies and works on metadata-only paths.

    Args:
        path: Path to the file.

    Returns:
        Format identifier string, or ``None``.
    """
    suffix = path.suffix.lower()
    name_lower = path.name.lower()

    if suffix in _EXTENSION_FORMAT_MAP:
        return _EXTENSION_FORMAT_MAP[suffix]

    if suffix in (".xlsx", ".xls", ".csv"):
        # GMPP files often carry "gmpp" or "portfolio" in their name.
        if any(kw in name_lower for kw in ("gmpp", "portfolio", "report")):
            return "gmpp"
        return "gmpp"  # Default spreadsheet assumption for PM context.

    if suffix == ".json":
        # Peek at the JSON keys to distinguish Jira / Monday / Asana / etc.
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            top_keys = set(data.keys()) if isinstance(data, dict) else set()
            for hint_key, fmt in _JSON_FORMAT_HINTS:
                if hint_key in top_keys:
                    return fmt
            # Check nested "data" wrapper (Monday, Asana API responses).
            if "data" in top_keys:
                nested = data["data"]
                if isinstance(nested, dict):
                    for hint_key, fmt in _JSON_FORMAT_HINTS:
                        if hint_key in nested:
                            return fmt
        except (OSError, json.JSONDecodeError, ValueError):
            pass
        return "nista"  # Default JSON assumption for PM context.

    return None


# Mapping from format identifier to extractor function.
_FORMAT_EXTRACTORS = {
    "mspdi": _extract_mspdi,
    "p6_xer": _extract_p6,
    "jira": _extract_jira,
    "monday": _extract_monday,
    "asana": _extract_asana,
    "smartsheet": _extract_smartsheet,
    "gmpp": _extract_gmpp,
    "nista": _extract_nista,
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def extract_metadata(
    file_path: str | Path,
    file_format: Optional[str] = None,
) -> DocumentMetadata:
    """Extract ``DocumentMetadata`` from a project management file.

    Combines OS-level file metadata with format-specific provenance
    information.  If ``file_format`` is not provided, it is auto-detected.

    Args:
        file_path: Path to the file to analyse.
        file_format: Optional format override (e.g. ``"jira"``).  When
            ``None``, format detection is attempted automatically.

    Returns:
        Populated ``DocumentMetadata`` instance.  Fields that cannot be
        determined are set to ``None`` rather than raising an exception.

    Example:
        >>> metadata = extract_metadata("schedule.xml")
        >>> print(metadata.modified_at)
        2026-01-15 10:30:00+00:00
    """
    path = Path(file_path)
    extracted_at = datetime.now(tz=timezone.utc)

    base: dict = _os_metadata(path)
    base["content_hash"] = _sha256(path)

    detected_format = file_format or _detect_format_from_path(path)

    if detected_format and detected_format in _FORMAT_EXTRACTORS:
        try:
            base = _FORMAT_EXTRACTORS[detected_format](path, base)
        except Exception:
            logger.debug(
                "Format-specific extraction failed for %s (%s)",
                path,
                detected_format,
                exc_info=True,
            )

    # Normalise revision_history to a tuple (extractors may leave it as list).
    revision_history = base.pop("revision_history", ())
    if isinstance(revision_history, list):
        revision_history = tuple(revision_history)

    return DocumentMetadata(
        file_path=str(path),
        file_format=detected_format,
        file_size_bytes=base.get("file_size_bytes"),
        created_at=base.get("created_at"),
        modified_at=base.get("modified_at"),
        accessed_at=base.get("accessed_at"),
        author=base.get("author"),
        last_modified_by=base.get("last_modified_by"),
        version_count=base.get("version_count"),
        revision_history=revision_history,
        content_hash=base.get("content_hash"),
        extracted_at=extracted_at,
    )
