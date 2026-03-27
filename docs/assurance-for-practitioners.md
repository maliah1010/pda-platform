# Assurance Quality Tracking — A Guide for Project Managers

This guide explains three capabilities available in the PDA Platform that help
you track assurance quality over time.  No technical background is needed.

---

## What is this for?

Every project goes through regular assurance reviews and gate assessments.
Over time, the same weaknesses can appear in review after review without being
resolved, compliance scores can quietly drift downwards between reporting
cycles, and the evidence artefacts submitted to a gate may not be as current
as they appear.

These three features help you spot all of those problems early:

1. **Artefact Currency Validator** checks whether the evidence documents
   submitted to a gate review are genuinely current — or whether they were
   hastily updated right before the gate without substantive change.

2. **Longitudinal Compliance Tracker** tells you whether your project's data
   compliance is getting better, getting worse, or staying flat — and raises
   an alert if it drops sharply or falls below a safe minimum.

3. **Cross-Cycle Finding Analyzer** captures every action point from a review,
   watches for the same action appearing in multiple consecutive reviews, and
   shows you which actions have been resolved and which are still open.

---

## Artefact Currency Validator

### What it does

When a project submits evidence artefacts — risk registers, benefits profiles,
delivery plans — to a gate review, the platform checks each document's last
modification timestamp against the gate date and a configured currency window.

It detects two distinct problems:

- **Genuinely outdated artefacts**: documents that have not been updated within
  the acceptable staleness window (default: 90 days).
- **Last-minute compliance updates**: documents updated within a very short
  window immediately before the gate date (default: 3 days).  This pattern —
  hastily updating stale documents right before a gate review — does not
  represent genuine evidence currency and should be investigated.

### What you see

For each artefact the platform returns a currency status:

| Status | What it means |
|--------|---------------|
| Current | The artefact has been updated within the acceptable window and was not updated immediately before the gate. |
| Outdated | The artefact has not been updated within the acceptable window.  It may not reflect the current state of the project. |
| Anomalous Update | The artefact was updated within a very short window before the gate date.  This is consistent with last-minute compliance updates and should be reviewed before accepting the evidence. |

### Configurable thresholds

| Setting | Default | Meaning |
|---------|---------|---------|
| Maximum staleness | 90 days | Artefacts not updated within this window are flagged as Outdated. |
| Anomaly window | 3 days | Updates this close to the gate date are flagged as Anomalous. |

### Example prompts

- "Check the currency of the evidence artefacts submitted for PROJ-001 against
  the June gate date."
- "Which artefacts for PROJ-001 were last updated more than 90 days ago?"
- "Were any documents updated within 3 days of the gate for PROJ-001?"

---

## Longitudinal Compliance Tracker

### What it does

Every time your project data is validated against the NISTA Programme and
Project Data Standard, the score is saved.  Over time this builds a history
that the platform uses to answer three questions:

- Is the score going up, staying flat, or going down?
- Has the score dropped sharply between two consecutive validation runs?
- Has the score fallen below an acceptable minimum?

### What you see

When you ask for a compliance trend report, the platform returns:

- **History**: a list of every validation run with its date and score.
- **Trend**: one of three values.

  | Trend | What it means |
  |-------|---------------|
  | Improving | Scores have risen meaningfully over recent runs. |
  | Stagnating | Scores are broadly flat — neither improving nor declining. |
  | Degrading | Scores have fallen meaningfully over recent runs. |

- **Active breaches**: any alert conditions that are currently triggered.

  | Breach | What it means |
  |--------|---------------|
  | Drop breach | The score fell by more than the configured tolerance between the last two runs.  This can signal a data quality problem that needs immediate attention. |
  | Floor breach | The score has fallen below the configured minimum.  This means the project data may not be sufficient for reporting purposes. |

### Configurable thresholds

Your programme office can adjust the alert thresholds to match your
organisation's tolerance for compliance risk:

| Setting | Default | Meaning |
|---------|---------|---------|
| Drop tolerance | 5 points | How large a single-run drop must be before an alert is raised. |
| Floor | 60% | The minimum compliance score before a floor alert is raised. |
| Stagnation window | 3 runs | How many recent runs are examined when computing the trend. |

