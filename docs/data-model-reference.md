# PDA Platform — Data Model Reference

This document describes the key Pydantic data models used throughout the
platform.  It is primarily aimed at developers integrating with
`pm-data-tools` in Python code.  For the MCP tool API reference see
[`docs/assurance.md`](./assurance.md).

---

## Canonical Project Model

The core data structure that all format parsers produce and all exporters
consume.  All fields use standard Python types with Pydantic v2 validation.

### `Project`

Top-level container returned by all parsers.

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | Unique project identifier |
| `name` | `str` | Project name |
| `description` | `str \| None` | Optional project description |
| `start_date` | `date \| None` | Project start date |
| `end_date` | `date \| None` | Project finish date |
| `tasks` | `list[Task]` | Work breakdown structure |
| `resources` | `list[Resource]` | People, equipment, materials |
| `assignments` | `list[Assignment]` | Task-resource allocations |
| `dependencies` | `list[Dependency]` | Task relationships |
| `calendars` | `list[Calendar]` | Working time definitions |
| `baselines` | `list[Baseline]` | Saved snapshots |
| `risks` | `list[Risk]` | Risk register entries |
| `issues` | `list[Issue]` | Issue log entries |
| `milestones` | `list[Milestone]` | Key deliverables |
| `metadata` | `dict[str, Any]` | Source-format-specific fields preserved for round-trip fidelity |

---

### `Task`

A single work item in the project schedule.

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | Unique task identifier within the project |
| `name` | `str` | Task name |
| `wbs` | `str \| None` | Work breakdown structure code (e.g. `1.2.3`) |
| `start_date` | `date \| None` | Planned start date |
| `end_date` | `date \| None` | Planned finish date |
| `duration_days` | `float \| None` | Duration in working days |
| `percent_complete` | `float` | Completion percentage (0–100) |
| `is_milestone` | `bool` | True if this task is a milestone |
| `is_summary` | `bool` | True if this task is a summary/parent task |
| `parent_id` | `str \| None` | ID of parent task (null for top-level tasks) |
| `critical` | `bool` | True if this task is on the critical path |
| `free_float` | `float \| None` | Free float in days |
| `total_float` | `float \| None` | Total float in days |
| `actual_start` | `date \| None` | Actual start date |
| `actual_end` | `date \| None` | Actual finish date |
| `baseline_start` | `date \| None` | Baseline planned start |
| `baseline_end` | `date \| None` | Baseline planned finish |
| `notes` | `str \| None` | Free-text notes |
| `metadata` | `dict[str, Any]` | Source-format-specific fields |

---

### `Resource`

A person, piece of equipment, or material.

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | Unique resource identifier |
| `name` | `str` | Resource name |
| `type` | `ResourceType` | `WORK`, `MATERIAL`, or `COST` |
| `email` | `str \| None` | Email address (for people) |
| `max_units` | `float` | Maximum allocation (1.0 = 100%) |
| `cost_per_hour` | `float \| None` | Standard hourly rate |
| `calendar_id` | `str \| None` | ID of the resource's working calendar |
| `metadata` | `dict[str, Any]` | Source-format-specific fields |

---

### `Assignment`

Links a task to a resource with allocation details.

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | Unique assignment identifier |
| `task_id` | `str` | ID of the assigned task |
| `resource_id` | `str` | ID of the assigned resource |
| `units` | `float` | Allocation fraction (0–1; 1.0 = 100%) |
| `work_hours` | `float \| None` | Total work in hours |
| `actual_work_hours` | `float \| None` | Actual work completed |
| `start_date` | `date \| None` | Assignment start date |
| `end_date` | `date \| None` | Assignment finish date |

---

### `Dependency`

A relationship between two tasks.

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | Unique dependency identifier |
| `predecessor_id` | `str` | ID of the predecessor task |
| `successor_id` | `str` | ID of the successor task |
| `type` | `DependencyType` | `FINISH_TO_START`, `START_TO_START`, `FINISH_TO_FINISH`, `START_TO_FINISH` |
| `lag_days` | `float` | Lag (positive) or lead (negative) in days |

---

### `Risk`

A risk register entry.

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | Unique risk identifier |
| `title` | `str` | Risk title |
| `description` | `str \| None` | Detailed description |
| `probability` | `float \| None` | Probability score (0–1) |
| `impact` | `float \| None` | Impact score (0–1) |
| `score` | `float \| None` | Combined risk score (typically probability × impact) |
| `status` | `str \| None` | Status (e.g. `Open`, `Closed`) |
| `owner` | `str \| None` | Risk owner |
| `mitigation` | `str \| None` | Mitigation action |
| `metadata` | `dict[str, Any]` | Source-format-specific fields |

---

## NISTA Compliance Models

### `ValidationResult`

Returned by `NISTAValidator.validate()`.

