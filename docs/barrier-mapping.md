# PDA Platform — Barrier Mapping

This document maps each component of the PDA Platform to the six systemic
barrier themes identified in the PDATF Green Paper *Closing the Gap: A Practical
Framework for Implementing Data and AI into the Built Environment* (June 2025)
and developed further in *From Policy to Practice: An Open Framework for
AI-Ready Project Delivery* (Newman, 2026).

---

## Background

In June 2025, the Project Data Analytics Task Force (PDATF) published its
Green Paper, the product of several years of cross-sector collaboration
involving government, industry, and academia.  It set out to answer a specific
question: why, despite a strong national policy landscape, does the practical
adoption of AI and data analytics in UK project delivery remain so inconsistent?

The Green Paper's assessment was that "the gap between strategy and
implementation remains wide" and that "structural challenges spanning data
architecture, digital infrastructure, procurement frameworks, organisational
capabilities, and governance were constraining progress not in isolation, but
systemically" [1].

The Government Major Projects Portfolio approaches £800 billion across over
200 major projects, with over 26,000 civil servants in the project delivery
function.  Despite robust policy architecture — the National Data Strategy,
AI Opportunities Action Plan, 10-Year Infrastructure Strategy, Green Book,
Magenta Book, Teal Book, GovS 002, and the Construction Playbook — the
platform for AI-enabled delivery did not exist.  The PDA Platform is that
platform.

---

## The Six Barrier Themes

The Green Paper identified six barrier themes that "must be addressed in
tandem" [1]:

| # | Barrier | Core challenge |
|---|---------|---------------|
| 1 | Leadership and Alignment | AI adoption disconnected from strategic leadership |
| 2 | Data Pooling and Interoperability | Siloed data, bespoke systems, incompatible formats |
| 3 | Digital and Tech Constraints | Legacy systems, vendor lock-in, under-investment |
| 4 | Skill and Culture Gaps | Technical talent shortage, limited AI fluency, cultural resistance |
| 5 | Procurement and Commercial Models | Outcome blindness, IP ambiguity, vendor lock-in |
| 6 | Risk, Ethics, and Assurance | Assurance frameworks not keeping pace with AI |

---

## Barrier 1: Leadership and Alignment

### From the Green Paper

> "AI adoption in most organisations remains disconnected from strategic
> leadership.  The green paper recommended naming an executive AI sponsor at
> board level, shifting to value-creation metrics, funding foundational data
> infrastructure before proofs of concept, and embedding meaningful human
> oversight into stage-gate governance." [1]

The deeper analysis in *From Policy to Practice* confirms that "governance
must be integrated into existing stage-gate processes, not bolted on as an
additional layer" [2].  The ideal target state is one in which "AI adoption
in major projects is sponsored from the boardroom, coordinated at programme
level, and embedded in project delivery routines. Outcome-based measures
(carbon, social value, schedule certainty) sit alongside financial ROI." [2]

### How the PDA Platform addresses this

**Component**: `agent-task-planning` + `pm-assure` (P1–P10)

| Solution | How it helps |
|----------|-------------|
| Confidence scoring | Connects AI outputs to outcome-based measures, giving sponsors quantified evidence for stage-gate decisions |
| Multi-sample consensus | Provides the "structured evidence base that stage-gate approvals need" [2] |
| P9 — Assurance Workflow Engine | Produces a single `ProjectHealth` classification (HEALTHY / ATTENTION_NEEDED / AT_RISK / CRITICAL) that maps directly to governance escalation |
| P10 — Domain Classifier | Tailors assurance intensity to project complexity, implementing the proportionate governance the Green Paper called for |

**Measurable outcomes**:
- ✅ Every AI-assisted analysis includes a confidence score and consensus measure
- ✅ Single workflow run produces executive-ready health classification and recommended actions
- ✅ Domain-appropriate review cadence (14–90 days) calibrated to actual project complexity

---

## Barrier 2: Data Pooling and Interoperability

### From the Green Paper

> "UK project delivery remains hampered by siloed data and bespoke systems.
> The green paper pointed to the National Underground Asset Register (NUAR) as
> a live blueprint and recommended mandating open, non-proprietary data
> standards, establishing a sector data trust, and deploying common data
> environments." [1]

