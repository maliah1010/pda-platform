# PM Data Tools

Universal parser, validator, and assurance toolkit for project management data.
Supports NISTA compliance, longitudinal score tracking, and cross-cycle review
action analysis.

Part of the [PDA Platform](https://github.com/antnewman/pda-platform).

[![Tests](https://github.com/antnewman/pda-platform/workflows/CI/badge.svg)](https://github.com/antnewman/pda-platform/actions)
[![Coverage](https://img.shields.io/badge/coverage-100%25-brightgreen)](https://github.com/antnewman/pda-platform)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Overview

PM Data Tools provides a canonical data model and conversion utilities for project
management data across multiple platforms and standards. Built for UK Government
NISTA (National Infrastructure and Service Transformation Authority) standard
compliance and assurance quality tracking.

## Features

- **Canonical data model** for project management data
- **Schema mappings** for major PM tools (MS Project, Primavera P6, Jira, Monday,
  Asana, Smartsheet, GMPP, NISTA)
- **NISTA compliance validation** at three strictness levels
- **Longitudinal Compliance Tracker** — persists NISTA scores over time, detects
  trends and threshold breaches
- **Cross-Cycle Finding Analyzer** — AI-powered extraction, deduplication, and
  recurrence detection for review actions
- **Artefact Currency Validator** — detects stale artefacts and last-minute
  compliance updates before gate reviews *(planned v0.4.0)*
- **SQLite-backed persistence** shared across all assurance features
- **CLI tools** for conversion, validation, and inspection
- **100% test coverage** with comprehensive test suite

## Installation

```bash
pip install pm-data-tools
```

For assurance features with recurrence detection:

```bash
pip install pm-data-tools[assurance]
pip install "agent-task-planning[mining]"
```

For development:

```bash
pip install pm-data-tools[dev]
```

## Quick Start

### Parse from supported formats

```python
from pm_data_tools.schemas.monday import MondayParser
from pm_data_tools.schemas.gmpp import GMPPParser

monday_parser = MondayParser()
project = monday_parser.parse_file("monday_board.json")

gmpp_parser = GMPPParser()
projects = gmpp_parser.parse_file("gmpp_projects.csv")
```

### Validate NISTA compliance

```python
from pm_data_tools.schemas.nista import NISTAValidator, StrictnessLevel

validator = NISTAValidator(strictness=StrictnessLevel.STANDARD)
result = validator.validate(data)

print(f"Compliant: {result.compliant}")
print(f"Score: {result.compliance_score}%")
```

### Track compliance scores over time (P2)

```python
from pm_data_tools.schemas.nista import NISTAValidator, LongitudinalComplianceTracker
from pm_data_tools.db import AssuranceStore

store = AssuranceStore()
tracker = LongitudinalComplianceTracker(store=store)

# Score is persisted as a side effect of validation
validator = NISTAValidator()
result = validator.validate(data, project_id="PROJ-001", history=tracker)

trend = tracker.compute_trend("PROJ-001")   # IMPROVING / STAGNATING / DEGRADING
breaches = tracker.check_thresholds("PROJ-001")  # floor and drop breaches
```

### Extract and track review actions (P3)

```python
from agent_planning.confidence import ConfidenceExtractor
from agent_planning.providers.anthropic import AnthropicProvider
from pm_data_tools.assurance import FindingAnalyzer, RecurrenceDetector

provider = AnthropicProvider(api_key="...")
ce = ConfidenceExtractor(provider)

analyzer = FindingAnalyzer(
    extractor=ce,
    recurrence_detector=RecurrenceDetector(),
)

result = await analyzer.extract(
    review_text="...",
    review_id="review-2026-Q1",
    project_id="PROJ-001",
)

for action in result.recommendations:
    print(f"[{action.status.value}] {action.text}")
```

### CLI Usage

```bash
pm-data-tools convert project.xml project.json --to canonical
pm-data-tools validate project.xml
pm-data-tools inspect project.xml
```

## Assurance Features

### P1 — Artefact Currency Validator *(planned v0.4.0)*

Detects two failure modes in gate evidence:

- **Outdated artefacts**: documents not updated within the configured staleness
  window (default 90 days).
- **Anomalous updates**: documents updated within a short window before the gate
  date — consistent with last-minute compliance updates rather than genuine
  revision. Status: `CURRENT / OUTDATED / ANOMALOUS_UPDATE`.

### P2 — Longitudinal Compliance Tracker

```
from pm_data_tools.schemas.nista.longitudinal import (
    LongitudinalComplianceTracker,
    ComplianceThresholdConfig,
    TrendDirection,
    ThresholdBreach,
)
```

| Class | Description |
|-------|-------------|
| `LongitudinalComplianceTracker` | Persist scores, compute trend, detect breaches |
| `ComplianceThresholdConfig` | Configurable drop tolerance, floor, stagnation window |
| `TrendDirection` | `IMPROVING / STAGNATING / DEGRADING` |
| `ThresholdBreach` | Drop or floor breach with message |

### P3 — Cross-Cycle Finding Analyzer

```
from pm_data_tools.assurance import (
    FindingAnalyzer,
    ReviewAction,
    ReviewActionStatus,
    FindingAnalysisResult,
    RecurrenceDetector,
)
```

| Class | Description |
|-------|-------------|
| `FindingAnalyzer` | Extract, deduplicate, and persist review actions |
| `ReviewAction` | Single action with lifecycle status and confidence |
| `ReviewActionStatus` | `OPEN / IN_PROGRESS / CLOSED / RECURRING` |
| `RecurrenceDetector` | Sentence-transformer cosine similarity across cycles |

Full API reference: [`docs/assurance.md`](../../docs/assurance.md)

## Supported Formats

| Format | Read | Write | Status |
|--------|------|-------|--------|
| Monday.com (JSON API) | ✅ | — | v0.1.0 |
| Asana (JSON API) | ✅ | — | v0.1.0 |
| Smartsheet (JSON API) | ✅ | — | v0.1.0 |
| GMPP (CSV) | ✅ | ✅ | v0.1.0 |
| NISTA (JSON/CSV/Excel) | ✅ | ✅ | v0.2.0 |
| Microsoft Project (MSPDI) | — | — | Planned |
| Primavera P6 (XER) | — | — | Planned |
| Jira (JSON API) | — | — | Planned |

## Architecture

```
src/pm_data_tools/
  db/
    store.py              # AssuranceStore — shared SQLite persistence
  schemas/
    nista/
      longitudinal.py     # LongitudinalComplianceTracker (P2)
      validator.py        # NISTAValidator
      parser.py
      exporter.py
  assurance/
    models.py             # ReviewAction, ReviewActionStatus, FindingAnalysisResult
    analyzer.py           # FindingAnalyzer (P3)
    recurrence.py         # RecurrenceDetector
  gmpp/                   # GMPP quarterly reporting and AI narratives
  integrations/nista/     # NISTA API client (OAuth 2.0 + mTLS)
```

## Development

```bash
git clone https://github.com/antnewman/pda-platform.git
cd pda-platform/packages/pm-data-tools
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -e ".[dev]"
```

### Running Tests

```bash
pytest                          # all tests
pytest tests/test_assurance/    # P2 and P3 assurance tests only
pytest --cov-report=html        # with coverage report
```

### Code Quality

```bash
ruff format .
ruff check .
mypy src/pm_data_tools
```

## Documentation

- [Assurance — Developer Reference](../../docs/assurance.md)
- [Assurance — Practitioner Guide](../../docs/assurance-for-practitioners.md)
- [NISTA Integration Reference](docs/nista/README.md)
- [Migration Guide](docs/nista/migration-guide.md)
- [Changelog](CHANGELOG.md)

## License

MIT License — see [LICENSE](LICENSE) for details.

## Acknowledgements

Fork maintained by Ant Newman ([github.com/antnewman](https://github.com/antnewman)).

Original work by members of the PDA Task Force. Made possible by:
- The **PDA Task Force White Paper** identifying AI implementation barriers in UK
  project delivery
- The **NISTA Programme and Project Data Standard** and its 12-month trial period
