"""Actions router — /api/actions (P3)."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Query

from ..config import get_store

router = APIRouter(prefix="/api/actions", tags=["actions"])


@router.get("/{project_id}")
async def get_actions(
    project_id: str,
    status: Optional[str] = Query(default=None, description="Filter by status (e.g. OPEN, CLOSED, RECURRING)"),
    store=Depends(get_store),
) -> dict:
    """All review actions for a project, optionally filtered by status."""
    records = store.get_recommendations(project_id, status_filter=status)
    return {"project_id": project_id, "count": len(records), "items": records}


@router.get("/{project_id}/summary")
async def get_actions_summary(
    project_id: str,
    store=Depends(get_store),
) -> dict:
    """Counts: total, open, closed, recurring, closure_rate."""
    all_actions = store.get_recommendations(project_id)
    open_actions = [r for r in all_actions if r["status"] == "OPEN"]
    closed_actions = [r for r in all_actions if r["status"] == "CLOSED"]
    recurring_actions = [r for r in all_actions if r["status"] == "RECURRING"]

    total = len(all_actions)
    closure_rate = round(len(closed_actions) / total, 3) if total else 0.0

    return {
        "project_id": project_id,
        "total": total,
        "open": len(open_actions),
        "closed": len(closed_actions),
        "recurring": len(recurring_actions),
        "closure_rate": closure_rate,
    }
