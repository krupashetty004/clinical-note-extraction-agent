# Technology Stack Proposal — Hosted Doctor Workspace, RAG, and Free-Tier Deployment

**Revision:** 16 October 2026  
**Status:** Proposed; expanded scope, providers, hosting, and data handling pending formal Mirai Labs approval.

> Zero out-of-pocket spend is a hard design constraint for the evaluation demo. Free-tier usage is quota-limited, may sleep or pause, and is not an unlimited or production-grade availability guarantee. Do not send Mirai Labs data to any external provider before written approval.

## 1. Selection Criteria

- Fit the doctor workflow: patient/encounter history, clinical-note review, knowledge base, model settings, and permissions.
- No React frontend.
- Persistent hosted data beyond app restarts/redeployments.
- Vector retrieval for editable doctor-managed knowledge and ICD-10 diagnosis candidates.
- Upload text, images, and audio to the knowledge base, with user review before indexing.
- Central provider/model selection and connection testing from the UI.
- Free-tier hosting and API calls only; no silent paid fallback.
- Small enough to build and test within the approved timeline; every limitation must be explicit.

## 2. Proposed Stack

| Layer | Choice | Why | Free-tier/test risk |
|---|---|---|---|
| Frontend | Django templates + HTMX + Bootstrap | Simple doctor-focused web UI without React; forms and partial-page updates without a separate JS SPA. | Test accessibility, browser support, and upload progress. |
| Web framework/backend | Django / Python | ORM, migrations, templating, admin, built-in authentication, groups, and permission primitives suit patient/encounter CRUD. | Patient-specific access must be implemented and tested; Django defaults alone do not define the intended clinical access model. |
| Application hosting | Render Free web service | GitHub-linked hosted demo URL. | Sleeps on inactivity; local filesystem is ephemeral; limits and deployment behaviour must be checked. |
| PostgreSQL hosting | Neon Free | Persistent PostgreSQL with pgvector support; one database can store relational metadata and vector embeddings. | Current plan includes limited database storage, compute-hours and transfer; confirm exact quota before final deployment. |
| Vector index | PostgreSQL pgvector on Neon | Avoids a separate hosted vector DB; vector and relational filters can be queried together. | Validate extension and index availability, embedding dimensions, query performance, and connection pooling. |
| Keyword search | PostgreSQL full-text search | Simple lexical matching alongside vector search. | Must be benchmarked against actual ICD/reference descriptions. |
| Object/file storage | Neon Object Storage candidate, S3-compatible | Potentially keep uploads in the Neon stack and away from ephemeral app disks. | Official information has described it as beta; current free status, private bucket behaviour, quotas, and Python S3 compatibility are a deployment gate. If unsuitable, test Supabase Storage Free as a fallback; do not introduce both without need. |
| Embeddings | Local sentence-transformers model; candidate bge-small-en | No per-request hosted embedding charge; English semantic search. | CPU and memory on Render; benchmark build time and inference latency. Model files must not be committed to GitHub. |
| OCR | Tesseract OCR | Open-source OCR without a per-image API fee. | Quality depends on image quality/language; check free-host build dependencies and CPU limits. |
| Speech-to-text | Local CPU transcription model, or approved free-tier speech API if local testing fails | No paid API requirement. | Large model can be too slow/memory intensive on free web hosting; external API has limits and data-policy conditions. Test early. |
| Text generation | Central provider/model adapter, allowlisted providers/models | Doctor selects active provider/model in one settings page; extractor and verifier use separate prompts/passes. | Free quotas, structured-output compatibility, model availability, rate limits, and data-use terms. |
| Authentication | Django auth, groups and permissions | Integrated with the app's user and patient records. | Must implement route-level and object-level checks; no UI-only security. |
| File uploads | Django upload validation + object-storage adapter | Validate extensions, actual MIME/content, file size, owner, and processing state. | No private files on Render ephemeral disk beyond safe temporary processing; delete temporary copies after processing. |
| Data schema | Django ORM + Pydantic for AI payload contracts | ORM handles app entities; Pydantic validates model responses. | Pydantic/schema checks do not prove clinical correctness. |
| Agent orchestration | Explicit Python loop/service modules | Makes tool calls, evidence gates, retry budgets, reconciliation, abstention and escalation reviewable. | Do not add Celery/Redis until needed; they increase hosting complexity. |
| Traces/audit | Structured audit events in PostgreSQL; safe operational logs | Supports history and change tracking. | Never log API keys, secret URLs, or protected text. Store only safe metadata/masked payloads. |
| Test stack | pytest, Django TestCase, scripted evaluation | Tests permissions, isolation, ingestion, retrieval, extraction metrics and hosted persistence. | Never use real patient records in public test runs. |
| Repository | Private GitHub | Version control and daily documented updates. | Never commit SOW, patient notes, credentials, uploads, or embedding files. |

