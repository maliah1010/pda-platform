# Validation and NISTA Submission — A Guide for Project Managers

This guide explains two capabilities available in the PDA Platform that together
cover the complete pipeline from data quality checking through to quarterly
submission to the NISTA Programme and Project Data Standard registry.  No
technical background is needed.

---

## What is this for?

Government projects on the Government Major Projects Portfolio (GMPP) have two
recurring obligations: they must maintain accurate, standards-compliant project
data at all times, and they must submit a structured quarterly return to the
Infrastructure and Projects Authority (IPA) via the NISTA system.

These two obligations are closely related.  A quarterly return built on
inaccurate or incomplete project data will either fail submission validation or,
worse, be accepted but give the IPA a misleading picture of the project.

The PDA Platform provides two modules to address this:

- **pm-validate** gives you four tools to check your project data before you
  rely on it.  It catches structural problems, scheduling logic errors, NISTA
  compliance gaps, and any custom rules your organisation requires.
- **pm-nista** gives you five tools to generate, review, and submit your GMPP
  quarterly return, including AI-assisted narrative drafting.

Both modules are available through Claude in a conversation where the relevant
MCP servers are connected.

---

## Why validate before analysis — and before submission

Project data quality is a prerequisite for meaningful results.  If a project
schedule contains orphan tasks (tasks with no parent in the hierarchy), circular
dependencies, or resource references pointing to staff who do not exist in the
system, then any analysis built on that data — float calculations, resource
utilisation, critical path — is unreliable.

Similarly, a GMPP quarterly return submitted to NISTA with missing required
fields, invalid formats, or a DCA rating outside the allowed list will be
rejected outright, or will trigger a follow-up query from the IPA that delays
your reporting cycle.

Running the validation tools described in Part 1 before generating a quarterly
return (Part 2) significantly reduces the risk of submission failure and
ensures that the narratives the platform generates are based on accurate
underlying data.

The recommended sequence is:

1. Run structural validation to confirm data integrity.
2. Run semantic validation to check business logic and scheduling coherence.
3. Run NISTA compliance validation to check fields and formats.
4. Run any custom organisational rules.
5. Resolve failures, then generate and submit the quarterly return.

---

## Part 1: Validation

### validate_structure — Data Integrity Checks

#### What it does

`validate_structure` performs a series of technical checks on the project file
to confirm that the data is internally consistent and well-formed.  It does not
assess whether the project is on track or well-planned — it checks whether the
data itself is structurally sound.

The checks it runs are:

| Check | What it looks for |
|-------|------------------|
| Orphan tasks | Tasks that have no parent in the work breakdown structure |
| Circular dependencies | Task A depends on Task B which depends on Task A (or any longer cycle) |
| Invalid resource references | Tasks assigned to resources that do not exist in the project resource list |
| Duplicate task IDs | Two or more tasks sharing the same identifier |
| Hierarchy integrity | The parent-child task structure is consistent with no gaps or mismatches |
| Date consistency | Tasks where the finish date is before the start date |
| Assignment validity | Task assignments that reference roles, costs, or units outside valid ranges |

Each check returns one of two results: pass or fail.  Failures include a list of
the affected tasks or records so you know exactly what needs fixing.

#### When to use it

Run `validate_structure` any time you receive a project file from a new source,
after a significant bulk update, or before generating any analysis or report.
It is the first and fastest check — most structural problems can be resolved
quickly once they are identified.

#### Example prompts

- "Run a structural validation on the project file for PROJ-001."
- "Check PROJ-001 for orphan tasks and circular dependencies."
- "Are there any duplicate task IDs in the project file for PROJ-001?"
- "Validate the date consistency for all tasks in PROJ-001."

#### What the output means

The tool returns a pass/fail result for each check, with a count of failures and
a list of the affected records.  A project with any structural failures should
be corrected before proceeding to semantic validation or report generation.  A
project with all checks passing is structurally sound and ready for the next
stage.

---

### validate_semantic — Business Rules and Scheduling Logic

#### What it does

Where `validate_structure` checks that the data is well-formed, `validate_semantic`
checks that it makes sense.  It applies business rules and scheduling logic to
identify problems that are structurally valid but analytically wrong.

The checks it runs are:

