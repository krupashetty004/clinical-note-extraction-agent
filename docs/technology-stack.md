# Technology Stack Proposal — Hosted, Zero-Cost Doctor Workspace

**Revision date:** 16 October 2026  
**Status:** Proposed, pending Mirai Labs approval and free-tier smoke testing  
**Cost constraint:** ₹0 out-of-pocket for the evaluation demo; no paid services, paid APIs, or silent paid fallback.

> This proposal records a materially expanded scope compared with the original SOW. It does not constitute permission to process Mirai Labs clinical data in a hosted environment. Use synthetic data until written approval covers scope, hosting, and provider/data handling.

## 1. Design Goals

- Build the UI around the doctor's workflow, not around AI subcomponents.
- Avoid React. Use server-rendered Django templates with HTMX and Bootstrap.
- Provide a hosted link that an evaluator can open.
- Persist database records and uploaded files outside the hosted web service's ephemeral filesystem.
- Use one managed PostgreSQL service for relational data and vector search where feasible.
- Allow doctors (subject to permissions) to manage the knowledge base and configure/test the active AI provider/model from one central settings page.
- Use only free-tier resources and open-source local components where practical.
- Make quota, cold-start, storage, and provider failures visible; do not upgrade or switch to a paid service automatically.
- Preserve the original SOW's evidence offsets, independent verification, abstention, trace safety, evaluation targets, and scope limitations unless Mirai Labs formally changes them.

## 2. Recommended Zero-Cost Stack

| Layer | Recommended technology | Why it fits | Constraint / validation |
|---|---|---|---|
| Frontend | Django templates + HTMX + Bootstrap | No React; simple, responsive dashboard, data tables, filters, and form interactions with modest frontend complexity | Implement accessible pages and verify on the final hosted service |
| Application/backend | Django / Python | ORM, migrations, authentication, groups/permissions, admin UI, forms, and server-side pages are useful for patient/encounter management | Enforce access in views/services and querysets, not just the UI |
| Hosted web application | Render Free web service | Produces a publicly reachable demo URL from GitHub | Sleeps after 15 minutes idle; cold start can take about a minute; filesystem is ephemeral; monitor monthly free limits |
| Database engine | PostgreSQL | Relational persistence for users, patients, encounters, note metadata, knowledge records, and audits | Use a managed hosted instance rather than an on-disk DB file |
| PostgreSQL host | Neon Free | Serverless PostgreSQL with scale-to-zero and documented free quota; independent of the app's filesystem | Current official docs/blog checked 16 Oct 2026: up to 100 projects, 100 CU-hours per project/month, 1 GB DB storage/project and 5 GB public network transfer/project/month. Recheck at setup |
| Vector search | pgvector extension on Neon PostgreSQL | Stores embeddings beside source metadata; avoids a separate vector database service | Enable/test the `vector` extension and benchmark retrieval quality |
| Keyword search | PostgreSQL full-text search | Supports lexical search alongside semantic similarity in one DB | Establish ranking, filters, and search fallback tests |
| Object/file storage | Neon Object Storage (S3-compatible) | Stores original text files, images, and audio independently of Render; listed at 5 GB per project in Neon Free plan documentation | Test private bucket behaviour and Python/boto3 upload/download/signing on the actual project. Do not make files public by default |
| File storage fallback | Supabase Storage Free, only if Neon storage fails acceptance tests | Known managed private object-storage alternative | Adds a second provider/project. Current documented free allowance is 1 GB; confirm policies and quota before use |
| Embeddings | Local sentence-transformers model; candidate bge-small-en | Avoids paid embedding endpoint | Measure CPU, memory, cold-start/build time, embedding dimensions, and retrieval relevance on the target host |
| AI text generation | Configurable provider/model adapter using approved free-tier inference | Allows central model selection from the UI without hardcoding a provider in workflow code | Provider selection/data terms/availability/quotas must be approved; no paid fallback |
| Image ingestion | Tesseract OCR | Open-source, no per-image API payment | Printed text only for initial support; check language, quality, CPU/memory and timeout limits. Handwriting is not promised |
| Audio ingestion | Local CPU speech-to-text candidate, or an explicitly approved free-tier API | Supports doctor-uploaded voice notes into the knowledge base | Whisper-family local models can be too costly for small hosting memory/CPU; benchmark a tiny model before commitment. External transcription requires data approval and quota handling |
| Structured schema | Pydantic | Validates extraction/verification response structure | Must supplement with evidence, offset, status, and meaning checks |
| Agent control | Explicit Python orchestration loop | Makes tool calls, retries, reconciliation, accept/reject/abstain decisions and escalation auditable | Bounded retries, per-note call/time budget, no hidden provider switch |
| Local privacy processing | Deterministic patterns plus spaCy NER or a tested local detector | Detects likely identifiers before approved external calls | Cannot guarantee perfect de-identification; test false negatives and preserve offset mapping |
| Credential management | Environment secrets + application-level encryption for any editable stored credentials | Protects provider API keys | Never store plaintext keys, expose them back to the UI, commit them, or log them. Use a documented allowlist of providers/endpoints |
| Audit and trace | Structured events persisted in PostgreSQL, with masked data/safe metadata only | Supports review history, model configuration versioning, and debugging | No protected raw-note content, API key, or long-lived private storage URL in operational logs |
| Tests | pytest / Django tests + repeatable evaluation scripts | Tests user access, data persistence, extraction, retrieval, and acceptance targets | Results must be measured; do not mark pending targets as achieved |
| Source control | Private GitHub repository | Documentation and code change history | No SOW, datasets, patient notes, credentials, or private uploads in Git |

