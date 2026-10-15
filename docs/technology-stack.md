# Technology Stack Proposal and Justification

**Project:** AI-Powered Clinical Note Extraction and Coding Agent MVP  
**Status:** Proposed — pending architecture and technology-stack approval  
**Research checked:** 15 October 2026

> All technology choices remain proposals until Mirai Labs approves them. Model availability and free-tier limits can change and must be rechecked before implementation.

## 1. Decision Criteria

| Criterion | Why It Matters |
|---|---|
| Fit to SOW | Must support extraction, verification, ICD-10 retrieval, review, traceability, and evaluation. |
| Free-tier availability | The SOW disallows paid API keys and GPU-dependent infrastructure. |
| Privacy and data use | Clinical text must be masked locally and any external provider must be acceptable under Mirai Labs' policy. |
| Structured output | Extraction results must follow a strict schema and include evidence spans. |
| Independent verification | The verifier must be a separate pass and must not receive the extractor's hidden reasoning. |
| Rate limits and latency | Multi-pass calls and bounded retries affect throughput and the under-30-second median target. |
| Simplicity | The MVP is local and single-reviewer; unnecessary production infrastructure should be avoided. |

## 2. Proposed Stack

| Layer | Proposed technology | Purpose and rationale |
|---|---|---|
| Core language | Python 3.12.x; exact patch to be pinned after testing | Supports NLP, data processing, APIs, and evaluation. |
| Schema validation | Pydantic 2.x | Validates required fields and data types. Schema validity alone does not prove clinical correctness. |
| LLM API | Provisional Groq API candidates, subject to privacy review and approval | Offers current hosted model candidates with documented free-plan quotas. |
| Agent orchestration | Explicit Python agent loop | Makes tool use, bounded retries, reconciliation, and escalation inspectable. |
| Keyword retrieval | SQLite FTS5 with BM25 ranking | Uses FTS5 for full-text search over the supplied ICD-10 table and BM25 to rank matching descriptions by relevance. |
| Semantic retrieval | ChromaDB with a compatible local embedding model, such as bge-small-en | Retrieves potentially related diagnosis descriptions when wording differs. |
| Local privacy processing | Rule-based masking plus spaCy NER | Detects and masks likely identifiers before model calls. |
| Reviewer interface | Streamlit | Provides evidence highlighting, accept/reject controls, flagged items, trace viewing, and JSON export locally. |
| Local persistence | SQLite/local files only where required | Stores review metadata and evaluation outputs without a separate database server. |
| Trace format | Structured JSON containing masked payloads or safe metadata | Records tool calls, decisions, retries, and outcomes without exposing PHI. |
| Evaluation | Python scripts and automated tests | Computes metrics and runs required robustness tests. |
| Version control | Git and private GitHub repository | Tracks documentation and implementation changes. |

Exact package versions must be pinned only after a clean environment test confirms compatibility.

## 3. LLM Candidates and Provisional Recommendation

The SOW's Gemini and Groq model IDs are reference examples. The model IDs below were checked against provider documentation on 15 October 2026.

| Candidate | Current documented status | Potential use | Important limitation |
|---|---|---|---|
| Groq openai/gpt-oss-20b | Listed as a supported model; free-plan limits are documented; strict JSON-schema output is supported | First candidate for structured extraction | Clinical extraction quality must be measured on approved examples. |
| Groq qwen/qwen3.8-27b | Listed as a supported model; free-plan limits are documented; strict JSON-schema output is supported | Candidate for the independent verification pass | Clinical verification quality must be measured; do not assume it is better simply because it is a different model family. |
| Google gemini-3.1-flash-lite | Listed as available with a free tier | Alternative to evaluate if policy permits | Google's pricing documentation states that free-tier content may be used to improve its products, requiring careful privacy review for clinical text. |