*From Policy to Practice* identifies three specific sub-barriers: "Incompatible
data formats, where BIM, cost, and schedule data are held in closed or
inconsistent schemas; Lack of a trusted sharing framework, where organisations
are reluctant to share without legal protection; and Privacy and IP concerns,
where data holders fear loss of control." [2]

The ideal target state is "a trusted, standardised, and interoperable data
ecosystem, mandating open, non-proprietary formats and progressively retiring
legacy barriers." [2]

### How the PDA Platform addresses this

**Components**: `pm-data-tools` (canonical model + NISTA Validator)

This is the direct response to Barrier 2.  *From Policy to Practice* maps the
canonical model to Barrier 2 explicitly: it "provides the minimum data schema
and agreed open format the green paper called for." [2]

| Solution | How it helps |
|----------|-------------|
| 12-entity canonical model | Single open JSON Schema for project management information derived from the common denominator across all eight source formats |
| 8-format parser | Parses MS Project, Primavera P6, Jira, Monday.com, Asana, Smartsheet, GMPP, and NISTA — eliminating incompatible format barriers |
| Lossless conversion | Exports to any supported format without data loss, enabling genuine interoperability |
| NISTA Validator | Automated compliance checking against the emerging government standard — "the green paper called for" [2] — producing a 0–100% compliance score |

```python
from pm_data_tools import parse_project
from pm_data_tools.validators import NISTAValidator

# Parse from any format
project = parse_project("schedule.mpp")

# Validate against NISTA standard
result = NISTAValidator().validate(project)
print(f"Compliance: {result.compliance_score}%")
```

**Measurable outcomes**:
- ✅ 8 formats supported — zero manual re-keying between systems
- ✅ 100% data fidelity in round-trip conversions
- ✅ Automated NISTA compliance score replaces manual checking

---

## Barrier 3: Digital and Tech Constraints

### From the Green Paper

> "A significant portion of central government IT is legacy.  The Public
> Accounts Committee estimated that around 28 per cent of central government
> systems were classified as legacy." [2, citing 20]

The Green Paper recommended "auditing legacy systems, wrapping high-priority
systems with APIs, and pursuing incremental modernisation." [1]

The ideal target state is "modern, interoperable digital foundations.  Legacy
systems remediated or wrapped with open APIs.  AI tools deployed as force
multipliers for project professionals." [2]

### How the PDA Platform addresses this

**Components**: `pm-data-tools` + `pm-mcp-servers`

*From Policy to Practice* maps pm-data-tools to Barrier 3 directly: it
"wraps legacy PM tools with a programmatic interface, the API-wrapping approach
the green paper recommended." [2]

| Solution | How it helps |
|----------|-------------|
| Format parsers | Reads data from legacy PM tools without requiring those tools to be replaced or modified |
| Auto format detection | Identifies file format automatically — no configuration or IT involvement needed |
| MCP servers | Cloud-native, API-first architecture enabling AI access to project data without bespoke integration work |
| Local operation | Runs entirely on existing hardware — no new infrastructure, no server provisioning |

```bash
# Install — no infrastructure required
pip install pm-data-tools pm-mcp-servers

# Reads legacy MS Project files without MS Project installed
python -c "from pm_data_tools import parse_project; p = parse_project('legacy.mpp'); print(p.name)"
```

**Measurable outcomes**:
- ✅ Legacy PM files readable without replacing source systems
- ✅ Installation time under 5 minutes
- ✅ No IT department involvement required for pilot adoption

---

## Barrier 4: Skill and Culture Gaps

### From the Green Paper

> "In RICS' 2023 digitalisation survey, shortage of skilled persons ranked as
> the second-highest blocker, flagged as high by 50 per cent of global
> respondents." [2, citing 5]

> "Specific barriers: Technical talent shortages; Limited AI fluency in
> delivery roles; Cultural resistance and fear of displacement; and Fragmented
> CPD pathways." [2]

The ideal target state is one in which "every role has a defined baseline of
AI literacy.  Safe sandboxes available.  Continuous learning incentivised.
Change champions celebrated." [2]