| Check | What it looks for |
|-------|------------------|
| Negative float | Tasks where late finish is earlier than early finish, indicating a scheduling logic error |
| Resource overallocation | Resources assigned to more work than their availability allows within a given period |
| Constraint violations | Hard-constrained tasks whose dates conflict with the logic driving the rest of the schedule |
| Cost inconsistencies | Cost data that does not reconcile across summary and detail levels |
| Baseline variance breaches | Tasks or costs that have deviated from baseline beyond a configured tolerance |
| Milestone date logic | Milestones whose dates are inconsistent with the dependencies feeding them |

#### Custom thresholds

Your programme office can configure the thresholds that determine when a check
triggers a failure rather than a warning.  For example, the acceptable baseline
variance before a flag is raised can be tightened (for high-scrutiny projects)
or relaxed (for projects in early planning where baselines are still being set).
Contact your platform administrator if you need thresholds adjusted.

#### When to use it

Run `validate_semantic` after `validate_structure` has passed.  It is particularly
important to run it before presenting schedule data to a senior governance board
or submitting a return, because negative float and resource overallocation are
the errors most likely to invalidate conclusions drawn from the schedule.

#### Example prompts

- "Run a semantic validation on PROJ-001."
- "Check PROJ-001 for resource overallocation."
- "Are there any negative float tasks in the PROJ-001 schedule?"
- "Has any cost data in PROJ-001 deviated significantly from baseline?"

#### What the output means

Each check returns pass, warning, or fail.  A warning means the issue is present
but within configured tolerances — it should be noted but does not block
progress.  A fail means the issue exceeds tolerances and should be investigated
before the project data is used for reporting.  The output includes the specific
tasks or resources implicated in each failure.

---

### validate_nista — NISTA Compliance Check

#### What it does

`validate_nista` checks your project data against the NISTA Programme and
Project Data Standard — the formal specification that governs what fields are
required in a GMPP quarterly return, what values are permitted, and how data
must be formatted.

It validates:

| Area | What is checked |
|------|----------------|
| Required fields | Project name, IPA code, Senior Responsible Owner name and contact details, Departmental Cost Authority rating, cost data |
| Field formats | Dates in the correct format, numeric fields containing numbers, text fields within permitted length limits |
| DCA values | Delivery Confidence Assessment values drawn only from the IPA's permitted list |

The permitted DCA values are: Highly Likely, Likely, Amber/Green, Amber/Red,
Unlikely, and Highly Unlikely.  Any value outside this list will cause a
NISTA submission failure.

#### Strictness levels

The tool supports three strictness levels:

| Level | Behaviour |
|-------|-----------|
| Lenient | Reports issues as warnings only.  Useful for an early-stage project that is not yet close to submission. |
| Standard | The recommended setting for most projects.  Reports missing required fields and format errors as failures; other issues as warnings. |
| Strict | All rules are enforced.  Failures are raised for any deviation from the standard, including fields that are technically optional but expected by the IPA. |

Use standard for normal working practice.  Move to strict in the weeks
immediately before a quarterly submission deadline.

#### When to use it

Run `validate_nista` once structural and semantic validation have passed.  It is
also worth running it at the start of a quarter to identify gaps while there is
still time to collect missing information, rather than discovering them the week
before a deadline.

#### Example prompts

- "Run a NISTA compliance check on PROJ-001 at standard strictness."
- "Check whether PROJ-001 has all required fields for a GMPP return."
- "Validate PROJ-001 against the NISTA standard at strict level."
- "What fields are missing from PROJ-001's NISTA data?"

#### What the output means

The tool returns a compliance score (expressed as a percentage) and a list of
missing or invalid fields.  A score of 100% at standard strictness means the
project data is ready for submission from a field-completeness perspective.
Any score below 100% will include a list of the specific fields to address.

---

### validate_custom — Organisation-Specific Rules

#### What it does

`validate_custom` allows your organisation to apply its own validation rules on
top of the three standard checks above.  These rules are configured by your
programme office or platform administrator and reflect your internal governance
standards.

Common examples of custom rules include:

- Every task must have an assignee before the project moves to the delivery phase.
- No task may exceed 20 working days in duration without at least one intermediate
  milestone.
- Every risk record must have a named mitigating action and a mitigation owner.
- All costs over a defined threshold must be linked to a specific approved budget line.

Custom rules can be written to apply universally (to all projects) or selectively
(only to projects of a certain type, phase, or directorate).

#### When to use it

