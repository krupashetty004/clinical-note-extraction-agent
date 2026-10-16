# Requirements Baseline and Proposed Scope Revision

**Project:** AI-Powered Clinical Note Extraction and Coding Agent  
**Revision date:** 16 October 2026  
**Status:** Revised product proposal; expanded scope and technology choices pending Mirai Labs approval.

> This document separates the original Statement of Work (SOW) from the requested product expansion. The new hosted doctor workspace, persistent patient records, role-based access, and multimodal knowledge ingestion conflict with parts of the original MVP scope. Do not assume the scope change is approved until Mirai Labs confirms it in writing.

## 1. Original SOW Requirements — Preserve Unless Formally Changed

The original SOW remains the source of truth for these requirements:

- Accept English free-text clinical notes supplied by Mirai Labs.
- Extract diagnoses, medications, procedures, allergies, and vital signs/key measurements.
- Return supporting evidence and character offsets into the exact original note.
- Validate structured output; a valid schema alone does not prove the claim is correct.
- Retrieve and rank ICD-10 diagnosis candidates from the supplied code table using keyword and semantic retrieval; allow a no-confident-match outcome.
- Extract procedure mentions, but do not assign procedure codes.
- Run a separate verification pass for evidence support, original offsets, status, contradictions, and likely omissions.
- Use a real, explicit agent/orchestrator loop with tool calls, bounded retries, reconciliation, abstention, human review, and safe traces.
- Keep protected information out of traces, logs, demos, and repository commits.
- Compare the proposed system with a naive single-prompt baseline.
- Label at least 100 notes across at least 10 specialties before prompt tuning.
- Preserve the SOW's entity, coding, contradiction, rare-diagnosis, adversarial, latency, and error-analysis acceptance targets in docs/evaluation-plan.md.
- The original SOW excluded OCR/scanned or handwritten notes, cloud/multi-user deployment, EHR/billing integration, fine-tuning, paid API keys, and GPU-dependent infrastructure.

## 2. Proposed Scope Expansion — Requested on 16 October 2026

These requirements are an expanded product proposal and must be confirmed with Mirai Labs before implementation.

### 2.1 Hosted doctor workspace

- Provide a publicly reachable hosted demo URL using only free tiers.
- Use a simple, responsive dashboard with a sidebar and a small number of clear sections.
- Provide separate pages for dashboard overview, patients, encounters/clinical notes, knowledge base, activity/history, and AI/system settings.
- Do not use React. The proposed UI is Django templates + HTMX + Bootstrap.
- Use real persisted data and database-backed lists; do not hardcode patient lists, knowledge-base entries, models, or dashboard counters.

### 2.2 Accounts, roles, and access controls

- Authenticate users before exposing patient or knowledge records.
- Proposed initial roles: Doctor and Administrator. Confirm whether more roles are needed.
- Doctors can access only patients and records they are authorized to see.
- Doctors can work with patient records, encounter history, notes, review results, the knowledge base, and the central AI configuration according to granted permissions.
- Administrators can manage accounts and role assignments, system-wide settings, and audit activity.
- Enforce authorization in backend views/services and database queries, not only by hiding UI elements.
- Audit important changes to patient records, knowledge items, roles, and AI settings.

### 2.3 Patient and encounter management

- A doctor can search and open authorized patient records.
- A patient record separates current encounters from previous encounters.
- Each encounter has its own clinical notes, extraction runs, review outcomes, and timestamps.
- Previous AI results remain historical; a new result must not silently overwrite the record of a previous encounter.
- Display the source and date for information from previous encounters.
- Patient-history retrieval must be scoped to the currently authorized patient; cross-patient retrieval is prohibited.
- Do not automatically convert a historical mention into a current diagnosis or medication.

This adds patient-record management beyond the original SOW's note-extraction MVP and requires explicit scope approval.

### 2.4 Editable multimodal knowledge base and RAG

- Doctors can add knowledge through the UI; the knowledge base must not be a hardcoded Python list or static collection.
- Accept text entered in the UI and supported text-file uploads, plus PDF documents (including multi-page PDFs) in the knowledge base.
- Accept image uploads and PDF files. Extract selectable text from normal PDFs first; use page-by-page OCR only for scanned/image-only PDF pages or image uploads. Show extracted text for doctor preview and correction before publication.
- Accept audio/voice uploads and transcribe them using an approved free-tier speech-to-text provider or a tested local option; show the transcript for doctor review before publication.
- Keep the original uploaded file (including PDF) in private object storage and keep source metadata, extracted text, page-level provenance where relevant, versions, status, and permissions in the database.
- For PDF extraction, use a simple two-stage flow: parse selectable text first (candidate: pypdf); if a page yields little/no text, render only that page to an image (candidate: pdf2image + Poppler) and run Tesseract OCR. Preserve page numbers in the extracted-text metadata.
- Enforce configurable file-size and PDF page-count limits, processing timeouts, and safe failure states. Do not publish if extraction fails or OCR output has not been reviewed.
- Let doctors review and correct extracted/transcribed text before publishing it to searchable knowledge.
- Chunk approved text, create embeddings, and store vectors in PostgreSQL with pgvector.
- Support keyword and semantic retrieval, metadata filters, source citations, and doctor-defined priority.
- Doctors can create, edit, version, deactivate, and re-index knowledge items.
- Retrieval priority can influence ranking but cannot make an irrelevant or unsafe passage valid evidence.
- Maintain separate logical scopes for reference knowledge and patient-specific history. Do not mix the two sources without explicit access filtering.
- A reference document can provide context, but it must not be treated as proof that an entity appears in a patient's original note.