### Example prompts

- "Show me the NISTA compliance trend for project PROJ-001."
- "Have there been any threshold breaches for PROJ-001 recently?"
- "Is PROJ-001's compliance score improving or degrading over time?"

---

## Cross-Cycle Finding Analyzer

### What it does

When you submit a project review document to the platform, it automatically:

1. Reads every recommended action from the text.
2. Removes any duplicates within the same review.
3. Checks whether any of the new actions match open actions from a previous
   review cycle.
4. Saves all actions to a shared record so they can be tracked over time.

### Review action lifecycle

Every action has a status:

| Status | Meaning |
|--------|---------|
| Open | Newly identified; no action taken yet. |
| In progress | Work is under way to address this action. |
| Closed | The action has been resolved. |
| Recurring | This action has appeared in a previous review and was not yet closed.  Recurring actions are a signal that something is not being addressed. |

### What "recurring" means in practice

If the platform identifies that an action in your Q2 review is essentially the
same as an open action from your Q1 review, the Q2 action is automatically
flagged as recurring.

Recurring actions are a management signal.  They suggest that either the action
has not been taken yet, or that the underlying issue is proving difficult to
resolve.  Your programme or assurance manager should investigate why the action
has not been closed.

### Confidence and human review flags

The platform extracts review actions using an AI model with a self-consistency
check (it runs the extraction several times and looks for agreement).  Each
extraction is given a confidence score.

If the confidence score is below a configured threshold (default: 60%), the
action is flagged for human review.  It is still recorded and included in the
results — it is never automatically discarded.  A flag means "a human should
check this before acting on it", not "this is wrong".

### Example prompts

- "Extract the actions from this review document and track them against our
  open actions for PROJ-001."
- "Show me all open review actions for PROJ-001."
- "Which actions for PROJ-001 are recurring from previous reviews?"

---

## Using these features through Claude

All three features are available as tools in the pm-assure MCP server.  You
can use them by asking Claude directly in a conversation where the server is
connected.

**Artefact Currency Validator:**

- "Check whether the evidence artefacts for PROJ-001 are current for the
  June gate."
- "Flag any documents for PROJ-001 that were updated within 3 days of the
  gate date."

**Longitudinal Compliance Tracker:**

- "Show me the NISTA compliance trend for project PROJ-001."
- "Have there been any threshold breaches for PROJ-001 recently?"

**Cross-Cycle Finding Analyzer:**

- "Extract the recommendations from this review document and track them
  against our open actions for PROJ-001."
- "Show me all open review actions for PROJ-001."
- "Which actions for PROJ-001 are recurring from previous reviews?"

---

## Frequently asked questions

**Do I need to do anything to start tracking compliance scores?**

No.  Score tracking begins automatically the first time your project data is
validated through the platform with the history feature enabled.  Contact your
programme office or technical team if you are unsure whether it is active.

**How many reviews does the platform need before it can show a compliance trend?**

At least two validation runs are needed before a trend can be computed.  With
only one run, the trend is shown as Stagnating until more data is available.

**What counts as an anomalous artefact update?**

An update is flagged as anomalous when it occurs within the configured anomaly
window (default: 3 days) before a gate date.  The platform does not assess
whether the content changed; it flags the timing pattern for human review.
Your assurance manager should compare the current version of the document
against the previous version to determine whether the update represents a
genuine revision.

**Can I mark a review action as closed myself?**

Yes.  Your programme office or platform administrator can update the status of
any action using the review action management tools.

**What happens if the AI misses a recommendation?**

Extraction is run multiple times and the results are compared for consistency.
Low-agreement extractions are flagged for review.  As with any AI-assisted
tool, a human reviewer should check the output before using it for formal
reporting purposes.

**Is review action text stored securely?**

Review action text is stored in a local SQLite database on the server where
the platform is running.  The same data security controls that apply to your
other project management data apply here.  Talk to your information security
team if you have specific requirements.
