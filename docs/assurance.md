# Assurance Module — Developer Reference

This document describes the six assurance features in the PDA Platform:

- **P1 — Artefact Currency Validator**: Detects stale or anomalously refreshed
  evidence artefacts by inspecting document metadata timestamps against
  validation-gate deadlines.
- **P2 — Longitudinal Compliance Tracker**: Persists NISTA compliance scores
  over time and surfaces trend direction and threshold breaches.
- **P3 — Cross-Cycle Finding Analyzer**: Extracts review actions from project
  review text, deduplicates within a review cycle, detects recurrences across
  cycles, and persists the full lifecycle.
- **P4 — Confidence Divergence Monitor**: Detects when AI extraction samples
  diverge significantly, consensus scores are low, or confidence is declining
  across review cycles.
- **P5 — Adaptive Review Scheduler**: Analyses P1–P4 outputs to recommend
  optimal review timing based on actual project signals rather than fixed
  calendar intervals.
- **P6 — Override Decision Logger**: Provides structured logging and pattern
  analysis for governance decisions that proceed against assurance advice.

---

## Architecture

```
pm_data_tools/
  db/
    store.py              # AssuranceStore — shared SQLite persistence layer
  schemas/
    nista/
      longitudinal.py     # LongitudinalComplianceTracker, ConfidenceScoreRecord,
                          # ComplianceThresholdConfig, TrendDirection
      validator.py        # NISTAValidator — extended with optional history param
  assurance/
    models.py             # ReviewAction, ReviewActionStatus, FindingAnalysisResult
    analyzer.py           # FindingAnalyzer
    recurrence.py         # RecurrenceDetector
    currency.py           # ArtefactCurrencyValidator, CurrencyConfig, CurrencyScore
    divergence.py         # DivergenceMonitor, DivergenceConfig, SignalType
    scheduler.py          # AdaptiveReviewScheduler, SchedulerConfig, ReviewUrgency
    overrides.py          # OverrideDecisionLogger, OverrideDecision, OverrideType

pm_mcp_servers/
  pm_assure/
    server.py             # MCP server: 8 tools (see MCP tool sections below)
```

All SQLite tables are created with `CREATE TABLE IF NOT EXISTS` so the store
is safe to initialise from any subset of features.

---

## Package Dependencies

| Feature | Required extras |
|---------|----------------|
| Artefact Currency Validator | none (stdlib only) |
| Longitudinal Compliance Tracker | none (SQLite is stdlib) |
| Finding Analyzer (extraction) | `agent-task-planning>=0.2.0` (already a core dep) |
| Finding Analyzer (recurrence) | `agent-task-planning[mining]` for sentence-transformers |

Install with recurrence detection enabled:

```bash
pip install pm-data-tools[assurance]
pip install "agent-task-planning[mining]"
```

---

## P1 — Artefact Currency Validator

### Purpose

Assurance gates depend on project artefacts — plans, risk registers, benefits
profiles — being current at the time of the gate.  A common failure mode is
hastily updating stale documents right before a gate review: timestamps are
refreshed but substantive content is unchanged.  The `ArtefactCurrencyValidator`
detects both genuinely outdated artefacts and last-minute compliance updates
that may not reflect real change.

### Data models

#### `CurrencyStatus`

```
CURRENT            — artefact is within the configured staleness window
OUTDATED           — artefact has not been updated within the staleness window
ANOMALOUS_UPDATE   — artefact was updated within a short window before the gate,
                     suggesting a last-minute compliance update rather than
                     genuine revision
```

#### `CurrencyScore`

```python
class CurrencyScore(BaseModel):
    artefact_id: str
    artefact_type: str             # e.g. "risk_register", "benefits_profile"
    last_modified: datetime
    gate_date: datetime
    status: CurrencyStatus
    staleness_days: int            # Days since last_modified at time of check
    anomaly_window_days: int       # Days before gate_date that triggered ANOMALOUS_UPDATE
    message: str
```

#### `CurrencyConfig`

