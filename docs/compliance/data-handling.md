# Data Handling

This document describes what data PDA Platform stores, what it transmits, and what it does not process. It is intended for information governance teams, data protection officers, and system administrators.

---

## What Is Stored Locally

PDA Platform uses a SQLite database (the AssuranceStore) for persistent storage. The default path is `~/.pm_data_tools/store.db`. This path is configurable via the `PDA_STORE_PATH` environment variable, which allows teams to direct the database to a managed location.

The AssuranceStore contains the following categories of data:

- **Project identifiers**: string identifiers supplied by the user (e.g. `PROJ-001`). No personal data is inferred from or attached to these identifiers.
- **NISTA compliance scores**: numeric scores (0–100) with timestamps, trend direction, and threshold breach records, as produced by the Longitudinal Compliance Tracker (P2).
- **Review actions**: structured records extracted from project review text, including action text, status (OPEN / IN_PROGRESS / CLOSED / RECURRING), cycle identifier, confidence score, and timestamp.
- **Artefact currency records**: document metadata (filename, last-modified timestamp, currency status) as submitted by the user.
- **Override decision records**: governance decisions that proceed against assurance advice, including the override type, rationale text, and outcome — as logged by P6.
- **Assumption records**: assumption text, baseline values, validation check history, and drift scores as registered by P11.
- **ARMM assessments**: maturity scores across four dimensions and 28 topics, as produced by P12, linked to a project identifier.
- **Gate readiness results**: composite scores, dimension breakdowns, blocking issues, and recommendations as produced by P14.
- **Benefits data**: benefit register entries, measurement records, dependency relationships, and realisation forecasts as managed by P13.
- **Assurance workflow results**: aggregated health scores and recommended actions from P9 workflow runs.

All records are keyed by project identifier. No records contain named individuals, job titles, email addresses, or any other personal data.

---

## What Is Not Stored

The following categories of data are not stored in the AssuranceStore and are not written to disk by any PDA Platform component:

- **Personal data**: no names, email addresses, job roles, or other information relating to identifiable individuals.
- **Authentication credentials**: API keys (including `ANTHROPIC_API_KEY`) are read from environment variables at runtime and are never written to the store or to log files.
- **Raw project files**: project schedule files (MSPDI, P6 XML, etc.) are parsed in memory; the parsed canonical model is used for analysis and is not persisted unless the user explicitly exports it.

---

## Where AI Processing Happens

Three tools in the platform make calls to the Anthropic Claude API:

| Tool | Module | What is sent to the API |
|------|--------|------------------------|
| `track_review_actions` | pm-assure (P3) | The review text supplied by the user in the tool call |
| `generate_narrative` | pm-nista | The structured project data fields required for the DCA narrative |
| Review text analysis (recurrence detection) | pm-assure (P3) | Action text for similarity comparison |

Project identifiers, compliance scores, and numeric data are not sent to the Anthropic API. Only the unstructured text content necessary for extraction or generation is transmitted.

The Anthropic API is subject to Anthropic's data processing terms. Teams operating under data handling restrictions should review those terms before using the AI-powered tools. The non-AI tools (data parsing, NISTA validation, structural validation, gate readiness scoring, and all deterministic assurance modules) make no external API calls.

---

## Data Retention

The AssuranceStore persists indefinitely. There is no automatic deletion or archival policy built into the platform. Users are responsible for managing their own database file, including backup, deletion, and retention in accordance with their organisation's data management policies.

Because the store path is configurable, teams can place the database on a managed volume subject to their standard retention controls.

---

## Remote Deployment Considerations

When PDA Platform is deployed on Render (or a similar platform as a service), the following additional considerations apply:

- **In-memory state**: the remote server (`pda-platform-remote`) is stateless between requests for modules that do not write to the AssuranceStore. Data submitted in one request is not retained for a subsequent request unless it has been written to the store.
- **Store path**: if the `PDA_STORE_PATH` environment variable is not set on the remote host, the store defaults to the container's home directory. On Render's free tier, this directory is ephemeral and will be lost on redeploy. Teams requiring persistent assurance data on a remote deployment should mount a persistent disk and set `PDA_STORE_PATH` accordingly.
- **Cold starts**: Render's free tier spins down idle instances. The first request after a cold start may experience additional latency of several seconds while the server initialises.
- **Transport**: the SSE endpoint (`/sse`) uses HTTPS. Data in transit is encrypted by the platform's TLS termination.
