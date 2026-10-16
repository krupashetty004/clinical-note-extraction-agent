# Evaluation Plan — Clinical Extraction, RAG, Permissions, and Free Hosted Demo

**Revision date:** 16 October 2026  
**Status:** Proposed; test execution pending approval and implementation  
**Principle:** Acceptance thresholds are targets, not measured results. Report each as Pass, Fail, or Not yet measured.

> Use synthetic data for public-hosted tests. The original SOW's clinical dataset may only be processed after Mirai Labs approves the revised scope, hosting, and data-handling design.

## 1. Evaluation Objectives

Evaluate whether the proposed system:
1. Extracts diagnoses, medications, procedures, allergies, and vital signs/key measurements.
2. Provides faithful evidence and original-note offsets for every accepted item.
3. Retrieves appropriate ICD-10 diagnosis candidates from the supplied table and abstains when there is no confident match.
4. Detects unsupported claims, status errors, contradictions, and likely omissions.
5. Improves over a naive single-prompt baseline.
6. Supports the doctor workflow: authenticated access, patient/encounter history, reviewer decisions, and JSON export.
7. Provides a dynamic editable knowledge base with text/image/audio ingestion, RAG, source citations, and priority controls.
8. Supports central model configuration without revealing secrets or silently changing providers.
9. Persists application records/files across restarts and works within the planned free-tier hosting constraints.
10. Handles failures and permissions correctly.

## 2. Original SOW Evaluation — Mandatory and Unchanged Unless Formally Revised

### Gold-standard data
- At least 100 manually labelled notes across at least 10 specialties.
- Labels must be created before prompt tuning.
- Include diagnosis, medication and procedure spans/status, and correct ICD-10 diagnosis labels where supported.
- Write annotation rules before annotation; record ambiguous cases and any review/adjudication procedure.
- Separate development/prompt-iteration data from the independent final reporting set. Do not claim independent performance on repeatedly tuned examples.

### Systems compared
- **Naive single-prompt baseline** using the same approved note set and comparable output definition.
- **Proposed agent** including structured extraction, retrieval, independent verification, reconciliation, bounded retries, abstention, and review controls.

### Required metrics/acceptance targets
| Item | Target |
|---|---|
| Diagnosis extraction | F1 >= 0.80 |
| Medication extraction | F1 >= 0.85 |
| Baseline improvement | Proposed agent measurably outperforms naive baseline |
| Accepted-item evidence | 100% faithful; one fabricated or unsupported accepted item fails this target |
| Status | >= 90% correct for accepted diagnoses and medications |
| ICD-10 | Report top-1 and top-3; top-3 accuracy >= 75% |
| Rare diagnosis | At least 10 test notes; >= 80% correct no-confident-match behaviour in cases where the supplied table/evidence does not support a reliable candidate |
| Contradictions | At least 20 modified notes; flag >= 80% |
| Adversarial handling | At least 10 notes with embedded instructions and/or protected information; 100% correct handling |
| Abstention | Report flagging precision/recall and show flagged cases are harder than accepted cases |
| Latency | Median end-to-end under 30 seconds per note on the approved free-tier environment |
| Operations | Report model calls, retries, quota/rate-limit errors, latency and per-note usage |
| Error analysis | Explain at least 3 poor-performing cases |

These are not achieved values. Mark them Pass/Fail/Not yet measured only after recording results.

## 3. Metric and Test Rules

- Define exact and partial entity matching before evaluation, and apply the same rules to both systems.
- Calculate precision, recall and F1 separately for diagnoses, medications and procedures. Evaluate allergies and vital signs where the approved labels support it.
- Check accepted evidence programmatically against the original note; supplement checks with sampled manual review. A span that exists but does not support the entity is not faithful.
- Score status categories according to the final annotation schema: current/present, negated/absent, uncertain, historical, or additional agreed values.
- Report ICD top-1/top-3 and the denominator. Verify every returned candidate against the supplied canonical table.
- For rare-diagnosis tests, define in advance which cases should lead to no-confident-match rather than an unsupported code.
- Report false-positive and false-negative flags. Compare error rate/difficulty for accepted and flagged items.
- Measure latency end-to-end including extraction, retrieval, verification, retries and review preparation.

## 4. Required Original Challenge Sets

| Test set | Minimum | Expected observation |
|---|---:|---|
| Contradiction set | 20 modified notes | Correctly flag >= 80% of contradictions |
| Rare-diagnosis set | 10 notes | Correct no-confident-match behaviour >= 80% on cases where no reliable supplied-table match exists |
| Adversarial set | 10 notes | Correctly ignore embedded instructions and avoid protected-information exposure; 100% correct handling |

Record test identifier, expected outcome, observed outcome, pass/fail, and likely cause for failures. Keep challenge notes separate from prompt tuning.

## 5. Expanded Hosted Product Tests — New Scope Pending Approval

### 5.1 Authentication and role-based authorization
- Anonymous users are redirected to login before seeing protected pages.
- Login/logout/session expiry and invalid login behaviour work.
- A Doctor has only explicitly permitted actions; Administrator-only role management is protected.
- Direct URL requests, form submissions, exports and API/service calls receive the same permission checks as UI navigation.
- Altering patient, encounter, document, or configuration IDs in a request cannot expose records outside the user's permitted scope.
- Permission tests include at least two synthetic doctors with intentionally separate patient records.

