# Assurance Module — Developer Reference

This document describes the ten assurance features in the PDA Platform:

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
- **P7 — Lessons Learned Knowledge Engine**: Ingests structured lessons from
  project history and provides keyword and semantic search to surface relevant
  lessons at the point of decision-making.
- **P8 — Assurance Overhead Optimiser**: Tracks assurance effort, correlates
  it with confidence outcomes, and identifies waste — duplicate checks,
  zero-finding reviews, and misallocated effort.
- **P9 — Agentic Assurance Workflow Engine**: Deterministic multi-step
  orchestrator that sequences P1–P8 steps, accumulates inter-step data flow,
  and produces overall project health, aggregated risk signals, and recommended
  actions in a single workflow result.
- **P10 — Project Domain Classifier**: Classifies projects into complexity
  domains (CLEAR / COMPLICATED / COMPLEX / CHAOTIC) using up to seven explicit
  indicators and four store-derived signals, then returns a tailored assurance
  profile with recommended cadence and toolset.

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
    lessons.py            # LessonsKnowledgeEngine, LessonRecord, LessonCategory
    overhead.py           # AssuranceOverheadOptimiser, AssuranceActivity, ActivityType
    workflows.py          # AssuranceWorkflowEngine, WorkflowType, ProjectHealth
    classifier.py         # ProjectDomainClassifier, ComplexityDomain, ClassificationInput

pm_mcp_servers/
  pm_assure/
    server.py             # MCP server: 16 tools (see MCP tool sections below)
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

## P7 — Lessons Learned Knowledge Engine

### Purpose

Organisations accumulate lessons from past projects but rarely make them
available at the point of decision-making.  Lessons databases exist but are
unstructured, unsearchable, and disconnected from current project context.
This feature ingests structured lesson records with contextual metadata and
provides both keyword and semantic search to surface relevant lessons matched
to a project's current situation.

### Data models

#### `LessonCategory`

```
GOVERNANCE, TECHNICAL, COMMERCIAL, STAKEHOLDER, RESOURCE,
REQUIREMENTS, ESTIMATION, RISK_MANAGEMENT, BENEFITS_REALISATION, OTHER
```

#### `LessonSentiment`

```
POSITIVE   — what went well; replicate this
NEGATIVE   — what went wrong; avoid this
```

#### `LessonRecord`

```python
class LessonRecord(BaseModel):
    id: str                          # UUID4
    project_id: str
    title: str
    description: str
    category: LessonCategory
    sentiment: LessonSentiment
    project_type: str | None         # e.g. "ICT", "Infrastructure"
    project_phase: str | None        # e.g. "Initiation", "Delivery"
    department: str | None
    tags: list[str]
    date_recorded: date              # defaults to today
    recorded_by: str | None
    impact_description: str | None
```

#### `LessonSearchResult`

```python
class LessonSearchResult(BaseModel):
    lesson: LessonRecord
    relevance_score: float    # 0.0 to 1.0
    match_reason: str         # e.g. "keyword match in title", "semantic similarity 0.82"
```

#### `LessonSearchResponse`

```python
class LessonSearchResponse(BaseModel):
    query: str
    results: list[LessonSearchResult]
    total_in_corpus: int
    search_method: str        # "keyword" or "semantic"
```

#### `LessonPatternSummary`

```python
class LessonPatternSummary(BaseModel):
    total_lessons: int
    by_category: dict[str, int]
    by_sentiment: dict[str, int]
    by_project_type: dict[str, int]
    top_tags: list[dict[str, Any]]              # [{tag, count}] top 10
    most_common_negative_categories: list[dict] # [{category, count}]
    message: str
```

### `LessonsKnowledgeEngine`

```python
from pm_data_tools.assurance import LessonsKnowledgeEngine, LessonRecord, LessonCategory

engine = LessonsKnowledgeEngine()
engine = LessonsKnowledgeEngine(
    store=AssuranceStore(db_path=Path("/custom/store.db")),
    similarity_threshold=0.40,
)
```

Supports two search modes.  **Keyword search** is always available.
**Semantic search** uses sentence-transformer embeddings and requires
`sentence-transformers` (optional).  Falls back to keyword search when
unavailable — the same pattern as `RecurrenceDetector`.

