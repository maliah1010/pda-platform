# PDA Platform

**Open-source infrastructure for AI-enabled project delivery.**

Home of **OPAL** (Open Project Assurance Library), **ARMM** (Agent Readiness Maturity Model), and **UDS** (Universal Dashboard Specification).

## Acknowledgement

This project is a fork of https://github.com/PDA-Task-Force/pda-platform originally developed by the PDA Task Force. This fork is maintained independently by https://github.com/antnewman and is not affiliated with the original creators.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.18133574.svg)](https://doi.org/10.5281/zenodo.18133574)
[![PyPI - pm-data-tools](https://img.shields.io/pypi/v/pm-data-tools)](https://pypi.org/project/pm-data-tools/)

## Overview

Government projects fail because assumptions go unchecked, risks go unquantified, and assurance happens too late.

The PDA Platform is the open-source assurance and governance layer for project delivery. It connects to whatever tools you already use — Jira, MS Project, Monday, Smartsheet, Primavera P6 — and provides continuous, AI-native project assurance through any AI that supports MCP.

**Try it now:** Connect to the live MCP server from claude.ai in 30 seconds. See [docs/hackathon/QUICKSTART.md](docs/hackathon/QUICKSTART.md).

## The Three Pillars

```
TortoiseAI
  └── PDA Platform (open source, DOI-cited)
        ├── OPAL   — Open Project Assurance Library
        ├── ARMM   — Agent Readiness Maturity Model
        └── UDS    — Universal Dashboard Specification
```

### OPAL — Open Project Assurance Library

The definitive open-source assurance framework for project delivery. Currently 12 core modules, community-extensible:

| Module | Name | What it does |
|--------|------|-------------|
| OPAL-1 | Artefact Currency | Detects stale documents and suspicious last-minute updates |
| OPAL-2 | Longitudinal Compliance | NISTA compliance score tracking, trends, threshold breaches |
| OPAL-3 | Review Action Tracker | AI extraction of review actions, cross-cycle recurrence detection |
| OPAL-4 | Confidence Divergence | AI confidence monitoring, sample consensus, degradation alerts |
| OPAL-5 | Adaptive Scheduling | Review cadence driven by OPAL-1 to OPAL-4 signals |
| OPAL-6 | Governance Overrides | Override decision logging with full audit trail |
| OPAL-7 | Lessons Learned | Knowledge engine with category, sentiment, and impact tracking |
| OPAL-8 | Overhead Optimiser | Assurance effort tracking and efficiency recommendations |
| OPAL-9 | Workflow Orchestration | Agentic multi-step assurance workflows |
| OPAL-10 | Domain Classification | Cynefin domains (CLEAR, COMPLICATED, COMPLEX, CHAOTIC) |
| OPAL-11 | Assumption Drift | Live validation, cascade impact, early warnings |
| OPAL-12 | ARMM Assessment | AI readiness maturity scoring (see below) |

### ARMM — Agent Readiness Maturity Model

251 criteria across 4 dimensions, weakest-link scoring:

| Dimension | Code | Topics |
|-----------|------|--------|
| Technical Controls | TC | 7 topics, 75 criteria |
| Operational Resilience | OR | 7 topics |
| Governance & Accountability | GA | 7 topics |
| Capability & Culture | CC | 7 topics |

Five maturity levels: Experimenting (0) → Supervised (1) → Reliable (2) → Resilient (3) → Mission-Critical (4).

### UDS — Universal Dashboard Specification

A vendor-neutral, declarative format for describing analytical dashboards. 19 panel types, semantic data binding, persona-aware layouts.

- **Specification**: [github.com/Tortoise-AI/uds](https://github.com/Tortoise-AI/uds)
- **Renderer**: [github.com/Tortoise-AI/uds-renderer](https://github.com/Tortoise-AI/uds-renderer)

## MCP Server — 28 Tools

Connect any MCP-compatible AI (Claude, and others as they add support) to the full platform:

```
Server URL: https://pda-platform-i33p.onrender.com/sse
```

| Server | Tools | Capabilities |
|--------|-------|-------------|
| **pm-assure** | 23 | OPAL-1 to OPAL-12, project creation, dashboard export |
| **pm-nista** | 5 | GMPP reporting, AI narratives, NISTA submission |

See [docs/hackathon/QUICKSTART.md](docs/hackathon/QUICKSTART.md) for connection instructions.

## Additional Capabilities

### Risk Analysis & Forecasting (pm-analyse)
- AI-powered risk identification across 8 dimensions
- Monte Carlo completion forecasting with confidence intervals
- Outlier detection, health scoring, baseline comparison
- AI-generated mitigation strategies

### Data Ingestion & Validation (pm-data, pm-validate)
- Parse 9 formats: MS Project, Primavera P6, Jira, Monday, Asana, Smartsheet, GMPP, NISTA, JSON
- Structural, semantic, and NISTA compliance validation
- Format conversion and export

### GMPP Quarterly Reporting (pm-nista)
- Complete quarterly report generation
- AI-powered DCA, cost, schedule, benefits, and risk narratives
- NISTA API submission (sandbox and production)

## Packages

| Package | Description | Install |
|---------|-------------|---------|
| **pm-data-tools** | Core library: parsers, validators, OPAL modules, ARMM, AssuranceStore | `pip install pm-data-tools` |
| **pm-mcp-servers** | MCP servers for AI integration (28 tools) | `pip install pm-mcp-servers` |
| **agent-task-planning** | AI reliability framework with confidence extraction | `pip install agent-task-planning` |

## Quick Start

```bash
# Install
pip install pm-data-tools pm-mcp-servers

# Parse any PM file
from pm_data_tools import parse_project
project = parse_project("schedule.mpp")

# Validate NISTA compliance
from pm_data_tools.validators import NISTAValidator
result = NISTAValidator().validate(project)
print(f"Compliance: {result.compliance_score}%")
```

Or connect via MCP — see [QUICKSTART.md](docs/hackathon/QUICKSTART.md).

## Repository Structure

```
pda-platform/
├── dashboards/      # 5 UDS dashboard definitions
├── docs/            # Documentation and hackathon guides
├── packages/
│   ├── pm-data-tools/      # Core library (OPAL modules, ARMM, parsers)
│   ├── pm-mcp-servers/     # MCP servers (28 tools)
│   └── agent-task-planning/ # AI reliability framework
├── render.yaml      # Render.com deployment config
└── specs/           # Technical specifications
```

## Limitations

NISTA compliance scores generated by this tool are indicative assessments against the trial standard and do not constitute formal certification. This tool is provided as-is under the MIT licence; see LICENSE for full warranty and liability terms. The paper this tool accompanies describes the intended scope and known gaps: https://doi.org/10.5281/zenodo.18711384

## Citation

If you use this platform in your research or work, please cite:

```
Newman, A. (2026) From Policy to Practice: An Open Framework for AI-Ready Project Delivery.
London: Tortoise AI. DOI: https://doi.org/10.5281/zenodo.18711384
```

## License

MIT License - see [LICENSE](LICENSE)

## Authors

**Original authors**: Members of the PDA Task Force

**Fork maintained by**: Ant Newman ([github.com/antnewman](https://github.com/antnewman)), CEO and Co-Founder, Tortoise AI

## Acknowledgments

- PDA Task Force White Paper on AI implementation barriers
- NISTA Programme and Project Data Standard
- The open-source community
- This platform accompanies the publication *From Policy to Practice: An Open Framework for AI-Ready Project Delivery* (Newman, 2026)
- [Lawrence Rowland](https://github.com/lawrencerowland) — requirements and conceptual design for the confidence extraction and outlier mining capabilities in `agent-task-planning`
- [Malia Hosseini](https://github.com/maliah1010) — implementation of the outlier mining module

---

*OPAL, ARMM, and UDS — powered by the PDA Platform. Built by [TortoiseAI](https://tortoiseai.co.uk).*
