"""Projects router — /api/projects."""

from __future__ import annotations

import json
import uuid
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..config import _resolve, get_registry, get_store, settings

router = APIRouter(prefix="/api/projects", tags=["projects"])


# ---------------------------------------------------------------------------
# Request model for project creation
# ---------------------------------------------------------------------------


class ProjectCreateRequest(BaseModel):
    """Profile produced by the Claude analysis step in the hackathon tool."""

    project_id: Optional[str] = None
    name: str
    department: str
    category: str = "ICT"
    sro: str = "Programme Director"
    start_date: str = Field(default_factory=lambda: date.today().isoformat())
    end_date: str = Field(
        default_factory=lambda: date.today().replace(year=date.today().year + 2).isoformat()
    )
    whole_life_cost_m: float = 10.0
    domain: str = "COMPLICATED"
    # P10 classifier inputs (0.0–1.0 scale)
    technical_complexity: float = 0.5
    stakeholder_complexity: float = 0.5
    requirement_clarity: float = 0.5
    delivery_track_record: float = 0.5
    organisational_change: float = 0.5
    regulatory_exposure: float = 0.5
    dependency_count: float = 0.5
    # Supplementary fields (stored in registry, displayed in dashboard header)
    summary: str = ""
    key_risks: list[str] = []


@router.post("", status_code=201)
async def create_project(
    payload: ProjectCreateRequest,
    registry: dict = Depends(get_registry),
    store=Depends(get_store),
) -> dict:
    """Create a new project, generate P1–P12 synthetic assurance data, and return project_id.

    This endpoint is used by the hackathon PDF-drop tool to onboard a new
    project profile produced by Claude.  The project is added to the
    in-memory registry and persisted to ``demo_registry.json`` so that all
    other GET endpoints can serve data for it immediately.
    """
    import sys
    from pathlib import Path

    # Ensure pm_data_tools is on the path (mirrors config.py pattern)
    _pkg_src = Path(__file__).resolve().parents[4] / "pm-data-tools" / "src"
    if str(_pkg_src) not in sys.path:
        sys.path.insert(0, str(_pkg_src))

    from pm_data_tools.assurance.classifier import ClassificationInput
    from pm_data_tools.assurance.generator import generate_single_project

    # Assign project_id if caller didn't supply one
    if not payload.project_id:
        short = str(uuid.uuid4())[:8].upper()
        payload.project_id = f"HACKATHON-{short}"

    project_id = payload.project_id

    if project_id in registry:
        raise HTTPException(status_code=409, detail=f"Project {project_id!r} already exists")

    # Build registry entry (mirrors demo_registry.json structure)
    entry: dict = {
        "name": payload.name,
        "department": payload.department,
        "category": payload.category,
        "sro": payload.sro,
        "start_date": payload.start_date,
        "end_date": payload.end_date,
        "whole_life_cost_m": payload.whole_life_cost_m,
        "domain": payload.domain,
        "summary": payload.summary,
        "key_risks": payload.key_risks,
    }

    # Add to in-memory registry immediately so GET endpoints respond during generation
    registry[project_id] = entry

    # Persist registry to JSON (best-effort — ephemeral on Railway, fine for hackathon)
    try:
        registry_path = _resolve(settings.registry_path)
        with open(registry_path, "w", encoding="utf-8") as fh:
            json.dump(registry, fh, indent=2)
    except OSError:
        pass  # Container might be read-only; in-memory registry is sufficient

    # Build P10 classifier input from Claude's complexity scores
    classifier_input = ClassificationInput(
        project_id=project_id,
        technical_complexity=payload.technical_complexity,
        stakeholder_complexity=payload.stakeholder_complexity,
        requirement_clarity=payload.requirement_clarity,
        delivery_track_record=payload.delivery_track_record,
        organisational_change=payload.organisational_change,
        regulatory_exposure=payload.regulatory_exposure,
        dependency_count=payload.dependency_count,
    )

    # Run full P1–P12 generation synchronously
    # (typically 2–8 s; within Netlify's 10 s function timeout for most domains)
    generate_single_project(
        store=store,
        project_id=project_id,
        domain=payload.domain,
        meta={"name": payload.name, "sro": payload.sro, "domain": payload.domain},
        classifier_input=classifier_input,
    )

    return {
        "project_id": project_id,
        "status": "created",
        "domain": payload.domain,
        "name": payload.name,
    }


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
