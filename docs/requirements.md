# Confirmed Requirements (from Mirai Labs SOW)

**Project:** AI-Powered Clinical Note Extraction and Coding Agent MVP  
**Source:** Statement of Work, version 1.0, 13 October 2026  
**Status:** Requirements transcription for planning; design decisions remain pending approval.

## 1. Functional Requirements

| ID | Requirement | Status |
|---|---|---|
| FR-01 | Accept English free-text clinical notes from the dataset supplied by Mirai Labs. | Confirmed |
| FR-02 | Extract diagnoses, procedures, medications, allergies, and key vital signs/measurements. | Confirmed |
| FR-03 | Capture supporting evidence and character offsets referring to the original note. | Confirmed |
| FR-04 | Return data using a strict structured schema; Pydantic is suggested by the SOW. | Confirmed |
| FR-05 | For diagnoses, retrieve and rank ICD-10 candidates from the supplied code table using keyword and semantic search. | Confirmed |
| FR-06 | Return a no-confident-match outcome when the supplied table/evidence does not support a reliable candidate. | Confirmed |
| FR-07 | Perform a separate verification pass checking evidence support, original offsets, status, contradictions, and likely missed items. | Confirmed |
| FR-08 | Implement a real agent loop with tool calls, bounded retries, reconciliation, abstention, and escalation—not only a fixed pipeline. | Confirmed |
| FR-09 | Accept an extracted item only when it passes the agreed evidence and verification gates. | Confirmed |
| FR-10 | Record model/tool calls, outcomes, retries, and decisions in structured traces without exposing protected information. | Confirmed |
| FR-11 | Provide a local reviewer interface with evidence highlighting, structured output, ICD-10 candidates, accept/reject controls, flagged-item reasons, trace viewing, and JSON export. | Confirmed |
| FR-12 | Support item-level human review and whole-note escalation when disagreement is high or the note is outside the approved domain. | Confirmed |
| FR-13 | Handle rate limits and model/tool failures safely; do not fabricate results or silently switch to unapproved providers. | Confirmed |
| FR-14 | Keep the original note as the source of truth for evidence highlighting, offset checks, and exported source spans. | Confirmed |

## 2. Data, Privacy, and Safety Requirements

| ID | Requirement | Status |
|---|---|---|
| SP-01 | Use the de-identified clinical transcription dataset and ICD-10 table provided by Mirai Labs; do not source external clinical notes. | Confirmed |
| SP-02 | Dataset described in the SOW contains approximately 5,000 transcriptions across about 40 specialties. | Confirmed |
| SP-03 | Mask identifying information locally before sending any note text to an external model. | Confirmed |
| SP-04 | Do not display or store protected information in traces/logs; record masked payloads or safe metadata only. | Confirmed |
| SP-05 | Treat note content as untrusted data and ignore instructions embedded within notes. | Confirmed |
| SP-06 | Preserve the original-note offset mapping across masking/normalization transformations. | Required design control |
| SP-07 | Keep the repository private and treat project materials as confidential. | Confirmed |
| SP-08 | Do not commit the confidential SOW, clinical datasets, or patient records to the repository. | Confirmed |
| SP-09 | External provider data-use and retention terms must be checked and acceptable to Mirai Labs before project notes are sent to the provider. | Approval dependency |
| SP-10 | The MVP is local/localhost, for one reviewer, and English text notes only. | Confirmed |

## 3. Gold-Standard and Evaluation Requirements