### 5.2 Patient and encounter history
- Create, view and update synthetic patient records.
- Create a current encounter and retain previous encounters separately.
- Save a note, extraction run, review decision, model config version and timestamp against the correct encounter.
- Confirm previous extraction results remain auditable and are not silently overwritten.
- Patient-history RAG retrieval for Patient A never includes Patient B content.
- Historical diagnosis/medication mentions stay labelled historical unless the current source supports a current status.

### 5.3 Multimodal knowledge ingestion
- Text entered in UI and supported text-file uploads index successfully after review.
- Image upload validates type/size, OCR returns text for preview, correction works, and doctor must approve before publication.
- Audio upload validates type/size, transcription can be reviewed/corrected before publication, and errors/timeouts are displayed.
- Unsupported/malformed/oversized files are rejected safely.
- Private object retrieval enforces permissions; guessed object keys or direct URLs do not expose files.
- Failure after upload or during indexing leaves an explicit pending/failed status rather than a published broken record.
- A knowledge item edited/deactivated has its stale chunks removed or updated; old source versions remain traceable where policy requires.
- Test against resource limits on the actual free hosting plan; do not assume OCR/audio inference fits until tested.

### 5.4 RAG relevance, permissions, and priority
- Queries retrieve relevant knowledge and expose title/source/version/chunk reference.
- Compare semantic retrieval, keyword/full-text retrieval, and hybrid ranking on a small labelled synthetic query set.
- Verify metadata filters are applied before ranking.
- Increasing a document's priority can only affect eligible relevant items; it cannot bypass user access or cause clearly unrelated material to be treated as evidence.
- Low-relevance queries produce a no-relevant-context result rather than forced context.
- Retrieved reference knowledge is visibly distinguished from evidence spans in the current clinical note.
- The system does not automatically train/fine-tune the model when knowledge is added.

### 5.5 AI settings and model testing
- Provider/model selection uses an allowlist; unsupported IDs/providers are rejected.
- Credentials are masked on screen; raw keys do not appear in database query output, logs, traces, error messages, HTML source, or Git.
- Test connection uses synthetic non-sensitive input and reports response status, latency, parsing/schema support, and failure reason.
- The model can be saved as a draft and activated only via an authorised action.
- A failed test does not silently replace the currently active configuration.
- Each run is tied to a config version/model identifier.
- Rate limits/outages produce safe failures and no paid fallback.
- Connection success is not scored as clinical accuracy; run a model quality evaluation separately.

### 5.6 Persistence, storage and hosting
- Publish synthetic patient/knowledge records, restart/redeploy the web service, and verify database records and uploaded files still exist.
- Confirm no persistent data is stored only on Render's ephemeral filesystem.
- Check Render cold-start and hosted-link behaviour.
- Verify database/vector/file quotas and response when nearing limits.
- Verify Neon PostgreSQL pgvector extension and migration support.
- Verify private Neon Object Storage buckets and Python S3 client upload/download/delete/signing; if integration fails, document the contingency before using another provider.
- Confirm no usage path can auto-upgrade or incur a paid charge; document manual quota-exhaustion behaviour.

## 6. Test Execution Order

1. Obtain approval for expanded scope, hosting, provider/data-use and patient data handling.
2. Create synthetic data and seed users with separate access permissions.
3. Define annotation and metric rules; prepare the gold standard before prompt tuning when approved data becomes available.
4. Verify local database schema, migration, vector extension, storage integration, secrets and permissions.
5. Run Django tests for auth, direct endpoint access, patient isolation, CRUD and encounter history.
6. Test document ingestion, OCR/audio limitations, review-before-publish, chunking, embeddings and re-indexing.
7. Run RAG retrieval/ranking/source-citation tests and patient/reference source separation.
8. Run the single-prompt baseline and proposed clinical extraction system on the same approved evaluation set.
9. Run contradiction, rare-diagnosis and adversarial test sets.
10. Test model configuration, provider errors, quotas and persistence.
11. Calculate/report metrics, inspect spans manually and describe at least three failures.
12. Publish evaluation results with Pass/Fail/Not yet measured status for all targets.

## 7. Final Evaluation Report Content

1. Dataset size, specialty distribution and annotation guideline.
2. Data split and system/model configuration identifiers.
3. Baseline and proposed-system metrics by entity type.
4. Original-note evidence faithfulness and offset validation.
5. Status correctness and common status errors.
6. ICD-10 top-1/top-3 and rare-diagnosis abstention.
7. Contradiction and adversarial results.
8. Abstention precision/recall and accepted-vs-flagged error analysis.
9. Model calls, retries, latency, free-tier usage and quota failures.
10. Results for authentication, patient isolation, persistence, uploads, RAG and central settings.
11. At least three failure case analyses.
12. Every acceptance target marked Pass, Fail, or Not yet measured.
13. A list of unimplemented/blocked features and scope/approval limitations.

## 8. Reporting Rules

- Use only approved Mirai Labs clinical data; use synthetic records for public hosting.
- Never claim a target before it has been measured.
- Do not silently reduce dataset sizes or challenge-set sizes due to time or quotas.
- Do not treat schema validity, successful API connectivity, high similarity, or an attractive demo as proof of clinical correctness.
- Do not label a free-hosting prototype production-ready or claim regulatory/compliance certification.
- Capture test environment and time, since free-tier quotas/provider capabilities change.

## 9. Approval Status

This is a proposed test plan. The expanded doctor workspace and hosted RAG system require written Mirai Labs scope approval. Clinical evaluation execution requires authorized dataset access and approved handling arrangements. Actual results remain **Not yet measured** until tests are run.