```python
class CurrencyConfig(BaseModel):
    max_staleness_days: int = 90       # Artefacts older than this are OUTDATED
    anomaly_window_days: int = 3       # Updates this close to a gate are suspicious
```

### `ArtefactCurrencyValidator`

```python
from pm_data_tools.assurance.currency import ArtefactCurrencyValidator, CurrencyConfig

validator = ArtefactCurrencyValidator()
validator = ArtefactCurrencyValidator(
    config=CurrencyConfig(max_staleness_days=60, anomaly_window_days=2)
)
```

| Method | Description |
|--------|-------------|
| `check_artefact_currency(artefact_id, last_modified, gate_date)` | Returns a `CurrencyScore` for a single artefact. |
| `check_batch(artefacts, gate_date)` | Returns a list of `CurrencyScore` objects for multiple artefacts. |

### MCP tool: `check_artefact_currency`

```json
{
  "project_id": "PROJ-001",
  "gate_date": "2026-06-30",
  "artefacts": [
    {"id": "risk-register-v3", "type": "risk_register", "last_modified": "2025-12-01"},
    {"id": "benefits-profile-v2", "type": "benefits_profile", "last_modified": "2026-06-28"}
  ]
}
```

Returns:

```json
{
  "project_id": "PROJ-001",
  "gate_date": "2026-06-30",
  "results": [
    {
      "artefact_id": "risk-register-v3",
      "status": "OUTDATED",
      "staleness_days": 211,
      "message": "Artefact has not been updated in 211 days (threshold: 90)."
    },
    {
      "artefact_id": "benefits-profile-v2",
      "status": "ANOMALOUS_UPDATE",
      "staleness_days": 2,
      "anomaly_window_days": 2,
      "message": "Artefact was updated 2 days before the gate date, which is within the anomaly window."
    }
  ]
}
```

> **Note:** P1 implementation is planned for v0.4.0.  The data models and MCP
> tool interface above represent the intended public API.

---

## P2 — Longitudinal Compliance Tracker

### Data models

#### `ConfidenceScoreRecord`

```python
class ConfidenceScoreRecord(BaseModel):
    project_id: str
    run_id: str           # UUID4 auto-generated if not supplied
    timestamp: datetime   # UTC, auto-set if not supplied
    score: float          # 0-100; validated
    dimension_scores: dict[str, float]
```

#### `ComplianceThresholdConfig`

```python
class ComplianceThresholdConfig(BaseModel):
    drop_tolerance: float = 5.0    # Max acceptable single-run score drop
    floor: float = 60.0            # Minimum acceptable score
    stagnation_window: int = 3     # Runs examined for trend direction
```

#### `TrendDirection`

```
IMPROVING  — latest score > oldest-in-window by > drop_tolerance
STAGNATING — change within drop_tolerance (or fewer than 2 runs)
DEGRADING  — latest score < oldest-in-window by > drop_tolerance
```

#### `ThresholdBreach`

Returned by `check_thresholds()`.  Fields: `breach_type` (`"drop"` or
`"floor"`), `current_score`, `previous_score`, `threshold_value`, `message`.

### `LongitudinalComplianceTracker`

```python
from pm_data_tools.schemas.nista.longitudinal import LongitudinalComplianceTracker

tracker = LongitudinalComplianceTracker()          # uses default ~/.pm_data_tools/store.db
tracker = LongitudinalComplianceTracker(
    store=AssuranceStore(db_path=Path("/custom/path.db")),
    thresholds=ComplianceThresholdConfig(floor=70.0),
)
```

| Method | Description |
|--------|-------------|
| `record(record)` | Persist a `ConfidenceScoreRecord`. |
| `get_history(project_id)` | Return all records oldest-first. |
| `compute_trend(project_id)` | Return `TrendDirection`. |
| `check_thresholds(project_id)` | Return list of `ThresholdBreach`. |

### Integrating with `NISTAValidator`

The `validate()` signature is unchanged; persistence is a **side effect**
controlled by an optional `history` keyword argument:

