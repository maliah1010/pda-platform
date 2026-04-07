"""Assurance module: artefact currency, compliance tracking, finding analysis, BRM.

This module provides twelve capabilities for assurance gate reviews:

- **P1** — :class:`ArtefactCurrencyValidator`: detect stale and last-minute
  artefact updates against a gate date.
- **P2** — :class:`~pm_data_tools.schemas.nista.LongitudinalComplianceTracker`:
  persist NISTA compliance scores and detect trends (see ``schemas.nista``).
- **P3** — :class:`FindingAnalyzer`: AI-powered extraction, deduplication, and
  cross-cycle recurrence detection for review actions.
- **P4** — :class:`DivergenceMonitor`: monitor AI confidence divergence across
  extraction samples and review cycles.
- **P5** — :class:`AdaptiveReviewScheduler`: recommend optimal review timing
  based on P1–P4 signals.
- **P6** — :class:`OverrideDecisionLogger`: structured logging and pattern
  analysis of governance override decisions.
- **P7** — :class:`LessonsKnowledgeEngine`: ingest, search, and analyse
  lessons learned from project history.
- **P8** — :class:`AssuranceOverheadOptimiser`: measure and optimise the
  efficiency of assurance activities.
- **P9** — :class:`AssuranceWorkflowEngine`: deterministic multi-step assurance
  workflow orchestrator across P1–P8.
- **P10** — :class:`ProjectDomainClassifier`: classify projects into complexity
  domains using explicit indicators and store-derived signals.
- **P12** — :class:`ARMMScorer`: Agent Readiness Maturity Model — four-dimension,
  28-topic, 251-criterion weakest-link maturity assessment for AI agent deployment.
- **P13** — :class:`BenefitsTracker`: Benefits Realisation Management — IPA/Green
  Book-compliant benefits register, time-series measurement tracking, drift
  detection, dependency network (DAG), cascade impact, and health scoring.

Public API::

    from pm_data_tools.assurance import (
        # P12
        ARMMScorer,
        ARMMAssessment,
        ARMMDimension,
        ARMMTopic,
        ARMMTopicResult,
        ARMMDimensionResult,
        ARMMReport,
        ARMMConfig,
        CriterionResult,
        MaturityLevel,
        # P1
        ArtefactCurrencyValidator,
        CurrencyConfig,
        CurrencyScore,
        CurrencyStatus,
        # P3
        ReviewAction,
        FindingAnalysisResult,
        FindingAnalyzer,
        ReviewActionStatus,
        RecurrenceDetector,
        # P4
        DivergenceMonitor,
        DivergenceConfig,
        DivergenceResult,
        DivergenceSnapshot,
        SignalType,
        # P7
        LessonsKnowledgeEngine,
        LessonRecord,
        LessonCategory,
        LessonSentiment,
        LessonSearchResult,
        LessonSearchResponse,
        LessonPatternSummary,
        # P8
        AssuranceOverheadOptimiser,
        AssuranceActivity,
        ActivityType,
        EfficiencyRating,
        DuplicateCheckResult,
        OverheadAnalysis,
        # P9
        AssuranceWorkflowEngine,
        WorkflowConfig,
        WorkflowResult,
        WorkflowStepResult,
        WorkflowStepStatus,
        WorkflowType,
        ProjectHealth,
        WorkflowRiskSignal,
        # P10
        ProjectDomainClassifier,
        ClassifierConfig,
        ClassificationInput,
        ClassificationResult,
        ComplexityDomain,
        DomainAssuranceProfile,
        DomainIndicator,
    )
"""

