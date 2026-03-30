# Introducing OPAL: Open Project Assurance Library

*3-minute read. One new framework. One live tool you can try right now.*

---

Government projects have a 0.5% success rate. 84% of the GMPP is rated Amber or Red. The pattern is always the same: assumptions go unchecked, risks go unquantified, and assurance happens too late to change the outcome.

We spent the last year building the fix. Today we're making it available to everyone.

---

## What we built

**OPAL** (Open Project Assurance Library) is an open-source assurance framework with 12 modules that run continuously against your project data:

| | Module | What it catches |
|---|---|---|
| 1 | Artefact Currency | Stale documents, last-minute gate-stuffing |
| 2 | Compliance Tracking | NISTA score drift over 12+ months |
| 3 | Review Actions | Recurring findings nobody closes |
| 4 | Confidence Monitoring | AI extraction scores diverging from reality |
| 5 | Adaptive Scheduling | Review cadence that responds to risk signals |
| 6 | Governance Overrides | Decisions made outside the framework — and their outcomes |
| 7 | Lessons Learned | Cross-programme knowledge that actually gets reused |
| 8 | Overhead Optimisation | Whether your assurance effort is producing findings |
| 9 | Workflow Orchestration | Multi-step assurance runs with full audit trail |
| 10 | Domain Classification | Cynefin complexity — CLEAR through CHAOTIC |
| 11 | Assumption Drift | Live validation against external data, cascade impact |
| 12 | ARMM Assessment | AI readiness maturity — 251 criteria, 4 dimensions |

OPAL sits alongside **ARMM** (Agent Readiness Maturity Model) and **UDS** (Universal Dashboard Specification) as the three pillars of the PDA Platform.

---

## Why it matters

On the Great Western Mainline electrification, assumptions were linked to ONS and BoE data feeds from the outset. When inflation spiked in 2022, the programme demonstrated the exact impact to HMT within 48 hours. Supplementary funding arrived in 6 weeks. No delay.

On the Midland Main Line, assumptions were static text in a business case. The same inflation shock. Nobody checked. £120m over budget. 14 months late. SRO replaced.

The difference was not intelligence or budget. It was whether assumption management was passive documentation or active assurance.

OPAL makes it active. By default.

---

## How it works

OPAL is delivered as 29 MCP tools on a live server. You connect it to Claude (or any AI that supports the Model Context Protocol) and use natural language:

> *"I've just been appointed SRO for a £2.4bn digital infrastructure programme. Give me a full assurance baseline — domain classification, compliance trend, assumption register, ARMM maturity, and a dashboard for the board."*

Claude calls the right tools. Nine tool calls. Under 60 seconds. You get a self-contained HTML dashboard you can email to the Investment Committee.

No install. No API key. No cost.

---

## Try it now

1. Open [claude.ai](https://claude.ai)
2. Settings → Integrations → Add Custom Integration
3. Name: **PDA Platform**
4. URL: `https://pda-platform-i33p.onrender.com/sse`
5. Start a new chat and paste the prompt above

The server is live. The tools are real. The data persists.

---

## The research

OPAL is the implementation of *From Policy to Practice: An Open Framework for AI-Ready Project Delivery* (Newman, 2026).

**Paper:** [doi.org/10.5281/zenodo.18711384](https://doi.org/10.5281/zenodo.18711384)
**Code:** [github.com/antnewman/pda-platform](https://github.com/antnewman/pda-platform)
**Spec:** [github.com/Tortoise-AI/uds](https://github.com/Tortoise-AI/uds)

Open source. MIT licence. Contributions welcome.

---

*Built by Ant Newman at [TortoiseAI](https://tortoiseai.co.uk). From policy to practice.*
