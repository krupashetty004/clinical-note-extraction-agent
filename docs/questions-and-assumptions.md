# Questions and Assumptions

## A) Open Questions (Need Mirai Labs Clarification)

| ID | Question | Why It Matters | Proposed Default Until Clarified |
|---|---|---|---|
| Q-01 | What exact PHI categories must be masked before external model calls? | Determines masking rules and false-positive risk. | Follow HIPAA Safe Harbor categories as conservative baseline (subject to approval). |
| Q-02 | Is any external LLM provider disallowed by policy/compliance? | Affects architecture and tool selection. | Keep provider/model final decision pending verification + approval. |
| Q-03 | What is the acceptable reviewer turnaround and workflow for human validation? | Affects UI behavior and batch sizing. | Assume asynchronous review queue with item-level accept/reject. |
| Q-04 | What ICD-10 reference source/version should be treated as canonical? | Ensures consistent code mapping. | Use publicly available ICD-10-CM references; finalize source by approval. |
| Q-05 | Should the system output uncertain entities to reviewer queue or suppress by default? | Impacts recall/safety tradeoff and abstention policy. | Route uncertain/flagged entities to reviewer queue. |
| Q-06 | Are there strict latency limits per note for MVP acceptance? | Drives model choice and retrieval depth. | Track latency; optimize after baseline measurement. |
| Q-07 | Is local deployment on a specific OS/hardware required for reviewer app demo? | Impacts packaging and runtime choices. | Assume cross-platform local execution (developer laptop). |
| Q-08 | Is annotation done by one reviewer or multiple (for adjudication)? | Affects gold-set quality and consistency process. | Assume single annotator + periodic spot-check until guidance received. |
| Q-09 | Are specialty distributions predefined for the 100-note dataset? | Affects sampling strategy and representativeness. | Aim for broad balance across ≥10 specialties. |
| Q-10 | What confidentiality controls are required for logs/traces at rest? | Affects logging detail and retention policy. | Keep local encrypted-at-rest recommendation pending policy details. |

## B) Assumptions (Planning-Only, Not Approved Decisions)

| ID | Assumption | Rationale | Risk if Wrong |
|---|---|---|---|
| A-01 | Reviewer UI can be local-only for MVP. | SOW explicitly asks for local reviewer interface. | May need server-hosted review workflow later. |
| A-02 | MVP can use free-tier model access where available. | Cost constraint disallows paid API/GPU. | Availability/rate limits may force fallback options. |
| A-03 | Character offsets are computed on normalized raw note text stored locally. | Needed for deterministic span validation. | Offset drift if preprocessing changes text. |
| A-04 | Verification pass is independent prompt/model pass (or deterministic checker) from extraction pass. | Reduces self-confirmation bias. | If coupled too tightly, contradiction detection may weaken. |
| A-05 | ICD-10 candidate generation can combine lexical retrieval + embedding similarity. | Matches SOW guidance (keyword + semantic retrieval). | Free-tier limits may reduce semantic retrieval quality. |

## C) Pending Decisions to Close by Approval Review (16 Oct 2026)

1. Final provider/model shortlist (availability verified at decision time).
2. Canonical ICD-10 source package/dataset and update method.
3. PHI masking rule set and acceptable residual-risk threshold.
4. Gold annotation protocol and acceptance criteria.
5. Target latency/cost envelope for MVP acceptance.
