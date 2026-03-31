"""Tests for the unified pda-platform MCP server.

Covers:
  - Server creation and tool aggregation
  - All 5 registry modules load correctly
  - No duplicate tool names across modules
  - Every tool has a dispatch entry
  - Tool count matches expected total
  - Remote SSE server creates correctly
  - Individual servers still work independently
"""

import pytest


class TestUnifiedServerImports:
    """Test that the unified server and all registries import cleanly."""

    def test_unified_server_imports(self):
        from pm_mcp_servers.pda_platform import server

        assert server is not None

    def test_unified_server_instance(self):
        from pm_mcp_servers.pda_platform.server import server

        assert server is not None
        assert server.name == "pda-platform"

    def test_all_tools_populated(self):
        from pm_mcp_servers.pda_platform.server import ALL_TOOLS

        assert len(ALL_TOOLS) > 0

    def test_tool_dispatch_populated(self):
        from pm_mcp_servers.pda_platform.server import _TOOL_DISPATCH

        assert len(_TOOL_DISPATCH) > 0


class TestRegistryModules:
    """Test that each registry module exports TOOLS and dispatch correctly."""

    def test_data_registry_loads(self):
        from pm_mcp_servers.pm_data.registry import TOOLS, dispatch

        assert len(TOOLS) == 6
        assert callable(dispatch)

    def test_analyse_registry_loads(self):
        from pm_mcp_servers.pm_analyse.registry import TOOLS, dispatch

        assert len(TOOLS) == 6
        assert callable(dispatch)

    def test_validate_registry_loads(self):
        from pm_mcp_servers.pm_validate.registry import TOOLS, dispatch

        assert len(TOOLS) == 4
        assert callable(dispatch)

    def test_nista_registry_loads(self):
        from pm_mcp_servers.pm_nista.registry import TOOLS, dispatch

        assert len(TOOLS) == 5
        assert callable(dispatch)

    def test_assure_registry_loads(self):
        from pm_mcp_servers.pm_assure.registry import TOOLS, dispatch

        assert len(TOOLS) == 20
        assert callable(dispatch)


class TestToolAggregation:
    """Test that tool aggregation in the unified server is correct."""

    def test_total_tool_count(self):
        """Unified server has exactly 41 tools (6+6+4+5+20)."""
        from pm_mcp_servers.pda_platform.server import ALL_TOOLS

        assert len(ALL_TOOLS) == 41

    def test_no_duplicate_tool_names(self):
        """No two tools share the same name across modules."""
        from pm_mcp_servers.pda_platform.server import ALL_TOOLS

        names = [t.name for t in ALL_TOOLS]
        assert len(names) == len(set(names)), f"Duplicate tools: {[n for n in names if names.count(n) > 1]}"

    def test_every_tool_has_dispatch(self):
        """Every registered tool has a corresponding dispatch function."""
        from pm_mcp_servers.pda_platform.server import ALL_TOOLS, _TOOL_DISPATCH

        missing = [t.name for t in ALL_TOOLS if t.name not in _TOOL_DISPATCH]
        assert len(missing) == 0, f"Tools without dispatch: {missing}"

    def test_tool_ordering(self):
        """Tools appear in module order: data, analyse, validate, nista, assure."""
        from pm_mcp_servers.pda_platform.server import ALL_TOOLS

        names = [t.name for t in ALL_TOOLS]
        # First tool should be from pm-data
        assert names[0] == "load_project"
        # Last tool should be from pm-assure
        assert names[-1] == "get_cascade_impact"

    def test_all_tools_have_valid_schemas(self):
        """Every tool has a name, description, and inputSchema."""
        from pm_mcp_servers.pda_platform.server import ALL_TOOLS

        for tool in ALL_TOOLS:
            assert tool.name, "Tool has no name"
            assert tool.description, f"Tool {tool.name} has no description"
            assert tool.inputSchema, f"Tool {tool.name} has no inputSchema"
            assert tool.inputSchema.get("type") == "object", f"Tool {tool.name} schema is not object type"


