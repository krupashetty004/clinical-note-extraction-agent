# Research and Source References (Working List)

> Use this list as a validation checklist. Confirm current capabilities/limits from official sources at implementation start.

## 1) Standards and Coding References

1. ICD-10-CM official resources (CDC/NCHS and CMS public pages).
2. WHO ICD information portal (for general taxonomy context).

## 2) Open-Source Clinical NLP Tools

1. Apache cTAKES (official project site/repository and documentation).
2. medspaCy (official repository/documentation).
3. scispaCy (official repository/documentation).

## 3) Commercial Landscape (Official Vendor Sources)

1. Solventum / 3M Health Information Systems documentation and product pages.
2. Microsoft/Nuance Dragon Medical product documentation pages.
3. Optum coding/compliance product pages.

## 4) Structured Output and Validation

1. Pydantic official documentation.
2. Official documentation of shortlisted model providers for structured outputs/tool calling (to be selected after approval).

## 5) Retrieval and Evaluation Methodology

1. Public IR references for lexical retrieval (e.g., BM25 foundations).
2. Embedding-based retrieval references from provider/open-source docs.
3. Clinical NLP evaluation papers covering precision/recall/F1 and robustness testing patterns.

## 6) Verification and Safety

1. Prompt injection defense guidance for untrusted input handling.
2. Safety/abstention literature for high-risk domain extraction.

## 7) Citation Quality Rules for This Repository

- Prefer primary and official documentation.
- Do not fabricate benchmark values, API limits, or feature claims.
- If a claim is unverified, label it explicitly as pending verification.
- Re-validate model/provider availability immediately before implementation.