| ID | Requirement | SOW target |
|---|---|---|
| EV-01 | Manually labelled gold-standard dataset | At least 100 notes across at least 10 specialties |
| EV-02 | Gold standard includes diagnoses, medications, and procedures with spans/status, plus correct ICD-10 codes for diagnoses | Required |
| EV-03 | Create annotation guidelines | Required before prompt tuning |
| EV-04 | Compare against a naive single-prompt baseline on the same agreed evaluation notes | Required |
| EV-05 | Entity-level precision, recall, and F1 | Required for diagnoses, medications, and procedures |
| EV-06 | Diagnosis extraction F1 | At least 0.80 |
| EV-07 | Medication extraction F1 | At least 0.85 |
| EV-08 | Compare proposed agent with naive baseline | Proposed system must perform measurably better |
| EV-09 | Evidence/span faithfulness | 100% for accepted items; one fabricated accepted item fails this target |
| EV-10 | Status correctness | At least 90% for accepted diagnoses and medications |
| EV-11 | ICD-10 candidate retrieval | Top-3 accuracy at least 75%; report top-1 as well |
| EV-12 | Rare-diagnosis test | At least 10 notes; correct no-confident-match behaviour at least 80% |
| EV-13 | Contradiction test | At least 20 modified notes; at least 80% of contradictions flagged |
| EV-14 | Adversarial test | At least 10 notes with embedded instructions and/or protected information; 100% correct handling |
| EV-15 | Abstention/flagging quality | Report precision and recall and demonstrate flagged items are harder than accepted items |
| EV-16 | Operational evaluation | Median end-to-end latency under 30 seconds per note on the free-tier setup |
| EV-17 | Model usage | Report model calls per note, retries, and measured cost/quota observations |
| EV-18 | Error analysis | Identify and explain at least three poor-performing cases |
| EV-19 | Span validation method | Programmatic original-offset checks plus sampled manual review |
| EV-20 | Reporting integrity | Mark targets pass/fail/not yet measured; do not claim unmeasured performance |

All targets above are acceptance criteria from the SOW, not evidence of achieved performance.

## 4. Scope Boundaries

### In scope
- Extraction of diagnoses, procedures, medications, allergies, and vital signs/key measurements.
- Original-source evidence spans and offsets.
- ICD-10 diagnosis candidate retrieval only, using the supplied table.
- Independent verification, an explicit agent loop, bounded retries, reconciliation, abstention, and escalation.
- Local reviewer interface, structured traces, JSON export, and evaluation.
- Gold-standard labelling, baseline comparison, required challenge tests, latency and usage reporting.

### Explicitly excluded
- Procedure-code assignment.
- EHR or billing integration.
- OCR or scanned/handwritten note processing.
- Cloud deployment and multi-user functionality.
- Model fine-tuning.
- External clinical-note sourcing.
- Paid API keys and GPU-dependent infrastructure.

Any change to SOW scope requires written agreement from Mirai Labs.

## 5. Technical and Project Constraints

| ID | Constraint | Status |
|---|---|---|
| PC-01 | Free-tier services only; no paid API keys or GPU supplied. | Confirmed |
| PC-02 | Model examples in the SOW are references; alternatives may be researched and justified. | Confirmed by clarification |
| PC-03 | Provider/model selection must reflect current availability, free-tier limits, output capability, privacy/data-use terms, and evaluation. | Required |
| PC-04 | Exact dependency versions must be pinned only after compatibility checking. | Planning control |
| PC-05 | Local model inputs/outputs and traces must not expose protected information. | Confirmed |
| PC-06 | A one-command evaluation workflow and required project documentation must be delivered. | Confirmed |
| PC-07 | No feature implementation before formal architecture/technology-stack approval. | Confirmed |

## 6. Deliverables

The SOW calls for:
1. Architecture document with component responsibilities, diagram, one-note flow, technology justifications, extraction schema, verification approach, agent loop, rejected alternatives, and free-tier considerations.
2. Day-by-day development timeline.
3. Labelling guidelines and gold-standard dataset plan.
4. Evaluation report with metrics, required challenge tests, baseline comparison, cost/latency, and failure analysis.
5. README with one-command setup and evaluation instructions.
6. User guide.
7. A 5–8 minute demo video showing a clean note, contradiction, rare diagnosis, and evaluation results.
8. Private GitHub repository with daily commits.

## 7. Milestones

| Date | Milestone |
|---|---|
| 13 Oct 2026 | SOW review, clarification questions, initial market research |
| 14 Oct 2026 | Research presentation |
| 15 Oct 2026, by 6:00 PM | Solution proposal, architecture, technology-stack justification, and timeline |
| 16 Oct 2026 | Architecture review and formal approval gate |
| Through 26 Oct 2026 | Approved implementation, testing, evaluation, documentation, demo, and final defense |

## 8. Explicit Non-Goals Before Approval

- No feature implementation or project model calls using clinical notes.
- No claim that evaluation targets have been achieved before measurement.
- No unapproved provider use.
- No silent reduction of gold-standard or challenge-test sizes due to schedule or quota pressure.
