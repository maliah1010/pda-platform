"""Project Domain Classifier (P10).

Classifies projects into four complexity domains using seven explicit
indicators provided by the caller and up to four store-derived signals
drawn automatically from P2, P3, P6, and P8.

Four complexity domains:

- ``CLEAR``: Low complexity.  Stable requirements, experienced team, few
  dependencies.  Standard gate cadence.
- ``COMPLICATED``: Moderate complexity.  Specialist input needed but
  cause-and-effect understood.  Increased review frequency.
- ``COMPLEX``: High complexity.  Emergent behaviour, significant
  organisational change, adaptive management required.
- ``CHAOTIC``: Crisis state.  Immediate stabilisation required.  Emergency
  assurance cadence with senior escalation.

Usage::

    from pm_data_tools.assurance.classifier import (
        ProjectDomainClassifier,
        ClassificationInput,
        ComplexityDomain,
    )
    from pm_data_tools.db.store import AssuranceStore

    store = AssuranceStore()
    clf = ProjectDomainClassifier(store=store)
    result = clf.classify(
        ClassificationInput(
            project_id="PROJ-001",
            technical_complexity=0.7,
            stakeholder_complexity=0.6,
            requirement_clarity=0.3,
            organisational_change=0.8,
        )
    )
    # result.domain → ComplexityDomain.COMPLEX
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from enum import Enum

import structlog
from pydantic import BaseModel, Field, field_validator

logger: structlog.stdlib.BoundLogger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ComplexityDomain(Enum):
    """Project complexity domain.

    Attributes:
        CLEAR: Low complexity — best practices apply, repeatable.
        COMPLICATED: Moderate complexity — expert analysis needed.
        COMPLEX: High complexity — emergent, adaptive management required.
        CHAOTIC: Crisis — novel, requires immediate action.
    """

    CLEAR = "CLEAR"
    COMPLICATED = "COMPLICATED"
    COMPLEX = "COMPLEX"
    CHAOTIC = "CHAOTIC"


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


class DomainIndicator(BaseModel):
    """A single complexity indicator contributing to the classification.

    Attributes:
        name: Indicator identifier (e.g. ``"technical_complexity"``).
        raw_value: The value as supplied (0–1).
        complexity_contribution: The value as it contributes to the composite
            score — inverse indicators are flipped (1 - raw_value).
        weight: Relative weight of this indicator within the explicit set.
        description: Human-readable explanation of what this indicator means.
    """

    name: str
    raw_value: float
    complexity_contribution: float
    weight: float = 1.0
    description: str


class ClassificationInput(BaseModel):
    """Explicit indicator inputs for domain classification.

    All indicator fields are optional (``None`` = not provided).  At least
    one explicit indicator OR a store with P2/P3/P6/P8 data is required to
    produce a meaningful classification.

    Indicator semantics:

    - ``technical_complexity``: Novelty and integration complexity (high = more
      complex).
    - ``stakeholder_complexity``: Breadth and diversity of stakeholders (high =
      more complex).
    - ``requirement_clarity``: How well-defined requirements are (high =
      *clearer* — inverted when computing complexity contribution).
    - ``delivery_track_record``: Team's prior delivery success rate (high =
      *better* — inverted when computing complexity contribution).
    - ``organisational_change``: Degree of organisational change required (high
      = more complex).
    - ``regulatory_exposure``: Level of regulatory or compliance risk (high =
      more complex).
    - ``dependency_count``: Normalised count of external dependencies (high =
      more complex).
    """

    project_id: str
    technical_complexity: float | None = None
    stakeholder_complexity: float | None = None
    requirement_clarity: float | None = None
    delivery_track_record: float | None = None
    organisational_change: float | None = None
    regulatory_exposure: float | None = None
    dependency_count: float | None = None
    notes: str | None = None

    @field_validator(
        "technical_complexity",
        "stakeholder_complexity",
        "requirement_clarity",
        "delivery_track_record",
        "organisational_change",
        "regulatory_exposure",
        "dependency_count",
    )
    @classmethod
    def _between_zero_and_one(cls, v: float | None) -> float | None:
        """Validate that indicator values are in [0, 1].

        Args:
            v: The value to validate.

        Returns:
            The validated value, or ``None``.

        Raises:
            ValueError: If value is outside [0, 1].
        """
        if v is not None and not 0.0 <= v <= 1.0:
            raise ValueError("indicator value must be between 0 and 1")
        return v


class ClassifierConfig(BaseModel):
    """Configuration for the domain classifier.

    Attributes:
        explicit_weight: Contribution weight of explicit indicators (0–1).
        derived_weight: Contribution weight of store-derived signals (0–1).
            ``explicit_weight + derived_weight`` need not sum to 1; weights
            are renormalised at classification time based on which data is
            actually available.
        clear_threshold: Composite scores below this → CLEAR.
        complicated_threshold: Composite scores below this → COMPLICATED.
        complex_threshold: Composite scores below this → COMPLEX.
            Scores at or above ``complex_threshold`` → CHAOTIC.
        store_results: Whether to persist each classification result.
    """

    explicit_weight: float = 0.70
    derived_weight: float = 0.30
    clear_threshold: float = 0.25
    complicated_threshold: float = 0.50
    complex_threshold: float = 0.75
    store_results: bool = True


class DomainAssuranceProfile(BaseModel):
    """Domain-specific assurance profile with tailored thresholds.

    Attributes:
        domain: The complexity domain this profile applies to.
        review_frequency_days: Recommended number of days between gate reviews.
        recommended_tools: List of MCP tool names recommended for this domain.
        confidence_threshold: Minimum acceptable AI confidence score (0–1).
        compliance_floor: Minimum acceptable NISTA compliance score (0–100).
        notes: Human-readable guidance for this domain.
    """

    domain: ComplexityDomain
    review_frequency_days: int
    recommended_tools: list[str]
    confidence_threshold: float
    compliance_floor: float
    notes: str


class ClassificationResult(BaseModel):
    """Complete output of a domain classification.

    Attributes:
        id: UUID4 identifier for this classification.
        project_id: The project that was classified.
        domain: The assigned complexity domain.
        composite_score: Final weighted composite score (0–1).
        explicit_score: Composite from explicit indicators only, or ``None``
            if no indicators were provided.
        derived_score: Composite from store-derived signals only, or ``None``
            if no signals were available.
        indicators: List of :class:`DomainIndicator` objects that contributed.
        profile: :class:`DomainAssuranceProfile` for the assigned domain.
        classified_at: UTC timestamp of the classification.
        rationale: Human-readable explanation of the assigned domain.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    project_id: str
    domain: ComplexityDomain
    composite_score: float
    explicit_score: float | None = None
    derived_score: float | None = None
    indicators: list[DomainIndicator]
    profile: DomainAssuranceProfile
    classified_at: datetime
    rationale: str


