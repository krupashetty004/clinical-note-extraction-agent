# Revised Development Timeline — Hosted Doctor Workspace and Clinical RAG MVP

**Revision date:** 16 October 2026  
**Planning window:** 13–26 October 2026  
**Status:** Proposed and high-risk; expanded scope and deployment/data handling require Mirai Labs approval.

> The original SOW has a six-workday implementation window (19, 20, 21, 22, 23 and 26 October). The expanded scope adds authentication, patient/encounter management, cloud persistence, multimodal knowledge ingestion, RAG, centralized model settings and hosting. Completing all expanded features plus the original evaluation criteria in this window is a substantial delivery risk. Confirm priority/scope with Mirai Labs instead of silently dropping mandatory SOW work.

## 1. Completed Planning Milestones

| Date | Work | Status |
|---|---|---|
| 13 Oct | Review SOW, identify requirements/questions, begin market research | Documented |
| 13–14 Oct | Review commercial products, open-source tools, and research papers | Documented |
| 14 Oct | Research presentation | Scheduled/completed status to be confirmed by project owner |
| 15 Oct | Solution, architecture, technology-stack rationale, requirements, evaluation and timeline documentation | Planning documents committed; technology choices remain proposals |
| 16 Oct | Revise direction for hosted doctor workflow, role access, patient/encounter history, editable multimodal knowledge base, RAG, central model settings, and zero-cost deployment | Proposed design updated; formal approval still required |

## 2. Approval Gate Before Clinical Data Use

Before any implementation sends project notes, uploaded media, or patient records to external hosting or model providers:

- Get written agreement from Mirai Labs for expanded hosted/multi-user scope.
- Confirm what data may be stored in the hosted database/object store and which providers may process it.
- Confirm the selected model provider's current data-use/retention terms.
- Recheck Render and Neon free-tier terms and limits.
- Confirm the required volume: all approximately 5,000 supplied notes or an explicitly approved evaluation/demo subset.
- Until approval, use synthetic patients, synthetic notes, and synthetic knowledge documents for UI/hosting tests.

## 3. Proposed Post-Approval Plan

| Date | Focus and deliverable | Tests / risk controls |
|---|---|---|
| Fri, 16 Oct | Finalise scope decisions, architecture, logical schema, roles, and free-tier provider checks | No feature work on clinical data before approval. Treat the expanded scope as a change request if the original SOW remains binding. |
| Mon, 19 Oct | Set up Django project, templates/HTMX/Bootstrap, configuration via environment secrets, Neon PostgreSQL connection, migrations, authentication and base roles | Test deploy preview, login/logout, server-side permissions, and synthetic seed data. Check Render cold start. |
| Tue, 20 Oct | Implement doctor dashboard, patient list, patient detail, current/previous encounters, clinical-note records and review-history persistence | Test two synthetic doctors and prove access isolation. Preserve previous run history. |
| Wed, 21 Oct | Implement central AI Settings page (provider/model allowlist, credential handling, test/save/activate) and clinical note input/extraction/schema/evidence checks | Use synthetic notes for provider tests; never log API keys. Test malformed outputs, invalid offsets, rate limits and no paid fallback. |
| Thu, 22 Oct | Implement knowledge-base CRUD and private Neon Object Storage upload/download; text-file and PDF ingestion (pypdf selectable-text extraction, page-by-page OCR fallback via pdf2image + Poppler + Tesseract), image OCR; doctor preview/correction/publication | Test file/page limits, mixed/scanned PDFs, page provenance, private access, failure states, object persistence and permission enforcement. Audio transcription may require a smaller tested local model or approved free endpoint. |
| Fri, 23 Oct | Implement local embeddings, PostgreSQL full-text + pgvector retrieval, RAG citations, priority rules, edit/version/deactivation/re-index, and integration with clinical workflow | Test source traceability, filters, stale-vector removal, relevance and patient-history isolation. Measure CPU/memory and request quotas. |
| Mon, 26 Oct | Integration hardening; run available SOW evaluation/challenge tests; hosted smoke test; fix critical access/evidence defects; final README, deployment guide, user guide and 5–8 minute demo | Report every SOW target Pass/Fail/Not yet measured. Do not claim full acceptance if labels or challenge sets are incomplete. Record latency, free quota issues, and at least three poor cases. |

## 4. Work That Must Not Be Silently Reduced

The original SOW acceptance criteria remain mandatory unless the SOW is formally revised:
- At least 100 manually labelled notes across at least 10 specialties before prompt tuning.
- Diagnosis F1 >= 0.80; medication F1 >= 0.85.
- 100% evidence faithfulness for accepted items; >= 90% status correctness.
- ICD-10 top-3 >= 75%; rare-diagnosis correct no-confident-match >= 80% on at least 10 cases.
- >= 80% contradiction detection on at least 20 cases; 100% correct handling of at least 10 adversarial cases.
- Measurable improvement over the naive single-prompt baseline; median latency under 30 seconds per note.
- Call/quota reporting and analysis of at least three poor-performing examples.

Expanded product tests additionally cover authentication, permissions, patient isolation, encounter persistence, upload validation, private files, OCR/transcription, knowledge versioning, RAG citations and filters, model configuration, secret handling, and redeployment persistence.

## 5. Risk and Contingency Table

| Risk | Impact | Required response |
|---|---|---|
| Expanded scope not approved | Cannot process Mirai Labs data or commit to cloud patient data | Continue using synthetic data and request written clarification |
| Six-day window too short | Mandatory functions/tests may remain incomplete | Agree on priority and revised schedule; document incomplete items honestly |
| Free hosting cold starts | Evaluator sees delay on first visit | Display a clear loading/waking state and test URL before submission |
| Render ephemeral filesystem | Uploads/local DB can disappear | Store persistent records in Neon PostgreSQL and files in external Object Storage |
| Neon quota/storage/network limits | Demo may fail under excessive use | Limit uploads, monitor quota, defer work on exhaustion, no paid fallback |
| OCR/audio consumes too many resources | Free-host CPU/RAM or execution time exceeded | Use small inputs, local OCR, test tiny transcription model or explicitly approved free API; defer if unsupported |
| Model free quota / outage | Extraction and verification interrupted | Bounded retries, clear status and safe deferral; no silent model switch |
| Annotation bottleneck | Required gold-standard set not ready | Track coverage daily, escalate risk, never shrink the minimum silently |
| Credential or patient-data exposure | Privacy/security incident | Use synthetic public demo records, private buckets, environment secrets, masked traces and authorization tests |

## 6. Final Status Reporting

For each day record:
- **Done:** verifiable code/docs/tests committed.
- **Blocked:** approval, data, provider, quota, or integration blockers.
- **Next:** specific testable deliverables for the next work session.

Do not describe proposed technologies as tested or implemented until commits and test results support it.

**Status:** Revised schedule is a planning baseline only; scope, provider selection and data handling remain subject to formal approval.
