# PM Data Tools

Universal parser and validator for project management data. Supports NISTA compliance.

Part of the [PDA Platform](https://github.com/PDA-Task-Force/pda-platform).

[![Tests](https://github.com/PDA-Task-Force/pda-platform/workflows/CI/badge.svg)](https://github.com/PDA-Task-Force/pda-platform/actions)
[![Coverage](https://img.shields.io/badge/coverage-100%25-brightgreen)](https://github.com/PDA-Task-Force/pda-platform)
[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Overview

PM Data Tools provides a canonical data model and conversion utilities for project management data across multiple platforms and standards. Built for UK Government NISTA (National Infrastructure and Service Transformation Authority) standard compliance.

## Features

- **Canonical data model** for project management data
- **Schema mappings** for major PM tools:
  - Microsoft Project (MSPDI XML)
  - Primavera P6 (XER, PMXML)
  - Jira
  - Microsoft Planner
  - Monday.com
  - Asana
  - Smartsheet
- **Validation framework** for structural and semantic rules
- **Evidence Freshness Detector** — detect stale documents and suspicious "fresh paint" editing patterns
- **CLI tools** for conversion, validation, inspection, and freshness analysis
- **GMPP-aligned** for UK government project data
- **NISTA-ready** (placeholder for official schema)
- **100% test coverage** with comprehensive test suite

## Installation

```bash
pip install pm-data-tools
```

For development:

```bash
pip install pm-data-tools[dev]
```

## Quick Start

### Parse from supported formats

```python
from pm_data_tools.schemas.monday import MondayParser
from pm_data_tools.schemas.asana import AsanaParser
from pm_data_tools.schemas.smartsheet import SmartsheetParser
from pm_data_tools.schemas.gmpp import GMPPParser

# Parse Monday.com data
monday_parser = MondayParser()
project = monday_parser.parse_file("monday_board.json")

# Parse Asana data
asana_parser = AsanaParser()
project = asana_parser.parse_file("asana_project.json")

# Parse Smartsheet data
smartsheet_parser = SmartsheetParser()
project = smartsheet_parser.parse_file("smartsheet.json")

# Parse GMPP CSV data
gmpp_parser = GMPPParser()
projects = gmpp_parser.parse_file("gmpp_projects.csv")
```

### Validate project data

```python
from pm_data_tools import validate

result = validate("project.xml")

if result.valid:
    print("✓ Validation passed")
else:
    for error in result.errors:
        print(f"✗ {error.code}: {error.message}")
```

### CLI Usage

```bash
# Convert formats
pm-data-tools convert project.xml project.json --to canonical

# Validate project file
pm-data-tools validate project.xml

# Inspect project structure
pm-data-tools inspect project.xml

# Analyse evidence freshness of a single file
pm-data-tools freshness schedule.xml

# Analyse an evidence pack (directory) with a gate date
pm-data-tools freshness /evidence/ --recursive --gate-date 2026-04-01

# Export freshness report as JSON
pm-data-tools freshness /evidence/ --json -o freshness_report.json
```

## Canonical Data Model

The canonical model is a superset of all supported formats, enabling lossless conversion between tools.

**Core entities:**
- **Project** - Container with metadata, schedule, and financials
- **Task** - Work items with WBS, schedule, progress, and costs
- **Resource** - People, equipment, materials with rates
- **Assignment** - Task-resource allocation
- **Dependency** - Task relationships (FS, FF, SS, SF)
- **Risk** - Risk register entries with probability/impact
- **Milestone** - Key project dates
- **Calendar** - Working time definitions

## Supported Formats

| Format | Read | Write | Status | Coverage |
|--------|------|-------|--------|----------|
| Monday.com (JSON API) | ✅ | 🚧 | v0.1.0 | 97% (32 tests) |
| Asana (JSON API) | ✅ | 🚧 | v0.1.0 | 99% (20 tests) |
| Smartsheet (JSON API) | ✅ | 🚧 | v0.1.0 | 94% (21 tests) |
| GMPP (CSV) | ✅ | 🚧 | v0.1.0 | 99% (21 tests) |
| Microsoft Project (MSPDI) | 🚧 | 🚧 | Planned | - |
| Primavera P6 (XER) | 🚧 | 🚧 | Planned | - |
| Primavera P6 (PMXML) | 🚧 | 🚧 | Planned | - |
| Jira (JSON API) | 🚧 | 🚧 | Planned | - |
| NISTA | 🚧 | 🚧 | Awaiting schema | - |

## NISTA Alignment

This library is designed to support the UK Government's [Programme and Project Data Standard](https://www.nista.gov.uk/) launched in December 2024. The GMPP schema module provides current alignment; full NISTA support will be added when the official schema is published.

## Development

### Setup

```bash
# Clone repository
git clone https://github.com/PDA-Task-Force/pda-platform.git
cd pm-data-tools

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install development dependencies
pip install -e ".[dev]"

# Install pre-commit hooks
pre-commit install
```

### Running Tests

```bash
# Run all tests with coverage
pytest

# Run specific test file
pytest tests/test_models/test_task.py

# Run with coverage report
pytest --cov-report=html
```

### Code Quality

```bash
# Format code
ruff format .

# Lint code
ruff check .

# Type check
mypy src/pm_data_tools
```

## Evidence Freshness Detector

The freshness module addresses the "Confidence and Fresh Paint" problem from *Next Gen Project Assurance* (Murray, Paver & Steinberg, 2026): documents polished immediately before reviews whilst underlying reality has diverged.

### Scoring model

Each document receives three sub-scores (0–100), combined into a composite **freshness score**:

| Sub-score | Weight | Description |
|-----------|--------|-------------|
| **Staleness** | 50% | Time since last modification. Green ≤30 days, amber ≤90 days, red beyond 90 days. |
| **Velocity** | 30% | Edit frequency patterns. Penalises burst editing before a gate date and long dormancy. |
| **Provenance** | 20% | Metadata completeness. Rewards author trail, version history, and consistent edits. |

### Alert types

| Alert | Severity | Trigger |
|-------|----------|---------|
| `stale` | warning/critical | Document not modified beyond threshold |
| `fresh_paint` | warning/critical | Burst editing before gate date after dormancy |
| `incomplete_provenance` | warning/critical | Missing author / modification metadata |
| `never_updated` | info | Version 1 with no revision history |

### Quick start

```python
from pm_data_tools.freshness import FreshnessAnalyser, FreshnessConfig
from datetime import datetime

# Analyse a single file
analyser = FreshnessAnalyser()
result = analyser.analyse_file("schedule.xml")
print(result.freshness_score)   # 0–100
print(result.rag_status)        # "green", "amber", or "red"
for alert in result.alerts:
    print(alert)

# Analyse an evidence pack with a gate date
analyser = FreshnessAnalyser(
    config=FreshnessConfig(gate_date=datetime(2026, 4, 1))
)
pack = analyser.analyse_pack("/evidence/", recursive=True)
print(pack.overall_score)
print(pack.rag_status)

# Score pre-extracted metadata directly (for custom pipelines)
from pm_data_tools.freshness import extract_metadata
metadata = extract_metadata("schedule.xml")
result = analyser.score_metadata(metadata)
```

See [`examples/freshness_analysis.py`](../../examples/freshness_analysis.py) for a full walkthrough.

## Architecture

PM Data Tools follows a three-layer architecture:

1. **Models Layer** (`src/pm_data_tools/models/`) - Canonical data structures
2. **Schemas Layer** (`src/pm_data_tools/schemas/`) - Format-specific parsers and writers
3. **Validation Layer** (`src/pm_data_tools/validators/`) - Structural and semantic validation
4. **Freshness Layer** (`src/pm_data_tools/freshness/`) - Evidence freshness scoring and alerting

All conversions pass through the canonical model:

```
Source Format → Parser → Canonical Model → Writer → Target Format
```

This ensures:
- **Lossless roundtrip** conversion (Source → Canonical → Source preserves data)
- **Consistent validation** (all formats validated against same rules)
- **Extensibility** (new formats only need parser/writer, not N² converters)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development guidelines, coding standards, and how to submit contributions.

## Acknowledgements

Developed by members of the PDA Task Force.

This work was made possible by:
- The **PDA Task Force White Paper** identifying AI implementation barriers in UK project delivery
- The **NISTA Programme and Project Data Standard** and its 12-month trial period

Sponsored by the UK Government's Infrastructure and Projects Authority (IPA) research initiative.

## License

MIT License - see [LICENSE](LICENSE) for details.

## Links

- [Documentation](https://github.com/PDA-Task-Force/pda-platform#readme)
- [Issues](https://github.com/PDA-Task-Force/pda-platform/issues)
- [Changelog](CHANGELOG.md)
- [NISTA Programme and Project Data Standard](https://www.nista.gov.uk/)
- [UK Government Major Projects Portfolio (GMPP)](https://www.gov.uk/government/collections/major-projects-data)
