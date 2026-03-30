# PDA Platform — Demo Quick-Start

End-to-end demo for the hackathon presentation.
Runs the FastAPI backend, the UDS renderer, and verifies all 5 dashboards
render with live data from the 15-project synthetic dataset.

---

## Stack overview

| Component | Location | Port |
|-----------|----------|------|
| PDA API (FastAPI) | `packages/pm-api` | 8000 |
| UDS Renderer (React/Vite) | `uds-renderer` (separate repo) | 5173 |
| Demo database | `packages/pm-api/demo_store.db` | — |

---

## 1. Generate the demo database (if not already present)

```bash
python packages/pm-data-tools/scripts/generate_synthetic_data.py \
  --output packages/pm-api/demo_store.db \
  --verify
```

Expected output: 14 tables, ~2,700 records across 15 UK government projects.

---

## 2. Start the PDA API

```bash
# Install dependencies (once)
pip install -e "packages/pm-data-tools[dev]"
pip install -e "packages/pm-api"

# Start the server
python run_api.py
# OR
uvicorn pm_api.main:app --reload --port 8000
```

The API will be available at `http://localhost:8000`.
Swagger docs: `http://localhost:8000/docs`

**Environment variables** (optional — defaults work for local demo):

| Variable | Default | Description |
|----------|---------|-------------|
| `PDA_DB_PATH` | `packages/pm-api/demo_store.db` | Path to SQLite database |
| `PDA_CORS_ORIGINS` | `http://localhost:5173` | Allowed CORS origins |

---

## 3. Run the health check

With the API running:

```bash
python scripts/check_demo.py
```

Runs 20 checks across all OPAL-1 to OPAL-12 endpoints for PROJ-001.
All checks should pass.

---

## 4. Start the UDS renderer

In the `uds-renderer` repo:

```bash
# Set the API URL
echo "VITE_PDA_API_URL=http://localhost:8000" > .env.local

npm install
npm run dev
```

Open `http://localhost:5173` in a browser.

---

## 5. Dashboard URLs

| Dashboard | URL |
|-----------|-----|
| Assurance Overview (portfolio) | `http://localhost:5173/?dashboard=assurance-overview` |
| Assurance Portfolio | `http://localhost:5173/?dashboard=assurance-portfolio` |
| Assurance Deep Dive (per project) | `http://localhost:5173/?dashboard=assurance-deep-dive&project_id=PROJ-001` |
| Assumption Drift Tracker | `http://localhost:5173/?dashboard=assumption-drift&project_id=PROJ-001` |
| ARMM Assessment | `http://localhost:5173/?dashboard=armm-assessment&project_id=PROJ-001` |

Use the project selector in the top bar to switch between the 15 demo projects.

---

## 6. Demo project data highlights

| Project ID | Name | Domain | Health |
|------------|------|--------|--------|
| PROJ-001 | Digital ID Verification Service | CLEAR | ATTENTION_NEEDED |
| PROJ-004 | AI Document Processing Platform | COMPLICATED | AT_RISK |
| PROJ-007 | Cross-Border Data Sharing Framework | COMPLEX | CRITICAL |
| PROJ-013 | Emergency Comms Transformation | CHAOTIC | CRITICAL |

Good demo path:
1. Start at **Assurance Overview** — show portfolio health distribution
2. Click through to **PROJ-007** (COMPLEX, AT_RISK) in **Deep Dive**
3. Switch to **Assumption Drift** — show cascade warnings for PROJ-007
4. Switch to **ARMM Assessment** — show PROJ-007 blocked at SUPERVISED (OR dimension)
5. Return to portfolio — compare PROJ-001 (CLEAR, RELIABLE) vs PROJ-013 (CHAOTIC, EXPERIMENTING)

---

## 7. Key API endpoints (reference)

```
GET /api/health                              — liveness check
GET /api/projects                            — list all 15 projects
GET /api/portfolio                           — portfolio overview
GET /api/projects/{project_id}               — project detail

GET /api/compliance/{project_id}             — P2 confidence trend
GET /api/schedule/{project_id}               — P5 review recommendation
GET /api/overrides/{project_id}              — P6 override log
GET /api/lessons/summary                     — P7 lessons overview
GET /api/overhead/{project_id}               — P8 effort analysis
GET /api/workflows/{project_id}/history      — P9 workflow executions
GET /api/classifier/{project_id}             — P10 domain classification
GET /api/currency/{project_id}               — P1 artefact currency
GET /api/actions/{project_id}               — P3 review actions

GET /api/assumptions/{project_id}            — P11 assumptions list
GET /api/assumptions/{project_id}/health     — P11 drift report
GET /api/assumptions/{project_id}/stale      — P11 stale assumptions

GET /api/armm/portfolio                      — P12 ARMM portfolio overview
GET /api/armm/{project_id}                   — P12 ARMM report (weakest-link)
GET /api/armm/{project_id}/dimensions        — P12 28-topic breakdown
GET /api/armm/{project_id}/criteria          — P12 251-criterion drill-through
GET /api/armm/{project_id}/history           — P12 assessment history
```

---

## 8. Architecture summary

```
┌─────────────────────────┐     ┌─────────────────────┐
│   uds-renderer (React)  │────>│  PDA API (FastAPI)   │
│   5 UDS dashboards      │     │  http://localhost:8000│
│   Live data via hooks   │     └──────────┬──────────┘
└─────────────────────────┘                │
                                           │ SQLite
                                     ┌─────▼──────────────┐
                                     │  demo_store.db      │
                                     │  14 tables          │
                                     │  OPAL assurance      │
                                     │  15 UK gov projects │
                                     └────────────────────┘
```

---

## 9. Regenerating from scratch

```bash
# Delete existing database
rm packages/pm-api/demo_store.db

# Regenerate
python packages/pm-data-tools/scripts/generate_synthetic_data.py \
  --output packages/pm-api/demo_store.db \
  --verify
```

The generator is deterministic (`random.seed(42)`) — the same database
is produced on every run.