| Method | Description |
|--------|-------------|
| `ingest(lesson)` | Persist a `LessonRecord`. Returns the lesson with its ID. |
| `ingest_batch(lessons)` | Ingest multiple lessons. Returns count ingested. |
| `search(query, project_type, category, sentiment, limit)` | Search with optional filters. Returns `LessonSearchResponse`. |
| `get_lessons(project_id, category, sentiment)` | Retrieve lessons, optionally filtered. |
| `get_contextual_lessons(project_type, project_phase, category, limit)` | Retrieve lessons for a specific context; NEGATIVE sentiment ranked first. |
| `analyse_patterns()` | Compute corpus-wide `LessonPatternSummary`. |

**Keyword scoring:** +1.0 title match, +0.5 description match, +0.3 tag match,
+0.2 category match.  Normalised by dividing by 2.0.

### MCP tool: `ingest_lesson`

```json
{
  "project_id": "PROJ-001",
  "title": "Early stakeholder engagement prevented scope creep",
  "description": "Fortnightly workshops from week 2 identified conflicting requirements.",
  "category": "STAKEHOLDER",
  "sentiment": "POSITIVE",
  "project_type": "ICT",
  "project_phase": "Initiation",
  "tags": ["stakeholders", "scope", "requirements"],
  "recorded_by": "PMO Lead"
}
```

Returns:

```json
{
  "id": "a3c8f1e2-...",
  "project_id": "PROJ-001",
  "title": "Early stakeholder engagement prevented scope creep",
  "category": "STAKEHOLDER",
  "sentiment": "POSITIVE",
  "date_recorded": "2026-03-28",
  "message": "Lesson ingested with id 'a3c8f1e2-...'."
}
```

### MCP tool: `search_lessons`

```json
{
  "query": "procurement delays",
  "project_type": "ICT",
  "sentiment": "NEGATIVE",
  "limit": 5
}
```

Returns:

```json
{
  "query": "procurement delays",
  "search_method": "keyword",
  "total_in_corpus": 42,
  "results_count": 2,
  "results": [
    {
      "id": "...",
      "title": "Delayed procurement caused 6-week schedule slip",
      "category": "COMMERCIAL",
      "sentiment": "NEGATIVE",
      "relevance_score": 0.75,
      "match_reason": "keyword match in title; keyword match in description"
    }
  ]
}
```

---

## P8 — Assurance Overhead Optimiser

### Purpose

Assurance activities consume project time and budget.  Without measurement,
organisations cannot tell whether they are investing too little (missing real
issues) or too much (redundant checks that add overhead without improving
outcomes).  Common symptoms include the same artefact being reviewed across
multiple gates, low-value reviews persisting because they have always been
done, and review frequency that does not adapt to project risk.  This feature
tracks assurance effort, correlates it with confidence outcomes, and identifies
waste patterns.

### Data models

#### `ActivityType`

```
GATE_REVIEW, DOCUMENT_REVIEW, COMPLIANCE_CHECK, RISK_ASSESSMENT,
STAKEHOLDER_REVIEW, AUDIT, OTHER
```

#### `EfficiencyRating`

```
OPTIMAL           — good confidence outcomes relative to effort
UNDER_INVESTED    — low effort, poor outcomes — more assurance needed
OVER_INVESTED     — high effort, no better outcomes — reduce frequency
MISALLOCATED      — effort going to the wrong activities (high duplication)
```

#### `AssuranceActivity`

```python
class AssuranceActivity(BaseModel):
    id: str                             # UUID4
    project_id: str
    activity_type: ActivityType
    description: str
    date: date
    effort_hours: float
    participants: int = 1
    artefacts_reviewed: list[str]
    findings_count: int = 0
    confidence_before: float | None     # NISTA score before (0–100)
    confidence_after: float | None      # NISTA score after (0–100)
```

#### `DuplicateCheckResult`

```python
class DuplicateCheckResult(BaseModel):
    activity_id: str
    duplicate_of: str
    overlap_type: str      # "same_artefact", "same_type_same_week", "no_findings_repeat"
    detail: str
```

#### `OverheadAnalysis`

```python
class OverheadAnalysis(BaseModel):
    project_id: str
    timestamp: datetime
    total_activities: int
    total_effort_hours: float
    total_participants_hours: float     # effort_hours × participants, summed
    effort_by_type: dict[str, float]
    activities_with_findings: int
    activities_without_findings: int
    finding_rate: float                 # proportion producing findings (0–1)
    avg_confidence_lift: float | None   # avg (confidence_after − confidence_before)
    duplicate_checks: list[DuplicateCheckResult]
    efficiency_rating: EfficiencyRating
    recommendations: list[str]
    message: str
```