# ---------------------------------------------------------------------------
# Default domain profiles
# ---------------------------------------------------------------------------

_DEFAULT_PROFILES: dict[ComplexityDomain, DomainAssuranceProfile] = {
    ComplexityDomain.CLEAR: DomainAssuranceProfile(
        domain=ComplexityDomain.CLEAR,
        review_frequency_days=90,
        recommended_tools=[
            "check_artefact_currency",
            "nista_longitudinal_trend",
        ],
        confidence_threshold=0.70,
        compliance_floor=70.0,
        notes=(
            "Low-complexity project.  Standard gate review cadence.  "
            "Light-touch assurance with currency and compliance checks."
        ),
    ),
    ComplexityDomain.COMPLICATED: DomainAssuranceProfile(
        domain=ComplexityDomain.COMPLICATED,
        review_frequency_days=60,
        recommended_tools=[
            "check_artefact_currency",
            "nista_longitudinal_trend",
            "review_action_status",
            "recommend_review_schedule",
        ],
        confidence_threshold=0.75,
        compliance_floor=75.0,
        notes=(
            "Moderate complexity.  Specialist involvement recommended at "
            "each gate.  Adaptive scheduling to detect emerging risk."
        ),
    ),
    ComplexityDomain.COMPLEX: DomainAssuranceProfile(
        domain=ComplexityDomain.COMPLEX,
        review_frequency_days=42,
        recommended_tools=[
            "check_artefact_currency",
            "nista_longitudinal_trend",
            "review_action_status",
            "check_confidence_divergence",
            "recommend_review_schedule",
            "log_override_decision",
        ],
        confidence_threshold=0.80,
        compliance_floor=80.0,
        notes=(
            "High complexity.  Full assurance toolkit required.  "
            "Adaptive scheduling and override logging are mandatory.  "
            "Expect emergent behaviour — increase review frequency at first sign of drift."
        ),
    ),
    ComplexityDomain.CHAOTIC: DomainAssuranceProfile(
        domain=ComplexityDomain.CHAOTIC,
        review_frequency_days=14,
        recommended_tools=[
            "check_artefact_currency",
            "nista_longitudinal_trend",
            "review_action_status",
            "check_confidence_divergence",
            "recommend_review_schedule",
            "log_override_decision",
            "run_assurance_workflow",
        ],
        confidence_threshold=0.85,
        compliance_floor=85.0,
        notes=(
            "Crisis state.  Emergency assurance cadence — fortnightly as a minimum.  "
            "Immediate escalation to SRO and DCA required.  "
            "Full workflow engine recommended at each review."
        ),
    ),
}


