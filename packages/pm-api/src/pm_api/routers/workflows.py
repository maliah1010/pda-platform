"""Workflows router — /api/workflows (P9)."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException

from ..config import get_store

router = APIRouter(prefix="/api/workflows", tags=["workflows"])


def _deserialise(record: dict) -> dict:
    """Deserialise result_json field."""
    raw = record.get("result_json")
    record["result"] = json.loads(raw) if isinstance(raw, str) else {}
    return record


@router.get("/{project_id}/history")
async def get_workflow_history(
    project_id: str,
    store=Depends(get_store),
) -> dict:
    """All workflow execution results for a project, oldest first."""
    records = store.get_workflow_history(project_id)
    items = [_deserialise(r) for r in records]
    return {"project_id": project_id, "count": len(items), "items": items}


@router.get("/{project_id}/latest")
async def get_workflow_latest(
    project_id: str,
    store=Depends(get_store),
) -> dict:
    """Most recent workflow execution result."""
    records = store.get_workflow_history(project_id)
    if not records:
        raise HTTPException(status_code=404, detail=f"No workflow data for {project_id!r}")
    latest = _deserialise(records[-1])
    return {"project_id": project_id, "execution": latest}
