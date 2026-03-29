"""Compliance router — /api/compliance (P2)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..config import get_store

router = APIRouter(prefix="/api/compliance", tags=["compliance"])


@router.get("/{project_id}/history")
async def get_compliance_history(
    project_id: str,
    store=Depends(get_store),
) -> dict:
    """All compliance score records for a project, oldest first."""
    records = store.get_confidence_scores(project_id)
    return {"project_id": project_id, "count": len(records), "records": records}


@router.get("/{project_id}/trend")
async def get_compliance_trend(
    project_id: str,
    store=Depends(get_store),
) -> dict:
    """Current trend direction and breach status."""
    records = store.get_confidence_scores(project_id)
    if not records:
        raise HTTPException(status_code=404, detail=f"No compliance data for {project_id!r}")

    latest = records[-1]
    prev = records[-2] if len(records) >= 2 else None

    trend = "STABLE"
    if prev:
        diff = latest["score"] - prev["score"]  # type: ignore[operator]
        if diff > 2.0:
            trend = "IMPROVING"
        elif diff < -2.0:
            trend = "DEGRADING"

    # Simple breach detection: score below 60 is a breach
    active_breaches = [
        r for r in records if isinstance(r["score"], (int, float)) and r["score"] < 60.0
    ]

    return {
        "project_id": project_id,
        "latest_score": latest["score"],
        "latest_timestamp": latest["timestamp"],
        "trend": trend,
        "active_breaches": len(active_breaches),
        "breach_threshold": 60.0,
    }