### 2.5 Central AI/model settings — one simple place in the UI

- Provide a central AI Settings page rather than exposing separate model configuration controls for every clinical task.
- Authorized doctors can select an available provider/model, enter or update API credentials, set supported parameters, test the connection, and activate the selected configuration.
- Default behaviour: the active global model configuration is used by the extraction and verification workflow in separate, differently instructed calls. An independently configured verifier model is not part of the initial UI unless approved as an additional requirement.
- Test with synthetic/non-sensitive sample input before activation.
- Check connectivity, model availability, response status, JSON/schema compatibility where required, latency, and returned errors.
- Mask API keys in the UI, encrypt stored provider credentials using an application encryption key held in deployment environment secrets, and never log credentials.
- Allowlist supported providers/endpoints; do not permit arbitrary URLs that could create server-side request forgery or other security issues.
- Record who changed the configuration, when it changed, the selected provider/model, and test outcome—but never record the API key itself.
- A successful connection test confirms only that a response was returned; it does not establish clinical quality.
- Model changes must not silently bypass evidence validation, verifier checks, or evaluation requirements.

### 2.6 Free-tier and deployment requirements

- Target zero out-of-pocket cost for the evaluation deployment. Use free-tier hosting, managed storage/database allowances, open-source components, and free-tier model calls only.
- Proposed deployment: Render Free web service + Neon Free PostgreSQL/pgvector and Neon Object Storage. Official Neon material checked 16 October 2026 lists Object Storage as generally available, S3-compatible, and 5 GB/project on Free. Validate actual quota, private-bucket access, and Python/S3 integration before use. If those checks fail, evaluate Supabase Storage Free as a fallback without changing the Neon database choice.
- Use PostgreSQL as the hosted persistence target. SQLite may be used for local tests only; do not depend on SQLite or uploaded files on the hosted application's ephemeral filesystem.
- Use local/open-source embeddings and Tesseract OCR where they fit the host resource limits.
- Audio transcription may use an approved free-tier API or a tested local CPU option. This component is a hosting/quota feasibility risk and must not be described as unlimited or guaranteed until tested.
- Handle sleeping app cold starts, rate limits, free-tier storage limits, possible free-project pausing, and provider outages.
- Do not add a paid service, paid API key, billing requirement, or automatic paid fallback.
- If a free quota is exceeded, pause/defer the operation and show a clear error. Never silently switch providers.
- A free tier does not promise unlimited availability or indefinite free service. Recheck terms and quotas at deployment time.

### 2.7 Privacy and demonstration

- Public hosted demos must use synthetic patient data by default.
- Do not place confidential SOW content or clinical records in the public or private code repository.
- Do not send Mirai Labs notes, patient data, uploaded images, or audio to an external provider until both the provider data terms and the exact use case are approved.
- De-identification/masking does not guarantee that every identifier is removed.
- Store uploaded files in private buckets, apply access checks, enforce upload size/type limits, and avoid exposing public object URLs.
- Use short-lived signed download links where appropriate; validate file type and size; protect against malicious uploads.
- Do not claim compliance or production clinical readiness merely because the demo is hosted.

## 3. Functional Requirements Matrix

| ID | Requirement | Baseline/status |
|---|---|---|
| FR-01 | Accept English free-text clinical notes | Original SOW |
| FR-02 | Extract diagnoses, medications, procedures, allergies, and vital signs/key measurements | Original SOW |
| FR-03 | Provide evidence text and character offsets in the original note | Original SOW |
| FR-04 | Validate strict structured outputs and source spans | Original SOW |
| FR-05 | Retrieve/rank ICD-10 candidates for diagnoses from the supplied table | Original SOW |
| FR-06 | Return no-confident-match where evidence/reference data is insufficient | Original SOW |
| FR-07 | Independent verification of support, status, contradictions, offsets, and omissions | Original SOW |
| FR-08 | Explicit orchestration loop with tool calls, bounded retries, reconciliation, abstention, and escalation | Original SOW |
| FR-09 | Privacy-safe trace and graceful provider failure handling | Original SOW |
| FR-10 | Reviewer UI, item-level accept/reject, flagged reasons, trace, JSON export | Original SOW |
| EXP-01 | Hosted responsive dashboard; no React | Scope expansion pending approval |
| EXP-02 | Authentication and role-based access | Scope expansion pending approval |
| EXP-03 | Patient profiles, current/previous encounters, and history | Scope expansion pending approval |
| EXP-04 | Doctor-managed dynamic knowledge records | Scope expansion pending approval |
| EXP-05 | Text, image, PDF, and audio knowledge ingestion with review before publication | Scope expansion; PDF/OCR/audio feasibility and approval required |
| EXP-06 | PostgreSQL + pgvector RAG with source/permission filtering | Scope expansion pending approval |
| EXP-07 | Doctor-defined retrieval priority with relevance safeguards | Scope expansion pending approval |
| EXP-08 | Central model/provider settings, test, activate, and audit changes | Scope expansion pending approval |
| EXP-09 | Zero-cost hosted demo using free tiers only | Deployment target; quotas/availability limited |
| EXP-10 | Persistent private file storage outside application filesystem | Scope expansion pending approval |