```python
from pm_data_tools.schemas.nista import NISTAValidator, LongitudinalComplianceTracker

validator = NISTAValidator()
tracker = LongitudinalComplianceTracker()

result = validator.validate(
    data,
    project_id="PROJ-001",   # optional: falls back to data["project_id"]
    history=tracker,          # optional: omit to skip persistence
)
# result is identical ValidationResult regardless
```

### MCP tool: `nista_longitudinal_trend`

```json
{
  "project_id": "PROJ-001"
}
```

Returns:

```json
{
  "project_id": "PROJ-001",
  "history": [{"run_id": "...", "timestamp": "...", "score": 78.5}],
  "trend": "IMPROVING",
  "active_breaches": []
}
```

---

## P3 — Cross-Cycle Finding Analyzer

### Data models

#### `ReviewActionStatus`

```
OPEN        — newly extracted, no action
IN_PROGRESS — being addressed
CLOSED      — resolved
RECURRING   — detected as recurring from a prior cycle
```

#### `ReviewAction`

```python
class ReviewAction(BaseModel):
    id: str                        # UUID4
    text: str                      # Recommended action
    category: str                  # Maps to extraction priority (High/Medium/Low)
    source_review_id: str
    review_date: date
    status: ReviewActionStatus
    owner: Optional[str]
    recurrence_of: Optional[str]   # Prior ReviewAction id
    confidence: float              # From ConfidenceExtractor
    flagged_for_review: bool       # True if confidence < min_confidence
```

#### `FindingAnalysisResult`

```python
class FindingAnalysisResult(BaseModel):
    recommendations: list[ReviewAction]
    extraction_confidence: float
    review_level: str
    cost_usd: float
```

### `FindingAnalyzer`

Wraps `ConfidenceExtractor` from `agent-task-planning` with the
`SchemaType.RECOMMENDATION` schema.  Does not make direct API calls.

```python
from agent_planning.confidence import ConfidenceExtractor
from agent_planning.providers.anthropic import AnthropicProvider
from pm_data_tools.assurance import FindingAnalyzer, RecurrenceDetector

provider = AnthropicProvider(api_key="...")
ce = ConfidenceExtractor(provider)

analyzer = FindingAnalyzer(
    extractor=ce,
    min_confidence=0.60,           # flag below this, never reject
    recurrence_detector=RecurrenceDetector(),
)

result = await analyzer.extract(
    review_text="...",
    review_id="review-2026-Q1",
    project_id="PROJ-001",
)
```

Behaviour:

1. Calls `ConfidenceExtractor.extract()` with `SchemaType.RECOMMENDATION`.
2. Maps `ReviewActionItem.action` to `ReviewAction.text`.
3. Deduplicates by normalised (lowercased) text within the current review.
4. If a `RecurrenceDetector` is supplied, fetches prior OPEN review actions
   (excluding those from the same `review_id`) and calls
   `detect_recurrences()`.
5. Persists all review actions to the shared SQLite store.

### `RecurrenceDetector`

Uses sentence-transformer cosine similarity.  Requires
`agent-task-planning[mining]` (or `sentence-transformers` directly).

```python
from pm_data_tools.assurance import RecurrenceDetector

detector = RecurrenceDetector(
    similarity_threshold=0.85,
    model_name="all-MiniLM-L6-v2",
)
```

When `sentence-transformers` is not installed the detector returns the input
list unchanged and emits a `structlog` warning at `WARNING` level.  No
exception is raised.

### Updating review action status

```python
from pm_data_tools.db import AssuranceStore
from pm_data_tools.assurance import ReviewActionStatus

store = AssuranceStore()
store.update_recommendation_status("action-id-001", ReviewActionStatus.CLOSED.value)
```

### MCP tools

**`track_review_actions`**

```json
{
  "review_text": "...",
  "review_id": "review-2026-Q1",
  "project_id": "PROJ-001",
  "min_confidence": 0.60
}
```

Requires `ANTHROPIC_API_KEY` to be set in the server environment.

**`review_action_status`**

```json
{
  "project_id": "PROJ-001",
  "status_filter": "OPEN"
}
```