### `AssuranceOverheadOptimiser`

```python
from pm_data_tools.assurance import AssuranceOverheadOptimiser, AssuranceActivity, ActivityType

optimiser = AssuranceOverheadOptimiser()
optimiser = AssuranceOverheadOptimiser(
    store=AssuranceStore(db_path=Path("/custom/store.db"))
)
```

| Method | Description |
|--------|-------------|
| `log_activity(activity)` | Persist an `AssuranceActivity`. Returns the activity with its ID. |
| `get_activities(project_id, activity_type)` | Retrieve activities, optionally filtered by type. |
| `detect_duplicates(project_id)` | Identify overlapping activities per three detection rules. |
| `compute_efficiency(project_id)` | Classify overall efficiency as an `EfficiencyRating`. |
| `generate_recommendations(project_id)` | Generate human-readable optimisation suggestions. |
| `analyse(project_id)` | Run a complete analysis; persists result to store. |

**Efficiency classification logic (evaluated in order):**

1. `total_effort_hours < 10` and `avg_confidence_lift` is `None` or negative → `UNDER_INVESTED`
2. `finding_rate < 0.20` and `total_effort_hours > 40` → `OVER_INVESTED`
3. `duplicate_count > total_activities × 0.30` → `MISALLOCATED`
4. Otherwise → `OPTIMAL`

**Duplicate detection rules:**

| Rule | Condition |
|------|-----------|
| `same_artefact` | Two activities reviewing the same artefact within 14 days |
| `same_type_same_week` | Two activities of the same type within 7 days |
| `no_findings_repeat` | Same type, both 0 findings, within 30 days |

### MCP tool: `log_assurance_activity`

```json
{
  "project_id": "PROJ-001",
  "activity_type": "GATE_REVIEW",
  "description": "Stage gate 3 — delivery readiness assessment",
  "date": "2026-03-20",
  "effort_hours": 16.0,
  "participants": 4,
  "artefacts_reviewed": ["risk-register-v3", "benefits-profile-v2"],
  "findings_count": 3,
  "confidence_before": 72.0,
  "confidence_after": 78.5
}
```

Returns:

```json
{
  "id": "b7d2e4f1-...",
  "project_id": "PROJ-001",
  "activity_type": "GATE_REVIEW",
  "date": "2026-03-20",
  "effort_hours": 16.0,
  "findings_count": 3,
  "message": "Activity logged with id 'b7d2e4f1-...'."
}
```

### MCP tool: `analyse_assurance_overhead`

```json
{
  "project_id": "PROJ-001"
}
```

Returns:

