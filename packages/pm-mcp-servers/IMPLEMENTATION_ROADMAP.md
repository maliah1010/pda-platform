# PM-MCP-Servers Implementation Roadmap

## Status: Phase 3 (Assurance) Complete ✅

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

## Phase 3: pm-assure Server ✅ Complete (v0.3.0)

`src/pm_mcp_servers/pm_assure/server.py`

**3 Tools:**
1. `nista_longitudinal_trend` — compliance score history, trend direction, breaches
2. `track_review_actions` — AI extraction + deduplication + cross-cycle recurrence
3. `review_action_status` — retrieve actions by project and status

See [`docs/assurance.md`](../../docs/assurance.md) for full reference.

## Next Steps

1. Complete Phase 2 (real parser integration for pm-data)
2. Test with sample MSPDI/NISTA files
3. Build Phase 4 (pm-validate with full NISTA v1.0 schema)
4. Add P1 Artefact Currency Validator (`check_artefact_currency` MCP tool)

## Attribution

All work: antnewman <antjsnewman@outlook.com>
For: PDA Task Force
Supporting: NISTA Programme and Project Data Standard trial