Official references:
- Groq [supported models](https://console.groq.com/docs/models)
- Groq [free-plan rate limits](https://console.groq.com/docs/rate-limits)
- Groq [structured outputs](https://console.groq.com/docs/structured-outputs)
- Groq [data retention and controls](https://console.groq.com/docs/your-data)
- Groq [model deprecation](https://console.groq.com/docs/deprecations)
- Google [Gemini models](https://ai.google.dev/gemini-api/docs/models)
- Google [Gemini API pricing and data-use terms](https://ai.google.dev/gemini-api/docs/pricing)

### Provisional configuration to evaluate

1. **Extraction:** Groq openai/gpt-oss-20b.
2. **Independent verification:** Groq qwen/qwen3.8-27b.

This pair is a starting point for a small, controlled evaluation because both are documented as supporting strict JSON-schema output and come from different model families. It is not a final decision or a claim of proven clinical quality.

The previously suggested Groq model llama-3.3-70b-versatile should not be used as the default candidate: Groq's deprecation documentation lists its shutdown date as 16 August 2026. Check provider documentation again before finalizing model IDs.

### Privacy requirement

Groq states that inference inputs and outputs are not retained by default, but data may be temporarily retained for reliability troubleshooting or abuse monitoring unless applicable data controls prevent it. This is not a substitute for Mirai Labs' approval or a data-use review.

Google's free-tier documentation states that content may be used to improve its products. Do not send clinical notes to any provider until Mirai Labs confirms that the provider's applicable terms and configuration are acceptable. Local PHI masking is mandatory regardless, but masking alone does not guarantee that every identifier will be removed.

### Free-tier capacity risk

Groq's current rate-limit documentation lists free-plan limits for openai/gpt-oss-20b and qwen/qwen3.8-27b of 1,000 requests per day, with model-specific token limits. Account-specific limits must be checked before implementation.

A two-pass design can require at least two model requests per note. At two calls per note, 1,000 requests would theoretically cover at most 500 notes per day before retries, failures, or additional model calls. Processing all approximately 5,000 notes may therefore exceed the available daily request budget. Confirm the required processing volume and quota before finalizing capacity; do not silently reduce the stated scope.

## 4. Technology Justifications

### 4.1 Python

Python is proposed because it supports data manipulation, text processing, API clients, NLP libraries, and repeatable evaluation in one environment. Node.js is possible, but Python is a direct fit for the project's NLP and evaluation tasks.

### 4.2 Pydantic

Pydantic validates the structure of extraction and verification results. It catches missing fields, incorrect types, and schema errors. Evidence existence, original offsets, clinical support, and status correctness require additional validation logic.

### 4.3 Explicit agent loop

A small Python loop is preferred over a large orchestration framework because the SOW requires deliberate tool calls, bounded retries, reconciliation, and escalation. Keeping those decisions explicit makes the process easier to test and explain.

### 4.4 Keyword and semantic ICD-10 retrieval

Keyword retrieval is transparent and can find exact terms. Semantic retrieval may find relevant descriptions when the note uses different wording. The two approaches are complementary, but their combined value must be measured against a keyword-only comparison.

SQLite FTS5 provides full-text retrieval and its BM25 ranking function orders matches by relevance. Evaluate this lexical retrieval against a simpler keyword-only baseline, then measure whether semantic retrieval adds value. ChromaDB is a candidate vector store for embeddings. Similarity scores must not be treated as proof that a code is clinically correct.

### 4.5 Local privacy processing

Rule-based matching can detect predictable patterns such as phone numbers and email addresses. spaCy NER may identify names, dates, and locations based on context. Neither is guaranteed to detect every identifier. Masking must be tested, and an explicit mapping between masked text and original offsets must be preserved so evidence can be validated against the original note.

### 4.6 Streamlit

Streamlit offers a fast path to a local review interface. React and a separate backend would add frontend work that is not needed for a single-reviewer localhost MVP.

### 4.7 SQLite and local files

SQLite and local files avoid the operational overhead of running a database server. Store only data needed for the local review and evaluation workflow. Keep raw protected information out of traces and repository commits.

### 4.8 Structured JSON trace

Structured JSON makes model/tool calls, retries, decisions, and verification outcomes easy to inspect and use during debugging. Store masked payloads or safe metadata only, and test that trace outputs do not contain protected information.

### 4.9 Evaluation scripts

Automated scripts provide repeatable entity metrics, span checks, ICD-10 measures, abstention analysis, adversarial tests, and latency/call counts. A demo alone cannot establish that the SOW acceptance thresholds have been achieved.

## 5. Alternatives and Scope Decisions

| Decision | Proposed choice | Alternative | Reason |
|---|---|---|---|
| Core language | Python | Node.js | Direct fit for NLP and evaluation tooling |
| Schema | Pydantic | Manual JSON validation | Reusable typed validation |
| Orchestration | Explicit Python loop | Heavy agent framework | Easier to inspect and control |
| Lexical retrieval | SQLite FTS5 with BM25 ranking | Exact substring matching only | Full-text retrieval with relevance ranking |
| Retrieval approach | Keyword + semantic, subject to evaluation | Keyword-only | Potentially broader candidate retrieval |
| UI | Streamlit | React frontend | Faster local MVP development |
| Persistence | SQLite/local files | PostgreSQL service | No separate database server required |
| Deployment | Localhost | Cloud and multi-user deployment | Cloud deployment is excluded from current scope |

The MVP excludes OCR, scanned/handwritten note processing, procedure-code assignment, EHR or billing integration, cloud deployment, multi-user support, model fine-tuning, paid APIs, and GPU-dependent infrastructure. These follow the SOW scope boundaries.

## 6. Version and Compatibility Policy

The SOW does not prescribe exact package versions. Python 3.12.x and Pydantic 2.x are proposed starting points, not confirmed tested combinations. Pin exact versions after checking:

- Python/library compatibility.
- API SDK compatibility with the selected provider.
- ChromaDB and embedding-model compatibility.
- CPU and memory requirements.
- Reproducible dependency installation.

Do not label versions as tested unless they have actually been tested in the target environment.

## 7. Implementation Readiness Checklist

- [ ] Architecture and technology stack approved by Mirai Labs.
- [ ] Exact model IDs rechecked and accessible.
- [ ] Current free-tier quotas and rate limits recorded.
- [ ] Provider data-use terms reviewed and approved for this project.
- [ ] Extraction and verification schemas defined.
- [ ] Original-to-masked text offset mapping specified and tested.
- [ ] Keyword retrieval approach and embedding model selected.
- [ ] Trace outputs checked for protected information.
- [ ] Dependency versions tested and pinned.
- [ ] Gold-standard and evaluation procedures ready.

## 8. Final Recommendation

Begin evaluation with Groq openai/gpt-oss-20b for extraction and qwen/qwen3.8-27b for verification, provided Mirai Labs approves the applicable data-handling terms. Use Pydantic, an explicit Python agent loop, keyword and semantic ICD-10 candidate retrieval, local PHI masking, Streamlit, privacy-safe JSON tracing, and a repeatable evaluation harness.

Keep the model pair provisional until privacy approval, account-specific quota checks, and evaluation demonstrate that the configuration meets project requirements. Recheck model availability before implementation because provider model catalogues and free-plan limits can change.

## References

1. Mirai Labs, *Statement of Work: AI-Powered Clinical Note Extraction and Coding Agent MVP*, version 1.0, 13 October 2026.
2. Groq, [Supported Models](https://console.groq.com/docs/models).
3. Groq, [Rate Limits](https://console.groq.com/docs/rate-limits).
4. Groq, [Structured Outputs](https://console.groq.com/docs/structured-outputs).
5. Groq, [Your Data in GroqCloud](https://console.groq.com/docs/your-data).
6. Groq, [Model Deprecation](https://console.groq.com/docs/deprecations).
7. Google, [Gemini API Models](https://ai.google.dev/gemini-api/docs/models).
8. Google, [Gemini API Pricing and Data-Use Terms](https://ai.google.dev/gemini-api/docs/pricing).
9. Pydantic, [Official Documentation](https://docs.pydantic.dev/).
10. Streamlit, [Official Documentation](https://docs.streamlit.io/).
11. Chroma, [Official Documentation](https://docs.trychroma.com/).
12. spaCy, [Official Documentation](https://spacy.io/usage).
13. Python, [Official Documentation](https://docs.python.org/).

*Provider details were checked on 15 October 2026. Recheck them before implementation; documentation of availability is not project approval.*
