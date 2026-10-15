# Architecture Proposal (Draft — Not Yet Approved)

**Project:** AI-Powered Clinical Note Extraction and Coding Agent MVP  
**Status:** Proposed for review on 16 October 2026  
**Constraint:** No feature implementation before formal Mirai Labs approval.

## 1. Purpose

This document describes the proposed logical architecture for a local MVP that extracts clinical information from free-text notes, links each extracted item to evidence in the original note, suggests ICD-10 diagnosis candidates, verifies results independently, and routes uncertain items for human review.

## 2. Proposed Components

| Component | Responsibility |
|---|---|
| Input handler | Accept note text and validate required input fields. |
| Local privacy layer | Detect and mask identifying information before any external model call. |
| Text and offset manager | Preserve the original note and maintain a reliable mapping between original and masked text offsets. |
| Agent orchestrator | Decide which tool/pass to call, manage retry limits, and handle disagreements. |
| Extraction pass | Extract diagnoses, procedures, medications, allergies, and key vital signs in a strict schema. |
| ICD-10 retrieval tool | Retrieve and rank candidate diagnosis codes from the supplied ICD-10 table using keyword and semantic search. |
| Independent verification pass | Check evidence support, original-text spans, item status, contradictions, and likely omissions without receiving extractor reasoning. |
| Reconciliation and decision logic | Accept only items that satisfy the agreed evidence and verification gates; reject unsupported items or flag unresolved ones. |
| Trace logger | Record masked model/tool activity, decisions, retries, and outcomes without exposing protected information. |
| Local reviewer interface | Display evidence, flagged items, ICD-10 candidates, accept/reject controls, trace, and JSON export. |
| Evaluation harness | Measure performance against a manually labelled gold standard and a naive single-prompt baseline. |

## 3. Plain-Text Architecture Diagram

```text
                 +--------------------------+
                 |    Clinical Note Text    |
                 +-------------+------------+
                               |
                               v
                 +--------------------------+
                 | Validate Input           |
                 | Keep Original Note        |
                 | Mask Identifying Data     |
                 | Preserve Offset Mapping   |
                 +-------------+------------+
                               |
                               v
                 +--------------------------+
                 |     Agent Orchestrator   |
                 | Plans Calls and Retries  |
                 +-------------+------------+
                               |
                               v
                 +--------------------------+
                 | 1. Extraction Pass        |
                 | Structured Clinical Items |
                 +-------------+------------+
                               |
                               v
                 +--------------------------+
                 | 2. ICD-10 Candidate Tool  |
                 | Keyword + Semantic Search |
                 +-------------+------------+
                               |
                               v
                 +--------------------------+
                 | 3. Independent Verifier   |
                 | Evidence, Status, Span,   |
                 | Contradictions, Omissions |
                 +-------------+------------+
                               |
                               v
                    +--------------------+
                    | Verification Gates |
                    | Passed for Item?   |
                    +---------+----------+
                              |
                   +----------+----------+
                   |                     |
                  YES                    NO
                   |                     |
                   v                     v
        +----------------------+  +----------------------+
        | Verified Item / JSON  |  | Recoverable Failure? |
        +----------+-----------+  +----------+-----------+
                   |                         |
                   |                 +-------+-------+
                   |                 |               |
                   |                YES              NO
                   |                 |               |
                   |                 v               v
                   |        +----------------+ +------------------+
                   |        | Retry via      | | Flag for Human   |
                   |        | Orchestrator   | | Review           |
                   |        +-------+--------+ +--------+---------+
                   |                |                   |
                   |                +--> Orchestrator   |
                   |                                    |
                   +------------------+-----------------+
                                      |
                                      v
                         +--------------------------+
                         | Local Streamlit Reviewer |
                         | Evidence / Accept-Reject |
                         | Flags / Trace / JSON     |
                         +-------------+------------+
                                       |
                                       v
                         +--------------------------+
                         | Evaluation Harness       |
                         | Gold Standard + Baseline |
                         | Metrics / Latency / Cost |
                         +--------------------------+

    Supporting trace: masked model calls, tool calls, retries,
    decisions, and outcomes are recorded separately.
```

