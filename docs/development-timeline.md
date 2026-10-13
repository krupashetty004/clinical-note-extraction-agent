# Development Timeline (Planning Baseline)

## 1) Pre-Approval Milestones (Fixed)

| Date | Deliverable |
|---|---|
| 13 Oct 2026 | Requirements clarification + repository documentation setup + initial research synthesis |
| 14 Oct 2026 (~4 PM) | Market research presentation deck/content |
| 15 Oct 2026 (by 6 PM) | Complete solution proposal + architecture + stack rationale + detailed timeline |
| 16 Oct 2026 | Architecture review and formal approval gate (no feature code before sign-off) |

## 2) Post-Approval Working-Day Plan (Through 26 Oct 2026)

| Date | Planned Deliverable | Risk Controls |
|---|---|---|
| 16 Oct (Fri) | Approval outcomes documented; finalize implementation scope freeze | Confirm blocked/pending decisions before coding |
| 19 Oct (Mon) | Data handling module plan + annotation guideline draft + gold-set sampling plan | Confirm specialty distribution and masking policy |
| 20 Oct (Tue) | Gold-set annotation start + baseline single-prompt evaluation harness skeleton | Track annotation throughput and consistency issues |
| 21 Oct (Wed) | Structured extraction pipeline implementation (pass 1) + schema validation | Guard against offset drift and malformed outputs |
| 22 Oct (Thu) | ICD-10 retrieval integration (keyword + semantic) + `no_confident_match` logic | Monitor free-tier limits and fallback behavior |
| 23 Oct (Fri) | Independent verification pass + reconciliation loop + trace logging | Stress-test contradiction and missed-item detection |
| 26 Oct (Mon) | Reviewer UI completion, end-to-end evaluation run, metrics summary, demo prep, final defense package | Validate latency/cost and document unresolved limitations |

## 3) Capacity and Contingency Notes

- Reserve buffer each day for rate-limit retries and debugging.
- Prioritize completing gold-standard annotation early to de-risk evaluation bottlenecks.
- If model availability changes, fall back to approved alternatives without violating free-tier constraint.

## 4) Explicit Constraint Reminder

Implementation tasks above activate **only after formal approval** on 16 Oct 2026.
