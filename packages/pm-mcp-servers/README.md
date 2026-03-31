# PM MCP Servers

MCP servers for AI-enabled project management. Enables Claude to interact with PM
data, validate NISTA compliance, and track assurance quality over time.

Part of the [PDA Platform](https://github.com/antnewman/pda-platform).

<!-- mcp-name: io.github.antnewman/pm-data -->
<!-- mcp-name: io.github.antnewman/pm-validate -->
<!-- mcp-name: io.github.antnewman/pm-analyse -->
<!-- mcp-name: io.github.antnewman/pm-assure -->

## Overview

PM MCP Servers provides Model Context Protocol (MCP) servers that enable Claude
Desktop and other MCP clients to interact with project management data and assurance
tooling. Built to support the NISTA Programme and Project Data Standard trial.

## Unified Server (Recommended)

The **`pda-platform-server`** is a single MCP endpoint that exposes all 45 tools
from all 5 modules. This is the recommended way to use PDA.

```json
{
  "mcpServers": {
    "pda-platform": {
      "command": "pda-platform-server",
      "args": [],
      "env": {
        "ANTHROPIC_API_KEY": "sk-ant-..."
      }
    }
  }
}
```

For remote access (e.g., from Claude.ai), use `pda-platform-remote` which adds
SSE transport over HTTP. See the deployment section below.

## Individual Servers

Individual servers are still available for use cases where you only need a
subset of tools.

### pm-data-server

Core server for PM data interaction.

**Tools:** `load_project`, `query_tasks`, `get_critical_path`, `export_project`

### pm-validate-server

Validation server for PM data quality.

**Tools:** `validate_nista`, `validate_structure`, `check_dependencies`

### pm-analyse-server

Analysis server for PM insights.

**Tools:** `analyze_risks`, `forecast_completion`, `resource_utilization`

### pm-benchmark-server

Benchmarking server for PM AI evaluation.

**Tools:** `run_benchmark`, `compare_results`

### pm-assure-server

Assurance quality tracking server. Covers longitudinal compliance score analysis,
cross-cycle review action management, and artefact currency checking.

**Tools:**

| Tool | Description |
|------|-------------|
| `nista_longitudinal_trend` | Retrieve NISTA compliance score history, trend direction (IMPROVING / STAGNATING / DEGRADING), and active threshold breaches for a project. |
| `track_review_actions` | Extract review actions from project review text using AI, deduplicate within the current review, and detect cross-cycle recurrences. Requires `ANTHROPIC_API_KEY`. |
| `review_action_status` | Retrieve tracked review actions for a project, optionally filtered by status (OPEN / IN_PROGRESS / CLOSED / RECURRING). |

See [`docs/assurance.md`](../../docs/assurance.md) for full API reference.

## UK Government Compliance

pda-platform is designed to support compliance with UK government AI and data
ethics frameworks.

| Framework | Status |
|-----------|--------|
| Model for Responsible Innovation | ✅ Aligned |
| AI Playbook for UK Government | ✅ Aligned |
| Data and AI Ethics Framework | ✅ Aligned |
| NISTA Programme and Project Data Standard | ✅ Supported |

Key properties:
- **Transparency**: MIT open source licence; full code visibility
- **Accountability**: Evidence trails on all AI outputs
- **Human Oversight**: Advisory outputs with confidence scoring (0.0–1.0)
- **Fairness**: No personal or demographic data processing
- **Safety**: Documented limitations and risk assessment

See [`docs/compliance/`](docs/compliance/), [`docs/model-cards/`](docs/model-cards/),
and [`docs/guides/`](docs/guides/) for full compliance documentation.

## Installation

```bash
pip install pm-mcp-servers
```

For assurance features with recurrence detection:

```bash
pip install "agent-task-planning[mining]"
```

## Quick Start

### Configure Claude Desktop

Add to `claude_desktop_config.json`
(`%APPDATA%\Claude\claude_desktop_config.json` on Windows,
`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "pda-platform": {
      "command": "pda-platform-server",
      "args": [],
      "env": {
        "ANTHROPIC_API_KEY": "sk-ant-..."
      }
    }
  }
}
```

This gives Claude access to all 45 tools across data loading, analysis,
validation, NISTA reporting, and assurance.

### Remote Deployment

For remote access from Claude.ai, deploy `pda-platform-remote`:

```bash
PORT=8080 pda-platform-remote
```

This starts an SSE server at `/sse` with a health check at `/health`.

### Example prompts

Once configured you can ask Claude:

**Project data:**
- "Load /projects/building.mpp and show the critical path"
- "Validate this project against NISTA requirements"

**Longitudinal compliance (P2):**
- "Show me the NISTA compliance trend for project PROJ-001."
- "Have there been any threshold breaches for PROJ-001 recently?"

**Review action tracking (P3):**
- "Extract the actions from this review document and track them for PROJ-001."
- "Show me all open review actions for PROJ-001."
- "Which actions for PROJ-001 are recurring from previous reviews?"

## Development

```bash
git clone https://github.com/antnewman/pda-platform.git
cd pda-platform/packages/pm-mcp-servers
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -e ".[dev]"
pytest
```

## License

MIT License — see [LICENSE](LICENSE) for details.

## Acknowledgments

Fork maintained by Ant Newman ([github.com/antnewman](https://github.com/antnewman)).

Original work by members of the PDA Task Force. Made possible by:
- The **PDA Task Force White Paper** identifying AI implementation barriers in UK
  project delivery
- The **NISTA Programme and Project Data Standard** and its 12-month trial period
