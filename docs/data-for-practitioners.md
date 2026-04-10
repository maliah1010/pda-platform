# Project Data Tools — A Guide for Project Managers and Programme Leads

This guide explains the six project data tools available in the PDA Platform
that let you load, query, and export your project schedule through Claude.  No
technical background is needed.

---

## What is this for?

Before any analysis can happen — before gate readiness is assessed, before
benefits are tracked, before compliance is checked — the platform needs to know
what your project actually looks like: its tasks, milestones, dependencies, and
critical path.

The pm-data module is where that information enters the platform.  It reads
your project schedule from whatever tool your team uses, makes the data
available for querying and analysis, and can export it in the formats required
for NISTA reporting.

If you are about to run a gate readiness assessment or submit a NISTA quarterly
return, you will almost certainly need to use the data tools first.

---

## Before you start

### Supported file formats

The platform accepts project data from all of the following sources:

| Format | Source tool | What to export |
|--------|-------------|----------------|
| MS Project XML (.xml) | Microsoft Project | File > Save As > XML |
| MS Project MPP (.mpp) | Microsoft Project | Native project file |
| Oracle Primavera P6 (.xer) | Oracle Primavera P6 | File > Export > XER |
| Jira JSON export | Jira | Issues > Export > JSON |
| Monday.com export | Monday.com | Board > Export to Excel/JSON |
| Asana export | Asana | Project > Export > JSON |
| Smartsheet export | Smartsheet | File > Export > Excel or JSON |
| GMPP CSV | Government Major Projects Portfolio | Standard GMPP template |
| NISTA JSON | Any source | Structured NISTA-compliant JSON |

If your organisation uses a tool not listed here, speak to your programme
office.  It may be possible to export to one of the supported formats from
within your tool, or to request a connector for your specific platform.

### Getting your export from common tools

**Microsoft Project:**  Open your project file.  Go to File > Save As, change
the file type to "XML Format" and save.  This is the most reliable option.
If you are on an older version of MS Project, look for File > Save As > XML
Data.

**Oracle Primavera P6:**  Go to File > Export.  Select XER as the export
type.  Include all relationships and resource assignments if you want full
dependency mapping.

**Jira:**  Go to your board or backlog view.  Use the Export option in the top
right (it may be under the three-dot menu).  Select JSON as the format.  If
you only see CSV, ask your Jira administrator to enable the full export.

**Monday.com, Asana, Smartsheet:**  Each of these tools has an export function
in the board or project settings menu.  Select JSON where available.  If your
tool only exports to Excel, your programme office may be able to convert it.

**GMPP CSV:**  Use the standard GMPP template as downloaded from the
Infrastructure and Projects Authority (IPA) portal.  Do not modify the column
headers.

---

## load_project

### What it does

This is the starting point.  It reads your project file and loads the schedule
data into the platform so that the other tools can work with it.  Until you
have loaded a project, none of the other data tools will have anything to
operate on.

Each load is associated with a project ID that you provide.  If you load a
new file for the same project ID at a later date, the platform replaces the
previous data.  This means you can refresh your schedule at any point — before
a gate review, after a re-plan, or at the start of a new reporting period —
and the analysis tools will immediately work against the updated data.

### When to use it

- At the start of any analysis session, if you have not already loaded the
  current schedule.
- After a significant re-plan, to ensure the platform is working from the
  latest baseline.
- Before generating a NISTA export, to confirm the data is current.
- Before running a gate readiness assessment.

### Example prompts

To load from a file on your computer (Claude Desktop):

- "Load the project file at C:/Projects/PROJ-001/plan.xml for project
  PROJ-001."
- "Load the Primavera export at /exports/proj001.xer as project PROJ-001."

To load by pasting or uploading content (Claude.ai):

- "I'm going to paste the contents of my MS Project XML file.  Please load it
  as project PROJ-001."
- "I've uploaded my Jira export.  The filename is jira-export-2026-04.json.
  Please load it as project PROJ-001."