## 4. Non-Functional Requirements

- **Evidence integrity:** accepted extraction items require valid evidence in the original note; do not infer missing clinical values.
- **Authorization:** all patient, encounter, document, configuration, and history access is checked server-side.
- **Tenant/patient isolation:** a request for one patient must not retrieve another patient's records.
- **Traceability:** store source references, processing status, timestamps, model configuration identifier, and safe decision metadata.
- **Privacy:** no secrets or protected note content in logs, traces, public storage, or GitHub.
- **Persistence:** data must survive app restarts/redeployments within managed-service limits.
- **Robustness:** support file validation, bounded retries, no-confident-match, error messages, and graceful rate-limit behaviour.
- **Usability:** simple doctor-focused dashboard; common actions should not require editing configuration files.
- **Free operation:** no feature may require a paid tier or paid API to complete the required demonstration; list quota-dependent limitations.
- **Reproducibility:** pin tested dependencies and document setup/deployment steps after compatibility checks.

## 5. Original SOW Evaluation Targets — Preserve

The existing acceptance targets are retained: at least 100 gold-standard notes across at least 10 specialties, label before prompt tuning; diagnosis F1 >= 0.80; medication F1 >= 0.85; 100% evidence faithfulness for accepted items; >= 90% status correctness for accepted diagnoses and medications; ICD-10 top-3 >= 75%; >= 80% contradiction flagging on at least 20 cases; >= 80% correct rare-diagnosis no-confident-match behaviour on at least 10 cases; 100% correct handling of at least 10 adversarial cases; median end-to-end latency < 30 seconds/note; measurable improvement over a naive single-prompt baseline; report model calls/quota and explain at least three poor cases. These are targets, not measured results.

Expanded product evaluation must additionally test login/permissions, patient isolation, encounter history persistence, document CRUD/versioning, text/image/PDF/audio ingestion (including selectable-text and scanned/mixed PDFs), indexing/re-indexing, RAG source attribution and ranking, global model settings, credential secrecy, and hosted restart/persistence behaviour. See docs/evaluation-plan.md.

## 6. Scope Conflicts and Approval Gate

The following requested features conflict with the original SOW and require a written scope decision:
- Hosted web deployment rather than localhost-only.
- Multiple accounts/role-based access rather than a single reviewer.
- Patient profiles and longitudinal encounter history.
- OCR/image and audio/voice ingestion.
- User-managed knowledge base and vector retrieval beyond the supplied ICD-10 table.
- User-editable provider/model settings.
- Managed cloud database and object storage.

The revised docs describe a proposed product direction; they do not constitute approval. Before implementation with Mirai Labs data, obtain approval for scope, hosting, access controls, data residency/handling, and model-provider terms. Until then, use synthetic data for UI and hosting tests.

## 7. Out of Scope Unless Newly Approved

- EHR/billing integrations.
- Automatic clinical decision-making, diagnosis confirmation, prescriptions, or treatment recommendations.
- Procedure-code assignment.
- Public sharing of patient records.
- Unrestricted arbitrary provider endpoints.
- Paid APIs, paid hosting, GPU-required components, or silent paid fallback.
- Automatic learning/training on patient records or doctor feedback.
- OCR handwriting recognition beyond separately tested feasibility.
- Multi-tenant production operation or claims of clinical/compliance certification.

## 8. Pending Clarifications

1. Does Mirai Labs approve the expanded patient-management, multi-user, hosted, and multimodal knowledge-base scope?
2. Will the hosted demo use synthetic data only, or is there an approved route for de-identified project data?
3. Are Doctor and Administrator the only roles, and who may change the global AI configuration?
4. Must all 5,000 notes be processed, or is an approved evaluation subset sufficient for the prototype? Do not silently reduce the original requirement.
5. Which provider terms are acceptable for clinical text and audio? Is any external transcription provider prohibited? For PDF knowledge ingestion, is printed text sufficient for the initial release, or are scanned PDFs required as well?
6. How much document storage is expected within the free-tier allowance?
7. What retention/deletion policy is required for patient records, source documents, audio, and traces?
8. What recovery/backup expectations apply to a free-tier demo?
9. What is the revised deadline/timeline for the expanded scope?

**Status:** Requirements baseline and requested additions documented; expanded scope, hosting, storage choice, and data use are still pending formal Mirai Labs approval.
