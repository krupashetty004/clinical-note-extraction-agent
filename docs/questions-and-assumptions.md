# Questions and Assumptions

## A) Open Questions (Need Mirai Labs Clarification)

| ID | Question | Why It Matters | Proposed Default Until Clarified |
|---|---|---|---|
| Q-01 | What exact protected-health-information (PHI) categories must be masked before external model calls? | Determines masking rules and false-positive risk. | Use a conservative rule set for common identifiers, subject to Mirai Labs approval. |
| Q-02 | Is any external LLM provider disallowed by project policy or compliance requirements? | Affects architecture and technology selection. | Keep the provider/model decision pending verification and approval. |
| Q-03 | What is the expected workflow for human review? | Affects the reviewer interface and review-state handling. | Use item-level accept/reject controls and a flagged-items panel. |
| Q-04 | Which ICD-10 reference table/version supplied by Mirai Labs is canonical? | Ensures coding evaluation uses the intended reference data. | Use the supplied ICD-10 table and document its version/source if provided. |
| Q-05 | Should uncertain entities be shown to reviewers or suppressed by default? | Affects recall, abstention, and review workload. | Flag uncertain or unresolved items for review. |
| Q-06 | Are there latency limits beyond the SOW's median under-30-seconds-per-note target? | Influences model calls, retrieval depth, and retry budget. | Measure and report end-to-end latency against the SOW target. |
| Q-07 | Is a specific operating system or hardware configuration required for the local demo? | Affects environment setup and reproducibility. | Plan for local CPU execution; validate on the intended demo machine. |
| Q-08 | Will gold-standard labels be created by one annotator or reviewed by multiple annotators? | Affects annotation consistency and adjudication effort. | Draft guidelines and document any review/adjudication procedure. |
| Q-09 | Is a predefined specialty distribution required for the 100-note gold standard? | Affects sampling and specialty coverage. | Include at least 100 notes across at least 10 specialties, as specified in the SOW. |
| Q-10 | What local retention and access controls are required for reviewer decisions and trace data? | Affects storage and confidentiality controls. | Store only necessary local metadata and ensure traces do not expose PHI. |
| Q-11 | Must the MVP process all approximately 5,000 supplied notes, or is the evaluation subset sufficient for the initial demonstration? | Free-tier quotas and multiple model calls may limit throughput during the schedule. | Confirm required processing volume before finalizing capacity estimates; do not silently reduce scope. |

## B) Assumptions (Planning-Only, Not Approved Decisions)

| ID | Assumption | Rationale | Risk if Wrong |
|---|---|---|---|
| A-01 | The reviewer interface can run locally for the MVP. | The SOW calls for a local reviewer interface. | A later review workflow may require different deployment arrangements. |
| A-02 | A free-tier model may be used only if its current terms are acceptable and Mirai Labs approves it. | The SOW disallows paid API keys and requires model choice to be justified. | Provider terms, quotas, or policy restrictions may require another option. |
| A-03 | The original clinical note remains the source of truth for evidence offsets. | Accepted output must point to supporting spans in the original note. | Masking or normalization could shift offsets without an explicit mapping. |
| A-04 | The verifier is a separate pass that does not receive the extractor's hidden reasoning. | The SOW requires independent verification of support, status, contradictions, and missed items. | Shared context or tightly coupled logic could weaken independence. |
| A-05 | ICD-10 retrieval may combine keyword ranking and semantic similarity. | The SOW calls for keyword and semantic candidate retrieval. | Semantic retrieval may add complexity without improving measured performance. |
| A-06 | Trace data will contain masked model payloads or safe metadata only. | The SOW prohibits protected information from appearing in logs/traces. | Unsafe logging could cause a privacy incident. |

## C) Pending Decisions Before Implementation Approval

1. Final provider/model selection based on current availability, free-tier limits, privacy terms, and quality checks.
2. Selection of the keyword-retrieval implementation and embedding model.
3. PHI masking rules and review procedure for missed identifiers.
4. Original-to-masked text offset mapping strategy.
5. Gold-standard annotation guidelines and any adjudication process.
6. Required processing volume for the full supplied dataset and evaluation subset.
7. Retry/call budget and handling of rate limits or provider outages.

## D) Confirmed Project Clarifications

| ID | Clarification | Effect on the Project |
|---|---|---|
| C-01 | No specific products, open-source tools, or research papers have been prescribed. | Select relevant options independently and justify their suitability in the project documentation. |
| C-02 | The Gemini and Groq model IDs in the SOW are references only. | Research currently available free-tier alternatives and document the model-selection rationale. |

*Source: Clarifications provided by Mirai Labs in response to questions about the SOW and evaluation approach.*
