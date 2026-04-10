# Gate Readiness Assessment — A Guide for Project Managers

This guide explains the Gate Readiness Assessor, a feature in the PDA
Platform that helps you understand whether a project is ready for an IPA
gate review.  No technical background is needed.

---

## What is gate readiness?

Before a project passes through a formal gate review — such as a Strategic
Outline Case gate, a Full Business Case gate, or a Readiness for Service
gate — someone needs to answer the question: "Is this project actually
ready?"

Traditionally, this judgement is made by assembling evidence documents,
reviewing them manually, and forming a view based on experience.  The Gate
Readiness Assessor automates the data-gathering part of that process.  It
pulls together signals from across the platform's assurance features and
produces a structured, scored assessment of how ready the project is across
eight distinct dimensions.

It does not replace human judgement.  It gives the assurance team and
governance board a consistent, evidence-based starting point for their
discussion.

---

## The eight dimensions

The assessor evaluates readiness across eight dimensions.  Each one draws
on data that has already been collected through other platform features.

### 1. Artefact Readiness

Are the evidence documents for the gate current?  Have the review actions
from previous assurance cycles been closed?

A project with stale risk registers and a long list of open actions from
the last review is not ready to present at a gate.

### 2. Data Quality

Is the project's data compliance trending in the right direction?  Is the
AI extraction producing reliable, consistent results?

Falling NISTA compliance scores or unreliable AI extractions indicate
underlying data problems that should be resolved before a gate.

### 3. Assumption Health

Are the project's key assumptions still valid?  Have they been recently
validated?  Are any showing critical drift from their baseline values?

Assumptions that have not been checked in months, or that have drifted
significantly beyond their tolerance, represent unacknowledged risk.

### 4. Governance Maturity

What is the project's track record with governance override decisions?
What is the organisation's maturity level for deploying AI in assurance?

A pattern of overrides with negative outcomes, or a low maturity score on
the Agent Readiness Maturity Model, suggests the governance environment may
not be ready for the next stage.

### 5. Review Timing

Are the scheduling signals from the platform suggesting that a review is
overdue or that conditions are deteriorating?

If the Adaptive Review Scheduler is recommending an immediate or expedited
review, proceeding through a gate without addressing the underlying signals
first is risky.

### 6. Assurance Efficiency

Is the assurance effort being applied effectively?  Are reviews finding
issues, or are they consuming time without producing findings?

A high proportion of zero-finding reviews may indicate that assurance
effort is being misallocated — reviewing the wrong things, or reviewing
too frequently.

### 7. Operational Learning

Is the project team capturing lessons learned?  Are those lessons
predominantly positive or negative?

A project with no recorded lessons has no institutional memory.  A project
with many negative lessons may have systemic issues that need to be
addressed before proceeding.

### 8. Complexity Alignment

Has the project been classified into a complexity domain?  Is the
assurance approach appropriate for that level of complexity?

A complex or chaotic project that is being managed with a light-touch
assurance approach is more likely to encounter problems at a gate.

---

## Reading the readiness score

When you run a gate readiness assessment, the platform returns an overall
readiness classification along with a composite score.

### Readiness levels

| Level | What it means |
|-------|---------------|
| READY | All dimensions are healthy, there are no blocking issues, and sufficient data is available.  The project can proceed to the gate with confidence. |
| CONDITIONALLY READY | The project is mostly ready, but there are minor gaps or limited data coverage.  The gate can proceed, but the governance board should be aware of the gaps. |
| AT RISK | Significant gaps exist in multiple dimensions.  The project should address the identified issues before proceeding to the gate. |
| NOT READY | Critical blocking issues have been identified, or there are widespread deficiencies.  The project should not proceed to the gate until the blocking issues are resolved. |

### Composite score

