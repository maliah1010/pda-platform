# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.0] - 2026-03-27

### Added
- **P1 — Artefact Currency Validator** (planned v0.4.0): `ArtefactCurrencyValidator`,
  `CurrencyConfig`, `CurrencyScore` — detects genuinely stale artefacts and
  last-minute compliance updates ahead of gate reviews. Status flags:
  `CURRENT / OUTDATED / ANOMALOUS_UPDATE`. Documented in `docs/assurance.md`.
- **P2 — Longitudinal Compliance Tracker**: `LongitudinalComplianceTracker`,
  `ComplianceThresholdConfig`, `TrendDirection`, `ThresholdBreach` — persists NISTA
  compliance scores over time, computes trend direction (IMPROVING / STAGNATING /
  DEGRADING), and detects floor and drop breaches. Module: `schemas.nista.longitudinal`.
- **P3 — Cross-Cycle Finding Analyzer**: `FindingAnalyzer`, `ReviewAction`,
  `ReviewActionStatus`, `FindingAnalysisResult` — extracts review actions from project
  review text, deduplicates within a cycle, detects cross-cycle recurrences using
  sentence-transformer embeddings, and persists the full lifecycle. Module:
  `assurance.analyzer`.
- `AssuranceStore` SQLite persistence layer (shared by P2 and P3).
- MCP tools: `nista_longitudinal_trend`, `track_review_actions`, `review_action_status`
  (served by `pm-assure` server in `pm-mcp-servers`).

### Changed
- Renamed `NISTAScoreHistory` → `LongitudinalComplianceTracker` (deprecated alias
  retained until v0.5.0).
- Renamed `NISTAThresholdConfig` → `ComplianceThresholdConfig` (deprecated alias
  retained until v0.5.0).
- Renamed `RecommendationExtractor` → `FindingAnalyzer` (deprecated alias retained).
- Renamed `Recommendation` → `ReviewAction` (deprecated alias retained).
- Renamed `RecommendationStatus` → `ReviewActionStatus` (deprecated alias retained).
- Renamed `RecommendationExtractionResult` → `FindingAnalysisResult` (deprecated
  alias retained).
- `NISTAValidator.validate()` `history` parameter now accepts `LongitudinalComplianceTracker`.

### Deprecated
- `schemas.nista.history` module (use `schemas.nista.longitudinal`).
- `assurance.extractor` module (use `assurance.analyzer`).
- All old class names listed under Changed above — will be removed in v0.5.0.

## [0.1.0] - 2025-01-01

### Added
- Project foundation and structure
- Build configuration (pyproject.toml)
- CI/CD pipeline (GitHub Actions)
- Documentation framework
