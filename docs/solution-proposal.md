# Solution Proposal (Draft — Pending Approval)

## 1) Proposal Summary

Design a two-pass, evidence-gated extraction pipeline that:
1. extracts structured clinical entities from note text,
2. retrieves ICD-10 candidate codes for diagnoses,
3. verifies all accepted outputs through an independent pass,
4. surfaces reviewer controls with highlighted evidence and trace visibility.

## 2) Proposed Output Contract (High-Level)

| Field Group | Intent |
|---|---|
| `note_metadata` | track note ID/source provenance without exposing raw PHI externally |
| `entities` | diagnoses/procedures/medications/allergies/vitals with normalized structure |
| `evidence` | exact note spans + character offsets per extracted item |
| `icd10_candidates` | ranked diagnosis-code suggestions with confidence/support metadata |
| `verification` | pass/fail reasons, contradiction flags, missing-item flags |
| `decision` | accepted/rejected/abstain markers and reviewer-required indicators |
| `trace` | model/tool calls, retries, reconciliations |

## 3) Extraction + Verification Flow (Proposed)

1. Local preprocessing and PHI masking for model-bound text.
2. Primary extraction pass under strict schema constraints.
3. ICD-10 candidate retrieval (keyword + semantic) for diagnosis entities.
4. Independent verification pass to:
   - validate source support,
   - detect status errors/contradictions,
   - identify likely missed entities.
5. Reconciliation logic with bounded retries.
6. Evidence-gated acceptance:
   - accept only if supported,
   - otherwise reject/flag,
   - use `no_confident_match` where confidence is insufficient.
7. Persist structured traces for audit and reviewer inspection.

## 4) Human-in-the-Loop Review (Proposed)

Reviewer interface should provide:
- highlighted evidence snippets and offsets,
- item-level accept/reject controls,
- flagged contradictions/unsupported claims,
- trace timeline view,
- JSON export for audited outputs.

## 5) Why This Proposal Fits SOW

- Meets extraction scope categories.
- Enforces supporting evidence before acceptance.
- Includes abstention path.
- Implements independent verification.
- Supports measurable evaluation through structured outputs and traces.

## 6) Explicitly Deferred Until Approval

- Final model/provider selection.
- Final retrieval stack implementation details.
- Any production/feature code.
