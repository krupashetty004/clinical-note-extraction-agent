# Technology Stack Options and Rationale (Draft)

> Final provider/model selection is **pending verification of current availability, free-tier limits, and Mirai Labs approval**.

## 1) Decision Criteria

| Criterion | Why It Matters |
|---|---|
| Structured output reliability | Needed for strict schema + evidence fields |
| Free-tier viability | Required by project constraints |
| Privacy controls | Must support local PHI masking before external calls |
| Observability | Needed for tool/model traceability and reviewability |
| Local reviewer UX speed | Required for practical human validation |

## 2) Proposed Stack Candidates (Planning)

| Layer | Candidate Options | Pros | Risks/Unknowns |
|---|---|---|---|
| Core language/runtime | Python | Strong NLP/data ecosystem, fast prototyping | Runtime/perf tuning later |
| Schema validation | Pydantic | Clear typed contracts and validation errors | Version-specific APIs to confirm |
| Orchestration | Lightweight agent workflow in Python | Flexible for retries/reconciliation | Complexity if over-engineered |
| Lexical retrieval | BM25-like / TF-IDF style indexing | Transparent and cheap | May miss semantic matches |
| Semantic retrieval | Embedding-based similarity | Better paraphrase handling | Free-tier model/index limits |
| Local reviewer app | Streamlit or Gradio (local mode) | Rapid local interface iteration | UI scalability limits |
| Storage/logging | Local JSON/SQLite traces | Simple audit trail | Need retention policy clarity |

## 3) Provisional Recommendation (Not Final)

| Area | Provisional Choice | Reason |
|---|---|---|
| Language | Python | Best fit for schema + NLP workflow in MVP timeline |
| Schema | Pydantic-style strict models | Direct match to SOW structured-schema requirement |
| Retrieval | Hybrid keyword + semantic | Required by SOW for ICD-10 candidate generation |
| UI | Local lightweight web UI | Aligns with local reviewer requirement |

## 4) Provider/Model Selection Status

| Topic | Status |
|---|---|
| External LLM provider | Pending policy/compliance confirmation |
| Model IDs | Pending real-time availability verification at implementation start |
| Embedding model | Pending free-tier and quality checks |
| Rate limits/cost envelope | Pending empirical measurement |

## 5) Non-Approved Items

No stack item in this document constitutes final approval. All choices are proposals for architecture review and can change based on Mirai Labs decisions and verified constraints.