| Field | Type | Description |
|-------|------|-------------|
| `compliance_score` | `float` | Overall compliance score (0–100) |
| `status` | `ValidationStatus` | `COMPLIANT`, `PARTIAL`, or `NON_COMPLIANT` |
| `issues` | `list[ValidationIssue]` | List of specific compliance issues |
| `dimension_scores` | `dict[str, float]` | Per-dimension scores keyed by dimension name |
| `run_id` | `str` | Unique identifier for this validation run |
| `timestamp` | `datetime` | When the validation ran |

---

### `ValidationIssue`

A single compliance issue found during validation.

| Field | Type | Description |
|-------|------|-------------|
| `field` | `str` | The field path that failed validation |
| `severity` | `IssueSeverity` | `ERROR`, `WARNING`, or `INFO` |
| `message` | `str` | Human-readable description of the issue |
| `suggestion` | `str \| None` | Recommended fix |

---

## Assurance Models

### P2 — Longitudinal Compliance

#### `ConfidenceScoreRecord`

| Field | Type | Description |
|-------|------|-------------|
| `project_id` | `str` | Project identifier |
| `run_id` | `str` | Validation run identifier |
| `timestamp` | `datetime` | When the validation ran |
| `score` | `float` | Overall compliance score (0–100) |
| `dimension_scores` | `dict[str, float]` | Per-dimension scores |

#### `LongitudinalTrend`

Returned by `LongitudinalComplianceTracker.compute_trend()`.

| Field | Type | Description |
|-------|------|-------------|
| `project_id` | `str` | Project identifier |
| `history` | `list[ConfidenceScoreRecord]` | All score records, oldest first |
| `trend` | `TrendDirection` | `IMPROVING`, `STAGNATING`, or `DEGRADING` |
| `active_breaches` | `list[ThresholdBreach]` | Currently active threshold alerts |
| `latest_score` | `float \| None` | Most recent score (null if no history) |

#### `ThresholdBreach`

| Field | Type | Description |
|-------|------|-------------|
| `breach_type` | `str` | `DROP_BREACH` or `FLOOR_BREACH` |
| `value` | `float` | The score that triggered the breach |
| `threshold` | `float` | The threshold that was crossed |
| `detected_at` | `datetime` | When the breach was detected |

---

### P3 — Cross-Cycle Finding Analyzer

#### `ReviewAction`

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | UUID |
| `project_id` | `str` | Project identifier |
| `text` | `str` | Full text of the recommendation |
| `category` | `str` | Category label |
| `source_review_id` | `str` | Review cycle the action came from |
| `review_date` | `date` | Date of the source review |
| `status` | `ReviewActionStatus` | `OPEN`, `IN_PROGRESS`, `CLOSED`, `RECURRING` |
| `owner` | `str \| None` | Assigned owner |
| `recurrence_of` | `str \| None` | ID of the earlier action this recurs from |
| `confidence` | `float` | Extraction confidence (0–1) |
| `created_at` | `datetime` | Record creation timestamp |

#### `FindingAnalysisResult`

Returned by `FindingAnalyzer.analyse()`.

| Field | Type | Description |
|-------|------|-------------|
| `project_id` | `str` | Project identifier |
| `review_id` | `str` | Review cycle identifier |
| `actions` | `list[ReviewAction]` | All extracted and deduped actions |
| `new_actions` | `list[ReviewAction]` | Actions new to this cycle |
| `recurring_actions` | `list[ReviewAction]` | Actions recurring from earlier cycles |
| `flagged_for_review` | `list[ReviewAction]` | Low-confidence actions needing human review |

---

### P4 — Confidence Divergence Monitor

#### `DivergenceResult`

Returned by `DivergenceMonitor.check()`.

| Field | Type | Description |
|-------|------|-------------|
| `project_id` | `str` | Project identifier |
| `review_id` | `str` | Review cycle identifier |
| `confidence_score` | `float` | Overall consensus confidence (0–1) |
| `signal` | `DivergenceSignal` | Classification of this check |
| `snapshot_id` | `str` | UUID of the persisted snapshot |
| `timestamp` | `datetime` | When the check ran |

#### `DivergenceSignal`

| Field | Type | Description |
|-------|------|-------------|
| `signal_type` | `SignalType` | `STABLE`, `HIGH_DIVERGENCE`, `LOW_CONSENSUS`, `DEGRADING_CONFIDENCE` |
| `spread` | `float` | Max minus min of sample scores |
| `description` | `str` | Human-readable explanation |

---

### P5 — Adaptive Review Scheduler

#### `SchedulerRecommendation`

Returned by `AdaptiveReviewScheduler.recommend()`.

