# Research and Source References

**Project:** AI-Powered Clinical Note Extraction and Coding Agent MVP  
**Purpose:** Source list supporting the market research, architecture proposal, technology choices, and evaluation plan.  
**Status:** Planning reference; verify volatile product, model, pricing, and quota information before implementation.

## 1. Project Requirements

- Mirai Labs, *Statement of Work: AI-Powered Clinical Note Extraction and Coding Agent MVP*, version 1.0, 13 October 2026. Internal project source; keep the SOW itself out of this repository.

## 2. Research Papers

1. *Extracting International Classification of Diseases Codes from Clinical Documentation Using Large Language Models.* PubMed record: https://pubmed.ncbi.nlm.nih.gov/39608761/
2. Yuan, M., Shing, H.-C., Strong, M., and Shivade, C. (2025). *Toward Reliable Clinical Coding with Language Models: Verification and Lightweight Adaptation.* EMNLP Industry Track: https://aclanthology.org/2025.emnlp-industry.12/
3. *Validating Large Language Model-Assisted Data Extraction from Clinical Notes.* ESMO Real World Data. Full text: https://pmc.ncbi.nlm.nih.gov/articles/PMC13195338/ DOI: https://doi.org/10.1016/j.esmorw.2026.100718

**Use rule:** Paper results apply to the task, dataset, and models studied in each paper. Do not report them as expected performance for this MVP.

## 3. Commercial Clinical Documentation, Coding, and NLP Products

- Abridge clinician platform: https://www.abridge.com/platform/clinicians
- Ambience Healthcare products: https://www.ambiencehealthcare.com/products
- Microsoft Dragon Copilot documentation: https://learn.microsoft.com/en-us/industry/healthcare/dragon-copilot/
- Amazon Comprehend Medical API, ICD-10-CM inference: https://docs.aws.amazon.com/comprehend-medical/latest/api/API_InferICD10CM.html
- Microsoft Text Analytics for Health overview: https://learn.microsoft.com/en-us/azure/ai-services/language-service/text-analytics-for-health/overview
- Nuance Clintegrity product information: https://www.nuance.com/healthcare/provider-solutions/coding-compliance.html

These products are market references, not assumed dependencies. Confirm current capability, access, pricing, and data-use terms before relying on a specific feature claim.

## 4. Open-Source Clinical NLP and Coding Tools

- MedCoder repository: https://github.com/insafim/medcoder
- medSpaCy repository: https://github.com/medspacy/medspacy
- scispaCy repository: https://github.com/allenai/scispacy
- Apache cTAKES project site: https://ctakes.apache.org/

Review licence, dependencies, model/API requirements, catalogue assumptions, offset behaviour, and evaluation suitability before using third-party code.

## 5. Proposed Technology Documentation

- Python documentation: https://docs.python.org/3/
- Pydantic documentation: https://docs.pydantic.dev/
- Streamlit documentation: https://docs.streamlit.io/
- Chroma documentation: https://docs.trychroma.com/
- spaCy usage documentation: https://spacy.io/usage
- Groq supported models: https://console.groq.com/docs/models
- Groq rate limits: https://console.groq.com/docs/rate-limits
- Groq structured outputs: https://console.groq.com/docs/structured-outputs
- Groq data controls: https://console.groq.com/docs/your-data
- Groq model deprecations: https://console.groq.com/docs/deprecations
- Google Gemini API models: https://ai.google.dev/gemini-api/docs/models
- Google Gemini API pricing and data-use terms: https://ai.google.dev/gemini-api/docs/pricing

Model IDs, pricing, quotas, and retention terms can change. Recheck official documentation at the time of selection and record the date of verification. No provider is approved for project clinical notes merely because a model appears in public documentation.

## 6. Retrieval and Evaluation Concepts

- SQLite FTS5 documentation: https://www.sqlite.org/fts5.html
- Chroma documentation for vector search: https://docs.trychroma.com/
- Python standard-library documentation for automated evaluation scripts: https://docs.python.org/3/

Use the SOW's metric definitions and accepted evaluation data as the authoritative project specification. Define entity-match and partial-match rules before scoring. Report diagnosis, medication, and procedure metrics separately; report span faithfulness, ICD-10 top-1/top-3 performance, abstention/flagging, contradictions, adversarial tests, latency, calls, and quota limitations.

## 7. Citation and Evidence Rules

- Prefer original papers, official product documentation, and source repositories.
- Distinguish documented facts from proposed design choices and assumptions.
- Do not invent benchmark values, model availability, rate limits, product features, licences, or data-use terms.
- Keep results tied to the source study's task and dataset.
- Revalidate changing model and product details before implementation.
- Do not place the confidential SOW or any clinical dataset in the repository.