**Diagram note:** Review is item-level where possible. A note may contain verified items and other items requiring review. If note-level disagreement or out-of-domain risk exceeds an approved threshold, escalate the whole note.

## 4. One-Note Data Flow

1. Read the note locally and validate the input.
2. Keep the original text immutable for evidence and offset validation.
3. Detect and mask identifying information locally before sending any text to an external model.
4. Maintain an explicit mapping between masked-text positions and the original note. Normalization or masking must not silently shift offsets.
5. The extraction pass returns strict-schema entities and evidence spans.
6. The ICD-10 tool retrieves diagnosis-code candidates from the SOW-provided code table. Procedure coding is out of scope.
7. The independent verifier receives the note and proposed entities, but not the extraction model's hidden reasoning. It checks source support, span correctness, status, contradictions, and possible omissions.
8. The orchestrator reconciles results. It may retry recoverable failures only within a configured budget.
9. Accept an item only when its evidence and verification requirements pass. Reject unsupported output; route unresolved disagreements and low-confidence results to human review.
10. Present items and evidence in the local reviewer interface, record a privacy-safe trace, and permit JSON export.
11. Run the evaluation harness separately against the gold-standard labels and naive baseline.

## 5. Trust Boundaries and Safety

- **Raw-note boundary:** Raw note text remains local. Access and retention must follow Mirai Labs' policy.
- **External model boundary:** Send only appropriately masked text after provider policy approval. Masking does not by itself guarantee compliance.
- **Untrusted note content:** Treat clinical note text as data, not instructions. Ignore embedded attempts to change system behaviour.
- **Evidence gate:** Every accepted entity must be supported by a valid span in the original note. One fabricated accepted item violates the SOW's span-faithfulness target.
- **Privacy-safe trace:** Do not display or persist raw protected information in traces. Log masked payloads or safe metadata only.
- **Human oversight:** Preserve reviewer ability to accept/reject items and see why an item was flagged.
- **Abstention:** Use the SOW-required no-confident-match outcome when ICD-10 evidence is inadequate.

## 6. Agent Loop and Recovery

The design is an agent loop, not merely a fixed pipeline. The orchestrator selects and invokes tools, evaluates the results, and decides whether a bounded retry is appropriate.

A retry must have a stated reason and must consume the retry budget. A retry does not automatically make an item valid. When the budget is exhausted, a disagreement remains unresolved, or the note is outside the approved domain, flag the item or escalate the whole note as appropriate.

## 7. Key Architecture Risks

| Risk | Planned control or validation |
|---|---|
| Offset drift after masking/normalization | Preserve original text and test explicit offset mapping. |
| Model free-tier quota or outage | Record limits; handle failure gracefully and queue/flag instead of fabricating. |
| Shared extractor/verifier errors | Prefer distinct models where feasible and evaluate verifier errors empirically. |
| PHI leakage in logs | Restrict traces to masked payloads and safe metadata. |
| Poor or rare ICD-10 match | Rank candidates, measure top-1/top-3, and support no-confident-match. |
| Too many retries or long latency | Configure a per-note call/time budget and record it. |
| Annotation schedule risk | Begin the gold set early; report capacity constraints rather than silently reducing the SOW target. |

## 8. Scope Boundaries

Included: English text notes supplied by Mirai Labs, structured entity extraction, original-text evidence, ICD-10 diagnosis candidates, independent verification, bounded agent loop, local review UI, tracing, JSON export, and evaluation.

Excluded by the SOW: OCR or scanned/handwritten notes, procedure-code assignment, EHR/billing integration, cloud or multi-user deployment, model fine-tuning, external clinical-note sourcing, paid API keys, and GPU-dependent infrastructure.

## 9. Approval Status

This is a proposed logical architecture, not an approved implementation design. Final provider/model choice, retrieval implementation, masking rules, retry thresholds, and storage details require compatibility/privacy checks and Mirai Labs approval before implementation.