Run `validate_custom` after the three standard validations, as the final check
before proceeding to report generation.  If your organisation has not yet
configured any custom rules, the tool will report that no rules are defined.
Talk to your programme office if you believe custom rules would be useful.

#### Example prompts

- "Run custom validation rules on PROJ-001."
- "Check PROJ-001 against our internal governance rules."
- "Which tasks in PROJ-001 are missing an assignee?"
- "Are there any risks in PROJ-001 without a mitigating action?"

#### What the output means

The tool returns a pass or fail for each configured rule, with the list of
records that triggered each failure.  Custom validation failures do not
necessarily block NISTA submission — they reflect your organisation's own
standards, not the IPA's.  However, persistent custom validation failures
are a signal that project data governance needs attention.

---

## Part 2: NISTA Reporting

### What GMPP reporting involves

The Government Major Projects Portfolio (GMPP) is the IPA's register of the
government's largest and most complex projects.  Projects on the GMPP are
required to submit a quarterly return covering their Delivery Confidence
Assessment, cost performance, schedule performance, benefits realisation, and
key risks.

Returns are submitted through the NISTA system — the IPA's digital reporting
platform — and are reviewed by IPA analysts who use them to track portfolio
health and advise ministers.

#### The quarterly cycle

There are four submission windows each financial year:

| Quarter | Period covered | Approximate submission deadline |
|---------|---------------|-------------------------------|
| Q1 | April to June | Late July |
| Q2 | July to September | Late October |
| Q3 | October to December | Late January |
| Q4 | January to March | Late April |

Exact deadlines are communicated by the IPA each year.  Your programme office
will normally set an internal deadline several weeks before the IPA deadline to
allow time for review and approval.

#### Who needs to submit

Submission is required for all projects formally registered on the GMPP.
If you are unsure whether your project is on the GMPP, check with your
departmental NISTA lead or your programme office.

---

### generate_gmpp_report — Generate a Quarterly Return

#### What it does

`generate_gmpp_report` reads your project file and generates a complete GMPP
quarterly return in the structured format required by NISTA.  It pulls together
all the required data fields and, if requested, uses an AI model to draft
narrative text for the sections that require it.

To generate a report you must specify:

- The quarter (Q1, Q2, Q3, or Q4).
- The financial year (for example, 2025-26).

Optionally, you can request AI narrative generation.  This requires an
`ANTHROPIC_API_KEY` environment variable to be set on the server.  If the key
is not configured, the report is generated with blank narrative fields that
you can complete manually.

The output is a complete report JSON file that is ready for pre-submission
validation and, once approved, submission to NISTA.

#### When to use it

Use `generate_gmpp_report` once all four validation checks have passed and any
failures have been resolved.  Generating the report from clean, validated data
reduces the risk of pre-submission validation failures.

#### Example prompts

- "Generate a GMPP Q2 2025-26 return for PROJ-001."
- "Create the quarterly report for PROJ-001 for Q3 2025-26, including AI narratives."
- "Produce a Q1 2026-27 GMPP return for PROJ-001 without AI narratives."

#### What the output means

The tool writes a report JSON file and confirms its location.  This file is not
yet submitted — it is a draft that should be reviewed and, if required,
validated using `validate_gmpp_report` before submission.

---

### generate_narrative — Draft a Single Narrative Section

#### What it does

`generate_narrative` uses an AI model to write a single narrative for one of
the five narrative sections in a GMPP quarterly return:

| Section | What the narrative covers |
|---------|--------------------------|
| DCA | The overall delivery confidence assessment and the reasoning behind it |
| Cost | Cost performance against baseline, including any variances and their causes |
| Schedule | Schedule performance against baseline, key milestones, and any slippage |
| Benefits | Progress against the benefits profile and any changes to expected outcomes |
| Risk | The key risks currently facing the project and the mitigations in place |

The AI uses a multi-sample consensus approach: it generates the narrative
several times and compares the outputs for agreement before returning a final
draft.  Each narrative includes a confidence score.

#### Confidence scoring

| Confidence | What it means |
|------------|--------------|
| High | The samples were in strong agreement.  The draft is likely to be a sound starting point. |
| Medium | The samples agreed on most points but diverged on some.  Review the draft carefully. |
| Low | The samples disagreed significantly.  The draft should be treated as indicative only and rewritten by a human reviewer. |

