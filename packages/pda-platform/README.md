# pda-platform

**AI-powered project delivery assurance for UK government.**

89 MCP tools connecting Claude and other AI assistants to the full IPA assurance framework: schedule analysis, risk registers, financial tracking, gate readiness, benefits realisation, change control, resource capacity, and more.

## Install

```bash
pip install pda-platform
```

This installs all three constituent packages:
- `agent-task-planning` — AI reliability framework
- `pm-data-tools` — parsers, validators, AssuranceStore
- `pm-mcp-servers` — 89 MCP tools across 13 modules

## Quick start

Add the unified server to Claude Desktop (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "pda-platform": {
      "command": "pda-platform-server",
      "args": []
    }
  }
}
```

Or connect Claude.ai to the hosted endpoint:

```
https://pda-platform-i33p.onrender.com/sse
```

## What's included

| Module | Tools | Capability |
|--------|------:|-----------|
| pm-data | 6 | Schedule loading, querying, format conversion |
| pm-analyse | 6 | Risk analysis, forecasting, health assessment |
| pm-validate | 4 | Structural, semantic, and NISTA validation |
| pm-nista | 5 | GMPP reporting and NISTA submission |
| pm-assure | 27 | P1–P14 assurance framework |
| pm-brm | 10 | Benefits Realisation Management |
| pm-portfolio | 5 | Cross-project health rollup |
| pm-ev | 2 | Earned Value metrics and dashboard |
| pm-synthesis | 2 | AI executive health summaries |
| pm-risk | 7 | Risk register and heat map |
| pm-change | 5 | Change control log |
| pm-resource | 5 | Resource loading and capacity |
| pm-financial | 5 | Budget baseline, actuals, EAC forecasting |
| **Total** | **89** | |

## Documentation

Full documentation at [github.com/antnewman/pda-platform](https://github.com/antnewman/pda-platform/tree/main/docs).

## Licence

MIT
