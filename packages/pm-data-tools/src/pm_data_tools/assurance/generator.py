"""On-demand single-project synthetic data generator.

Provides :func:`generate_single_project` which runs the full P1–P12
generation pipeline for one project using a parameterised profile.
Used by the PDA API's ``POST /api/projects`` endpoint to generate
assurance data for dynamically-created projects (e.g. from the hackathon
PDF-drop tool).

Unlike ``generate_synthetic_data.py`` (a batch script), this module:
- Never touches the global ``PROJECT_REGISTRY`` or ``_CLASSIFIER_INPUTS``
- Accepts all project-specific values as arguments
- Has no ``random.seed()`` call at module level
"""

from __future__ import annotations

import json
import random
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pm_data_tools.db.store import AssuranceStore

# ---------------------------------------------------------------------------
# Date helpers (mirrors generate_synthetic_data.py)
# ---------------------------------------------------------------------------

_MONTHS = 12
_START_DATE = date(2025, 4, 1)


def _month_date(month_index: int) -> date:
    year = 2025 + (3 + month_index) // 12
    month = ((3 + month_index) % 12) + 1
    return date(year, month, 1)


def _ts(d: date) -> str:
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc).isoformat()


def _jitter(base: float, amplitude: float = 2.0) -> float:
    return round(max(0.0, min(100.0, base + random.uniform(-amplitude, amplitude))), 1)


# ---------------------------------------------------------------------------
# Score trajectories
# ---------------------------------------------------------------------------

def _score_trajectory(domain: str) -> list[float]:
    if domain == "CLEAR":
        base = random.uniform(87.0, 93.0)
        return [_jitter(base, 1.5) for _ in range(_MONTHS)]
    if domain == "COMPLICATED":
        base = random.uniform(74.0, 83.0)
        return [_jitter(base, 2.5) for _ in range(_MONTHS)]
    if domain == "COMPLEX":
        base = random.uniform(68.0, 76.0)
        scores: list[float] = []
        for _ in range(_MONTHS):
            swing = random.uniform(-8.0, 8.0)
            s = max(55.0, min(80.0, base + swing))
            scores.append(round(s, 1))
            base = s
        return scores
    # CHAOTIC
    scores = []
    score = random.uniform(66.0, 72.0)
    for _ in range(_MONTHS):
        score = max(30.0, score - random.uniform(1.5, 4.0))
        scores.append(round(score + random.uniform(-2.0, 1.0), 1))
    return scores


def _dimension_scores(overall: float) -> dict[str, float]:
    dims = ["required_fields", "recommended_fields", "data_quality", "timeliness"]
    return {d: round(max(0.0, min(100.0, overall + random.uniform(-8.0, 8.0))), 1) for d in dims}


# ---------------------------------------------------------------------------
# P2 — Confidence scores
# ---------------------------------------------------------------------------

def _generate_confidence_scores(store: AssuranceStore, project_id: str, domain: str) -> list[float]:
    scores = _score_trajectory(domain)
    for i, score in enumerate(scores):
        d = _month_date(i)
        store.insert_confidence_score(
            project_id=project_id,
            run_id=f"run-{project_id}-{d.isoformat()}",
            timestamp=_ts(d),
            score=score,
            dimension_scores=_dimension_scores(score),
        )
    return scores


# ---------------------------------------------------------------------------
# P3 — Recommendations
# ---------------------------------------------------------------------------

_ACTION_TEXTS: dict[str, list[str]] = {
    "CLEAR": [
        "Confirm gate readiness documentation is current.",
        "Verify benefits realisation plan is reviewed by SRO.",
        "Archive previous-version artefacts in line with retention policy.",
    ],
    "COMPLICATED": [
        "Update interface specification register before next gate.",
        "Ensure procurement timeline is reflected in updated schedule.",
        "Schedule deep-dive with technical lead on dependency mapping.",
        "Reassess risk register following scope change.",
        "Close outstanding action from last gate regarding data migration plan.",
    ],
    "COMPLEX": [
        "Address recurring divergence in supplier dependency classification.",
        "Resolve open action on governance override.",
        "Update benefits profile — current version is out of date.",
        "Escalate stale Benefits Realisation Plan to programme board.",
        "Convene emergency review of RAID log following restructure.",
        "Review AI extraction confidence thresholds with assurance team.",
        "Confirm stakeholder sign-off on revised scope baseline.",
    ],
    "CHAOTIC": [
        "Immediately update Programme Business Case — current version unfit for gate.",
        "Escalate CRITICAL divergence signal to SRO within 24 hours.",
        "Commission emergency independent review of benefits realisation.",
        "Governance board to meet within 7 days to address recurring overrides.",
        "Address all OUTSTANDING compliance actions before next gate.",
        "Reinstate benefits owner — role has been vacant.",
        "Produce emergency schedule recovery plan.",
    ],
}