See the section on [Claude.ai vs Claude Desktop](#using-with-claudeai-vs-claude-desktop)
below for more detail on which approach to use and why.

### What to expect back

The platform confirms that the file has been loaded and returns a brief
summary: the number of tasks found, the detected format, and the project
start and finish dates it has identified.  If the file cannot be read — for
example because a required export field is missing — it will say so clearly and
explain what is needed.

### Common pitfalls

- **Exporting from MS Project as CSV instead of XML.**  CSV exports from MS
  Project do not include dependency (predecessor/successor) information.  Always
  use XML if you need dependency data.
- **Partial Jira exports.**  By default, some Jira export configurations only
  include currently visible columns.  Make sure your export includes all fields,
  including sprint, assignee, and link (dependency) data.
- **Loading the wrong version.**  If your team keeps multiple plan files (e.g.,
  a baseline and a current plan), make sure you are loading the one that
  represents the current state.

---

## query_tasks

### What it does

Once a project is loaded, this tool lets you retrieve a filtered list of tasks.
You can narrow the results by status, by whether a task is on the critical path
or is a milestone, by who it is assigned to, or by date range.  By default it
returns up to 100 tasks.

### When to use it

- To get a list of overdue tasks before a progress review.
- To see all tasks assigned to a particular team member.
- To pull out milestones only for a summary report.
- To find tasks due in the next four weeks.

### Example prompts

- "Show me all overdue tasks for project PROJ-001."
- "List the milestones for PROJ-001 that are due between 1 May and 30 June
  2026."
- "Which tasks in PROJ-001 are assigned to Sarah Jones?"
- "Show me the critical path tasks for PROJ-001 that are still in progress."
- "List all tasks in PROJ-001 with a status of 'Not Started' that were due to
  start before today."

### What to expect back

A list of matching tasks, each showing: task name, assignee, planned start and
finish dates, current status, whether it is on the critical path, and whether
it is a milestone.  If more than 100 tasks match your filter, the platform will
tell you and suggest narrowing the criteria.

### Common pitfalls

- **Assignee names must match the plan exactly.**  If your plan has "S. Jones"
  but you ask for "Sarah Jones", nothing will be returned.  If you are not sure
  of the exact name, ask for all tasks first and look at what names appear.
- **Date filters use the task's planned dates, not actual dates.**  If a task
  started late, the filter will still look at the original planned start date
  unless you ask specifically for actual dates.

---

## get_critical_path

### What it does

The critical path is the sequence of tasks that determines the earliest
possible finish date for the project.  Any delay to a task on the critical
path — however small — pushes the project end date out by the same amount.

This tool identifies all tasks on the critical path and, optionally, near-
critical tasks: those with five days of float or fewer.  A task with very
little float is not yet critical, but it is close enough that a small delay
could make it so.

### When to use it

- Before a gate review, to understand which tasks present the greatest schedule
  risk.
- During a re-planning exercise, to confirm that your proposed changes do not
  inadvertently create a new critical path.
- When escalating a delay to a senior stakeholder, to explain whether the
  affected task is critical or has contingency.

### Example prompts

- "Show me the critical path for project PROJ-001."
- "Which tasks in PROJ-001 are on the critical path or near-critical (within
  5 days of float)?"
- "How long is the critical path for PROJ-001 in working days?"
- "Are any of the critical path tasks in PROJ-001 currently overdue?"

### What to expect back

A list of critical path tasks in sequence, showing each task's name, planned
duration, float (number of days), and current status.  Near-critical tasks are
clearly labelled separately if you have asked for them.  The platform will also
tell you the total critical path length in working days.

### Common pitfalls

- **Your plan must have dependencies set.**  The critical path cannot be
  computed if tasks are not linked to each other.  A flat list of tasks with
  no predecessor/successor relationships will not produce a meaningful critical
  path.  If the result looks wrong, ask the platform to show you how many
  dependency relationships it found.
- **Milestone-only critical paths.**  Some project files have dependencies only
  on milestones, not on the tasks between them.  This can give the appearance
  of a short critical path when the real schedule risk is hidden in the task-
  level detail.

---

## get_dependencies

### What it does

This tool maps the dependency network: for any given task (or for the whole
project), it shows what that task is waiting for (predecessors) and what is
waiting for it (successors).  You can ask for predecessors only, successors
only, or both.