| Field | Type | Description |
|-------|------|-------------|
| `project_id` | `str` | Project identifier |
| `urgency` | `ReviewUrgency` | `IMMEDIATE`, `EXPEDITED`, `STANDARD`, `DEFERRED` |
| `recommended_date` | `date` | Suggested date for the next review |
| `composite_score` | `float` | Weighted severity composite driving the recommendation |
| `signals` | `list[SchedulerSignal]` | All signals that contributed |
| `rationale` | `str` | Plain-language explanation |
| `timestamp` | `datetime` | When the recommendation was made |

#### `SchedulerSignal`

| Field | Type | Description |
|-------|------|-------------|
| `source` | `str` | Feature code (e.g. `P1`, `P4`) |
| `signal_name` | `str` | Short signal identifier |
| `severity` | `float` | Severity contribution (0–1) |
| `description` | `str` | Human-readable description |

---

### P6 — Override Decision Logger

#### `OverrideDecision`

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | UUID |
| `project_id` | `str` | Project identifier |
| `override_type` | `OverrideType` | `GATE_PROGRESSION`, `RECOMMENDATION_DISMISSED`, `RAG_OVERRIDE`, `RISK_ACCEPTANCE`, `SCHEDULE_OVERRIDE` |
| `decision_date` | `date` | Date of the decision |
| `authoriser` | `str` | Name and role of authoriser |
| `rationale` | `str` | Reason given |
| `overridden_finding_id` | `str \| None` | ID of the specific finding overridden |
| `overridden_value` | `str \| None` | Original value |
| `override_value` | `str \| None` | Substituted value |
| `conditions` | `list[str]` | Conditions attached to the override |
| `evidence_refs` | `list[str]` | Evidence references cited |
| `outcome` | `OverrideOutcome` | `PENDING`, `NO_IMPACT`, `MINOR_IMPACT`, `SIGNIFICANT_IMPACT`, `PREVENTED_BENEFIT` |
| `outcome_date` | `date \| None` | Date outcome was observed |
| `outcome_notes` | `str \| None` | Notes about the outcome |
| `created_at` | `datetime` | Record creation timestamp |

#### `OverridePatternSummary`

Returned by `OverrideDecisionLogger.analyse_patterns()`.

| Field | Type | Description |
|-------|------|-------------|
| `project_id` | `str` | Project identifier |
| `total_overrides` | `int` | Total number of override decisions |
| `by_type` | `dict[str, int]` | Count of overrides by type |
| `by_outcome` | `dict[str, int]` | Count of overrides by outcome |
| `adverse_rate` | `float` | Fraction of overrides with an adverse outcome |
| `most_common_type` | `str \| None` | Most frequently occurring override type |

---

### P7 — Lessons Learned Knowledge Engine

#### `LessonRecord`

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | UUID |
| `project_id` | `str` | Project identifier |
| `title` | `str` | Short lesson title |
| `description` | `str` | Full description |
| `category` | `LessonCategory` | Domain category |
| `sentiment` | `LessonSentiment` | `POSITIVE`, `NEGATIVE`, `NEUTRAL` |
| `project_type` | `str \| None` | Project type (e.g. `ICT`, `Infrastructure`) |
| `project_phase` | `str \| None` | Phase the lesson arose in |
| `department` | `str \| None` | Owning department |
| `tags` | `list[str]` | Searchable tags |
| `date_recorded` | `date` | Date recorded |
| `recorded_by` | `str \| None` | Person who recorded it |
| `impact_description` | `str \| None` | Description of impact |
| `created_at` | `datetime` | Record creation timestamp |

#### `LessonSearchResponse`

Returned by `LessonsKnowledgeEngine.search()`.

| Field | Type | Description |
|-------|------|-------------|
| `query` | `str` | The search query |
| `results` | `list[LessonRecord]` | Matching lessons |
| `total` | `int` | Total number of results |
| `semantic_available` | `bool` | Whether semantic search was used |

---

### P8 — Assurance Overhead Optimiser

#### `AssuranceActivity`

| Field | Type | Description |
|-------|------|-------------|
| `id` | `str` | UUID |
| `project_id` | `str` | Project identifier |
| `activity_type` | `ActivityType` | Type of assurance activity |
| `description` | `str` | Description of the activity |
| `date` | `date` | Date of the activity |
| `effort_hours` | `float` | Person-hours invested |
| `participants` | `int` | Number of participants |
| `artefacts_reviewed` | `list[str]` | Artefact identifiers reviewed |
| `findings_count` | `int` | Number of findings produced |
| `confidence_before` | `float \| None` | Confidence score before the activity |
| `confidence_after` | `float \| None` | Confidence score after the activity |
| `created_at` | `datetime` | Record creation timestamp |

#### `OverheadAnalysis`

Returned by `AssuranceOverheadOptimiser.analyse()`.

