# Assurance Module — Developer Reference

This document describes the three assurance features in the PDA Platform:

- **P1 — Artefact Currency Validator**: Detects stale or anomalously refreshed
  evidence artefacts by inspecting document metadata timestamps against
  validation-gate deadlines.
- **P2 — Longitudinal Compliance Tracker**: Persists NISTA compliance scores
  over time and surfaces trend direction and threshold breaches.
- **P3 — Cross-Cycle Finding Analyzer**: Extracts review actions from project
  review text, deduplicates within a review cycle, detects recurrences across
  cycles, and persists the full lifecycle.

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

pm_mcp_servers/
  pm_assure/
    server.py             # MCP server: nista_longitudinal_trend,
                          #             track_review_actions,
                          #             review_action_status
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

## SQLite Store

The `AssuranceStore` manages all persistence.  The default database path is
`~/.pm_data_tools/store.db`.

```python
from pm_data_tools.db import AssuranceStore
from pathlib import Path

store = AssuranceStore(db_path=Path("/project/data/store.db"))
```

Tables are created on first use with `CREATE TABLE IF NOT EXISTS`.  Both P2
and P3 share one store instance; initialising from either feature is safe.

---

## Testing

Tests live in `packages/pm-data-tools/tests/test_assurance/`.

```
test_assurance/
  conftest.py                        # Shared fixtures, mock ConfidenceExtractor
  test_longitudinal_compliance.py    # 12 tests for P2
  test_finding_analyzer.py           # 11 tests for P3
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
