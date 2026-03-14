"""Freshness subcommand for the PM Data Tools CLI.

Analyses evidence freshness of a single file or an entire evidence pack
(directory) and reports scores, RAG statuses, and alerts.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import click


@click.command("freshness")
@click.argument("path", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--format",
    "file_format",
    type=click.Choice(
        [
            "mspdi",
            "p6_xer",
            "nista",
            "jira",
            "monday",
            "asana",
            "smartsheet",
            "gmpp",
        ],
        case_sensitive=False,
    ),
    default=None,
    help="Force a specific file format (auto-detected by default).",
)
@click.option(
    "--gate-date",
    type=click.DateTime(formats=["%Y-%m-%d", "%Y-%m-%dT%H:%M:%S"]),
    default=None,
    help=(
        "Gate/review date for fresh-paint detection (YYYY-MM-DD). "
        "When set, burst editing before this date is flagged."
    ),
)
@click.option(
    "--fresh-days",
    type=int,
    default=30,
    show_default=True,
    help="Days within which a document is considered fresh (green).",
)
@click.option(
    "--stale-days",
    type=int,
    default=90,
    show_default=True,
    help="Days beyond which a document is considered stale (red).",
)
@click.option(
    "--recursive",
    "-r",
    is_flag=True,
    default=False,
    help="Scan directories recursively (ignored when PATH is a file).",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    default=None,
    help="Write results to a JSON file instead of stdout.",
)
@click.option(
    "--json",
    "output_json",
    is_flag=True,
    default=False,
    help="Output results as JSON (implies machine-readable format).",
)
def freshness_cmd(
    path: Path,
    file_format: Optional[str],
    gate_date: Optional[datetime],
    fresh_days: int,
    stale_days: int,
    recursive: bool,
    output: Optional[Path],
    output_json: bool,
) -> None:
    """Analyse evidence freshness of a file or evidence pack.

    PATH may be a single project file or a directory of project files (an
    evidence pack).  When a directory is given, all recognised PM files
    are analysed and a pack-level summary is produced.

    \b
    Examples:
        pm-data-tools freshness schedule.xml
        pm-data-tools freshness /evidence/ --recursive --gate-date 2026-04-01
        pm-data-tools freshness project.json --json -o report.json
    """
    from pm_data_tools.freshness import FreshnessAnalyser, FreshnessConfig

    config = FreshnessConfig(
        fresh_threshold_days=fresh_days,
        stale_threshold_days=stale_days,
        gate_date=gate_date,
    )
    analyser = FreshnessAnalyser(config=config)

    if path.is_dir():
        result = analyser.analyse_pack(path, recursive=recursive, file_format=file_format)
        _output_pack(result, output, output_json)
    else:
        result = analyser.analyse_file(path, file_format=file_format)
        _output_document(result, output, output_json)


def _rag_colour(rag: str) -> str:
    """Return an ANSI-coloured RAG label for terminal output.

    Args:
        rag: One of ``"green"``, ``"amber"``, or ``"red"``.

    Returns:
        Click-styled string.
    """
    colours = {"green": "green", "amber": "yellow", "red": "red"}
    return click.style(rag.upper(), fg=colours.get(rag, "white"), bold=True)


def _output_document(result, output: Optional[Path], as_json: bool) -> None:
    """Render a single-document freshness result.

    Args:
        result: ``DocumentFreshnessResult`` instance.
        output: Optional file path for JSON output.
        as_json: When ``True``, format output as JSON.
    """
    if as_json or output:
        data = result.to_dict()
        text = json.dumps(data, indent=2, default=str)
        if output:
            output.write_text(text, encoding="utf-8")
            click.echo(f"Results written to {output}")
        else:
            click.echo(text)
        return

    # Human-readable output.
    click.echo(f"\nFile:              {result.metadata.file_path}")
    click.echo(f"Format:            {result.metadata.file_format or 'unknown'}")
    click.echo(f"Modified:          {result.metadata.modified_at or 'unknown'}")
    click.echo(f"Author:            {result.metadata.author or '—'}")
    click.echo(f"Last modified by:  {result.metadata.last_modified_by or '—'}")
    click.echo(f"Version count:     {result.metadata.version_count or '—'}")
    click.echo()
    click.echo(f"Freshness score:   {result.freshness_score:.1f} / 100")
    click.echo(f"  Staleness:       {result.staleness_score:.1f}")
    click.echo(f"  Velocity:        {result.velocity_score:.1f}")
    click.echo(f"  Provenance:      {result.provenance_score:.1f}")
    click.echo(f"RAG status:        {_rag_colour(result.rag_status)}")

    if result.alerts:
        click.echo(f"\nAlerts ({len(result.alerts)}):")
        for alert in result.alerts:
            click.echo(f"  [{alert.severity.upper()}] {alert.alert_type}: {alert.message}")
    else:
        click.echo("\nNo alerts raised.")

    sys.exit(0 if result.rag_status == "green" else 1)


def _output_pack(result, output: Optional[Path], as_json: bool) -> None:
    """Render a pack-level freshness result.

    Args:
        result: ``PackFreshnessResult`` instance.
        output: Optional file path for JSON output.
        as_json: When ``True``, format output as JSON.
    """
    if as_json or output:
        data = result.to_dict()
        text = json.dumps(data, indent=2, default=str)
        if output:
            output.write_text(text, encoding="utf-8")
            click.echo(f"Results written to {output}")
        else:
            click.echo(text)
        return

    # Human-readable output.
    click.echo(f"\nEvidence Pack Summary")
    click.echo(f"{'=' * 40}")
    click.echo(f"Documents analysed: {len(result.documents)}")
    click.echo(f"Overall score:      {result.overall_score:.1f} / 100")
    click.echo(f"Minimum score:      {result.minimum_score:.1f} / 100")
    click.echo(f"Pack RAG status:    {_rag_colour(result.rag_status)}")
    click.echo()
    click.echo(f"Green documents:    {result.green_count}")
    click.echo(f"Amber documents:    {result.amber_count}")
    click.echo(f"Red documents:      {result.red_count}")
    click.echo(f"Total alerts:       {len(result.all_alerts)}")

    if result.documents:
        click.echo(f"\nPer-document breakdown:")
        for doc in sorted(result.documents, key=lambda d: d.freshness_score):
            rag = _rag_colour(doc.rag_status)
            name = Path(doc.metadata.file_path).name
            click.echo(
                f"  {name:<40} {doc.freshness_score:5.1f}  {rag}"
            )

    if result.all_alerts:
        click.echo(f"\nAll alerts:")
        for alert in result.all_alerts:
            doc_name = Path(alert.document_id).name
            click.echo(
                f"  [{alert.severity.upper()}] {doc_name}: "
                f"{alert.alert_type} — {alert.message}"
            )

    sys.exit(0 if result.rag_status == "green" else 1)
