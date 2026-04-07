"""Tests for the Benefits Realisation Management module (P13)."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from pm_data_tools.assurance.assumptions import DriftSeverity
from pm_data_tools.assurance.benefits import (
    Benefit,
    BenefitConfig,
    BenefitDriftResult,
    BenefitForecast,
    BenefitMeasurement,
    BenefitStatus,
    BenefitsHealthReport,
    BenefitsTracker,
    DependencyEdge,
    DependencyNode,
    EdgeType,
    Explicitness,
    FinancialType,
    IndicatorType,
    IpaLifecycleStage,
    MeasurementFrequency,
    MeasurementSource,
    NodeType,
    RecipientType,
    TrendDirection,
)
from pm_data_tools.db.store import AssuranceStore


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def store(tmp_path: Path) -> AssuranceStore:
    """An isolated AssuranceStore backed by a temp file."""
    return AssuranceStore(db_path=tmp_path / "test_benefits.db")


@pytest.fixture()
def tracker(store: AssuranceStore) -> BenefitsTracker:
    """BenefitsTracker backed by the isolated temp store."""
    return BenefitsTracker(store=store)


@pytest.fixture()
def sample_benefit() -> Benefit:
    """A standard benefit with baseline and target for measurement tests."""
    return Benefit(
        project_id="PROJ-001",
        title="Reduced processing time",
        description="Average processing time reduced from 15 to 5 days",
        financial_type=FinancialType.NON_CASH_RELEASING,
        recipient_type=RecipientType.GOVERNMENT,
        baseline_value=15.0,
        target_value=5.0,
        target_date=date(2027, 3, 31),
        measurement_kpi="avg_processing_days",
    )


@pytest.fixture()
def sample_disbenefit() -> Benefit:
    """A dis-benefit for negative consequence tracking."""
    return Benefit(
        project_id="PROJ-001",
        title="Increased support calls",
        description="Temporary increase in helpdesk volume during transition",
        is_disbenefit=True,
        financial_type=FinancialType.QUANTIFIABLE,
        recipient_type=RecipientType.GOVERNMENT,
        baseline_value=100.0,
        target_value=150.0,
        measurement_kpi="monthly_support_calls",
    )


def _make_benefit(
    project_id: str = "PROJ-001",
    title: str = "Test benefit",
    description: str = "A test benefit.",
    financial_type: FinancialType = FinancialType.NON_CASH_RELEASING,
    recipient_type: RecipientType = RecipientType.GOVERNMENT,
    baseline_value: float | None = 100.0,
    target_value: float | None = 50.0,
    target_date: date | None = None,
    **kwargs: object,
) -> Benefit:
    """Helper to build a Benefit with sensible defaults."""
    return Benefit(
        project_id=project_id,
        title=title,
        description=description,
        financial_type=financial_type,
        recipient_type=recipient_type,
        baseline_value=baseline_value,
        target_value=target_value,
        target_date=target_date,
        **kwargs,  # type: ignore[arg-type]
    )


# ===========================================================================
# 1. TestEnums
# ===========================================================================


class TestEnums:
    """Verify enum members and their string values."""

    def test_benefit_status_values(self) -> None:
        """BenefitStatus has all six lifecycle states."""
        expected = {
            "IDENTIFIED",
            "PLANNED",
            "REALIZING",
            "ACHIEVED",
            "EVAPORATED",
            "CANCELLED",
        }
        actual = {s.value for s in BenefitStatus}
        assert actual == expected

    def test_financial_type_values(self) -> None:
        """FinancialType covers the four Green Book categories."""
        expected = {
            "CASH_RELEASING",
            "NON_CASH_RELEASING",
            "QUANTIFIABLE",
            "QUALITATIVE",
        }
        actual = {f.value for f in FinancialType}
        assert actual == expected

    def test_recipient_type_values(self) -> None:
        """RecipientType has the three IPA recipient categories."""
        expected = {"GOVERNMENT", "PRIVATE_SECTOR", "WIDER_UK_PUBLIC"}
        actual = {r.value for r in RecipientType}
        assert actual == expected

    def test_node_type_values(self) -> None:
        """NodeType covers all six dependency hierarchy levels."""
        expected = {
            "STRATEGIC_OBJECTIVE",
            "END_BENEFIT",
            "INTERMEDIATE_BENEFIT",
            "BUSINESS_CHANGE",
            "ENABLER",
            "PROJECT_OUTPUT",
        }
        actual = {n.value for n in NodeType}
        assert actual == expected


# ===========================================================================
# 2. TestBenefitModel
# ===========================================================================


class TestBenefitModel:
    """Pydantic model creation, defaults, and validation."""

    def test_creation_with_defaults(self) -> None:
        """Benefit created with only required fields gets sensible defaults."""
        b = Benefit(
            project_id="PROJ-001",
            title="Cost saving",
            description="Reduced staffing costs",
            financial_type=FinancialType.CASH_RELEASING,
            recipient_type=RecipientType.GOVERNMENT,
        )
        assert b.status == BenefitStatus.IDENTIFIED
        assert b.is_disbenefit is False
        assert b.explicitness == Explicitness.QUANTIFIABLE
        assert b.measurement_frequency == MeasurementFrequency.QUARTERLY
        assert b.indicator_type == IndicatorType.LAGGING
        assert b.ipa_lifecycle_stage == IpaLifecycleStage.IDENTIFY_QUANTIFY

    def test_required_fields_enforced(self) -> None:
        """Missing required fields raises ValidationError."""
        with pytest.raises(Exception):
            Benefit(
                project_id="PROJ-001",
                title="Missing fields",
                # description, financial_type, recipient_type omitted
            )  # type: ignore[call-arg]

    def test_uuid_auto_generated(self) -> None:
        """Each Benefit gets a unique UUID4 identifier."""
        b1 = _make_benefit()
        b2 = _make_benefit()
        assert len(b1.id) == 36
        assert "-" in b1.id
        assert b1.id != b2.id

    def test_disbenefit_flag(self) -> None:
        """is_disbenefit=True marks the benefit as a negative consequence."""
        b = _make_benefit(is_disbenefit=True)
        assert b.is_disbenefit is True


# ===========================================================================
# 3. TestBenefitsTrackerCRUD
# ===========================================================================


class TestBenefitsTrackerCRUD:
    """Ingest, retrieve, filter, and update operations."""

    def test_ingest_and_retrieve(
        self, tracker: BenefitsTracker, sample_benefit: Benefit
    ) -> None:
        """Ingested benefit can be retrieved with all fields intact."""
        tracker.ingest(sample_benefit)
        results = tracker.get_benefits("PROJ-001")
        assert len(results) == 1
        r = results[0]
        assert r.id == sample_benefit.id
        assert r.title == "Reduced processing time"
        assert r.baseline_value == 15.0
        assert r.target_value == 5.0
        assert r.financial_type == FinancialType.NON_CASH_RELEASING

    def test_ingest_batch(self, tracker: BenefitsTracker) -> None:
        """Multiple benefits ingested; correct count returned."""
        benefits = [_make_benefit(title=f"Benefit {i}") for i in range(5)]
        count = tracker.ingest_batch(benefits)
        assert count == 5
        assert len(tracker.get_benefits("PROJ-001")) == 5

    def test_get_benefits_filter_by_status(
        self, tracker: BenefitsTracker
    ) -> None:
        """Filter by status returns only matching benefits."""
        b1 = _make_benefit(title="Planned A", status=BenefitStatus.PLANNED)
        b2 = _make_benefit(title="Realizing A", status=BenefitStatus.REALIZING)
        b3 = _make_benefit(title="Planned B", status=BenefitStatus.PLANNED)
        tracker.ingest_batch([b1, b2, b3])

        planned = tracker.get_benefits("PROJ-001", status=BenefitStatus.PLANNED)
        assert len(planned) == 2
        assert all(b.status == BenefitStatus.PLANNED for b in planned)

    def test_get_benefits_filter_by_financial_type(
        self, tracker: BenefitsTracker
    ) -> None:
        """Filter by financial_type returns only matching benefits."""
        b1 = _make_benefit(title="Cash A", financial_type=FinancialType.CASH_RELEASING)
        b2 = _make_benefit(title="Non-cash A", financial_type=FinancialType.NON_CASH_RELEASING)
        tracker.ingest_batch([b1, b2])

        cash = tracker.get_benefits(
            "PROJ-001", financial_type=FinancialType.CASH_RELEASING
        )
        assert len(cash) == 1
        assert cash[0].title == "Cash A"

    def test_update_status(
        self, tracker: BenefitsTracker, sample_benefit: Benefit
    ) -> None:
        """update_status changes the lifecycle status and returns updated benefit."""
        tracker.ingest(sample_benefit)
        updated = tracker.update_status(sample_benefit.id, BenefitStatus.REALIZING)
        assert updated.status == BenefitStatus.REALIZING

    def test_update_status_missing_benefit_raises(
        self, tracker: BenefitsTracker
    ) -> None:
        """update_status raises ValueError for a non-existent benefit ID."""
        with pytest.raises(ValueError, match="not found"):
            tracker.update_status("nonexistent-id", BenefitStatus.ACHIEVED)

    def test_disbenefit_handling(
        self, tracker: BenefitsTracker, sample_disbenefit: Benefit
    ) -> None:
        """Dis-benefits are persisted and retrieved with is_disbenefit=True."""
        tracker.ingest(sample_disbenefit)
        results = tracker.get_benefits("PROJ-001")
        assert len(results) == 1
        assert results[0].is_disbenefit is True
        assert results[0].title == "Increased support calls"


# ===========================================================================
# 4. TestMeasurementTracking
# ===========================================================================


class TestMeasurementTracking:
    """Measurement recording, drift, severity, realisation, and trend."""

    def test_record_measurement_computes_drift(
        self, tracker: BenefitsTracker, sample_benefit: Benefit
    ) -> None:
        """drift_pct computed from baseline: abs((12-15)/15)*100 = 20.0."""
        tracker.ingest(sample_benefit)
        m = tracker.record_measurement(sample_benefit.id, value=12.0)
        assert m.drift_pct == pytest.approx(20.0)
        assert m.drift_severity in list(DriftSeverity)

    def test_severity_thresholds(
        self, store: AssuranceStore
    ) -> None:
        """Drift severity correctly classified at each threshold boundary."""
        config = BenefitConfig(
            minor_threshold_pct=5.0,
            moderate_threshold_pct=15.0,
            significant_threshold_pct=30.0,
        )
        t = BenefitsTracker(store=store, config=config)

        # Baseline 100, so value of X gives drift = abs(X-100)%
        b_none = _make_benefit(title="None drift", baseline_value=100.0, target_value=50.0)
        t.ingest(b_none)
        m = t.record_measurement(b_none.id, value=103.0)  # 3% drift
        assert m.drift_severity == DriftSeverity.NONE

        b_minor = _make_benefit(title="Minor drift", baseline_value=100.0, target_value=50.0)
        t.ingest(b_minor)
        m = t.record_measurement(b_minor.id, value=110.0)  # 10% drift
        assert m.drift_severity == DriftSeverity.MINOR

        b_mod = _make_benefit(title="Mod drift", baseline_value=100.0, target_value=50.0)
        t.ingest(b_mod)
        m = t.record_measurement(b_mod.id, value=125.0)  # 25% drift
        assert m.drift_severity == DriftSeverity.MODERATE

        b_sig = _make_benefit(title="Sig drift", baseline_value=100.0, target_value=50.0)
        t.ingest(b_sig)
        m = t.record_measurement(b_sig.id, value=140.0)  # 40% drift
        assert m.drift_severity == DriftSeverity.SIGNIFICANT

        b_crit = _make_benefit(title="Crit drift", baseline_value=100.0, target_value=50.0)
        t.ingest(b_crit)
        m = t.record_measurement(b_crit.id, value=160.0)  # 60% drift
        assert m.drift_severity == DriftSeverity.CRITICAL

    def test_realisation_pct_calculation(
        self, tracker: BenefitsTracker, sample_benefit: Benefit
    ) -> None:
        """realisation_pct: (current-baseline)/(target-baseline)*100.

        Baseline=15, target=5, current=10 => (10-15)/(5-15)*100 = 50.0.
        """
        tracker.ingest(sample_benefit)
        m = tracker.record_measurement(sample_benefit.id, value=10.0)
        assert m.realisation_pct == pytest.approx(50.0)

    def test_trend_with_three_measurements(
        self, tracker: BenefitsTracker
    ) -> None:
        """Trend computed as IMPROVING/DECLINING/STABLE with 3+ values.

        For a benefit where lower is better (baseline=100, target=50),
        decreasing values mean improvement. But the trend logic uses
        simple first-to-last comparison: if last > first -> IMPROVING.
        """
        config = BenefitConfig(min_measurements_for_trend=3)
        b = _make_benefit(baseline_value=10.0, target_value=100.0)
        tracker.ingest(b)

        # Record 3 measurements with increasing values (10 -> 20 -> 30)
        # First measurement: only 1 value total, trend = INSUFFICIENT_DATA
        m1 = tracker.record_measurement(b.id, value=20.0)
        assert m1.trend_direction == TrendDirection.INSUFFICIENT_DATA

        # Second: 2 values total, still insufficient
        m2 = tracker.record_measurement(b.id, value=25.0)
        assert m2.trend_direction == TrendDirection.INSUFFICIENT_DATA

        # Third: 3 values total [20, 25, 30] -> last > first -> IMPROVING
        m3 = tracker.record_measurement(b.id, value=30.0)
        assert m3.trend_direction == TrendDirection.IMPROVING

    def test_zero_baseline_drift(
        self, tracker: BenefitsTracker
    ) -> None:
        """Zero baseline produces 0.0 drift_pct (no division by zero)."""
        b = _make_benefit(baseline_value=0.0, target_value=10.0)
        tracker.ingest(b)
        m = tracker.record_measurement(b.id, value=5.0)
        assert m.drift_pct == 0.0

    def test_record_measurement_missing_benefit_raises(
        self, tracker: BenefitsTracker
    ) -> None:
        """record_measurement raises ValueError for unknown benefit_id."""
        with pytest.raises(ValueError, match="not found"):
            tracker.record_measurement("nonexistent-id", value=42.0)


# ===========================================================================
# 5. TestDependencyNetwork
# ===========================================================================


class TestDependencyNetwork:
    """Dependency DAG node/edge management and cycle detection."""

    def test_add_node_all_types(self, tracker: BenefitsTracker) -> None:
        """All six NodeType values can be persisted and retrieved."""
        for nt in NodeType:
            node = DependencyNode(
                project_id="PROJ-001",
                node_type=nt,
                title=f"Node {nt.value}",
            )
            result = tracker.add_node(node)
            assert result.node_type == nt

        network = tracker.get_network("PROJ-001")
        assert len(network["nodes"]) == 6

    def test_add_edge(self, tracker: BenefitsTracker) -> None:
        """An edge between two nodes is persisted and returned in the network."""
        n1 = DependencyNode(
            project_id="PROJ-001",
            node_type=NodeType.PROJECT_OUTPUT,
            title="Deliverable A",
        )
        n2 = DependencyNode(
            project_id="PROJ-001",
            node_type=NodeType.ENABLER,
            title="Capability B",
        )
        tracker.add_node(n1)
        tracker.add_node(n2)

        edge = DependencyEdge(
            project_id="PROJ-001",
            source_node=n1.id,
            target_node=n2.id,
            edge_type=EdgeType.ENABLES,
        )
        result = tracker.add_edge(edge)
        assert result.edge_type == EdgeType.ENABLES

        network = tracker.get_network("PROJ-001")
        assert len(network["edges"]) == 1
        assert network["edges"][0]["source_node"] == n1.id
        assert network["edges"][0]["target_node"] == n2.id

    def test_get_network_returns_nodes_and_edges(
        self, tracker: BenefitsTracker
    ) -> None:
        """get_network returns dict with 'nodes' and 'edges' keys."""
        network = tracker.get_network("PROJ-001")
        assert "nodes" in network
        assert "edges" in network
        assert isinstance(network["nodes"], list)
        assert isinstance(network["edges"], list)

    def test_cycle_detection_raises(self, tracker: BenefitsTracker) -> None:
        """Adding an edge that creates a cycle raises ValueError."""
        n1 = DependencyNode(
            project_id="PROJ-001",
            node_type=NodeType.ENABLER,
            title="A",
        )
        n2 = DependencyNode(
            project_id="PROJ-001",
            node_type=NodeType.BUSINESS_CHANGE,
            title="B",
        )
        n3 = DependencyNode(
            project_id="PROJ-001",
            node_type=NodeType.INTERMEDIATE_BENEFIT,
            title="C",
        )
        tracker.add_node(n1)
        tracker.add_node(n2)
        tracker.add_node(n3)

        # A -> B -> C
        tracker.add_edge(
            DependencyEdge(
                project_id="PROJ-001",
                source_node=n1.id,
                target_node=n2.id,
            )
        )
        tracker.add_edge(
            DependencyEdge(
                project_id="PROJ-001",
                source_node=n2.id,
                target_node=n3.id,
            )
        )

        # C -> A would create a cycle
        with pytest.raises(ValueError, match="cycle"):
            tracker.add_edge(
                DependencyEdge(
                    project_id="PROJ-001",
                    source_node=n3.id,
                    target_node=n1.id,
                )
            )

    def test_validate_dag_returns_errors(
        self, tracker: BenefitsTracker
    ) -> None:
        """validate_dag returns empty list for a valid acyclic network."""
        n1 = DependencyNode(
            project_id="PROJ-001",
            node_type=NodeType.PROJECT_OUTPUT,
            title="Output",
        )
        n2 = DependencyNode(
            project_id="PROJ-001",
            node_type=NodeType.END_BENEFIT,
            title="End Benefit",
        )
        tracker.add_node(n1)
        tracker.add_node(n2)
        tracker.add_edge(
            DependencyEdge(
                project_id="PROJ-001",
                source_node=n1.id,
                target_node=n2.id,
            )
        )

        errors = tracker.validate_dag("PROJ-001")
        assert errors == []

    def test_benefit_id_linkage(
        self, tracker: BenefitsTracker, sample_benefit: Benefit
    ) -> None:
        """Dependency node can link to a registered benefit via benefit_id."""
        tracker.ingest(sample_benefit)
        node = DependencyNode(
            project_id="PROJ-001",
            node_type=NodeType.END_BENEFIT,
            title="Reduced processing time",
            benefit_id=sample_benefit.id,
        )
        result = tracker.add_node(node)
        assert result.benefit_id == sample_benefit.id

        network = tracker.get_network("PROJ-001")
        assert network["nodes"][0]["benefit_id"] == sample_benefit.id


# ===========================================================================
# 6. TestCascadeImpact
# ===========================================================================


class TestCascadeImpact:
    """BFS cascade impact propagation through the dependency DAG."""

    def _build_chain(self, tracker: BenefitsTracker) -> list[DependencyNode]:
        """Build a chain: Output -> Enabler -> Change -> Benefit (3 edges)."""
        nodes = [
            DependencyNode(
                project_id="PROJ-001",
                node_type=NodeType.PROJECT_OUTPUT,
                title="System deployed",
            ),
            DependencyNode(
                project_id="PROJ-001",
                node_type=NodeType.ENABLER,
                title="Training completed",
            ),
            DependencyNode(
                project_id="PROJ-001",
                node_type=NodeType.BUSINESS_CHANGE,
                title="New process adopted",
            ),
            DependencyNode(
                project_id="PROJ-001",
                node_type=NodeType.END_BENEFIT,
                title="Cost saving",
            ),
        ]
        for n in nodes:
            tracker.add_node(n)

        for i in range(len(nodes) - 1):
            tracker.add_edge(
                DependencyEdge(
                    project_id="PROJ-001",
                    source_node=nodes[i].id,
                    target_node=nodes[i + 1].id,
                )
            )
        return nodes

    def test_bfs_propagation(self, tracker: BenefitsTracker) -> None:
        """Impact from root node propagates to all downstream nodes."""
        nodes = self._build_chain(tracker)
        impacts = tracker.find_cascade_impact(nodes[0].id)

        # Starting node excluded, so 3 downstream nodes
        assert len(impacts) == 3
        impact_ids = {imp["node_id"] for imp in impacts}
        assert nodes[1].id in impact_ids
        assert nodes[2].id in impact_ids
        assert nodes[3].id in impact_ids

    def test_leaf_node_empty_impact(self, tracker: BenefitsTracker) -> None:
        """Leaf node with no outgoing edges returns empty cascade."""
        nodes = self._build_chain(tracker)
        impacts = tracker.find_cascade_impact(nodes[-1].id)
        assert impacts == []

    def test_depth_values(self, tracker: BenefitsTracker) -> None:
        """BFS depth values increase correctly along the chain."""
        nodes = self._build_chain(tracker)
        impacts = tracker.find_cascade_impact(nodes[0].id)

        depth_by_id = {imp["node_id"]: imp["depth"] for imp in impacts}
        assert depth_by_id[nodes[1].id] == 1
        assert depth_by_id[nodes[2].id] == 2
        assert depth_by_id[nodes[3].id] == 3


# ===========================================================================
# 7. TestHealthAnalysis
# ===========================================================================


class TestHealthAnalysis:
    """Portfolio-level health analysis and reporting."""

    def test_overall_health_score(
        self, tracker: BenefitsTracker
    ) -> None:
        """Health score is between 0.0 and 1.0 for a project with benefits."""
        b = _make_benefit(baseline_value=100.0, target_value=50.0)
        tracker.ingest(b)
        tracker.record_measurement(b.id, value=95.0)

        report = tracker.analyse_health("PROJ-001")
        assert 0.0 <= report.overall_health_score <= 1.0
        assert report.total_benefits == 1

    def test_stale_measurement_detection(
        self, store: AssuranceStore
    ) -> None:
        """Benefits not measured within staleness window are flagged stale."""
        config = BenefitConfig(staleness_days=30)
        t = BenefitsTracker(store=store, config=config)

        b = _make_benefit()
        t.ingest(b)
        t.record_measurement(b.id, value=90.0)

        # Manually backdate the measurement in the DB to make it stale
        with store._connect() as conn:
            old_date = (datetime.now(tz=timezone.utc) - timedelta(days=60)).isoformat()
            conn.execute(
                "UPDATE benefit_measurements SET measured_at = ? WHERE benefit_id = ?",
                (old_date, b.id),
            )

        report = t.analyse_health("PROJ-001")
        assert report.stale_count == 1

    def test_at_risk_count(self, store: AssuranceStore) -> None:
        """Benefits with SIGNIFICANT or CRITICAL drift are counted as at risk."""
        config = BenefitConfig(
            minor_threshold_pct=5.0,
            moderate_threshold_pct=15.0,
            significant_threshold_pct=30.0,
        )
        t = BenefitsTracker(store=store, config=config)

        # Create a benefit with huge drift (current_actual_value set via measurement)
        b = _make_benefit(baseline_value=100.0, target_value=50.0)
        t.ingest(b)
        # 60% drift -> CRITICAL
        t.record_measurement(b.id, value=160.0)

        report = t.analyse_health("PROJ-001")
        assert report.at_risk_count >= 1

    def test_empty_project_defaults(self, tracker: BenefitsTracker) -> None:
        """Empty project returns health_score=1.0 and zero counts."""
        report = tracker.analyse_health("EMPTY-PROJECT")
        assert report.overall_health_score == 1.0
        assert report.total_benefits == 0
        assert report.total_disbenefits == 0
        assert report.stale_count == 0
        assert report.at_risk_count == 0
        assert report.aggregate_realisation_pct == 0.0
        assert report.leading_indicator_warnings == []

    def test_leading_indicator_warnings(
        self, tracker: BenefitsTracker
    ) -> None:
        """Declining leading indicator generates a warning message."""
        b = _make_benefit(
            title="User adoption rate",
            baseline_value=10.0,
            target_value=100.0,
            indicator_type=IndicatorType.LEADING,
        )
        tracker.ingest(b)

        # Record 3+ measurements with declining values to get DECLINING trend
        # Values: 50, 40, 30 -- last < first -> DECLINING
        tracker.record_measurement(b.id, value=50.0)
        tracker.record_measurement(b.id, value=40.0)
        tracker.record_measurement(b.id, value=30.0)

        report = tracker.analyse_health("PROJ-001")
        assert len(report.leading_indicator_warnings) >= 1
        assert "User adoption rate" in report.leading_indicator_warnings[0]
        assert "declining" in report.leading_indicator_warnings[0].lower()


# ===========================================================================
# 8. TestForecasting
# ===========================================================================


class TestForecasting:
    """Linear extrapolation forecasting."""

    def test_linear_extrapolation_sufficient_data(
        self, tracker: BenefitsTracker
    ) -> None:
        """With 2+ measurements, linear forecast returns a valid probability."""
        b = _make_benefit(
            baseline_value=100.0,
            target_value=50.0,
            target_date=date(2027, 12, 31),
        )
        tracker.ingest(b)

        # Record two measurements showing improvement (decreasing toward 50)
        tracker.record_measurement(b.id, value=90.0)
        tracker.record_measurement(b.id, value=80.0)

        forecast = tracker.forecast(b.id)
        assert forecast.forecast_method == "linear_extrapolation"
        assert 0.0 <= forecast.probability_of_realisation <= 1.0
        assert forecast.target_value == 50.0
        assert forecast.target_date == date(2027, 12, 31)

    def test_insufficient_data_returns_zero_probability(
        self, tracker: BenefitsTracker
    ) -> None:
        """With fewer than 2 measurements, forecast returns 0 probability."""
        b = _make_benefit(
            baseline_value=100.0,
            target_value=50.0,
            target_date=date(2027, 12, 31),
        )
        tracker.ingest(b)
        # Only one measurement
        tracker.record_measurement(b.id, value=90.0)

        forecast = tracker.forecast(b.id)
        assert forecast.probability_of_realisation == 0.0
        assert forecast.forecast_method == "insufficient_data"

    def test_missing_target_raises(self, tracker: BenefitsTracker) -> None:
        """Benefit with no target_value or target_date raises ValueError."""
        b = _make_benefit(target_value=None, target_date=None)
        tracker.ingest(b)
        with pytest.raises(ValueError, match="no target"):
            tracker.forecast(b.id)

    def test_forecast_nonexistent_benefit_raises(
        self, tracker: BenefitsTracker
    ) -> None:
        """Forecasting a non-existent benefit raises ValueError."""
        with pytest.raises(ValueError, match="not found"):
            tracker.forecast("nonexistent-id")


# ===========================================================================
# 9. TestDriftDetection
# ===========================================================================


class TestDriftDetection:
    """detect_drift analysis across a project's benefits."""

    def test_detect_drift_sorted_by_severity(
        self, store: AssuranceStore
    ) -> None:
        """Results are sorted worst-first by severity weight."""
        config = BenefitConfig(
            minor_threshold_pct=5.0,
            moderate_threshold_pct=15.0,
            significant_threshold_pct=30.0,
        )
        t = BenefitsTracker(store=store, config=config)

        # Low drift benefit
        b_low = _make_benefit(
            title="Low drift", baseline_value=100.0, target_value=50.0
        )
        t.ingest(b_low)
        t.record_measurement(b_low.id, value=102.0)  # 2% -> NONE

        # High drift benefit
        b_high = _make_benefit(
            title="High drift", baseline_value=100.0, target_value=50.0
        )
        t.ingest(b_high)
        t.record_measurement(b_high.id, value=160.0)  # 60% -> CRITICAL

        results = t.detect_drift("PROJ-001")
        assert len(results) == 2
        # First result should be the one with higher severity
        assert results[0].severity.value in ("CRITICAL", "SIGNIFICANT")
        assert results[0].benefit.title == "High drift"

    def test_detect_drift_filtered_results(
        self, tracker: BenefitsTracker
    ) -> None:
        """detect_drift returns results for all benefits in the project."""
        b1 = _make_benefit(
            title="Benefit A", baseline_value=100.0, target_value=50.0
        )
        b2 = _make_benefit(
            title="Benefit B",
            baseline_value=200.0,
            target_value=100.0,
            project_id="PROJ-002",
        )
        tracker.ingest(b1)
        tracker.ingest(b2)
        tracker.record_measurement(b1.id, value=95.0)
        tracker.record_measurement(b2.id, value=190.0)

        # Only PROJ-001 benefits returned
        results = tracker.detect_drift("PROJ-001")
        assert len(results) == 1
        assert results[0].benefit.title == "Benefit A"

        # Only PROJ-002 benefits returned
        results_2 = tracker.detect_drift("PROJ-002")
        assert len(results_2) == 1
        assert results_2[0].benefit.title == "Benefit B"