class TestExpectedTools:
    """Verify the exact set of expected tool names is present."""

    EXPECTED_DATA_TOOLS = {
        "load_project", "query_tasks", "get_critical_path",
        "get_dependencies", "convert_format", "get_project_summary",
    }

    EXPECTED_ANALYSE_TOOLS = {
        "identify_risks", "forecast_completion", "detect_outliers",
        "assess_health", "suggest_mitigations", "compare_baseline",
    }

    EXPECTED_VALIDATE_TOOLS = {
        "validate_structure", "validate_semantic",
        "validate_nista", "validate_custom",
    }

    EXPECTED_NISTA_TOOLS = {
        "generate_gmpp_report", "generate_narrative",
        "submit_to_nista", "fetch_nista_metadata", "validate_gmpp_report",
    }

    EXPECTED_ASSURE_TOOLS = {
        "nista_longitudinal_trend", "track_review_actions", "review_action_status",
        "check_artefact_currency", "check_confidence_divergence",
        "recommend_review_schedule", "log_override_decision",
        "analyse_override_patterns", "ingest_lesson", "search_lessons",
        "log_assurance_activity", "analyse_assurance_overhead",
        "run_assurance_workflow", "get_workflow_history",
        "classify_project_domain", "reclassify_from_store",
        "ingest_assumption", "validate_assumption",
        "get_assumption_drift", "get_cascade_impact",
    }

    def test_data_tools_present(self):
        from pm_mcp_servers.pm_data.registry import TOOLS

        actual = {t.name for t in TOOLS}
        assert actual == self.EXPECTED_DATA_TOOLS

    def test_analyse_tools_present(self):
        from pm_mcp_servers.pm_analyse.registry import TOOLS

        actual = {t.name for t in TOOLS}
        assert actual == self.EXPECTED_ANALYSE_TOOLS

    def test_validate_tools_present(self):
        from pm_mcp_servers.pm_validate.registry import TOOLS

        actual = {t.name for t in TOOLS}
        assert actual == self.EXPECTED_VALIDATE_TOOLS

    def test_nista_tools_present(self):
        from pm_mcp_servers.pm_nista.registry import TOOLS

        actual = {t.name for t in TOOLS}
        assert actual == self.EXPECTED_NISTA_TOOLS

    def test_assure_tools_present(self):
        from pm_mcp_servers.pm_assure.registry import TOOLS

        actual = {t.name for t in TOOLS}
        assert actual == self.EXPECTED_ASSURE_TOOLS

    def test_all_expected_tools_in_unified(self):
        """Every expected tool from every module is in the unified server."""
        from pm_mcp_servers.pda_platform.server import ALL_TOOLS

        actual = {t.name for t in ALL_TOOLS}
        expected = (
            self.EXPECTED_DATA_TOOLS
            | self.EXPECTED_ANALYSE_TOOLS
            | self.EXPECTED_VALIDATE_TOOLS
            | self.EXPECTED_NISTA_TOOLS
            | self.EXPECTED_ASSURE_TOOLS
        )
        assert actual == expected


class TestRemoteServer:
    """Test the SSE remote server wrapper."""

    def test_remote_module_imports(self):
        from pm_mcp_servers.pda_platform import remote

        assert remote is not None

    def test_starlette_app_created(self):
        from pm_mcp_servers.pda_platform.remote import app

        assert app is not None

    def test_routes_registered(self):
        from pm_mcp_servers.pda_platform.remote import app

        paths = [r.path for r in app.routes]
        assert "/sse" in paths
        assert "/messages" in paths
        assert "/health" in paths

    def test_main_entry_point_exists(self):
        from pm_mcp_servers.pda_platform.remote import main

        assert callable(main)


class TestIndividualServersStillWork:
    """Verify that individual servers are unbroken by unified server changes."""

    def test_pm_data_server(self):
        from pm_mcp_servers.pm_data.server import server

        assert server.name == "pm-data"

    def test_pm_analyse_server(self):
        from pm_mcp_servers.pm_analyse.server import server

        assert server.name == "pm-analyse"

    def test_pm_validate_server(self):
        from pm_mcp_servers.pm_validate.server import app

        assert app.name == "pm-validate"

    def test_pm_nista_server(self):
        from pm_mcp_servers.pm_nista.server import app

        assert app.name == "pm-nista-server"

    def test_pm_assure_server(self):
        from pm_mcp_servers.pm_assure.server import app

        assert app.name == "pm-assure-server"


@pytest.mark.asyncio
class TestUnifiedDispatch:
    """Test that the unified call_tool dispatcher routes correctly."""

    async def test_unknown_tool_returns_error(self):
        from pm_mcp_servers.pda_platform.server import call_tool

        result = await call_tool("nonexistent_tool_xyz", {})
        assert len(result) == 1
        assert "Unknown tool" in result[0].text
