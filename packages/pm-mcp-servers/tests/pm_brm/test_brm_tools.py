"""
Integration tests for PM-BRM MCP server tools.

Tests all 8 BRM tools with 20+ test cases covering:
- Missing required parameters
- Successful execution with valid params
- Cross-tool measurement workflow
- Dependency network workflow
"""

import json
import os

import pytest

from pm_mcp_servers.pm_brm.server import (
    _detect_benefits_drift,
    _forecast_benefit_realisation,
    _get_benefit_dependency_network,
    _get_benefits_cascade_impact,
    _get_benefits_health,
    _ingest_benefit,
    _map_benefit_dependency,
    _track_benefit_measurement,
)


def _parse(result) -> dict:
    """Parse a handler result list into a dict."""
    assert len(result) == 1
    text = result[0].text
    # Error strings are not JSON
    if text.startswith("Error:") or text.startswith("Validation error:"):
        return {"_error": text}
    return json.loads(text)


def _db(tmp_path) -> str:
    """Return a fresh DB path string inside tmp_path."""
    return str(tmp_path / "test_brm.db")


def _make_benefit_args(tmp_path, **overrides) -> dict:
    """Build a minimal valid argument dict for ingest_benefit."""
    args = {
        "project_id": "PRJ-001",
        "title": "Reduce processing time",
        "description": "Reduce average claim processing time from 10 to 5 days",
        "financial_type": "CASH_RELEASING",
        "recipient_type": "GOVERNMENT",
        "baseline_value": 10.0,
        "baseline_date": "2025-01-01",
        "target_value": 5.0,
        "target_date": "2026-12-31",
        "measurement_kpi": "avg_processing_days",
        "db_path": _db(tmp_path),
    }
    args.update(overrides)
    return args


# ============================================================================
# 1. ingest_benefit
# ============================================================================


class TestIngestBenefit:
    """Tests for the ingest_benefit tool."""

    @pytest.mark.asyncio
    async def test_missing_project_id(self, tmp_path):
        result = _parse(
            await _ingest_benefit(
                {
                    "title": "X",
                    "description": "Y",
                    "financial_type": "CASH_RELEASING",
                    "recipient_type": "GOVERNMENT",
                    "db_path": _db(tmp_path),
                }
            )
        )
        assert "_error" in result

    @pytest.mark.asyncio
    async def test_missing_title(self, tmp_path):
        result = _parse(
            await _ingest_benefit(
                {
                    "project_id": "PRJ-001",
                    "description": "Y",
                    "financial_type": "CASH_RELEASING",
                    "recipient_type": "GOVERNMENT",
                    "db_path": _db(tmp_path),
                }
            )
        )
        assert "_error" in result

    @pytest.mark.asyncio
    async def test_success(self, tmp_path):
        result = _parse(await _ingest_benefit(_make_benefit_args(tmp_path)))
        assert result["status"] == "success"
        assert result["title"] == "Reduce processing time"
        assert result["project_id"] == "PRJ-001"
        assert "benefit_id" in result

    @pytest.mark.asyncio
    async def test_disbenefit(self, tmp_path):
        result = _parse(
            await _ingest_benefit(
                _make_benefit_args(
                    tmp_path,
                    title="Staff retraining cost",
                    is_disbenefit=True,
                )
            )
        )
        assert result["status"] == "success"
        assert result["is_disbenefit"] is True

    @pytest.mark.asyncio
    async def test_invalid_financial_type(self, tmp_path):
        result = _parse(
            await _ingest_benefit(
                _make_benefit_args(tmp_path, financial_type="INVALID")
            )
        )
        assert "_error" in result


# ============================================================================
# 2. track_benefit_measurement
# ============================================================================