# ---------------------------------------------------------------------------
# Classifier
# ---------------------------------------------------------------------------


class ProjectDomainClassifier:
    """Classify projects into complexity domains using indicators and store signals.

    Combines up to seven explicit caller-provided indicators (weighted at 70 %
    by default) with up to four store-derived signals from P2, P3, P6, and P8
    (weighted at 30 % by default).  Weights are renormalised when only one
    category of data is available.

    Example::

        clf = ProjectDomainClassifier(store=store)
        result = clf.classify(
            ClassificationInput(
                project_id="PROJ-001",
                technical_complexity=0.8,
                stakeholder_complexity=0.7,
                requirement_clarity=0.2,
                delivery_track_record=0.4,
                organisational_change=0.9,
                regulatory_exposure=0.6,
                dependency_count=0.5,
            )
        )
        print(result.domain.value)   # "COMPLEX" or "CHAOTIC"
        print(result.profile.review_frequency_days)   # 42 or 14
    """

    def __init__(
        self,
        config: ClassifierConfig | None = None,
        store: object | None = None,
    ) -> None:
        """Initialise the classifier.

        Args:
            config: Classifier configuration.  Defaults to
                :class:`ClassifierConfig` defaults.
            store: :class:`~pm_data_tools.db.store.AssuranceStore` instance.
                Required for store-derived signals (P2, P3, P6, P8).
                When ``None``, only explicit indicators are used.
        """
        self._config = config or ClassifierConfig()
        self._store = store

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def classify(self, inp: ClassificationInput) -> ClassificationResult:
        """Classify a project given explicit indicators and store signals.

        Args:
            inp: :class:`ClassificationInput` with up to 7 explicit indicators.

        Returns:
            A :class:`ClassificationResult` with domain, profile, and rationale.
        """
        # 1. Compute explicit indicator score
        indicators, explicit_score = self._compute_explicit_score(inp)

        # 2. Compute store-derived signals
        derived_score = self._compute_derived_score(inp.project_id)

        # 3. Weighted composite
        composite_score = self._combine(explicit_score, derived_score)

        # 4. Domain classification
        domain = self._score_to_domain(composite_score)

        # 5. Profile and rationale
        profile = _DEFAULT_PROFILES[domain]
        rationale = self._build_rationale(
            domain=domain,
            composite_score=composite_score,
            explicit_score=explicit_score,
            derived_score=derived_score,
            indicators=indicators,
        )

        classified_at = datetime.now(tz=timezone.utc)
        result = ClassificationResult(
            project_id=inp.project_id,
            domain=domain,
            composite_score=composite_score,
            explicit_score=explicit_score,
            derived_score=derived_score,
            indicators=indicators,
            profile=profile,
            classified_at=classified_at,
            rationale=rationale,
        )

        if self._store is not None and self._config.store_results:
            self._persist(result)

        logger.info(
            "project_domain_classified",
            project_id=inp.project_id,
            domain=domain.value,
            composite_score=round(composite_score, 3),
            explicit_score=round(explicit_score, 3) if explicit_score is not None else None,
            derived_score=round(derived_score, 3) if derived_score is not None else None,
        )

        return result

    def reclassify_from_store(self, project_id: str) -> ClassificationResult:
        """Classify using only store-derived signals (no explicit indicators).

        Useful for automated or scheduled reclassification where explicit
        indicator values are not available.

        Args:
            project_id: The project identifier.

        Returns:
            A :class:`ClassificationResult` based solely on store signals.
        """
        inp = ClassificationInput(project_id=project_id)
        return self.classify(inp)

    def get_profile(self, domain: ComplexityDomain) -> DomainAssuranceProfile:
        """Return the assurance profile for a given complexity domain.

        Args:
            domain: The :class:`ComplexityDomain` to look up.

        Returns:
            The :class:`DomainAssuranceProfile` for that domain.
        """
        return _DEFAULT_PROFILES[domain]

    def get_classification_history(
        self, project_id: str
    ) -> list[ClassificationResult]:
        """Retrieve classification history for a project from the store.

        Args:
            project_id: The project identifier.

        Returns:
            List of :class:`ClassificationResult` objects ordered by
            ``classified_at`` ascending.  Returns an empty list when no
            store is configured or no history exists.
        """
        if self._store is None:
            return []

        rows = self._store.get_domain_classifications(project_id)  # type: ignore[union-attr]
        results: list[ClassificationResult] = []
        for row in rows:
            raw = row.get("result_json")
            if raw:
                try:
                    data = json.loads(str(raw))
                    results.append(ClassificationResult(**data))
                except Exception as exc:
                    logger.warning(
                        "classification_result_deserialisation_failed",
                        project_id=project_id,
                        error=str(exc),
                    )
        return results

    # ------------------------------------------------------------------
    # Explicit indicator computation
    # ------------------------------------------------------------------

    # Indicators where high value = MORE complex (used directly)
    _POSITIVE_INDICATORS: tuple[str, ...] = (
        "technical_complexity",
        "stakeholder_complexity",
        "organisational_change",
        "regulatory_exposure",
        "dependency_count",
    )

    # Indicators where high value = LESS complex (inverted: 1 - value)
    _INVERSE_INDICATORS: tuple[str, ...] = (
        "requirement_clarity",
        "delivery_track_record",
    )

    _INDICATOR_DESCRIPTIONS: dict[str, str] = {
        "technical_complexity": "Technical novelty and integration complexity (high = more complex).",
        "stakeholder_complexity": "Breadth and diversity of stakeholders (high = more complex).",
        "requirement_clarity": "How well-defined requirements are (high = clearer, inverted).",
        "delivery_track_record": "Prior delivery success rate of the team (high = better, inverted).",
        "organisational_change": "Degree of organisational change required (high = more complex).",
        "regulatory_exposure": "Level of regulatory or compliance risk (high = more complex).",
        "dependency_count": "Normalised count of external dependencies (high = more complex).",
    }

    def _compute_explicit_score(
        self,
        inp: ClassificationInput,
    ) -> tuple[list[DomainIndicator], float | None]:
        """Compute the explicit indicator composite score.

        Args:
            inp: The :class:`ClassificationInput`.

        Returns:
            A tuple of ``(indicators, explicit_score)``.  ``explicit_score``
            is ``None`` when no indicators were provided.
        """
        indicators: list[DomainIndicator] = []
        contributions: list[float] = []

        all_fields = list(self._POSITIVE_INDICATORS) + list(self._INVERSE_INDICATORS)
        for name in all_fields:
            raw = getattr(inp, name, None)
            if raw is None:
                continue
            is_inverse = name in self._INVERSE_INDICATORS
            contribution = 1.0 - raw if is_inverse else raw
            contributions.append(contribution)
            indicators.append(
                DomainIndicator(
                    name=name,
                    raw_value=raw,
                    complexity_contribution=contribution,
                    weight=1.0,
                    description=self._INDICATOR_DESCRIPTIONS.get(name, ""),
                )
            )

        explicit_score: float | None = (
            sum(contributions) / len(contributions) if contributions else None
        )
        return indicators, explicit_score

    # ------------------------------------------------------------------
    # Store-derived signal computation
    # ------------------------------------------------------------------

    def _derive_p2_signal(self, project_id: str) -> float | None:
        """Derive a complexity signal from P2 compliance trend.

        Args:
            project_id: The project identifier.

        Returns:
            Severity score (0–1) or ``None`` if no data available.
        """
        if self._store is None:
            return None
        try:
            from ..schemas.nista.longitudinal import (
                LongitudinalComplianceTracker,
                TrendDirection,
            )

            tracker = LongitudinalComplianceTracker(store=self._store)
            records = tracker.get_history(project_id)
            if not records:
                return None
            trend = tracker.compute_trend(project_id)
            severity_map: dict[TrendDirection, float] = {
                TrendDirection.IMPROVING: 0.0,
                TrendDirection.STAGNATING: 0.3,
                TrendDirection.DEGRADING: 0.7,
            }
            return severity_map.get(trend, 0.3)
        except Exception as exc:
            logger.warning("classifier_p2_signal_failed", error=str(exc))
            return None

    def _derive_p3_signal(self, project_id: str) -> float | None:
        """Derive a complexity signal from P3 open action rate.

        Args:
            project_id: The project identifier.

        Returns:
            Open-action ratio (0–1) or ``None`` if no data available.
        """
        if self._store is None:
            return None
        try:
            recs = self._store.get_recommendations(project_id)  # type: ignore[union-attr]
            if not recs:
                return None
            total = len(recs)
            open_count = sum(1 for r in recs if r.get("status") == "OPEN")
            return open_count / total
        except Exception as exc:
            logger.warning("classifier_p3_signal_failed", error=str(exc))
            return None

    def _derive_p6_signal(self, project_id: str) -> float | None:
        """Derive a complexity signal from P6 override impact rate.

        Args:
            project_id: The project identifier.

        Returns:
            Override impact rate (0–1) or ``None`` if no overrides recorded.
        """
        if self._store is None:
            return None
        try:
            from .overrides import OverrideDecisionLogger

            log_obj = OverrideDecisionLogger(store=self._store)
            summary = log_obj.analyse_patterns(project_id)
            if summary.total_overrides == 0:
                return None
            return min(summary.impact_rate, 1.0)
        except Exception as exc:
            logger.warning("classifier_p6_signal_failed", error=str(exc))
            return None

    def _derive_p8_signal(self, project_id: str) -> float | None:
        """Derive a complexity signal from P8 assurance efficiency rating.

        Args:
            project_id: The project identifier.

        Returns:
            Efficiency-based severity score (0–1) or ``None`` if no
            activities recorded.
        """
        if self._store is None:
            return None
        try:
            from .overhead import AssuranceOverheadOptimiser, EfficiencyRating

            opt = AssuranceOverheadOptimiser(store=self._store)
            analysis = opt.analyse(project_id)
            if analysis.total_activities == 0:
                return None
            severity_map: dict[EfficiencyRating, float] = {
                EfficiencyRating.OPTIMAL: 0.0,
                EfficiencyRating.UNDER_INVESTED: 0.5,
                EfficiencyRating.OVER_INVESTED: 0.4,
                EfficiencyRating.MISALLOCATED: 0.7,
            }
            return severity_map.get(analysis.efficiency_rating, 0.0)
        except Exception as exc:
            logger.warning("classifier_p8_signal_failed", error=str(exc))
            return None

    def _compute_derived_score(self, project_id: str) -> float | None:
        """Compute the store-derived signal composite score.

        Averages available signals from P2, P3, P6, P8.

        Args:
            project_id: The project identifier.

        Returns:
            Average derived score (0–1) or ``None`` if no signals available.
        """
        raw_signals: list[float | None] = [
            self._derive_p2_signal(project_id),
            self._derive_p3_signal(project_id),
            self._derive_p6_signal(project_id),
            self._derive_p8_signal(project_id),
        ]
        present = [s for s in raw_signals if s is not None]
        return sum(present) / len(present) if present else None

    # ------------------------------------------------------------------
    # Composite and domain mapping
    # ------------------------------------------------------------------

    def _combine(
        self,
        explicit_score: float | None,
        derived_score: float | None,
    ) -> float:
        """Combine explicit and derived scores with weight renormalisation.

        When only one category has data its weight is effectively 1.0.

        Args:
            explicit_score: Composite from explicit indicators, or ``None``.
            derived_score: Composite from store-derived signals, or ``None``.

        Returns:
            Weighted composite score (0–1).  Returns 0.0 when neither
            category has data (no information → assume CLEAR).
        """
        if explicit_score is None and derived_score is None:
            return 0.0

        ew = self._config.explicit_weight
        dw = self._config.derived_weight

        if explicit_score is None:
            return float(derived_score)  # type: ignore[arg-type]
        if derived_score is None:
            return float(explicit_score)

        total_weight = ew + dw
        return (explicit_score * ew + derived_score * dw) / total_weight

    def _score_to_domain(self, score: float) -> ComplexityDomain:
        """Map a composite score to a complexity domain.

        Thresholds (default):

        - score < 0.25 → CLEAR
        - 0.25 ≤ score < 0.50 → COMPLICATED
        - 0.50 ≤ score < 0.75 → COMPLEX
        - score ≥ 0.75 → CHAOTIC

        Args:
            score: Composite complexity score (0–1).

        Returns:
            The corresponding :class:`ComplexityDomain`.
        """
        if score < self._config.clear_threshold:
            return ComplexityDomain.CLEAR
        if score < self._config.complicated_threshold:
            return ComplexityDomain.COMPLICATED
        if score < self._config.complex_threshold:
            return ComplexityDomain.COMPLEX
        return ComplexityDomain.CHAOTIC

    # ------------------------------------------------------------------
    # Rationale
    # ------------------------------------------------------------------

    def _build_rationale(
        self,
        domain: ComplexityDomain,
        composite_score: float,
        explicit_score: float | None,
        derived_score: float | None,
        indicators: list[DomainIndicator],
    ) -> str:
        """Build a human-readable rationale for the classification.

        Args:
            domain: Assigned complexity domain.
            composite_score: Final weighted composite score.
            explicit_score: Explicit-only composite, or ``None``.
            derived_score: Derived-only composite, or ``None``.
            indicators: Explicit indicator objects.

        Returns:
            A rationale string.
        """
        parts: list[str] = [
            f"Classified as {domain.value} (composite score {composite_score:.2f})."
        ]

        if explicit_score is not None:
            top_indicators = sorted(
                indicators,
                key=lambda i: i.complexity_contribution,
                reverse=True,
            )[:3]
            names = ", ".join(i.name for i in top_indicators)
            parts.append(
                f"Explicit indicators score: {explicit_score:.2f} "
                f"({len(indicators)} provided; highest contribution: {names})."
            )
        else:
            parts.append("No explicit indicators provided.")

        if derived_score is not None:
            parts.append(
                f"Store-derived signal score: {derived_score:.2f} "
                f"(from P2/P3/P6/P8 historical data)."
            )
        else:
            parts.append("No store-derived signals available.")

        profile = _DEFAULT_PROFILES[domain]
        parts.append(
            f"Recommended review cadence: every {profile.review_frequency_days} days."
        )

        return "  ".join(parts)

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _persist(self, result: ClassificationResult) -> None:
        """Persist a classification result to the store.

        Args:
            result: The :class:`ClassificationResult` to persist.
        """
        self._store.insert_domain_classification(  # type: ignore[union-attr]
            classification_id=result.id,
            project_id=result.project_id,
            domain=result.domain.value,
            composite_score=result.composite_score,
            classified_at=result.classified_at.isoformat(),
            result_json=json.dumps(result.model_dump(mode="json"), default=str),
        )
        logger.debug(
            "domain_classification_persisted",
            classification_id=result.id,
            project_id=result.project_id,
            domain=result.domain.value,
        )