Returns the list of matching review actions with recurrence flags included.

---

## P4 — Confidence Divergence Monitor

### Purpose

AI-extracted findings gain confidence through multi-sample consensus.  When
extraction samples diverge significantly, the consensus score is low, or
confidence is declining across successive review cycles, the extracted data
may be unreliable.  The `DivergenceMonitor` detects these conditions and
produces a structured signal that downstream components (notably P5) can
consume.

### Data models

#### `SignalType`

```
STABLE                — extraction is consistent; no concern
LOW_CONSENSUS         — consensus score below threshold across samples
HIGH_DIVERGENCE       — spread between sample scores exceeds threshold
DEGRADING_CONFIDENCE  — confidence has declined across recent review cycles
```

#### `DivergenceConfig`

```python
class DivergenceConfig(BaseModel):
    divergence_threshold: float = 0.20   # Max acceptable spread between samples
    min_consensus: float = 0.70          # Minimum acceptable consensus score
    degradation_window: int = 3          # Review cycles examined for trend
```

#### `DivergenceSnapshot`

```python
class DivergenceSnapshot(BaseModel):
    snapshot_id: str          # UUID4
    project_id: str
    review_id: str
    confidence_score: float
    sample_scores: list[float]
    signal_type: SignalType
    spread: float
    timestamp: datetime
```

#### `DivergenceSignal`

```python
class DivergenceSignal(BaseModel):
    signal_type: SignalType
    project_id: str
    review_id: str
    confidence_score: float
    spread: float
    previous_confidence: float | None
    message: str
```

#### `DivergenceResult`

```python
class DivergenceResult(BaseModel):
    project_id: str
    review_id: str
    confidence_score: float
    sample_scores: list[float]
    signal: DivergenceSignal
    snapshot_id: str
```

### `DivergenceMonitor`

```python
from pm_data_tools.assurance import DivergenceMonitor, DivergenceConfig

monitor = DivergenceMonitor()
monitor = DivergenceMonitor(
    config=DivergenceConfig(divergence_threshold=0.15, min_consensus=0.75),
    store=AssuranceStore(db_path=Path("/custom/store.db")),
)
```

| Method | Description |
|--------|-------------|
| `check(project_id, review_id, confidence_score, sample_scores)` | Returns a `DivergenceResult` and persists a snapshot. |
| `get_history(project_id)` | Returns all snapshots for the project, oldest-first. |

### MCP tool: `check_confidence_divergence`

```json
{
  "project_id": "PROJ-001",
  "review_id": "review-2026-Q1",
  "confidence_score": 0.61,
  "sample_scores": [0.82, 0.55, 0.61, 0.49, 0.78]
}
```

Returns:

```json
{
  "project_id": "PROJ-001",
  "review_id": "review-2026-Q1",
  "signal_type": "HIGH_DIVERGENCE",
  "confidence_score": 0.61,
  "spread": 0.33,
  "message": "Sample spread 0.33 exceeds threshold 0.20."
}
```

---

## P5 — Adaptive Review Scheduler

### Purpose

Fixed calendar intervals cause reviews to happen either too early (before
enough has changed) or too late (after problems have escalated).  The
`AdaptiveReviewScheduler` analyses outputs from P1–P4 to recommend *when*
the next project review should happen: high-risk projects get reviewed
sooner; stable projects can safely wait longer.

### Data models

#### `ReviewUrgency`

```
IMMEDIATE   — within 7 days; multiple critical signals detected
EXPEDITED   — within 14 days; at least one significant signal
STANDARD    — normal cadence (default 42 days)
DEFERRED    — can safely wait beyond normal cadence (default 90 days)
```

#### `SchedulerSignal`

```python
class SchedulerSignal(BaseModel):
    source: str        # "P1", "P2", "P3", or "P4"
    signal_name: str   # e.g. "outdated_artefacts", "compliance_trend"
    severity: float    # 0.0 (benign) to 1.0 (critical)
    detail: str        # Human-readable explanation
```

#### `SchedulerConfig`

