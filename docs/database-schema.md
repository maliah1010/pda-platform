# PDA Platform — Database Schema Reference

The PDA Platform stores all assurance data in a local SQLite database at
`~/.pm_data_tools/store.db`.  All tables use `CREATE TABLE IF NOT EXISTS` so
any subset of features can initialise the store safely.

This document describes every table, its columns, and the feature that owns it.

---

## Overview

| Table | Feature | Purpose |
|-------|---------|---------|
| `confidence_scores` | P2 — Longitudinal Compliance Tracker | NISTA validation score history |
| `recommendations` | P3 — Cross-Cycle Finding Analyzer | Extracted review actions and their lifecycle |
| `divergence_snapshots` | P4 — Confidence Divergence Monitor | AI extraction sample divergence history |
| `review_schedule_recommendations` | P5 — Adaptive Review Scheduler | Scheduling recommendations and signals |
| `override_decisions` | P6 — Override Decision Logger | Governance override decision log |
| `lessons_learned` | P7 — Lessons Learned Knowledge Engine | Structured lessons corpus |
| `assurance_activities` | P8 — Assurance Overhead Optimiser | Effort and activity tracking |
| `overhead_analyses` | P8 — Assurance Overhead Optimiser | Persisted overhead analysis results |
| `workflow_executions` | P9 — Assurance Workflow Engine | Workflow execution results |
| `domain_classifications` | P10 — Project Domain Classifier | Domain classification results |

---

## `confidence_scores` (P2)

Stores one row per NISTA validation run.  Re-running the same `run_id` for
a project updates the existing row (`INSERT OR REPLACE`).

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `id` | INTEGER | No | Auto-increment primary key |
| `project_id` | TEXT | No | Project identifier (e.g. `PROJ-001`) |
| `run_id` | TEXT | No | Unique identifier for this validation run |
| `timestamp` | TEXT | No | ISO-8601 timestamp of the validation run |
| `score` | REAL | No | Overall NISTA compliance score (0–100) |
| `dimension_scores` | TEXT | No | JSON object of per-dimension scores (e.g. `{"required": 85.0, "recommended": 60.0}`) |

**Unique constraint**: `(project_id, run_id)`

**Typical query**: All scores for a project ordered by timestamp, used to compute trend direction.

---

## `recommendations` (P3)

Stores extracted review actions with full lifecycle tracking.  Each action
has a UUID primary key.  Re-submitting the same `id` updates the row.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `id` | TEXT | No | UUID primary key |
| `project_id` | TEXT | No | Project identifier |
| `text` | TEXT | No | Full text of the recommendation |
| `category` | TEXT | No | Category label (e.g. `GOVERNANCE`, `TECHNICAL`) |
| `source_review_id` | TEXT | No | Identifier of the review cycle this action came from |
| `review_date` | TEXT | No | ISO-8601 date of the source review |
| `status` | TEXT | No | Lifecycle status: `OPEN`, `IN_PROGRESS`, `CLOSED`, `RECURRING` |
| `owner` | TEXT | Yes | Assigned owner (optional) |
| `recurrence_of` | TEXT | Yes | ID of the earlier action this recurs from (null if not recurring) |
| `confidence` | REAL | No | Extraction confidence score (0–1) |
| `created_at` | TEXT | No | ISO-8601 timestamp of record creation |

---

## `divergence_snapshots` (P4)

One row per confidence divergence check.  Re-submitting the same `id` updates
the row.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `id` | TEXT | No | UUID primary key |
| `project_id` | TEXT | No | Project identifier |
| `review_id` | TEXT | No | Review cycle identifier |
| `confidence_score` | REAL | No | Overall consensus confidence score (0–1) |
| `sample_scores` | TEXT | No | JSON array of individual per-sample scores |
| `signal_type` | TEXT | No | Signal classification: `STABLE`, `HIGH_DIVERGENCE`, `LOW_CONSENSUS`, `DEGRADING_CONFIDENCE` |
| `timestamp` | TEXT | No | ISO-8601 timestamp of the check |

---

## `review_schedule_recommendations` (P5)

