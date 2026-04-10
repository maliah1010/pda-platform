# Benefits Realisation Management (P13) — Developer Reference

This document describes the Benefits Realisation Management module in the PDA
Platform, designated **P13** in the assurance capability series.

---

## Overview

The BRM module provides eight MCP tools for tracking, measuring, and analysing
the realisation of project benefits:

- **`ingest_benefit`**: Register a benefit or dis-benefit with full
  IPA/Green Book-compliant metadata and multi-axis classification.
- **`track_benefit_measurement`**: Record a measurement against a registered
  benefit. Computes drift from baseline, realisation percentage, and trend.
- **`get_benefits_health`**: Portfolio-level health assessment returning
  realisation rates, at-risk counts, and an overall health score (0.0–1.0).
- **`map_benefit_dependency`**: Create nodes and typed edges in the Benefits
  Dependency Network (directed acyclic graph).
- **`get_benefit_dependency_network`**: Retrieve the full or filtered DAG
  for a project with node statuses and edge types.
- **`forecast_benefit_realisation`**: Linear extrapolation forecast from
  measurement time-series to estimate probability of target achievement.
- **`detect_benefits_drift`**: Time-series analysis detecting statistically
  significant deviations from planned realisation profiles.
- **`get_benefits_cascade_impact`**: BFS propagation through the dependency
  network to identify all downstream nodes affected by a change.

---

## Architecture

```
pm_data_tools/
  assurance/
    benefits.py           # BenefitsTracker, Benefit, BenefitMeasurement,
                          # DependencyNode, DependencyEdge, enums, models
  db/
    store.py              # AssuranceStore — 4 new tables, 12 new methods

pm_mcp_servers/
  pm_brm/
    __init__.py
    server.py             # 8 MCP tool definitions + async handlers
    registry.py           # TOOLS re-export + dispatch dict
  pda_platform/
    server.py             # Unified server — imports pm_brm registry
```

All SQLite tables use `CREATE TABLE IF NOT EXISTS` so the store is safe to
initialise from any subset of features.

---

## Package Dependencies

| Feature | Required extras |
|---------|----------------|
| Benefits Register | none (stdlib + pydantic) |
| Measurement Tracking | none |
| Dependency Network | none |
| Health Analysis | none |
| Drift Detection | none |
| Forecasting | none |

No additional dependencies beyond the existing `pm-data-tools` requirements.

---

## Data Models

### Enums

#### `BenefitStatus`

| Value | Description |
|-------|-------------|
| `IDENTIFIED` | Benefit recognised but not yet baselined |
| `PLANNED` | Baseline and target established |
| `REALIZING` | Active measurement tracking |
| `ACHIEVED` | Target value met or exceeded |
| `EVAPORATED` | Benefit will not be realised |
| `CANCELLED` | Deliberately removed from scope |

#### `FinancialType` (Green Book)

| Value | Description |
|-------|-------------|
| `CASH_RELEASING` | Direct financial savings reducing government spend |
| `NON_CASH_RELEASING` | Financial value not reducing cash expenditure |
| `QUANTIFIABLE` | Measurable in non-financial units |
| `QUALITATIVE` | Observable but not numerically measurable |

#### `RecipientType` (IPA)

| Value | Description |
|-------|-------------|
| `GOVERNMENT` | Internal departmental accrual |
| `PRIVATE_SECTOR` | Benefits to private sector partners |
| `WIDER_UK_PUBLIC` | Benefits to the wider UK public |

#### `Explicitness` (Ward & Daniel)

| Value | Description |
|-------|-------------|
| `FINANCIAL` | Directly measurable in monetary terms |
| `QUANTIFIABLE` | Measurable in numeric units but not money |
| `MEASURABLE` | Observable change against a baseline |
| `OBSERVABLE` | Expert judgment required |

#### `IndicatorType`

| Value | Description |
|-------|-------------|
| `LEADING` | Predictive metric gathered during execution |
| `LAGGING` | Post-implementation outcome metric |