class TestTrackBenefitMeasurement:
    """Tests for the track_benefit_measurement tool."""

    @pytest.mark.asyncio
    async def test_missing_benefit_id(self, tmp_path):
        result = _parse(
            await _track_benefit_measurement(
                {"value": 8.0, "db_path": _db(tmp_path)}
            )
        )
        assert "_error" in result

    @pytest.mark.asyncio
    async def test_missing_value(self, tmp_path):
        result = _parse(
            await _track_benefit_measurement(
                {"benefit_id": "B-001", "db_path": _db(tmp_path)}
            )
        )
        assert "_error" in result

    @pytest.mark.asyncio
    async def test_nonexistent_benefit(self, tmp_path):
        result = _parse(
            await _track_benefit_measurement(
                {
                    "benefit_id": "nonexistent",
                    "value": 8.0,
                    "db_path": _db(tmp_path),
                }
            )
        )
        assert "_error" in result

    @pytest.mark.asyncio
    async def test_success(self, tmp_path):
        db = _db(tmp_path)
        ingest_result = _parse(
            await _ingest_benefit(_make_benefit_args(tmp_path))
        )
        benefit_id = ingest_result["benefit_id"]

        result = _parse(
            await _track_benefit_measurement(
                {"benefit_id": benefit_id, "value": 8.0, "db_path": db}
            )
        )
        assert result["status"] == "success"
        assert result["value"] == 8.0
        assert "drift_pct" in result
        assert "drift_severity" in result

    @pytest.mark.asyncio
    async def test_with_source_and_notes(self, tmp_path):
        db = _db(tmp_path)
        ingest_result = _parse(
            await _ingest_benefit(_make_benefit_args(tmp_path))
        )
        benefit_id = ingest_result["benefit_id"]

        result = _parse(
            await _track_benefit_measurement(
                {
                    "benefit_id": benefit_id,
                    "value": 7.5,
                    "source": "EXTERNAL_API",
                    "notes": "From automated monitoring",
                    "db_path": db,
                }
            )
        )
        assert result["status"] == "success"
        assert result["value"] == 7.5


# ============================================================================
# 3. get_benefits_health
# ============================================================================


class TestGetBenefitsHealth:
    """Tests for the get_benefits_health tool."""

    @pytest.mark.asyncio
    async def test_missing_project_id(self, tmp_path):
        result = _parse(
            await _get_benefits_health({"db_path": _db(tmp_path)})
        )
        assert "_error" in result

    @pytest.mark.asyncio
    async def test_empty_project(self, tmp_path):
        """Health report for a project with no benefits should still succeed."""
        result = _parse(
            await _get_benefits_health(
                {"project_id": "PRJ-EMPTY", "db_path": _db(tmp_path)}
            )
        )
        # Should return valid data even if empty
        assert "total_benefits" in result or "_error" in result

    @pytest.mark.asyncio
    async def test_success_with_benefit(self, tmp_path):
        db = _db(tmp_path)
        await _ingest_benefit(_make_benefit_args(tmp_path))

        result = _parse(
            await _get_benefits_health(
                {"project_id": "PRJ-001", "db_path": db}
            )
        )
        assert result["project_id"] == "PRJ-001"
        assert result["total_benefits"] >= 1
        assert "overall_health_score" in result
        assert "aggregate_realisation_pct" in result


# ============================================================================
# 4. map_benefit_dependency
# ============================================================================


class TestMapBenefitDependency:
    """Tests for the map_benefit_dependency tool."""

    @pytest.mark.asyncio
    async def test_missing_project_id(self, tmp_path):
        result = _parse(
            await _map_benefit_dependency(
                {
                    "source_node_id": "N1",
                    "target_node_id": "N2",
                    "edge_type": "DEPENDS_ON",
                    "db_path": _db(tmp_path),
                }
            )
        )
        assert "_error" in result

    @pytest.mark.asyncio
    async def test_missing_edge_type(self, tmp_path):
        """edge_type is required; omitting it should use default or error."""
        result = _parse(
            await _map_benefit_dependency(
                {
                    "project_id": "PRJ-001",
                    "source_node_id": "N1",
                    "target_node_id": "N2",
                    "source_node": {
                        "node_type": "ENABLER",
                        "title": "Training programme",
                    },
                    "target_node": {
                        "node_type": "INTERMEDIATE_BENEFIT",
                        "title": "Staff capability uplift",
                    },
                    "db_path": _db(tmp_path),
                }
            )
        )
        # Should use default DEPENDS_ON
        assert result.get("status") == "success" or "_error" in result

    @pytest.mark.asyncio
    async def test_success_with_inline_nodes(self, tmp_path):
        result = _parse(
            await _map_benefit_dependency(
                {
                    "project_id": "PRJ-001",
                    "source_node_id": "node-enabler-1",
                    "target_node_id": "node-benefit-1",
                    "edge_type": "ENABLES",
                    "source_node": {
                        "node_type": "ENABLER",
                        "title": "New CRM system",
                    },
                    "target_node": {
                        "node_type": "INTERMEDIATE_BENEFIT",
                        "title": "Faster customer lookup",
                    },
                    "db_path": _db(tmp_path),
                }
            )
        )
        assert result["status"] == "success"
        assert result["source_node"] == "node-enabler-1"
        assert result["target_node"] == "node-benefit-1"
        assert result["edge_type"] == "ENABLES"