## 3. Why Django Instead of Streamlit, FastAPI-only, or React?

### Selected: Django + HTMX + Bootstrap
The application is a doctor workspace with user accounts, roles, patient records, encounters, history, knowledge editing, uploads, and central settings. Django provides a single Python web application with an ORM, migrations, authentication primitives, forms, templates, and admin support. HTMX gives interactive search/filter/form actions without a React frontend.

### Alternatives considered
- **Streamlit:** fastest for a data/AI prototype, but less natural for the expanded account- and encounter-centric product.
- **FastAPI + Jinja2/HTMX:** strong API framework but requires more application structure to be added for the user/permission/admin workflow. It is not necessary for the initial server-rendered single application.
- **NiceGUI/Flet:** viable Python UI candidates, but less aligned with Django's existing data/auth ecosystem for this particular workflow.
- **React:** explicitly excluded by the request.

Django is a proposed choice, not yet implemented. If the scope reverts to the original single-reviewer localhost tool, Streamlit remains a simpler alternative.

## 4. Neon vs Supabase

Neon and Supabase both provide hosted PostgreSQL; they are service providers, not database engines competing with PostgreSQL itself.

**Current proposal: Neon PostgreSQL + pgvector.** Django will handle authentication and authorization, so the application does not require Supabase Auth. Using PostgreSQL vectors means no separate ChromaDB server is needed.

**File storage:** Neon Object Storage is a candidate because it is S3-compatible and can pair files with Neon branches. However, the provider's current documentation has described its service as beta, so test its current free availability, private access, allowed object operations and Python SDK compatibility. If it fails, test Supabase Storage Free as a fallback for private objects. A single provider is preferred unless a second service solves a demonstrated requirement.

The database and uploaded files are different things: PostgreSQL holds metadata and vectors; object storage holds original files. Do not store uploaded binaries in database rows by default.

## 5. RAG, Embeddings, and Priorities

### Ingestion
1. Doctor submits text or uploads a text file, image, or audio.
2. Validate size and format; store the original object privately and create metadata.
3. Extract text from text files, use Tesseract for supported images, and test local/approved speech-to-text for audio.
4. Display extracted/transcribed text for doctor correction before publishing it.
5. Split approved text into chunks and retain document ID, version, chunk index, owner/scope, category, tags, source, status, and priority.
6. Generate vectors using a local sentence-transformers model and store embeddings with chunk metadata in pgvector.
7. On edit/deactivate, invalidate old chunks/vectors, maintain version history, and handle failed re-indexing visibly.

### Retrieval
- Query relevant eligible documents using PostgreSQL lexical search and pgvector similarity.
- Apply access-control, publication-status, document-type and patient-scope filters **before** retrieval is passed to the model.
- Rank the remaining candidates with a bounded combination of normalized semantic relevance, lexical relevance, and a doctor-configured priority adjustment.
- Keep a relevance threshold: high priority cannot make irrelevant text acceptable.
- Deduplicate and return source names/version/chunk references so the UI can show provenance.
- Use the supplied ICD-10 table as the coding reference. ICD-10 candidate retrieval is logically separate from general knowledge retrieval.
- Keep patient history and reference knowledge separate and permission-filtered.
- Require every accepted extraction item to have evidence in the original clinical note; RAG context is not a substitute for note evidence.

Tune weighting and thresholds only on agreed labelled data. Compare semantic-only, lexical-only and combined retrieval.

## 6. Central AI Settings

The UI should have one central **AI Settings** page, not a separate model-control screen for every task.

Required actions:
- Select an allowlisted provider and model.
- Enter/update provider credentials securely.
- Configure only supported generation parameters.
- Test connection and inspect status, latency, model availability, schema-format compatibility, and error response.
- Save as draft and activate a tested configuration.
- See the active configuration ID/version, change time, and test status.