AI-generated narratives should always be reviewed and approved by a qualified
human before submission.  The confidence score is a guide to how much review
effort is likely to be needed, not a statement of accuracy.

#### When to use it

Use `generate_narrative` when you want to draft a single section separately —
for example, to review the cost narrative before the full report is generated,
or to regenerate a narrative for a section that has been updated.  If you want
all narratives generated at once, use `generate_gmpp_report` with the AI
narratives option.

#### Example prompts

- "Draft a DCA narrative for PROJ-001 for Q2 2025-26."
- "Generate a risk narrative for PROJ-001."
- "Write a cost narrative for the Q3 return for PROJ-001."
- "What confidence score did the AI assign to the benefits narrative for PROJ-001?"

---

### validate_gmpp_report — Pre-Submission Validation

#### What it does

`validate_gmpp_report` checks a generated report JSON file against the full
NISTA specification before you submit it.  It is a final safety check that
catches errors introduced during report generation that the earlier data
validation checks would not have detected — for example, a required field that
is present in the project data but was not correctly mapped into the report
format.

It returns:

- A compliance score for the report.
- A list of missing or invalid fields, with the specific location in the report
  structure where each problem occurs.

#### When to use it

Always run `validate_gmpp_report` on the report JSON before submitting to
NISTA.  Even if all four data validation checks passed cleanly, it is good
practice to validate the generated output.  This is particularly important the
first time a new project submits a return, as mapping issues are most likely
to appear then.

#### Example prompts

- "Validate the GMPP report for PROJ-001 Q2 2025-26 before submission."
- "Check the quarterly return report file for PROJ-001 against the NISTA spec."
- "Are there any missing or invalid fields in the Q3 report for PROJ-001?"

#### What the output means

A compliance score of 100% means the report file is structurally complete and
ready for submission.  Any score below 100% includes a list of fields to
correct.  Re-run `generate_gmpp_report` or edit the report file as directed,
then re-validate before proceeding to submission.

---

### fetch_nista_metadata — Retrieve Project Registration Details

#### What it does

`fetch_nista_metadata` pulls the current registration record for a project
from the NISTA master registry.  This includes:

- The project code assigned by the IPA.
- The sponsoring department.
- The current Senior Responsible Owner name and contact email.
- Baseline dates as registered with the IPA.

This is useful for confirming that the details in your project file match the
IPA's records before generating a return.  Discrepancies between your SRO
details and the registered SRO, or between your baseline dates and the
registered baselines, should be resolved with your departmental NISTA lead
before submission.

#### When to use it

Use `fetch_nista_metadata` at the start of a quarterly reporting cycle, and
particularly if there has been any change to the SRO or to the project's
registered baseline since the last submission.

#### Example prompts

- "Fetch the NISTA registration details for PROJ-001."
- "What SRO details does NISTA have on record for PROJ-001?"
- "Check the NISTA baseline dates for PROJ-001."

---

### submit_to_nista — Submit the Quarterly Return

#### What it does

`submit_to_nista` transmits a validated report JSON file to the NISTA API.
On successful submission it returns:

- A submission ID that serves as proof of submission.
- Any validation warnings raised by the NISTA system during ingestion.

#### Environments

The tool operates in two environments:

| Environment | Purpose |
|-------------|---------|
| Sandbox | Testing environment.  Submissions go to a test instance of NISTA and do not form part of your official GMPP record.  Use this when familiarising yourself with the process or testing a new project's first return. |
| Production | The live NISTA system.  Submissions are received by the IPA and form part of your official quarterly record. |

Always test in sandbox first if you are submitting for the first time or
if there has been a significant change to your project data structure.

#### Credentials

Submission requires NISTA API credentials.  These are set as environment
variables on the server by your IT team.  You do not need to handle credentials
directly — if they are configured correctly, the tool will use them
automatically.  See the note on credentials at the end of this guide.

#### When to use it

Submit only after `validate_gmpp_report` has returned a 100% compliance score
(or after any remaining issues have been reviewed and accepted by your
departmental NISTA lead).  Keep a record of the submission ID returned by the
tool for your project audit trail.

#### Example prompts

- "Submit the Q2 2025-26 return for PROJ-001 to NISTA production."
- "Submit the PROJ-001 quarterly report to the NISTA sandbox for testing."
- "What was the submission ID for the last NISTA submission for PROJ-001?"

---

