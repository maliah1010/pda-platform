"""Divergence router — /api/divergence (P4)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..config import get_store

router = APIRouter(prefix="/api/divergence", tags=["divergence"])


@router.get("/{project_id}/history")
async def get_divergence_history(
    project_id: str,
    store=Depends(get_store),
) -> dict:
    """All divergence snapshots for a project, oldest first."""
    records = store.get_divergence_history(project_id)
    return {"project_id": project_id, "count": len(records), "records": records}


@router.get("/{project_id}/latest")
async def get_divergence_latest(
    project_id: str,
    store=Depends(get_store),
) -> dict:
    """Most recent divergence snapshot."""
    records = store.get_divergence_history(project_id)
    if not records:
        raise HTTPException(status_code=404, detail=f"No divergence data for {project_id!r}")
    return {"project_id": project_id, "snapshot": records[-1]}