from .analyzer import FindingAnalyzer
from .armm import (
    ARMMAssessment,
    ARMMConfig,
    ARMMDimension,
    ARMMDimensionResult,
    ARMMReport,
    ARMMScorer,
    ARMMTopic,
    ARMMTopicResult,
    CriterionResult,
    MaturityLevel,
)
from .assumptions import (
    Assumption,
    AssumptionCategory,
    AssumptionConfig,
    AssumptionHealthReport,
    AssumptionSource,
    AssumptionTracker,
    AssumptionValidation,
    DriftResult,
    DriftSeverity,
)
from .benefits import (
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
from .classifier import (
    ClassificationInput,
    ClassificationResult,
    ClassifierConfig,
    ComplexityDomain,
    DomainAssuranceProfile,
    DomainIndicator,
    ProjectDomainClassifier,
)
from .currency import (
    ArtefactCurrencyValidator,
    CurrencyConfig,
    CurrencyScore,
    CurrencyStatus,
)
from .divergence import (
    DivergenceConfig,
    DivergenceMonitor,
    DivergenceResult,
    DivergenceSignal,
    DivergenceSnapshot,
    SignalType,
)
from .lessons import (
    LessonCategory,
    LessonPatternSummary,
    LessonRecord,
    LessonSearchResponse,
    LessonSearchResult,
    LessonSentiment,
    LessonsKnowledgeEngine,
)
from .models import (
    FindingAnalysisResult,
    # Backward-compatibility aliases
    Recommendation,
    RecommendationExtractionResult,
    RecommendationStatus,
    ReviewAction,
    ReviewActionStatus,
)
from .overhead import (
    ActivityType,
    AssuranceActivity,
    AssuranceOverheadOptimiser,
    DuplicateCheckResult,
    EfficiencyRating,
    OverheadAnalysis,
)
from .overrides import (
    OverrideDecision,
    OverrideDecisionLogger,
    OverrideOutcome,
    OverridePatternSummary,
    OverrideType,
)
from .recurrence import RecurrenceDetector
from .scheduler import (
    AdaptiveReviewScheduler,
    ReviewUrgency,
    SchedulerConfig,
    SchedulerRecommendation,
    SchedulerSignal,
)
from .workflows import (
    AssuranceWorkflowEngine,
    ProjectHealth,
    WorkflowConfig,
    WorkflowResult,
    WorkflowRiskSignal,
    WorkflowStepResult,
    WorkflowStepStatus,
    WorkflowType,
)

# Backward-compatibility alias for FindingAnalyzer
RecommendationExtractor = FindingAnalyzer

__all__ = [
    # P1 — Artefact Currency Validator
    "ArtefactCurrencyValidator",
    "CurrencyConfig",
    "CurrencyScore",
    "CurrencyStatus",
    # P3 — Finding Analyzer
    "ReviewAction",
    "FindingAnalysisResult",
    "FindingAnalyzer",
    "ReviewActionStatus",
    "RecurrenceDetector",
    # P4 — Divergence Monitor
    "DivergenceMonitor",
    "DivergenceConfig",
    "DivergenceResult",
    "DivergenceSignal",
    "DivergenceSnapshot",
    "SignalType",
    # P5 — Adaptive Review Scheduler
    "AdaptiveReviewScheduler",
    "ReviewUrgency",
    "SchedulerConfig",
    "SchedulerRecommendation",
    "SchedulerSignal",
    # P6 — Override Decision Logger
    "OverrideDecision",
    "OverrideDecisionLogger",
    "OverrideOutcome",
    "OverridePatternSummary",
    "OverrideType",
    # P7 — Lessons Learned Knowledge Engine
    "LessonsKnowledgeEngine",
    "LessonRecord",
    "LessonCategory",
    "LessonSentiment",
    "LessonSearchResult",
    "LessonSearchResponse",
    "LessonPatternSummary",
    # P8 — Assurance Overhead Optimiser
    "AssuranceOverheadOptimiser",
    "AssuranceActivity",
    "ActivityType",
    "EfficiencyRating",
    "DuplicateCheckResult",
    "OverheadAnalysis",
    # P9 — Agentic Assurance Workflow Engine
    "AssuranceWorkflowEngine",
    "WorkflowConfig",
    "WorkflowResult",
    "WorkflowRiskSignal",
    "WorkflowStepResult",
    "WorkflowStepStatus",
    "WorkflowType",
    "ProjectHealth",
    # P10 — Project Domain Classifier
    "ProjectDomainClassifier",
    "ClassifierConfig",
    "ClassificationInput",
    "ClassificationResult",
    "ComplexityDomain",
    "DomainAssuranceProfile",
    "DomainIndicator",
    # P11 — Assumption Drift Tracker
    "AssumptionTracker",
    "Assumption",
    "AssumptionCategory",
    "AssumptionConfig",
    "AssumptionSource",
    "AssumptionValidation",
    "DriftSeverity",
    "DriftResult",
    "AssumptionHealthReport",
    # P12 — ARMM (Agent Readiness Maturity Model)
    "ARMMScorer",
    "ARMMAssessment",
    "ARMMConfig",
    "ARMMDimension",
    "ARMMDimensionResult",
    "ARMMReport",
    "ARMMTopic",
    "ARMMTopicResult",
    "CriterionResult",
    "MaturityLevel",
    # P13 — Benefits Realisation Management
    "BenefitsTracker",
    "Benefit",
    "BenefitConfig",
    "BenefitStatus",
    "BenefitMeasurement",
    "BenefitDriftResult",
    "BenefitForecast",
    "BenefitsHealthReport",
    "DependencyNode",
    "DependencyEdge",
    "FinancialType",
    "RecipientType",
    "Explicitness",
    "IndicatorType",
    "MeasurementFrequency",
    "MeasurementSource",
    "IpaLifecycleStage",
    "NodeType",
    "EdgeType",
    "TrendDirection",
    # Deprecated aliases — will be removed in v0.5.0
    "Recommendation",
    "RecommendationExtractionResult",
    "RecommendationExtractor",
    "RecommendationStatus",
]
