# Market Research: AI-Powered Clinical Note Extraction and Coding Agent MVP

**Project:** Mirai Labs — Clinical Note Extraction and Coding Agent MVP  
**Research date:** 15 October 2026  
**Status:** Planning input only; no implementation or performance claim is approved by this document.

## 1. Objective and SOW Alignment

This document reviews relevant commercial products, open-source clinical NLP tools, coding pipelines, and research papers. Its purpose is to identify relevant approaches and risks for the proposed MVP, not to claim that the MVP already outperforms existing products.

The SOW requires a local MVP that works with Mirai Labs-provided English clinical notes and an ICD-10 reference table. It must extract diagnoses, procedures, medications, allergies, and key vital signs; associate each accepted item with evidence and character offsets in the original note; retrieve ranked ICD-10 diagnosis candidates; verify results independently; support abstention and human review; record privacy-safe traces; and evaluate performance against a manually labelled gold standard and a naive single-prompt baseline.

The SOW excludes OCR/scanned or handwritten notes, procedure-code assignment, EHR/billing integration, multi-user/cloud deployment, model fine-tuning, and external clinical-note sourcing. It also restricts the MVP to free-tier services and no GPU-dependent infrastructure.

## 2. Commercial Clinical Documentation, Coding, and NLP Products

These products provide market context. They are not automatically suitable implementation dependencies: some are commercial services, some focus on encounter documentation rather than the complete extraction-and-verification workflow, and their current contracts, data-use terms, pricing, APIs, and limits must be checked independently.

