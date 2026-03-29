"""ARMM router — /api/armm (P12).

Agent Readiness Maturity Model endpoints.

- GET /api/armm/portfolio              — overview for all projects
- GET /api/armm/{project_id}           — latest report (overall + dimension + topic)
- GET /api/armm/{project_id}/history   — all assessments, oldest first
- GET /api/armm/{project_id}/criteria  — criterion-level results (drill-through)
- GET /api/armm/{project_id}/dimensions — per-dimension breakdown with topics
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..config import get_store

router = APIRouter(prefix="/api/armm", tags=["armm"])


def _get_scorer(store):
    from pm_data_tools.assurance.armm import ARMMScorer  # noqa: PLC0415

    return ARMMScorer(store=store)


def _serialise_report(report) -> dict:
    from pm_data_tools.assurance.armm import (  # noqa: PLC0415
        DIMENSION_LABELS,
        MATURITY_DESCRIPTIONS,
        MATURITY_LABELS,
        ARMMDimension,
        MaturityLevel,
    )

    dimension_detail = {}
    for dim_code, level_int in report.dimension_levels.items():
        ml = MaturityLevel(level_int)
        dim = ARMMDimension(dim_code)
        dimension_detail[dim_code] = {
            "label": DIMENSION_LABELS.get(dim, dim_code),
            "level": level_int,
            "level_label": MATURITY_LABELS.get(ml, str(level_int)),
            "score_pct": report.dimension_scores.get(dim_code, 0.0),
            "blocking_topic": report.dimension_blocking_topics.get(dim_code),
        }

    overall_ml = report.overall_level
    return {
        "project_id": report.project_id,
        "latest_assessment_id": report.latest_assessment_id,
        "assessed_at": report.assessed_at,
        "overall_level": int(overall_ml),
        "overall_level_label": MATURITY_LABELS.get(overall_ml, str(int(overall_ml))),
        "overall_level_description": MATURITY_DESCRIPTIONS.get(overall_ml, ""),
        "overall_score_pct": report.overall_score_pct,
        "criteria_total": report.criteria_total,
        "criteria_met": report.criteria_met,
        "dimensions": dimension_detail,
        "topic_levels": report.topic_levels,
        "topic_scores": report.topic_scores,
        "blocking_dimension": report.blocking_dimension,
        "history_count": report.history_count,
        "maturity_trend": report.maturity_trend,
    }


def _serialise_assessment_row(row: dict) -> dict:
    import json

    return {
        "id": row["id"],
        "project_id": row["project_id"],
        "assessed_at": row["assessed_at"],
        "assessed_by": row["assessed_by"],
        "overall_level": row["overall_level"],
        "overall_score_pct": row["overall_score_pct"],
        "criteria_total": row["criteria_total"],
        "criteria_met": row["criteria_met"],
        "dimension_levels": json.loads(row["dimension_levels_json"]),
        "dimension_scores": json.loads(row["dimension_scores_json"]),
        "topic_levels": json.loads(row["topic_levels_json"]),
        "notes": row.get("notes") or "",
    }


@router.get("/portfolio")
async def get_portfolio_overview(
    store=Depends(get_store),
) -> dict:
    """ARMM maturity overview for all projects with assessment data."""
    scorer = _get_scorer(store)
    reports = scorer.get_portfolio_overview()
    items = [_serialise_report(r) for r in reports]
    levels = [r["overall_level"] for r in items]
    avg_score = round(sum(r["overall_score_pct"] for r in items) / len(items), 2) if items else 0.0
    return {
        "count": len(items),
        "average_score_pct": avg_score,
        "level_distribution": {str(i): levels.count(i) for i in range(5)},
        "items": items,
    }


@router.get("/{project_id}")
async def get_armm_report(
    project_id: str,
    store=Depends(get_store),
) -> dict:
    """Latest ARMM report for a project with weakest-link breakdown."""
    scorer = _get_scorer(store)
    report = scorer.get_report(project_id)
    if report.latest_assessment_id is None:
        raise HTTPException(
            status_code=404,
            detail=f"No ARMM assessment found for project {project_id!r}",
        )
    return _serialise_report(report)


@router.get("/{project_id}/history")
async def get_armm_history(
    project_id: str,
    store=Depends(get_store),
) -> dict:
    """All ARMM assessments for a project, oldest first."""
    rows = store.get_armm_assessments(project_id)
    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"No ARMM assessments found for project {project_id!r}",
        )
    return {
        "project_id": project_id,
        "count": len(rows),
        "items": [_serialise_assessment_row(r) for r in rows],
    }


@router.get("/{project_id}/criteria")
async def get_armm_criteria(
    project_id: str,
    dimension: str | None = None,
    topic: str | None = None,
    met: bool | None = None,
    store=Depends(get_store),
) -> dict:
    """Criterion-level results for the latest assessment (drill-through).

    Query params:
    - ``dimension``: filter by dimension code (TC / OR / GA / CC)
    - ``topic``: filter by topic code (e.g. TC-IV, OR-BC)
    - ``met``: filter by met status (true/false)
    """
    # Get latest assessment id
    rows = store.get_armm_assessments(project_id)
    if not rows:
        raise HTTPException(
            status_code=404,
            detail=f"No ARMM assessments found for project {project_id!r}",
        )
    latest_id = rows[-1]["id"]

    criteria_rows = store.get_armm_criterion_results(
        assessment_id=latest_id,
        dimension_code=dimension,
        topic_code=topic,
    )
    if met is not None:
        criteria_rows = [r for r in criteria_rows if bool(r["met"]) == met]

    return {
        "project_id": project_id,
        "assessment_id": latest_id,
        "dimension_filter": dimension,
        "topic_filter": topic,
        "met_filter": met,
        "total": len(criteria_rows),
        "met_count": sum(1 for r in criteria_rows if r["met"]),
        "items": [
            {
                "criterion_id": r["criterion_id"],
                "topic_code": r["topic_code"],
                "dimension_code": r["dimension_code"],
                "met": bool(r["met"]),
                "evidence_ref": r.get("evidence_ref") or None,
                "notes": r.get("notes") or None,
            }
            for r in criteria_rows
        ],
    }


@router.get("/{project_id}/dimensions")
async def get_armm_dimensions(
    project_id: str,
    store=Depends(get_store),
) -> dict:
    """Per-dimension and per-topic breakdown for the latest assessment."""
    from pm_data_tools.assurance.armm import (  # noqa: PLC0415
        DIMENSION_LABELS,
        DIMENSION_TOPICS,
        MATURITY_LABELS,
        TOPIC_LABELS,
        ARMMDimension,
        MaturityLevel,
    )

    scorer = _get_scorer(store)
    report = scorer.get_report(project_id)
    if report.latest_assessment_id is None:
        raise HTTPException(
            status_code=404,
            detail=f"No ARMM assessment found for project {project_id!r}",
        )

    dimensions = []
    for dim in ARMMDimension:
        dim_level_int = report.dimension_levels.get(dim.value, 0)
        dim_level = MaturityLevel(dim_level_int)
        topics_out = []
        for topic in DIMENSION_TOPICS[dim]:
            t_level_int = report.topic_levels.get(topic.value, 0)
            t_level = MaturityLevel(t_level_int)
            topics_out.append(
                {
                    "topic_code": topic.value,
                    "label": TOPIC_LABELS.get(topic, topic.value),
                    "level": t_level_int,
                    "level_label": MATURITY_LABELS.get(t_level, str(t_level_int)),
                    "score_pct": report.topic_scores.get(topic.value, 0.0),
                    "is_blocking": report.dimension_blocking_topics.get(dim.value) == topic.value,
                }
            )
        dimensions.append(
            {
                "dimension_code": dim.value,
                "label": DIMENSION_LABELS.get(dim, dim.value),
                "level": dim_level_int,
                "level_label": MATURITY_LABELS.get(dim_level, str(dim_level_int)),
                "score_pct": report.dimension_scores.get(dim.value, 0.0),
                "blocking_topic": report.dimension_blocking_topics.get(dim.value),
                "is_overall_blocking": report.blocking_dimension == dim.value,
                "topics": topics_out,
            }
        )

    return {
        "project_id": project_id,
        "assessment_id": report.latest_assessment_id,
        "assessed_at": report.assessed_at,
        "overall_level": int(report.overall_level),
        "overall_score_pct": report.overall_score_pct,
        "dimensions": dimensions,
    }