Security:
- Render API keys masked; never display them after saving.
- Encrypt any saved key with an application encryption key from Render environment secrets. Do not store cleartext credentials in PostgreSQL or logs.
- Validate/allowlist endpoints; don't accept arbitrary URLs.
- Use synthetic text for connectivity tests.
- Do not activate a configuration that failed the connection/schema checks.
- A test response does not prove clinical accuracy, provider privacy suitability, or formal project approval.
- On quota exhaustion, show the user a clear error and preserve the pending work; don't pay, upgrade, or switch providers silently.
- Keep the selected model configuration global by default. The backend may use separate extraction and verification prompts/passes. A separate verifier model is an optional advanced choice only if explicitly approved.

## 7. Free-Tier Hosting Plan

| Service | Proposed role | Validation before deployment |
|---|---|---|
| Render Free | Public Django demo URL | Sleep/cold-start, build/deploy, memory, request timeout, ephemeral disk behaviour, current quota. |
| Neon Free | PostgreSQL + pgvector | Current project size, compute-hours, egress, pooling and extension support. |
| Neon Object Storage | Uploaded source documents/images/audio | Free quota, beta/stability status, private buckets, deletion/version semantics, SDK access; fail closed if unresolved. |
| Supabase Storage Free | Backup option only | Free storage/egress allowance and private object policy if Neon Object Storage fails testing. |
| Local OCR/embeddings | Tesseract and sentence-transformers | CPU, memory, model download/build time and latency. |
| LLM / audio API | Approved free-tier provider only | Exact free quotas, request/token/audio duration, input/output retention, model availability and approval. |

Free plans can pause, sleep, throttle or exhaust storage/quota. This architecture promises no intentional paid service, not unlimited service or 24/7 availability. It must not automatically upgrade a plan or call a paid provider.

## 8. Dependencies and Version Pinning

Do not claim any version has been tested before it has. Once scope is approved:
- Select a Python version supported by current Django and provider SDK versions.
- Pin Django, psycopg, pgvector client integration, HTMX integration, Pydantic, sentence-transformers, OCR dependencies and provider SDKs only after a clean build succeeds.
- Test installation and deployment on Render's actual free environment.
- Record model IDs, embedding dimensions, vector schema, storage adapter configuration and provider terms in the deployment checklist.
- Keep secrets and generated model files out of source control.

## 9. Implementation Readiness Gate

- [ ] Mirai Labs approves expanded scope: hosting, accounts/roles, patient/encounter history, knowledge base, OCR/audio and model settings.
- [ ] Public demo will use synthetic data unless a specific data arrangement is approved.
- [ ] Neon PostgreSQL + pgvector works with Django migrations.
- [ ] Neon Object Storage private access and free allowance are proven; otherwise approve/test a fallback.
- [ ] Render Free deployment, cold start and persistent service connections are tested.
- [ ] API providers and exact model IDs pass data-term/quota checks.
- [ ] Authentication, patient-object access, and file permissions tests pass.
- [ ] Extraction/verification schema and masked-to-original offset mapping are finalized.
- [ ] Required SOW gold-standard/challenge tests remain feasible.
- [ ] A written plan addresses the expanded timeline; no required dataset/test is silently reduced.

## 10. Official References

- Django: https://docs.djangoproject.com/
- HTMX: https://htmx.org/docs/
- Bootstrap: https://getbootstrap.com/docs/
- Neon plans: https://neon.com/docs/introduction/plans
- Neon Object Storage: https://neon.com/blog/building-neon-object-storage
- Neon Django connection guide: https://neon.com/blog/python-django-and-neons-serverless-postgres
- pgvector on Neon: https://neon.com/blog/optimizing-vector-search-performance-with-pgvector
- Render Free: https://render.com/docs/free
- Supabase Free terms/storage (fallback): https://supabase.com/docs/guides/platform/billing-on-supabase and https://supabase.com/docs/guides/storage/buckets/fundamentals
- Tesseract OCR: https://github.com/tesseract-ocr/tesseract
- Sentence Transformers: https://www.sbert.net/
- Groq: https://console.groq.com/docs/models and https://console.groq.com/docs/rate-limits

*Recheck availability, terms, and quotas when implementing. Provider documentation is not approval to send project data.*