*From Policy to Practice* maps pm-mcp-servers to Barrier 4: "natural-language
interaction with project data, lowering the technical barrier." [2]

### How the PDA Platform addresses this

**Components**: `pm-mcp-servers` + assurance practitioner documentation

| Solution | How it helps |
|----------|-------------|
| Natural language interface via MCP | Project managers ask questions in plain English — no Python, no data science skills required |
| Claude Desktop integration | Works through a familiar chat interface that delivery professionals already use |
| Practitioner guide | `docs/assurance-for-practitioners.md` explains all ten assurance features without technical background, aligned with the Green Paper's call for "more practitioner-friendly" guidance [1] |
| Pre-built MCP tools | 16 ready-to-use tools in pm-assure — no custom development needed |

```
# No code required — ask Claude directly:
"Show me the NISTA compliance trend for PROJ-001"
"When should the next review be scheduled for PROJ-001?"
"What is the overall health of PROJ-001?"
```

**Measurable outcomes**:
- ✅ Non-technical users can run compliance checks and assurance workflows through natural language
- ✅ Time from question to insight: seconds rather than hours
- ✅ Full practitioner documentation covering all ten features without technical prerequisites

---

## Barrier 5: Procurement and Commercial Models

### From the Green Paper

> "Four interlocking barriers: Outcome blindness, where transactional contracts
> leave no budget for data pipelines, model retraining, or cloud inference
> costs; IP and liability ambiguity around AI-generated outputs; Vendor lock-in
> through closed architectures; and Absence of transparency requirements for
> AI-assisted procurement decisions." [2]

The ideal target state is "outcome-based, data-friendly contracts.  AI-ready
clauses.  Shared-savings models routine.  Procurement encourages competition
and avoids lock-in." [2]

### How the PDA Platform addresses this

**Component**: MIT licence + open-source architecture

The platform's response to Barrier 5 is structural.  Proprietary tools create
the very lock-in the Green Paper identifies as a barrier.  The PDA Platform
eliminates that barrier at source.

| Solution | How it helps |
|----------|-------------|
| MIT licence | Free to use, modify, and distribute — no per-seat cost, no vendor negotiations |
| Open-source | Source code available for audit, customisation, and contribution |
| Provider-agnostic AI | `agent-task-planning` supports Anthropic, OpenAI, Google AI, and Ollama — no lock-in to a single AI vendor |
| Standard protocols | MCP (Model Context Protocol) is an open standard, not a proprietary integration |
| Composable components | Organisations can adopt pm-data-tools without pm-mcp-servers, or use the canonical model without the parser — no bundled purchase required |

**Measurable outcomes**:
- ✅ Zero licensing cost
- ✅ No vendor lock-in — replace any component or AI provider without rewriting
- ✅ Full source code available for public sector audit and transparency requirements

---

## Barrier 6: Risk, Ethics, and Assurance

### From the Green Paper

> "The green paper found that assurance frameworks had not kept pace with AI
> capabilities.  It recommended establishing ethics and assurance boards,
> mandating AI safety case templates, and working towards proportionate
> assurance." [1]

> "Specific barriers: Fragmented governance and unclear accountability;
> Insufficient use of HM Treasury guidance; Absence of embedded ethical
> processes; Lack of structured assurance mechanisms; and Innovation
> bottlenecks through over-regulation." [2]

The ideal target state is "risk, ethics, and assurance embedded seamlessly
across all levels.  Proportionate, risk-based checks.  Ethics-by-design.
Clear accountability and transparency." [2]

*From Policy to Practice* maps agent-task-planning to Barrier 6: "confidence
scoring, consensus, and human review, implementing proportionate assurance." [2]

### How the PDA Platform addresses this

**Components**: `agent-task-planning` + `pm-assure` (P1–P10)

This barrier receives the deepest treatment in the platform.  The ten assurance
features in pm-assure are a direct implementation of the structured assurance
mechanisms the Green Paper called for.

