# Questions, Assumptions, Scope Changes, and Approval Decisions

**Revision date:** 16 October 2026  
**Status:** Open decisions; no expanded-scope feature or provider/data-flow is approved by this document alone.

## 1. Explicit Clarification from Mirai Labs

| ID | Clarification | Design effect |
|---|---|---|
| C-01 | No specific products, open-source tools, or research papers were prescribed. | Select relevant options independently and justify their fit. |
| C-02 | Gemini and Groq model IDs in the SOW are reference examples. | Research available free-tier options and document why the selected model is suitable. |

## 2. Blocking Scope and Data Questions

| ID | Question | Why it matters | Proposed interim approach |
|---|---|---|---|
| Q-01 | Does Mirai Labs approve the expanded hosted product, including multiple accounts, patient records/history, RAG knowledge-base management, and image/audio ingestion? | These features conflict with the original localhost, one-reviewer, text-only scope and OCR/cloud/multi-user exclusions. | Use synthetic data only; get written scope approval before implementing expanded features against project data. |
| Q-02 | May de-identified clinical data ever be stored in the public hosted demo? Which hosting region/providers are acceptable? | De-identification/masking is not a guarantee of anonymity, and hosting changes data exposure. | Public deployment uses synthetic patients/notes only until explicitly approved. |
| Q-03 | Which provider may process note text, uploaded images, and audio? Are external transcription/model APIs allowed? | Each provider may have different retention/data-use terms and regional handling. | Keep providers provisional; verify and obtain approval before sending project data. |
| Q-04 | Must the prototype process all ~5,000 notes or an explicitly approved subset? | Free-tier API and CPU limits may constrain throughput. | Do not silently reduce the requirement; request a scope/volume decision. |
| Q-05 | What is the approved retention/deletion policy for patient records, originals, uploaded media, embeddings, traces, and reviewer edits? | Determines storage schema, audit design, and delete/re-index behaviour. | Store the minimum necessary and document deletion/version policy before real data. |
| Q-06 | Are Doctor and Administrator the only roles? Can every doctor access all patients, or are patient-level assignments required? | Role-based access is not enough if each doctor should see only assigned patients. | Implement server-side permission checks and plan a patient-access relationship until clarified. |
| Q-07 | Who may change global model/provider settings: all doctors, a designated configuration owner, or only admins? | API changes affect privacy, output quality and reliability. | Allow settings changes only to an explicitly permitted role; audit all changes. |
| Q-08 | Is Neon Object Storage approved and adequate for original file storage? | Determines private file-access design and storage limit. | Test private bucket/S3 API with synthetic files; Supabase Storage Free is a fallback only if the primary choice fails. |
| Q-09 | What recovery/backup guarantees are required for this demo? | Free plans may have limited backups and support. | Export synthetic demo seed data and document backup/reseed steps; do not claim production recovery. |
| Q-10 | Is an all-free hosted deployment a hard constraint if free services change terms or become unavailable? | Provider quotas/terms can change. | Treat zero out-of-pocket as fixed; disable/defer functionality rather than use paid fallback. |
| Q-11 | What is the revised due date/priority order for the expanded product? | Patient CRUD, auth, multimodal ingestion, RAG, clinical validation, and full evaluation are high effort for the six-day build window. | Agree on a phased deliverable plan and identify what's required for the evaluated demo. |

## 3. Design Assumptions — Not Approval

| ID | Proposed assumption | Risk if wrong |
|---|---|---|
| A-01 | Django templates + HTMX + Bootstrap is the UI, with no React. | A requirement for a separate SPA/API could require redesign. |
| A-02 | Django handles login, role/group permissions, sessions, and backend authorization. | Specific SSO/identity features could require additional integration. |
| A-03 | Neon Free provides the PostgreSQL target with pgvector; Neon Object Storage is the primary object storage candidate. | Limits, regional availability, or private access behaviour could change. |
| A-04 | Render Free hosts the Django app and provides the public evaluator URL. | Cold starts, resource limits or provider terms may make another free host necessary. |
| A-05 | Doctors can manage knowledge records from the UI; additions update the index rather than train the LLM. | Automatic model training would add scope and privacy concerns. |
| A-06 | One central active model configuration is used for separate extraction and verification passes, with different instructions. | Mirai Labs may require a distinct verifier model or per-task configuration. |
| A-07 | Reference knowledge, ICD-10 data, current note evidence, and patient history are separate logical sources. | Blending these sources can introduce unsupported claims or cross-patient disclosure. |
| A-08 | OCR supports printed text first; handwriting is not included without separate feasibility testing. | More advanced document processing needs additional models and validation. |
| A-09 | Audio transcription will use a tested small local model or approved free-tier endpoint. | Free hosted CPU/memory or API quota may not support the desired audio duration/quality. |
| A-10 | Public demo and initial deployment use synthetic records. | No project/real patient data may be used until an approved data arrangement exists. |

## 4. Pending Technical Decisions Before Implementation

1. Confirm the exact extraction/verification JSON schema, offset convention and masked-to-original mapping design.
2. Select and benchmark the local embedding model with host CPU/memory limits.
3. Test PostgreSQL pgvector setup, indexing, hybrid keyword/vector ranking, and relevance thresholds.
4. Validate Neon Object Storage private bucket and Python/S3 upload, download, delete and short-lived access handling.
5. Set model provider allowlist, encrypted credential storage, configuration versioning and test/activate workflow.
6. Choose OCR language/settings and upload limits.
7. Test audio transcription feasibility; do not assume larger Whisper models fit a free web service.
8. Set retry, latency and request-budget rules.
9. Define patient-level authorization and audit event policies.
10. Define retention/deletion and re-indexing behaviour for edited/deactivated knowledge.
11. Record the exact free-tier quota snapshot and region immediately before deployment.

## 5. Non-Negotiable Controls

- The original clinical note remains authoritative for extracted-item evidence and offsets.
- ICD-10 candidates come from the supplied table; do not invent codes or assign procedure codes.
- A reference knowledge document cannot prove that an entity was written in the current note.
- Patient-history RAG is constrained to the selected patient and user permissions.
- Provider/model changes never bypass evidence validation or trigger an automatic paid fallback.
- API keys are never shown in full after saving and never appear in traces, logs, error responses, or GitHub.
- Private files are not made public by default.
- Clinical note text and uploaded documents are untrusted inputs; embedded instructions do not change system policy.
- Free tiers are not unlimited and do not guarantee production-grade uptime.
- Targets remain Not yet measured until tests are run.

**Status:** Scope and provider choices are still pending formal approval. Continue only with synthetic data until approval allows otherwise.