```python
class SchedulerConfig(BaseModel):
    immediate_threshold: float = 0.80      # Composite score ≥ this → IMMEDIATE
    expedited_threshold: float = 0.50      # ≥ this → EXPEDITED
    deferred_threshold: float = 0.15       # ≤ this → DEFERRED
    source_weights: dict[str, float] = {   # Renormalised at scoring time
        "P1": 0.20, "P2": 0.30, "P3": 0.25, "P4": 0.25
    }
    min_days_between_reviews: int = 7
    max_days_between_reviews: int = 90
    standard_cadence_days: int = 42
```

#### `SchedulerRecommendation`

```python
class SchedulerRecommendation(BaseModel):
    project_id: str
    timestamp: datetime
    urgency: ReviewUrgency
    recommended_date: date
    days_until_review: int
    composite_score: float
    signals: list[SchedulerSignal]
    rationale: str
```

### `AdaptiveReviewScheduler`

```python
from pm_data_tools.assurance import AdaptiveReviewScheduler, SchedulerConfig

scheduler = AdaptiveReviewScheduler()
scheduler = AdaptiveReviewScheduler(
    config=SchedulerConfig(standard_cadence_days=30),
    store=AssuranceStore(db_path=Path("/custom/store.db")),
)
```

All signal inputs are optional; the scheduler works with whatever P1–P4
data is available.

| Method | Description |
|--------|-------------|
| `recommend(project_id, last_review_date, currency_scores, trend, breaches, open_actions, total_actions, recurring_actions, divergence_result)` | Returns a `SchedulerRecommendation` and persists it when a store is configured. |

**Signal severity mapping:**

| Source | Signal | Severity |
|--------|--------|----------|
| P1 | CURRENT artefact | 0.0 per artefact |
| P1 | ANOMALOUS_UPDATE artefact | 0.5 per artefact |
| P1 | OUTDATED artefact | 1.0 per artefact |
| P2 | IMPROVING trend | 0.0 |
| P2 | STAGNATING trend | 0.3 |
| P2 | DEGRADING trend | 0.7 |
| P2 | Floor breach (any trend) | 1.0 (overrides) |
| P2 | Drop breach | +0.3 boost |
| P3 | Open actions | `open/total + recurring×0.1`, capped 1.0 |
| P4 | STABLE | 0.0 |
| P4 | DEGRADING_CONFIDENCE | 0.5 |
| P4 | LOW_CONSENSUS | 0.6 |
| P4 | HIGH_DIVERGENCE | 0.8 |

### MCP tool: `recommend_review_schedule`

```json
{
  "project_id": "PROJ-001",
  "last_review_date": "2026-01-15",
  "open_actions": 4,
  "total_actions": 6,
  "recurring_actions": 1,
  "trend": "DEGRADING",
  "breaches": []
}
```

Returns:

```json
{
  "project_id": "PROJ-001",
  "urgency": "EXPEDITED",
  "recommended_date": "2026-02-12",
  "days_until_review": 14,
  "composite_score": 0.62,
  "rationale": "2 signal(s) contributed ... Top signal: open_review_actions (source P3, severity 0.72).",
  "signals": [
    {"source": "P2", "signal_name": "compliance_trend", "severity": 0.70, "detail": "..."},
    {"source": "P3", "signal_name": "open_review_actions", "severity": 0.72, "detail": "..."}
  ]
}
```

---

## P6 — Override Decision Logger

### Purpose

Governance boards sometimes proceed against assurance advice — continuing
past a failed gate, dismissing a recurring recommendation, or overriding a
risk rating.  These decisions are rarely captured in a structured way,
making it impossible to analyse patterns or track whether overrides led to
predicted consequences.  The `OverrideDecisionLogger` provides structured
logging and post-override outcome tracking.

### Data models

#### `OverrideType`

```
GATE_PROGRESSION          — proceeded past a failed or red-rated gate
RECOMMENDATION_DISMISSED  — dismissed an assurance recommendation
RAG_OVERRIDE              — changed a RAG rating against assessor advice
RISK_ACCEPTANCE           — accepted a risk flagged for mitigation
SCHEDULE_OVERRIDE         — overrode a recommended review schedule
```

