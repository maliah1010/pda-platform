# Your First Project: From Zero to Assurance Baseline

This guide walks you through creating your first project and running a full assurance baseline using Claude.ai connected to the PDA Platform remote server. No local installation is required.

---

## Prerequisites

- A Claude.ai account with Projects or the ability to configure MCP connections
- Access to the PDA Platform remote server (`https://pda-platform-i33p.onrender.com/sse`)

If you prefer a local install, see [local-claude-desktop.md](local-claude-desktop.md) first.

---

## Step 1: Connect Claude.ai to PDA Platform

In Claude.ai, open your settings and add a new MCP server connection. Use the SSE endpoint:

```
https://pda-platform-i33p.onrender.com/sse
```

Once connected, Claude will indicate that PDA Platform tools are available. You can verify by asking: "What PDA tools do you have?"

You should see a list of tools across the six modules: pm-data, pm-analyse, pm-validate, pm-nista, pm-assure, and pm-brm.

---

## Step 2: Create a Project and Run the NSDIP Scenario

The fastest way to understand the platform is to use the NSDIP hackathon scenario — a realistic government programme that exercises the full assurance stack in a single prompt.

Paste the following into Claude.ai:

```
I've just been appointed SRO for the National Schools Digital Infrastructure
Programme (NSDIP) at the Department for Education. £2.4bn whole life cost,
Digital/ICT category.

Complexity indicators: technical 0.85, stakeholder 0.6, requirement clarity 0.3,
delivery track record 0.2, organisational change 0.8, regulatory 0.5,
dependencies 0.7.

Key risks: legacy system integration, teacher adoption resistance,
data migration from 22,000 schools, ministerial timeline pressure.

I need a full assurance baseline before my Investment Committee tomorrow:
1. Create the project and run the full OPAL pipeline
2. Classify the complexity domain
3. Set up assumption tracking for the £2.4bn cost envelope
4. Run the full assurance workflow
5. Generate a DCA narrative for the quarterly return
6. Export me a dashboard I can email to the board
```

---

## Step 3: What Claude Does

Claude will call approximately nine MCP tools in sequence:

1. `create_project_from_profile` — creates the NSDIP project and generates 12 months of OPAL compliance data
2. `classify_project_domain` — classifies the programme using the seven complexity indicators (expect COMPLEX given the scores above)
3. `ingest_assumption` — registers the £2.4bn cost envelope as a tracked assumption with a baseline
4. `run_assurance_workflow` — runs the full assurance pipeline across P1–P8
5. `get_assumption_drift` — returns the assumption health baseline
6. `nista_longitudinal_trend` — shows the 12-month compliance trend
7. `review_action_status` — lists any open review actions
8. `generate_narrative` — produces a DCA narrative for the quarterly GMPP return
9. `export_dashboard_html` — generates a self-contained HTML file you can email

---

## Step 4: Review the Outputs

Once Claude has completed the sequence, you will have:

- A domain classification with a tailored assurance profile and recommended review cadence
- A registered assumption for the cost envelope, ready to track drift over time
- A workflow result with an overall project health assessment and prioritised recommended actions
- A DCA narrative in the format expected for GMPP quarterly returns
- An HTML dashboard summarising all outputs

The entire process typically completes in under 60 seconds from the first tool call.

---

## Next Steps

- To track assumption drift over subsequent months, use `record_assumption_check` with updated cost data
- To add review actions from a real gate report, use `track_review_actions` with the review text
- To run a gate readiness assessment ahead of your Investment Committee, use `assess_gate_readiness`

For all available tools and prompts, see [Assurance Practitioner Guide](../assurance-for-practitioners.md).