_CATEGORIES = ["HIGH", "MEDIUM", "LOW", "CRITICAL"]
_STATUS_BY_DOMAIN = {
    "CLEAR": ["CLOSED", "CLOSED", "CLOSED"],
    "COMPLICATED": ["CLOSED", "CLOSED", "OPEN"],
    "COMPLEX": ["OPEN", "OPEN", "RECURRING", "CLOSED"],
    "CHAOTIC": ["OPEN", "OPEN", "OPEN", "RECURRING", "RECURRING"],
}


def _generate_recommendations(store: AssuranceStore, project_id: str, domain: str) -> None:
    texts = _ACTION_TEXTS[domain]
    statuses = _STATUS_BY_DOMAIN[domain]
    prev_ids: list[str] = []
    for quarter in range(1, 5):
        year_suffix = "2025" if quarter <= 2 else "2026"
        review_id = f"review-{project_id}-Q{quarter}-{year_suffix}"
        review_month = (quarter - 1) * 3
        review_d = _month_date(review_month)
        n_actions = random.randint(2, min(5, len(texts)))
        selected = random.sample(texts, n_actions)
        for i, text in enumerate(selected):
            status = random.choice(statuses)
            rec_id = f"rec-{project_id}-Q{quarter}-{i}"
            recurrence_of = random.choice(prev_ids) if prev_ids and status == "RECURRING" else None
            store.upsert_recommendation({
                "id": rec_id,
                "project_id": project_id,
                "text": text,
                "category": random.choice(_CATEGORIES),
                "source_review_id": review_id,
                "review_date": review_d.isoformat(),
                "status": status,
                "owner": random.choice(["PMO", "Tech Lead", "SRO", "Delivery Manager", None]),
                "recurrence_of": recurrence_of,
                "confidence": round(random.uniform(0.65, 0.97), 2),
                "created_at": _ts(review_d),
            })
            prev_ids.append(rec_id)


# ---------------------------------------------------------------------------
# P4 — Divergence snapshots
# ---------------------------------------------------------------------------

_SIGNAL_BY_DOMAIN: dict[str, list[str]] = {
    "CLEAR": ["STABLE", "STABLE", "STABLE", "STABLE"],
    "COMPLICATED": ["STABLE", "STABLE", "STABLE", "LOW_CONSENSUS"],
    "COMPLEX": ["STABLE", "HIGH_DIVERGENCE", "LOW_CONSENSUS", "DEGRADING_CONFIDENCE"],
    "CHAOTIC": ["HIGH_DIVERGENCE", "LOW_CONSENSUS", "HIGH_DIVERGENCE", "DEGRADING_CONFIDENCE"],
}


def _sample_scores_for_signal(signal: str) -> tuple[float, list[float]]:
    if signal == "STABLE":
        c = round(random.uniform(0.78, 0.95), 2)
        s = [round(c + random.uniform(-0.04, 0.04), 2) for _ in range(5)]
    elif signal == "HIGH_DIVERGENCE":
        c = round(random.uniform(0.55, 0.75), 2)
        s = [round(random.uniform(0.30, 0.90), 2) for _ in range(5)]
    elif signal == "LOW_CONSENSUS":
        c = round(random.uniform(0.40, 0.58), 2)
        s = [round(c + random.uniform(-0.05, 0.05), 2) for _ in range(5)]
    else:  # DEGRADING_CONFIDENCE
        c = round(random.uniform(0.55, 0.70), 2)
        s = [round(c + random.uniform(-0.06, 0.04), 2) for _ in range(5)]
    return c, s


