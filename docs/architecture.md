# Architecture Proposal (Draft — Pending Mirai Labs Approval)

**Project:** AI-Powered Clinical Note Extraction and Coding Agent MVP  
**Status:** Proposed logical architecture; implementation requires formal approval.  
**Target:** Localhost MVP, one reviewer, English text notes, free-tier services only.

## 1. Architecture Objective

The architecture describes how a note moves through input validation, local privacy processing, structured extraction, ICD-10 candidate retrieval, independent verification, reconciliation, reviewer approval, and evaluation.

The original clinical note is the source of truth for evidence. An item must not be accepted merely because it is well-formed JSON or has a plausible diagnosis-code candidate.

## 2. Proposed Components and Responsibilities

| Component | Responsibility |
|---|---|
| Input handler | Accept clinical note text and validate the input. |
| Local privacy layer | Detect and mask identifying information before any external model call. |
| Original-text and offset manager | Keep the original note unchanged and map positions in masked text back to the original note. |
| Agent orchestrator | Choose the next tool/pass, inspect outcomes, manage the retry budget, and decide whether to accept, retry, abstain, or escalate. |
| Extraction pass | Produce structured diagnoses, medications, procedures, allergies, and vital signs with supporting evidence and stated status. |
| ICD-10 retrieval tool | Search the supplied ICD-10 table using keyword and semantic retrieval and return ranked diagnosis candidates. |
| Independent verification pass | Check source support, offsets, status, contradictions, and likely missed items without receiving the extractor's hidden reasoning. |
| Reconciliation and decision logic | Apply evidence gates, reconcile disagreements, reject unsupported items, and flag unresolved cases. |
| Privacy-safe trace | Record masked model/tool activity, retries, decisions, and results without exposing protected information. |
| Local reviewer interface | Show evidence, extracted fields, ICD-10 candidates, flagged items, trace, accept/reject controls, and JSON export. |
| Evaluation harness | Compare the agent with the naive baseline and calculate SOW metrics and challenge-test results. |

## 3. Plain-Text Logical Architecture

```text
 +--------------------------+
 |    Clinical Note Text    |
 +------------+-------------+
              |
              v
 +--------------------------+
 | Validate Input            |
 | Keep Original Note        |
 | Mask Identifying Data     |
 | Preserve Offset Mapping   |
 +------------+-------------+
              |
              v
 +--------------------------+
 |     Agent Orchestrator    |
 | Controls Tools and Retries|
 +------------+-------------+
              |
              v
 +--------------------------+
 | 1. Extraction Pass        |
 | Structured Clinical Items |
 +------------+-------------+
              |
              v
 +--------------------------+
 | 2. ICD-10 Lookup Tool     |
 | Keyword + Semantic Search |
 | Diagnosis Candidates     |
 +------------+-------------+
              |
              v
 +--------------------------+
 | 3. Independent Verifier   |
 | Evidence, Offsets, Status |
 | Contradictions, Omissions |
 +------------+-------------+
              |
              v
      +-------------------+
      | Verification      |
      | Successful?       |
      +---------+---------+
                |
        +-------+-------+
        |               |
       YES              NO
        |               |
        v               v
 +----------------+  +-------------------+
 | Verified Items |  | Recoverable issue?|
 | Structured JSON|  +---------+---------+
 +-------+--------+            |
         |                 +---+---+
         |                 |       |
         |                YES      NO
         |                 |       |
         |                 v       v
         |           +----------+ +----------------+
         |           | Retry via| | Flag for Human |
         |           |Orchestr. | | Review         |
         |           +----+-----+ +-------+--------+
         |                |               |
         |                +--> Orchestr.  |
         |                                |
         +----------------+---------------+
                          |
                          v
              +--------------------------+
              | Local Reviewer Interface |
              | Evidence / Accept-Reject |
              | Flags / Trace / JSON     |
              +-------------+------------+
                            |
                            v
              +--------------------------+
              | Evaluation Harness       |
              | Gold Standard + Baseline |
              | Metrics / Latency / Calls|
              +--------------------------+

 Supporting component across the workflow:
 Privacy-safe Trace records tool calls, masked inputs/outputs,
 verification outcomes, retries, and decision reasons.
```

**Reading the diagram:** If a problem may be recoverable, the orchestrator can retry within its limit. If a disagreement remains unresolved, the relevant item is flagged for human review. A single note may contain verified items as well as items requiring review. A note-level escalation is required when the note is out of scope or overall disagreement exceeds the approved threshold.

## 4. One-Note Data Flow

1. **Receive input:** Accept an English clinical note through the local application.
2. **Preserve original text:** Store the original note for source-span validation and reviewer highlighting. Do not replace it with normalized or masked text.
3. **Mask locally:** Detect and mask identifying information before any external model call. Keep a mapping from the model-bound masked text to original character offsets.
4. **Extract:** The extraction model returns structured entities, relevant attributes/status, and evidence spans.
5. **Validate structure and spans:** Validate the schema and ensure every proposed span maps to a valid location in the original note.
6. **Retrieve code candidates:** For diagnosis items, search the supplied ICD-10 table through keyword and semantic retrieval. Return ranked candidates or a no-confident-match result when evidence is insufficient. Procedure-code assignment is out of scope.
7. **Verify independently:** A second model pass receives the note and proposed extracted items, but not the extraction model's hidden reasoning. It checks evidence support, span validity, status, contradictions, and likely omissions.
8. **Reconcile:** The orchestrator interprets tool outputs and decides whether an item is accepted, rejected, retried, abstained, or flagged for review.
9. **Record a safe trace:** Record tool calls and decisions using masked payloads or safe metadata only.
10. **Review and export:** Display the output and evidence in the reviewer interface; allow item-level accept/reject and JSON export.
11. **Evaluate:** Run the repeatable evaluation harness against the gold-standard labels, naive baseline, and required challenge sets.

