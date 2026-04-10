# Gate Readiness Assessor (P14) — Developer Reference

The Gate Readiness Assessor synthesises persisted data from all existing
assurance modules (P1-P12) into a composite, gate-specific readiness
assessment.  It reads data that has already been written to the shared
`AssuranceStore` — it does not re-execute any module.

The assessor supports all seven IPA assurance review points (Gate 0-5 plus
Project Assessment Review) and applies gate-specific dimension weighting so
that early gates emphasise assumptions and governance while later gates
emphasise artefact readiness and operational learning.

---

## Architecture

```
pm_data_tools/
  db/
    store.py                    # AssuranceStore — shared SQLite persistence
  assurance/
    gate_readiness.py           # GateReadinessAssessor, GateType, ReadinessLevel,
                                # AssessmentDimension, DimensionStatus,
                                # DimensionScore, GateRiskSignal,
                                # GateReadinessAssessment, GateComparisonResult,
                                # GateReadinessConfig

pm_mcp_servers/
  pm_assure/
    server.py                   # MCP tools: assess_gate_readiness,
                                #   get_gate_readiness_history,
                                #   compare_gate_readiness
    registry.py                 # Tool dispatch registration
```

---

## Assessment Dimensions

The assessor scores eight dimensions, each mapped to one or more source
modules:

| Dimension | Source modules | What it measures |
|-----------|---------------|------------------|
| ARTEFACT_READINESS | P1, P3 | Document currency and review action closure rate |
| DATA_QUALITY | P2, P4 | NISTA compliance trends and AI extraction confidence |
| ASSUMPTION_HEALTH | P11 | Assumption drift severity and staleness |
| GOVERNANCE_MATURITY | P6, P12 | Override impact patterns and ARMM maturity level |
| REVIEW_TIMING | P5 | Review scheduling urgency signals |
| ASSURANCE_EFFICIENCY | P8 | Assurance activity effectiveness and waste rate |
| OPERATIONAL_LEARNING | P7 | Lessons learned capture volume and sentiment balance |
| COMPLEXITY_ALIGNMENT | P10 | Project complexity domain and assurance alignment |

Each dimension produces a score between 0.0 and 1.0 (where 1.0 = healthy).
Dimensions for which no persisted data exists are marked `NO_DATA` and
excluded from the composite calculation with weight renormalisation.

---

## Gate Weight Matrix

All rows sum to 1.0.  Early gates weight assumptions and governance more
heavily; later gates weight artefact readiness and operational learning.
PAR uses equal weights across all dimensions.

| Gate | Artefact Readiness | Data Quality | Assumption Health | Governance Maturity | Review Timing | Assurance Efficiency | Operational Learning | Complexity Alignment |
|------|---:|---:|---:|---:|---:|---:|---:|---:|
| Gate 0 | 0.05 | 0.10 | 0.25 | 0.20 | 0.10 | 0.05 | 0.10 | 0.15 |
| Gate 1 | 0.10 | 0.15 | 0.20 | 0.15 | 0.10 | 0.05 | 0.10 | 0.15 |
| Gate 2 | 0.15 | 0.20 | 0.15 | 0.10 | 0.10 | 0.05 | 0.10 | 0.15 |
| Gate 3 | 0.20 | 0.15 | 0.15 | 0.10 | 0.10 | 0.05 | 0.10 | 0.15 |
| Gate 4 | 0.15 | 0.10 | 0.10 | 0.20 | 0.10 | 0.10 | 0.15 | 0.10 |
| Gate 5 | 0.10 | 0.10 | 0.15 | 0.10 | 0.10 | 0.15 | 0.20 | 0.10 |
| PAR   | 0.125 | 0.125 | 0.125 | 0.125 | 0.125 | 0.125 | 0.125 | 0.125 |

---

## Enums

### `GateType`

IPA assurance review points.

```
GATE_0   — Opportunity Framing
GATE_1   — Strategic Outline Case
GATE_2   — Outline Business Case
GATE_3   — Full Business Case
GATE_4   — Readiness for Service / Work to Realise
GATE_5   — Operations Review & Benefits Realisation
PAR      — Project Assessment Review (any stage)
```

### `ReadinessLevel`

Gate readiness classification.

```
READY                — All dimensions healthy, no blocking issues.
CONDITIONALLY_READY  — Mostly ready, minor gaps or limited data coverage.
AT_RISK              — Significant gaps in multiple dimensions.
NOT_READY            — Critical blocking issues or widespread deficiencies.
```