def _generate_divergence_snapshots(store: AssuranceStore, project_id: str, domain: str) -> None:
    signals = _SIGNAL_BY_DOMAIN[domain]
    for quarter in range(1, 5):
        year_suffix = "2025" if quarter <= 2 else "2026"
        review_id = f"review-{project_id}-Q{quarter}-{year_suffix}"
        review_d = _month_date((quarter - 1) * 3)
        signal = signals[quarter - 1]
        confidence, samples = _sample_scores_for_signal(signal)
        store.insert_divergence_snapshot(
            snapshot_id=str(uuid.uuid4()),
            project_id=project_id,
            review_id=review_id,
            confidence_score=confidence,
            sample_scores=samples,
            signal_type=signal,
            timestamp=_ts(review_d),
        )


# ---------------------------------------------------------------------------
# P5 — Schedule recommendations
# ---------------------------------------------------------------------------

_URGENCY_BY_DOMAIN = {
    "CLEAR": "DEFERRED",
    "COMPLICATED": "STANDARD",
    "COMPLEX": "EXPEDITED",
    "CHAOTIC": "IMMEDIATE",
}
_URGENCY_DAYS = {"IMMEDIATE": 7, "EXPEDITED": 14, "STANDARD": 42, "DEFERRED": 90}


def _generate_schedule_recommendations(store: AssuranceStore, project_id: str, domain: str) -> None:
    urgency = _URGENCY_BY_DOMAIN[domain]
    days_ahead = _URGENCY_DAYS[urgency]
    for quarter in range(1, 5):
        rec_d = _month_date((quarter - 1) * 3)
        recommended_d = rec_d + timedelta(days=days_ahead + random.randint(-3, 3))
        signals = json.dumps([
            {"source": "P2", "severity": round(random.uniform(0.1, 0.8), 2), "description": "Compliance trend"},
            {"source": "P4", "severity": round(random.uniform(0.1, 0.7), 2), "description": "Divergence signal"},
        ])
        store.insert_schedule_recommendation(
            project_id=project_id,
            timestamp=_ts(rec_d),
            urgency=urgency,
            recommended_date=recommended_d.isoformat(),
            composite_score=round(random.uniform(0.1, 0.9), 2),
            signals_json=signals,
            rationale=f"{urgency} review recommended based on {domain} domain profile.",
        )


# ---------------------------------------------------------------------------
# P6 — Override decisions
# ---------------------------------------------------------------------------

from pm_data_tools.assurance.overrides import (  # noqa: E402
    OverrideDecision,
    OverrideDecisionLogger,
    OverrideOutcome,
    OverrideType,
)

_CHAOTIC_OVERRIDE_TEMPLATES = [
    {
        "override_type": OverrideType.GATE_PROGRESSION,
        "rationale": "Crisis timeline means gate cannot be postponed despite critical assurance findings.",
        "overridden_value": "RED",
        "override_value": "Proceed — emergency conditions apply",
        "outcome": OverrideOutcome.SIGNIFICANT_IMPACT,
        "outcome_notes": "Predicted consequences materialised. Emergency recovery plan now active.",
    },
    {
        "override_type": OverrideType.RECOMMENDATION_DISMISSED,
        "rationale": "Assurance recommendation considered impractical given operational constraints.",
        "outcome": OverrideOutcome.SIGNIFICANT_IMPACT,
    },
    {
        "override_type": OverrideType.RAG_OVERRIDE,
        "rationale": "Board overrides RED rating. Delivery must continue.",
        "overridden_value": "RED",
        "override_value": "AMBER — board accepted residual risk",
        "outcome": OverrideOutcome.ESCALATED,
        "outcome_notes": "Situation deteriorated. Escalation to IPA required.",
    },
]