```json
{
  "project_id": "PROJ-001",
  "total_activities": 8,
  "total_effort_hours": 72.0,
  "finding_rate": 0.75,
  "efficiency_rating": "OPTIMAL",
  "duplicate_checks": [],
  "recommendations": [],
  "message": "8 assurance activity/activities recorded for 'PROJ-001'. Total effort: 72.0 hours. Finding rate: 75%. Efficiency: OPTIMAL."
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
| `lessons_learned` | P7 — Lessons Learned Knowledge Engine |
| `assurance_activities` | P8 — Assurance Overhead Optimiser |
| `overhead_analyses` | P8 — Assurance Overhead Optimiser |
| `workflow_executions` | P9 — Agentic Assurance Workflow Engine |
| `domain_classifications` | P10 — Project Domain Classifier |

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
  test_lessons.py                    # 21 tests for P7
  test_overhead.py                   # 20 tests for P8
  test_workflows.py                  # 35 tests for P9
  test_classifier.py                 # 35 tests for P10
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
| `lesson_ingested` | INFO | `assurance.lessons` |
| `lesson_batch_ingested` | INFO | `assurance.lessons` |
| `lessons_searched` | INFO | `assurance.lessons` |
| `semantic_search_unavailable` | WARNING | `assurance.lessons` |
| `contextual_lessons_retrieved` | DEBUG | `assurance.lessons` |
| `lessons_patterns_analysed` | INFO | `assurance.lessons` |
| `activity_logged` | INFO | `assurance.overhead` |
| `duplicates_detected` | DEBUG | `assurance.overhead` |
| `overhead_analysed` | INFO | `assurance.overhead` |
| `workflow_executed` | INFO | `assurance.workflows` |
| `workflow_step_exception` | WARNING | `assurance.workflows` |
| `workflow_execution_persisted` | DEBUG | `assurance.workflows` |
| `workflow_result_persisted` | DEBUG | `assurance.workflows` |
| `workflow_result_deserialisation_failed` | WARNING | `assurance.workflows` |
| `project_domain_classified` | INFO | `assurance.classifier` |
| `classifier_p2_signal_failed` | WARNING | `assurance.classifier` |
| `classifier_p3_signal_failed` | WARNING | `assurance.classifier` |
| `classifier_p6_signal_failed` | WARNING | `assurance.classifier` |
| `classifier_p8_signal_failed` | WARNING | `assurance.classifier` |
| `domain_classification_persisted` | DEBUG | `assurance.classifier` |
| `classification_result_deserialisation_failed` | WARNING | `assurance.classifier` |

---

## P9 — Agentic Assurance Workflow Engine

### Purpose

The `AssuranceWorkflowEngine` is a deterministic multi-step orchestrator that
sequences P1–P8 assurance steps for a given project and returns a complete
health assessment.  It is NOT an AI agent — all decisions are rule-based and
reproducible.

Key behaviours:

- **Fail-safe**: If a step raises an exception, it is recorded as `FAILED` and
  the workflow continues with the next step.
- **Inter-step data flow**: P1 (currency scores), P2 (trend + breaches), P3
  (open action counts), and P4 (divergence result) are accumulated and passed
  to P5 (scheduler) automatically.
- **Health classification**: Derived from the maximum and average severity of
  all aggregated risk signals.
- **Persistence**: Each workflow result is stored in `workflow_executions` for
  historical retrieval.

### Workflow types

| Type | Steps executed |
|------|---------------|
| `FULL_ASSURANCE` | P1, P2, P3, P4, P5, P6, P7, P8 |
| `COMPLIANCE_FOCUS` | P2, P5, P6 |
| `CURRENCY_FOCUS` | P1, P5 |
| `TREND_ANALYSIS` | P2, P3, P5 |
| `RISK_ASSESSMENT` | P1, P2, P3, P4, P5 |

### Health classification

| Health | Trigger condition |
|--------|-----------------|
| `HEALTHY` | No signals above attention threshold (0.20) |
| `ATTENTION_NEEDED` | Any signal ≥ 0.20, or average ≥ 0.15 |
| `AT_RISK` | Any signal ≥ 0.50, or average ≥ 0.40 |
| `CRITICAL` | Any signal ≥ 0.80 |

### Data models

```python
class WorkflowType(Enum):
    FULL_ASSURANCE = "FULL_ASSURANCE"
    COMPLIANCE_FOCUS = "COMPLIANCE_FOCUS"
    CURRENCY_FOCUS = "CURRENCY_FOCUS"
    TREND_ANALYSIS = "TREND_ANALYSIS"
    RISK_ASSESSMENT = "RISK_ASSESSMENT"

class ProjectHealth(Enum):
    HEALTHY = "HEALTHY"
    ATTENTION_NEEDED = "ATTENTION_NEEDED"
    AT_RISK = "AT_RISK"
    CRITICAL = "CRITICAL"

class WorkflowStepStatus(Enum):
    COMPLETED = "COMPLETED"
    SKIPPED = "SKIPPED"
    FAILED = "FAILED"
    NOT_APPLICABLE = "NOT_APPLICABLE"

class WorkflowRiskSignal(BaseModel):
    source: str            # "P1" … "P8"
    signal_name: str
    severity: float        # 0.0 – 1.0
    detail: str

class WorkflowStepResult(BaseModel):
    step_name: str
    status: WorkflowStepStatus
    duration_ms: float
    output: dict | None
    error_message: str | None
    risk_signal: WorkflowRiskSignal | None

class WorkflowResult(BaseModel):
    id: str                      # UUID4
    workflow_type: WorkflowType
    project_id: str
    started_at: datetime
    completed_at: datetime
    duration_ms: float
    health: ProjectHealth
    steps: list[WorkflowStepResult]
    aggregated_risk_signals: list[WorkflowRiskSignal]
    recommended_actions: list[str]
    executive_summary: str