One row per scheduling recommendation.  Rows are append-only (no upsert) so
the full recommendation history is preserved.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `id` | INTEGER | No | Auto-increment primary key |
| `project_id` | TEXT | No | Project identifier |
| `timestamp` | TEXT | No | ISO-8601 timestamp of the recommendation |
| `urgency` | TEXT | No | Urgency level: `IMMEDIATE`, `EXPEDITED`, `STANDARD`, `DEFERRED` |
| `recommended_date` | TEXT | No | ISO-8601 date of the recommended next review |
| `composite_score` | REAL | No | Weighted composite severity score (0–1) driving the recommendation |
| `signals_json` | TEXT | No | JSON array of contributing `SchedulerSignal` objects |
| `rationale` | TEXT | No | Plain-language explanation of the recommendation |

---

## `override_decisions` (P6)

One row per governance override decision.  Re-submitting the same `id`
updates the row.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `id` | TEXT | No | UUID primary key |
| `project_id` | TEXT | No | Project identifier |
| `override_type` | TEXT | No | Type: `GATE_PROGRESSION`, `RECOMMENDATION_DISMISSED`, `RAG_OVERRIDE`, `RISK_ACCEPTANCE`, `SCHEDULE_OVERRIDE` |
| `decision_date` | TEXT | No | ISO-8601 date of the decision |
| `authoriser` | TEXT | No | Name and role of the person who authorised the override |
| `rationale` | TEXT | No | Reason given for the override |
| `overridden_finding_id` | TEXT | Yes | ID of the specific finding that was overridden (optional) |
| `overridden_value` | TEXT | Yes | The original value that was overridden (optional) |
| `override_value` | TEXT | Yes | The value substituted by the override (optional) |
| `conditions_json` | TEXT | No | JSON array of conditions attached to the override |
| `evidence_refs_json` | TEXT | No | JSON array of evidence references cited |
| `outcome` | TEXT | No | Current outcome: `PENDING`, `NO_IMPACT`, `MINOR_IMPACT`, `SIGNIFICANT_IMPACT`, `PREVENTED_BENEFIT` |
| `outcome_date` | TEXT | Yes | ISO-8601 date when the outcome was observed (null until known) |
| `outcome_notes` | TEXT | Yes | Free-text notes about the outcome (null until recorded) |
| `created_at` | TEXT | No | ISO-8601 timestamp of record creation |

---

## `lessons_learned` (P7)

One row per lesson record.  Re-submitting the same `id` updates the row.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `id` | TEXT | No | UUID primary key |
| `project_id` | TEXT | No | Project identifier the lesson originated from |
| `title` | TEXT | No | Short title summarising the lesson |
| `description` | TEXT | No | Full description of the lesson |
| `category` | TEXT | No | Domain: `GOVERNANCE`, `TECHNICAL`, `COMMERCIAL`, `STAKEHOLDER`, `RESOURCE`, `REQUIREMENTS`, `ESTIMATION`, `RISK_MANAGEMENT`, `BENEFITS_REALISATION`, `OTHER` |
| `sentiment` | TEXT | No | Valence: `POSITIVE`, `NEGATIVE`, `NEUTRAL` |
| `project_type` | TEXT | Yes | Type of project (e.g. `ICT`, `Infrastructure`) |
| `project_phase` | TEXT | Yes | Phase during which the lesson arose (e.g. `Initiation`, `Delivery`) |
| `department` | TEXT | Yes | Owning department or organisation |
| `tags_json` | TEXT | No | JSON array of searchable tags |
| `date_recorded` | TEXT | No | ISO-8601 date the lesson was recorded |
| `recorded_by` | TEXT | Yes | Name or role of person who recorded the lesson |
| `impact_description` | TEXT | Yes | Description of the impact this lesson had |
| `created_at` | TEXT | No | ISO-8601 timestamp of record creation |

---

## `assurance_activities` (P8)