## End-to-end quarterly return workflow

The following steps cover the complete process from project file to accepted
NISTA submission.  This is the recommended sequence.  Steps 1 to 4 can be
run in a single conversation session.

**Step 1 — Fetch registration details**

Start by confirming that your project's NISTA registration is up to date.

Prompt: "Fetch the NISTA metadata for PROJ-001."

Check that the SRO name and email match your current SRO, and that the baseline
dates match your project's registered position.  If there are discrepancies,
resolve them with your departmental NISTA lead before continuing.

**Step 2 — Run structural validation**

Prompt: "Run a structural validation on the project file for PROJ-001."

Review any failures.  Common structural failures and how to resolve them are
listed in the reference table below.  Resolve all failures before continuing.

**Step 3 — Run semantic validation**

Prompt: "Run a semantic validation on PROJ-001."

Pay particular attention to resource overallocation and negative float, as
these are most likely to affect the schedule narrative.  Resolve or acknowledge
all failures before continuing.

**Step 4 — Run NISTA compliance validation**

Prompt: "Run a NISTA compliance check on PROJ-001 at standard strictness."

Obtain a 100% compliance score (or as close as possible given the project's
current phase) before generating the report.  If fields are flagged as missing,
collect the information from the appropriate data owner before continuing.

**Step 5 — Run custom validation**

Prompt: "Run custom validation rules on PROJ-001."

Resolve any failures that your organisation's governance standards require to
be addressed before submission.

**Step 6 — Generate the quarterly return**

Prompt: "Generate a GMPP Q2 2025-26 return for PROJ-001, including AI narratives."

Review the generated narrative sections.  These are drafts — they must be
reviewed, edited where necessary, and approved by the SRO or their delegate
before submission.  Pay particular attention to the DCA narrative, which will
receive the most IPA scrutiny.

**Step 7 — Validate the report file**

Prompt: "Validate the GMPP report for PROJ-001 Q2 2025-26 before submission."

Achieve a 100% compliance score on the report file before proceeding.  If
issues are found, correct them and re-validate.

**Step 8 — Test submission to sandbox**

If this is the first submission for this project or this quarter's structure
is materially different from the last:

Prompt: "Submit the Q2 2025-26 return for PROJ-001 to the NISTA sandbox."

Confirm that the sandbox submission is accepted without errors.

**Step 9 — Submit to production**

Once the report has been reviewed and approved through your internal governance
process:

Prompt: "Submit the Q2 2025-26 return for PROJ-001 to NISTA production."

Record the submission ID in your project log.  The IPA will use this ID if they
raise any queries about the submission.

---

## Common validation failures and how to fix them

| Failure | Module | What it means | How to fix it |
|---------|--------|--------------|---------------|
| Orphan task | validate_structure | A task exists in the project file with no parent in the work breakdown structure | Add the task to the correct part of the hierarchy, or delete it if it is a duplicate |
| Circular dependency | validate_structure | Two or more tasks form a dependency loop | Review the predecessor chain for the tasks listed and remove the link that creates the loop |
| Invalid resource reference | validate_structure | A task is assigned to a resource not in the project resource list | Either add the resource to the resource list or correct the assignment to reference an existing resource |
| Duplicate task ID | validate_structure | Two tasks share the same identifier | Rename one of the tasks; check whether the duplication reflects an actual data entry error |
| Date inconsistency | validate_structure | A task's finish date is earlier than its start date | Correct the dates in the project file; if dates are driven by constraints, check the constraints |
| Negative float | validate_semantic | A task's late finish is earlier than its early finish | Review the constraints and dependencies on the affected tasks; negative float is usually caused by an over-constrained schedule |
| Resource overallocation | validate_semantic | A resource is assigned to more work than their availability permits | Adjust assignments, extend durations, or revise resource availability in the project file |
| Baseline variance breach | validate_semantic | Cost or schedule has deviated from baseline beyond the configured threshold | Update the project narrative to explain the variance, and consider whether a formal re-baselining is needed |
| Missing DCA value | validate_nista | The Delivery Confidence Assessment field is empty | Obtain the current DCA rating from the SRO and enter it in the project file |
| Invalid DCA value | validate_nista | The DCA field contains a value not on the IPA's permitted list | Replace the value with one of the six permitted values (see the validate_nista section above) |
| Missing IPA code | validate_nista | The project's IPA registration code is not present in the data | Obtain the code from your departmental NISTA lead and add it to the project file |
| Missing SRO details | validate_nista | SRO name or contact email is absent | Enter the current SRO's details; confirm they match the NISTA master registry using fetch_nista_metadata |
| Missing cost data | validate_nista | Whole-life cost or spend-to-date figures are absent or incomplete | Obtain the current approved cost figures from your finance business partner |
| Report field mapping error | validate_gmpp_report | A required field is present in the project data but was not correctly written into the report | Re-run generate_gmpp_report; if the problem persists, contact your platform administrator |