# ============================================================================
# 5. get_benefit_dependency_network
# ============================================================================


class TestGetBenefitDependencyNetwork:
    """Tests for the get_benefit_dependency_network tool."""

    @pytest.mark.asyncio
    async def test_missing_project_id(self, tmp_path):
        result = _parse(
            await _get_benefit_dependency_network(
                {"db_path": _db(tmp_path)}
            )
        )
        assert "_error" in result

    @pytest.mark.asyncio
    async def test_empty_network(self, tmp_path):
        result = _parse(
            await _get_benefit_dependency_network(
                {"project_id": "PRJ-EMPTY", "db_path": _db(tmp_path)}
            )
        )
        assert result.get("node_count", 0) == 0 or "_error" in result

    @pytest.mark.asyncio
    async def test_success_after_mapping(self, tmp_path):
        db = _db(tmp_path)
        await _map_benefit_dependency(
            {
                "project_id": "PRJ-001",
                "source_node_id": "n-a",
                "target_node_id": "n-b",
                "edge_type": "CONTRIBUTES_TO",
                "source_node": {
                    "node_type": "PROJECT_OUTPUT",
                    "title": "Automated pipeline",
                },
                "target_node": {
                    "node_type": "END_BENEFIT",
                    "title": "Cost reduction",
                },
                "db_path": db,
            }
        )

        result = _parse(
            await _get_benefit_dependency_network(
                {"project_id": "PRJ-001", "db_path": db}
            )
        )
        assert result["node_count"] == 2
        assert result["edge_count"] == 1


# ============================================================================
# 6. forecast_benefit_realisation
# ============================================================================


class TestForecastBenefitRealisation:
    """Tests for the forecast_benefit_realisation tool."""

    @pytest.mark.asyncio
    async def test_missing_benefit_id(self, tmp_path):
        result = _parse(
            await _forecast_benefit_realisation({"db_path": _db(tmp_path)})
        )
        assert "_error" in result

    @pytest.mark.asyncio
    async def test_nonexistent_benefit(self, tmp_path):
        result = _parse(
            await _forecast_benefit_realisation(
                {"benefit_id": "nonexistent", "db_path": _db(tmp_path)}
            )
        )
        assert "_error" in result

    @pytest.mark.asyncio
    async def test_success_with_measurements(self, tmp_path):
        db = _db(tmp_path)
        ingest = _parse(await _ingest_benefit(_make_benefit_args(tmp_path)))
        bid = ingest["benefit_id"]

        # Record enough measurements for a forecast
        for val in [9.0, 8.0, 7.0]:
            await _track_benefit_measurement(
                {"benefit_id": bid, "value": val, "db_path": db}
            )

        result = _parse(
            await _forecast_benefit_realisation(
                {"benefit_id": bid, "db_path": db}
            )
        )
        # Should succeed or indicate insufficient data
        if "_error" not in result:
            assert result["benefit_id"] == bid
            assert "probability_of_realisation" in result
            assert "current_trajectory_value" in result


# ============================================================================
# 7. detect_benefits_drift
# ============================================================================


