# Video Storyboard: 60 Seconds to Assurance

**Format:** 1080x1350 (4:5 portrait) for LinkedIn mobile
**Length:** 55-60 seconds
**Style:** Screen recording + bold animated captions (burned in)
**Music:** Subtle lo-fi/tech ambient, very low in mix
**Tools:** Record in OBS, edit in CapCut (free) for animated captions

---

## Pre-recording Setup

1. Wake the server: visit `https://pda-platform-i33p.onrender.com/health`
2. Open Claude.ai in a clean browser window (no clutter)
3. Ensure MCP integration is connected (test with a quick tool call first)
4. Have the challenge prompt ready to paste
5. Screen resolution: 1440x900 or similar (will be cropped to 4:5)

---

## Storyboard

### 0-3s: THE HOOK
**Visual:** Full-screen TortoiseAI dashboard (the HTML export), zooming out slowly
**Caption:** `12 assurance modules. 47 seconds.`
**Audio:** Music starts

### 3-7s: THE PROBLEM
**Visual:** Cut to claude.ai chat, empty conversation
**Caption:** `New SRO. Investment Committee tomorrow. One prompt.`

### 7-12s: THE PROMPT
**Visual:** Paste the challenge prompt (speed up 4x). Show the full text briefly.
**Caption:** `"Give me a full assurance baseline"`

### 12-17s: TOOL 1 — CREATE PROJECT
**Visual:** Claude calls `create_project_from_profile`. Tool call visible, result streams in.
**Caption:** `Creating 12 months of P1-P12 data...`
**Counter badge (top-right):** `1/9`

### 17-22s: TOOLS 2-3 — CLASSIFY + WORKFLOW
**Visual:** Speed up 4x. `classify_project_domain` returns COMPLEX. `run_assurance_workflow` returns health.
**Caption:** `Domain: COMPLEX. Health: ATTENTION NEEDED.`
**Counter:** `3/9`

### 22-27s: TOOLS 4-5 — ASSUMPTIONS + COMPLIANCE
**Visual:** Speed up 4x. `ingest_assumption` and `nista_longitudinal_trend` results.
**Caption:** `Assumption register. Compliance: 72%.`
**Counter:** `5/9`

### 27-33s: TOOL 8 — AI NARRATIVE
**Visual:** `generate_narrative` returns DCA text. Show the narrative scrolling.
**Caption:** `AI-generated DCA narrative. Civil service grade.`
**Counter:** `8/9`

### 33-40s: TOOL 9 — THE DASHBOARD
**Visual:** `export_dashboard_html` fires. Cut to the HTML opening in a browser. Slow pan across:
- TortoiseAI header
- Health gauge + KPI cards
- Compliance trend chart
- Domain classification card
- Open actions table
- Footer with "Built by Ant Newman"
**Caption:** `Email it. Print it. No login needed.`
**Counter:** `9/9`

### 40-47s: THE NUMBERS
**Visual:** Dark background, numbers animate in one by one:
```
28 tools
12 assurance modules
251 ARMM criteria
1 prompt
47 seconds
```
**Caption:** (same as visual)

### 47-52s: TRY IT
**Visual:** Quick screen recording of Settings → Integrations → paste URL
**Caption:** `Connect in 30 seconds. No install.`
**URL on screen:** `pda-platform-i33p.onrender.com/sse`

### 52-58s: CREDITS
**Visual:** TortoiseAI logo + dark background
**Text on screen:**
```
PDA Platform
Open source. Published research.
doi.org/10.5281/zenodo.18711384

Built by Ant Newman
tortoiseai.co.uk
```
**Caption:** `Open source. Published research. Try it now.`

### 58-60s: FADE
**Visual:** Fade to black

---

## Post-Production Checklist

- [ ] Speed up all AI processing sections 4x minimum
- [ ] Cut every loading/waiting moment
- [ ] Bold animated captions throughout (white text, dark semi-transparent bar)
- [ ] Tool counter badge in top-right corner
- [ ] Export at 1080x1350 (4:5)
- [ ] Generate SRT file for LinkedIn upload
- [ ] Test that video works on mute (captions carry 100% of story)

---

## LinkedIn Post Copy (post with the video)

```
I dropped one prompt into Claude and got a full government
project assurance dashboard in 47 seconds.

12 assurance modules. 251 ARMM maturity criteria.
Domain classification. DCA narrative. Assumption tracking.
All from one prompt.

Built on the PDA Platform — the open-source implementation of
"From Policy to Practice" (doi.org/10.5281/zenodo.18711384).

Try it yourself:
1. Open claude.ai
2. Settings > Integrations > Add
3. URL: https://pda-platform-i33p.onrender.com/sse
4. Paste the challenge prompt (link in comments)

28 MCP tools. Zero cost. Zero install.

Built by me at TortoiseAI.

What would you build with this?

#ProjectManagement #AI #GovTech #MCP #OpenSource #ARMM #UDS
```

---

## Comment to Post Immediately After

```
Challenge prompt and full connection guide:
https://github.com/antnewman/pda-platform/blob/main/docs/hackathon/CHALLENGE.md

Quick start (30 seconds):
https://github.com/antnewman/pda-platform/blob/main/docs/hackathon/QUICKSTART.md
```