### `AssessmentDimension`

Eight assessment dimensions mapped to source modules.

```
ARTEFACT_READINESS    — P1 + P3
DATA_QUALITY          — P2 + P4
ASSUMPTION_HEALTH     — P11
GOVERNANCE_MATURITY   — P6 + P12
REVIEW_TIMING         — P5
ASSURANCE_EFFICIENCY  — P8
OPERATIONAL_LEARNING  — P7
COMPLEXITY_ALIGNMENT  — P10
```

### `DimensionStatus`

Whether a dimension could be scored.

```
SCORED    — Full data available from all sources.
PARTIAL   — Some source data missing.
NO_DATA   — No data available for this dimension.
```

---

## Models

### `DimensionScore`

Score for a single assessment dimension.

```python
class DimensionScore(BaseModel):
    dimension: AssessmentDimension
    score: float                    # 0.0-1.0 (1.0 = healthy/ready)
    status: DimensionStatus
    weight: float                   # Gate-specific weight
    weighted_score: float           # score * weight
    sources_available: list[str]    # Module codes with data (e.g. ["P2", "P4"])
    sources_missing: list[str]      # Module codes without data
    detail: str                     # Human-readable explanation
```

### `GateRiskSignal`

A risk signal generated when a dimension scores below 0.5.

```python
class GateRiskSignal(BaseModel):
    dimension: AssessmentDimension
    source: str                     # Module code (e.g. "P11")
    signal_name: str                # Short description
    severity: float                 # 0.0-1.0
    is_blocking: bool               # True if severity >= critical threshold (0.80)
    detail: str                     # Full explanation
```

### `GateReadinessAssessment`

Full gate readiness assessment result.

```python
class GateReadinessAssessment(BaseModel):
    id: str                                         # UUID
    project_id: str
    gate: GateType
    assessed_at: datetime                            # UTC
    readiness: ReadinessLevel
    composite_score: float                           # 0.0-1.0
    dimension_scores: dict[str, DimensionScore]      # Keyed by dimension value
    risk_signals: list[GateRiskSignal]
    blocking_issues: list[str]                       # Issues that must be resolved
    recommended_actions: list[str]                   # Prioritised improvements
    data_availability: dict[str, bool]               # Which dimensions had data
    dimensions_scored: int                           # Count with data
    dimensions_total: int = 8
    executive_summary: str                           # Human-readable paragraph
```

### `GateComparisonResult`

Comparison between two gate readiness assessments.

```python
class GateComparisonResult(BaseModel):
    project_id: str
    gate: GateType
    before_id: str
    after_id: str
    before_score: float
    after_score: float
    before_readiness: ReadinessLevel
    after_readiness: ReadinessLevel
    score_delta: float
    readiness_changed: bool
    improved_dimensions: list[str]
    degraded_dimensions: list[str]
    resolved_blockers: list[str]
    new_blockers: list[str]
    message: str                                    # Human-readable summary
```

### `GateReadinessConfig`

Configuration for gate readiness assessment.

```python
class GateReadinessConfig(BaseModel):
    critical_signal_threshold: float = 0.80    # Severity at which a signal becomes blocking
    min_dimensions_for_ready: int = 4          # Minimum scored dimensions for READY
    ready_threshold: float = 0.75              # Composite score >= this for READY
    conditional_threshold: float = 0.50        # Composite score >= this for CONDITIONALLY_READY
    at_risk_threshold: float = 0.25            # Composite score >= this for AT_RISK, below = NOT_READY
```

---

## `GateReadinessAssessor` API

```python
from pm_data_tools.assurance.gate_readiness import (
    GateReadinessAssessor,
    GateType,
    ReadinessLevel,
    GateReadinessConfig,
)
from pm_data_tools.db.store import AssuranceStore

store = AssuranceStore()
assessor = GateReadinessAssessor(store=store)

# With custom config
assessor = GateReadinessAssessor(
    store=store,
    config=GateReadinessConfig(
        critical_signal_threshold=0.70,
        min_dimensions_for_ready=5,
    ),
)
```

### `assess(project_id, gate) -> GateReadinessAssessment`

Runs a full gate readiness assessment.  Scores all 8 dimensions using
persisted data from P1-P12, applies gate-specific weights, identifies
blocking issues, generates prioritised recommendations, and persists the
result to the store.