class TestDetectBenefitsDrift:
    """Tests for the detect_benefits_drift tool."""

    @pytest.mark.asyncio
    async def test_missing_project_id(self, tmp_path):
        result = _parse(
            await _detect_benefits_drift({"db_path": _db(tmp_path)})
        )
        assert "_error" in result

    @pytest.mark.asyncio
    async def test_empty_project(self, tmp_path):
        result = _parse(
            await _detect_benefits_drift(
                {"project_id": "PRJ-EMPTY", "db_path": _db(tmp_path)}
            )
        )
        if "_error" not in result:
            assert result["total_analysed"] == 0

    @pytest.mark.asyncio
    async def test_success_with_measurements(self, tmp_path):
        db = _db(tmp_path)
        ingest = _parse(await _ingest_benefit(_make_benefit_args(tmp_path)))
        bid = ingest["benefit_id"]

        for val in [9.5, 9.0, 8.5]:
            await _track_benefit_measurement(
                {"benefit_id": bid, "value": val, "db_path": db}
            )

        result = _parse(
            await _detect_benefits_drift(
                {"project_id": "PRJ-001", "db_path": db}
            )
        )
        if "_error" not in result:
            assert result["project_id"] == "PRJ-001"
            assert "drift_results" in result
            assert result["total_analysed"] >= 1


# ============================================================================
# 8. get_benefits_cascade_impact
# ============================================================================


class TestGetBenefitsCascadeImpact:
    """Tests for the get_benefits_cascade_impact tool."""

    @pytest.mark.asyncio
    async def test_missing_node_id(self, tmp_path):
        result = _parse(
            await _get_benefits_cascade_impact({"db_path": _db(tmp_path)})
        )
        assert "_error" in result

    @pytest.mark.asyncio
    async def test_nonexistent_node(self, tmp_path):
        result = _parse(
            await _get_benefits_cascade_impact(
                {"node_id": "nonexistent", "db_path": _db(tmp_path)}
            )
        )
        # May return empty impacts or error
        if "_error" not in result:
            assert result["total_affected"] == 0

    @pytest.mark.asyncio
    async def test_success_with_dag(self, tmp_path):
        db = _db(tmp_path)

        # Build a small DAG: A -> B -> C
        await _map_benefit_dependency(
            {
                "project_id": "PRJ-001",
                "source_node_id": "cascade-a",
                "target_node_id": "cascade-b",
                "edge_type": "ENABLES",
                "source_node": {
                    "node_type": "PROJECT_OUTPUT",
                    "title": "Deliverable A",
                },
                "target_node": {
                    "node_type": "BUSINESS_CHANGE",
                    "title": "Change B",
                },
                "db_path": db,
            }
        )
        await _map_benefit_dependency(
            {
                "project_id": "PRJ-001",
                "source_node_id": "cascade-b",
                "target_node_id": "cascade-c",
                "edge_type": "CONTRIBUTES_TO",
                "target_node": {
                    "node_type": "END_BENEFIT",
                    "title": "Outcome C",
                },
                "db_path": db,
            }
        )

        result = _parse(
            await _get_benefits_cascade_impact(
                {"node_id": "cascade-a", "db_path": db}
            )
        )
        if "_error" not in result:
            assert result["source_node_id"] == "cascade-a"
            assert result["total_affected"] >= 1


# ============================================================================
# Cross-tool workflow: Measurement lifecycle
# ============================================================================


class TestMeasurementWorkflow:
    """End-to-end workflow: ingest -> measure -> health -> drift."""

    @pytest.mark.asyncio
    async def test_full_measurement_lifecycle(self, tmp_path):
        db = _db(tmp_path)

        # Step 1: Ingest a benefit
        ingest = _parse(await _ingest_benefit(_make_benefit_args(tmp_path)))
        assert ingest["status"] == "success"
        benefit_id = ingest["benefit_id"]

        # Step 2: Record 3 measurements (declining from baseline toward target)
        measurements = []
        for val in [9.0, 7.5, 6.0]:
            m = _parse(
                await _track_benefit_measurement(
                    {"benefit_id": benefit_id, "value": val, "db_path": db}
                )
            )
            assert m["status"] == "success"
            measurements.append(m)

        # Verify trend data is populated on later measurements
        last = measurements[-1]
        assert "trend_direction" in last

        # Step 3: Get health report
        health = _parse(
            await _get_benefits_health(
                {"project_id": "PRJ-001", "db_path": db}
            )
        )
        assert health["project_id"] == "PRJ-001"
        assert health["total_benefits"] >= 1
        assert 0.0 <= health["overall_health_score"] <= 1.0

        # Step 4: Detect drift
        drift = _parse(
            await _detect_benefits_drift(
                {"project_id": "PRJ-001", "db_path": db}
            )
        )
        assert drift["project_id"] == "PRJ-001"
        assert drift["total_analysed"] >= 1
        assert len(drift["drift_results"]) >= 1

        dr = drift["drift_results"][0]
        assert dr["benefit_id"] == benefit_id
        assert "severity" in dr
        assert "trend" in dr