def _generate_overrides(store: AssuranceStore, project_id: str, domain: str, sro: str) -> None:
    if domain == "CLEAR":
        return
    logger_obj = OverrideDecisionLogger(store=store)
    counts = {"COMPLICATED": (0, 2), "COMPLEX": (2, 4), "CHAOTIC": (4, 6)}
    lo, hi = counts.get(domain, (1, 3))
    count = random.randint(lo, hi)
    months_used: set[int] = set()
    for _ in range(count):
        month = random.randint(1, 11)
        while month in months_used:
            month = random.randint(1, 11)
        months_used.add(month)
        d = _month_date(month)
        if domain == "CHAOTIC":
            tpl = random.choice(_CHAOTIC_OVERRIDE_TEMPLATES)
            outcome = tpl["outcome"]
            decision = OverrideDecision(
                project_id=project_id,
                override_type=tpl["override_type"],
                decision_date=d,
                authoriser=sro,
                rationale=tpl["rationale"],
                overridden_value=tpl.get("overridden_value"),
                override_value=tpl.get("override_value"),
                outcome=outcome,
                outcome_notes=tpl.get("outcome_notes"),
                outcome_date=d + timedelta(days=45) if outcome != OverrideOutcome.PENDING else None,
            )
        else:
            otype = random.choice(list(OverrideType))
            outcome = (
                random.choice([OverrideOutcome.NO_IMPACT, OverrideOutcome.PENDING])
                if domain == "COMPLICATED"
                else random.choice([OverrideOutcome.NO_IMPACT, OverrideOutcome.MINOR_IMPACT, OverrideOutcome.PENDING])
            )
            decision = OverrideDecision(
                project_id=project_id,
                override_type=otype,
                decision_date=d,
                authoriser=sro,
                rationale=f"Override required due to project constraints. Domain: {domain}.",
                outcome=outcome,
                outcome_date=d + timedelta(days=45) if outcome != OverrideOutcome.PENDING else None,
            )
        logger_obj.log_override(decision)


# ---------------------------------------------------------------------------
# P8 — Assurance activities
# ---------------------------------------------------------------------------

from pm_data_tools.assurance.overhead import (  # noqa: E402
    ActivityType,
    AssuranceActivity,
    AssuranceOverheadOptimiser,
)

_ACTIVITY_COUNTS = {"CLEAR": (3, 4), "COMPLICATED": (4, 6), "COMPLEX": (6, 8), "CHAOTIC": (7, 9)}
_ACTIVITY_TYPES_BY_DOMAIN = {
    "CLEAR": [ActivityType.COMPLIANCE_CHECK, ActivityType.DOCUMENT_REVIEW, ActivityType.GATE_REVIEW],
    "COMPLICATED": [ActivityType.GATE_REVIEW, ActivityType.COMPLIANCE_CHECK, ActivityType.DOCUMENT_REVIEW, ActivityType.RISK_ASSESSMENT],
    "COMPLEX": list(ActivityType),
    "CHAOTIC": [ActivityType.GATE_REVIEW, ActivityType.GATE_REVIEW, ActivityType.AUDIT, ActivityType.STAKEHOLDER_REVIEW, ActivityType.RISK_ASSESSMENT],
}


def _generate_activities(
    store: AssuranceStore, project_id: str, domain: str, scores: list[float], project_name: str
) -> None:
    lo, hi = _ACTIVITY_COUNTS[domain]
    count = random.randint(lo, hi)
    optimiser = AssuranceOverheadOptimiser(store=store)
    activity_types = _ACTIVITY_TYPES_BY_DOMAIN[domain]
    used_months = sorted(random.sample(range(_MONTHS), min(count, _MONTHS)))
    for i, month_idx in enumerate(used_months):
        d = _month_date(month_idx)
        atype = activity_types[i % len(activity_types)]
        before = scores[max(0, month_idx - 1)] if month_idx > 0 else scores[0]
        after = scores[month_idx]
        if domain == "CHAOTIC":
            effort, participants, findings = round(random.uniform(20.0, 40.0), 1), random.randint(4, 8), random.randint(0, 2)
        elif domain == "COMPLEX":
            effort, participants, findings = round(random.uniform(10.0, 24.0), 1), random.randint(3, 6), random.randint(1, 5)
        elif domain == "COMPLICATED":
            effort, participants, findings = round(random.uniform(6.0, 16.0), 1), random.randint(2, 4), random.randint(1, 4)
        else:
            effort, participants, findings = round(random.uniform(4.0, 10.0), 1), random.randint(1, 3), random.randint(0, 2)
        artefacts = [f"artefact-{project_id.lower()}-{random.randint(1, 6)}" for _ in range(random.randint(1, 3))]
        activity = AssuranceActivity(
            project_id=project_id,
            activity_type=atype,
            description=f"{atype.value.replace('_', ' ').title()} — {project_name}",
            date=d,
            effort_hours=effort,
            participants=participants,
            artefacts_reviewed=artefacts,
            findings_count=findings,
            confidence_before=before,
            confidence_after=after,
        )
        optimiser.log_activity(activity)
    optimiser.analyse(project_id)


