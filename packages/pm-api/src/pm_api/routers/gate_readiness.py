"""Gate Readiness router — /api/gate-readiness (P14).

Gate Readiness Assessment endpoints.

- GET /api/gate-readiness/{project_id}            — all assessments for a project
- GET /api/gate-readiness/{project_id}/latest     — most recent assessment
- GET /api/gate-readiness/{assessment_id}/detail  — single assessment by ID
"""

from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from ..config import get_store

router = APIRouter(prefix="/api/gate-readiness", tags=["gate-readiness"])


def _expand_result_json(row: dict) -> dict:
    """Return a copy of *row* with ``result_json`` parsed into ``result``."""
    out = dict(row)
    raw = out.pop("result_json", None)
    if raw:
        try:
            out["result"] = json.loads(raw)
        except (TypeError, ValueError):
            out["result"] = None
    else:
        out["result"] = None
    return out


@router.get("/{project_id}")
async def get_gate_readiness(
    project_id: str,
    gate: Optional[str] = Query(default=None, description="Filter by gate identifier (e.g. GATE_2)"),
    store=Depends(get_store),
) -> dict:
    """All gate readiness assessments for a project, optionally filtered by gate.

    The ``result_json`` field is parsed and returned as ``result``.
    """
    rows = store.get_gate_readiness_history(project_id, gate=gate)
    items = [_expand_result_json(r) for r in rows]
    return {"project_id": project_id, "count": len(items), "items": items}


@router.get("/{project_id}/latest")
async def get_gate_readiness_latest(
    project_id: str,
    store=Depends(get_store),
) -> dict:
    """Most recent gate readiness assessment for a project.

    Returns 404 if no assessments exist.  The ``result_json`` field is parsed
    and returned as ``result``.
    """
    rows = store.get_gate_readiness_history(project_id)
    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"No gate readiness assessments found for project {project_id!r}",
        )
    return _expand_result_json(rows[-1])


@router.get("/{assessment_id}/detail")
async def get_gate_readiness_detail(
    assessment_id: str,
    store=Depends(get_store),
) -> dict:
    """Single gate readiness assessment by ID.

    Returns 404 if the assessment does not exist.  The ``result_json`` field is
    parsed and returned as ``result``.
    """
    row = store.get_gate_readiness_assessment_by_id(assessment_id)
    if row is None:
        raise HTTPException(
            status_code=404,
            detail=f"Gate readiness assessment {assessment_id!r} not found",
        )
    return _expand_result_json(row)