#### `OverrideOutcome`

```
PENDING              — outcome not yet determined
NO_IMPACT            — override had no measurable negative effect
MINOR_IMPACT         — some negative effect but manageable
SIGNIFICANT_IMPACT   — predicted consequences materialised
ESCALATED            — worse than predicted; escalation was required
```

#### `OverrideDecision`

```python
class OverrideDecision(BaseModel):
    id: str                              # UUID4
    project_id: str
    override_type: OverrideType
    decision_date: date
    authoriser: str
    rationale: str
    overridden_finding_id: str | None    # Link to ReviewAction id, gate ref, etc.
    overridden_value: str | None         # e.g. "RED"
    override_value: str | None           # e.g. "Proceed with conditions"
    conditions: list[str]
    evidence_refs: list[str]
    outcome: OverrideOutcome             # Defaults to PENDING
    outcome_date: date | None
    outcome_notes: str | None
```

#### `OverridePatternSummary`

```python
class OverridePatternSummary(BaseModel):
    project_id: str
    total_overrides: int
    by_type: dict[str, int]
    by_outcome: dict[str, int]
    pending_outcomes: int
    impact_rate: float        # impactful / resolved (0–1); 0 if none resolved
    top_authorisers: list[dict]  # [{"authoriser": str, "count": int}]
    message: str
```

`impact_rate` counts overrides with `MINOR_IMPACT`, `SIGNIFICANT_IMPACT`,
or `ESCALATED` outcomes as a proportion of all non-`PENDING` overrides.

### `OverrideDecisionLogger`

```python
from pm_data_tools.assurance import OverrideDecisionLogger, OverrideDecision, OverrideType

logger_obj = OverrideDecisionLogger()
logger_obj = OverrideDecisionLogger(
    store=AssuranceStore(db_path=Path("/custom/store.db"))
)
```

| Method | Description |
|--------|-------------|
| `log_override(decision)` | Persist an `OverrideDecision`. Returns the same object. |
| `record_outcome(override_id, outcome, outcome_date, outcome_notes)` | Update the outcome of a previously logged decision. |
| `get_overrides(project_id, override_type, outcome)` | Retrieve decisions, optionally filtered by type and/or outcome. |
| `analyse_patterns(project_id)` | Compute an `OverridePatternSummary` for the project. |

### MCP tool: `log_override_decision`

```json
{
  "project_id": "PROJ-001",
  "override_type": "GATE_PROGRESSION",
  "decision_date": "2026-03-15",
  "authoriser": "Jane Smith (SRO)",
  "rationale": "Critical business deadline requires progression.",
  "overridden_value": "RED",
  "override_value": "Proceed with conditions",
  "conditions": ["Complete risk register by 2026-04-01"],
  "evidence_refs": ["board-paper-2026-03-15"]
}
```

Returns:

```json
{
  "id": "a3c8f1e2-...",
  "project_id": "PROJ-001",
  "override_type": "GATE_PROGRESSION",
  "decision_date": "2026-03-15",
  "outcome": "PENDING"
}
```

### MCP tool: `analyse_override_patterns`

```json
{
  "project_id": "PROJ-001"
}
```

Returns:

```json
{
  "project_id": "PROJ-001",
  "total_overrides": 5,
  "by_type": {"GATE_PROGRESSION": 3, "RAG_OVERRIDE": 2},
  "by_outcome": {"PENDING": 2, "NO_IMPACT": 1, "MINOR_IMPACT": 2},
  "pending_outcomes": 2,
  "impact_rate": 0.67,
  "top_authorisers": [{"authoriser": "Jane Smith (SRO)", "count": 3}],
  "message": "5 override(s) recorded ... Impact rate: 67% (2/3 resolved). 2 outcome(s) still pending."
}
```

---

## SQLite Store

The `AssuranceStore` manages all persistence.  The default database path is
`~/.pm_data_tools/store.db`.

