"""Benefits router — /api/benefits (P13).

Benefits Realisation Management endpoints.

- GET /api/benefits/{project_id}                — all benefits for a project
- GET /api/benefits/{project_id}/summary        — totals by status and financial type
- GET /api/benefits/{benefit_id}/measurements   — measurement history for a benefit
- GET /api/benefits/{project_id}/network        — dependency nodes and edges
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from ..config import get_store

router = APIRouter(prefix="/api/benefits", tags=["benefits"])


@router.get("/{project_id}")
async def get_benefits(
    project_id: str,
    status: Optional[str] = Query(default=None, description="Filter by status (e.g. PLANNED, REALISING, REALISED)"),
    financial_type: Optional[str] = Query(default=None, description="Filter by financial type (e.g. CASHABLE, NON_CASHABLE)"),
    store=Depends(get_store),
) -> dict:
    """All benefits for a project, optionally filtered by status and/or financial type."""
    records = store.get_benefits(project_id, status_filter=status, financial_type_filter=financial_type)
    return {"project_id": project_id, "count": len(records), "items": records}


@router.get("/{project_id}/summary")
async def get_benefits_summary(
    project_id: str,
    store=Depends(get_store),
) -> dict:
    """Totals by status and financial type, plus aggregate target and realised values."""
    records = store.get_benefits(project_id)

    by_status: dict[str, int] = {}
    by_financial_type: dict[str, int] = {}
    total_target_value = 0.0
    total_realised_value = 0.0

    for row in records:
        status = row.get("status") or "UNKNOWN"
        by_status[status] = by_status.get(status, 0) + 1

        ftype = row.get("financial_type") or "UNKNOWN"
        by_financial_type[ftype] = by_financial_type.get(ftype, 0) + 1

        target = row.get("target_value")
        if target is not None:
            try:
                total_target_value += float(target)
            except (TypeError, ValueError):
                pass

        realised = row.get("realised_value")
        if realised is not None:
            try:
                total_realised_value += float(realised)
            except (TypeError, ValueError):
                pass

    return {
        "project_id": project_id,
        "total": len(records),
        "by_status": by_status,
        "by_financial_type": by_financial_type,
        "total_target_value": round(total_target_value, 2),
        "total_realised_value": round(total_realised_value, 2),
    }


@router.get("/{benefit_id}/measurements")
async def get_benefit_measurements(
    benefit_id: str,
    store=Depends(get_store),
) -> dict:
    """Measurement history for a single benefit, oldest first.

    Returns 404 if the benefit does not exist.
    """
    row = store.get_benefit_by_id(benefit_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Benefit {benefit_id!r} not found")
    measurements = store.get_benefit_measurements(benefit_id)
    return {"benefit_id": benefit_id, "count": len(measurements), "items": measurements}


@router.get("/{project_id}/network")
async def get_benefits_network(
    project_id: str,
    store=Depends(get_store),
) -> dict:
    """Benefit dependency network — nodes and edges — for a project."""
    nodes = store.get_dependency_nodes(project_id)
    edges = store.get_dependency_edges(project_id)
    return {"project_id": project_id, "nodes": nodes, "edges": edges}