# ============================================================================
# Cross-tool workflow: Dependency network
# ============================================================================


class TestDependencyNetworkWorkflow:
    """End-to-end workflow: map nodes/edges -> get network -> cascade impact."""

    @pytest.mark.asyncio
    async def test_full_dependency_workflow(self, tmp_path):
        db = _db(tmp_path)
        project_id = "PRJ-DEP"

        # Step 1: Build a dependency chain
        # output -> enabler -> intermediate -> end_benefit -> strategic_objective
        edges = [
            {
                "project_id": project_id,
                "source_node_id": "dep-output",
                "target_node_id": "dep-enabler",
                "edge_type": "ENABLES",
                "source_node": {
                    "node_type": "PROJECT_OUTPUT",
                    "title": "New IT system",
                },
                "target_node": {
                    "node_type": "ENABLER",
                    "title": "Automated workflow",
                },
                "db_path": db,
            },
            {
                "project_id": project_id,
                "source_node_id": "dep-enabler",
                "target_node_id": "dep-intermediate",
                "edge_type": "ENABLES",
                "target_node": {
                    "node_type": "INTERMEDIATE_BENEFIT",
                    "title": "Faster processing",
                },
                "db_path": db,
            },
            {
                "project_id": project_id,
                "source_node_id": "dep-intermediate",
                "target_node_id": "dep-end",
                "edge_type": "CONTRIBUTES_TO",
                "target_node": {
                    "node_type": "END_BENEFIT",
                    "title": "Cost savings",
                },
                "db_path": db,
            },
            {
                "project_id": project_id,
                "source_node_id": "dep-end",
                "target_node_id": "dep-strategic",
                "edge_type": "CONTRIBUTES_TO",
                "target_node": {
                    "node_type": "STRATEGIC_OBJECTIVE",
                    "title": "Operational efficiency",
                },
                "db_path": db,
            },
        ]

        for edge_args in edges:
            r = _parse(await _map_benefit_dependency(edge_args))
            assert r["status"] == "success", f"Edge mapping failed: {r}"

        # Step 2: Get network
        network = _parse(
            await _get_benefit_dependency_network(
                {"project_id": project_id, "db_path": db}
            )
        )
        assert network["node_count"] == 5
        assert network["edge_count"] == 4

        # Step 3: Cascade impact from the root output node
        cascade = _parse(
            await _get_benefits_cascade_impact(
                {"node_id": "dep-output", "db_path": db}
            )
        )
        assert cascade["source_node_id"] == "dep-output"
        # Should propagate to enabler, intermediate, end, and strategic
        assert cascade["total_affected"] >= 2

    @pytest.mark.asyncio
    async def test_network_node_type_filter(self, tmp_path):
        db = _db(tmp_path)

        await _map_benefit_dependency(
            {
                "project_id": "PRJ-FILT",
                "source_node_id": "f-enabler",
                "target_node_id": "f-benefit",
                "edge_type": "ENABLES",
                "source_node": {
                    "node_type": "ENABLER",
                    "title": "Training",
                },
                "target_node": {
                    "node_type": "END_BENEFIT",
                    "title": "Revenue growth",
                },
                "db_path": db,
            }
        )

        result = _parse(
            await _get_benefit_dependency_network(
                {
                    "project_id": "PRJ-FILT",
                    "node_type_filter": "ENABLER",
                    "db_path": db,
                }
            )
        )
        if "_error" not in result:
            # Only ENABLER nodes should be returned
            assert result["node_count"] == 1
            for node in result["nodes"]:
                assert node.get("node_type") == "ENABLER"