---

## A note on credentials and environments

### What credentials are needed

Submitting to NISTA requires two items:

- A NISTA API key — issued to your department by the IPA.
- A project-level authentication token — linked to your GMPP project registration.

These are sensitive credentials and should never be shared in a conversation,
entered into a chat interface, or stored in a project file.

### How credentials are configured

Your IT team will store the NISTA credentials as environment variables on the
server running the PDA Platform.  The variable names are defined in the platform
configuration documentation provided to your technical team.  Once they are in
place, the `submit_to_nista` tool will use them automatically — you do not need
to handle them or refer to them when using Claude.

If you receive an authentication error when attempting a submission, report it
to your IT team rather than attempting to resolve it yourself.

### Sandbox versus production

The sandbox environment is a test instance of NISTA maintained by the IPA for
integration and testing purposes.  Submissions made to the sandbox:

- Do not appear in your official GMPP record.
- Do not count as having met your quarterly submission obligation.
- Can be submitted as many times as needed without consequence.

Separate credentials are typically used for sandbox and production.  Your IT
team will configure both.  When using Claude, specify the environment explicitly
in your prompt (for example, "submit to the NISTA sandbox" or "submit to NISTA
production") to ensure the correct environment is used.

---

## Frequently asked questions

**Do I need to run all four validation checks before generating a quarterly return?**

It is strongly recommended but not enforced by the platform.  You can generate
a report at any time, but doing so before validation is complete increases the
risk of producing a return that contains errors or fails NISTA submission
validation.  The four checks together typically take only a few minutes and are
worth running on every submission cycle.

**What happens if I fix a problem between validation and report generation?**

Re-run the relevant validation check after making changes to confirm that the
issue is resolved.  If the change is significant — for example, correcting the
DCA value or updating cost data — re-run `validate_nista` before generating the
report.

**Can I edit the generated report JSON manually?**

Yes, but exercise caution.  The report JSON has a specific structure required by
NISTA.  If you edit it directly, run `validate_gmpp_report` again afterwards to
confirm the file is still valid.  In most cases it is better to correct the
underlying project data and regenerate the report.

**The AI-generated narrative does not accurately reflect the project.  What should I do?**

Edit the narrative manually before submission.  AI-generated narratives are
drafts — they are intended to reduce the time spent writing from scratch, not
to replace human judgement.  The SRO or their delegate must review and approve
all narratives regardless of their source.

**What if the NISTA system is unavailable at submission time?**

Try again after a short interval.  If the system remains unavailable close to
the deadline, contact your departmental NISTA lead and the IPA helpdesk
immediately so that a manual or alternative submission route can be arranged.
Keep a copy of the report JSON and the timestamp of your attempted submission
as evidence.

**Can I submit an amended return after the deadline?**

This depends on the IPA's policy for the relevant quarter.  Contact your
departmental NISTA lead and the IPA directly.  The platform can re-submit an
updated report to NISTA at any time, but whether the IPA will accept a late
amendment is a policy matter outside the platform's control.

**The submission returned warnings rather than errors.  Do I need to resubmit?**

Not necessarily.  Warnings indicate that the IPA system has noted something for
attention but has not rejected the submission.  Review each warning with your
departmental NISTA lead.  If any warning relates to a factual error in the
return, resubmit with a corrected report.  If the warnings are expected (for
example, a known data gap that has been notified to the IPA), keep a record of
the warning text alongside the submission ID for your audit trail.

**How do I know which version of the NISTA data standard my validation is checking against?**

The version of the NISTA standard used by the validation tools is configured
when the platform is deployed and updated by your technical team when the IPA
issues a new version.  Your platform administrator can confirm which version
is active.  If the IPA has issued a new standard version and you are unsure
whether the platform has been updated, check with your technical team before
submitting.