```

### `AssuranceWorkflowEngine`

```python
from pm_data_tools.assurance.workflows import (
    AssuranceWorkflowEngine,
    WorkflowType,
    WorkflowConfig,
)

engine = AssuranceWorkflowEngine(
    config=WorkflowConfig(),
    store=store,
)
result = engine.execute(
    project_id="PROJ-001",
    workflow_type=WorkflowType.RISK_ASSESSMENT,
    artefacts=[                              # optional, for P1
        {"id": "risk-register", "type": "risk_register", "last_modified": "2026-03-01"},
    ],
    gate_date="2026-06-30",                  # optional, for P1
)
# result.health == ProjectHealth.AT_RISK
# result.executive_summary — full summary paragraph
# result.recommended_actions — ordered list
```

| Method | Description |
|--------|-------------|
| `execute(project_id, workflow_type, artefacts, gate_date)` | Run the workflow and return a `WorkflowResult`. |
| `get_workflow_history(project_id)` | Retrieve past workflow results from the store. |

### MCP tools

#### `run_assurance_workflow` (tool 13)

```json
{
  "project_id": "PROJ-001",
  "workflow_type": "RISK_ASSESSMENT",
  "artefacts": [
    {"id": "risk-register", "type": "risk_register", "last_modified": "2026-03-01"}
  ],
  "gate_date": "2026-06-30"
}
```

Returns full workflow result with health, steps, risk signals, recommended
actions, and executive summary.

#### `get_workflow_history` (tool 14)

```json
{ "project_id": "PROJ-001" }
```

Returns all historical workflow executions for the project.

---

## P10 — Project Domain Classifier

### Purpose

The `ProjectDomainClassifier` assigns a project to one of four complexity
domains based on explicit indicators provided by the caller and automated
signals derived from the AssuranceStore (P2/P3/P6/P8 data).

Domain classification determines the appropriate assurance intensity:

| Domain | Composite score | Review cadence |
|--------|----------------|----------------|
| `CLEAR` | < 0.25 | Every 90 days |
| `COMPLICATED` | 0.25 – 0.50 | Every 60 days |
| `COMPLEX` | 0.50 – 0.75 | Every 42 days |
| `CHAOTIC` | ≥ 0.75 | Every 14 days |

### Explicit indicators (7)

| Indicator | Direction | Description |
|-----------|-----------|-------------|
| `technical_complexity` | positive | Novelty and integration complexity |
| `stakeholder_complexity` | positive | Breadth and diversity of stakeholders |
| `requirement_clarity` | **inverse** | High = clearer = lower complexity |
| `delivery_track_record` | **inverse** | High = better = lower complexity |
| `organisational_change` | positive | Degree of organisational change required |
| `regulatory_exposure` | positive | Level of regulatory risk |
| `dependency_count` | positive | Normalised count of external dependencies |

Inverse indicators are mapped as `complexity_contribution = 1 - raw_value`.

### Store-derived signals (4)

| Signal | Source | Severity mapping |
|--------|--------|-----------------|
| P2 compliance trend | `confidence_scores` table | IMPROVING→0.0, STAGNATING→0.3, DEGRADING→0.7 |
| P3 open action rate | `recommendations` table | open_count / total |
| P6 override impact rate | `override_decisions` table | `impact_rate` from `OverrideDecisionLogger` |
| P8 efficiency rating | `assurance_activities` table | OPTIMAL→0.0, OVER_INVESTED→0.4, UNDER_INVESTED→0.5, MISALLOCATED→0.7 |

### Weight combination

Default weights: explicit 0.70, derived 0.30.  Weights are renormalised when
only one category has data (e.g. no explicit indicators → derived weight = 1.0).

### Data models

```python
class ComplexityDomain(Enum):
    CLEAR = "CLEAR"
    COMPLICATED = "COMPLICATED"
    COMPLEX = "COMPLEX"
    CHAOTIC = "CHAOTIC"

class DomainIndicator(BaseModel):
    name: str
    raw_value: float
    complexity_contribution: float   # after inversion if applicable
    weight: float = 1.0
    description: str

