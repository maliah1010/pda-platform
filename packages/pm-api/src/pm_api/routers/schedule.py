"""Schedule router — /api/schedule (P5)."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException

from ..config import get_store

router = APIRouter(prefix="/api/schedule", tags=["schedule"])


@router.get("/{project_id}/history")
async def get_schedule_history(
    project_id: str,
    store=Depends(get_store),
) -> dict:
    """All schedule recommendations for a project, oldest first."""
    records = store.get_schedule_history(project_id)
    # Deserialise signals_json
    for r in records:
        raw = r.get("signals_json")
        r["signals"] = json.loads(raw) if isinstance(raw, str) else []
    return {"project_id": project_id, "count": len(records), "records": records}


@router.get("/{project_id}/latest")
async def get_schedule_latest(
    project_id: str,
    store=Depends(get_store),
) -> dict:
    """Most recent schedule recommendation."""
    records = store.get_schedule_history(project_id)
    if not records:
        raise HTTPException(status_code=404, detail=f"No schedule data for {project_id!r}")
    rec = records[-1]
    raw = rec.get("signals_json")
    rec["signals"] = json.loads(raw) if isinstance(raw, str) else []
    return {"project_id": project_id, "recommendation": rec}