# ---------------------------------------------------------------------------
# P9 — Workflow executions
# ---------------------------------------------------------------------------

from pm_data_tools.assurance.workflows import (  # noqa: E402
    AssuranceWorkflowEngine,
    WorkflowType,
)

_WORKFLOW_TYPES = [
    WorkflowType.FULL_ASSURANCE,
    WorkflowType.RISK_ASSESSMENT,
    WorkflowType.COMPLIANCE_FOCUS,
    WorkflowType.TREND_ANALYSIS,
    WorkflowType.CURRENCY_FOCUS,
]
_HEALTH_BY_DOMAIN = {
    "CLEAR": ["HEALTHY", "HEALTHY", "HEALTHY"],
    "COMPLICATED": ["HEALTHY", "ATTENTION_NEEDED", "HEALTHY"],
    "COMPLEX": ["ATTENTION_NEEDED", "AT_RISK", "ATTENTION_NEEDED", "AT_RISK"],
    "CHAOTIC": ["AT_RISK", "CRITICAL", "CRITICAL", "CRITICAL"],
}


def _generate_workflow_executions(store: AssuranceStore, project_id: str, domain: str) -> None:
    engine = AssuranceWorkflowEngine(store=store)
    health_pool = _HEALTH_BY_DOMAIN[domain]
    n_workflows = random.randint(2, 4)
    months_used = sorted(random.sample(range(1, 12), n_workflows))
    for i, month_idx in enumerate(months_used):
        wf_type = _WORKFLOW_TYPES[i % len(_WORKFLOW_TYPES)]
        d = _month_date(month_idx)
        try:
            engine.execute(project_id=project_id, workflow_type=wf_type)
        except Exception:
            health = health_pool[i % len(health_pool)]
            wf_id = str(uuid.uuid4())
            started = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
            completed = started + timedelta(seconds=random.uniform(1.5, 8.0))
            store.insert_workflow_execution(
                workflow_id=wf_id,
                project_id=project_id,
                workflow_type=wf_type.value,
                started_at=started.isoformat(),
                completed_at=completed.isoformat(),
                duration_ms=round((completed - started).total_seconds() * 1000, 1),
                health=health,
                result_json=json.dumps({"steps": [], "health": health, "risk_signals": []}),
            )


# ---------------------------------------------------------------------------
# P10 — Domain classification
# ---------------------------------------------------------------------------

from pm_data_tools.assurance.classifier import ProjectDomainClassifier  # noqa: E402


def _generate_domain_classification(store: AssuranceStore, classifier_input: Any) -> None:
    clf = ProjectDomainClassifier(store=store)
    clf.classify(classifier_input)
    clf.reclassify_from_store(classifier_input.project_id)


# ---------------------------------------------------------------------------
# P11 — Assumptions
# ---------------------------------------------------------------------------

_ASSUMPTION_TEMPLATES: list[dict[str, Any]] = [
    {"text": "Annual inflation rate will not exceed 3%", "category": "COST", "baseline": 2.5, "unit": "%", "ext": "ONS_CPI"},
    {"text": "Contractor day rates within 10% of current levels", "category": "COST", "baseline": 850.0, "unit": "GBP"},
    {"text": "Planning approval granted within 12 weeks", "category": "SCHEDULE", "baseline": 12.0, "unit": "weeks"},
    {"text": "Delivery milestone dates will not slip more than 4 weeks", "category": "SCHEDULE", "baseline": 4.0, "unit": "weeks"},
    {"text": "Senior developer availability >= 3 FTE through delivery", "category": "RESOURCE", "baseline": 3.0, "unit": "FTE"},
    {"text": "Specialist contractor supply remains stable", "category": "RESOURCE", "baseline": 1.0, "unit": "score"},
    {"text": "API response times will remain under 200ms", "category": "TECHNICAL", "baseline": 200.0, "unit": "ms"},
    {"text": "Cloud platform SLA stays at 99.9%", "category": "TECHNICAL", "baseline": 99.9, "unit": "%"},
    {"text": "Primary supplier remains financially viable", "category": "COMMERCIAL", "baseline": 1.0, "unit": "score"},
    {"text": "GDPR requirements will not change materially", "category": "REGULATORY", "baseline": 1.0, "unit": "score"},
]