| Feature | How it addresses Barrier 6 |
|---------|---------------------------|
| P1 — Artefact Currency Validator | Detects stale or anomalously refreshed evidence artefacts before a gate — implements the evidence quality checks missing from current assurance practice |
| P2 — Longitudinal Compliance Tracker | Persists NISTA compliance scores over time; alerts on drops and floor breaches — the continuous monitoring the Green Paper called for |
| P3 — Cross-Cycle Finding Analyzer | Tracks whether assurance recommendations are acted on across review cycles — addresses the "fragmented governance" sub-barrier directly |
| P4 — Confidence Divergence Monitor | Detects when AI extraction is unreliable — implements the human review workflow called for in the Green Paper's "proportionate assurance" principle |
| P5 — Adaptive Review Scheduler | Calibrates review frequency to actual project risk signals rather than fixed calendar intervals — proportionate assurance in practice |
| P6 — Override Decision Logger | Structured logging and pattern analysis for governance decisions that proceed against assurance advice — addresses "unclear accountability" sub-barrier |
| P7 — Lessons Learned Knowledge Engine | Surfaces relevant lessons at the point of decision — implements the organisational learning dimension of risk management |
| P8 — Assurance Overhead Optimiser | Measures whether assurance effort is proportionate to outcomes — prevents "innovation bottlenecks through over-regulation" by identifying redundant checks |
| P9 — Assurance Workflow Engine | Deterministic multi-step orchestrator: runs P1–P8 in sequence, produces a single `ProjectHealth` classification and executive summary |
| P10 — Domain Classifier | Classifies project complexity (CLEAR / COMPLICATED / COMPLEX / CHAOTIC) and returns a tailored assurance profile — the risk-tiered approach the Green Paper explicitly recommended |
| Confidence extraction | Every AI-generated analysis includes a consensus score, sample spread, and human review flag — "confidence scoring, consensus, and human review, implementing proportionate assurance" [2] |

```python
from pm_data_tools.assurance.workflows import AssuranceWorkflowEngine, WorkflowType
from pm_data_tools.db.store import AssuranceStore

store = AssuranceStore()
engine = AssuranceWorkflowEngine(store=store)
result = engine.execute(
    project_id="PROJ-001",
    workflow_type=WorkflowType.FULL_ASSURANCE,
)
# result.health → ProjectHealth.HEALTHY / AT_RISK / CRITICAL …
print(result.executive_summary)
```

**Measurable outcomes**:
- ✅ 10 structured assurance capabilities, 16 MCP tools, 198 tests
- ✅ Every AI analysis includes quantified confidence and human review flag
- ✅ Override decisions logged, tracked, and pattern-analysed
- ✅ Assurance overhead measured — redundant effort identified and eliminated

---

## Platform–Barrier Mapping Summary

Adapted from Table 11 of *From Policy to Practice* [2], extended to include
pm-assure (P1–P10):

| Component | Primary Barrier | Secondary Barrier |
|-----------|----------------|-------------------|
| Canonical model (12 entities) | 2 — Data Pooling and Interoperability | — |
| pm-data-tools (8-format parser) | 3 — Digital and Tech Constraints | 2 — Data Pooling |
| NISTA Validator | 2 — Data Pooling and Interoperability | — |
| pm-mcp-servers | 4 — Skill and Culture Gaps | 3 — Digital and Tech |
| agent-task-planning | 6 — Risk, Ethics, and Assurance | 1 — Leadership |
| pm-assure (P1–P10) | 6 — Risk, Ethics, and Assurance | 1 — Leadership |
| MIT licence + open source | 5 — Procurement and Commercial | 3 — Digital and Tech |
| Practitioner documentation | 4 — Skill and Culture Gaps | — |
| Project Delivery Toolkit | 4 — Skill and Culture Gaps | 1 — Leadership |

---

## The Project Delivery Toolkit

> "The toolkit complements the paper: the paper provides narrative and evidence;
> the toolkit provides the reference interface.  It is maintained as an open
> resource and will be updated as implementation experience accumulates.  Each
> barrier theme page links to the relevant pda-platform component, ARMM
> dimension, and UDS specification, shortening the distance between
> understanding a barrier and doing something about it." [2]