One row per assurance activity.  Re-submitting the same `id` updates the row.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `id` | TEXT | No | UUID primary key |
| `project_id` | TEXT | No | Project identifier |
| `activity_type` | TEXT | No | Type: `GATE_REVIEW`, `DOCUMENT_REVIEW`, `COMPLIANCE_CHECK`, `RISK_ASSESSMENT`, `STAKEHOLDER_REVIEW`, `AUDIT`, `OTHER` |
| `description` | TEXT | No | Description of the activity |
| `date` | TEXT | No | ISO-8601 date of the activity |
| `effort_hours` | REAL | No | Total person-hours invested |
| `participants` | INTEGER | No | Number of participants |
| `artefacts_reviewed` | TEXT | No | JSON array of artefact identifiers reviewed |
| `findings_count` | INTEGER | No | Number of findings produced |
| `confidence_before` | REAL | Yes | Project confidence score before this activity (null if not recorded) |
| `confidence_after` | REAL | Yes | Project confidence score after this activity (null if not recorded) |
| `created_at` | TEXT | No | ISO-8601 timestamp of record creation |

---

## `overhead_analyses` (P8)

One row per overhead analysis run.  Rows are append-only so the full analysis
history is preserved.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `id` | INTEGER | No | Auto-increment primary key |
| `project_id` | TEXT | No | Project identifier |
| `timestamp` | TEXT | No | ISO-8601 timestamp of the analysis |
| `analysis_json` | TEXT | No | Full `OverheadAnalysis` object serialised as JSON |

---

## `workflow_executions` (P9)

One row per workflow execution.  Re-submitting the same `id` updates the row.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `id` | TEXT | No | UUID primary key |
| `project_id` | TEXT | No | Project identifier |
| `workflow_type` | TEXT | No | Workflow plan: `FULL_ASSURANCE`, `COMPLIANCE_FOCUS`, `CURRENCY_FOCUS`, `TREND_ANALYSIS`, `RISK_ASSESSMENT` |
| `started_at` | TEXT | No | ISO-8601 timestamp when execution began |
| `completed_at` | TEXT | No | ISO-8601 timestamp when execution finished |
| `duration_ms` | REAL | No | Total execution duration in milliseconds |
| `health` | TEXT | No | Health classification: `HEALTHY`, `ATTENTION_NEEDED`, `AT_RISK`, `CRITICAL` |
| `result_json` | TEXT | No | Full `WorkflowResult` object serialised as JSON |

---

## `domain_classifications` (P10)

One row per classification run.  Re-submitting the same `id` updates the row.

| Column | Type | Nullable | Description |
|--------|------|----------|-------------|
| `id` | TEXT | No | UUID primary key |
| `project_id` | TEXT | No | Project identifier |
| `domain` | TEXT | No | Complexity domain: `CLEAR`, `COMPLICATED`, `COMPLEX`, `CHAOTIC` |
| `composite_score` | REAL | No | Final weighted composite score (0–1) |
| `classified_at` | TEXT | No | ISO-8601 timestamp of the classification |
| `result_json` | TEXT | No | Full `ClassificationResult` object serialised as JSON |

---

## Database location and configuration

The default database path is `~/.pm_data_tools/store.db`.  To use a
custom location, pass `db_path` when constructing `AssuranceStore`:

```python
from pathlib import Path
from pm_data_tools.db.store import AssuranceStore

store = AssuranceStore(db_path=Path("/data/my_project/assurance.db"))
```

The parent directory is created automatically if it does not exist.

---

## Data retention

The platform does not currently enforce automatic data retention or purging.
All records accumulate indefinitely.  For long-running programmes, consider
archiving older records to a separate database file if the store grows large.

---

## Querying the store directly

All data is stored in a standard SQLite database and can be queried with any
SQLite client.  For example, using the `sqlite3` command-line tool:

```bash
sqlite3 ~/.pm_data_tools/store.db

# List all projects with compliance score history
SELECT DISTINCT project_id FROM confidence_scores;

# Most recent compliance score per project
SELECT project_id, score, timestamp
FROM confidence_scores
GROUP BY project_id
HAVING timestamp = MAX(timestamp);

# All open review actions
SELECT project_id, text, review_date
FROM recommendations
WHERE status = 'OPEN'
ORDER BY review_date ASC;

# Override decisions with adverse outcomes
SELECT project_id, override_type, decision_date, outcome
FROM override_decisions
WHERE outcome IN ('MINOR_IMPACT', 'SIGNIFICANT_IMPACT')
ORDER BY decision_date DESC;
```

---

**Last Updated**: March 2026
**Maintained by**: PDA Platform Contributors
