"""Classifier router — /api/classifier (P10)."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException

from ..config import get_store

router = APIRouter(prefix="/api/classifier", tags=["classifier"])

# Domain → assurance profile mapping
_DOMAIN_PROFILES = {
    "CLEAR": {
        "review_cadence": "Quarterly",
        "assurance_intensity": "Standard",
        "escalation_threshold": "Score < 70",
        "recommended_workflow": "COMPLIANCE_FOCUS",
    },
    "COMPLICATED": {
        "review_cadence": "Bi-monthly",
        "assurance_intensity": "Increased",
        "escalation_threshold": "Score < 65",
        "recommended_workflow": "TREND_ANALYSIS",
    },
    "COMPLEX": {
        "review_cadence": "Monthly",
        "assurance_intensity": "High",
        "escalation_threshold": "Score < 60",
        "recommended_workflow": "RISK_ASSESSMENT",
    },
    "CHAOTIC": {
        "review_cadence": "Weekly",
        "assurance_intensity": "Maximum",
        "escalation_threshold": "Immediate escalation",
        "recommended_workflow": "FULL_ASSURANCE",
    },
}


def _deserialise(record: dict) -> dict:
    """Deserialise result_json field."""
    raw = record.get("result_json")
    record["result"] = json.loads(raw) if isinstance(raw, str) else {}
    return record


@router.get("/{project_id}/history")
async def get_classification_history(
    project_id: str,
    store=Depends(get_store),
) -> dict:
    """All domain classifications for a project, oldest first."""
    records = store.get_domain_classifications(project_id)
    items = [_deserialise(r) for r in records]
    return {"project_id": project_id, "count": len(items), "items": items}


@router.get("/{project_id}/latest")
async def get_classification_latest(
    project_id: str,
    store=Depends(get_store),
) -> dict:
    """Most recent domain classification."""
    records = store.get_domain_classifications(project_id)
    if not records:
        raise HTTPException(status_code=404, detail=f"No classification data for {project_id!r}")
    latest = _deserialise(records[-1])
    return {"project_id": project_id, "classification": latest}


@router.get("/{project_id}/profile")
async def get_domain_profile(
    project_id: str,
    store=Depends(get_store),
) -> dict:
    """Domain assurance profile derived from the latest classification."""
    records = store.get_domain_classifications(project_id)
    if not records:
        raise HTTPException(status_code=404, detail=f"No classification data for {project_id!r}")
    latest = records[-1]
    domain = latest["domain"]
    profile = _DOMAIN_PROFILES.get(domain, {})
    return {
        "project_id": project_id,
        "domain": domain,
        "composite_score": latest["composite_score"],
        "classified_at": latest["classified_at"],
        "profile": profile,
    }