```python
from pm_data_tools.db import AssuranceStore
from pathlib import Path

store = AssuranceStore(db_path=Path("/project/data/store.db"))
```

Tables are created on first use with `CREATE TABLE IF NOT EXISTS`.  All
features share one store instance; initialising from any subset of features
is safe.

| Table | Feature |
|-------|---------|
| `confidence_scores` | P2 — Longitudinal Compliance Tracker |
| `review_actions` | P3 — Cross-Cycle Finding Analyzer |
| `divergence_snapshots` | P4 — Confidence Divergence Monitor |
| `review_schedule_recommendations` | P5 — Adaptive Review Scheduler |
| `override_decisions` | P6 — Override Decision Logger |

---

## Testing

Tests live in `packages/pm-data-tools/tests/test_assurance/`.

```
test_assurance/
  conftest.py                        # Shared fixtures, mock ConfidenceExtractor
  test_currency.py                   # 14 tests for P1
  test_longitudinal_compliance.py    # 12 tests for P2
  test_finding_analyzer.py           # 11 tests for P3
  test_divergence.py                 # 17 tests for P4
  test_scheduler.py                  # 18 tests for P5
  test_overrides.py                  # 15 tests for P6
```

Run:

```bash
cd packages/pm-data-tools
pytest tests/test_assurance/ -v
```

All tests use a temporary SQLite file via the `tmp_path` pytest fixture.
`ConfidenceExtractor` is mocked with `unittest.mock.AsyncMock` — no live API
calls are made.

---

## Backward Compatibility

The following aliases are provided for codebases that imported the previous
names.  They will be removed in v0.5.0.

| Deprecated name | Current name | Location |
|---|---|---|
| `NISTAScoreHistory` | `LongitudinalComplianceTracker` | `schemas.nista.longitudinal` |
| `NISTAThresholdConfig` | `ComplianceThresholdConfig` | `schemas.nista.longitudinal` |
| `RecommendationExtractor` | `FindingAnalyzer` | `assurance` |
| `Recommendation` | `ReviewAction` | `assurance.models` |
| `RecommendationStatus` | `ReviewActionStatus` | `assurance.models` |
| `RecommendationExtractionResult` | `FindingAnalysisResult` | `assurance.models` |
| `nista_score_trend` (MCP) | `nista_longitudinal_trend` | `pm_assure` server |
| `track_recommendations` (MCP) | `track_review_actions` | `pm_assure` server |
| `recommendation_status` (MCP) | `review_action_status` | `pm_assure` server |

---

## Logging

All modules use `structlog`.  Key events:

| Logger event | Level | Module |
|---|---|---|
| `assurance_store_ready` | DEBUG | `db.store` |
| `confidence_score_persisted` | DEBUG | `db.store` |
| `compliance_score_recorded` | INFO | `schemas.nista.longitudinal` |
| `trend_computed` | DEBUG | `schemas.nista.longitudinal` |
| `thresholds_checked` | INFO | `schemas.nista.longitudinal` |
| `finding_analysis_started` | INFO | `assurance.analyzer` |
| `finding_analysis_complete` | INFO | `assurance.analyzer` |
| `review_action_deduplicated` | DEBUG | `assurance.analyzer` |
| `recurrence_detected` | INFO | `assurance.recurrence` |
| `recurrence_detection_skipped` | WARNING | `assurance.recurrence` |
| `divergence_checked` | INFO | `assurance.divergence` |
| `divergence_snapshot_persisted` | DEBUG | `assurance.divergence` |
| `review_schedule_recommended` | INFO | `assurance.scheduler` |
| `scheduler_currency_signal` | DEBUG | `assurance.scheduler` |
| `scheduler_trend_signal` | DEBUG | `assurance.scheduler` |
| `scheduler_actions_signal` | DEBUG | `assurance.scheduler` |
| `scheduler_divergence_signal` | DEBUG | `assurance.scheduler` |
| `override_logged` | INFO | `assurance.overrides` |
| `override_outcome_recorded` | INFO | `assurance.overrides` |
| `override_patterns_analysed` | INFO | `assurance.overrides` |