#### `NodeType` (Dependency Network)

| Value | Description |
|-------|-------------|
| `STRATEGIC_OBJECTIVE` | Terminal goal nodes |
| `END_BENEFIT` | Ultimate measurable value (lagging KPIs) |
| `INTERMEDIATE_BENEFIT` | Stepping-stone benefits (leading KPIs) |
| `BUSINESS_CHANGE` | Operational modifications required |
| `ENABLER` | Capabilities the project builds |
| `PROJECT_OUTPUT` | Root deliverables linked to schedule |

#### `EdgeType`

| Value | Description |
|-------|-------------|
| `DEPENDS_ON` | Target depends on source being delivered |
| `CONTRIBUTES_TO` | Source contributes to target realisation |
| `ENABLES` | Source enables target to occur |

#### `IpaLifecycleStage`

| Value | Business Case Stage |
|-------|-------------------|
| `DEFINE_SUCCESS` | Opportunity framing |
| `IDENTIFY_QUANTIFY` | Strategic Outline Case |
| `VALUE_APPRAISE` | Outline Business Case |
| `PLAN_REALISE` | Full Business Case |
| `REVIEW` | Post-delivery operations |

### Core Models

#### `Benefit`

```python
class Benefit(BaseModel):
    id: str                                    # UUID4
    project_id: str
    title: str
    description: str                           # Must pass MSP DOAM test
    is_disbenefit: bool = False
    status: BenefitStatus = IDENTIFIED
    financial_type: FinancialType
    recipient_type: RecipientType
    explicitness: Explicitness = QUANTIFIABLE
    baseline_value: float | None
    baseline_date: date | None
    target_value: float | None
    target_date: date | None
    current_actual_value: float | None
    interim_targets: list[dict]                # [{date, value}]
    measurement_kpi: str | None
    measurement_frequency: MeasurementFrequency = QUARTERLY
    indicator_type: IndicatorType = LAGGING
    owner_sro: str | None
    benefits_owner: str | None
    business_change_owner: str | None
    ipa_lifecycle_stage: IpaLifecycleStage = IDENTIFY_QUANTIFY
    business_case_ref: str | None
    gate_alignment: str | None
    contributing_projects: list[str]
    associated_risks: list[str]
    associated_assumptions: list[str]
    confidence_score: float | None             # AI-derived, 0-100
    created_at: datetime
    updated_at: datetime
```

#### `BenefitMeasurement`

```python
class BenefitMeasurement(BaseModel):
    id: str                                    # UUID4
    benefit_id: str
    project_id: str
    measured_at: datetime
    value: float
    source: MeasurementSource = MANUAL
    drift_pct: float                           # Drift from baseline
    drift_severity: DriftSeverity
    realisation_pct: float | None              # % of target achieved
    trend_direction: TrendDirection | None
    notes: str | None
```

#### `DependencyNode`

```python
class DependencyNode(BaseModel):
    id: str                                    # UUID4
    project_id: str
    node_type: NodeType
    title: str
    description: str | None
    status: str = "PLANNED"
    owner: str | None
    target_date: date | None
    benefit_id: str | None                     # Links to benefits table
```

#### `DependencyEdge`

```python
class DependencyEdge(BaseModel):
    id: str                                    # UUID4
    project_id: str
    source_node: str
    target_node: str
    edge_type: EdgeType = DEPENDS_ON
    assumption_id: str | None                  # Links to assumptions table
    risk_id: str | None
    notes: str | None
```

---

## BenefitsTracker API

```python
from pm_data_tools.assurance.benefits import (
    BenefitsTracker, Benefit, FinancialType, RecipientType,
)
from pm_data_tools.db.store import AssuranceStore

store = AssuranceStore()
tracker = BenefitsTracker(store=store)
```

### CRUD Operations

| Method | Description |
|--------|-------------|
| `ingest(benefit)` | Persist a benefit, return with ID |
| `ingest_batch(benefits)` | Persist multiple, return count |
| `get_benefits(project_id, status?, financial_type?)` | Query with filters |
| `update_status(benefit_id, status)` | Update lifecycle status |

