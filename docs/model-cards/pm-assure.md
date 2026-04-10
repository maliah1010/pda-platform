# Model Card: pm-assure AI Tools

This model card describes the AI-powered components within the `pm-assure` module of PDA Platform. It is intended for information governance teams, senior responsible owners, and others who need to understand what AI is doing within the assurance toolchain.

---

## Model Details

- **Foundation model**: Anthropic Claude (`claude-3-5-sonnet`) accessed via the Anthropic API.
- **Version**: The model version is pinned in the `agent-task-planning` package. See `packages/agent-task-planning/pyproject.toml` for the current pin.
- **Integration layer**: The `agent-task-planning` package provides provider abstraction, multi-sample confidence extraction, and structured output handling. The underlying model is called via the `anthropic` Python SDK.
- **Purpose**: Extracting structured review actions from unstructured review text, detecting recurrence of actions across review cycles, and generating assurance narratives.

---

## Intended Use

The AI components in `pm-assure` are designed for use by project delivery professionals and assurance teams working on UK government programmes. The primary use cases are:

- **Review action extraction** (`track_review_actions`, P3): given a body of review text (e.g. a gate review report or review minutes), the model identifies discrete action points, assigns each a confidence score (0.0–1.0), and returns structured records suitable for tracking.
- **Recurrence detection** (`track_review_actions`, P3): the model compares newly extracted actions against the historical action store to identify whether the same or similar actions have appeared in previous review cycles, using a configurable similarity threshold.
- **Narrative generation** (`generate_narrative`, pm-nista): given structured project data fields, the model drafts a DCA (Delivery Confidence Assessment) narrative for GMPP quarterly returns.

All outputs are advisory. They are intended to support human review, not to replace it.

---

## Out-of-Scope Uses

The following uses are outside the intended scope of these tools and should be avoided:

- **Legal or regulatory decisions**: outputs should not be used as the sole basis for legal, regulatory, or formal programme decisions without independent human review.
- **Performance management of individuals**: the tools process project-level data and review text. They are not designed to assess, rank, or make decisions about named individuals. No personal data should be submitted to these tools.
- **Sole basis for gate approval or rejection**: gate readiness scores (P14) and extracted actions (P3) are advisory inputs to a human-led gate review process. They should not be the sole determining factor in a gate decision.
- **Jurisdictions outside UK government project delivery**: the tools are calibrated against NISTA, GMPP, and IPA frameworks. Use in other regulatory contexts has not been evaluated.

---

## Training Data

Not applicable. PDA Platform uses a pre-trained foundation model (Anthropic Claude) via API. No fine-tuning or additional training has been performed using project delivery data. The model's training data, training methodology, and data governance are Anthropic's responsibility and are documented in Anthropic's published model cards.

---

## Evaluation

### Confidence Scoring

Every AI extraction returns a confidence score on a 0.0–1.0 scale. This score is derived from multi-sample consensus: the `agent-task-planning` package requests multiple independent completions for each extraction, then measures the degree of agreement across samples. A low consensus score indicates that the model's outputs varied across samples, which is a signal that human review is particularly important for that extraction.

Confidence scores are model-reported values reflecting internal consistency across samples. They have not been externally validated against a ground truth dataset of UK government review documents.

### Recurrence Detection

Recurrence detection uses sentence-transformer embeddings to compare newly extracted actions against stored historical actions. The similarity threshold is configurable (default: 0.85). Actions with a similarity score above the threshold are flagged as potentially recurring. The threshold should be tuned by teams based on their tolerance for false positives and false negatives.

---

## Limitations

- **Domain jargon**: the model may miss or misinterpret context-specific terminology (e.g. programme-specific acronyms, departmental shorthand) that is not explained in the review text. Teams with highly specialised vocabulary should review low-confidence extractions carefully.
- **Confidence score calibration**: confidence scores reflect agreement across model samples, not accuracy against an external reference. A high confidence score does not guarantee correctness.
- **Context window**: very long review documents may be truncated if they exceed the model's context window. The tool does not currently implement chunking for documents above the context limit.
- **API dependency**: the AI-powered tools require a valid `ANTHROPIC_API_KEY` environment variable. Tools fail gracefully if the key is absent, but AI-dependent features are unavailable.
- **Language**: the model performs best on English-language text. Performance on Welsh-language documents or mixed-language content has not been evaluated.

---

## Ethical Considerations

- **No PII processed**: the tools are designed to process project-level text and structured project data. No personal data, named individuals, or sensitive personal information should be submitted. The system has no mechanism to enforce this at the API boundary; responsibility for data minimisation rests with the user.
- **Advisory outputs**: all outputs carry confidence scores and are explicitly labelled as recommendations or extractions requiring human review. The platform documentation consistently describes outputs as advisory.
- **Auditability**: every AI-generated output stored in the AssuranceStore includes the tool name, timestamp, project identifier, and confidence score, enabling retrospective audit of AI-influenced decisions.
- **Override capability**: the P6 Override Decision Logger allows practitioners to record when a governance decision proceeds against an AI-generated recommendation. This supports contestability and audit.

---

## Caveats

- Deployments on Render's free tier may experience cold start latency of several seconds on the first request after a period of inactivity. This affects response time but not output quality.
- The `agent-task-planning` package is under active development. The specific model version and confidence extraction algorithm may change between releases. Significant changes will be noted in the package changelog.
- Multi-sample consensus increases API call volume relative to single-pass extraction. Teams with API usage budgets should account for this when estimating costs.
