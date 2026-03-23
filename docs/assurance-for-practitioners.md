# Assurance Quality Tracking — A Guide for Project Managers

This guide explains two new capabilities available in the PDA Platform that
help you track assurance quality over time.  No technical background is needed.

---

## What is this for?

Every project goes through regular assurance reviews.  Over time, the same
weaknesses can appear in review after review without being resolved, and
compliance scores can quietly drift downwards between reporting cycles.

These two features help you spot both problems early:

1. **NISTA Score History** tells you whether your project's data compliance
   is getting better, getting worse, or staying flat — and raises an alert if
   it drops sharply or falls below a safe minimum.

2. **Recommendation Tracker** captures every action point from a review,
   watches for the same action appearing in multiple consecutive reviews, and
   shows you which recommendations have been resolved and which are still open.

---

## NISTA Score History

### What it does

Every time your project data is validated against the NISTA Programme and
Project Data Standard, the score is saved.  Over time this builds a history
that the platform uses to answer three questions:

- Is the score going up, staying flat, or going down?
- Has the score dropped sharply between two consecutive validation runs?
- Has the score fallen below an acceptable minimum?

### What you see

When you ask for a score trend report, the platform returns:

- **History**: a list of every validation run with its date and score.
- **Trend**: one of three values.

  | Trend | What it means |
  |-------|---------------|
  | IMPROVING | Scores have risen meaningfully over recent runs. |
  | STAGNATING | Scores are broadly flat — neither improving nor declining. |
  | DEGRADING | Scores have fallen meaningfully over recent runs. |

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

---

## Recommendation Tracker

### What it does

When you submit a project review document to the platform, it automatically:

1. Reads every recommended action from the text.
2. Removes any duplicates within the same review.
3. Checks whether any of the new recommendations match open recommendations
   from a previous review cycle.
4. Saves all recommendations to a shared record so they can be tracked over
   time.

### Recommendation lifecycle

Every recommendation has a status:

| Status | Meaning |
|--------|---------|
| Open | Newly identified; no action taken yet. |
| In progress | Work is under way to address this recommendation. |
| Closed | The recommendation has been resolved. |
| Recurring | This recommendation has appeared in a previous review and was not yet closed.  Recurring recommendations are a signal that something is not being addressed. |

### What "recurring" means in practice

If the platform identifies that a recommendation in your Q2 review is
essentially the same as an open recommendation from your Q1 review, the Q2
recommendation is automatically flagged as recurring.

Recurring recommendations are a management signal.  They suggest that either
the action has not been taken yet, or that the underlying issue is proving
difficult to resolve.  Your programme or assurance manager should investigate
why the recommendation has not been closed.

### Confidence and human review flags

The platform extracts recommendations using an AI model with a self-consistency
check (it runs the extraction several times and looks for agreement).  Each
extraction is given a confidence score.

If the confidence score is below a configured threshold (default: 60%), the
recommendation is flagged for human review.  It is still recorded and included
in the results — it is never automatically discarded.  A flag means "a human
should check this before acting on it", not "this is wrong".

---

## Using these features through Claude

Both features are available as tools in the pm-assure MCP server.  You can use
them by asking Claude directly in a conversation where the server is connected.

**Example prompts:**

- "Show me the NISTA compliance trend for project PROJ-001."
- "Have there been any threshold breaches for PROJ-001 recently?"
- "Extract the recommendations from this review document and track them against
  our open actions for PROJ-001."
- "Show me all open recommendations for PROJ-001."
- "Which recommendations for PROJ-001 are recurring from previous reviews?"

---

## Frequently asked questions

**Do I need to do anything to start tracking scores?**

No.  Score tracking begins automatically the first time your project data is
validated through the platform with the history feature enabled.  Contact your
programme office or technical team if you are unsure whether it is active.

**How many reviews does the platform need before it can show a trend?**

At least two validation runs are needed before a trend can be computed.  With
only one run, the trend is shown as Stagnating until more data is available.

**Can I mark a recommendation as closed myself?**

Yes.  Your programme office or platform administrator can update the status of
any recommendation using the recommendation management tools.

**What happens if the AI misses a recommendation?**

Extraction is run multiple times and the results are compared for consistency.
Low-agreement extractions are flagged for review.  As with any AI-assisted
tool, a human reviewer should check the output before using it for formal
reporting purposes.

**Is the recommendation text stored securely?**

Recommendation text is stored in a local SQLite database on the server where
the platform is running.  The same data security controls that apply to your
other project management data apply here.  Talk to your information security
team if you have specific requirements.
