"""Evidence Freshness Detector — usage example.

This script demonstrates how to use the freshness analysis API from
``pm_data_tools.freshness`` to:

1. Analyse a single file and inspect its score and alerts.
2. Analyse an evidence pack (directory) and review pack-level results.
3. Use a gate date to detect "fresh paint" burst-editing patterns.
4. Work directly with ``DocumentMetadata`` for custom pipelines.
5. Export results to JSON for downstream tooling.

Run with::

    python examples/freshness_analysis.py

No external files are required — the example creates temporary fixtures
and cleans them up automatically.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from pm_data_tools.freshness import (
    FreshnessAnalyser,
    FreshnessConfig,
    DocumentMetadata,
    RevisionEntry,
    extract_metadata,
)


def separator(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"  {title}")
    print(f"{'=' * 60}")


# ---------------------------------------------------------------------------
# 1. Analyse a single file
# ---------------------------------------------------------------------------

def example_single_file(directory: Path) -> None:
    separator("1. Single-file freshness analysis")

    # Create a synthetic JSON project file.
    project_file = directory / "project.json"
    project_file.write_text(
        json.dumps({"project_name": "Alpha Programme", "updated_at": "2025-09-01T00:00:00Z"}),
        encoding="utf-8",
    )

    analyser = FreshnessAnalyser()
    result = analyser.analyse_file(project_file)

    print(f"File:             {result.metadata.file_path}")
    print(f"Format detected:  {result.metadata.file_format}")
    print(f"Modified at:      {result.metadata.modified_at}")
    print(f"Freshness score:  {result.freshness_score:.1f} / 100")
    print(f"  Staleness:      {result.staleness_score:.1f}")
    print(f"  Velocity:       {result.velocity_score:.1f}")
    print(f"  Provenance:     {result.provenance_score:.1f}")
    print(f"RAG status:       {result.rag_status.upper()}")
    print(f"Alerts raised:    {len(result.alerts)}")
    for alert in result.alerts:
        print(f"  [{alert.severity.upper()}] {alert.alert_type}: {alert.message}")


# ---------------------------------------------------------------------------
# 2. Analyse an evidence pack
# ---------------------------------------------------------------------------

def example_evidence_pack(directory: Path) -> None:
    separator("2. Evidence pack (directory) analysis")

    pack_dir = directory / "evidence_pack"
    pack_dir.mkdir()

    # Create a variety of files with different ages.
    fresh_file = pack_dir / "schedule.json"
    fresh_file.write_text('{"updated_at": "2026-03-01T00:00:00Z"}', encoding="utf-8")

    stale_file = pack_dir / "risks.json"
    stale_file.write_text('{"updated_at": "2024-06-01T00:00:00Z"}', encoding="utf-8")

    analyser = FreshnessAnalyser(
        config=FreshnessConfig(
            fresh_threshold_days=30,
            stale_threshold_days=90,
        )
    )
    pack = analyser.analyse_pack(pack_dir)

    print(f"Documents analysed:  {len(pack.documents)}")
    print(f"Overall score:       {pack.overall_score:.1f} / 100")
    print(f"Minimum score:       {pack.minimum_score:.1f} / 100")
    print(f"Pack RAG status:     {pack.rag_status.upper()}")
    print(f"Green / Amber / Red: {pack.green_count} / {pack.amber_count} / {pack.red_count}")
    print(f"Total alerts:        {len(pack.all_alerts)}")

    print("\nPer-document breakdown:")
    for doc in sorted(pack.documents, key=lambda d: d.freshness_score):
        name = Path(doc.metadata.file_path).name
        print(f"  {name:<30}  score={doc.freshness_score:.1f}  [{doc.rag_status.upper()}]")


# ---------------------------------------------------------------------------
# 3. Fresh paint detection with a gate date
# ---------------------------------------------------------------------------

def example_fresh_paint_detection(directory: Path) -> None:
    separator("3. Fresh paint detection with gate date")

    now = datetime.now(tz=timezone.utc)
    gate_date = now  # Gate is today.

    # Build synthetic metadata that simulates a document with burst editing
    # in the 7 days before the gate — a classic "fresh paint" pattern.
    burst_revisions = tuple(
        RevisionEntry(
            timestamp=now - timedelta(days=d),
            author="PM",
            summary=f"Last-minute update {d}",
        )
        for d in range(0, 7)  # 7 edits in 7 days.
    )
    # Plus one old edit 90 days ago.
    old_revisions = (
        RevisionEntry(timestamp=now - timedelta(days=90), author="PM", summary="Original draft"),
    )

    meta = DocumentMetadata(
        file_path="/evidence/benefits_realisation.xlsx",
        extracted_at=now,
        file_format="gmpp",
        modified_at=now - timedelta(days=1),
        created_at=now - timedelta(days=365),
        author="Programme Manager",
        last_modified_by="PM",
        version_count=8,
        revision_history=burst_revisions + old_revisions,
    )

    config = FreshnessConfig(
        burst_edit_min_count=5,
        burst_edit_window_days=7,
        gate_date=gate_date,
    )
    analyser = FreshnessAnalyser(config=config)
    result = analyser.score_metadata(meta)

    print(f"Document:         {meta.file_path}")
    print(f"Revision count:   {len(meta.revision_history)}")
    print(f"Burst revisions:  {len(burst_revisions)} edits in the last 7 days")
    print(f"Freshness score:  {result.freshness_score:.1f} / 100")
    print(f"RAG status:       {result.rag_status.upper()}")
    print("\nAlerts:")
    for alert in result.alerts:
        print(f"  [{alert.severity.upper()}] {alert.alert_type}")
        print(f"    {alert.message}")


# ---------------------------------------------------------------------------
# 4. Custom metadata pipeline
# ---------------------------------------------------------------------------

def example_custom_metadata_pipeline() -> None:
    separator("4. Custom metadata pipeline (score_metadata directly)")

    now = datetime.now(tz=timezone.utc)

    # Build metadata from your own data pipeline (e.g. from an API response).
    meta = DocumentMetadata(
        file_path="jira://PROJECT-123",
        extracted_at=now,
        file_format="jira",
        modified_at=now - timedelta(days=45),
        created_at=now - timedelta(days=200),
        author="Product Owner",
        last_modified_by="Scrum Master",
        version_count=None,  # Jira doesn't expose a version count here.
        revision_history=tuple(
            RevisionEntry(
                timestamp=now - timedelta(days=d * 10),
                author="Developer",
                summary=f"Sprint {d} update",
            )
            for d in range(1, 6)
        ),
    )

    analyser = FreshnessAnalyser()
    result = analyser.score_metadata(meta)

    print(f"Source:           {meta.file_path}")
    print(f"Freshness score:  {result.freshness_score:.1f} / 100")
    print(f"RAG status:       {result.rag_status.upper()}")


# ---------------------------------------------------------------------------
# 5. JSON export
# ---------------------------------------------------------------------------

def example_json_export(directory: Path) -> None:
    separator("5. JSON export for downstream tooling")

    f = directory / "export_demo.json"
    f.write_text('{"project_name": "Demo"}', encoding="utf-8")

    result = FreshnessAnalyser().analyse_file(f)
    output = result.to_dict()

    print("Result as JSON (truncated):")
    text = json.dumps(output, indent=2, default=str)
    lines = text.splitlines()
    for line in lines[:20]:
        print(f"  {line}")
    if len(lines) > 20:
        print(f"  ... ({len(lines) - 20} more lines)")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        example_single_file(base)
        example_evidence_pack(base)
        example_fresh_paint_detection(base)
        example_custom_metadata_pipeline()
        example_json_export(base)

    print(f"\n{'=' * 60}")
    print("  All examples complete.")
    print(f"{'=' * 60}\n")
