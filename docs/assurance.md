# Assurance Module — Developer Reference

This document describes the two assurance features added in v0.3.0:

- **P2 — NISTA Score History**: Persists compliance scores over time and
  surfaces trend direction and threshold breaches.
- **P3 — Recommendation Tracker**: Extracts assurance recommendations from
  review text, deduplicates within a review cycle, detects recurrences across
  cycles, and persists the full lifecycle.

---

## Architecture

```
pm_data_tools/
  db/
    store.py          # AssuranceStore — shared SQLite persistence layer
  schemas/
    nista/
      history.py      # NISTAScoreHistory, ConfidenceScoreRecord, TrendDirection
      validator.py    # NISTAValidator — extended with optional history param
  assurance/
    models.py         # Recommendation, RecommendationStatus, ...
    extractor.py      # RecommendationExtractor
    recurrence.py     # RecurrenceDetector

pm_mcp_servers/
  pm_assure/
    server.py         # MCP server: nista_score_trend, track_recommendations,
                      #             recommendation_status
```

All SQLite tables are created with `CREATE TABLE IF NOT EXISTS` so the store
is safe to initialise from any subset of features.

---

## Package Dependencies

| Feature | Required extras |
|---------|----------------|
| NISTA Score History | none (SQLite is stdlib) |
| Recommendation Tracker (extraction) | `agent-task-planning>=0.2.0` (already a core dep) |
| Recommendation Tracker (recurrence) | `agent-task-planning[mining]` for sentence-transformers |

Install with recurrence detection enabled:

```bash
pip install pm-data-tools[assurance]
pip install "agent-task-planning[mining]"
```

---

## P2 — NISTA Score History

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

#### `NISTAThresholdConfig`

```python
class NISTAThresholdConfig(BaseModel):
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

### `NISTAScoreHistory`

```python
from pm_data_tools.schemas.nista.history import NISTAScoreHistory

history = NISTAScoreHistory()          # uses default ~/.pm_data_tools/store.db
history = NISTAScoreHistory(
    store=AssuranceStore(db_path=Path("/custom/path.db")),
    thresholds=NISTAThresholdConfig(floor=70.0),
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
from pm_data_tools.schemas.nista import NISTAValidator, NISTAScoreHistory

validator = NISTAValidator()
history = NISTAScoreHistory()

result = validator.validate(
    data,
    project_id="PROJ-001",   # optional: falls back to data["project_id"]
    history=history,          # optional: omit to skip persistence
)
# result is identical ValidationResult regardless
```

### MCP tool: `nista_score_trend`

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

## P3 — Recommendation Tracker

### Data models

#### `RecommendationStatus`

```
OPEN        — newly extracted, no action
IN_PROGRESS — being addressed
CLOSED      — resolved
RECURRING   — detected as recurring from a prior cycle
```

#### `Recommendation`

```python
class Recommendation(BaseModel):
    id: str                        # UUID4
    text: str                      # Recommended action
    category: str                  # Maps to extraction priority (High/Medium/Low)
    source_review_id: str
    review_date: date
    status: RecommendationStatus
    owner: Optional[str]
    recurrence_of: Optional[str]   # Prior recommendation id
    confidence: float              # From ConfidenceExtractor
    flagged_for_review: bool       # True if confidence < min_confidence
```

#### `RecommendationExtractionResult`

```python
class RecommendationExtractionResult(BaseModel):
    recommendations: list[Recommendation]
    extraction_confidence: float
    review_level: str
    cost_usd: float
```

### `RecommendationExtractor`

Wraps `ConfidenceExtractor` from `agent-task-planning` with the
`SchemaType.RECOMMENDATION` schema.  Does not make direct API calls.

```python
from agent_planning.confidence import ConfidenceExtractor
from agent_planning.providers.anthropic import AnthropicProvider
from pm_data_tools.assurance import RecommendationExtractor, RecurrenceDetector

provider = AnthropicProvider(api_key="...")
ce = ConfidenceExtractor(provider)

extractor = RecommendationExtractor(
    extractor=ce,
    min_confidence=0.60,           # flag below this, never reject
    recurrence_detector=RecurrenceDetector(),
)

result = await extractor.extract(
    review_text="...",
    review_id="review-2026-Q1",
    project_id="PROJ-001",
)
```

Behaviour:

1. Calls `ConfidenceExtractor.extract()` with `SchemaType.RECOMMENDATION`.
2. Maps `RecommendationItem.action` to `Recommendation.text`.
3. Deduplicates by normalised (lowercased) text within the current review.
4. If a `RecurrenceDetector` is supplied, fetches prior OPEN recommendations
   (excluding those from the same `review_id`) and calls
   `detect_recurrences()`.
5. Persists all recommendations to the shared SQLite store.

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

### Updating recommendation status

```python
from pm_data_tools.db import AssuranceStore
from pm_data_tools.assurance import RecommendationStatus

store = AssuranceStore()
store.update_recommendation_status("rec-id-001", RecommendationStatus.CLOSED.value)
```

### MCP tools

**`track_recommendations`**

```json
{
  "review_text": "...",
  "review_id": "review-2026-Q1",
  "project_id": "PROJ-001",
  "min_confidence": 0.60
}
```

Requires `ANTHROPIC_API_KEY` to be set in the server environment.

**`recommendation_status`**

```json
{
  "project_id": "PROJ-001",
  "status_filter": "OPEN"
}
```

Returns the list of matching recommendations with recurrence flags included.

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
  conftest.py                      # Shared fixtures, mock ConfidenceExtractor
  test_nista_history.py            # 12 tests for P2
  test_recommendation_tracker.py   # 11 tests for P3
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

## Logging

All modules use `structlog`.  Key events:

| Logger event | Level | Module |
|---|---|---|
| `assurance_store_ready` | DEBUG | `db.store` |
| `confidence_score_persisted` | DEBUG | `db.store` |
| `nista_score_recorded` | INFO | `schemas.nista.history` |
| `trend_computed` | DEBUG | `schemas.nista.history` |
| `thresholds_checked` | INFO | `schemas.nista.history` |
| `recommendation_extraction_started` | INFO | `assurance.extractor` |
| `recommendation_extraction_complete` | INFO | `assurance.extractor` |
| `recommendation_deduplicated` | DEBUG | `assurance.extractor` |
| `recurrence_detected` | INFO | `assurance.recurrence` |
| `recurrence_detection_skipped` | WARNING | `assurance.recurrence` |