The **Project Delivery Toolkit** (`projects-toolkit.netlify.app`) is the
interactive companion to this barrier mapping document.  Built with React,
Vite, and Recharts, it provides a navigable, filterable interface to the
framework content.

### What it does

| Feature | Description |
|---------|-------------|
| Donut chart visualisation | Six outer barrier themes with sub-barriers as an interactive ring — click any segment to filter resources |
| Persona filtering | Filter resources by role: Project Lead, Programme Lead, Business Lead |
| Search | Filter by title, description, and tags across all resources |
| Resource cards | Each resource links directly to the relevant pda-platform component, ARMM assessment, or UDS specification |

### Which barriers it addresses

The toolkit is primarily a response to **Barrier 4 (Skill and Culture Gaps)** —
it lowers the literacy barrier by presenting the framework in a visual,
navigable format that does not require reading the full paper.  It also
supports **Barrier 1 (Leadership and Alignment)** by providing the persona-
based action model in a format programme and business leads can engage with
directly.

*From Policy to Practice* describes the ideal target state for Barrier 4 as
one in which "every role has a defined baseline of AI literacy" and "safe
sandboxes [are] available." [2]  The toolkit operationalises the literacy
dimension: a programme lead can filter to their role and see exactly which
actions apply to them, without navigating the full analytical framework.

### How to use it alongside this document

This document explains *what* the platform does and *why* it addresses each
barrier.  The toolkit provides the *reference interface* — use it to:

- Explore sub-barriers and their recommended actions by persona
- Navigate from a barrier to the specific pda-platform component that addresses it
- Self-assess against the Indicative Questions (Section 3.3 of the paper)
- Share with colleagues who need a visual rather than a document

---

## Cross-cutting: Indicative Principles

*From Policy to Practice* distils six indicative principles — one per barrier
— that describe what must be true for adoption to succeed [2].  The platform
implements each:

| Barrier | Indicative Principle | Platform implementation |
|---------|---------------------|------------------------|
| Leadership and Alignment | Business-led with executive sponsorship; governance integrated into stage-gates | P9 health classification → stage-gate evidence; P10 domain profile → governance intensity |
| Data Pooling and Interoperability | Open standards mandatory; shared environments the norm | 12-entity canonical model published under MIT; 8-format interoperability |
| Digital and Tech Constraints | API-first and cloud-ready; vendor lock-in actively avoided | MCP servers (open protocol); runs locally on existing hardware |
| Skill and Culture Gaps | Defined baseline AI literacy per role; sandbox environments available | Natural language MCP interface; practitioner guide requires no technical background |
| Procurement and Commercial Models | Outcome-based and data-friendly; procurement encourages competition | MIT licence; provider-agnostic AI framework; composable components |
| Risk, Ethics, and Assurance | Proportionate assurance embedded; accountability clear and traceable | 10 assurance features; override logging; confidence scoring on all AI outputs |

---

## References

[1] PDATF (June 2025) *Closing the Gap: A Practical Framework for Implementing
Data and AI into the Built Environment*. London: PDA Task Force.

[2] Newman, A. (February 2026) *From Policy to Practice: An Open Framework for
AI-Ready Project Delivery*. London: Tortoise AI. CC BY 4.0.
DOI: [to be assigned on publication].

[3] Infrastructure and Projects Authority (2024) *Annual Report 2023–24*.
https://www.gov.uk/government/publications/infrastructure-and-projects-authority-annual-report-2023-24

[4] RICS (June 2023) *Digitalisation in Construction Report 2023*. London: RICS.

[5] EY and FIDIC (September 2024) *How Artificial Intelligence Can Unlock a New
Future for Infrastructure*. London/Geneva.
https://www.ey.com/en_uk/insights/infrastructure/how-artificial-intelligence-can-unlock-a-new-future-for-infrastructure

[6] House of Commons Committee of Public Accounts (March 2025) *Use of AI in
Government: 18th Report of Sessions 2024–25*. London: House of Commons.
https://committees.parliament.uk/publications/47199/documents/244683/default/

[7] NISTA (2025) *Programme and Project Data Standard — Trial Version*.

---

**Document Version**: 2.0
**Last Updated**: March 2026
**Maintained by**: PDA Platform Contributors
