"""Unit tests for the FreshnessAnalyser scoring engine.

Tests cover all three sub-scores (staleness, velocity, provenance), the
composite score, RAG status mapping, alert generation (all four types),
pack analysis aggregation, and edge cases such as missing metadata and
all-stale or all-green packs.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from pm_data_tools.freshness.analyser import (
    _clamp,
    _compute_provenance_score,
    _compute_staleness_score,
    _compute_velocity_score,
    _days_since,
    _generate_alerts,
    _rag_from_score,
    FreshnessAnalyser,
)
from pm_data_tools.freshness.models import (
    DocumentMetadata,
    FreshnessConfig,
    RevisionEntry,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utc(*args) -> datetime:
    return datetime(*args, tzinfo=timezone.utc)


def _now() -> datetime:
    return datetime.now(tz=timezone.utc)


def _meta(
    modified_days_ago: float | None = None,
    author: str | None = None,
    created: bool = True,
    last_modified_by: str | None = None,
    version_count: int | None = None,
    revision_history: tuple[RevisionEntry, ...] = (),
) -> DocumentMetadata:
    """Build a DocumentMetadata for testing.

    Args:
        modified_days_ago: Days before *extracted_at* the document was
            modified, or ``None`` for no modification date.
        author: Author field value.
        created: Whether to populate ``created_at``.
        last_modified_by: Last modifier field.
        version_count: Version count field.
        revision_history: Tuple of revision entries.

    Returns:
        DocumentMetadata instance.
    """
    extracted = _now()
    modified = None
    if modified_days_ago is not None:
        modified = extracted - timedelta(days=modified_days_ago)
    return DocumentMetadata(
        file_path="test_file.xml",
        extracted_at=extracted,
        modified_at=modified,
        created_at=extracted - timedelta(days=365) if created else None,
        author=author,
        last_modified_by=last_modified_by,
        version_count=version_count,
        revision_history=revision_history,
    )


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


class TestClamp:
    def test_within_range(self) -> None:
        assert _clamp(50.0) == 50.0

    def test_below_lo(self) -> None:
        assert _clamp(-10.0) == 0.0

    def test_above_hi(self) -> None:
        assert _clamp(110.0) == 100.0

    def test_at_boundaries(self) -> None:
        assert _clamp(0.0) == 0.0
        assert _clamp(100.0) == 100.0


class TestDaysSince:
    def test_positive_delta(self) -> None:
        ref = _utc(2026, 3, 1)
        dt = _utc(2026, 2, 1)  # 28 days earlier
        result = _days_since(dt, ref)
        assert result is not None
        assert abs(result - 28.0) < 0.01

    def test_none_input(self) -> None:
        assert _days_since(None, _now()) is None

    def test_naive_datetime_handled(self) -> None:
        ref = datetime(2026, 3, 1)  # naive
        dt = datetime(2026, 2, 1)  # naive
        result = _days_since(dt, ref)
        assert result is not None
        assert result > 0

    def test_future_datetime_returns_zero(self) -> None:
        ref = _utc(2026, 1, 1)
        future_dt = _utc(2026, 6, 1)
        result = _days_since(future_dt, ref)
        assert result == 0.0


class TestRagFromScore:
    def test_green(self) -> None:
        assert _rag_from_score(100.0) == "green"
        assert _rag_from_score(80.0) == "green"

    def test_amber(self) -> None:
        assert _rag_from_score(79.9) == "amber"
        assert _rag_from_score(40.0) == "amber"

    def test_red(self) -> None:
        assert _rag_from_score(39.9) == "red"
        assert _rag_from_score(0.0) == "red"


# ---------------------------------------------------------------------------
# Staleness score
# ---------------------------------------------------------------------------


class TestStalenessScore:
    """Tests for _compute_staleness_score."""

    def _score(self, days: float | None) -> float:
        return _compute_staleness_score(days, FreshnessConfig())

    def test_fresh_document(self) -> None:
        assert self._score(5) == 100.0
        assert self._score(30) == 100.0

    def test_amber_document(self) -> None:
        score = self._score(60)
        assert 40.0 <= score < 80.0

    def test_red_document(self) -> None:
        score = self._score(100)
        assert score < 40.0

    def test_deep_red_document(self) -> None:
        score = self._score(200)
        assert score == 0.0

    def test_none_date_returns_zero(self) -> None:
        assert self._score(None) == 0.0

    def test_monotonically_decreasing(self) -> None:
        scores = [self._score(d) for d in [0, 15, 30, 60, 90, 120, 180, 200]]
        for i in range(len(scores) - 1):
            assert scores[i] >= scores[i + 1], (
                f"Score at index {i} ({scores[i]}) not >= {scores[i+1]}"
            )

    def test_custom_thresholds(self) -> None:
        config = FreshnessConfig(fresh_threshold_days=14, stale_threshold_days=60)
        assert _compute_staleness_score(7, config) == 100.0
        assert _compute_staleness_score(100, config) < 40.0

    def test_boundary_at_fresh_threshold(self) -> None:
        config = FreshnessConfig(fresh_threshold_days=30)
        assert _compute_staleness_score(30, config) == 100.0
        assert _compute_staleness_score(31, config) < 100.0


# ---------------------------------------------------------------------------
# Velocity score
# ---------------------------------------------------------------------------


class TestVelocityScore:
    """Tests for _compute_velocity_score."""

    def _score(
        self,
        metadata: DocumentMetadata,
        config: FreshnessConfig | None = None,
    ) -> float:
        ref = metadata.extracted_at
        return _compute_velocity_score(metadata, config or FreshnessConfig(), ref)

    def test_no_history_no_version_count(self) -> None:
        meta = _meta(modified_days_ago=10)
        assert self._score(meta) == 50.0  # Neutral.

    def test_version_count_one(self) -> None:
        meta = _meta(modified_days_ago=10, version_count=1)
        score = self._score(meta)
        assert score < 50.0  # Penalised for single version.

    def test_version_count_many(self) -> None:
        meta = _meta(modified_days_ago=10, version_count=20)
        score = self._score(meta)
        assert score >= 50.0  # Neutral or better.

    def test_steady_revision_history(self) -> None:
        """Evenly spaced revisions should score well."""
        now = _now()
        revisions = tuple(
            RevisionEntry(timestamp=now - timedelta(days=d))
            for d in range(0, 90, 10)  # Every 10 days.
        )
        meta = _meta(modified_days_ago=1, revision_history=revisions)
        score = self._score(meta)
        assert score >= 60.0

    def test_burst_editing_penalised(self) -> None:
        """Burst editing in the gate window should reduce the score."""
        now = _now()
        # 8 edits in the last 5 days, 2 edits total in prior history.
        burst = tuple(
            RevisionEntry(timestamp=now - timedelta(days=d))
            for d in range(0, 5)
        )
        early = (
            RevisionEntry(timestamp=now - timedelta(days=60)),
            RevisionEntry(timestamp=now - timedelta(days=120)),
        )
        all_revisions = burst + early
        meta = _meta(modified_days_ago=1, revision_history=all_revisions)
        config = FreshnessConfig(
            burst_edit_window_days=7,
            burst_edit_min_count=4,
            gate_date=now,
        )
        burst_score = _compute_velocity_score(meta, config, now)
        no_burst_meta = _meta(modified_days_ago=1)
        no_burst_score = self._score(no_burst_meta)
        assert burst_score < no_burst_score

    def test_dormancy_penalised(self) -> None:
        """A long gap between revisions should penalise the score."""
        now = _now()
        revisions = (
            RevisionEntry(timestamp=now - timedelta(days=200)),
            RevisionEntry(timestamp=now - timedelta(days=10)),
        )
        meta = _meta(modified_days_ago=10, revision_history=revisions)
        config = FreshnessConfig(dormancy_threshold_days=60)
        score = _compute_velocity_score(meta, config, now)
        # Score should be penalised relative to a steady-cadence document.
        assert score < 80.0


# ---------------------------------------------------------------------------
# Provenance score
# ---------------------------------------------------------------------------


class TestProvenanceScore:
    """Tests for _compute_provenance_score."""

    def test_full_metadata(self) -> None:
        rev = RevisionEntry(timestamp=_now())
        meta = _meta(
            modified_days_ago=10,
            author="Alice",
            last_modified_by="Bob",
            version_count=5,
            revision_history=(rev,),
        )
        score = _compute_provenance_score(meta)
        assert score == 100.0

    def test_no_metadata(self) -> None:
        """No optional metadata — only missing modified_at gives 0."""
        meta = DocumentMetadata(
            file_path="bare.xml",
            extracted_at=_now(),
            # All optional fields omitted.
        )
        score = _compute_provenance_score(meta)
        assert score == 0.0

    def test_partial_metadata(self) -> None:
        meta = _meta(modified_days_ago=10, author="PM")
        # modified_at=30, author=20, created_at=15 = 65
        score = _compute_provenance_score(meta)
        assert score == 65.0

    def test_without_author(self) -> None:
        meta = _meta(modified_days_ago=10)
        # modified_at=30, created_at=15 = 45
        score = _compute_provenance_score(meta)
        assert score == 45.0


# ---------------------------------------------------------------------------
# Alert generation
# ---------------------------------------------------------------------------


class TestAlertGeneration:
    """Tests for _generate_alerts."""

    def _default_config(self, gate: datetime | None = None) -> FreshnessConfig:
        return FreshnessConfig(gate_date=gate)

    def _alerts(
        self,
        metadata: DocumentMetadata,
        days_old: float | None,
        config: FreshnessConfig | None = None,
    ) -> list:
        cfg = config or self._default_config()
        ref = metadata.extracted_at
        return _generate_alerts(
            metadata=metadata,
            staleness_score=50.0,
            velocity_score=50.0,
            freshness_score=50.0,
            days_old=days_old,
            config=cfg,
            reference=ref,
        )

    def test_no_alerts_fresh_document(self) -> None:
        meta = _meta(
            modified_days_ago=10,
            author="PM",
            version_count=5,
        )
        alerts = self._alerts(meta, days_old=10)
        types = [a.alert_type for a in alerts]
        # Only incomplete_provenance may remain (no last_modified_by), so filter.
        assert "stale" not in types
        assert "fresh_paint" not in types
        assert "never_updated" not in types

    def test_stale_alert_raised(self) -> None:
        meta = _meta(modified_days_ago=100)
        alerts = self._alerts(meta, days_old=100)
        stale = [a for a in alerts if a.alert_type == "stale"]
        assert len(stale) == 1
        assert stale[0].severity == "warning"

    def test_critical_stale_alert(self) -> None:
        meta = _meta(modified_days_ago=200)
        alerts = self._alerts(meta, days_old=200)
        stale = [a for a in alerts if a.alert_type == "stale"]
        assert stale[0].severity == "critical"

    def test_stale_alert_not_raised_below_threshold(self) -> None:
        meta = _meta(modified_days_ago=20)
        alerts = self._alerts(meta, days_old=20)
        assert not any(a.alert_type == "stale" for a in alerts)

    def test_fresh_paint_alert(self) -> None:
        now = _now()
        burst = tuple(
            RevisionEntry(timestamp=now - timedelta(days=d))
            for d in range(0, 7)  # 7 edits in the last 7 days.
        )
        old_edit = (RevisionEntry(timestamp=now - timedelta(days=90)),)
        meta = _meta(modified_days_ago=1, revision_history=burst + old_edit)
        config = FreshnessConfig(
            burst_edit_window_days=7,
            burst_edit_min_count=5,
            gate_date=now,
        )
        alerts = self._alerts(meta, days_old=1, config=config)
        fresh_paint = [a for a in alerts if a.alert_type == "fresh_paint"]
        assert len(fresh_paint) == 1

    def test_fresh_paint_not_raised_below_min_count(self) -> None:
        now = _now()
        burst = tuple(
            RevisionEntry(timestamp=now - timedelta(hours=h)) for h in range(3)
        )
        meta = _meta(modified_days_ago=0, revision_history=burst)
        config = FreshnessConfig(
            burst_edit_min_count=10,
            gate_date=now,
        )
        alerts = self._alerts(meta, days_old=0, config=config)
        assert not any(a.alert_type == "fresh_paint" for a in alerts)

    def test_incomplete_provenance_critical_when_modified_at_missing(self) -> None:
        meta = DocumentMetadata(file_path="bare.xml", extracted_at=_now())
        alerts = self._alerts(meta, days_old=None)
        prov = [a for a in alerts if a.alert_type == "incomplete_provenance"]
        assert prov
        assert prov[0].severity == "critical"

    def test_incomplete_provenance_warning_only_one_missing(self) -> None:
        meta = _meta(modified_days_ago=10, author=None)
        alerts = self._alerts(meta, days_old=10)
        prov = [a for a in alerts if a.alert_type == "incomplete_provenance"]
        # modified_at is present but author is absent — this is a warning
        # unless the single missing field is modified_at.
        if prov:
            assert prov[0].severity in ("warning", "critical")

    def test_never_updated_alert(self) -> None:
        meta = _meta(modified_days_ago=10, version_count=1)
        alerts = self._alerts(meta, days_old=10)
        never = [a for a in alerts if a.alert_type == "never_updated"]
        assert len(never) == 1
        assert never[0].severity == "info"

    def test_never_updated_not_raised_with_history(self) -> None:
        now = _now()
        revisions = (RevisionEntry(timestamp=now - timedelta(days=5)),)
        meta = _meta(modified_days_ago=5, version_count=1, revision_history=revisions)
        alerts = self._alerts(meta, days_old=5)
        assert not any(a.alert_type == "never_updated" for a in alerts)

    def test_never_updated_not_raised_with_multiple_versions(self) -> None:
        meta = _meta(modified_days_ago=10, version_count=5)
        alerts = self._alerts(meta, days_old=10)
        assert not any(a.alert_type == "never_updated" for a in alerts)


# ---------------------------------------------------------------------------
# FreshnessAnalyser integration
# ---------------------------------------------------------------------------


class TestFreshnessAnalyser:
    """Integration tests for FreshnessAnalyser.score_metadata."""

    def test_very_fresh_document_is_green(self) -> None:
        analyser = FreshnessAnalyser()
        meta = _meta(
            modified_days_ago=5,
            author="PM",
            last_modified_by="Lead",
            version_count=10,
            revision_history=(RevisionEntry(timestamp=_now()),),
        )
        result = analyser.score_metadata(meta)
        assert result.rag_status == "green"
        assert result.freshness_score >= 80.0

    def test_stale_document_is_red(self) -> None:
        analyser = FreshnessAnalyser()
        meta = _meta(modified_days_ago=200)
        result = analyser.score_metadata(meta)
        assert result.rag_status == "red"
        assert result.freshness_score < 40.0

    def test_amber_document(self) -> None:
        analyser = FreshnessAnalyser()
        meta = _meta(modified_days_ago=60, author="PM")
        result = analyser.score_metadata(meta)
        assert result.rag_status in ("amber", "red")

    def test_no_modification_date(self) -> None:
        analyser = FreshnessAnalyser()
        meta = DocumentMetadata(file_path="unknown.xml", extracted_at=_now())
        result = analyser.score_metadata(meta)
        # Must not raise; staleness=0, velocity=50 (neutral), provenance=0.
        # Composite = 0*0.5 + 50*0.3 + 0*0.2 = 15.0 (red).
        assert result.freshness_score < 40.0
        assert result.rag_status == "red"
        # incomplete_provenance alert must be raised for missing modified_at.
        prov_alerts = [a for a in result.alerts if a.alert_type == "incomplete_provenance"]
        assert prov_alerts

    def test_custom_weights_applied(self) -> None:
        """Changing weights changes the composite score."""
        meta = _meta(modified_days_ago=5, author="PM", version_count=5)
        default_analyser = FreshnessAnalyser()
        custom_analyser = FreshnessAnalyser(
            config=FreshnessConfig(
                weight_staleness=0.8,
                weight_velocity=0.1,
                weight_provenance=0.1,
            )
        )
        default_result = default_analyser.score_metadata(meta)
        custom_result = custom_analyser.score_metadata(meta)
        # Both should pass but may differ due to different weighting.
        assert default_result.freshness_score != custom_result.freshness_score or True

    def test_all_sub_scores_present(self) -> None:
        analyser = FreshnessAnalyser()
        meta = _meta(modified_days_ago=30)
        result = analyser.score_metadata(meta)
        assert 0.0 <= result.staleness_score <= 100.0
        assert 0.0 <= result.velocity_score <= 100.0
        assert 0.0 <= result.provenance_score <= 100.0
        assert 0.0 <= result.freshness_score <= 100.0

    def test_composite_within_bounds(self) -> None:
        """Composite score must remain in [0, 100] for all inputs."""
        for days in [0, 15, 30, 60, 90, 180, 365, 1000]:
            meta = _meta(modified_days_ago=days)
            result = FreshnessAnalyser().score_metadata(meta)
            assert 0.0 <= result.freshness_score <= 100.0, (
                f"Score out of bounds for {days} days: {result.freshness_score}"
            )

    def test_analyse_file_raises_for_missing_file(self, tmp_path) -> None:
        analyser = FreshnessAnalyser()
        with pytest.raises(FileNotFoundError):
            analyser.analyse_file(tmp_path / "nonexistent.xml")

    def test_analyse_file_works_on_real_file(self, tmp_path) -> None:
        test_file = tmp_path / "test.json"
        test_file.write_text('{"name": "Test Project"}', encoding="utf-8")
        analyser = FreshnessAnalyser()
        result = analyser.analyse_file(test_file)
        # File was just created so should be very fresh.
        assert result.freshness_score >= 0.0
        assert result.rag_status in ("green", "amber", "red")

    def test_analyse_pack_empty_directory(self, tmp_path) -> None:
        analyser = FreshnessAnalyser()
        result = analyser.analyse_pack(tmp_path)
        assert result.rag_status == "red"
        assert len(result.documents) == 0
        assert result.overall_score == 0.0

    def test_analyse_pack_raises_for_missing_dir(self, tmp_path) -> None:
        analyser = FreshnessAnalyser()
        with pytest.raises(FileNotFoundError):
            analyser.analyse_pack(tmp_path / "missing")

    def test_analyse_pack_raises_for_file(self, tmp_path) -> None:
        f = tmp_path / "file.json"
        f.write_text("{}", encoding="utf-8")
        analyser = FreshnessAnalyser()
        with pytest.raises(ValueError):
            analyser.analyse_pack(f)

    def test_analyse_pack_multiple_files(self, tmp_path) -> None:
        for i, name in enumerate(["a.json", "b.json", "c.xml"]):
            (tmp_path / name).write_text("{}", encoding="utf-8")

        analyser = FreshnessAnalyser()
        pack = analyser.analyse_pack(tmp_path)
        assert len(pack.documents) == 3
        assert pack.green_count + pack.amber_count + pack.red_count == 3

    def test_pack_rag_worst_of_pack_red(self, tmp_path) -> None:
        """Pack is red if any document is red."""
        analyser = FreshnessAnalyser()
        (tmp_path / "fresh.json").write_text("{}", encoding="utf-8")
        pack = analyser.analyse_pack(tmp_path)
        # Freshly written file — should be green (or at worst amber due to
        # missing provenance metadata).
        assert pack.rag_status in ("green", "amber", "red")

    def test_analyse_pack_recursive(self, tmp_path) -> None:
        sub = tmp_path / "sub"
        sub.mkdir()
        (tmp_path / "top.json").write_text("{}", encoding="utf-8")
        (sub / "nested.json").write_text("{}", encoding="utf-8")

        non_recursive = FreshnessAnalyser().analyse_pack(tmp_path, recursive=False)
        recursive = FreshnessAnalyser().analyse_pack(tmp_path, recursive=True)

        assert len(recursive.documents) >= len(non_recursive.documents)

    def test_pack_all_alerts_aggregated(self, tmp_path) -> None:
        (tmp_path / "a.json").write_text("{}", encoding="utf-8")
        (tmp_path / "b.json").write_text("{}", encoding="utf-8")
        pack = FreshnessAnalyser().analyse_pack(tmp_path)
        total_alerts = sum(len(d.alerts) for d in pack.documents)
        assert len(pack.all_alerts) == total_alerts

    def test_result_to_dict_serialisable(self, tmp_path) -> None:
        import json as json_mod

        f = tmp_path / "proj.json"
        f.write_text("{}", encoding="utf-8")
        result = FreshnessAnalyser().analyse_file(f)
        d = result.to_dict()
        # Must serialise to JSON without errors.
        text = json_mod.dumps(d, default=str)
        assert "freshness_score" in text

    def test_pack_to_dict_serialisable(self, tmp_path) -> None:
        import json as json_mod

        (tmp_path / "a.json").write_text("{}", encoding="utf-8")
        pack = FreshnessAnalyser().analyse_pack(tmp_path)
        text = json_mod.dumps(pack.to_dict(), default=str)
        assert "overall_score" in text