| Field | Type | Description |
|-------|------|-------------|
| `project_id` | `str` | Project identifier |
| `total_hours` | `float` | Total person-hours across all activities |
| `total_activities` | `int` | Number of activities |
| `findings_per_hour` | `float` | Average findings produced per hour |
| `efficiency_rating` | `str` | `EFFICIENT`, `MODERATE`, or `INEFFICIENT` |
| `wasteful_patterns` | `list[WastefulPattern]` | Identified wasteful patterns |
| `recommendations` | `list[str]` | Recommended actions to reduce overhead |
| `timestamp` | `datetime` | When the analysis ran |

---

### P9 — Assurance Workflow Engine

#### `WorkflowResult`

Returned by `AssuranceWorkflowEngine.execute()`.

| Field | Type | Description |
|-------|------|-------------|
| `workflow_id` | `str` | UUID of this execution |
| `project_id` | `str` | Project identifier |
| `workflow_type` | `WorkflowType` | Workflow plan executed |
| `health` | `ProjectHealth` | `HEALTHY`, `ATTENTION_NEEDED`, `AT_RISK`, `CRITICAL` |
| `steps` | `list[WorkflowStepResult]` | Result of each step |
| `risk_signals` | `list[WorkflowRiskSignal]` | All risk signals, sorted by severity descending |
| `recommended_actions` | `list[str]` | Prioritised recommended actions |
| `executive_summary` | `str` | Plain-language summary |
| `started_at` | `datetime` | Execution start timestamp |
| `completed_at` | `datetime` | Execution end timestamp |
| `duration_ms` | `float` | Total execution duration in milliseconds |

#### `WorkflowStepResult`

| Field | Type | Description |
|-------|------|-------------|
| `step_name` | `str` | Name of the step (e.g. `artefact_currency`) |
| `feature` | `str` | Feature code (e.g. `P1`) |
| `status` | `WorkflowStepStatus` | `COMPLETED`, `SKIPPED`, `FAILED`, `NOT_APPLICABLE` |
| `risk_signals` | `list[WorkflowRiskSignal]` | Signals emitted by this step |
| `summary` | `str` | Brief summary of this step's output |
| `error_message` | `str \| None` | Error detail if status is `FAILED` |
| `duration_ms` | `float` | Step execution time in milliseconds |

#### `WorkflowRiskSignal`

| Field | Type | Description |
|-------|------|-------------|
| `source` | `str` | Feature code (e.g. `P1`) |
| `signal_name` | `str` | Short signal identifier |
| `severity` | `float` | Normalised severity (0–1) |
| `detail` | `str` | Human-readable explanation |

---

### P10 — Project Domain Classifier

#### `ClassificationResult`

Returned by `ProjectDomainClassifier.classify()`.

| Field | Type | Description |
|-------|------|-------------|
| `classification_id` | `str` | UUID of this classification |
| `project_id` | `str` | Project identifier |
| `domain` | `ComplexityDomain` | `CLEAR`, `COMPLICATED`, `COMPLEX`, `CHAOTIC` |
| `composite_score` | `float` | Final weighted composite score (0–1) |
| `explicit_score` | `float \| None` | Score from explicit indicators only |
| `derived_score` | `float \| None` | Score from store-derived signals only |
| `indicators` | `list[DomainIndicator]` | All indicators used |
| `profile` | `DomainAssuranceProfile` | Recommended assurance profile |
| `classified_at` | `datetime` | When the classification ran |

#### `DomainIndicator`

| Field | Type | Description |
|-------|------|-------------|
| `name` | `str` | Indicator identifier |
| `raw_value` | `float` | Value as supplied (0–1) |
| `complexity_contribution` | `float` | Contribution after inversion for inverse indicators |
| `weight` | `float` | Relative weight within the explicit set |
| `description` | `str` | Human-readable explanation |

#### `DomainAssuranceProfile`

| Field | Type | Description |
|-------|------|-------------|
| `domain` | `ComplexityDomain` | Domain this profile applies to |
| `review_frequency_days` | `int` | Recommended days between reviews (90 / 60 / 42 / 14) |
| `governance_intensity` | `str` | `LIGHT`, `STANDARD`, `ENHANCED`, `INTENSIVE` |
| `recommended_tools` | `list[str]` | Assurance feature codes recommended for this domain |
| `description` | `str` | Plain-language description of this domain |

---

## Serialisation notes

All models use Pydantic v2.  To serialise a model to JSON including enums as
string values (not `EnumClass.VALUE`), always use `mode='json'`:

```python
result = engine.execute(project_id="PROJ-001", workflow_type=WorkflowType.FULL_ASSURANCE)

# Correct — enums serialised as strings
json_str = json.dumps(result.model_dump(mode='json'))

# Incorrect — enums serialised as EnumClass.VALUE
json_str = json.dumps(result.model_dump())
```

---

**Last Updated**: March 2026
**Maintained by**: PDA Platform Contributors