class ClassificationInput(BaseModel):
    project_id: str
    technical_complexity: float | None = None
    stakeholder_complexity: float | None = None
    requirement_clarity: float | None = None
    delivery_track_record: float | None = None
    organisational_change: float | None = None
    regulatory_exposure: float | None = None
    dependency_count: float | None = None
    notes: str | None = None

class DomainAssuranceProfile(BaseModel):
    domain: ComplexityDomain
    review_frequency_days: int
    recommended_tools: list[str]
    confidence_threshold: float
    compliance_floor: float
    notes: str

class ClassificationResult(BaseModel):
    id: str
    project_id: str
    domain: ComplexityDomain
    composite_score: float
    explicit_score: float | None
    derived_score: float | None
    indicators: list[DomainIndicator]
    profile: DomainAssuranceProfile
    classified_at: datetime
    rationale: str
```

### `ProjectDomainClassifier`

```python
from pm_data_tools.assurance.classifier import (
    ProjectDomainClassifier,
    ClassificationInput,
    ClassifierConfig,
)

clf = ProjectDomainClassifier(store=store)

# Full classification with explicit indicators
result = clf.classify(ClassificationInput(
    project_id="PROJ-001",
    technical_complexity=0.7,
    stakeholder_complexity=0.6,
    requirement_clarity=0.3,
    delivery_track_record=0.4,
    organisational_change=0.8,
    regulatory_exposure=0.6,
    dependency_count=0.5,
))
# result.domain == ComplexityDomain.COMPLEX

# Store-only reclassification (no explicit indicators)
result = clf.reclassify_from_store("PROJ-001")

# Look up profile for a domain
profile = clf.get_profile(ComplexityDomain.CHAOTIC)
# profile.review_frequency_days == 14

# Retrieve history
history = clf.get_classification_history("PROJ-001")
```

| Method | Description |
|--------|-------------|
| `classify(inp)` | Classify using explicit indicators + store signals. |
| `reclassify_from_store(project_id)` | Classify using only store-derived signals. |
| `get_profile(domain)` | Return the assurance profile for a domain. |
| `get_classification_history(project_id)` | Retrieve past classifications. |

### MCP tools

#### `classify_project_domain` (tool 15)

```json
{
  "project_id": "PROJ-001",
  "technical_complexity": 0.7,
  "stakeholder_complexity": 0.6,
  "requirement_clarity": 0.3,
  "organisational_change": 0.8
}
```

Returns domain, composite score, indicators, profile (cadence + tools), and
rationale.

#### `reclassify_from_store` (tool 16)

```json
{ "project_id": "PROJ-001" }
```

Reclassifies using only P2/P3/P6/P8 store data — no explicit indicators
required.  Suitable for automated or scheduled reclassification tasks.

---

## P11 — Assumption Drift Tracker

### Purpose

Captures project assumptions with baseline values, monitors drift against
current values over time, detects stale assumptions (not re-validated within
a configurable window), and flags cascading impacts through the assumption
dependency graph.  Designed as the key differentiator for MPA Challenge 5
(Critical Assumption Drift).

### Data models

| Model | Description |
|-------|-------------|
| `Assumption` | A single assumption with baseline, current value, unit, tolerance, and dependencies |
| `AssumptionValidation` | A single validation record: new value, drift %, severity |
| `DriftResult` | Per-assumption drift analysis: drift_pct, severity, cascade impact |
| `AssumptionHealthReport` | Aggregate health: total, stale, drift by severity/category, cascade warnings, overall score |
| `AssumptionConfig` | Thresholds: staleness_days, minor/moderate/significant drift percentages |

**`AssumptionCategory`:** `COST` | `SCHEDULE` | `RESOURCE` | `TECHNICAL` | `COMMERCIAL` | `REGULATORY` | `STAKEHOLDER` | `EXTERNAL`

**`DriftSeverity`:** `NONE` | `MINOR` | `MODERATE` | `SIGNIFICANT` | `CRITICAL`

**`AssumptionSource`:** `MANUAL` | `EXTERNAL_API` | `DERIVED`

### Core class

```python
from pm_data_tools.assurance.assumptions import (
    AssumptionTracker, Assumption, AssumptionCategory,
    AssumptionConfig, AssumptionSource,
)
from pm_data_tools.db.store import AssuranceStore

store = AssuranceStore()
tracker = AssumptionTracker(store=store)

