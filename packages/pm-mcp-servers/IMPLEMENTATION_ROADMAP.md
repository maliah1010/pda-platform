# PM-MCP-Servers Implementation Roadmap

## Status: All Three Horizons Complete ✅ (v1.0.0)

### Completed
- ✅ Version bumped to 0.2.0
- ✅ Added pm-data-tools>=0.2.0 dependency
- ✅ Added dev dependencies (pytest-cov, mypy)
- ✅ Git configured with antnewman author

### Phase 2: Real Parser Integration (IN PROGRESS)

Replace mock implementations in `src/pm_mcp_servers/pm_data/tools.py` with real pm-data-tools integration.

**Key Changes Needed:**
1. Import real pm-data-tools parsers, models, exceptions, exporters
2. Replace mock project store with dataclass-based ProjectStore
3. Update all 6 tools to use real parsers:
   - `load_project()` - Use detect_format() and create_parser()
   - `query_tasks()` - Work with real Project.tasks
   - `get_critical_path()` - Calculate from real task data
   - `get_dependencies()` - Use real Project.dependencies
   - `convert_format()` - Use create_exporter()
   - `get_project_summary()` - Aggregate real metrics

**Error Handling:**
- UnsupportedFormatError - Invalid format
- ParseError - Malformed file
- Generic Exception - Unexpected errors

### Phase 3: PM-Validate Server (TODO)

Create new validation MCP server at `src/pm_mcp_servers/pm_validate/`

**Structure:**
```
pm_validate/
├── __init__.py
├── tools.py      # 4 validation tools
└── server.py     # MCP server setup
```

**4 Tools:**
1. `validate_structure()` - Check references, hierarchy, cycles
2. `validate_semantic()` - Business rules, schedule logic
3. `validate_nista()` - UK government NISTA compliance
4. `validate_custom()` - Custom rule engine

**NISTA Compliance:**
- Required fields: department, DCA, SRO, dates
- Valid DCA values: green, amber_green, amber, amber_red, red
- Strictness levels: lenient, standard, strict

### Phase 4: Testing (TODO)

Create comprehensive test suite:
- `tests/test_pm_data_integration.py` - Real parser tests
- `tests/test_pm_validate.py` - Validation tests

Target: 90%+ coverage

### Phase 5: Documentation (TODO)

Update README with:
- Real parser capabilities
- Format support matrix
- NISTA validation guide
- Usage examples

## Phase 3: pm-assure Server ✅ Complete (v1.0.0)

`src/pm_mcp_servers/pm_assure/server.py`

**16 Tools (P1–P10):**
1. `nista_longitudinal_trend` — P2: compliance score history, trend direction, breaches
2. `track_review_actions` — P3: AI extraction + deduplication + cross-cycle recurrence
3. `review_action_status` — P3: retrieve actions by project and status
4. `check_artefact_currency` — P1: detect stale and last-minute artefact updates
5. `check_confidence_divergence` — P4: detect AI extraction sample divergence
6. `recommend_review_schedule` — P5: adaptive review timing from P1–P4 signals
7. `log_override_decision` — P6: structured logging of governance override decisions
8. `analyse_override_patterns` — P6: pattern analysis of override history
9. `ingest_lesson` — P7: ingest a structured lessons learned record
10. `search_lessons` — P7: keyword and semantic search of the lessons corpus
11. `log_assurance_activity` — P8: log assurance activity with effort tracking
12. `analyse_assurance_overhead` — P8: complete overhead analysis with efficiency rating
13. `run_assurance_workflow` — P9: multi-step deterministic assurance orchestration
14. `get_workflow_history` — P9: retrieve workflow execution history
15. `classify_project_domain` — P10: classify project complexity domain with profile
16. `reclassify_from_store` — P10: store-signal-only domain reclassification

**Features implemented (all three horizons complete):**
- P1 — Artefact Currency Validator (`assurance/currency.py`) — 14 tests
- P2 — Longitudinal Compliance Tracker (`schemas/nista/longitudinal.py`) — 12 tests
- P3 — Cross-Cycle Finding Analyzer (`assurance/analyzer.py`) — 11 tests
- P4 — Confidence Divergence Monitor (`assurance/divergence.py`) — 17 tests
- P5 — Adaptive Review Scheduler (`assurance/scheduler.py`) — 18 tests
- P6 — Override Decision Logger (`assurance/overrides.py`) — 15 tests
- P7 — Lessons Learned Knowledge Engine (`assurance/lessons.py`) — 21 tests
- P8 — Assurance Overhead Optimiser (`assurance/overhead.py`) — 20 tests
- P9 — Agentic Assurance Workflow Engine (`assurance/workflows.py`) — 35 tests
- P10 — Project Domain Classifier (`assurance/classifier.py`) — 35 tests

See [`docs/assurance.md`](../../docs/assurance.md) for full reference.

## Horizon 3 Complete ✅ (v1.0.0)

**13. `run_assurance_workflow` — P9: Agentic Assurance Workflow Engine**
**14. `get_workflow_history` — P9: Workflow execution history**
**15. `classify_project_domain` — P10: Project Domain Classifier**
**16. `reclassify_from_store` — P10: Store-signal reclassification**

**Features implemented (Horizon 3 complete):**
- P9 — Agentic Assurance Workflow Engine (`assurance/workflows.py`) — 35 tests
- P10 — Project Domain Classifier (`assurance/classifier.py`) — 35 tests

**Full test suite (all three horizons):**
- P1: 14 tests, P2: 12 tests, P3: 11 tests, P4: 17 tests
- P5: 18 tests, P6: 15 tests, P7: 21 tests, P8: 20 tests
- P9: 35 tests, P10: 35 tests
- **Total: 198 tests across 10 P-features**

## Next Steps

1. Complete Phase 2 (real parser integration for pm-data)
2. Build Phase 4 (pm-validate with full NISTA v1.0 schema)

## Attribution

All work: antnewman <antjsnewman@outlook.com>
For: PDA Task Force
Supporting: NISTA Programme and Project Data Standard trial
