"""Assumptions router — /api/assumptions (P11)."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException

from ..config import get_store

router = APIRouter(prefix="/api/assumptions", tags=["assumptions"])


def _get_tracker(store):
    """Return an AssumptionTracker backed by the singleton store."""
    from pm_data_tools.assurance.assumptions import AssumptionTracker  # noqa: PLC0415

    return AssumptionTracker(store=store)


def _serialise_assumption(a) -> dict:
    return {
        "id": a.id,
        "project_id": a.project_id,
        "text": a.text,
        "category": a.category.value,
        "baseline_value": a.baseline_value,
        "current_value": a.current_value,
        "unit": a.unit,
        "tolerance_pct": a.tolerance_pct,
        "source": a.source.value,
        "external_ref": a.external_ref,
        "dependencies": a.dependencies,
        "owner": a.owner,
        "last_validated": a.last_validated.isoformat() if a.last_validated else None,
        "created_date": a.created_date.isoformat(),
        "notes": a.notes,
    }


def _serialise_drift_result(dr) -> dict:
    return {
        "assumption": _serialise_assumption(dr.assumption),
        "drift_pct": dr.drift_pct,
        "severity": dr.severity.value,
        "days_since_validation": dr.days_since_validation,
        "cascade_impact": dr.cascade_impact,
        "message": dr.message,
    }


@router.get("/{project_id}")
async def get_assumptions(
    project_id: str,
    store=Depends(get_store),
) -> dict:
    """All assumptions for a project."""
    tracker = _get_tracker(store)
    assumptions = tracker.get_assumptions(project_id)
    return {
        "project_id": project_id,
        "count": len(assumptions),
        "items": [_serialise_assumption(a) for a in assumptions],
    }


@router.get("/{project_id}/health")
async def get_assumption_health(
    project_id: str,
    store=Depends(get_store),
) -> dict:
    """Full assumption health report for a project."""
    tracker = _get_tracker(store)
    report = tracker.analyse_project(project_id)
    return {
        "project_id": report.project_id,
        "timestamp": report.timestamp.isoformat(),
        "total_assumptions": report.total_assumptions,
        "validated_count": report.validated_count,
        "stale_count": report.stale_count,
        "overall_drift_score": report.overall_drift_score,
        "by_severity": report.by_severity,
        "by_category": report.by_category,
        "cascade_warnings": report.cascade_warnings,
        "message": report.message,
        "drift_results": [_serialise_drift_result(dr) for dr in report.drift_results],
    }


@router.get("/{project_id}/stale")
async def get_stale_assumptions(
    project_id: str,
    store=Depends(get_store),
) -> dict:
    """Stale assumptions only — not validated within the staleness window."""
    tracker = _get_tracker(store)
    stale = tracker.get_stale_assumptions(project_id)
    return {
        "project_id": project_id,
        "count": len(stale),
        "items": [_serialise_assumption(a) for a in stale],
    }


@router.get("/{assumption_id}/history")
async def get_validation_history(
    assumption_id: str,
    store=Depends(get_store),
) -> dict:
    """Validation history for a single assumption, oldest first."""
    tracker = _get_tracker(store)
    history = tracker.get_validation_history(assumption_id)
    if not history:
        # Check if the assumption exists at all
        row = store.get_assumption_by_id(assumption_id)
        if row is None:
            raise HTTPException(status_code=404, detail=f"Assumption {assumption_id!r} not found")
    items = [
        {
            "id": v.id,
            "assumption_id": v.assumption_id,
            "validated_at": v.validated_at.isoformat(),
            "previous_value": v.previous_value,
            "new_value": v.new_value,
            "source": v.source.value,
            "drift_pct": v.drift_pct,
            "severity": v.severity.value,
            "notes": v.notes,
        }
        for v in history
    ]
    return {"assumption_id": assumption_id, "count": len(items), "items": items}


@router.get("/{assumption_id}/cascade")
async def get_cascade_impact(
    assumption_id: str,
    store=Depends(get_store),
) -> dict:
    """Cascade impact analysis — assumptions affected if this one drifts."""
    row = store.get_assumption_by_id(assumption_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"Assumption {assumption_id!r} not found")

    tracker = _get_tracker(store)
    impacted_ids = tracker.get_cascade_impact(assumption_id)

    items = []
    for aid in impacted_ids:
        dep_row = store.get_assumption_by_id(aid)
        if dep_row is not None:
            from pm_data_tools.assurance.assumptions import _row_to_assumption  # noqa: PLC0415

            a = _row_to_assumption(dep_row)
            dr = tracker.compute_drift(a)
            items.append({
                "assumption_id": aid,
                "text": a.text,
                "category": a.category.value,
                "drift_pct": dr.drift_pct,
                "severity": dr.severity.value,
            })

    return {
        "source_assumption_id": assumption_id,
        "impacted_count": len(items),
        "impacted_assumptions": items,
    }