```python
result = assessor.assess("PROJ-001", GateType.GATE_3)
print(result.readiness)          # ReadinessLevel.CONDITIONALLY_READY
print(result.composite_score)    # 0.62
print(result.blocking_issues)    # ["3 assumptions with CRITICAL drift"]
print(result.executive_summary)
```

### `get_history(project_id, gate=None) -> list[GateReadinessAssessment]`

Retrieves past gate readiness assessments, oldest first.  Optionally
filtered by gate type.

```python
history = assessor.get_history("PROJ-001")
gate_3_history = assessor.get_history("PROJ-001", gate=GateType.GATE_3)
```

### `compare(assessment_id_before, assessment_id_after) -> GateComparisonResult`

Compares two assessments and returns deltas: score change, improved and
degraded dimensions, resolved and new blocking issues.

```python
comparison = assessor.compare(
    assessment_id_before="abc-123",
    assessment_id_after="def-456",
)
print(comparison.score_delta)         # +0.15
print(comparison.improved_dimensions) # ["ARTEFACT_READINESS", "DATA_QUALITY"]
print(comparison.resolved_blockers)   # ["3 assumptions with CRITICAL drift"]
print(comparison.message)
```

Raises `ValueError` if either assessment ID is not found.

---

## Readiness Classification Logic

The assessor classifies readiness using the following rules, applied in
order:

1. **Any blocking signal** (severity >= `critical_signal_threshold`):
   `NOT_READY`.
2. **Insufficient data coverage** (fewer than `min_dimensions_for_ready`
   dimensions scored): capped at `CONDITIONALLY_READY` regardless of
   composite score.
3. **Score-based classification**:

   | Composite score | Classification |
   |-----------------|----------------|
   | >= 0.75 | READY |
   | >= 0.50 | CONDITIONALLY_READY |
   | >= 0.25 | AT_RISK |
   | < 0.25 | NOT_READY |

Dimensions with `NO_DATA` status are excluded from the composite
calculation.  The remaining dimension weights are renormalised so the
composite is always computed on a 0.0-1.0 scale.

---

## Dimension Scoring Detail

### ARTEFACT_READINESS (P1 + P3)

- **P3**: Queries open review actions from the store.  Score =
  (closed actions / total actions).
- **P1**: Reads the latest workflow result for currency step data.
  Score = 1.0 - severity from the currency risk signal.
- Final score = average of available sub-scores.

### DATA_QUALITY (P2 + P4)

- **P2**: Reads latest NISTA compliance score.  Score = compliance / 100.
- **P4**: Reads latest divergence signal type.  Signal-to-score mapping:
  `STABLE` = 1.0, `LOW_CONSENSUS` = 0.5, `HIGH_DIVERGENCE` = 0.3,
  `DEGRADING_CONFIDENCE` = 0.2.
- Final score = average of available sub-scores.

### ASSUMPTION_HEALTH (P11)

- Queries all assumptions for the project, then their latest validations.
- Penalty = (critical * 0.3 + significant * 0.15 + stale * 0.1) / total.
- Score = 1.0 - min(penalty, 1.0).

### GOVERNANCE_MATURITY (P6 + P12)

- **P6**: Reads override decisions.  Score = 1.0 - (negative outcomes / total).
- **P12**: Reads latest ARMM assessment.  Score = overall_level / 4.0.
- Final score = average of available sub-scores.

### REVIEW_TIMING (P5)

- Reads latest scheduler result.  Score = 1.0 - composite_score
  (P5 composite is severity, where 0 = good).

### ASSURANCE_EFFICIENCY (P8)

- Reads assurance activities.  Score = 1.0 - (zero-finding activities /
  total activities).

### OPERATIONAL_LEARNING (P7)

- Reads lessons for the project.
- Capture score = min(1.0, total_lessons / 5.0) — having 5+ lessons =
  full credit.
- Sentiment score = (positive + 0.5 * neutral) / total.
- Final score = 0.6 * capture_score + 0.4 * sentiment_score.

### COMPLEXITY_ALIGNMENT (P10)

- Reads latest domain classification.
- Domain-to-score mapping: `CLEAR` = 1.0, `COMPLICATED` = 0.75,
  `COMPLEX` = 0.50, `CHAOTIC` = 0.25.

---

## Risk Signal Generation