_DOMAIN_ASSUMPTION_COUNTS = {"CLEAR": 4, "COMPLICATED": 6, "COMPLEX": 8, "CHAOTIC": 10}
_DOMAIN_DRIFT_SCALE = {"CLEAR": 0.02, "COMPLICATED": 0.08, "COMPLEX": 0.25, "CHAOTIC": 0.50}


def _generate_assumptions(store: AssuranceStore, project_id: str, domain: str) -> None:
    from pm_data_tools.assurance.assumptions import (
        Assumption,
        AssumptionCategory,
        AssumptionSource,
        AssumptionTracker,
    )
    n = _DOMAIN_ASSUMPTION_COUNTS.get(domain, 5)
    drift_scale = _DOMAIN_DRIFT_SCALE.get(domain, 0.05)
    tracker = AssumptionTracker(store=store)
    templates = _ASSUMPTION_TEMPLATES[:n]
    assumption_ids: list[str] = []
    base_date = date(2025, 4, 1)
    for i, tmpl in enumerate(templates):
        cat = AssumptionCategory(tmpl["category"])
        src = AssumptionSource.EXTERNAL_API if tmpl.get("ext") else AssumptionSource.MANUAL
        a = Assumption(
            project_id=project_id,
            text=tmpl["text"],
            category=cat,
            baseline_value=tmpl["baseline"],
            unit=tmpl.get("unit", ""),
            tolerance_pct=15.0 if domain in ("COMPLEX", "CHAOTIC") else 10.0,
            source=src,
            external_ref=tmpl.get("ext"),
            dependencies=[],
            owner="SRO" if i == 0 else ("Finance Lead" if cat == AssumptionCategory.COST else "PM"),
            created_date=base_date,
        )
        tracker.ingest(a)
        assumption_ids.append(a.id)
    n_validations = {"CLEAR": 2, "COMPLICATED": 3, "COMPLEX": 3, "CHAOTIC": 4}.get(domain, 2)
    for idx, assumption_id in enumerate(assumption_ids):
        row = store.get_assumption_by_id(assumption_id)
        if row is None:
            continue
        baseline = float(row["baseline_value"])
        for v in range(n_validations):
            months_elapsed = int((v + 1) * (12 / n_validations))
            base_date + timedelta(days=months_elapsed * 30)
            drift_factor = 1.0 + drift_scale * (v + 1) * random.uniform(0.5, 1.5)
            new_val = round(baseline * drift_factor if idx % 3 == 0 else baseline / drift_factor, 3)
            tracker.update_value(
                assumption_id=assumption_id,
                new_value=new_val,
                source=AssumptionSource.EXTERNAL_API if idx % 2 == 0 else AssumptionSource.MANUAL,
                notes=f"Periodic review month {months_elapsed}",
            )


# ---------------------------------------------------------------------------
# P12 — ARMM assessments
# ---------------------------------------------------------------------------

_ARMM_DOMAIN_PCT: dict[str, dict[str, float]] = {
    "CLEAR":       {"TC": 0.82, "OR": 0.78, "GA": 0.75, "CC": 0.70},
    "COMPLICATED": {"TC": 0.58, "OR": 0.52, "GA": 0.55, "CC": 0.45},
    "COMPLEX":     {"TC": 0.30, "OR": 0.22, "GA": 0.35, "CC": 0.28},
    "CHAOTIC":     {"TC": 0.12, "OR": 0.08, "GA": 0.18, "CC": 0.10},
}
_ARMM_WEAKEST_TOPIC: dict[str, dict[str, str]] = {
    "CLEAR":       {"TC": "TC-SC", "OR": "OR-DR", "GA": "GA-EA", "CC": "CC-CI"},
    "COMPLICATED": {"TC": "TC-RT", "OR": "OR-BC", "GA": "GA-EA", "CC": "CC-CM"},
    "COMPLEX":     {"TC": "TC-SC", "OR": "OR-BC", "GA": "GA-ER", "CC": "CC-SK"},
    "CHAOTIC":     {"TC": "TC-IV", "OR": "OR-BC", "GA": "GA-PF", "CC": "CC-LC"},
}


