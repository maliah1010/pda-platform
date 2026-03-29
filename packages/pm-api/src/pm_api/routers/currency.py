"""Currency router — /api/currency (P1)."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from ..config import get_artefacts, get_store

router = APIRouter(prefix="/api/currency", tags=["currency"])

_GATE_DATE = datetime(2026, 6, 30, tzinfo=timezone.utc)


def _get_validator():
    """Lazy-import ArtefactCurrencyValidator to avoid import-time side effects."""
    _pkg_src = Path(__file__).resolve().parents[4] / "pm-data-tools" / "src"
    if str(_pkg_src) not in sys.path:
        sys.path.insert(0, str(_pkg_src))
    from pm_data_tools.assurance.currency import ArtefactCurrencyValidator  # noqa: PLC0415

    return ArtefactCurrencyValidator()


@router.get("/{project_id}")
async def get_currency(
    project_id: str,
    artefacts: dict = Depends(get_artefacts),
    store=Depends(get_store),  # noqa: ARG001 — keeps store warm
) -> dict:
    """Run P1 artefact currency check using demo_artefacts.json with gate_date=2026-06-30."""
    project_artefacts = artefacts.get(project_id)
    if project_artefacts is None:
        raise HTTPException(status_code=404, detail=f"No artefacts for {project_id!r}")

    validator = _get_validator()

    # Build list of dicts with datetime objects for check_batch
    artefact_list = []
    for a in project_artefacts:
        raw_date = a.get("last_modified", "")
        try:
            last_modified = datetime.fromisoformat(raw_date).replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            last_modified = datetime(2020, 1, 1, tzinfo=timezone.utc)
        artefact_list.append(
            {
                "id": a.get("id", ""),
                "type": a.get("type", ""),
                "last_modified": last_modified,
            }
        )

    results = validator.check_batch(artefacts=artefact_list, gate_date=_GATE_DATE)

    # Serialise CurrencyScore objects to dicts
    serialised = []
    for r in results:
        if hasattr(r, "model_dump"):
            item = r.model_dump()
        else:
            item = {
                "artefact_id": getattr(r, "artefact_id", None),
                "artefact_type": getattr(r, "artefact_type", None),
                "status": getattr(r, "status", None),
                "days_since_update": getattr(r, "days_since_update", None),
                "days_to_gate": getattr(r, "days_to_gate", None),
                "is_current": getattr(r, "is_current", None),
            }
        # Ensure enum values are strings
        for k, v in item.items():
            if hasattr(v, "value"):
                item[k] = v.value
        serialised.append(item)

    stale_count = sum(1 for r in serialised if r.get("status") == "OUTDATED")
    anomalous_count = sum(1 for r in serialised if r.get("status") == "ANOMALOUS_UPDATE")

    return {
        "project_id": project_id,
        "gate_date": _GATE_DATE.date().isoformat(),
        "artefact_count": len(serialised),
        "stale_count": stale_count,
        "anomalous_count": anomalous_count,
        "results": serialised,
    }