## 3. Why Django Instead of Streamlit or a React SPA?

**Django + HTMX + Bootstrap is the current recommendation.**

- Django provides the application foundation needed for accounts, roles, database-backed patient records, encounter history, admin tasks, and form processing.
- HTMX can update tables, filters, and selected page fragments without building a separate React frontend.
- Bootstrap offers common dashboard layout components without introducing a large frontend build pipeline.
- Render has documented support for deploying Django applications as free web services.
- Streamlit remains useful for an isolated NLP experiment or fast internal demo, but the expanded multi-page, user-managed application fits a conventional web framework more naturally.
- FastAPI remains a good alternative for API-first architectures, but would require assembling more of the user, role, admin, and page-management features separately. A separate FastAPI service is not required initially; avoid extra moving parts.

## 4. Why Neon Instead of Supabase for the Database?

Neon and Supabase both offer managed PostgreSQL; PostgreSQL is the database engine, while Neon is the hosting provider selected here.

Neon is the primary choice because:
- It provides managed PostgreSQL, scale-to-zero compute, pgvector support, and—per the latest official documentation—S3-compatible Object Storage in the same provider.
- The current free plan is documented as including 1 GB of PostgreSQL storage and 5 GB of Object Storage per project, plus 100 CU-hours and 5 GB of monthly public network transfer.
- Django will own authentication and application authorization. We therefore do not need Supabase Auth to run this app.
- Using Neon database + Neon object storage keeps the prototype simpler than adding a second managed-storage provider.

**Fallback:** Test Neon Object Storage integration and private access first. If it cannot satisfy requirements in the actual deployment, use Supabase Storage Free as a separately documented fallback; do not switch the primary database from Neon. Recheck current limits before deployment because free-tier terms can change.

Official provider references (reviewed 16 Oct 2026):
- Neon Free plan updates: https://neon.com/blog/neon-free-plan-1-gb-per-project
- Neon backend and Object Storage: https://neon.com/blog/neon-backend-is-ga
- Neon Object Storage: https://neon.com/blog/building-neon-object-storage
- Neon pgvector: https://neon.com/blog/optimizing-vector-search-performance-with-pgvector
- Render Free service constraints: https://render.com/docs/free
- Supabase billing/Storage quota fallback: https://supabase.com/docs/guides/platform/billing-on-supabase and https://supabase.com/docs/guides/storage/pricing

## 5. Model Settings — Centralised, Not Per-Task Controls

The doctor UI should expose one central **AI Settings** page rather than ask a doctor to configure an unrelated model control for every processing task.

Required controls:
- Provider and model selection from an allowlist.
- Secret input field; show only a masked value after saving.
- Supported parameters with safe defaults and bounds.
- Test Connection / Test Response using synthetic input.
- Save Draft and Activate Configuration actions.
- Current active provider/model, last test result, test time, latency, and errors.
- Configuration version and actor/time metadata.
- Visible message for rate limits, unsupported IDs, malformed JSON, or unavailable providers.

The active model can be called with different instructions for extraction and verification in separate passes. A distinct verifier model is not selected per task unless Mirai Labs explicitly requires it.

For credentials, encrypt any persisted key with an application encryption key stored separately in deployment environment secrets; never store or log the raw key. Prevent arbitrary endpoints and SSRF by allowlisting providers/hosts. A successful ping/response check is not proof of clinical accuracy or provider approval.

## 6. Dynamic Knowledge Base and RAG

Knowledge must be managed through the UI and persisted in the database/storage; do not hardcode reference content.

Ingestion sources:
- Typed text and supported text files.
- Images -> Tesseract OCR -> doctor preview/correction.
- Audio/voice -> tested local speech-to-text or approved free API -> doctor preview/correction.

Only doctor-reviewed and published material becomes eligible for retrieval. Store source file, source/title, owner, type, tags, category, priority, status, version, extracted text, and indexing state. Chunk the approved text, generate local embeddings, and store vectors plus metadata in pgvector. Edits/deactivation must invalidate or refresh stale chunks.

