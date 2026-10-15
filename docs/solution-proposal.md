# Solution Proposal (Draft — Pending Mirai Labs Approval)

**Project:** AI-Powered Clinical Note Extraction and Coding Agent MVP  
**Status:** Proposed solution; no implementation is authorized until formal approval.  
**Target environment:** Localhost MVP, single reviewer, English text notes, free-tier services only.

## 1. Proposal Summary

Build a local, evidence-gated clinical information extraction agent for the de-identified clinical transcriptions and ICD-10 reference table provided by Mirai Labs.

The proposed solution combines:
1. Structured extraction of clinical entities from the original note.
2. ICD-10 diagnosis candidate retrieval using keyword and semantic search over the supplied code table.
3. A separate verification pass to check source evidence, offsets, status, contradictions, and likely missed items.
4. An explicit agent loop that invokes tools, applies bounded retries, reconciles disagreements, and escalates unresolved or out-of-domain cases.
5. A local reviewer interface for highlighted evidence, item-level decisions, flagged issues, trace inspection, and JSON export.
6. A repeatable evaluation harness comparing the proposed agent with a naive single-prompt baseline.

The system is an assistive MVP, not an autonomous clinical decision-maker. Human review remains available, and uncertain results must not be presented as verified facts.

## 2. Problem and Proposed Approach

Clinical notes contain relevant information in varied wording and contexts. A keyword match alone may misinterpret negation, uncertainty, historical conditions, or contradictory statements. A generated entity can also look plausible without being supported by the actual note.

The proposed approach therefore makes source evidence and independent verification part of the acceptance decision. It also separates diagnosis-code candidate generation from deciding whether a candidate is sufficiently supported.

## 3. Required Extraction Scope

The system is proposed to extract the following categories from English clinical note text:

| Category | Required information |
|---|---|
| Diagnoses | Diagnosis mention, contextual status, supporting evidence, and ICD-10 candidates where applicable |
| Medications | Medication name, dose, route, frequency, and status where stated |
| Procedures | Procedure mention, status/context where stated, and supporting evidence; procedure-code assignment is excluded |
| Allergies | Allergy or absence/status information when stated |
| Vital signs and key measurements | Mentioned measurement, value, unit when stated, and evidence |

Do not infer missing dose, route, frequency, unit, diagnosis, or other clinical details. Represent unavailable information as absent/unknown according to the agreed schema rather than inventing a value.

## 4. Proposed Output Contract

Every extracted item should be represented in a strict, documented structure. The final field names and types will be defined in the schema before implementation.

| Field group | Intended content |
|---|---|
| Note reference | Non-identifying note ID and processing metadata |
| Entity | Category, extracted text/normalized value, and relevant attributes |
| Status | Current/present, absent/negated, uncertain, historical, or another status defined by the approved annotation schema |
| Evidence | Exact supporting text and start/end character offsets mapped to the original note |
| ICD-10 candidates | Ranked diagnosis-code candidates, descriptions, retrieval scores, and match/abstention decision |
| Verification | Evidence-support result, offset validation, status/contradiction checks, missed-item findings, and reasons |
| Decision | Accepted, rejected, abstain/no-confident-match, or reviewer-required state |
| Trace reference | Links the output to privacy-safe process records without exposing protected information |

The schema must distinguish a model-proposed item from a verified and accepted item. Schema validity alone does not establish clinical correctness.

## 5. Proposed Processing Flow

1. **Input validation:** Accept a note supplied through the local workflow and validate the request.
2. **Preserve the source:** Keep the original note immutable for span validation and reviewer highlighting.
3. **Local privacy processing:** Detect and mask identifying information before any external model call. Maintain an explicit offset mapping between the masked text and original text.
4. **Extraction pass:** Ask the primary model for structured diagnoses, medications, procedures, allergies, and vital signs, with evidence spans and stated status.
5. **Schema and span checks:** Validate the response structure and reject malformed offsets or spans that cannot be mapped back to the original note.
6. **ICD-10 candidate lookup:** For diagnoses, search the supplied ICD-10 code table through keyword and semantic retrieval, then return ranked candidates. This tool does not assign procedure codes.
7. **Independent verification:** A separate pass receives the note and proposed extracted items, but not the extractor's hidden reasoning. It checks evidence support, offsets, status, contradictions, and likely missed items.
8. **Agent reconciliation:** The orchestrator examines tool results and decides whether to accept, reject, abstain, retry a recoverable failure, or require human review.
9. **Safe output and trace:** Produce structured output and privacy-safe traces. Do not include raw protected information in trace records.
10. **Review and export:** Present evidence and decisions in the local reviewer interface and allow JSON export.
11. **Evaluation:** Run the baseline, main evaluation, and required challenge tests through a repeatable harness.

## 6. Evidence-Gated Acceptance and Decision Rules

- **Accept:** An item has a valid span in the original note, the span supports the item's meaning, required attributes/status pass checks, and verification requirements are satisfied.
- **Reject:** The item is unsupported, fabricated, mapped to an invalid span, or contradicted by the source in a way that invalidates the proposed claim.
- **Abstain / no confident match:** The evidence or supplied ICD-10 table does not support a sufficiently reliable coding candidate.
- **Retry:** A recoverable schema, tool, or verification failure may be retried only within the configured budget. Retrying does not make a result valid automatically.
- **Item-level human review:** Conflicting, ambiguous, or unresolved items are flagged with reasons.
- **Whole-note escalation:** Escalate the note when the disagreement rate is high, the note is outside the approved domain, or an unresolved failure makes safe processing unreliable.

A note may contain both verified items and items requiring review. Do not require the whole note to be rejected merely because one entity is unresolved. Conversely, a note-level escalation must not be hidden by accepting other outputs without recording the escalation.

