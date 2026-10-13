# Evaluation Plan (Draft)

## 1) Evaluation Goals

Validate whether the MVP produces clinically useful, evidence-grounded structured outputs with safe abstention behavior and traceable coding suggestions.

## 2) Dataset Plan (Gold Standard)

| Requirement | Plan |
|---|---|
| Minimum size | At least 100 manually labelled notes |
| Specialty coverage | At least 10 specialties |
| Data source | Mirai Labs-provided clinical data only |
| Annotation outputs | entities, statuses, offsets, ICD-10 references (where available), contradiction notes |

## 3) Baselines and Systems Under Test

| System | Purpose |
|---|---|
| Naive single-prompt baseline | Lower-bound comparison |
| Proposed multi-pass agent pipeline | Primary system under evaluation |

## 4) Metrics

| Category | Metric |
|---|---|
| Entity extraction | Precision / Recall / F1 (entity-level) |
| Evidence grounding | Span-faithfulness and offset validity checks |
| Coding quality | ICD-10 Top-1 and Top-3 accuracy |
| Safety behavior | Abstention rate and abstention correctness analysis |
| Robustness | Contradiction tests, rare-diagnosis tests, adversarial note tests |
| Operational | Latency per note, cost per note/workload |

## 5) Test Set Design Considerations

- Include varied note styles (concise, narrative, templated).
- Include specialty diversity and class imbalance visibility.
- Include difficult negatives (insufficient evidence, ambiguous diagnosis mentions).
- Include contradiction-rich notes for verifier stress tests.

## 6) Analysis Outputs

1. Metric table by entity type and overall.
2. Error taxonomy (missed extraction, unsupported extraction, wrong code, verifier misses).
3. Abstention analysis (appropriate vs inappropriate abstentions).
4. Cost/latency profile under free-tier limits.
5. Qualitative reviewer feedback on UI and trace usefulness.

## 7) Reporting Rules

- Do not claim target achievement before measured results exist.
- Clearly separate measured findings from assumptions.
- Document all known limitations and unresolved risks.
