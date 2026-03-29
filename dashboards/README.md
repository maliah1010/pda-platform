# PDA Platform Assurance Dashboards

UDS ([Universal Dashboard Specification](https://github.com/Tortoise-AI/uds)) definitions for the PDA Platform assurance module.

## Dashboards

| Dashboard | Persona | Description |
|-----------|---------|-------------|
| [assurance-overview](assurance-overview.uds.yaml) | Executive (SRO) | Single-screen health summary: gauge, domain, urgency, four key signals, trends, gate readiness |
| [assurance-deep-dive](assurance-deep-dive.uds.yaml) | Analyst (PMO) | Five-tab operational view: evidence, compliance, governance, efficiency, workflows |
| [assurance-portfolio](assurance-portfolio.uds.yaml) | Portfolio Director | Cross-project comparison: war-room table, domain distribution, systemic patterns |

## Data Sources

All three dashboards consume data from the PDA Platform assurance module (P1-P10) via the `pm-assure` MCP server and `AssuranceStore` SQLite database.

| Feature | Dashboards |
|---------|-----------|
| P1 Artefact Currency Validator | Overview, Deep Dive, Portfolio |
| P2 Longitudinal Compliance Tracker | Overview, Deep Dive, Portfolio |
| P3 Cross-Cycle Finding Analyzer | Overview, Deep Dive, Portfolio |
| P4 Confidence Divergence Monitor | Overview, Deep Dive, Portfolio |
| P5 Adaptive Review Scheduler | Overview, Portfolio |
| P6 Override Decision Logger | Deep Dive, Portfolio |
| P7 Lessons Learned Knowledge Engine | Deep Dive, Portfolio |
| P8 Assurance Overhead Optimiser | Deep Dive, Portfolio |
| P9 Agentic Assurance Workflow Engine | Overview, Deep Dive, Portfolio |
| P10 Project Domain Classifier | Overview, Portfolio |

## Rendering

These are UDS v0.1.0 documents. They can be rendered by any UDS-conformant renderer. To validate:

```bash
cd /path/to/uds
python scripts/validate-examples.py ../pda-platform/dashboards/
```

## Configuration

Set these environment variables for the semantic source:

```bash
export PDA_ASSURANCE_API_URL="http://localhost:8080/api/v1"
export PDA_API_TOKEN="your-token-here"
```