This is particularly useful before gate reviews, when you need to understand
the downstream impact of a task that is running late, or when you are
preparing a risk assessment and want to identify which tasks have the most
dependencies clustered around them.

### When to use it

- When a task is delayed and you need to know what else will be affected.
- When you are reviewing a supplier delivery and need to know what is blocked
  behind it.
- When constructing a risk description — "if this task slips, these five other
  tasks cannot start".
- When validating that the plan is logically connected and has no orphaned
  tasks.

### Example prompts

- "Show me the dependencies for the task 'Infrastructure Procurement' in
  project PROJ-001."
- "What does the 'User Acceptance Testing' task in PROJ-001 depend on?"
- "What tasks in PROJ-001 are blocked behind the 'Data Migration' task?"
- "Show me the full dependency network for project PROJ-001."
- "Which tasks in PROJ-001 have no predecessors?" (useful for checking plan
  logic)

### What to expect back

For a single task: a list of its predecessors (what it depends on) and its
successors (what depends on it), with the dependency type (finish-to-start,
start-to-start, etc.) and any lag or lead time.

For the full network: a structured overview of all task relationships, which
may be large for complex programmes.  Consider asking for a summary or
filtering to a specific part of the plan if the full output is unwieldy.

### Common pitfalls

- **Dependency types matter.**  A finish-to-start dependency means one task
  cannot start until another finishes.  A start-to-start dependency means they
  can run in parallel from the same start point.  If the dependency type is not
  what you expect, the plan logic may need reviewing.
- **Large programmes.**  Asking for the full dependency network on a programme
  with several hundred tasks will produce a very large result.  In most cases
  it is more useful to query dependencies for a specific task or section of the
  plan.

---

## convert_format

### What it does

This tool exports the loaded project data to a different format.  There are
four output formats available:

| Format | Use case |
|--------|----------|
| MS Project XML (mspdi) | Re-importing into Microsoft Project or sharing with teams who use it |
| JSON | Integrations with other systems, bespoke analysis, or archiving |
| NISTA JSON | Submission to the NISTA Programme and Project Data Standard |
| NISTA CSV | Completing the IPA quarterly return template |

The conversion uses the data that is currently loaded in the platform.  It does
not re-read the original source file.

### When to use it

- At the end of a reporting period, to generate the NISTA JSON or CSV for your
  quarterly GMPP return.
- When sharing schedule data with a team that uses a different tool.
- When submitting a schedule as part of a gate review evidence pack.
- When you want a clean JSON snapshot of the current plan for records.

### Example prompts

- "Export project PROJ-001 to NISTA JSON."
- "Generate the NISTA CSV for PROJ-001 for the quarterly return."
- "Convert the PROJ-001 plan to MS Project XML format."
- "Export PROJ-001 as JSON for our integration system."

### What to expect back

The converted file content, which you can copy, download, or have Claude save
to a location you specify.  For NISTA formats, the platform will confirm which
fields have been mapped and flag any fields that are required by the standard
but were not present in the source data.

### Common pitfalls

- **Missing NISTA-required fields.**  The NISTA standard requires certain fields
  that not all source formats include — for example, benefits ownership or
  Senior Responsible Owner details.  If these are missing, the export will be
  produced but the platform will list the gaps.  You will need to add those
  fields manually before formal submission.
- **Converting before loading.**  The tool works on data already loaded in the
  session.  If you have started a new conversation with Claude, you will need
  to load the project again before converting.

---

## get_project_summary

### What it does

Returns a concise overview of the loaded project: total number of tasks,
critical path length in working days, number of milestones, project start and
finish dates, and the source format the data was loaded from.

This is the quickest way to confirm that the right data has been loaded and to
get a top-level picture before diving into more detailed analysis.

### When to use it

- As the first thing you ask after loading a project, to verify the data looks
  correct.
- At the start of a review meeting, for a quick orientation.
- When you need headline figures for a briefing note or slide.
- Before converting to NISTA format, to confirm the project dates and milestone
  count look right.

### Example prompts

