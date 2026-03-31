"""Tests for P10 — Project Domain Classifier.

Covers:
- All four complexity domains (CLEAR / COMPLICATED / COMPLEX / CHAOTIC)
- Explicit indicator computation and inversion
- Store-derived signals from P2 / P3 / P6 / P8
- Weight renormalisation (only explicit, only derived, both)
- reclassify_from_store (derived-only path)
- Domain assurance profiles
- Store persistence and classification history
"""

from __future__ import annotations

from pm_data_tools.assurance.classifier import (
    ClassificationInput,
    ClassificationResult,
    ClassifierConfig,
    ComplexityDomain,
    ProjectDomainClassifier,
)
from pm_data_tools.db.store import AssuranceStore
from pm_data_tools.schemas.nista.longitudinal import (
    ConfidenceScoreRecord,
    LongitudinalComplianceTracker,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_classifier(
    store: AssuranceStore | None = None,
    config: ClassifierConfig | None = None,
) -> ProjectDomainClassifier:
    return ProjectDomainClassifier(config=config, store=store)


def clear_input(project_id: str = "PROJ-001") -> ClassificationInput:
    return ClassificationInput(
        project_id=project_id,
        technical_complexity=0.1,
        stakeholder_complexity=0.1,
        requirement_clarity=0.9,  # high = clearer → low contribution
        delivery_track_record=0.9,  # high = better → low contribution
        organisational_change=0.1,
        regulatory_exposure=0.1,
        dependency_count=0.1,
    )


def chaotic_input(project_id: str = "PROJ-001") -> ClassificationInput:
    return ClassificationInput(
        project_id=project_id,
        technical_complexity=0.9,
        stakeholder_complexity=0.9,
        requirement_clarity=0.1,  # low = unclear → high contribution
        delivery_track_record=0.1,  # low = poor → high contribution
        organisational_change=0.9,
        regulatory_exposure=0.9,
        dependency_count=0.9,
    )


# ---------------------------------------------------------------------------
# Domain classification
# ---------------------------------------------------------------------------


def test_classify_clear_domain(store: AssuranceStore) -> None:
    clf = make_classifier(store=store)
    result = clf.classify(clear_input())
    assert result.domain == ComplexityDomain.CLEAR


def test_classify_chaotic_domain(store: AssuranceStore) -> None:
    clf = make_classifier(store=store)
    result = clf.classify(chaotic_input())
    assert result.domain == ComplexityDomain.CHAOTIC


def test_classify_complicated_domain(store: AssuranceStore) -> None:
    clf = make_classifier(store=store)
    inp = ClassificationInput(
        project_id="PROJ-001",
        technical_complexity=0.4,
        stakeholder_complexity=0.4,
        requirement_clarity=0.6,
        delivery_track_record=0.6,
        organisational_change=0.3,
        regulatory_exposure=0.3,
        dependency_count=0.3,
    )
    result = clf.classify(inp)
    assert result.domain == ComplexityDomain.COMPLICATED


def test_classify_complex_domain(store: AssuranceStore) -> None:
    clf = make_classifier(store=store)
    inp = ClassificationInput(
        project_id="PROJ-001",
        technical_complexity=0.7,
        stakeholder_complexity=0.7,
        requirement_clarity=0.3,
        delivery_track_record=0.3,
        organisational_change=0.7,
        regulatory_exposure=0.6,
        dependency_count=0.6,
    )
    result = clf.classify(inp)
    assert result.domain == ComplexityDomain.COMPLEX


def test_classify_returns_classification_result(store: AssuranceStore) -> None:
    clf = make_classifier(store=store)
    result = clf.classify(clear_input())
    assert isinstance(result, ClassificationResult)


def test_result_has_uuid_id(store: AssuranceStore) -> None:
    clf = make_classifier(store=store)
    result = clf.classify(clear_input())
    assert result.id
    assert len(result.id) == 36


# ---------------------------------------------------------------------------
# Indicator inversion
# ---------------------------------------------------------------------------


def test_requirement_clarity_inverted() -> None:
    """High requirement_clarity should reduce complexity contribution."""
    clf = make_classifier()
    high_clarity = ClassificationInput(
        project_id="P", requirement_clarity=0.9
    )
    low_clarity = ClassificationInput(
        project_id="P", requirement_clarity=0.1
    )
    high_result = clf.classify(high_clarity)
    low_result = clf.classify(low_clarity)
    assert high_result.composite_score < low_result.composite_score


def test_delivery_track_record_inverted() -> None:
    """High delivery_track_record should reduce complexity contribution."""
    clf = make_classifier()
    high_track = ClassificationInput(
        project_id="P", delivery_track_record=0.9
    )
    low_track = ClassificationInput(
        project_id="P", delivery_track_record=0.1
    )
    high_result = clf.classify(high_track)
    low_result = clf.classify(low_track)
    assert high_result.composite_score < low_result.composite_score


def test_technical_complexity_positive() -> None:
    """High technical_complexity should increase complexity score."""
    clf = make_classifier()
    high = ClassificationInput(project_id="P", technical_complexity=0.9)
    low = ClassificationInput(project_id="P", technical_complexity=0.1)
    assert clf.classify(high).composite_score > clf.classify(low).composite_score


# ---------------------------------------------------------------------------
# Weight renormalisation
# ---------------------------------------------------------------------------


def test_only_explicit_indicators_uses_full_explicit_score(store: AssuranceStore) -> None:
    """When no derived signals are available, explicit score IS the composite."""
    clf = make_classifier(store=store)
    inp = ClassificationInput(project_id="PROJ-EMPTY", technical_complexity=0.5)
    result = clf.classify(inp)
    assert result.derived_score is None
    assert result.explicit_score is not None
    assert abs(result.composite_score - result.explicit_score) < 1e-9


def test_no_indicators_and_no_store_returns_clear() -> None:
    """No data → composite 0.0 → CLEAR."""
    clf = make_classifier(store=None)
    inp = ClassificationInput(project_id="PROJ-001")
    result = clf.classify(inp)
    assert result.domain == ComplexityDomain.CLEAR
    assert result.composite_score == 0.0


def test_only_derived_score_uses_full_derived(store: AssuranceStore) -> None:
    """When no explicit indicators given, derived_score IS the composite."""
    from pm_data_tools.schemas.nista.longitudinal import (
        ConfidenceScoreRecord,
        LongitudinalComplianceTracker,
    )

    tracker = LongitudinalComplianceTracker(store=store)
    # Add a degrading trend (3 declining scores)
    for i, score in enumerate([80.0, 70.0, 60.0]):
        tracker.record(ConfidenceScoreRecord(
            project_id="PROJ-DERIVED",
            run_id=f"run-{i}",
            score=score,
        ))

    clf = make_classifier(store=store)
    inp = ClassificationInput(project_id="PROJ-DERIVED")  # no explicit indicators
    result = clf.classify(inp)
    assert result.explicit_score is None
    assert result.derived_score is not None
    assert abs(result.composite_score - result.derived_score) < 1e-9


# ---------------------------------------------------------------------------
# Indicators list in result
# ---------------------------------------------------------------------------


def test_indicators_list_populated(store: AssuranceStore) -> None:
    clf = make_classifier(store=store)
    inp = ClassificationInput(
        project_id="PROJ-001",
        technical_complexity=0.5,
        stakeholder_complexity=0.6,
    )
    result = clf.classify(inp)
    assert len(result.indicators) == 2


def test_indicators_list_empty_when_no_explicit(store: AssuranceStore) -> None:
    clf = make_classifier(store=store)
    inp = ClassificationInput(project_id="PROJ-001")
    result = clf.classify(inp)
    assert result.indicators == []


def test_indicator_contribution_correct_for_inverse() -> None:
    clf = make_classifier()
    inp = ClassificationInput(project_id="P", requirement_clarity=0.7)
    _, _indicators, _ = (
        clf._compute_explicit_score(inp)[0],
        clf._compute_explicit_score(inp)[0],
        clf._compute_explicit_score(inp)[1],
    )
    indicator_list, _ = clf._compute_explicit_score(inp)
    rc = next(i for i in indicator_list if i.name == "requirement_clarity")
    assert abs(rc.complexity_contribution - (1.0 - 0.7)) < 1e-9


# ---------------------------------------------------------------------------
# Domain profile
# ---------------------------------------------------------------------------


def test_clear_profile_review_frequency_90_days(store: AssuranceStore) -> None:
    clf = make_classifier(store=store)
    profile = clf.get_profile(ComplexityDomain.CLEAR)
    assert profile.review_frequency_days == 90


def test_chaotic_profile_review_frequency_14_days(store: AssuranceStore) -> None:
    clf = make_classifier(store=store)
    profile = clf.get_profile(ComplexityDomain.CHAOTIC)
    assert profile.review_frequency_days == 14


def test_complicated_profile_review_frequency_60_days(store: AssuranceStore) -> None:
    clf = make_classifier(store=store)
    profile = clf.get_profile(ComplexityDomain.COMPLICATED)
    assert profile.review_frequency_days == 60


def test_complex_profile_review_frequency_42_days(store: AssuranceStore) -> None:
    clf = make_classifier(store=store)
    profile = clf.get_profile(ComplexityDomain.COMPLEX)
    assert profile.review_frequency_days == 42


def test_result_profile_matches_domain(store: AssuranceStore) -> None:
    clf = make_classifier(store=store)
    result = clf.classify(clear_input())
    assert result.profile.domain == result.domain


def test_chaotic_profile_has_workflow_tool(store: AssuranceStore) -> None:
    clf = make_classifier(store=store)
    profile = clf.get_profile(ComplexityDomain.CHAOTIC)
    assert "run_assurance_workflow" in profile.recommended_tools


# ---------------------------------------------------------------------------
# reclassify_from_store
# ---------------------------------------------------------------------------


def test_reclassify_from_store_returns_result(store: AssuranceStore) -> None:
    clf = make_classifier(store=store)
    result = clf.reclassify_from_store("PROJ-001")
    assert isinstance(result, ClassificationResult)


def test_reclassify_from_store_no_explicit_indicators(store: AssuranceStore) -> None:
    clf = make_classifier(store=store)
    result = clf.reclassify_from_store("PROJ-001")
    assert result.indicators == []
    assert result.explicit_score is None


def test_reclassify_from_store_degrading_p2_raises_score(store: AssuranceStore) -> None:
    tracker = LongitudinalComplianceTracker(store=store)
    for i, score in enumerate([85.0, 75.0, 65.0]):
        tracker.record(ConfidenceScoreRecord(
            project_id="PROJ-DEG",
            run_id=f"run-{i}",
            score=score,
        ))

    clf = make_classifier(store=store)
    result_no_p2 = clf.reclassify_from_store("PROJ-NONE")
    result_p2 = clf.reclassify_from_store("PROJ-DEG")
    assert result_p2.composite_score > result_no_p2.composite_score


# ---------------------------------------------------------------------------
# Rationale
# ---------------------------------------------------------------------------


def test_rationale_contains_domain(store: AssuranceStore) -> None:
    clf = make_classifier(store=store)
    result = clf.classify(clear_input())
    assert result.domain.value in result.rationale


def test_rationale_contains_composite_score(store: AssuranceStore) -> None:
    clf = make_classifier(store=store)
    result = clf.classify(clear_input())
    assert str(round(result.composite_score, 2)) in result.rationale


def test_rationale_mentions_no_explicit_when_none(store: AssuranceStore) -> None:
    clf = make_classifier(store=store)
    result = clf.classify(ClassificationInput(project_id="PROJ-001"))
    assert "No explicit indicators" in result.rationale


# ---------------------------------------------------------------------------
# Store persistence and history
# ---------------------------------------------------------------------------


def test_classification_persisted_to_store(store: AssuranceStore) -> None:
    clf = make_classifier(store=store)
    result = clf.classify(clear_input())
    rows = store.get_domain_classifications("PROJ-001")
    assert len(rows) == 1
    assert rows[0]["id"] == result.id
    assert rows[0]["domain"] == result.domain.value


def test_classification_history_accumulates(store: AssuranceStore) -> None:
    clf = make_classifier(store=store)
    clf.classify(clear_input("PROJ-001"))
    clf.classify(chaotic_input("PROJ-001"))
    rows = store.get_domain_classifications("PROJ-001")
    assert len(rows) == 2


def test_get_classification_history_returns_results(store: AssuranceStore) -> None:
    clf = make_classifier(store=store)
    clf.classify(clear_input())
    history = clf.get_classification_history("PROJ-001")
    assert len(history) == 1
    assert isinstance(history[0], ClassificationResult)


def test_classification_history_empty(store: AssuranceStore) -> None:
    clf = make_classifier(store=store)
    assert clf.get_classification_history("PROJ-UNKNOWN") == []


def test_no_store_history_returns_empty() -> None:
    clf = make_classifier(store=None)
    assert clf.get_classification_history("PROJ-001") == []


def test_store_results_false_skips_persistence(store: AssuranceStore) -> None:
    config = ClassifierConfig(store_results=False)
    clf = make_classifier(store=store, config=config)
    clf.classify(clear_input())
    rows = store.get_domain_classifications("PROJ-001")
    assert len(rows) == 0