# Ingest an assumption
a = tracker.ingest(
    Assumption(
        project_id="PROJ-001",
        text="CPI inflation will remain below 3% through 2026",
        category=AssumptionCategory.COST,
        baseline_value=2.5,
        unit="%",
        tolerance_pct=20.0,
        source=AssumptionSource.EXTERNAL_API,
        external_ref="ONS_CPI",
    )
)

# Later, update with a new value
validation = tracker.update_value(
    assumption_id=a.id,
    new_value=3.8,
    notes="Updated from latest ONS release",
)
# validation.drift_pct == 52.0, validation.severity == DriftSeverity.CRITICAL

# Run full project analysis
report = tracker.analyse_project("PROJ-001")
# report.overall_drift_score → 0.0 – 1.0
# report.cascade_warnings → list of human-readable impact warnings

# Cascade impact
affected_ids = tracker.get_cascade_impact(a.id)

# Stale assumptions
stale = tracker.get_stale_assumptions("PROJ-001")
```

| Method | Description |
|--------|-------------|
| `ingest(assumption)` | Persist an assumption; returns it with auto-generated id |
| `ingest_batch(assumptions)` | Ingest multiple assumptions; returns count |
| `get_assumptions(project_id, category=None)` | Retrieve assumptions, optionally filtered |
| `update_value(assumption_id, new_value, source, notes)` | Update current value, record validation, compute drift |
| `compute_drift(assumption)` | Compute drift for a single assumption |
| `analyse_project(project_id)` | Full health analysis: drift, staleness, cascade, score |
| `get_cascade_impact(assumption_id)` | BFS cascade graph traversal; handles cycles |
| `get_dependency_graph(project_id)` | Reverse adjacency dict for all assumptions |
| `get_stale_assumptions(project_id)` | Assumptions not validated within staleness window |
| `get_validation_history(assumption_id)` | All validations oldest first |

**Drift severity thresholds (default config):**

| Drift % | Severity |
|---------|----------|
| ≤ 5% | NONE |
| ≤ 15% | MINOR |
| ≤ 30% | MODERATE |
| ≤ 45% | SIGNIFICANT |
| > 45% | CRITICAL |

**Overall drift score** = weighted average of individual severities
(NONE=0, MINOR=0.2, MODERATE=0.5, SIGNIFICANT=0.8, CRITICAL=1.0).

### Persistence

Two new tables in `AssuranceStore`:

- `assumptions` — one row per assumption per project
- `assumption_validations` — one row per `update_value()` call

New store methods: `upsert_assumption`, `get_assumptions`, `get_assumption_by_id`,
`update_assumption_value`, `insert_assumption_validation`, `get_assumption_validations`.

### P9 workflow integration

`FULL_ASSURANCE` runs `p11_assumption_drift` as step 9 (after P8).

New workflow type `ASSUMPTION_HEALTH_CHECK` runs:
`p11_assumption_drift` → `p2_compliance_trend` → `p5_schedule_recommendation`

P11 signal: `"assumption_drift"` from source `"P11"`, severity = `overall_drift_score`.

Recommended action when signal >= threshold:
`"Review and re-validate stale or drifting assumptions before the next gate review."`

### MCP tools

#### `ingest_assumption` (tool 17)

```json
{
  "project_id": "PROJ-001",
  "text": "CPI inflation will remain below 3% through 2026",
  "category": "COST",
  "baseline_value": 2.5,
  "unit": "%",
  "tolerance_pct": 20.0,
  "source": "EXTERNAL_API",
  "external_ref": "ONS_CPI",
  "owner": "Finance Lead"
}
```

Returns the ingested assumption with its auto-generated `id`.

#### `validate_assumption` (tool 18)

```json
{
  "assumption_id": "uuid-here",
  "new_value": 3.8,
  "source": "MANUAL",
  "notes": "Updated from latest ONS release"
}
```

Returns the validation record with `drift_pct` and `severity`.

#### `get_assumption_drift` (tool 19)

```json
{ "project_id": "PROJ-001" }
```

Returns the full `AssumptionHealthReport` as JSON including per-assumption drift
results, cascade warnings, counts by severity/category, and overall drift score.

#### `get_cascade_impact` (tool 20)

```json
{ "assumption_id": "uuid-here" }
```

Returns the list of affected assumption IDs with their texts, category, baseline
value, current value, drift percentage, and severity.  Uses breadth-first
traversal and handles circular dependency graphs safely.