### Measurement Tracking

| Method | Description |
|--------|-------------|
| `record_measurement(benefit_id, value, source?, notes?)` | Record + compute drift |
| `get_measurements(benefit_id)` | All measurements, oldest first |

### Health Analysis

| Method | Description |
|--------|-------------|
| `analyse_health(project_id)` | Full portfolio health report |

### Dependency Network

| Method | Description |
|--------|-------------|
| `add_node(node)` | Add a node to the DAG |
| `add_edge(edge)` | Add an edge (validates acyclicity) |
| `get_network(project_id)` | Full DAG as {nodes, edges} |
| `validate_dag(project_id)` | Check for cycles |

### Cascade & Drift

| Method | Description |
|--------|-------------|
| `find_cascade_impact(node_id)` | BFS downstream propagation |
| `detect_drift(project_id)` | All drift results, worst first |

### Forecasting

| Method | Description |
|--------|-------------|
| `forecast(benefit_id)` | Linear extrapolation forecast |

---

## Database Schema

### `benefits` table

The benefits register. 28+ fields supporting IPA, Green Book, MSP, PMI, and
APMG classification simultaneously.

### `benefit_measurements` table

Time-series measurement tracking with drift analysis. Foreign key to `benefits`.

### `benefit_dependency_nodes` table

Nodes in the benefits dependency network (DAG). Six node types from Strategic
Objectives down to Project Outputs.

### `benefit_dependency_edges` table

Directed edges with typed relationships. Unique constraint on
`(source_node, target_node)`. Optional links to assumptions and risks.

---

## Integration Points

| BRM Feature | Existing Module | Integration |
|-------------|----------------|-------------|
| Drift detection | P11 Assumptions | Reuses `DriftSeverity` enum and severity weights |
| Cascade impact | P11 Assumptions | Cross-references assumption drift with benefit dependencies |
| Dependency edges | Assumptions table | `assumption_id` field links edges to assumption records |
| Health scoring | P12 ARMM | Follows same severity-weighted composite scoring philosophy |
| Lessons | P7 Lessons Engine | Existing `BENEFITS_REALISATION` category available |
| Unified server | pda-platform | pm_brm registry imported as 6th module |

---

## MCP Tools

### `ingest_benefit`

Register a benefit with full metadata.

**Required**: `project_id`, `title`, `description`, `financial_type`, `recipient_type`

**Optional**: `is_disbenefit`, `baseline_value`, `baseline_date`, `target_value`,
`target_date`, `measurement_kpi`, `measurement_frequency`, `indicator_type`,
`explicitness`, `owner_sro`, `benefits_owner`, `ipa_lifecycle_stage`,
`interim_targets`, `contributing_projects`, `associated_assumptions`,
`associated_risks`, `business_case_ref`, `db_path`

### `track_benefit_measurement`

Record a measurement and compute drift/trend.

**Required**: `benefit_id`, `value`

**Optional**: `source`, `notes`, `db_path`

### `get_benefits_health`

Portfolio-level health assessment.

**Required**: `project_id`

**Optional**: `status_filter`, `db_path`

### `map_benefit_dependency`

Create nodes and edges in the dependency DAG.

**Required**: `project_id`, `source_node_id`, `target_node_id`, `edge_type`

**Optional**: `source_node`, `target_node` (inline creation), `assumption_id`,
`risk_id`, `notes`, `db_path`

### `get_benefit_dependency_network`

Retrieve the full DAG.

**Required**: `project_id`

**Optional**: `node_type_filter`, `db_path`

### `forecast_benefit_realisation`

Linear extrapolation forecast.

**Required**: `benefit_id`

**Optional**: `db_path`

### `detect_benefits_drift`

Time-series drift detection.

**Required**: `project_id`

**Optional**: `severity_filter`, `db_path`

### `get_benefits_cascade_impact`

Cascade impact propagation through DAG.

**Required**: `node_id`

**Optional**: `db_path`
