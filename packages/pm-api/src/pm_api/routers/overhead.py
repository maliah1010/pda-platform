"""Overhead router — /api/overhead (P8)."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException

from ..config import get_store

router = APIRouter(prefix="/api/overhead", tags=["overhead"])


def _deserialise_activity(record: dict) -> dict:
    """Deserialise artefacts_reviewed JSON string."""
    raw = record.get("artefacts_reviewed")
    record["artefacts_reviewed"] = json.loads(raw) if isinstance(raw, str) else []
    return record


@router.get("/{project_id}/activities")
async def get_activities(
    project_id: str,
    store=Depends(get_store),
) -> dict:
    """All assurance activities for a project."""
    records = store.get_assurance_activities(project_id)
    items = [_deserialise_activity(r) for r in records]
    return {"project_id": project_id, "count": len(items), "items": items}


@router.get("/{project_id}/analysis")
async def get_overhead_analysis(
    project_id: str,
    store=Depends(get_store),
) -> dict:
    """Latest overhead analysis for a project."""
    history = store.get_overhead_history(project_id)
    if not history:
        raise HTTPException(status_code=404, detail=f"No overhead analysis for {project_id!r}")
    latest = history[-1]
    raw = latest.get("analysis_json")
    latest["analysis"] = json.loads(raw) if isinstance(raw, str) else {}
    return {"project_id": project_id, "analysis": latest}