For every dimension with `score < 0.5`, a `GateRiskSignal` is generated:

- `severity = 1.0 - score`
- `is_blocking = severity >= critical_signal_threshold` (default: 0.80,
  so any dimension scoring below 0.20 is blocking)

Signals are sorted by severity descending.  Blocking signals force the
overall readiness to `NOT_READY` regardless of composite score.

---

## Recommended Actions

The assessor generates two types of recommended action:

1. **Signal-driven actions**: for each risk signal, a pre-defined action
   template specific to the dimension (e.g. "Close open review actions and
   ensure all gate artefacts are current before proceeding").
2. **Data gap actions**: for each `NO_DATA` dimension, a recommendation to
   run the relevant assurance checks (e.g. "Run P5 assurance checks to
   establish Review Timing baseline data").

Actions are deduplicated and ordered with signal-driven actions first
(severity order) followed by data gap actions.

---

## MCP Tools

### `assess_gate_readiness`

Run a full gate readiness assessment.

```json
{
  "project_id": "PROJ-001",
  "gate": "GATE_3",
  "db_path": "/optional/path/to/store.db"
}
```

Required: `project_id`, `gate`.

`gate` accepts: `GATE_0`, `GATE_1`, `GATE_2`, `GATE_3`, `GATE_4`,
`GATE_5`, `PAR`.

Returns the full `GateReadinessAssessment` serialised as JSON.

### `get_gate_readiness_history`

Retrieve past assessments for a project.

```json
{
  "project_id": "PROJ-001",
  "gate": "GATE_3",
  "db_path": "/optional/path/to/store.db"
}
```

Required: `project_id`.  `gate` is optional — if omitted, returns
assessments for all gates.

Returns a list of serialised `GateReadinessAssessment` objects, oldest
first.

### `compare_gate_readiness`

Compare two assessments to show improvement or regression.

```json
{
  "assessment_id_before": "abc-123",
  "assessment_id_after": "def-456",
  "db_path": "/optional/path/to/store.db"
}
```

Required: `assessment_id_before`, `assessment_id_after`.

Returns the serialised `GateComparisonResult` with score delta,
improved/degraded dimensions, and resolved/new blocking issues.

---

## Database Schema

```sql
CREATE TABLE IF NOT EXISTS gate_readiness_assessments (
    id              TEXT PRIMARY KEY,
    project_id      TEXT NOT NULL,
    gate            TEXT NOT NULL,
    readiness       TEXT NOT NULL,
    composite_score REAL NOT NULL,
    assessed_at     TEXT NOT NULL,
    result_json     TEXT NOT NULL
);
```

The `result_json` column stores the full `GateReadinessAssessment`
serialised via `model_dump_json()`.  This allows the `get_history` and
`compare` methods to reconstruct the complete assessment object including
all dimension scores, risk signals, and recommendations.

---

## Integration with P1-P12

The Gate Readiness Assessor is a pure consumer of data produced by other
modules.  It never triggers execution of P1-P12 — it reads only what has
already been persisted to the `AssuranceStore`.

| Source module | Store method called | Data used |
|---------------|-------------------|-----------|
| P1 | `get_workflow_history()` | Currency step severity from latest workflow |
| P2 | `get_confidence_scores()` | Latest NISTA compliance score |
| P3 | `get_recommendations()` | Review action closure rate |
| P4 | `get_divergence_history()` | Latest divergence signal type |
| P5 | `get_schedule_history()` | Latest scheduler composite score |
| P6 | `get_override_decisions()` | Override outcome impact rate |
| P7 | `get_lessons()` | Lesson count and sentiment distribution |
| P8 | `get_assurance_activities()` | Activity count and zero-finding rate |
| P10 | `get_domain_classifications()` | Latest complexity domain |
| P11 | `get_assumptions()`, `get_assumption_validations()` | Assumption drift severity and staleness |
| P12 | `get_armm_assessments()` | Latest ARMM maturity level |

If a source module has not yet been run for a project, the corresponding
dimension receives `NO_DATA` status and is excluded from the composite
calculation.  This means the assessor can produce useful results even when
only a subset of P1-P12 modules have been used.

To maximise dimension coverage before a gate review, run the P9 Assurance
Workflow Engine (`full_assurance` workflow type) which sequences P1-P8,
then separately ensure P10 (domain classification), P11 (assumption
tracking), and P12 (ARMM) data are current.
