"""Projects router — /api/projects."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..config import get_registry, get_store

router = APIRouter(prefix="/api/projects", tags=["projects"])


@router.get("")
async def list_projects(registry: dict = Depends(get_registry)) -> dict:
    """List all projects with metadata."""
    items = list(registry.values())
    return {"count": len(items), "items": items}


@router.get("/{project_id}")
async def get_project(
    project_id: str,
    registry: dict = Depends(get_registry),
) -> dict:
    """Return metadata for a single project."""
    project = registry.get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project {project_id!r} not found")
    return project


@router.get("/{project_id}/summary")
async def get_project_summary(
    project_id: str,
    registry: dict = Depends(get_registry),
    store=Depends(get_store),
) -> dict:
    """Aggregated summary: latest compliance score, trend, open actions, latest health, domain."""
    project = registry.get(project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project {project_id!r} not found")

    # Latest compliance score
    scores = store.get_confidence_scores(project_id)
    latest_score = scores[-1]["score"] if scores else None
    prev_score = scores[-2]["score"] if len(scores) >= 2 else None
    trend = None
    if latest_score is not None and prev_score is not None:
        diff = latest_score - prev_score
        trend = "IMPROVING" if diff > 1.0 else ("DEGRADING" if diff < -1.0 else "STABLE")

    # Open actions
    open_actions = store.get_recommendations(project_id, status_filter="OPEN")
    recurring_actions = store.get_recommendations(project_id, status_filter="RECURRING")
    open_count = len(open_actions) + len(recurring_actions)

    # Latest workflow health
    workflows = store.get_workflow_history(project_id)
    latest_health = workflows[-1]["health"] if workflows else None

    # Latest domain classification
    classifications = store.get_domain_classifications(project_id)
    latest_domain = classifications[-1]["domain"] if classifications else project.get("domain")

    return {
        "project_id": project_id,
        "name": project.get("name"),
        "department": project.get("department"),
        "latest_score": latest_score,
        "trend": trend,
        "open_actions": open_count,
        "latest_health": latest_health,
        "domain": latest_domain,
    }