Retrieval:
1. Apply patient/knowledge permissions and content status filters first.
2. Search full-text/keywords and vectors.
3. Deduplicate, rank and apply doctor-set priority as a bounded tie-break or calibrated factor.
4. Apply relevance threshold; priority must not make irrelevant text appear relevant.
5. Return source and chunk identifiers with the context.
6. Keep reference-knowledge context distinct from original-note evidence and from patient history.

Do not auto-train the model on newly uploaded data. Adding a document updates the knowledge index; it does not change the model's weights.

## 7. Logical Data Model

- **User/DoctorProfile:** Django user identity, group/role, activation status.
- **Patient:** internal identifier and only necessary profile fields.
- **PatientAccess:** access grants where doctor-specific patient access is required.
- **Encounter:** patient, visit date/status, creating doctor.
- **ClinicalNote:** encounter reference, immutable original content/version, source, creation time.
- **ExtractionRun:** note/version, active config version, model identifier, status, latency, call count, trace ID.
- **ExtractedItem:** category, text/value, attributes/status, evidence, original offsets, ICD candidates, verification outcome, review decision.
- **KnowledgeDocument:** title, owner, source file key, file type, category/tags, priority, version, publication/index status.
- **KnowledgeChunk:** document/version, chunk position/text, pgvector embedding, metadata and provenance.
- **ICDCode:** supplied table's code/description and source/version.
- **AIConfiguration:** provider/model ID, supported parameters, encrypted secret reference, test status, active version, updater/time.
- **AuditEvent:** safe actor/action/resource/time metadata with no secrets or raw protected content.

Schema, retention, access, and indexes must be tested with synthetic records before real data.

## 8. Zero-Cost Hosting Limitations

The target is zero out-of-pocket cost for a bounded evaluation demo—not unlimited or production-grade hosting.

- Render Free services spin down after 15 minutes without traffic, may take about a minute to wake, and have ephemeral storage. The app must not store uploads or SQLite data on its local filesystem.
- Neon Free (official details reviewed 16 Oct 2026) lists 1 GB database storage/project, 100 CU-hours/project/month, and 5 GB public network transfer/project/month. Compute scales to zero after inactivity.
- Neon Object Storage Free allowance is documented as 5 GB/project. Confirm private bucket configuration and actual project quotas before using it.
- Provider LLM, audio API, bandwidth and hosting limits can throttle service. If quota is exhausted, defer the operation and show a clear error.
- Do not add paid upgrades, paid APIs, or automated paid fallbacks. Set usage checks and keep upload/audio limits small enough for the demo.
- Use synthetic patient data for the public hosted evaluation unless project data handling is explicitly approved.

## 9. Implementation-Readiness Checklist

- [ ] Mirai Labs approves expanded scope (hosted app, multiple roles, patient records, image/audio ingestion, managed storage and knowledge-base RAG).
- [ ] Render and Neon free plan terms/current usage checked; no payment path or paid fallback configured.
- [ ] Neon PostgreSQL connection, pgvector extension and Django migrations pass.
- [ ] Neon Object Storage private upload/download/signing tested from Python/boto3; fallback decided only if necessary.
- [ ] Doctor/Administrator permissions and patient-level access tests pass.
- [ ] Synthetic patient/encounter data survive restart and redeploy tests.
- [ ] Knowledge CRUD/version/deactivation and re-indexing pass.
- [ ] OCR/audio components tested against actual free host CPU/memory limits.
- [ ] Model provider terms approved before any project note/media is sent externally.
- [ ] Secrets, private files, traces, logs, and Git repository checked for leakage.
- [ ] Gold-standard annotation and challenge sets meet original SOW minimum sizes.
- [ ] Deployment URL and synthetic evaluator credentials documented securely.

## 10. Decision Status

| Decision | Current proposal | Status |
|---|---|---|
| Frontend | Django templates + HTMX + Bootstrap; no React | Proposed |
| App hosting | Render Free | Proposed, deployment test pending |
| Relational DB | Neon PostgreSQL Free | Proposed |
| Vector DB | pgvector within Neon PostgreSQL | Proposed |
| File storage | Neon Object Storage Free | Proposed, private-access test pending |
| File fallback | Supabase Storage Free | Contingency only |
| Embeddings | Local sentence-transformer candidate | Needs benchmark |
| OCR | Tesseract | Needs benchmark |
| Voice transcription | Local CPU or approved free-tier endpoint | Needs feasibility/approval |
| LLM provider/model | Configurable allowlisted adapter | Pending Mirai Labs approval |
| Auth | Django auth + groups/permissions | Proposed |
| Production clinical data use | Not permitted until approval | Blocking gate |

**Status:** Proposed architecture only. Exact model/provider, file-storage integration, versions, quota observations, and implementation results are not yet validated.
