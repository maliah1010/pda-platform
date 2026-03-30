# PM MCP Servers

MCP servers for AI-enabled project management. Provides the **OPAL** (Open Project Assurance Library), **ARMM** (Agent Readiness Maturity Model), and **GMPP/NISTA** reporting tools via the Model Context Protocol.

Part of the [PDA Platform](https://github.com/antnewman/pda-platform).

## Live Server

Connect from claude.ai or any MCP client — no install needed:

```
https://pda-platform-i33p.onrender.com/sse
```

See [QUICKSTART](../../docs/hackathon/QUICKSTART.md) for setup instructions.

## Available Servers (28 tools)

### pm-assure-server (23 tools)

The OPAL assurance framework — continuous project assurance across 12 modules:

| Module | Tools | Capability |
|--------|-------|-----------|
| OPAL-1 | `check_artefact_currency` | Stale document detection, anomalous update alerts |
| OPAL-2 | `nista_longitudinal_trend` | Compliance score history, trend analysis, threshold breaches |
| OPAL-3 | `track_review_actions`, `review_action_status` | AI action extraction, cross-cycle recurrence detection |
| OPAL-4 | `check_confidence_divergence` | AI confidence monitoring, sample consensus scoring |
| OPAL-5 | `recommend_review_schedule` | Adaptive scheduling driven by OPAL-1 to OPAL-4 signals |
| OPAL-6 | `log_override_decision`, `analyse_override_patterns` | Governance override logging with full audit trail |
| OPAL-7 | `ingest_lesson`, `search_lessons` | Knowledge engine with category, sentiment, impact tracking |
| OPAL-8 | `log_assurance_activity`, `analyse_assurance_overhead` | Effort tracking and efficiency optimisation |
| OPAL-9 | `run_assurance_workflow`, `get_workflow_history` | Multi-step agentic workflow orchestration |
| OPAL-10 | `classify_project_domain`, `reclassify_from_store` | Cynefin domains (CLEAR/COMPLICATED/COMPLEX/CHAOTIC) |
| OPAL-11 | `ingest_assumption`, `validate_assumption`, `get_assumption_drift`, `get_cascade_impact` | Assumption drift tracking with cascade analysis |
| OPAL-12 | Via `create_project_from_profile` | ARMM maturity assessment (251 criteria, 4 dimensions) |

**Hackathon tools:**

| Tool | Description |
|------|-------------|
| `create_project_from_profile` | Create full OPAL project from metadata — runs entire pipeline |
| `export_dashboard_data` | Export static JSON for UDS Renderer |
| `export_dashboard_html` | Generate self-contained branded HTML dashboard |

### pm-nista-server (5 tools)

GMPP quarterly reporting and NISTA integration:

| Tool | Description |
|------|-------------|
| `generate_gmpp_report` | Complete quarterly report from project data |
| `generate_narrative` | AI-powered DCA, cost, schedule, benefits, risk narratives |
| `validate_gmpp_report` | NISTA compliance validation (LENIENT/STANDARD/STRICT) |
| `submit_to_nista` | Submit to NISTA API (sandbox or production) |
| `fetch_nista_metadata` | Fetch from NISTA master registry |

### pm-data-server (6 tools)

Project data ingestion and querying:

| Tool | Description |
|------|-------------|
| `load_project` | Parse 9 formats (MS Project, P6, Jira, Monday, Asana, Smartsheet, GMPP, NISTA) |
| `query_tasks` | Filter by status, critical path, milestone, assignee, dates |
| `get_critical_path` | Critical path + near-critical tasks |
| `get_dependencies` | Predecessor/successor analysis |
| `convert_format` | Export to MSPDI, JSON, NISTA |
| `get_project_summary` | High-level project statistics |

### pm-validate-server (4 tools)

Data integrity and compliance:

| Tool | Description |
|------|-------------|
| `validate_structure` | Orphan tasks, circular deps, duplicate IDs, hierarchy |
| `validate_semantic` | Schedule logic, overallocation, cost consistency |
| `validate_nista` | NISTA standard compliance (3 strictness levels) |
| `validate_custom` | Organisation-specific custom rules |

### pm-analyse-server (6 tools)

AI-powered analysis:

| Tool | Description |
|------|-------------|
| `identify_risks` | 8 risk dimensions with confidence scoring |
| `forecast_completion` | Monte Carlo, EVM, Reference Class, ML Ensemble |
| `detect_outliers` | Duration, progress, float, date anomalies |
| `assess_health` | 5-dimension weighted health scoring |
| `suggest_mitigations` | AI-generated strategies with effectiveness ratings |
| `compare_baseline` | Schedule, duration, cost variance analysis |

## UK Government Compliance

| Framework | Status |
|-----------|--------|
| Model for Responsible Innovation | Aligned |
| AI Playbook for UK Government | Aligned |
| Data and AI Ethics Framework | Aligned |
| NISTA Programme and Project Data Standard | Supported |

See [`docs/compliance/`](docs/compliance/) and [`docs/model-cards/`](docs/model-cards/) for full compliance documentation.

## Installation

```bash
pip install pm-mcp-servers
```

## Quick Start

### Option 1: Remote server (no install)

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "pda-platform": {
      "url": "https://pda-platform-i33p.onrender.com/sse"
    }
  }
}
```

### Option 2: Local server

```json
{
  "mcpServers": {
    "pm-assure": {
      "command": "pm-assure-server",
      "args": [],
      "env": {
        "ANTHROPIC_API_KEY": "sk-ant-..."
      }
    }
  }
}
```

### Example prompts

```
Create a COMPLEX domain project called "Digital Infrastructure Programme"
for the Department for Education, then export a dashboard.
```

```
Ingest an assumption that construction inflation will stay below 4.5%,
then validate it with a current value of 7.8%.
```

```
Run a full assurance workflow for my project and tell me the health status.
```

## Development

```bash
git clone https://github.com/antnewman/pda-platform.git
cd pda-platform/packages/pm-mcp-servers
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -e ".[dev]"
pytest
```

## Citation

```
Newman, A. (2026) From Policy to Practice: An Open Framework for AI-Ready Project Delivery.
London: Tortoise AI. DOI: https://doi.org/10.5281/zenodo.18711384
```

## License

MIT License — see [LICENSE](LICENSE) for details.

## Acknowledgments

Fork maintained by Ant Newman ([github.com/antnewman](https://github.com/antnewman)), CEO and Co-Founder, Tortoise AI.

Original work by members of the PDA Task Force.
