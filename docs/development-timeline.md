# Development Timeline (SOW-Aligned Plan)

**Project:** AI-Powered Clinical Note Extraction and Coding Agent MVP  
**Project window:** 13–26 October 2026  
**Status:** Proposed schedule; implementation tasks require formal approval.

## 1. Fixed Milestones and Approval Gate

| Date | Milestone / deliverable | Constraint |
|---|---|---|
| Tue, 13 Oct 2026 | Review the SOW, identify scope and constraints, prepare clarification questions, begin market research | Planning and research only |
| Tue, 13–Wed, 14 Oct 2026 | Review commercial products, open-source tools, research papers, and relevant methods | Record sources and distinguish documented facts from assumptions |
| Wed, 14 Oct 2026 | Research presentation | Present findings and gaps relevant to the proposed MVP |
| Thu, 15 Oct 2026, by 6:00 PM | Submit solution proposal, architecture, technology-stack rationale, and detailed timeline | Documents must clearly label unapproved choices |
| Fri, 16 Oct 2026 | Architecture and technology review / formal approval gate | Do not begin feature implementation until approval is received |

## 2. Post-Approval Execution Plan

Implementation activities start only after formal approval. The available post-approval build window is six working days: 19, 20, 21, 22, 23, and 26 October.

| Date | Planned work and deliverable | Verification / risk control |
|---|---|---|
| Fri, 16 Oct | Record approval decisions, settle permitted provider and data-handling requirements, confirm processing volume and scope | No implementation before approval; unresolved privacy or provider decisions remain blocking issues |
| Mon, 19 Oct | Inspect the provided dataset and ICD-10 table; finalize annotation guidelines and sampling plan; begin gold-standard labelling; define the naive single-prompt baseline | Gold-standard labelling must begin before prompt tuning. Confirm access to the required data and specialty coverage |
| Tue, 20 Oct | Continue gold-standard labelling toward at least 100 notes across at least 10 specialties; define and test the output schema and original-text offset rules; create the evaluation harness skeleton | Track annotation throughput and disagreements. Do not tune prompts against examples intended to remain an independent final test set |
| Wed, 21 Oct | Implement approved local input handling and PHI masking; implement the structured extraction pass and schema validation | Test masked-to-original offset mapping and reject outputs with invalid or unsupported evidence |
| Thu, 22 Oct | Implement ICD-10 keyword and semantic candidate retrieval; add ranked candidates and the no-confident-match outcome; run initial retrieval checks | Confirm the supplied code table is the retrieval source. Monitor API quotas and avoid unsupported code claims |
| Fri, 23 Oct | Implement independent verification, bounded retries, reconciliation, abstention/escalation, and privacy-safe structured tracing; begin integrating reviewer controls | Test contradictions, missed entities, retry-limit behaviour, and note-embedded instructions |
| Mon, 26 Oct | Complete reviewer UI and JSON export; finish integration; run evaluation and required challenge sets where labelled data is ready; report metrics and at least three poor-performing cases; finalize README, user guide, demo video (5–8 minutes), and final defense materials | Report every target as pass, fail, or not yet measured. Document any incomplete test, quota failure, or unresolved limitation rather than implying completion |

## 3. Required Evaluation Work

The following activities must be included in the plan and final evaluation report:

- Gold standard: at least 100 manually labelled notes from at least 10 specialties, labelled before prompt tuning.
- Baseline: compare the proposed agent with a naive single-prompt baseline on the same agreed evaluation notes.
- Entity metrics: precision, recall, and F1 for diagnoses, medications, and procedures.
- Evidence: programmatic original-span/offset checks with sampled manual review.
- ICD-10: top-1 and top-3 metrics and correct no-confident-match behaviour for rare diagnoses.
- Challenge data: at least 20 modified contradiction notes, at least 10 rare-diagnosis notes, and at least 10 adversarial notes containing embedded instructions and/or protected information.
- Operations: median end-to-end latency, model calls per note, and cost/quota observations.
- Error review: describe at least three poor-performing cases and likely causes.

The SOW's acceptance thresholds are documented in `docs/evaluation-plan.md`. This schedule does not assert that any target has already been met.

## 4. Capacity, Dependencies, and Contingencies

The six-day implementation window is tight given the required labelling, multi-pass agent, reviewer interface, evaluation, and final demo. The schedule depends on timely access to the supplied data, ICD-10 table, and approved model/API.

- Start labelling immediately after approval and before prompt tuning.
- Track the number of labelled notes and specialty coverage daily.
- If annotation throughput, API quotas, or privacy approval threatens a required deliverable, raise the constraint with Mirai Labs promptly.
- Do not silently reduce the minimum gold-standard or challenge-set sizes, remove evaluation requirements, or switch to an unapproved provider.
- If any SOW target cannot be measured by 26 October, record the exact limitation and mark it **Not yet measured** rather than claiming success.
- Use only Mirai Labs-provided clinical notes; do not source external clinical notes.

## 5. Scope Boundaries

The plan excludes OCR/scanned or handwritten notes, procedure-code assignment, EHR or billing integration, cloud or multi-user deployment, model fine-tuning, paid API keys, and GPU-dependent infrastructure, consistent with the SOW.

## 6. Approval Status

This timeline is a planning baseline, not permission to begin implementation. Feature work starts only after formal Mirai Labs approval. Final model, provider, and retrieval decisions must satisfy the approved privacy, free-tier, and compatibility requirements.
