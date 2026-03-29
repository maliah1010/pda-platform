"""Portfolio router — /api/portfolio."""

from __future__ import annotations

from collections import Counter

from fastapi import APIRouter, Depends

from ..config import get_registry, get_store

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


@router.get("/summary")
async def portfolio_summary(
    registry: dict = Depends(get_registry),
    store=Depends(get_store),
) -> dict:
    """Aggregate stats: project count by domain/health, average compliance, total open actions."""
    project_ids = list(registry.keys())

    domain_counts: Counter = Counter()
    health_counts: Counter = Counter()
    total_score = 0.0
    scored_count = 0
    total_open_actions = 0

    for pid in project_ids:
        meta = registry[pid]
        domain_counts[meta.get("domain", "UNKNOWN")] += 1

        scores = store.get_confidence_scores(pid)
        if scores:
            total_score += scores[-1]["score"]
            scored_count += 1

        open_actions = store.get_recommendations(pid, status_filter="OPEN")
        recurring = store.get_recommendations(pid, status_filter="RECURRING")
        total_open_actions += len(open_actions) + len(recurring)

        workflows = store.get_workflow_history(pid)
        if workflows:
            health_counts[workflows[-1]["health"]] += 1
        else:
            health_counts["UNKNOWN"] += 1

    avg_compliance = round(total_score / scored_count, 2) if scored_count else None

    return {
        "project_count": len(project_ids),
        "by_domain": dict(domain_counts),
        "by_health": dict(health_counts),
        "average_compliance": avg_compliance,
        "total_open_actions": total_open_actions,
    }


@router.get("/health-matrix")
async def health_matrix(
    registry: dict = Depends(get_registry),
    store=Depends(get_store),
) -> dict:
    """All projects with: id, name, department, domain, latest_score, trend, health, open_actions, urgency."""
    rows = []

    for pid, meta in registry.items():
        scores = store.get_confidence_scores(pid)
        latest_score = scores[-1]["score"] if scores else None
        prev_score = scores[-2]["score"] if len(scores) >= 2 else None
        trend = None
        if latest_score is not None and prev_score is not None:
            diff = latest_score - prev_score
            trend = "IMPROVING" if diff > 1.0 else ("DEGRADING" if diff < -1.0 else "STABLE")

        open_actions = store.get_recommendations(pid, status_filter="OPEN")
        recurring = store.get_recommendations(pid, status_filter="RECURRING")
        open_count = len(open_actions) + len(recurring)

        workflows = store.get_workflow_history(pid)
        latest_health = workflows[-1]["health"] if workflows else None

        schedule_history = store.get_schedule_history(pid)
        latest_urgency = schedule_history[-1]["urgency"] if schedule_history else None

        classifications = store.get_domain_classifications(pid)
        domain = classifications[-1]["domain"] if classifications else meta.get("domain")

        rows.append({
            "id": pid,
            "name": meta.get("name"),
            "department": meta.get("department"),
            "domain": domain,
            "latest_score": latest_score,
            "trend": trend,
            "health": latest_health,
            "open_actions": open_count,
            "urgency": latest_urgency,
        })

    return {"count": len(rows), "items": rows}