## 7. Explicit Agent Loop

The design must be an agent loop rather than only a fixed pipeline.

The orchestrator:
1. Determines the next required tool or processing pass.
2. Invokes extraction, ICD-10 retrieval, verification, or validation tools.
3. Examines tool outcomes and verification results.
4. Applies evidence gates and disagreement rules.
5. Retries recoverable failures only while retry and time/call budgets remain.
6. Stops on a safe final decision, abstention, or human-review escalation.
7. Records each tool/model call and decision in the privacy-safe trace.

Retry limits, note-level escalation thresholds, and model-call budgets must be configured and documented. They must not be tuned in a way that hides failures or bypasses evidence validation.

## 8. Human-in-the-Loop Reviewer Interface

The local reviewer interface should provide:

- Original note display with accepted evidence highlighted at mapped source offsets.
- A structured table of extracted entities and relevant attributes.
- Ranked ICD-10 candidates for diagnosis items.
- Item-level accept and reject controls.
- Flagged-items panel showing reasons for unsupported evidence, contradictions, uncertainty, or unresolved verification.
- Trace viewer displaying the process, tool calls, retry decisions, and outcomes without protected information.
- Structured JSON export of reviewed results.

The MVP is local and intended for one reviewer. Multi-user collaboration and cloud deployment are outside the current scope.

## 9. Privacy, Security, and Reliability

- Use only the de-identified clinical transcriptions and ICD-10 table supplied by Mirai Labs.
- Do not source external clinical notes or commit clinical datasets/patient records to the repository.
- Keep raw note handling and PHI detection/masking local.
- Do not send note text to an external model until provider data-use terms and project approval permit the proposed processing.
- Treat note content as untrusted data. Embedded instructions must not change system rules or tool permissions.
- Do not display or persist protected information in logs/traces; use masked payloads or safe metadata.
- Preserve original-text offset mapping through masking/normalization and validate spans against the original note.
- Handle API rate limits and outages gracefully. Flag or defer work rather than fabricating output or switching to an unapproved provider.
- Apply bounded retries and a per-note time/call budget.

## 10. Evaluation Approach

Evaluate the proposed solution against the requirements and thresholds in `docs/evaluation-plan.md`.

The plan includes:
- A gold standard of at least 100 manually labelled notes across at least 10 specialties, prepared before prompt tuning.
- A naive single-prompt baseline on the same agreed evaluation notes.
- Entity-level precision, recall, and F1 for diagnoses, medications, and procedures.
- Programmatic span-faithfulness and offset checks, plus sampled manual review.
- ICD-10 top-1/top-3 performance and correct no-confident-match behaviour.
- At least 20 modified contradiction notes, at least 10 rare-diagnosis notes, and at least 10 adversarial notes.
- Abstention/flagging precision and recall, latency, model calls per note, quota/usage reporting, and analysis of at least three poor-performing cases.

Acceptance thresholds must be reported as pass, fail, or not yet measured. This proposal does not assert that the model or system has achieved any performance target.

## 11. Scope Boundaries

### Included in the MVP
- English free-text clinical notes from Mirai Labs.
- Extraction of diagnoses, medications, procedures, allergies, and vital signs/key measurements.
- Evidence spans and offsets referring to the original note.
- ICD-10 diagnosis candidate lookup against the supplied table.
- Independent verification, bounded agent loop, reconciliation, abstention, and escalation.
- Local reviewer interface, privacy-safe trace viewing, and JSON export.
- Gold-standard annotation and repeatable evaluation.

### Explicitly excluded by the SOW
- Procedure-code assignment.
- EHR or billing integration.
- OCR or scanned/handwritten note processing.
- Cloud deployment and multi-user support.
- Model fine-tuning.
- External clinical data sourcing.
- Paid API keys and GPU-dependent infrastructure.

### Possible future phase — options for discussion only

The following items remain outside the current SOW/MVP and must not be implemented without written approval from Mirai Labs:

- **OCR/document ingestion:** Support printed or scanned clinical PDFs/images; treat handwriting as a separate feasibility question. OCR would require recognition-quality checks, page/region provenance and human review for uncertain results.
- **Input-quality checks:** Detect empty, truncated, duplicate or garbled notes before extraction.
- **Review prioritization:** Sort unresolved items by calibrated uncertainty or contradiction risk; confidence must not replace evidence verification.
- **Reviewer feedback and error analytics:** Record privacy-safe corrections and recurring error categories to guide a later improvement cycle, while keeping the final evaluation set independent.
- **Resumable batch processing:** Track note-level progress, failures and quota use so an interrupted approved batch can safely resume.

OCR is the main optional expansion to consider. If approved later, the schema may need page numbers and bounding boxes in addition to text offsets, and OCR accuracy must be evaluated separately. These options do not change the current exclusion of OCR, scanned/handwritten notes or other out-of-scope features.

Any scope change must receive written agreement from Mirai Labs.

## 12. Decisions Pending Approval

The following remain provisional and must be resolved before implementation:
1. Final model/provider choice based on current availability, free-tier limits, privacy/data-use terms, and evaluation.
2. Extraction and verification schema details.
3. Keyword retrieval implementation and embedding model.
4. PHI masking rules and original-to-masked offset mapping strategy.
5. Retry/call budget and note-level escalation threshold.
6. Annotation guidelines and any adjudication procedure.
7. Processing volume expectations for the approximately 5,000 supplied notes versus the evaluation subset.

Technology candidates and decisions are detailed in `docs/technology-stack.md`. Component responsibilities and the logical data flow are detailed in `docs/architecture.md`.

## 13. Approval Status

This document is a solution proposal for review, not implementation authorization. No feature work or model calls using project clinical notes should begin before formal architecture/technology approval and confirmation that the data-handling arrangement is acceptable.
