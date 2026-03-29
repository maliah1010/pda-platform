"""Synthetic data generator for the PDA Assurance Module.

Generates a realistic portfolio of 15 UK government projects with 12 months
of assurance history across all 10 AssuranceStore tables.

Usage::

    # Generate with defaults (demo_store.db in cwd)
    python packages/pm-data-tools/scripts/generate_synthetic_data.py

    # Custom output path
    python packages/pm-data-tools/scripts/generate_synthetic_data.py --output /path/to/demo_store.db

    # Verify record counts after generation
    python packages/pm-data-tools/scripts/generate_synthetic_data.py --verify
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import uuid
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Module path fix — run from repo root
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

import structlog

from pm_data_tools.assurance import (
    ActivityType,
    AssuranceActivity,
    AssuranceOverheadOptimiser,
    AssuranceWorkflowEngine,
    ClassificationInput,
    ComplexityDomain,
    LessonCategory,
    LessonRecord,
    LessonSentiment,
    LessonsKnowledgeEngine,
    OverrideDecision,
    OverrideDecisionLogger,
    OverrideOutcome,
    OverrideType,
    ProjectDomainClassifier,
    ReviewUrgency,
    SignalType,
    WorkflowType,
)
from pm_data_tools.db.store import AssuranceStore

log: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Deterministic seed
# ---------------------------------------------------------------------------
random.seed(42)

# ---------------------------------------------------------------------------
# Date helpers
# ---------------------------------------------------------------------------
START_DATE = date(2025, 4, 1)
END_DATE = date(2026, 3, 31)
MONTHS = 12


def month_date(month_index: int) -> date:
    """Return the first day of month_index (0=Apr 2025 … 11=Mar 2026)."""
    year = 2025 + (3 + month_index) // 12
    month = ((3 + month_index) % 12) + 1
    return date(year, month, 1)


def ts(d: date) -> str:
    """Convert a date to an ISO-8601 UTC timestamp string."""
    return datetime(d.year, d.month, d.day, tzinfo=timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Project registry
# ---------------------------------------------------------------------------
PROJECT_REGISTRY: dict[str, dict[str, Any]] = {
    "PROJ-001": {
        "name": "Digital ID Verification Service",
        "department": "Home Office",
        "category": "ICT",
        "sro": "Sarah Chen",
        "start_date": "2025-04-01",
        "end_date": "2026-09-30",
        "whole_life_cost_m": 12.5,
        "domain": "CLEAR",
    },
    "PROJ-002": {
        "name": "Estate Rationalisation Programme",
        "department": "MoJ",
        "category": "Property",
        "sro": "James Whitfield",
        "start_date": "2025-04-01",
        "end_date": "2027-03-31",
        "whole_life_cost_m": 45.0,
        "domain": "CLEAR",
    },
    "PROJ-003": {
        "name": "Network Refresh Phase 2",
        "department": "HMRC",
        "category": "ICT",
        "sro": "Diana Okafor",
        "start_date": "2025-05-01",
        "end_date": "2026-06-30",
        "whole_life_cost_m": 8.2,
        "domain": "CLEAR",
    },
    "PROJ-004": {
        "name": "ERP Modernisation",
        "department": "DWP",
        "category": "ICT",
        "sro": "Robert Singh",
        "start_date": "2025-04-01",
        "end_date": "2027-09-30",
        "whole_life_cost_m": 110.0,
        "domain": "COMPLICATED",
    },
    "PROJ-005": {
        "name": "Citizen Portal Redesign",
        "department": "HMRC",
        "category": "Digital",
        "sro": "Emma Hastings",
        "start_date": "2025-06-01",
        "end_date": "2026-12-31",
        "whole_life_cost_m": 22.0,
        "domain": "COMPLICATED",
    },
    "PROJ-006": {
        "name": "Border Systems Integration",
        "department": "Home Office",
        "category": "ICT",
        "sro": "Marcus Levy",
        "start_date": "2025-04-01",
        "end_date": "2027-03-31",
        "whole_life_cost_m": 78.5,
        "domain": "COMPLICATED",
    },
    "PROJ-007": {
        "name": "Court Scheduling Platform",
        "department": "MoJ",
        "category": "Digital",
        "sro": "Priya Nair",
        "start_date": "2025-07-01",
        "end_date": "2026-12-31",
        "whole_life_cost_m": 18.0,
        "domain": "COMPLICATED",
    },
    "PROJ-008": {
        "name": "Tax Credits Migration",
        "department": "HMRC",
        "category": "ICT",
        "sro": "Kevin O'Brien",
        "start_date": "2025-04-01",
        "end_date": "2027-06-30",
        "whole_life_cost_m": 145.0,
        "domain": "COMPLICATED",
    },
    "PROJ-009": {
        "name": "Cross-Government Data Platform",
        "department": "CDDO",
        "category": "Transformation",
        "sro": "Amara Diallo",
        "start_date": "2025-04-01",
        "end_date": "2027-09-30",
        "whole_life_cost_m": 62.0,
        "domain": "COMPLEX",
    },
    "PROJ-010": {
        "name": "Defence Logistics Overhaul",
        "department": "MoD",
        "category": "Transformation",
        "sro": "Colonel Peter Nash",
        "start_date": "2025-04-01",
        "end_date": "2028-03-31",
        "whole_life_cost_m": 320.0,
        "domain": "COMPLEX",
    },
    "PROJ-011": {
        "name": "NHS Referral Pathway",
        "department": "DHSC",
        "category": "Digital",
        "sro": "Dr Claire Moss",
        "start_date": "2025-05-01",
        "end_date": "2027-04-30",
        "whole_life_cost_m": 55.0,
        "domain": "COMPLEX",
    },
    "PROJ-012": {
        "name": "Smart Motorways Monitoring",
        "department": "DfT",
        "category": "Infrastructure",
        "sro": "Alan Griffiths",
        "start_date": "2025-04-01",
        "end_date": "2028-09-30",
        "whole_life_cost_m": 890.0,
        "domain": "COMPLEX",
    },
    "PROJ-013": {
        "name": "Universal Credit Next Gen",
        "department": "DWP",
        "category": "Transformation",
        "sro": "Natasha Patel",
        "start_date": "2025-04-01",
        "end_date": "2029-03-31",
        "whole_life_cost_m": 1200.0,
        "domain": "COMPLEX",
    },
    "PROJ-014": {
        "name": "Emergency Response Coordination",
        "department": "Cabinet Office",
        "category": "Transformation",
        "sro": "Sir Douglas Hale",
        "start_date": "2025-04-01",
        "end_date": "2027-03-31",
        "whole_life_cost_m": 180.0,
        "domain": "CHAOTIC",
    },
    "PROJ-015": {
        "name": "AI-Assisted Casework System",
        "department": "Home Office",
        "category": "AI/ICT",
        "sro": "Fiona Campbell",
        "start_date": "2025-06-01",
        "end_date": "2027-06-30",
        "whole_life_cost_m": 95.0,
        "domain": "CHAOTIC",
    },
}

# ---------------------------------------------------------------------------
# Score trajectory builders — produce 12 monthly scores
# ---------------------------------------------------------------------------


def _jitter(base: float, amplitude: float = 2.0) -> float:
    """Add small random noise to a score."""
    return round(max(0.0, min(100.0, base + random.uniform(-amplitude, amplitude))), 1)


def clear_trajectory() -> list[float]:
    """CLEAR: stable plateau 85–95."""
    base = random.uniform(87.0, 93.0)
    return [_jitter(base, 1.5) for _ in range(MONTHS)]


def complicated_trajectory(project_id: str) -> list[float]:
    """COMPLICATED: mostly 70–85 with one optional wobble."""
    base = random.uniform(74.0, 83.0)
    scores = [_jitter(base, 2.5) for _ in range(MONTHS)]
    # Court Scheduling: dip at month 5 then recover
    if project_id == "PROJ-007":
        scores[5] = _jitter(64.0, 2.0)
        scores[6] = _jitter(70.0, 2.0)
    # ERP: stale artefacts month 8, partial recovery
    if project_id == "PROJ-004":
        scores[7] = _jitter(67.0, 2.0)
        scores[8] = _jitter(72.0, 2.0)
    return scores


def complex_trajectory(project_id: str) -> list[float]:
    """COMPLEX: volatile 55–80."""
    base = random.uniform(68.0, 76.0)
    scores: list[float] = []
    for i in range(MONTHS):
        swing = random.uniform(-8.0, 8.0)
        s = max(55.0, min(80.0, base + swing))
        scores.append(round(s, 1))
        base = s
    return scores


def chaotic_trajectory() -> list[float]:
    """CHAOTIC: trending down from ~70 to below 50."""
    scores: list[float] = []
    score = random.uniform(66.0, 72.0)
    for _ in range(MONTHS):
        score = max(30.0, score - random.uniform(1.5, 4.0))
        scores.append(round(score + random.uniform(-2.0, 1.0), 1))
    return scores


def score_trajectory(project_id: str, domain: str) -> list[float]:
    """Return 12 monthly compliance scores for a project."""
    if domain == "CLEAR":
        return clear_trajectory()
    if domain == "COMPLICATED":
        return complicated_trajectory(project_id)
    if domain == "COMPLEX":
        return complex_trajectory(project_id)
    return chaotic_trajectory()


# ---------------------------------------------------------------------------
# Dimension scores helper
# ---------------------------------------------------------------------------

_DIMENSIONS = ["required_fields", "recommended_fields", "data_quality", "timeliness"]


def dimension_scores(overall: float) -> dict[str, float]:
    """Generate plausible per-dimension scores around the overall score."""
    return {
        dim: round(max(0.0, min(100.0, overall + random.uniform(-8.0, 8.0))), 1)
        for dim in _DIMENSIONS
    }


# ---------------------------------------------------------------------------
# P2 — Confidence scores
# ---------------------------------------------------------------------------


def generate_confidence_scores(store: AssuranceStore, project_id: str, domain: str) -> list[float]:
    """Insert 12 monthly compliance scores and return them."""
    scores = score_trajectory(project_id, domain)
    for i, score in enumerate(scores):
        d = month_date(i)
        store.insert_confidence_score(
            project_id=project_id,
            run_id=f"run-{project_id}-{d.isoformat()}",
            timestamp=ts(d),
            score=score,
            dimension_scores=dimension_scores(score),
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
        "Reassess risk register following scope change in module 3.",
        "Close outstanding action from Q1 gate regarding data migration plan.",
    ],
    "COMPLEX": [
        "Address recurring divergence in supplier dependency classification.",
        "Resolve open action on governance override from month 4.",
        "Update benefits profile — current version is 6 months old.",
        "Escalate stale Benefits Realisation Plan to programme board.",
        "Convene emergency review of RAID log following restructure.",
        "Review AI extraction confidence thresholds with assurance team.",
        "Confirm stakeholder sign-off on revised scope baseline.",
        "Close recurring action on data quality in legacy system feeds.",
    ],
    "CHAOTIC": [
        "Immediately update Programme Business Case — current version unfit for gate.",
        "Escalate CRITICAL divergence signal to SRO within 24 hours.",
        "Commission emergency independent review of benefits realisation.",
        "Governance board to meet within 7 days to address recurring overrides.",
        "Halt delivery on workstream 3 until security review is complete.",
        "Reinstate benefits owner — role has been vacant for 3 months.",
        "Produce emergency schedule recovery plan for gate 5.",
        "Address all OUTSTANDING compliance actions before next gate.",
    ],
}

_CATEGORIES = ["HIGH", "MEDIUM", "LOW", "CRITICAL"]
_STATUS_BY_DOMAIN = {
    "CLEAR": ["CLOSED", "CLOSED", "CLOSED"],
    "COMPLICATED": ["CLOSED", "CLOSED", "OPEN"],
    "COMPLEX": ["OPEN", "OPEN", "RECURRING", "CLOSED"],
    "CHAOTIC": ["OPEN", "OPEN", "OPEN", "RECURRING", "RECURRING"],
}


def generate_recommendations(store: AssuranceStore, project_id: str, domain: str) -> None:
    """Insert 2–5 actions per quarterly review (4 quarters = 8–20 per project)."""
    texts = _ACTION_TEXTS[domain]
    statuses = _STATUS_BY_DOMAIN[domain]
    prev_ids: list[str] = []

    for quarter in range(1, 5):
        year_suffix = "2025" if quarter <= 2 else "2026"
        review_id = f"review-{project_id}-Q{quarter}-{year_suffix}"
        review_month = (quarter - 1) * 3
        review_d = month_date(review_month)
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
                "created_at": ts(review_d),
            })
            prev_ids.append(rec_id)


# ---------------------------------------------------------------------------
# P4 — Divergence snapshots
# ---------------------------------------------------------------------------

_SIGNAL_BY_DOMAIN = {
    "CLEAR": [SignalType.STABLE, SignalType.STABLE, SignalType.STABLE, SignalType.STABLE],
    "COMPLICATED": [SignalType.STABLE, SignalType.STABLE, SignalType.STABLE, SignalType.LOW_CONSENSUS],
    "COMPLEX": [
        SignalType.STABLE,
        SignalType.HIGH_DIVERGENCE,
        SignalType.LOW_CONSENSUS,
        SignalType.DEGRADING_CONFIDENCE,
    ],
    "CHAOTIC": [
        SignalType.HIGH_DIVERGENCE,
        SignalType.LOW_CONSENSUS,
        SignalType.HIGH_DIVERGENCE,
        SignalType.DEGRADING_CONFIDENCE,
    ],
}


def _sample_scores_for_signal(signal: SignalType) -> tuple[float, list[float]]:
    """Generate a consensus score and 5 sample scores for a given signal type."""
    if signal == SignalType.STABLE:
        consensus = round(random.uniform(0.78, 0.95), 2)
        samples = [round(consensus + random.uniform(-0.04, 0.04), 2) for _ in range(5)]
    elif signal == SignalType.HIGH_DIVERGENCE:
        consensus = round(random.uniform(0.55, 0.75), 2)
        samples = [round(random.uniform(0.30, 0.90), 2) for _ in range(5)]
    elif signal == SignalType.LOW_CONSENSUS:
        consensus = round(random.uniform(0.40, 0.58), 2)
        samples = [round(consensus + random.uniform(-0.05, 0.05), 2) for _ in range(5)]
    else:  # DEGRADING_CONFIDENCE
        consensus = round(random.uniform(0.55, 0.70), 2)
        samples = [round(consensus + random.uniform(-0.06, 0.04), 2) for _ in range(5)]
    return consensus, samples


def generate_divergence_snapshots(store: AssuranceStore, project_id: str, domain: str) -> None:
    """Insert one divergence snapshot per quarterly review."""
    signals = _SIGNAL_BY_DOMAIN[domain]
    for quarter in range(1, 5):
        year_suffix = "2025" if quarter <= 2 else "2026"
        review_id = f"review-{project_id}-Q{quarter}-{year_suffix}"
        review_month = (quarter - 1) * 3
        review_d = month_date(review_month)
        signal = signals[quarter - 1]
        confidence, samples = _sample_scores_for_signal(signal)
        store.insert_divergence_snapshot(
            snapshot_id=str(uuid.uuid4()),
            project_id=project_id,
            review_id=review_id,
            confidence_score=confidence,
            sample_scores=samples,
            signal_type=signal.value,
            timestamp=ts(review_d),
        )


# ---------------------------------------------------------------------------
# P5 — Schedule recommendations
# ---------------------------------------------------------------------------

_URGENCY_BY_DOMAIN = {
    "CLEAR": ReviewUrgency.DEFERRED,
    "COMPLICATED": ReviewUrgency.STANDARD,
    "COMPLEX": ReviewUrgency.EXPEDITED,
    "CHAOTIC": ReviewUrgency.IMMEDIATE,
}


def generate_schedule_recommendations(store: AssuranceStore, project_id: str, domain: str) -> None:
    """Insert quarterly adaptive scheduling recommendations."""
    urgency = _URGENCY_BY_DOMAIN[domain]
    intervals = {
        ReviewUrgency.IMMEDIATE: 7,
        ReviewUrgency.EXPEDITED: 14,
        ReviewUrgency.STANDARD: 42,
        ReviewUrgency.DEFERRED: 90,
    }
    days_ahead = intervals[urgency]

    for quarter in range(1, 5):
        review_month = (quarter - 1) * 3
        rec_d = month_date(review_month)
        recommended_d = rec_d + timedelta(days=days_ahead + random.randint(-3, 3))
        composite = round(random.uniform(0.1, 0.9), 2)
        signals = json.dumps([
            {"source": "P2", "severity": round(random.uniform(0.1, 0.8), 2), "description": "Compliance trend"},
            {"source": "P4", "severity": round(random.uniform(0.1, 0.7), 2), "description": "Divergence signal"},
        ])
        store.insert_schedule_recommendation(
            project_id=project_id,
            timestamp=ts(rec_d),
            urgency=urgency.value,
            recommended_date=recommended_d.isoformat(),
            composite_score=composite,
            signals_json=signals,
            rationale=f"{urgency.value} review recommended based on {domain} domain profile.",
        )


# ---------------------------------------------------------------------------
# P6 — Override decisions
# ---------------------------------------------------------------------------

_OVERRIDE_COUNTS = {"CLEAR": 0, "COMPLICATED": (0, 2), "COMPLEX": (2, 4), "CHAOTIC": (4, 6)}

_PROJECT_OVERRIDES: dict[str, list[dict[str, Any]]] = {
    "PROJ-005": [  # Citizen Portal: one RAG_OVERRIDE, NO_IMPACT
        {
            "override_type": OverrideType.RAG_OVERRIDE,
            "month": 4,
            "authoriser": "Emma Hastings (SRO)",
            "rationale": "Business stakeholder assessment differs from assurance RAG. Proceeding amber.",
            "overridden_value": "RED",
            "override_value": "AMBER",
            "outcome": OverrideOutcome.NO_IMPACT,
        }
    ],
    "PROJ-008": [  # Tax Credits: SCHEDULE_OVERRIDE for procurement
        {
            "override_type": OverrideType.SCHEDULE_OVERRIDE,
            "month": 5,
            "authoriser": "Kevin O'Brien (SRO)",
            "rationale": "Procurement challenge period extends timeline by 6 weeks. Review deferred.",
            "overridden_value": "Review due 2025-09-01",
            "override_value": "Review deferred to 2025-10-15",
            "outcome": OverrideOutcome.NO_IMPACT,
        }
    ],
    "PROJ-011": [  # NHS: 3 RECOMMENDATION_DISMISSED, 2 with MINOR_IMPACT
        {
            "override_type": OverrideType.RECOMMENDATION_DISMISSED,
            "month": 2,
            "authoriser": "Dr Claire Moss (SRO)",
            "rationale": "Requirements change is clinically justified. Assurance recommendation noted but dismissed.",
            "outcome": OverrideOutcome.MINOR_IMPACT,
            "outcome_notes": "Minor delay in pathways testing caused by scope expansion.",
        },
        {
            "override_type": OverrideType.RECOMMENDATION_DISMISSED,
            "month": 5,
            "authoriser": "Dr Claire Moss (SRO)",
            "rationale": "Clinical team confirmed requirements are stable — assurance concern overestimated.",
            "outcome": OverrideOutcome.NO_IMPACT,
        },
        {
            "override_type": OverrideType.RECOMMENDATION_DISMISSED,
            "month": 9,
            "authoriser": "NHS Programme Board",
            "rationale": "Patient safety board overrides assurance schedule recommendation.",
            "outcome": OverrideOutcome.MINOR_IMPACT,
            "outcome_notes": "Assurance gap contributed to delayed system validation.",
        },
    ],
    "PROJ-012": [  # Smart Motorways: GATE_PROGRESSION past RED
        {
            "override_type": OverrideType.GATE_PROGRESSION,
            "month": 6,
            "authoriser": "Alan Griffiths (SRO)",
            "rationale": "Parliamentary commitment requires delivery on schedule. Proceeding past red gate.",
            "overridden_value": "RED — gate failed on safety baseline",
            "override_value": "Proceed with conditions: safety review by month 9",
            "outcome": OverrideOutcome.SIGNIFICANT_IMPACT,
            "outcome_notes": "Safety review revealed integration gaps requiring rework.",
        },
        {
            "override_type": OverrideType.RISK_ACCEPTANCE,
            "month": 9,
            "authoriser": "DfT Risk Committee",
            "rationale": "Technical novelty risk accepted in line with programme risk appetite.",
            "outcome": OverrideOutcome.PENDING,
        },
    ],
    "PROJ-013": [  # Universal Credit: multiple overrides
        {
            "override_type": OverrideType.GATE_PROGRESSION,
            "month": 3,
            "authoriser": "Natasha Patel (SRO)",
            "rationale": "Political visibility requires delivery to proceed despite stale benefits profile.",
            "overridden_value": "AMBER — benefits profile outdated",
            "override_value": "Proceed with updated benefits review within 30 days",
            "outcome": OverrideOutcome.MINOR_IMPACT,
        },
        {
            "override_type": OverrideType.RECOMMENDATION_DISMISSED,
            "month": 6,
            "authoriser": "DWP Assurance Committee",
            "rationale": "Recommendation to pause delivery considered disproportionate.",
            "outcome": OverrideOutcome.MINOR_IMPACT,
        },
        {
            "override_type": OverrideType.RAG_OVERRIDE,
            "month": 10,
            "authoriser": "Natasha Patel (SRO)",
            "rationale": "SRO overrides AMBER to GREEN ahead of ministerial briefing.",
            "overridden_value": "AMBER",
            "override_value": "GREEN",
            "outcome": OverrideOutcome.PENDING,
        },
    ],
}

_CHAOTIC_OVERRIDE_TEMPLATES = [
    {
        "override_type": OverrideType.GATE_PROGRESSION,
        "authoriser": "{sro}",
        "rationale": "Crisis timeline means gate cannot be postponed despite critical assurance findings.",
        "overridden_value": "RED",
        "override_value": "Proceed — emergency conditions apply",
        "outcome": OverrideOutcome.SIGNIFICANT_IMPACT,
        "outcome_notes": "Predicted consequences materialised. Emergency recovery plan now active.",
    },
    {
        "override_type": OverrideType.RECOMMENDATION_DISMISSED,
        "authoriser": "{sro}",
        "rationale": "Assurance recommendation considered impractical given operational constraints.",
        "outcome": OverrideOutcome.SIGNIFICANT_IMPACT,
    },
    {
        "override_type": OverrideType.RAG_OVERRIDE,
        "authoriser": "Programme Board",
        "rationale": "Board overrides RED rating. Delivery must continue.",
        "overridden_value": "RED",
        "override_value": "AMBER — board accepted residual risk",
        "outcome": OverrideOutcome.ESCALATED,
        "outcome_notes": "Situation deteriorated. Escalation to IPA required.",
    },
    {
        "override_type": OverrideType.RISK_ACCEPTANCE,
        "authoriser": "{sro}",
        "rationale": "Risk formally accepted at programme board. No alternative mitigation available.",
        "outcome": OverrideOutcome.SIGNIFICANT_IMPACT,
    },
    {
        "override_type": OverrideType.SCHEDULE_OVERRIDE,
        "authoriser": "Ministers office",
        "rationale": "Ministerial direction requires schedule maintained despite assurance concerns.",
        "outcome": OverrideOutcome.ESCALATED,
        "outcome_notes": "Schedule slippage of 6 months now confirmed. IPA review commissioned.",
    },
]


def generate_overrides(store: AssuranceStore, project_id: str, domain: str) -> None:
    """Insert override decisions appropriate to the domain."""
    meta = PROJECT_REGISTRY[project_id]
    logger_obj = OverrideDecisionLogger(store=store)

    # Specific overrides for named projects
    if project_id in _PROJECT_OVERRIDES:
        for spec in _PROJECT_OVERRIDES[project_id]:
            d = month_date(spec["month"])
            decision = OverrideDecision(
                project_id=project_id,
                override_type=spec["override_type"],
                decision_date=d,
                authoriser=spec["authoriser"],
                rationale=spec["rationale"],
                overridden_value=spec.get("overridden_value"),
                override_value=spec.get("override_value"),
                outcome=spec.get("outcome", OverrideOutcome.PENDING),
                outcome_notes=spec.get("outcome_notes"),
                outcome_date=d + timedelta(days=60) if spec.get("outcome") not in (None, OverrideOutcome.PENDING) else None,
            )
            logger_obj.log_override(decision)
        return

    # General generation by domain
    if domain == "CLEAR":
        return

    lo, hi = _OVERRIDE_COUNTS[domain] if isinstance(_OVERRIDE_COUNTS[domain], tuple) else (0, 0)
    count = random.randint(lo, hi)
    months_used: set[int] = set()
    for _ in range(count):
        month = random.randint(1, 11)
        while month in months_used:
            month = random.randint(1, 11)
        months_used.add(month)

        d = month_date(month)
        otype = random.choice(list(OverrideType))
        if domain == "COMPLICATED":
            outcome = random.choice([OverrideOutcome.NO_IMPACT, OverrideOutcome.PENDING])
        elif domain == "COMPLEX":
            outcome = random.choice([
                OverrideOutcome.NO_IMPACT, OverrideOutcome.MINOR_IMPACT,
                OverrideOutcome.PENDING, OverrideOutcome.MINOR_IMPACT,
            ])
        else:  # CHAOTIC — use templates
            tpl = random.choice(_CHAOTIC_OVERRIDE_TEMPLATES)
            otype = tpl["override_type"]
            outcome = tpl["outcome"]
            decision = OverrideDecision(
                project_id=project_id,
                override_type=otype,
                decision_date=d,
                authoriser=tpl["authoriser"].format(sro=meta["sro"]),
                rationale=tpl["rationale"],
                overridden_value=tpl.get("overridden_value"),
                override_value=tpl.get("override_value"),
                outcome=outcome,
                outcome_notes=tpl.get("outcome_notes"),
                outcome_date=d + timedelta(days=45) if outcome != OverrideOutcome.PENDING else None,
            )
            logger_obj.log_override(decision)
            continue

        decision = OverrideDecision(
            project_id=project_id,
            override_type=otype,
            decision_date=d,
            authoriser=meta["sro"],
            rationale=f"Override required due to project constraints. Domain: {domain}.",
            outcome=outcome,
            outcome_date=d + timedelta(days=45) if outcome != OverrideOutcome.PENDING else None,
        )
        logger_obj.log_override(decision)


# ---------------------------------------------------------------------------
# P7 — Lessons learned (30–40 across the portfolio)
# ---------------------------------------------------------------------------

_LESSONS_CORPUS: list[dict[str, Any]] = [
    # GOVERNANCE
    {
        "project_id": "PROJ-014", "title": "Governance structures must be established before delivery begins",
        "description": "Emergency Response lacked a functioning programme board for the first 3 months. Decision-making was paralysed during a critical initiation period.",
        "category": LessonCategory.GOVERNANCE, "sentiment": LessonSentiment.NEGATIVE,
        "project_type": "Transformation", "project_phase": "Initiation",
        "department": "Cabinet Office", "tags": ["governance", "programme-board", "initiation"],
        "impact_description": "6-week delay in mobilisation. First gate review had to be postponed.",
    },
    {
        "project_id": "PROJ-001", "title": "Fortnightly SRO updates maintain assurance momentum",
        "description": "Digital ID kept assurance current by scheduling short fortnightly SRO briefings. Gate reviews were straightforward as a result.",
        "category": LessonCategory.GOVERNANCE, "sentiment": LessonSentiment.POSITIVE,
        "project_type": "ICT", "project_phase": "Delivery",
        "department": "Home Office", "tags": ["governance", "SRO", "cadence"],
    },
    {
        "project_id": "PROJ-013", "title": "Political visibility creates pressure to override assurance advice",
        "description": "Universal Credit Next Gen experienced repeated pressure to override assurance recommendations to meet ministerial milestones.",
        "category": LessonCategory.GOVERNANCE, "sentiment": LessonSentiment.NEGATIVE,
        "project_type": "Transformation", "project_phase": "Delivery",
        "department": "DWP", "tags": ["overrides", "political", "assurance"],
        "impact_description": "Three overrides in 12 months. Two resulted in minor impact on delivery quality.",
    },
    # TECHNICAL
    {
        "project_id": "PROJ-015", "title": "AI systems require bespoke assurance frameworks — standard templates are insufficient",
        "description": "AI-Assisted Casework found that NISTA standard fields did not capture AI-specific risks. Assurance team had to improvise, leading to low confidence scores.",
        "category": LessonCategory.TECHNICAL, "sentiment": LessonSentiment.NEGATIVE,
        "project_type": "AI/ICT", "project_phase": "Initiation",
        "department": "Home Office", "tags": ["AI", "assurance-framework", "NISTA"],
        "impact_description": "Confidence scores consistently below 0.60 due to framework mismatch.",
    },
    {
        "project_id": "PROJ-003", "title": "Well-documented network architecture accelerates gate reviews",
        "description": "Network Refresh Phase 2 maintained a live architecture decision log. Reviewers could validate technical decisions without deep-dive interviews.",
        "category": LessonCategory.TECHNICAL, "sentiment": LessonSentiment.POSITIVE,
        "project_type": "ICT", "project_phase": "Delivery",
        "department": "HMRC", "tags": ["architecture", "documentation", "gate-review"],
    },
    {
        "project_id": "PROJ-010", "title": "Supplier dependency mapping must be completed before gate 2",
        "description": "Defence Logistics had 47 external dependencies. Many were not mapped until gate 3, creating recurring assurance actions.",
        "category": LessonCategory.TECHNICAL, "sentiment": LessonSentiment.NEGATIVE,
        "project_type": "Transformation", "project_phase": "Initiation",
        "department": "MoD", "tags": ["dependencies", "suppliers", "mapping"],
        "impact_description": "Recurring assurance actions raised at every quarterly review.",
    },
    # COMMERCIAL
    {
        "project_id": "PROJ-008", "title": "Challenge period for contracts must be built into the schedule baseline",
        "description": "Tax Credits Migration assumed a 10-week procurement cycle. The challenge period extended this by 6 weeks, causing a SCHEDULE_OVERRIDE.",
        "category": LessonCategory.COMMERCIAL, "sentiment": LessonSentiment.NEGATIVE,
        "project_type": "ICT", "project_phase": "Procurement",
        "department": "HMRC", "tags": ["procurement", "schedule", "commercial"],
        "impact_description": "Schedule override required. 6-week delivery slip.",
    },
    {
        "project_id": "PROJ-006", "title": "Contracts with clear interface specifications reduce recurring assurance actions",
        "description": "Border Systems Integration included detailed interface specs in supplier contracts from the outset. This reduced ambiguity-driven assurance actions by 40%.",
        "category": LessonCategory.COMMERCIAL, "sentiment": LessonSentiment.POSITIVE,
        "project_type": "ICT", "project_phase": "Procurement",
        "department": "Home Office", "tags": ["contracts", "interfaces", "suppliers"],
    },
    # STAKEHOLDER
    {
        "project_id": "PROJ-009", "title": "Cross-government programmes require a dedicated stakeholder engagement plan",
        "description": "Cross-Government Data Platform underestimated stakeholder diversity. 12 departments with competing priorities drove volatile compliance scores.",
        "category": LessonCategory.STAKEHOLDER, "sentiment": LessonSentiment.NEGATIVE,
        "project_type": "Transformation", "project_phase": "Initiation",
        "department": "CDDO", "tags": ["stakeholders", "cross-government", "engagement"],
        "impact_description": "Compliance volatility ranged 55–80. Multiple overrides required.",
    },
    {
        "project_id": "PROJ-005", "title": "Early citizen research prevents costly redesign",
        "description": "Citizen Portal ran user research panels from month 2. Requirements were stable from gate 1. No significant change control needed.",
        "category": LessonCategory.STAKEHOLDER, "sentiment": LessonSentiment.POSITIVE,
        "project_type": "Digital", "project_phase": "Initiation",
        "department": "HMRC", "tags": ["user-research", "citizens", "requirements"],
    },
    # RESOURCE
    {
        "project_id": "PROJ-014", "title": "Crisis-mode staffing leads to assurance overhead misallocation",
        "description": "Emergency Response Coordination staffed assurance activities reactively. All effort went to gate reviews, none to document review or compliance checks.",
        "category": LessonCategory.RESOURCE, "sentiment": LessonSentiment.NEGATIVE,
        "project_type": "Transformation", "project_phase": "Delivery",
        "department": "Cabinet Office", "tags": ["staffing", "assurance-overhead", "MISALLOCATED"],
        "impact_description": "Efficiency rating: MISALLOCATED. 80% of effort in GATE_REVIEW type.",
    },
    {
        "project_id": "PROJ-002", "title": "Dedicated estates PM with prior MoJ experience halved review preparation time",
        "description": "Estate Rationalisation appointed an experienced PM who knew the asset register. Gate review preparation dropped from 3 weeks to 10 days.",
        "category": LessonCategory.RESOURCE, "sentiment": LessonSentiment.POSITIVE,
        "project_type": "Property", "project_phase": "Delivery",
        "department": "MoJ", "tags": ["experience", "preparation", "efficiency"],
    },
    # REQUIREMENTS
    {
        "project_id": "PROJ-011", "title": "Clinically-driven requirements changes invalidate baseline assurance",
        "description": "NHS Referral Pathway had requirements changed 4 times for clinical safety reasons. Each change invalidated previous assurance compliance checks.",
        "category": LessonCategory.REQUIREMENTS, "sentiment": LessonSentiment.NEGATIVE,
        "project_type": "Digital", "project_phase": "Delivery",
        "department": "DHSC", "tags": ["requirements", "clinical", "change-control"],
        "impact_description": "Three RECOMMENDATION_DISMISSED overrides. Two with MINOR_IMPACT.",
    },
    {
        "project_id": "PROJ-007", "title": "Mock court sessions early in design prevent late-stage rework",
        "description": "Court Scheduling Platform ran shadow scheduling sessions with court clerks in month 4. Requirements were locked before technical build started.",
        "category": LessonCategory.REQUIREMENTS, "sentiment": LessonSentiment.POSITIVE,
        "project_type": "Digital", "project_phase": "Design",
        "department": "MoJ", "tags": ["requirements", "user-testing", "courts"],
    },
    # ESTIMATION
    {
        "project_id": "PROJ-013", "title": "Benefits profiles for legacy transformation projects must be revisited quarterly",
        "description": "Universal Credit Next Gen produced a benefits profile at gate 1 that was not updated for 8 months. Artefact was classified OUTDATED at three consecutive reviews.",
        "category": LessonCategory.ESTIMATION, "sentiment": LessonSentiment.NEGATIVE,
        "project_type": "Transformation", "project_phase": "Delivery",
        "department": "DWP", "tags": ["benefits", "estimation", "artefact-currency"],
        "impact_description": "OUTDATED classification triggered gate_progression override.",
    },
    {
        "project_id": "PROJ-004", "title": "ERP implementation velocity estimates must include data migration overhead",
        "description": "ERP Modernisation underestimated data migration effort by 35%. Compliance scores dipped at month 8 when this became apparent.",
        "category": LessonCategory.ESTIMATION, "sentiment": LessonSentiment.NEGATIVE,
        "project_type": "ICT", "project_phase": "Delivery",
        "department": "DWP", "tags": ["ERP", "estimation", "data-migration"],
    },
    # RISK_MANAGEMENT
    {
        "project_id": "PROJ-015", "title": "AI divergence signals must trigger immediate risk management review",
        "description": "AI-Assisted Casework received HIGH_DIVERGENCE signals in Q1 and Q3 but risk register was not updated. Divergence worsened before any action was taken.",
        "category": LessonCategory.RISK_MANAGEMENT, "sentiment": LessonSentiment.NEGATIVE,
        "project_type": "AI/ICT", "project_phase": "Delivery",
        "department": "Home Office", "tags": ["AI", "divergence", "risk-register"],
        "impact_description": "Risk not captured. Governance escalation required in month 10.",
    },
    {
        "project_id": "PROJ-012", "title": "Safety baseline must be established and gated before proceeding to delivery",
        "description": "Smart Motorways proceeded past a RED gate on safety baseline. GATE_PROGRESSION override had SIGNIFICANT_IMPACT when integration gaps were discovered.",
        "category": LessonCategory.RISK_MANAGEMENT, "sentiment": LessonSentiment.NEGATIVE,
        "project_type": "Infrastructure", "project_phase": "Delivery",
        "department": "DfT", "tags": ["safety", "gate-progression", "infrastructure"],
        "impact_description": "GATE_PROGRESSION override. Significant rework required.",
    },
    {
        "project_id": "PROJ-001", "title": "Risk register linked to assurance artefacts enables proactive currency management",
        "description": "Digital ID linked every risk to the artefact that provided the evidence base. When a risk was updated, the linked artefact was automatically flagged for review.",
        "category": LessonCategory.RISK_MANAGEMENT, "sentiment": LessonSentiment.POSITIVE,
        "project_type": "ICT", "project_phase": "Delivery",
        "department": "Home Office", "tags": ["risk-register", "artefact-currency", "automation"],
    },
    # BENEFITS_REALISATION
    {
        "project_id": "PROJ-014", "title": "Benefits owner vacancy creates assurance gap in crisis projects",
        "description": "Emergency Response had no benefits owner for 3 months. Benefits realisation plan was classified OUTDATED and no one had authority to update it.",
        "category": LessonCategory.BENEFITS_REALISATION, "sentiment": LessonSentiment.NEGATIVE,
        "project_type": "Transformation", "project_phase": "Delivery",
        "department": "Cabinet Office", "tags": ["benefits", "ownership", "vacancy"],
        "impact_description": "Benefits profile stale for 3 consecutive reviews. Assurance score impacted.",
    },
    {
        "project_id": "PROJ-002", "title": "Tracking asset disposal milestones against benefits baseline maintains assurance confidence",
        "description": "Estate Rationalisation tied each asset disposal event to the benefits realisation plan. Benefits profile was always current.",
        "category": LessonCategory.BENEFITS_REALISATION, "sentiment": LessonSentiment.POSITIVE,
        "project_type": "Property", "project_phase": "Delivery",
        "department": "MoJ", "tags": ["benefits", "milestones", "property"],
    },
    # OTHER
    {
        "project_id": "PROJ-009", "title": "Cross-department data governance must be resolved before technical build starts",
        "description": "Cross-Government Data Platform started technical delivery before data governance agreements were in place. Multiple overrides required to proceed.",
        "category": LessonCategory.OTHER, "sentiment": LessonSentiment.NEGATIVE,
        "project_type": "Transformation", "project_phase": "Initiation",
        "department": "CDDO", "tags": ["data-governance", "cross-government", "prerequisites"],
    },
    {
        "project_id": "PROJ-003", "title": "Standard network refresh checklist eliminates gate preparation overhead",
        "description": "Network Refresh Phase 2 adapted a standard NCSC checklist for gate reviews. Preparation time was 4 days versus 2 weeks for bespoke projects.",
        "category": LessonCategory.OTHER, "sentiment": LessonSentiment.POSITIVE,
        "project_type": "ICT", "project_phase": "Delivery",
        "department": "HMRC", "tags": ["checklist", "efficiency", "network"],
    },
    # Additional lessons to reach 30+
    {
        "project_id": "PROJ-010", "title": "Divergence signals in defence contracts indicate contractor information asymmetry",
        "description": "High divergence in AI extractions for Defence Logistics correlated with contractors withholding programme data. Supplier meetings resolved most cases.",
        "category": LessonCategory.COMMERCIAL, "sentiment": LessonSentiment.NEGATIVE,
        "project_type": "Transformation", "project_phase": "Delivery",
        "department": "MoD", "tags": ["divergence", "contractors", "information"],
        "impact_description": "Recurring HIGH_DIVERGENCE signals in Q2 and Q3.",
    },
    {
        "project_id": "PROJ-006", "title": "Interface specification register updated at every sprint reduces gate friction",
        "description": "Border Systems Integration maintained a live interface register updated at each sprint. Reviewers could verify status without requesting separate documentation.",
        "category": LessonCategory.TECHNICAL, "sentiment": LessonSentiment.POSITIVE,
        "project_type": "ICT", "project_phase": "Delivery",
        "department": "Home Office", "tags": ["interface-specs", "sprint", "documentation"],
    },
    {
        "project_id": "PROJ-004", "title": "ERP artefact staleness is predictable — schedule updates proactively",
        "description": "ERP Modernisation found that artefacts consistently went stale between months 7–9 of delivery phases. Scheduling proactive update cycles prevented future classification issues.",
        "category": LessonCategory.GOVERNANCE, "sentiment": LessonSentiment.POSITIVE,
        "project_type": "ICT", "project_phase": "Delivery",
        "department": "DWP", "tags": ["ERP", "artefact-currency", "scheduling"],
    },
    {
        "project_id": "PROJ-011", "title": "Clinical governance and programme governance must be explicitly mapped to avoid duplication",
        "description": "NHS Referral Pathway maintained two parallel governance boards. Decisions were duplicated and sometimes contradictory, leading to overrides.",
        "category": LessonCategory.GOVERNANCE, "sentiment": LessonSentiment.NEGATIVE,
        "project_type": "Digital", "project_phase": "Delivery",
        "department": "DHSC", "tags": ["governance", "clinical", "duplication"],
    },
    {
        "project_id": "PROJ-007", "title": "Month 6 mid-project health check prevents late-stage compliance crises",
        "description": "Court Scheduling Platform added a structured mid-project health check at month 6. The dip in compliance was caught and corrected before the next gate.",
        "category": LessonCategory.GOVERNANCE, "sentiment": LessonSentiment.POSITIVE,
        "project_type": "Digital", "project_phase": "Delivery",
        "department": "MoJ", "tags": ["health-check", "mid-project", "prevention"],
    },
    {
        "project_id": "PROJ-015", "title": "Novel AI deployments should be piloted in sandbox before assurance evidence is collected",
        "description": "AI-Assisted Casework collected assurance evidence from a production-like environment without a sandbox phase. Evidence quality was low and confidence scores suffered.",
        "category": LessonCategory.TECHNICAL, "sentiment": LessonSentiment.NEGATIVE,
        "project_type": "AI/ICT", "project_phase": "Initiation",
        "department": "Home Office", "tags": ["AI", "sandbox", "evidence"],
    },
    {
        "project_id": "PROJ-013", "title": "Universal Credit scale demands dedicated assurance team, not ad hoc reviews",
        "description": "With 7 million claimants in scope, ad hoc assurance was insufficient. A dedicated assurance team was appointed at month 7, improving compliance from 62 to 71.",
        "category": LessonCategory.RESOURCE, "sentiment": LessonSentiment.POSITIVE,
        "project_type": "Transformation", "project_phase": "Delivery",
        "department": "DWP", "tags": ["scale", "assurance-team", "dedicated"],
    },
    {
        "project_id": "PROJ-012", "title": "Infrastructure projects with novel technology require increased assurance cadence from gate 1",
        "description": "Smart Motorways' monitoring technology had no comparable precedent. Standard assurance cadence (quarterly) was too slow to detect emerging risks.",
        "category": LessonCategory.GOVERNANCE, "sentiment": LessonSentiment.NEGATIVE,
        "project_type": "Infrastructure", "project_phase": "Initiation",
        "department": "DfT", "tags": ["infrastructure", "novelty", "cadence"],
        "impact_description": "Safety gap not detected in time. Gate override required.",
    },
    {
        "project_id": "PROJ-005", "title": "Single HMRC assurance team covering multiple digital projects enables cross-learning",
        "description": "The HMRC digital assurance team covered both Citizen Portal and Network Refresh. Lessons from one project were applied to the other within weeks.",
        "category": LessonCategory.RESOURCE, "sentiment": LessonSentiment.POSITIVE,
        "project_type": "Digital", "project_phase": "Delivery",
        "department": "HMRC", "tags": ["shared-team", "cross-learning", "efficiency"],
    },
    {
        "project_id": "PROJ-009", "title": "Lessons from similar platforms were available but not consulted",
        "description": "Cross-Government Data Platform encountered issues identical to GDS data.gov.uk redesign in 2021. Lessons were in the corpus but were not searched before decisions were made.",
        "category": LessonCategory.OTHER, "sentiment": LessonSentiment.NEGATIVE,
        "project_type": "Transformation", "project_phase": "Delivery",
        "department": "CDDO", "tags": ["lessons-learned", "knowledge-management", "repeated-mistakes"],
        "impact_description": "At least 4 issues could have been avoided. Estimated 8-week delay.",
    },
]


def generate_lessons(store: AssuranceStore) -> None:
    """Ingest all portfolio lessons into the store."""
    engine = LessonsKnowledgeEngine(store=store)
    for spec in _LESSONS_CORPUS:
        lesson = LessonRecord(
            project_id=spec["project_id"],
            title=spec["title"],
            description=spec["description"],
            category=spec["category"],
            sentiment=spec["sentiment"],
            project_type=spec.get("project_type"),
            project_phase=spec.get("project_phase"),
            department=spec.get("department"),
            tags=spec.get("tags", []),
            date_recorded=month_date(random.randint(0, 11)),
            recorded_by="PMO Assurance Team",
            impact_description=spec.get("impact_description"),
        )
        engine.ingest(lesson)


# ---------------------------------------------------------------------------
# P8 — Assurance activities
# ---------------------------------------------------------------------------

_ACTIVITY_COUNTS = {"CLEAR": (3, 4), "COMPLICATED": (4, 6), "COMPLEX": (6, 8), "CHAOTIC": (7, 9)}
_ACTIVITY_TYPES_BY_DOMAIN = {
    "CLEAR": [ActivityType.COMPLIANCE_CHECK, ActivityType.DOCUMENT_REVIEW, ActivityType.GATE_REVIEW],
    "COMPLICATED": [ActivityType.GATE_REVIEW, ActivityType.COMPLIANCE_CHECK, ActivityType.DOCUMENT_REVIEW, ActivityType.RISK_ASSESSMENT],
    "COMPLEX": list(ActivityType),
    "CHAOTIC": [ActivityType.GATE_REVIEW, ActivityType.GATE_REVIEW, ActivityType.AUDIT, ActivityType.STAKEHOLDER_REVIEW, ActivityType.RISK_ASSESSMENT],
}


def generate_activities(store: AssuranceStore, project_id: str, domain: str, scores: list[float]) -> None:
    """Insert assurance activities and a single overhead analysis."""
    lo, hi = _ACTIVITY_COUNTS[domain]
    count = random.randint(lo, hi)
    optimiser = AssuranceOverheadOptimiser(store=store)

    activity_types = _ACTIVITY_TYPES_BY_DOMAIN[domain]
    used_months: list[int] = sorted(random.sample(range(MONTHS), min(count, MONTHS)))

    for i, month_idx in enumerate(used_months):
        d = month_date(month_idx)
        atype = activity_types[i % len(activity_types)]
        before = scores[max(0, month_idx - 1)] if month_idx > 0 else scores[0]
        after = scores[month_idx]

        # Chaotic: high effort, low findings per hour
        if domain == "CHAOTIC":
            effort = round(random.uniform(20.0, 40.0), 1)
            participants = random.randint(4, 8)
            findings = random.randint(0, 2)
        elif domain == "COMPLEX":
            effort = round(random.uniform(10.0, 24.0), 1)
            participants = random.randint(3, 6)
            findings = random.randint(1, 5)
        elif domain == "COMPLICATED":
            effort = round(random.uniform(6.0, 16.0), 1)
            participants = random.randint(2, 4)
            findings = random.randint(1, 4)
        else:  # CLEAR
            effort = round(random.uniform(4.0, 10.0), 1)
            participants = random.randint(1, 3)
            findings = random.randint(0, 2)

        artefacts = [f"artefact-{project_id.lower()}-{random.randint(1, 6)}" for _ in range(random.randint(1, 3))]
        activity = AssuranceActivity(
            project_id=project_id,
            activity_type=atype,
            description=f"{atype.value.replace('_', ' ').title()} — {PROJECT_REGISTRY[project_id]['name']}",
            date=d,
            effort_hours=effort,
            participants=participants,
            artefacts_reviewed=artefacts,
            findings_count=findings,
            confidence_before=before,
            confidence_after=after,
        )
        optimiser.log_activity(activity)

    # Generate overhead analysis (also persists to store)
    optimiser.analyse(project_id)


# ---------------------------------------------------------------------------
# P9 — Workflow executions
# ---------------------------------------------------------------------------

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


def generate_workflow_executions(store: AssuranceStore, project_id: str, domain: str) -> None:
    """Insert 2–4 workflow executions using the workflow engine directly."""
    engine = AssuranceWorkflowEngine(store=store)
    health_pool = _HEALTH_BY_DOMAIN[domain]
    n_workflows = random.randint(2, 4)
    months_used = sorted(random.sample(range(1, 12), n_workflows))

    for i, month_idx in enumerate(months_used):
        wf_type = _WORKFLOW_TYPES[i % len(_WORKFLOW_TYPES)]
        d = month_date(month_idx)

        try:
            result = engine.execute(project_id=project_id, workflow_type=wf_type)
        except Exception:
            # Fall back to direct insert if engine execution fails (no artefact data)
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
# P10 — Domain classifications
# ---------------------------------------------------------------------------

_CLASSIFIER_INPUTS: dict[str, ClassificationInput] = {
    "PROJ-001": ClassificationInput(project_id="PROJ-001", technical_complexity=0.20, stakeholder_complexity=0.15, requirement_clarity=0.85, delivery_track_record=0.90, organisational_change=0.10, regulatory_exposure=0.25, dependency_count=0.15),
    "PROJ-002": ClassificationInput(project_id="PROJ-002", technical_complexity=0.10, stakeholder_complexity=0.20, requirement_clarity=0.80, delivery_track_record=0.85, organisational_change=0.15, regulatory_exposure=0.20, dependency_count=0.10),
    "PROJ-003": ClassificationInput(project_id="PROJ-003", technical_complexity=0.20, stakeholder_complexity=0.10, requirement_clarity=0.85, delivery_track_record=0.90, organisational_change=0.10, regulatory_exposure=0.15, dependency_count=0.20),
    "PROJ-004": ClassificationInput(project_id="PROJ-004", technical_complexity=0.50, stakeholder_complexity=0.40, requirement_clarity=0.60, delivery_track_record=0.65, organisational_change=0.45, regulatory_exposure=0.35, dependency_count=0.45),
    "PROJ-005": ClassificationInput(project_id="PROJ-005", technical_complexity=0.40, stakeholder_complexity=0.35, requirement_clarity=0.65, delivery_track_record=0.70, organisational_change=0.30, regulatory_exposure=0.30, dependency_count=0.35),
    "PROJ-006": ClassificationInput(project_id="PROJ-006", technical_complexity=0.55, stakeholder_complexity=0.50, requirement_clarity=0.55, delivery_track_record=0.60, organisational_change=0.40, regulatory_exposure=0.50, dependency_count=0.60),
    "PROJ-007": ClassificationInput(project_id="PROJ-007", technical_complexity=0.40, stakeholder_complexity=0.45, requirement_clarity=0.60, delivery_track_record=0.65, organisational_change=0.35, regulatory_exposure=0.30, dependency_count=0.30),
    "PROJ-008": ClassificationInput(project_id="PROJ-008", technical_complexity=0.50, stakeholder_complexity=0.40, requirement_clarity=0.60, delivery_track_record=0.70, organisational_change=0.40, regulatory_exposure=0.45, dependency_count=0.50),
    "PROJ-009": ClassificationInput(project_id="PROJ-009", technical_complexity=0.65, stakeholder_complexity=0.80, requirement_clarity=0.35, delivery_track_record=0.45, organisational_change=0.70, regulatory_exposure=0.60, dependency_count=0.65),
    "PROJ-010": ClassificationInput(project_id="PROJ-010", technical_complexity=0.70, stakeholder_complexity=0.60, requirement_clarity=0.40, delivery_track_record=0.50, organisational_change=0.65, regulatory_exposure=0.70, dependency_count=0.80),
    "PROJ-011": ClassificationInput(project_id="PROJ-011", technical_complexity=0.55, stakeholder_complexity=0.65, requirement_clarity=0.30, delivery_track_record=0.55, organisational_change=0.60, regulatory_exposure=0.75, dependency_count=0.55),
    "PROJ-012": ClassificationInput(project_id="PROJ-012", technical_complexity=0.75, stakeholder_complexity=0.55, requirement_clarity=0.45, delivery_track_record=0.55, organisational_change=0.60, regulatory_exposure=0.80, dependency_count=0.65),
    "PROJ-013": ClassificationInput(project_id="PROJ-013", technical_complexity=0.65, stakeholder_complexity=0.75, requirement_clarity=0.35, delivery_track_record=0.45, organisational_change=0.80, regulatory_exposure=0.70, dependency_count=0.70),
    "PROJ-014": ClassificationInput(project_id="PROJ-014", technical_complexity=0.80, stakeholder_complexity=0.90, requirement_clarity=0.20, delivery_track_record=0.25, organisational_change=0.90, regulatory_exposure=0.85, dependency_count=0.75),
    "PROJ-015": ClassificationInput(project_id="PROJ-015", technical_complexity=0.90, stakeholder_complexity=0.70, requirement_clarity=0.20, delivery_track_record=0.30, organisational_change=0.75, regulatory_exposure=0.85, dependency_count=0.60),
}


def generate_domain_classifications(store: AssuranceStore, project_id: str) -> None:
    """Insert two domain classifications: start and month 6."""
    clf = ProjectDomainClassifier(store=store)
    inp = _CLASSIFIER_INPUTS[project_id]

    # Classification 1: project start
    clf.classify(inp)

    # Classification 2: month 6 (reclassify from store signals)
    clf.reclassify_from_store(project_id)


# ---------------------------------------------------------------------------
# Artefact data (supplementary JSON)
# ---------------------------------------------------------------------------

_ARTEFACT_TEMPLATES: dict[str, list[tuple[str, str]]] = {
    "CLEAR": [
        ("business-case-v2", "business_case"),
        ("risk-register-v4", "risk_register"),
        ("benefits-realisation-plan-v3", "benefits_plan"),
        ("project-initiation-document-v2", "pid"),
    ],
    "COMPLICATED": [
        ("business-case-v2", "business_case"),
        ("risk-register-v3", "risk_register"),
        ("benefits-realisation-plan-v2", "benefits_plan"),
        ("project-initiation-document-v1", "pid"),
        ("architecture-decision-record-v2", "adr"),
    ],
    "COMPLEX": [
        ("business-case-v1", "business_case"),
        ("risk-register-v2", "risk_register"),
        ("benefits-realisation-plan-v1", "benefits_plan"),
        ("project-initiation-document-v1", "pid"),
        ("architecture-decision-record-v1", "adr"),
        ("dependency-map-v1", "dependency_map"),
    ],
    "CHAOTIC": [
        ("business-case-v1", "business_case"),
        ("risk-register-v1", "risk_register"),
        ("benefits-realisation-plan-v1", "benefits_plan"),
        ("project-initiation-document-v1", "pid"),
        ("architecture-decision-record-v1", "adr"),
        ("dependency-map-v1", "dependency_map"),
        ("recovery-plan-v1", "recovery_plan"),
    ],
}


def _last_modified(domain: str, i: int, n: int) -> str:
    """Return a plausible last_modified date for artefact i of n."""
    today = date(2026, 3, 29)
    if domain == "CLEAR":
        days_ago = random.randint(5, 30)
    elif domain == "COMPLICATED":
        # 1–2 slightly stale
        days_ago = random.randint(90, 150) if i >= n - 2 else random.randint(10, 45)
    elif domain == "COMPLEX":
        # 2–3 stale, 1 anomalously fresh
        if i == 0:
            days_ago = random.randint(3, 7)  # anomalously fresh
        elif i >= n - 3:
            days_ago = random.randint(120, 200)  # stale
        else:
            days_ago = random.randint(30, 60)
    else:  # CHAOTIC
        # Most stale, some anomalously fresh before gate
        if i in (0, 1):
            days_ago = random.randint(2, 5)  # anomalously fresh right before gate
        else:
            days_ago = random.randint(150, 365)  # very stale
    return (today - timedelta(days=days_ago)).isoformat()


def build_artefacts() -> dict[str, list[dict[str, str]]]:
    """Build a PROJECT_ARTEFACTS dict for all 15 projects."""
    artefacts: dict[str, list[dict[str, str]]] = {}
    for pid, meta in PROJECT_REGISTRY.items():
        domain = meta["domain"]
        templates = _ARTEFACT_TEMPLATES[domain]
        artefacts[pid] = [
            {
                "id": f"{pid.lower()}-{aid}",
                "type": atype,
                "last_modified": _last_modified(domain, i, len(templates)),
            }
            for i, (aid, atype) in enumerate(templates)
        ]
    return artefacts


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


def verify(db_path: Path) -> None:
    """Print record counts for all 10 tables."""
    import sqlite3

    size_mb = db_path.stat().st_size / (1024 * 1024)
    conn = sqlite3.connect(str(db_path))
    tables = [
        "confidence_scores",
        "recommendations",
        "divergence_snapshots",
        "review_schedule_recommendations",
        "override_decisions",
        "lessons_learned",
        "assurance_activities",
        "overhead_analyses",
        "workflow_executions",
        "domain_classifications",
    ]

    print("\n=== Synthetic Data Summary ===")
    print(f"Database: {db_path} ({size_mb:.1f} MB)\n")

    domain_counts = {d: sum(1 for m in PROJECT_REGISTRY.values() if m["domain"] == d) for d in ["CLEAR", "COMPLICATED", "COMPLEX", "CHAOTIC"]}
    print(f"Projects: {len(PROJECT_REGISTRY)}")
    print(f"  CLEAR: {domain_counts['CLEAR']}  |  COMPLICATED: {domain_counts['COMPLICATED']}  |  COMPLEX: {domain_counts['COMPLEX']}  |  CHAOTIC: {domain_counts['CHAOTIC']}\n")

    print("Tables:")
    for tbl in tables:
        count = conn.execute(f"SELECT COUNT(*) FROM {tbl}").fetchone()[0]
        print(f"  {tbl:<45} {count} records")

    print("\nHealth distribution (from latest workflow per project):")
    health_counts: dict[str, int] = {"HEALTHY": 0, "ATTENTION_NEEDED": 0, "AT_RISK": 0, "CRITICAL": 0}
    for pid in PROJECT_REGISTRY:
        row = conn.execute(
            "SELECT health FROM workflow_executions WHERE project_id = ? ORDER BY started_at DESC LIMIT 1",
            (pid,),
        ).fetchone()
        if row:
            h = row[0]
            health_counts[h] = health_counts.get(h, 0) + 1

    print("  " + "  |  ".join(f"{k}: {v}" for k, v in health_counts.items()))
    conn.close()


# ---------------------------------------------------------------------------
# Main generation loop
# ---------------------------------------------------------------------------


def generate(output: Path) -> None:
    """Generate the full synthetic dataset."""
    random.seed(42)  # re-seed in case called programmatically

    store = AssuranceStore(db_path=output)

    for project_id, meta in PROJECT_REGISTRY.items():
        domain: str = meta["domain"]
        print(f"  [{project_id}] {meta['name']} ({domain})")

        scores = generate_confidence_scores(store, project_id, domain)
        generate_recommendations(store, project_id, domain)
        generate_divergence_snapshots(store, project_id, domain)
        generate_schedule_recommendations(store, project_id, domain)
        generate_overrides(store, project_id, domain)
        generate_activities(store, project_id, domain, scores)
        generate_workflow_executions(store, project_id, domain)
        generate_domain_classifications(store, project_id)

    # P7: portfolio-wide lessons (inserted once, not per project)
    print("  [portfolio] Ingesting lessons learned corpus …")
    generate_lessons(store)

    # Export supplementary JSON files
    out_dir = output.parent
    artefacts = build_artefacts()
    artefacts_path = out_dir / "demo_artefacts.json"
    with open(artefacts_path, "w", encoding="utf-8") as f:
        json.dump(artefacts, f, indent=2)

    registry_path = out_dir / "demo_registry.json"
    with open(registry_path, "w", encoding="utf-8") as f:
        json.dump(PROJECT_REGISTRY, f, indent=2)

    print(f"\nDatabase:       {output}")
    print(f"Artefacts JSON: {artefacts_path}")
    print(f"Registry JSON:  {registry_path}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    """Entry point."""
    parser = argparse.ArgumentParser(
        description="Generate synthetic PDA assurance data for demo and development."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("demo_store.db"),
        help="Path to the output SQLite file (default: demo_store.db in cwd).",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Print table record counts after generation.",
    )
    args = parser.parse_args()

    output: Path = args.output.resolve()
    print(f"Generating synthetic data → {output}")
    print(f"15 projects  |  12 months  |  10 tables\n")

    generate(output)

    if args.verify:
        verify(output)


if __name__ == "__main__":
    main()