- "Give me a summary of project PROJ-001."
- "What are the headline figures for PROJ-001?"
- "How many milestones does PROJ-001 have?"
- "What is the planned completion date for PROJ-001?"
- "How long is the critical path for PROJ-001?"

### What to expect back

A short structured summary, for example:

- **Source format:** MS Project XML
- **Total tasks:** 247
- **Milestones:** 18
- **Project start:** 3 February 2025
- **Project finish:** 14 November 2026
- **Critical path:** 83 working days

### Common pitfalls

- **The summary reflects what was loaded, not the current state of your plan.**
  If the plan has changed since you last loaded it, the summary will be out of
  date.  Re-load the latest file before relying on the figures.

---

## Typical workflow

The six tools are designed to be used in sequence.  Below is the recommended
flow for the two most common scenarios.

### Before a gate review

1. **Load the current schedule.**
   Ask Claude to load the latest version of your project file.  Confirm with a
   project summary that the dates and task count look right.

2. **Check the critical path.**
   Ask for the critical path, including near-critical tasks.  Identify any
   critical tasks that are currently overdue or at risk.

3. **Query overdue and at-risk tasks.**
   Ask for all overdue tasks, and separately for tasks due in the next four
   weeks.  This gives you the short-term picture alongside the structural
   schedule risk.

4. **Map dependencies on problem tasks.**
   For any task that is delayed or at risk, ask for its successors.  This tells
   you what is downstream and helps you assess the realistic impact of the
   delay.

5. **Export for the evidence pack.**
   If the gate requires a schedule submission, use convert_format to produce
   the appropriate output — MS Project XML for the reviewer, or NISTA JSON if
   the gate is a GMPP milestone.

### For the quarterly NISTA return

1. **Load the latest plan.**
   Use load_project with the most recent export from your scheduling tool.

2. **Verify with a summary.**
   Use get_project_summary to confirm the project dates and milestone count
   match what you expect to report.

3. **Check milestones specifically.**
   Use query_tasks filtered to milestones only, to review each milestone's
   planned and actual dates before they go into the return.

4. **Convert to NISTA format.**
   Use convert_format with either NISTA JSON (for system submission) or NISTA
   CSV (for the quarterly return template).  Review any flagged missing fields
   and add them manually before submitting.

---

## Using with Claude.ai vs Claude Desktop

The platform supports two ways of getting your project file into Claude.  Which
one to use depends on how you access Claude.

### Claude Desktop (recommended for large files)

If you have Claude Desktop installed on your computer, Claude can read files
directly from your local file system.  You provide the file path and Claude
handles the rest.

**Use this approach when:**

- Your project file is larger than a few megabytes (MS Project or Primavera
  files often are).
- You want to avoid copying and pasting large amounts of text.
- You are working with a file in a fixed location that you will reload
  regularly.

**How to do it:**

Tell Claude the path to your file.  For example:

- "Load the project at C:/Projects/PROJ-001/current-plan.xml for project
  PROJ-001."
- "Load /Users/yourname/Documents/proj001-export.xer as project PROJ-001."

The key parameter used here is the file path.  Claude passes it to the
platform, which reads the file directly.

### Claude.ai (browser — file upload or paste)

If you are using Claude through a web browser, Claude cannot access your local
file system.  Instead, you have two options:

**Option 1 — Upload the file.**  In Claude.ai, use the attachment or upload
button to attach the file to your message.  Then tell Claude:

- "I've uploaded my project file.  The filename is current-plan.xml.  Please
  load it as project PROJ-001."

**Option 2 — Paste the content.**  Open the file in a text editor (this works
for XML, JSON, XER, and CSV files), select all, and paste the content into
your message.  Then tell Claude:

- "I'm pasting the contents of my MS Project XML file below.  Please load it
  as project PROJ-001."

With both browser options, Claude passes the file content and the filename to
the platform, rather than a file path.  The platform uses the filename to help
it determine the format.

**Practical note on file size:**  Very large project files (for example, a
Primavera XER export for a large programme) can exceed what you can practically
paste into a browser conversation.  If you regularly work with large files,
Claude Desktop is a better fit.  If you only occasionally need to load
schedules, or your files are reasonably compact, the browser approach works
well.

