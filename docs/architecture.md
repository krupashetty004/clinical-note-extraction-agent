# Architecture Proposal (Draft — Not Yet Approved)

## 1) Proposed Logical Components

| Component | Responsibility |
|---|---|
| Input Handler | Accept note text and metadata in controlled local workflow |
| PHI Masking Layer (Local) | Mask protected information before any external model call |
| Extraction Agent | Structured entity extraction under strict schema |
| ICD-10 Retrieval Service | Keyword + semantic candidate retrieval for diagnosis coding |
| Verification Agent | Independent support/contradiction/missed-item checks |
| Reconciliation Engine | Bounded retries, conflict resolution, abstention decisions |
| Trace Logger | Persist model/tool/decision traces |
| Reviewer UI (Local) | Evidence highlighting, accept/reject, flags, trace view, JSON export |

## 2) Trust Boundaries (Proposed)

1. **Local trusted boundary:** raw notes, PHI handling, trace storage.
2. **External model boundary (if used):** masked text only.
3. **Reviewer boundary:** final decisions remain human-auditable.

## 3) Data Flow (Proposed)

1. Ingest raw clinical note locally.
2. Normalize text + compute stable character offsets.
3. Apply local PHI masking for model-bound payload.
4. Run extraction pass.
5. Retrieve ICD-10 candidates.
6. Run independent verification pass.
7. Reconcile outputs with bounded retries.
8. Persist structured output + trace.
9. Present results in local reviewer UI.
10. Export approved JSON output.

## 4) Safety and Reliability Controls

| Control | Purpose |
|---|---|
| Prompt-injection resistance policy for notes | Ignore embedded instructions in note content |
| Evidence-required acceptance | Prevent unsupported structured outputs |
| Independent verification pass | Catch contradictions and missed items |
| Abstention (`no_confident_match`) | Avoid unsafe overclaiming |
| Structured tracing | Enable audits, debugging, and reproducibility |

## 5) Architecture Risks to Validate After Approval

- Free-tier rate limits and latency impacts on multi-pass flow.
- Offset integrity when masking/normalization is applied.
- Verifier disagreement handling thresholds.
- Local storage and confidentiality controls for trace data.

## 6) Approval Note

This architecture is a proposal for review on 16 Oct 2026 and must not be treated as an approved implementation design until Mirai Labs sign-off.
