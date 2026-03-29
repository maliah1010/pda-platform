"""Overrides router — /api/overrides (P6)."""

from __future__ import annotations

import json
from collections import Counter

from fastapi import APIRouter, Depends

from ..config import get_store

router = APIRouter(prefix="/api/overrides", tags=["overrides"])


def _deserialise(record: dict) -> dict:
    """Deserialise JSON string fields in an override decision record."""
    for field in ("conditions_json", "evidence_refs_json"):
        raw = record.get(field)
        if isinstance(raw, str):
            record[field.replace("_json", "")] = json.loads(raw)
    return record


@router.get("/{project_id}")
async def get_overrides(
    project_id: str,
    store=Depends(get_store),
) -> dict:
    """All override decisions for a project."""
    records = store.get_override_decisions(project_id)
    items = [_deserialise(r) for r in records]
    return {"project_id": project_id, "count": len(items), "items": items}


@router.get("/{project_id}/patterns")
async def get_override_patterns(
    project_id: str,
    store=Depends(get_store),
) -> dict:
    """Pattern analysis: counts by type and outcome."""
    records = store.get_override_decisions(project_id)
    by_type: Counter = Counter(r["override_type"] for r in records)
    by_outcome: Counter = Counter(r["outcome"] for r in records)
    pending = sum(1 for r in records if r["outcome"] == "PENDING")

    return {
        "project_id": project_id,
        "total": len(records),
        "pending": pending,
        "by_type": dict(by_type),
        "by_outcome": dict(by_outcome),
    }