---

## Tips for getting the most from the data tools

**Load once per session, not once per question.**  Once you have loaded a
project in a conversation, Claude remembers it for the rest of that
conversation.  You do not need to load it again before each question.  You
only need to reload if you are working from a freshly updated file.

**Be specific about task names.**  When asking about a particular task, use the
name as it appears in the plan.  If you are not sure of the exact name, ask
for a list of tasks first and then pick from the results.

**Use the summary as a sense check.**  Before running detailed queries or
generating a NISTA export, always ask for a project summary first.  If the
task count or project dates look wrong, it usually means the wrong file was
loaded or the export from your tool was incomplete.

**Chain queries together.**  The data tools work well in sequence within a
single conversation.  You might ask: "Show me the critical path" and then,
based on what comes back, immediately follow up with "Now show me the
dependencies for the Infrastructure Delivery task".  Claude will use the
already-loaded data for the follow-up question.

**Ask Claude to interpret the results.**  The data tools return facts — task
lists, dependency maps, path lengths.  If you want an assessment of what those
facts mean for your gate readiness or reporting, ask Claude to interpret them.
For example: "Based on those critical path tasks, what is the most significant
schedule risk I should flag at next week's gate?"

**Keep your source file current.**  The quality of the analysis depends
entirely on the quality of the schedule you load.  A plan that has not been
updated for six weeks will produce six-week-old answers.  Before any
significant review, load a freshly exported file from your scheduling tool.

**Check NISTA outputs before submitting.**  When you use convert_format to
produce a NISTA export, review the list of flagged missing fields before
sending anything formally.  Some NISTA-required fields — such as benefits
ownership and SRO details — need to be added manually if they are not captured
in your scheduling tool.

---

## Frequently asked questions

**Do I need to re-load the project every time I start a new conversation with
Claude?**

Yes.  Each conversation starts fresh.  If you open a new chat, you will need
to load the project file again before using any of the data tools.

**Can I have more than one project loaded at the same time?**

Yes.  Each project is identified by its project ID.  You can load multiple
projects in the same conversation by giving each one a different ID and then
specifying which project you are asking about in each question.

**What if my project file uses a different date format or calendar to the
platform's default?**

The platform reads calendar settings from MS Project XML and Primavera XER
exports where they are present.  If working days or bank holidays are set up
in your project file, they should carry through.  For formats that do not
include calendar information, the platform uses a standard five-day working
week.  If your critical path lengths look different from what your scheduling
tool shows, a calendar mismatch is a likely cause.

**Can I query tasks across multiple loaded projects at once?**

You can ask Claude to compare information across projects, but the underlying
queries run against one project at a time.  Ask your question in terms of
project IDs — for example, "How does the critical path length of PROJ-001
compare to PROJ-002?" — and Claude will run both queries and present a
comparison.

**The critical path looks much shorter than I expected.  What might be wrong?**

The most common causes are: dependencies not being set in the source file;
the export only including summary tasks rather than detailed tasks; or a
partial export that does not include all tasks.  Ask Claude to tell you how
many dependency relationships it found when the project was loaded.  If that
number is very low relative to the task count, the dependency structure is
probably not in the export.

**My Jira export does not include dependencies.  Can I still use the data?**

Yes.  You can still load the data and query tasks by status, assignee, and
date.  The get_critical_path and get_dependencies tools will not produce
meaningful results without dependency information, but query_tasks and
get_project_summary will work normally.

**How do I know which version of my plan is currently loaded?**

Ask Claude: "What file is currently loaded for project PROJ-001 and when was
it loaded?"  Claude will tell you the filename and the format it was loaded
from.  If you are unsure whether the data is current, reload from your latest
export to be certain.

**Is there a limit to how many tasks the platform can handle?**

The platform is designed for programmes of the scale typically found in
government and infrastructure portfolios.  Very large programmes with thousands
of tasks may take slightly longer to process, but there is no hard limit.  If
you are working with an unusually large programme, load it and check the
summary — if the task count looks right, the data has been read correctly.