## 5. Evidence, Offsets, and Acceptance Rules

- **Original note is authoritative:** Evidence highlighting and span validation use offsets mapped back to the original note.
- **Masking must preserve mapping:** If a mask or preprocessing step changes text length, offsets must not be reused without a verified mapping.
- **Evidence must support meaning:** A phrase may exist in the note but still not support the entity interpretation. Text presence alone is insufficient.
- **Schema validation is necessary, not sufficient:** Valid JSON does not prove clinical correctness.
- **Accepted item:** Must pass structure, offset, evidence-support, required status, and verification gates.
- **Rejected item:** Used for unsupported, fabricated, incorrectly mapped, or contradicted output.
- **Abstention:** Use the no-confident-match outcome when no sufficiently supported diagnosis-code candidate is available.
- **Human review:** Flag ambiguity, unresolved verifier disagreement, and items that cannot safely be accepted automatically.
- **Whole-note escalation:** Flag the note when it is outside the approved domain or crosses the agreed note-level disagreement/failure threshold.

## 6. Agent Loop and Recovery

The orchestrator implements a real control loop; the application is not only a fixed sequence of calls.

1. Determine which processing pass or tool is needed next.
2. Invoke extraction, retrieval, verification, or deterministic validation.
3. Inspect the outcome and any error/verification reason.
4. Retry a recoverable failure only if the retry and time/call budgets allow it.
5. Re-evaluate the result after each retry; never assume a retry succeeded.
6. Accept only items that pass the agreed evidence and verification rules.
7. Otherwise reject, abstain, or escalate for human review.
8. Record the tool call, retry reason, decision, and outcome in the privacy-safe trace.

Retry limits, time/call budgets, and the note-level escalation threshold must be documented and evaluated. They must not be used to hide failures.

## 7. Trust Boundaries and Safety Controls

| Boundary / risk | Required control |
|---|---|
| Raw note and protected information | Keep raw-note processing local; follow Mirai Labs' data-handling rules. |
| External model provider | Send only appropriately masked text after the provider terms and use have been approved. Masking alone does not prove compliance. |
| Instructions embedded in the note | Treat note content as untrusted data; it must not override system instructions or change tool permissions. |
| Trace/log exposure | Never display or persist protected information in traces. Store masked payloads or safe metadata only. |
| Unsupported extraction | Require valid source evidence and independent verification before automatic acceptance. |
| Weak ICD-10 match | Return ranked candidates and allow no-confident-match instead of forcing a code. |
| Provider outage or rate limit | Fail safely, preserve safe local state, and flag/defer processing rather than fabricate output or switch to an unapproved provider. |

## 8. Reviewer Interface

The local reviewer interface must support:

- Original note display.
- Highlighting of evidence at mapped source offsets.
- A structured table of extracted entities, attributes, status, and ICD-10 candidates.
- Item-level accept/reject controls.
- A flagged-items panel with reasons.
- A trace viewer with process steps, tool calls, retries, and decisions, without protected information.
- JSON export of reviewed results.

The MVP is intended for a single local reviewer. Cloud deployment, multi-user collaboration, and EHR/billing integration are excluded by the SOW.

## 9. Evaluation Boundary

The evaluation harness is separate from runtime decision-making. It measures performance against manually labelled data and the naive single-prompt baseline.

The SOW-aligned plan is recorded in `docs/evaluation-plan.md` and includes:
- At least 100 manually labelled notes across at least 10 specialties, labelled before prompt tuning.
- Entity-level precision, recall, and F1 for diagnoses, medications, and procedures.
- Programmatic original-span faithfulness checks with sampled manual review.
- ICD-10 top-1/top-3 measures and rare-diagnosis no-confident-match performance.
- At least 20 modified contradiction notes, at least 10 rare-diagnosis notes, and at least 10 adversarial notes.
- Abstention/flagging precision and recall, latency, model calls per note, and analysis of at least three poor-performing cases.

These are evaluation requirements, not measured results.

## 10. Architecture Risks to Validate

- Compatibility of the selected model/API and availability of its free-tier quota.
- Whether provider data-use and retention terms are approved for the project.
- Offset mapping correctness after masking and preprocessing.
- Verifier performance on contradictions, status errors, and missed entities.
- Retrieval quality, particularly for rare or absent ICD-10 entries.
- Whether the required annotation and evaluation work can be completed within the available schedule.
- Whether the under-30-second median latency target is met under the measured setup.

## 11. Scope Boundaries

**Included:** English text notes from Mirai Labs, entity extraction, source evidence/offsets, ICD-10 diagnosis candidates, independent verification, an explicit agent loop, privacy-safe tracing, local review, JSON export, and evaluation.

**Excluded by the SOW:** OCR or scanned/handwritten notes, procedure-code assignment, EHR/billing integration, cloud or multi-user deployment, model fine-tuning, external clinical-note sourcing, paid API keys, and GPU-dependent infrastructure.

## 12. Approval Status

This is the proposed logical architecture and does not authorize implementation. Final provider/model choice, retrieval implementation, masking rules, retry limits, and other pending decisions require verification and formal Mirai Labs approval before feature work or model calls using project clinical notes begin.