The composite score is a number between 0% and 100%.  It is computed by
scoring each of the eight dimensions and then combining them using weights
that are specific to the gate being assessed (see "How gate weighting
works" below).

The score is an indicator, not a pass/fail mark.  A score of 62% at
CONDITIONALLY READY tells you something different from 62% at NOT READY —
the latter means there are blocking issues that override the score.

### Dimensions scored

The assessment also reports how many of the eight dimensions had data
available.  If only three dimensions could be scored, the result is less
reliable than one where all eight were scored.  The platform will cap the
readiness at CONDITIONALLY READY when fewer than four dimensions have data,
regardless of the composite score.

---

## What blocking issues mean

Some problems are severe enough that they override the composite score
entirely.  These are called blocking issues.

A blocking issue is generated when any dimension scores very low — below
20% — indicating a critical problem in that area.  For example:

- Multiple assumptions with critical drift that have not been addressed.
- A very high proportion of review actions still open from previous cycles.
- Governance override decisions that have consistently resulted in negative
  outcomes.

When any blocking issue is present, the overall readiness is automatically
set to NOT READY, regardless of how well other dimensions are scoring.
The rationale is simple: a project that is healthy in seven areas but
critically deficient in one is not ready for a gate.

The assessment lists all blocking issues explicitly so you know exactly
what needs to be resolved.

---

## How gate weighting works

Not all dimensions matter equally at every gate.  The platform adjusts the
weight given to each dimension depending on which gate is being assessed.

### Early gates (Gate 0, Gate 1)

At early gates — Opportunity Framing and Strategic Outline Case — the
project is still being shaped.  The most important questions are:

- Are the assumptions well-founded? (Assumption Health is weighted most
  heavily)
- Is governance set up properly? (Governance Maturity is weighted heavily)
- Is the complexity understood? (Complexity Alignment is weighted
  moderately)

Artefact readiness matters less at this stage because few formal artefacts
exist yet.

### Middle gates (Gate 2, Gate 3)

At Outline Business Case and Full Business Case gates, the emphasis shifts:

- Are the evidence artefacts current and complete? (Artefact Readiness
  increases)
- Is the data quality high enough for decision-making? (Data Quality
  increases)
- Assumptions still matter but are weighted less heavily than at Gate 0.

### Later gates (Gate 4, Gate 5)

At Readiness for Service and Operations Review:

- Is the organisation learning from what has happened? (Operational
  Learning is weighted most heavily at Gate 5)
- Is governance mature? (Governance Maturity is weighted heavily at Gate 4)
- Is assurance effort well-calibrated? (Assurance Efficiency increases)

### Project Assessment Review (PAR)

A PAR can happen at any stage and is not tied to a specific lifecycle
phase.  The platform uses equal weights across all eight dimensions for
PAR assessments.

---

## Comparing assessments over time

One of the most useful features of the gate readiness assessor is the
ability to compare two assessments.  This answers the question: "Have we
improved since the last time we checked?"

A comparison shows:

- **Score change**: whether the composite score went up, down, or stayed
  the same, and by how much.
- **Improved dimensions**: which dimensions got better (by more than 5
  percentage points).
- **Degraded dimensions**: which dimensions got worse (by more than 5
  percentage points).
- **Resolved blockers**: blocking issues that were present in the earlier
  assessment but are no longer present.
- **New blockers**: blocking issues that have appeared since the earlier
  assessment.

This is particularly valuable when a project was assessed as NOT READY or
AT RISK and the team has taken remedial action.  Running a new assessment
and comparing it to the previous one provides evidence that the issues have
been addressed — or highlights where further work is still needed.

### Example prompts

- "Run a gate readiness assessment for PROJ-001 at Gate 3."
- "Show me the gate readiness history for PROJ-001."
- "Compare the latest two gate readiness assessments for PROJ-001."
- "Is PROJ-001 ready for Gate 4?"

---

## How to improve your score before a gate review

If a gate readiness assessment returns AT RISK or NOT READY, here are
practical steps to improve the result before the gate:

### Address blocking issues first

Blocking issues force the readiness to NOT READY regardless of other
scores.  Read the blocking issues list and resolve those before doing
anything else.  Common blockers include:

- **Critical assumption drift**: validate stale assumptions and develop
  mitigation plans for assumptions that have drifted beyond tolerance.
- **Very low action closure rate**: close outstanding review actions from
  previous assurance cycles.
- **Severe governance concerns**: review override decisions that resulted
  in negative outcomes and put corrective measures in place.

### Increase data coverage

If the assessment reports that only a few dimensions had data, run the
relevant assurance features to build baseline data:

- Run a full assurance workflow (P9) to populate P1-P8 data.
- Run the domain classifier (P10) to establish a complexity classification.
- Ingest and validate project assumptions (P11).
- Run an ARMM assessment (P12) for governance maturity.

More data coverage leads to a more reliable assessment and removes the
cap at CONDITIONALLY READY that applies when fewer than four dimensions
are scored.

### Target low-scoring dimensions

The assessment breaks down scores by dimension.  Focus your effort on
the dimensions that scored lowest, especially those with high weight for
the gate you are targeting.  For example, if you are approaching Gate 3
and Artefact Readiness scored 30%, updating your evidence documents and
closing open review actions will have the largest impact on your composite
score.

### Run a comparison

After taking remedial action, run a new assessment and compare it to the
previous one.  This gives you a clear before-and-after view and helps you
demonstrate progress to the governance board.

---

## Frequently asked questions

**Does the gate readiness assessment replace a formal gate review?**

No.  It provides structured, evidence-based input to a gate review.  The
governance board still makes the decision about whether to proceed.

**What if some dimensions have no data?**

The assessment still works.  Dimensions with no data are excluded from the
composite score and the remaining dimensions are re-weighted.  However, if
fewer than four dimensions have data, the readiness is capped at
CONDITIONALLY READY to reflect the limited evidence base.

**Can I change the gate weights?**

The gate weights are built into the platform to reflect IPA best practice
for each lifecycle stage.  They cannot be changed through configuration.
The readiness thresholds (what score counts as READY vs AT RISK) can be
adjusted through the `GateReadinessConfig` — speak to your platform
administrator.

**How often should I run a gate readiness assessment?**

Run an assessment when you are preparing for a gate review and want to
understand your readiness posture.  Run it again after taking remedial
action to verify improvement.  There is no cost to running it frequently —
each assessment is saved to history and can be compared to previous ones.

**What is the relationship between gate readiness and the assurance
workflow?**

The assurance workflow (P9) runs individual assurance checks (P1-P8) and
produces per-check results.  The gate readiness assessor (P14) reads the
outputs of all modules (P1-P12) and synthesises them into a single
gate-specific readiness score.  Running a full assurance workflow before
a gate readiness assessment ensures that the assessor has the most current
data to work with.

**Does the assessor contact any external systems?**

No.  It reads only from the local platform database.  It does not call
any APIs, send any data externally, or trigger any notifications.
