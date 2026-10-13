# Market Research (Planning Input)

> This document summarizes planning-level research categories and candidate tools/products. Any product capability claims must be validated against current official documentation and, where possible, live trials before implementation decisions.

## 1) Commercial Clinical Documentation & Coding Landscape

| Product/Vendor | Publicly Known Focus Area | Relevance to MVP | Notes for Validation |
|---|---|---|---|
| 3M M*Modal / Solventum clinical documentation solutions | Clinical documentation and coding support | Demonstrates enterprise demand for documentation-to-coding workflows | Verify current product lines, features, and integration boundaries from official docs |
| Nuance Dragon Medical (Microsoft) | Clinical documentation and ambient capture ecosystems | Shows user expectations for clinician-facing workflows | Validate coding-assist scope vs transcription scope |
| Optum coding/compliance tooling | Coding quality and revenue-cycle alignment | Highlights coding accuracy and auditability needs | Verify feature-level details directly from vendor docs |

**Planning takeaway:** MVP should differentiate with transparent evidence spans, explicit abstention, and verification traceability.

## 2) Open-Source Clinical NLP / Medical Extraction Tools

| Tool | Core Strength | MVP Usefulness | Caveat |
|---|---|---|---|
| Apache cTAKES | Clinical concept extraction pipeline | Useful reference for entity categories and clinical NLP patterns | Java-heavy stack, integration overhead |
| MedSpaCy | Clinical NLP components in Python | Potential lightweight rule-based augmentations | Requires tuning for dataset/domain |
| scispaCy | Biomedical NLP models and entity linking primitives | Candidate support for biomedical text preprocessing | General biomedical, not ICD-specific by default |

## 3) Structured-Output LLM Approaches

| Approach | Benefit | Risk / Constraint | Status |
|---|---|---|---|
| Schema-constrained output (e.g., Pydantic validation) | Predictable JSON, easier downstream checks | May reduce recall if schema too rigid | Recommended for MVP planning |
| Tool-calling agent loops | Enables retrieval + verification + reconciliation | More latency and orchestration complexity | Candidate architecture pattern |
| Single-prompt extraction baseline | Fast and simple benchmark baseline | Lower controllability, weaker robustness | Required as naive baseline |

## 4) ICD-10 Candidate Retrieval Patterns

| Pattern | Strength | Limitation | MVP Recommendation |
|---|---|---|---|
| Keyword/lexical retrieval | Transparent and fast | Misses paraphrases/synonyms | Include as first-stage retriever |
| Semantic retrieval (embeddings) | Better paraphrase handling | Model/index quality sensitive | Include as complementary stage |
| Hybrid fusion/reranking | Better candidate recall-quality balance | More complexity/latency | Use if free-tier limits allow |

## 5) Verification & Safety Approaches

| Technique | Purpose | MVP Fit |
|---|---|---|
| Independent second-pass verifier | Check support/contradictions/missed entities | High (SOW-required) |
| Evidence-required acceptance gating | Prevent unsupported outputs | High (SOW-required) |
| Abstention outcome (`no_confident_match`) | Avoid unsafe overclaiming | High (SOW-required) |
| Prompt-injection resistance policy for note text | Treat notes as untrusted input | High (SOW-required) |

## 6) Research Themes to Track

- Clinical IE with span-grounded extraction and auditability.
- Entity/linking reliability for diagnosis normalization.
- Abstention-calibrated extraction in safety-critical NLP.
- Robustness under adversarial/noisy clinical narratives.

## 7) Risks Identified from Market/Research Review

1. **Model/API availability drift:** public model IDs and limits can change quickly.
2. **Free-tier constraints:** throughput/rate limits may impact evaluation scale.
3. **Domain shift:** coding performance can vary sharply by specialty and note style.
4. **False confidence risk:** unsupported extraction without strict evidence gating.

## 8) Decision Impact on Current Planning

- Keep model/provider selection explicitly **pending verification and approval**.
- Preserve a fallback architecture where retrieval + deterministic checks remain useful even under model limits.
- Prioritize observability (trace logs, verifier decisions, abstention analytics).