def _generate_armm_assessments(store: AssuranceStore, project_id: str, domain: str) -> None:
    from pm_data_tools.assurance.armm import (
        TOPIC_CRITERIA_COUNT,
        TOPIC_DIMENSION,
        ARMMScorer,
        ARMMTopic,
        CriterionResult,
    )
    scorer = ARMMScorer(store=store)
    pct_profile = _ARMM_DOMAIN_PCT.get(domain, _ARMM_DOMAIN_PCT["COMPLICATED"])
    weakest = _ARMM_WEAKEST_TOPIC.get(domain, {})
    n_assessments = {"CLEAR": 3, "COMPLICATED": 3, "COMPLEX": 2, "CHAOTIC": 2}.get(domain, 2)
    base_date = date(2025, 4, 1)
    assessors = ["Assurance Lead", "Senior Responsible Owner", "Portfolio Manager"]
    for idx in range(n_assessments):
        months_offset = int(idx * 12 / n_assessments)
        assessment_date = (base_date + timedelta(days=months_offset * 30)).isoformat()
        improvement_bonus = 0.06 * idx if idx > 0 and domain != "CHAOTIC" else 0.0
        criterion_results: list[CriterionResult] = []
        for topic in ARMMTopic:
            dim_code = TOPIC_DIMENSION[topic].value
            n_criteria = TOPIC_CRITERIA_COUNT[topic]
            base_pct = pct_profile.get(dim_code, 0.3) + improvement_bonus
            is_weakest = weakest.get(dim_code) == topic.value
            topic_pct = max(0.0, min(1.0, base_pct - 0.25 if is_weakest else base_pct))
            for i in range(1, n_criteria + 1):
                criterion_id = f"{topic.value}-{i}"
                met = (i / n_criteria) <= topic_pct
                criterion_results.append(CriterionResult(
                    criterion_id=criterion_id,
                    met=met,
                    evidence_ref=f"DOC-{project_id}-{topic.value}-{i}" if met else None,
                ))
        assessment = scorer.assess(
            project_id=project_id,
            criterion_results=criterion_results,
            assessed_by=assessors[idx % len(assessors)],
            notes=f"Assessment {idx + 1} of {n_assessments}",
        )
        with store._connect() as conn:
            conn.execute(
                "UPDATE armm_assessments SET assessed_at = ? WHERE id = ?",
                (assessment_date + "T09:00:00+00:00", assessment.id),
            )
        store.insert_armm_criterion_results(
            assessment_id=assessment.id,
            project_id=project_id,
            results=[
                {
                    "criterion_id": r.criterion_id,
                    "topic_code": "-".join(r.criterion_id.split("-")[:2]),
                    "dimension_code": r.criterion_id.split("-")[0],
                    "met": r.met,
                    "evidence_ref": r.evidence_ref or "",
                    "notes": "",
                }
                for r in criterion_results
            ],
        )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def generate_single_project(
    store: AssuranceStore,
    project_id: str,
    domain: str,
    meta: dict[str, Any],
    classifier_input: Any,
) -> None:
    """Run the full P1–P12 generation pipeline for a single project.

    Args:
        store: Initialised AssuranceStore instance.
        project_id: Unique project identifier (e.g. ``"HACKATHON-A1B2C3D4"``).
        domain: Complexity domain — ``"CLEAR"``, ``"COMPLICATED"``, ``"COMPLEX"``,
            or ``"CHAOTIC"``.
        meta: Project metadata dict with at least ``"name"`` and ``"sro"`` keys.
        classifier_input: A :class:`ClassificationInput` instance for P10
            domain classification.
    """
    scores = _generate_confidence_scores(store, project_id, domain)
    _generate_recommendations(store, project_id, domain)
    _generate_divergence_snapshots(store, project_id, domain)
    _generate_schedule_recommendations(store, project_id, domain)
    _generate_overrides(store, project_id, domain, sro=meta.get("sro", "Programme Director"))
    _generate_activities(store, project_id, domain, scores, project_name=meta.get("name", project_id))
    _generate_assumptions(store, project_id, domain)
    _generate_armm_assessments(store, project_id, domain)
    _generate_workflow_executions(store, project_id, domain)
    _generate_domain_classification(store, classifier_input)
