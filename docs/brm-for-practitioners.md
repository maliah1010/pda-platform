# Benefits Realisation Management — A Guide for Project Managers

This guide explains the Benefits Realisation Management (BRM) capabilities
available in the PDA Platform. No technical background is needed.

---

## What is this for?

Every major project is approved on the basis of a business case that promises
measurable benefits — cost savings, time reductions, improved services, or
broader social value. Yet in practice, rigorous tracking of whether those
benefits actually materialise is rare. The National Audit Office has
documented billions of pounds in "benefits evaporation" across UK government
programmes, where expected gains disappeared between the approval of the
business case and post-implementation review.

This module gives you structured, persistent tracking of your project's
benefits from identification through to realisation or evaporation. It
replaces spreadsheets and manual quarterly returns with a data-driven system
that computes drift, detects early warnings, and produces portfolio-level
health scores.

---

## The Benefits Register

### What it captures

The register records each benefit with metadata drawn from IPA, HM Treasury
Green Book, MSP, PMI, and APMG Managing Benefits standards:

- **Title and description**: What the benefit is, in language that passes
  the MSP DOAM test (Described, Observable, Attributable, Measurable).
- **Financial classification** (Green Book): Cash-releasing, non-cash-releasing,
  quantifiable, or qualitative.
- **Recipient** (IPA taxonomy): Government, private sector partner, or wider
  UK public.
- **Baseline and target**: Where performance is today and where it needs to be.
- **Measurement KPI**: The specific metric used for tracking (e.g., "average
  processing time in days").
- **Ownership**: Senior Responsible Owner (SRO), Benefits Owner (post-BAU),
  and Business Change Owner.
- **IPA lifecycle stage**: Which stage of the IPA five-stage lifecycle the
  benefit is currently in.

### Status lifecycle

| Status | What it means |
|--------|---------------|
| Identified | Benefit recognised in the business case but not yet baselined or measured. |
| Planned | Baseline measurement taken, target set, measurement plan in place. |
| Realizing | Active tracking in progress — measurements are being recorded. |
| Achieved | Target value has been met or exceeded. The benefit is delivered. |
| Evaporated | The benefit will not be realised. Value has been lost. |
| Cancelled | The benefit has been deliberately removed from scope. |

### Dis-benefits

Dis-benefits — negative consequences of implementing a solution — are tracked
with the same rigour as positive benefits. They use the same fields and appear
in the same register, flagged with a dis-benefit marker. The health report
accounts for them separately.

---

## Measurement Tracking

### How to record measurements

Each time you measure a benefit's KPI, the system records the value along
with when it was measured and where the data came from (manual entry, external
API, or derived calculation).

When you record a measurement, the system automatically computes:

- **Drift from baseline**: How far the current value has moved from the
  original baseline, expressed as a percentage.
- **Realisation percentage**: How much of the target change has been achieved
  (e.g., if the target is to reduce from 15 to 5 days and the current value
  is 10 days, realisation is 50%).
- **Trend direction**: Whether successive measurements show improvement,
  stability, or decline.

### Drift severity levels

| Severity | What it means |
|----------|---------------|
| None | Drift is within 5% of baseline — no concern. |
| Minor | Drift between 5–15% — worth monitoring. |
| Moderate | Drift between 15–30% — approaching tolerance boundary. |
| Significant | Drift between 30–45% — action needed. |
| Critical | Drift above 45% — plan integrity at risk. |

These thresholds are configurable.

---

## The Dependency Network

### What the six node types mean

Benefits do not appear in isolation. They are the product of a causal chain
running from what the project builds through to the strategic goals it serves.
The dependency network maps these relationships:

| Node Type | Plain English | Example |
|-----------|---------------|---------|
| Project Output | What the project physically builds or delivers | "New claims processing system deployed" |
| Enabler | A capability the output creates | "Automated eligibility checking" |
| Business Change | An operational change required to exploit the enabler | "Staff retrained on new system" |
| Intermediate Benefit | A measurable stepping-stone showing change is taking effect | "Claims processed per day increased by 30%" |
| End Benefit | The ultimate measurable value delivered | "Average claim processing reduced from 15 to 5 days" |
| Strategic Objective | The high-level organisational goal | "Improved citizen service experience" |

### How dependencies work

Nodes are connected by directed edges that flow upwards: Project Outputs
enable Business Changes, which contribute to Intermediate Benefits, which
feed End Benefits, which support Strategic Objectives.

If a Project Output is delayed (detected via schedule analysis), the impact
cascades through the network — every downstream benefit's timeline is affected.

### Cascade impact

When you query cascade impact for a node, the system traces all downstream
dependencies and tells you which benefits are affected and how far away
they are in the chain. This is the core predictive capability: schedule
slippage in delivery directly translates to delayed benefit realisation.

---

## Reading the Health Score

The health assessment produces a score between 0.0 and 1.0 for your project's
benefits portfolio:

| Score Range | Interpretation |
|-------------|---------------|
| 0.80–1.00 | Healthy — benefits are on track with low drift |
| 0.60–0.79 | Watch — some benefits showing moderate drift |
| 0.40–0.59 | Concern — multiple benefits at risk |
| 0.20–0.39 | Poor — significant benefits evaporation risk |
| 0.00–0.19 | Critical — majority of benefits at risk of evaporation |

The score is computed by averaging severity-weighted drift across all tracked
benefits. A single critical benefit drags the score down; many well-tracked
benefits pull it up.

The report also tells you:

- **At-risk count**: Benefits with significant or critical drift.
- **Stale count**: Benefits not measured within the staleness window (default
  90 days).
- **Leading indicator warnings**: Benefits flagged as leading indicators that
  are declining — a signal that downstream lagging indicators may fail.

---

## Forecasting

The forecast tool uses linear extrapolation from your measurement time-series
to project the current trajectory forward to the target date. It tells you:

- **Projected value at target date**: Where you'll end up if the current
  trend continues.
- **Probability of realisation**: How likely the target will be achieved
  (0–100%).

### Limitations

- Requires at least 2 measurements to produce a forecast.
- Uses linear regression — it assumes the trend will continue unchanged.
- Does not account for planned interventions or external events.
- More measurements produce more reliable forecasts.

---

## Configurable Thresholds

| Parameter | Default | Description |
|-----------|---------|-------------|
| `staleness_days` | 90 | Days without measurement before flagging as stale |
| `minor_threshold_pct` | 5.0 | Drift percentage below this is NONE |
| `moderate_threshold_pct` | 15.0 | Below this is MINOR |
| `significant_threshold_pct` | 30.0 | Below this is MODERATE, above is SIGNIFICANT |
| `min_measurements_for_trend` | 3 | Minimum measurements to compute trend |
