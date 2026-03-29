"""Portfolio router — /api/portfolio."""

from __future__ import annotations

from collections import Counter, defaultdict

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


def _health_to_score(health: str) -> int:
    return {"HEALTHY": 90, "ATTENTION_NEEDED": 65, "AT_RISK": 40, "CRITICAL": 20}.get(health, 50)


@router.get("/action-closure")
async def portfolio_action_closure(
    registry: dict = Depends(get_registry),
    store=Depends(get_store),
) -> dict:
    """Portfolio-wide action closure rate: closed / total."""
    total, closed = 0, 0
    for pid in registry:
        all_actions = store.get_recommendations(pid)
        total += len(all_actions)
        closed += sum(1 for a in all_actions if a.get("status") == "CLOSED")
    rate = round(closed / total, 3) if total else 0.0
    return {"total_actions": total, "closed_actions": closed, "closure_rate": rate}


@router.get("/override-impact")
async def portfolio_override_impact(
    registry: dict = Depends(get_registry),
    store=Depends(get_store),
) -> dict:
    """Portfolio-wide override impact rate: significant+escalated / total."""
    total, impactful = 0, 0
    for pid in registry:
        overrides = store.get_override_decisions(pid)
        total += len(overrides)
        impactful += sum(
            1 for o in overrides
            if o.get("outcome") in ("SIGNIFICANT_IMPACT", "ESCALATED")
        )
    rate = round(impactful / total, 3) if total else 0.0
    return {"total_overrides": total, "impactful_overrides": impactful, "impact_rate": rate}


@router.get("/compliance-trend")
async def portfolio_compliance_trend(
    registry: dict = Depends(get_registry),
    store=Depends(get_store),
) -> dict:
    """Average monthly compliance score across all projects."""
    monthly: dict[str, list[float]] = defaultdict(list)
    for pid in registry:
        for record in store.get_confidence_scores(pid):
            ts = record.get("timestamp", "")
            month = ts[:7]  # "YYYY-MM"
            if month and isinstance(record.get("score"), (int, float)):
                monthly[month].append(record["score"])
    items = [
        {"month": m, "compliance_score": round(sum(v) / len(v), 1)}
        for m, v in sorted(monthly.items())
    ]
    return {"count": len(items), "items": items}


@router.get("/health-by-domain")
async def portfolio_health_by_domain(
    registry: dict = Depends(get_registry),
    store=Depends(get_store),
) -> dict:
    """Average health score per complexity domain."""
    domain_scores: dict[str, list[int]] = defaultdict(list)
    for pid in registry:
        classifications = store.get_domain_classifications(pid)
        domain = classifications[-1]["domain"] if classifications else registry[pid].get("domain", "CLEAR")
        workflows = store.get_workflow_history(pid)
        health = workflows[-1]["health"] if workflows else "ATTENTION_NEEDED"
        domain_scores[domain].append(_health_to_score(health))
    items = [
        {"label": d, "value": round(sum(v) / len(v))}
        for d, v in sorted(domain_scores.items())
    ]
    return {"count": len(items), "items": items}


@router.get("/effort-by-domain")
async def portfolio_effort_by_domain(
    registry: dict = Depends(get_registry),
    store=Depends(get_store),
) -> dict:
    """Average total effort hours per complexity domain."""
    domain_effort: dict[str, list[float]] = defaultdict(list)
    for pid in registry:
        classifications = store.get_domain_classifications(pid)
        domain = classifications[-1]["domain"] if classifications else registry[pid].get("domain", "CLEAR")
        try:
            history = store.get_overhead_history(pid)
            analysis = history[-1].get("analysis", {}) if history else {}
            hours = analysis.get("total_effort_hours", 0) if analysis else 0
        except Exception:
            hours = 0
        domain_effort[domain].append(hours)
    items = [
        {"label": d, "value": round(sum(v) / len(v), 1)}
        for d, v in sorted(domain_effort.items())
    ]
    return {"count": len(items), "items": items}


@router.get("/recurring-actions")
async def portfolio_recurring_actions(
    registry: dict = Depends(get_registry),
    store=Depends(get_store),
) -> dict:
    """Top recurring action texts across the portfolio."""
    text_counts: Counter = Counter()
    for pid in registry:
        for rec in store.get_recommendations(pid):
            if rec.get("recurrence_of") or rec.get("status") == "RECURRING":
                text_counts[rec.get("text", "")[:60]] += 1
    if not text_counts:
        # Fallback: most common action texts
        for pid in registry:
            for rec in store.get_recommendations(pid):
                text_counts[rec.get("text", "")[:60]] += 1
    items = [
        {"label": text, "value": count}
        for text, count in text_counts.most_common(10)
    ]
    return {"count": len(items), "items": items}


@router.get("/override-heatmap")
async def portfolio_override_heatmap(
    registry: dict = Depends(get_registry),
    store=Depends(get_store),
) -> dict:
    """Override counts by department x override_type for heatmap."""
    matrix: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for pid, meta in registry.items():
        dept = meta.get("department", "Unknown")
        overrides = store.get_override_decisions(pid)
        for o in overrides:
            ov_type = o.get("override_type", "UNKNOWN")
            matrix[dept][ov_type] += 1
    # Convert defaultdicts to plain dicts
    return {"matrix": {d: dict(types) for d, types in matrix.items()}}


@router.get("/lessons-coverage")
async def portfolio_lessons_coverage(store=Depends(get_store)) -> dict:
    """Lesson count by category (adopted vs pending)."""
    all_lessons = store.get_all_lessons()
    cat_counts: dict[str, dict[str, int]] = defaultdict(lambda: {"Adopted": 0, "Pending": 0})
    for lesson in all_lessons:
        cat = lesson.get("category", "OTHER")
        key = "Adopted" if lesson.get("sentiment") == "POSITIVE" else "Pending"
        cat_counts[cat][key] += 1
    items = [
        {"label": cat, **counts}
        for cat, counts in sorted(cat_counts.items())
    ]
    return {"count": len(items), "items": items}