| Product | Publicly documented focus | Relevance to this MVP | Limits and validation needs |
|---|---|---|---|
| **Abridge** | Clinical conversation intelligence and AI-generated clinical documentation, with workflow support around clinical encounters. | Shows the importance of clinician-facing workflows and readable documentation outputs. | Commercial clinical workflow product, not an assumed free-tier extraction library. Confirm exact feature and integration claims before comparison. [Official site](https://www.abridge.com/platform/clinicians) |
| **Ambience Healthcare** | AI clinical documentation and broader clinical workflow support, including coding and compliance capabilities. | Relevant to understanding how documentation, coding support, and human workflows can be combined. | Enterprise product, not a default dependency for this local free-tier MVP. Validate feature claims and data access. [Official site](https://www.ambiencehealthcare.com/products) |
| **Microsoft Dragon Copilot** | AI clinical assistant for clinical documentation, ambient capture, dictation, and clinician workflow. | Useful commercial reference for note-generation and clinician-review experience. | Not the same as an independent entity-verification benchmark or a local NLP library. Speech-to-text and EHR integration are not required by the MVP. [Official documentation](https://learn.microsoft.com/en-us/industry/healthcare/dragon-copilot/) |
| **Amazon Comprehend Medical** | Healthcare NLP API for detecting medical entities and linking certain concepts to standardized vocabularies, including ICD-10-CM-related results. | Useful benchmark for entity extraction, terminology linking, confidence information, and source-position outputs. | Commercial AWS service, not assumed to meet the free-tier constraint. Confirm pricing, supported entity categories, text limits, and data terms. It does not by itself implement the complete agent and reviewer workflow. [Official documentation](https://docs.aws.amazon.com/comprehend-medical/latest/api/API_InferICD10CM.html) |
| **Microsoft Text Analytics for Health** | Healthcare NLP service supporting entity recognition, relation extraction, entity linking, and assertion detection. | Relevant to clinical context such as certainty, temporality, and relationships among concepts. | Hosted service whose terms, limits, and output schema must be reviewed. Additional processing may be needed to match all SOW requirements. [Overview](https://learn.microsoft.com/en-us/azure/ai-services/language-service/text-analytics-for-health/overview) |
| **Nuance Clintegrity** | Enterprise medical coding, compliance, and coding-review workflows. | Useful workflow reference for code review, compliance, and auditability. | Public product information may not establish current standalone product boundaries or a usable API for this MVP. Validate current product names and features. [Product information](https://www.nuance.com/healthcare/provider-solutions/coding-compliance.html) |

### Commercial landscape finding

Medical documentation, healthcare NLP, terminology linking, coding support, and independent evidence verification are related but different capabilities. Public product descriptions alone do not establish that a product satisfies the complete SOW. The proposed MVP must be evaluated on original-note evidence spans, entity categories, status handling, diagnosis candidate retrieval, independent verification, abstention, traceability, local review, and measured evaluation results.

## 3. Open-Source Clinical NLP and Medical Coding Tools

| Tool | Main capabilities or design | Potential relevance | Caveats for this MVP |
|---|---|---|---|
| **medSpaCy** | Python clinical NLP components for sentence processing, section detection, rules, and context attributes such as negation and uncertainty. | Could help detect cues such as “denies,” “history of,” or “rule out,” which affect clinical status. | Requires evaluation/configuration on supplied notes; it is not a complete extraction, coding, verification, or reviewer application. [Repository](https://github.com/medspacy/medspacy) |
| **scispaCy** | Python NLP pipelines and models for biomedical text, including entity recognition and entity-linking components. | Candidate for biomedical preprocessing or terminology-related tasks if it improves measured performance. | General biomedical models are not guaranteed to cover the full clinical schema or assign correct ICD-10 codes. Validate compatibility, memory, licence, and results. [Repository](https://github.com/allenai/scispacy) |
| **Apache cTAKES** | Open-source clinical text-analysis system for extracting information from electronic medical record narratives. | Reference for clinical concept extraction and established clinical NLP patterns. | Java-oriented and may add integration overhead to a Python-based, short-duration MVP. Adopt only if evaluation demonstrates a concrete benefit. [Project site](https://ctakes.apache.org/) |
| **MedCoder** | Open-source auditable medical-coding pipeline. Its repository describes constrained code selection, hybrid retrieval, deterministic checks, evidence-linked suggestions, independent auditing, and trace output. | Particularly relevant architecture reference for evidence-gated coding, candidate retrieval, independent verification, and traceability. | Not automatically a drop-in dependency. Inspect its licence, model/API requirements, catalogue assumptions, evaluation data, and offset handling. Procedure-code assignment remains outside this MVP's scope. [Repository](https://github.com/insafim/medcoder) |

### Preliminary open-source assessment

- Investigate **medSpaCy** first if section detection and contextual attributes improve status handling on the supplied notes.
- Evaluate **scispaCy** only if biomedical entity recognition or linking adds measurable value beyond the selected extraction approach.
- Treat **MedCoder** primarily as an architecture and implementation reference. Do not assume its provider, licence, code catalogue, or evaluation setup fits the SOW.
- Keep **Apache cTAKES** as a comparison option; avoid adding a second language runtime unless the evaluation shows a concrete benefit.

## 4. Structured Extraction and Agent Design Patterns

| Pattern | Benefit | Risk or constraint | Planning implication |
|---|---|---|---|
| Strict schema with validation (for example, Pydantic) | Predictable output that is easier to validate, test, display, and export. | A valid schema does not prove clinical correctness or source support. | Validate structure separately from evidence, status, and verification outcome. |
| Evidence-linked extraction | Provides a source span that can be checked and highlighted. | Offsets can become invalid after masking or normalization. | Keep the original note as source of truth and map transformed-text positions back to original offsets. |
| Independent verification pass | Can detect unsupported items, wrong status, contradictions, and potentially missed entities. | The verifier can make errors; a second pass adds latency and quota use. | Measure verifier quality and disagreement handling instead of assuming verification guarantees correctness. |
| Explicit agent loop and tool calls | Lets the orchestrator choose tools, inspect results, retry recoverable failures, and escalate unresolved cases. | Adds orchestration complexity and possible latency. | Use a simple explicit loop with bounded retries, traceable decisions, and per-note call/time budgets. |
| Human-in-the-loop review | Allows a reviewer to accept/reject outputs and inspect evidence. | Review effort increases if too many items are flagged. | Show clear reasons and highlights; measure abstention and review behaviour. |
| Naive single-prompt baseline | Provides a simple comparison system. | Does not test all multi-pass safeguards. | Run it on the same agreed evaluation notes as the proposed system. |

## 5. ICD-10 Diagnosis Candidate Retrieval

The SOW requires keyword and semantic candidate retrieval over the supplied ICD-10 table. Procedure coding is explicitly out of scope.

| Retrieval approach | Strength | Limitation | Planned use |
|---|---|---|---|
| Keyword/lexical retrieval (for example, SQLite FTS5 or BM25) | Transparent, fast, and useful when wording overlaps. | Can miss abbreviations, synonyms, and paraphrases. | Use as one candidate-generation path; select one primary implementation after testing. |
| Semantic retrieval using embeddings | Can retrieve related descriptions when wording differs. | Depends on embedding quality and index design; similarity is not proof of clinical correctness. | Use as a complementary path if compatible with the free/local constraints. |
| Hybrid retrieval and ranking | Can combine lexical matching and semantic similarity. | Fusion/reranking can increase complexity, latency, and false-positive candidates. | Compare against keyword-only retrieval and keep only if measured gains justify the complexity. |
| No-confident-match outcome | Avoids forcing an uncertain code. | Poorly calibrated thresholds may over-abstain or return weak candidates. | Include the SOW-required outcome and evaluate it on rare/poorly represented diagnoses. |

### Proposed retrieval flow for evaluation

1. Read the diagnosis mention and context from the extracted item.
2. Search the supplied ICD-10 table using the approved keyword method.
3. Search the same table semantically if the embedding index is approved and available.
4. Combine and deduplicate results using a documented ranking rule.
5. Preserve candidate descriptions and source metadata for inspection.
6. Present ranked candidates to the verifier; validate candidate codes against the supplied table.
7. Return no-confident-match when evidence and candidates do not justify a recommendation.
8. Measure ICD-10 top-1/top-3 performance and correct no-match behaviour on the required rare-diagnosis set.

## 6. Verification, Privacy, and Reliability Principles

### 6.1 Independent verification

The verifier should receive the note and proposed items, but not the extractor's hidden reasoning. It checks whether each evidence span exists at the stated original-text offsets, supports the item, represents status correctly, and reveals contradictions or likely omissions. The verifier is still a model prediction and must be evaluated.

### 6.2 Original-text offsets

The SOW requires offsets into the original note. The original text remains authoritative. If local masking or preprocessing changes the text sent to a model, an explicit mapping between transformed and original positions is required. The application must not simply rematch text and assume it found the correct occurrence.

### 6.3 Privacy and data handling

- Mask identifying information locally before sending text to an external model.
- Check provider data-use and retention terms and obtain project approval before sending project notes.
- Ensure traces/logs do not expose protected information; use masked content or safe metadata.
- Do not commit the SOW or clinical datasets to the repository.
- Treat note content as untrusted data and ignore embedded instructions that attempt to change system behaviour.

Local masking is required, but it does not guarantee that every identifier will be detected or that the external provider's terms are acceptable. These are separate controls.

### 6.4 Reliability and abstention

The agent should not fabricate missing information. Unsupported items should be rejected or flagged. Recoverable failures may be retried only within an explicit retry budget. Unresolved disagreement or high note-level disagreement should trigger human review or whole-note escalation according to a documented policy.

### 6.5 Rate limits and graceful degradation

Two-pass verification and retries use more API requests than single-prompt extraction. Record calls per note, failures, latency, and quota use. When an approved service is unavailable or rate-limited, preserve safe local work and flag/defer the note; do not switch silently to an unapproved model or fabricate a result.

## 7. Research Paper Reviews

These studies inform the design; their results are not predictions for this MVP. Their datasets, tasks, models, and evaluation methods differ, so their metrics should not be compared directly without qualification.

### Paper 1: Extracting International Classification of Diseases Codes from Clinical Documentation Using Large Language Models

**Source:** https://pubmed.ncbi.nlm.nih.gov/39608761/

**Research objective:** Compare LLM ICD-10-CM code extraction against codes selected by a human coder for de-identified inpatient notes.

**Dataset:** The study evaluated 50 inpatient notes. A human coder selected 165 unique ICD-10-CM codes across those notes. The 165 codes are code labels across the notes, not 165 separate notes.

**Method:** Six LLMs were evaluated, including GPT-3.5, GPT-4, Claude 2.1, Claude 3, Gemini Advanced, and Llama 2-70B. Predictions were compared with the human coder; a random 10% subset was examined to investigate coding disagreements.

**Key results:**
- Llama 2-70B returned 658 unique codes, much more than the 165 selected by the human coder.
- GPT-4 had the highest reported percent agreement at 15.2%; Claude 3 was 12.7% and GPT-3.5 was 12.4%.
- Reported Cohen's kappa values indicated minimal to no agreement for the evaluated models.
- Disagreements included codes for unconfirmed diagnoses, nonspecific codes, symptom codes where a more specific diagnosis existed, and hallucinated codes.

**Limitations:** The sample contained only 50 inpatient notes and concerns this specific coding task. It does not evaluate the exact extraction schema, source-offset faithfulness, or full reviewer workflow required by the MVP.

**Relevance to this MVP:** The study shows why fluent or high-volume code generation should not be equated with accuracy. Candidate constraints, evidence checks, abstention, independent verification, human review, and measurement of overprediction are important.

**Conclusion:** This paper supports evaluation against a reference standard. It does not establish that the proposed MVP will achieve any particular accuracy target.

### Paper 2: Toward Reliable Clinical Coding with Language Models: Verification and Lightweight Adaptation (Yuan et al., 2025)

**Source:** https://aclanthology.org/2025.emnlp-industry.12/

**Research objective:** Investigate why LLMs make clinical coding errors and whether prompt changes, lightweight adaptation, and a verification stage improve ICD-10-CM coding.

**Dataset:** An expert double-annotated outpatient coding benchmark derived from ACI-Bench, containing 207 examples: 67 training, 20 development, and 120 test examples. Each example includes a note, candidate codes, gold-standard codes, and verification labels. Annotators resolved disagreements through adjudication.

**Method:** The generate-expand-verify pipeline generates code candidates, expands them using ICD-10-CM hierarchy and index relationships, and then verifies/selects among expanded candidates. The paper also studies prompting and small-scale fine-tuning.

**Key results:**
- For Claude Haiku 3, exact-match F1 increased from 41.6 for generation alone to 47.2 after verification.
- The fine-tuned Haiku 3 configuration reported 57.6 F1 with verification versus 56.9 for generation alone in that configuration.
- Oracle selection is an upper-bound analysis using gold labels, not a deployable system result.
- The authors report that hierarchically close codes can still be incorrect and that candidate expansion plus verification improved results on this dataset.

**Limitations:** The benchmark contains 207 outpatient examples and uses models and definitions different from this project. Results cannot be assumed to transfer. Fine-tuning is outside the current SOW scope.

**Relevance to this MVP:** The paper supports separating candidate generation from verification and measuring top-1/top-3 performance, correct abstention, and verifier contribution against a baseline.

**Conclusion:** Verification improved results in the studied setting but does not guarantee correctness. The MVP must evaluate its own verification stage.

### Paper 3: Validating Large Language Model-Assisted Data Extraction from Clinical Notes

**Source:** https://pmc.ncbi.nlm.nih.gov/articles/PMC13195338/  
**DOI:** https://doi.org/10.1016/j.esmorw.2026.100718

**Research objective:** Evaluate LLM-assisted structured extraction from clinical documentation in head and neck oncology consultations against clinician assessments.

**Dataset:** Documentation from 60 patients, totalling 1,482 pages, was analysed across 29 clinically relevant categories. Six clinical experts evaluated 2,555 extracted values: first judging match/non-match against human consensus, then categorising mismatches.

**Method:** A pretrained open-source LLM's extraction was compared with physician extraction and expert consensus. Mismatches were categorised as incorrect, incomplete, missing, hallucinated, or overcomplete information.

**Key results:**
- Overall reported accuracy was 0.81, precision 0.82, recall 0.91, and F1 0.86 across the study's categories.
- Performance varied by category; explicit, consistently formatted information performed better than more variable or implicit content.
- Reported extraction time per case decreased from 8.6 minutes manually to 1.9 minutes with LLM assistance in that study setting.

**Limitations:** The work focused on a specific oncology consultation setting and 29 categories. Its metrics do not establish performance on the Mirai Labs dataset or the full set of required entity categories, offsets, and coding tasks. Human assessment was part of its evaluation.

**Relevance to this MVP:** It supports category-by-category evaluation and detailed error analysis rather than relying only on an overall score. Reviewer oversight remains important.

**Conclusion:** The study supports expert-labelled evaluation and error categorisation. Its results are contextual evidence, not a transferable benchmark for this project.

## 8. Cross-Paper Synthesis and Research Gaps

1. **Overprediction and unsupported coding:** LLMs may generate codes not justified by a record or select codes that are less specific than the evidence supports.
2. **Verification has potential but can fail:** A separate verification stage may improve coding results but must be evaluated independently.
3. **Dataset design matters:** Specialty, inpatient/outpatient context, note format, label definitions, and annotation quality influence results.
4. **Aggregate metrics can hide failures:** Per-category metrics, error analysis, span checks, and contradiction handling are needed.
5. **Annotation consistency matters:** Guidelines and a process for resolving disagreements are important for a trustworthy gold standard.

### Gaps the MVP should address

- Preserve verifiable evidence spans and character offsets in the original note.
- Extract all SOW entity groups using a consistent schema.
- Distinguish present, absent, uncertain, and historical mentions.
- Retrieve ICD-10 candidates rather than allowing unsupported arbitrary code generation.
- Verify source support, status, contradictions, and possible omissions independently.
- Abstain when the evidence/candidates are inadequate.
- Record decisions and model/tool activity without exposing protected information.
- Evaluate at least 100 manually labelled notes across at least 10 specialties, as required by the SOW.
- Compare against a naive single-prompt baseline and explain poor-performing cases.

## 9. Risks Requiring Validation

| Risk | Why it matters | Required follow-up |
|---|---|---|
| Product descriptions overstate fit | Products may cover only a subset of the required workflow. | Validate features using official documentation; do not imply complete SOW compliance from marketing descriptions. |
| Model/API availability changes | Model IDs, data terms, and quotas can change. | Recheck provider documentation at selection time. |
| Free-tier quotas limit throughput | Multiple calls and retries consume requests quickly. | Estimate calls per note, check account-specific limits, and document graceful degradation. |
| Offset drift after masking | Evidence may highlight the wrong location in the note. | Preserve original text and test explicit offset mapping. |
| Clinical status errors | Negation, uncertainty, and historical mentions change meaning. | Include labelled examples and measure status correctness. |
| Rare diagnoses lack good candidates | Retrieval may produce weak or no match. | Use the required rare-diagnosis test set and measure correct no-match behaviour. |
| Verifier misses errors | A second model is not guaranteed to be right. | Evaluate contradiction detection and disagreements. |
| Protected information appears in traces | Logs may expose sensitive information. | Record masked payloads/safe metadata only and test for leakage. |
| Short project timeline | Annotation and integration compete for limited time. | Begin labelling early and raise capacity risks rather than silently changing requirements. |

## 10. Preliminary Planning Recommendations

1. Require a source span and offsets for every proposed entity; do not accept unsupported entities.
2. Separate retrieval from selection: retrieve candidates, validate codes against the supplied table, and retain a no-confident-match path.
3. Use independent verification for entity support, offsets, status, contradictions, and omissions.
4. Implement an explicit agent loop with bounded retries, reconciliation, traceable decisions, and human escalation.
5. Keep the original note as the source of truth for span validation and UI highlighting.
6. Evaluate against the SOW using the same agreed gold set for the baseline and proposed pipeline.
7. Keep the architecture local and small; Streamlit and local persistence are candidate choices for a single-reviewer localhost MVP.
8. Choose models only after checking provider policy, availability, output format, quotas, latency, and measured quality.
9. Do not implement excluded features such as OCR, procedure coding, fine-tuning, EHR integration, or cloud deployment.

## 11. Questions for the Architecture Phase

1. Which available free-tier LLM API, if any, has data-use terms acceptable to Mirai Labs for masked project notes?
2. Can its quotas accommodate the required evaluation volume and bounded retries?
3. Which keyword retrieval method is simplest and sufficiently accurate on the supplied code table?
4. Does local semantic retrieval measurably improve candidate coverage over keyword retrieval alone?
5. How will original-to-masked text offset mapping be implemented and tested?
6. What retry/call budget should trigger item-level review or whole-note escalation?
7. Must all approximately 5,000 supplied notes be processed, or is an evaluation subset sufficient for the initial demonstration? Confirm scope rather than silently reducing it.

## 12. References

### Project specification

- Mirai Labs, *Statement of Work: AI-Powered Clinical Note Extraction and Coding Agent MVP*, version 1.0, 13 October 2026. Internal project document; do not publish it in the repository.

### Research papers

1. *Extracting International Classification of Diseases Codes from Clinical Documentation Using Large Language Models.* PubMed: https://pubmed.ncbi.nlm.nih.gov/39608761/
2. Yuan, M., Shing, H.-C., Strong, M., and Shivade, C. (2025). *Toward Reliable Clinical Coding with Language Models: Verification and Lightweight Adaptation.* EMNLP Industry Track: https://aclanthology.org/2025.emnlp-industry.12/
3. *Validating Large Language Model-Assisted Data Extraction from Clinical Notes.* ESMO Real World Data: https://doi.org/10.1016/j.esmorw.2026.100718

### Commercial product documentation

- Abridge: https://www.abridge.com/platform/clinicians
- Ambience Healthcare: https://www.ambiencehealthcare.com/products
- Microsoft Dragon Copilot: https://learn.microsoft.com/en-us/industry/healthcare/dragon-copilot/
- Amazon Comprehend Medical: https://docs.aws.amazon.com/comprehend-medical/latest/api/API_InferICD10CM.html
- Microsoft Text Analytics for Health: https://learn.microsoft.com/en-us/azure/ai-services/language-service/text-analytics-for-health/overview
- Nuance Clintegrity: https://www.nuance.com/healthcare/provider-solutions/coding-compliance.html

### Open-source tools and repositories

- MedCoder: https://github.com/insafim/medcoder
- medSpaCy: https://github.com/medspacy/medspacy
- scispaCy: https://github.com/allenai/scispacy
- Apache cTAKES: https://ctakes.apache.org/

### Citation quality rules

- Prefer primary research, official documentation, and original repositories.
- Product descriptions are not proof of end-to-end performance against the MVP requirements.
- Do not invent benchmark values, rate limits, or feature claims.
- Keep study results tied to their original datasets and tasks; do not compare metrics as if they came from one benchmark.
- Recheck product/model availability, terms, licences, and quotas before implementation.
- Mark unverified claims as pending validation.
