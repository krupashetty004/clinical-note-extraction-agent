# Confirmed Requirements (from SOW)

## 1) Functional Requirements (Confirmed)

| ID | Requirement | Confirmation Status |
|---|---|---|
| FR-01 | Read free-text clinical notes. | Confirmed |
| FR-02 | Extract diagnoses, procedures, medications, allergies, and key vitals. | Confirmed |
| FR-03 | Record exact supporting source spans with character offsets. | Confirmed |
| FR-04 | Use strict structured schema (Pydantic suggested). | Confirmed |
| FR-05 | Provide ICD-10 diagnosis-code candidates via keyword + semantic retrieval. | Confirmed |
| FR-06 | Return `no_confident_match` when appropriate. | Confirmed |
| FR-07 | Run independent verification pass for source support, status, contradictions, and missed items. | Confirmed |
| FR-08 | Use agent loop with tool calls, bounded retries, reconciliation, and abstention. | Confirmed |
| FR-09 | Require supporting evidence before accepting any item. | Confirmed |
| FR-10 | Keep structured traces of model/tool calls and decisions. | Confirmed |
| FR-11 | Provide local reviewer UI with highlighted evidence, accept/reject controls, flagged items, trace viewing, JSON export. | Confirmed |

## 2) Security, Privacy, and Safety Requirements (Confirmed)

| ID | Requirement | Confirmation Status |
|---|---|---|
| SP-01 | Mask protected information locally before sending note text to external models. | Confirmed |
| SP-02 | Treat note content as untrusted; ignore instructions embedded in notes. | Confirmed |
| SP-03 | Keep repository private; treat all project materials as confidential. | Confirmed |
| SP-04 | Do not commit confidential SOW or clinical datasets. | Confirmed |
| SP-05 | Use only Mirai Labs-provided clinical data; do not source external clinical notes. | Confirmed |

## 3) Evaluation and Data Requirements (Confirmed)

| ID | Requirement | Confirmation Status |
|---|---|---|
| EV-01 | Build manually labelled gold standard: at least 100 notes from at least 10 specialties. | Confirmed |
| EV-02 | Include naive single-prompt baseline. | Confirmed |
| EV-03 | Measure entity-level precision/recall/F1. | Confirmed |
| EV-04 | Measure span-faithfulness checks. | Confirmed |
| EV-05 | Measure ICD-10 top-1/top-3 accuracy. | Confirmed |
| EV-06 | Perform abstention analysis. | Confirmed |
| EV-07 | Run contradiction tests, rare-diagnosis tests, adversarial tests. | Confirmed |
| EV-08 | Measure latency and cost. | Confirmed |
| EV-09 | Do not claim performance targets before measurement. | Confirmed |

## 4) Program Constraints (Confirmed)

| ID | Constraint | Confirmation Status |
|---|---|---|
| PC-01 | Planning/research phase only until formal approval. | Confirmed |
| PC-02 | Free-tier services only; no paid API keys/GPU provided. | Confirmed |
| PC-03 | Final model/provider selection must account for actual availability and approval. | Confirmed |

## 5) Milestones (Confirmed)

| Date | Milestone |
|---|---|
| 13 Oct 2026 | Requirements review, clarifications, repository setup, market research |
| 14 Oct 2026 (~4 PM) | Market research presentation |
| 15 Oct 2026 (by 6 PM) | Solution proposal, architecture, stack justification, timeline |
| 16 Oct 2026 | Architecture review and formal approval gate |
| Through 26 Oct 2026 | Build, testing, evaluation, docs, demo, final defense |

## 6) Explicit Non-Goals for Current Phase

- No application implementation.
- No API integration work.
- No dependency-install planning that assumes paid tiers.
- No claim of benchmark/performance achievement.
