# Hosted Deployment Plan — Free-Tier Django + Neon Stack

**Revision date:** 16 October 2026  
**Status:** Draft guide; no deployment is claimed to exist. Validate all provider settings against the actual Neon/Render accounts before use.

> Use synthetic patient, note, image, audio, and knowledge data for the public evaluation URL. Do not deploy or process Mirai Labs project data until the expanded hosted scope and data-handling design receive written approval.

## 1. Proposed Free-Tier Topology

- **App:** Render Free web service running Django/Python with Django templates, HTMX, and Bootstrap.
- **Database/vector search:** Neon Free PostgreSQL with pgvector.
- **File storage:** Neon Object Storage, private S3-compatible bucket.
- **Embeddings:** local sentence-transformer model, after CPU/memory measurement.
- **PDF text extraction:** pypdf for selectable text, page by page.
- **PDF scanned-page fallback:** pdf2image + Poppler to render pages with little/no text, then Tesseract OCR. This is conditional; do not OCR every PDF page unnecessarily.
- **OCR for standalone images:** Tesseract for supported printed text.
- **Audio transcription:** a tested small local CPU model or approved free-tier endpoint; no paid fallback.
- **LLM:** central allowlisted provider/model configuration, free-tier only.

Neon Free plan details checked 16 October 2026: 1 GB PostgreSQL storage per project, 100 CU-hours per project/month, 5 GB public network transfer per project/month, and 5 GB Object Storage per project. Recheck these limits before deployment. Render Free services spin down after 15 minutes idle, can need around a minute to wake, and do not preserve local filesystem writes across restart/redeploy/spin-down. Official references:
- https://neon.com/blog/neon-free-plan-1-gb-per-project
- https://neon.com/blog/neon-backend-is-ga
- https://neon.com/blog/building-neon-object-storage
- https://render.com/docs/free

## 2. Approval and Safety Gate

Before hosting:
1. Receive written agreement that the expanded hosted/multi-user product is in scope.
2. Confirm which data may be hosted and which providers may process it.
3. Use synthetic data in public demo by default.
4. Do not send clinical notes/media to an external model/transcription API without data-policy approval.
5. Do not put patient records, real notes/media, SOW content, or API credentials in GitHub.
6. Confirm zero-cost is hard requirement, and do not attach a billing fallback or automatically upgrade services.

## 3. Create Neon Database

1. Create a Neon Free project in an available region suitable for the app.
2. Create a dedicated database role/credential for the Django application; do not use a more privileged account unnecessarily.
3. Copy the PostgreSQL connection string into Render's environment variables as `NEON_DATABASE_URL`. Do not commit it.
4. Enable pgvector through a controlled migration or setup SQL:

   ```sql
   CREATE EXTENSION IF NOT EXISTS vector;
   ```

5. Confirm the app can connect using TLS, run migrations, create test records, and execute vector similarity queries.
6. Use Django's migrations as the canonical schema-change mechanism. Test migrations against a disposable/test branch/database before updating the hosted demo.
7. Configure sensible connection limits and keep connections short-lived/pooled where supported; the free host may restart or scale to zero.

## 4. Configure Neon Object Storage

1. Create a private bucket for source uploads (private by default; do not make patient/media buckets public). Allow `application/pdf` for knowledge-base uploads along with explicitly supported text, image, and audio types.
2. Obtain the S3-compatible endpoint, region and credentials from the Neon console.
3. Put these values into Render environment variables, such as:
   - `AWS_ENDPOINT_URL_S3`
   - `AWS_REGION`
   - `AWS_ACCESS_KEY_ID`
   - `AWS_SECRET_ACCESS_KEY`
   - `UPLOADS_BUCKET`
4. Use a Python S3-compatible client such as boto3 and configure its endpoint explicitly from the environment.
5. Test upload, download, delete, and—if required—short-lived signed URL creation with synthetic files.
6. Test that unauthorised users cannot retrieve objects by guessing a key or calling a file endpoint.
7. Store only the object key and safe metadata in PostgreSQL, not a public URL. Check permissions on the Django endpoint before serving a file or creating a short-lived signed link.
8. Apply size/type limits and create a cleanup path for abandoned/failed uploads.
9. If private access or Python/S3 integration fails actual smoke tests, document the issue and evaluate Supabase Storage Free as a fallback. Do not use a public bucket as a workaround.

## 5. Configure Django

Deployment settings should come from environment variables, not hardcoded literals:
- `DJANGO_SECRET_KEY` — strong random secret.
- `DJANGO_DEBUG=False` — always false for the hosted deployment.
- `DJANGO_ALLOWED_HOSTS` — exact Render host.
- `CSRF_TRUSTED_ORIGINS` — exact HTTPS origin(s).
- `NEON_DATABASE_URL` — database connection.
- Object-storage endpoint/region/access credentials/bucket variables.
- A distinct application encryption key for stored provider credentials, if editable API keys are retained in the database.
- Approved model provider and API key values (or encrypted credential references).
- Upload size, PDF page count, rendered-page DPI, PDF/OCR processing timeout, audio duration, model call and request-time limits.

Use secure cookies/HTTPS protections and CSRF validation. Never print environment variables or raw credentials in logs, HTML, error reports, or trace events. Avoid placing API keys in client-side JavaScript or HTML.

## 6. Suggested Render Settings

Connect the private GitHub repository and create a free Web Service.

- **Runtime:** Python.
- **Build command:** `pip install -r requirements.txt && python manage.py collectstatic --noinput && python manage.py migrate`
- **Start command:** `gunicorn <django_project_package>.wsgi:application`

Replace `<django_project_package>` with the actual Django settings package once the application exists. Do not paste the placeholder literally. Confirm the app binds to the port supplied by Render and that `gunicorn` is in the tested requirements file.

For safer deployment, prefer running schema migrations as an explicit controlled deployment step once the application exists. If the build command is used for migrations in this small demo, ensure migrations are idempotent and cannot destructively reset existing data.

Build and static collect must not require credentials for an external model call. The app should boot even if an LLM API is unavailable; model errors should be handled at request time.

## 7. Free-Tier Limits and Safe Failure

- Render service sleeping/cold-start: show a normal loading page, then retry after the app wakes. Test the hosted link before evaluator handoff.
- Render ephemeral filesystem: no SQLite database, uploaded files, or irreplaceable state on local disk.
- Neon DB/Object Storage quotas: measure and document usage. Restrict upload size/audio duration; clean up only according to documented retention rules.
- LLM limits: count requests/tokens; use bounded retries; do not retry indefinitely.
- PDF parsing/rendering, embedding/OCR/audio CPU memory: process limited-size files with timeouts; return visible pending/failed status for work that exceeds available resources.
- Provider failure/quota: defer the task and keep its state; never fabricate an output, switch providers silently, or call a paid service.
- Database connectivity failure: show safe unavailable status; don't expose connection strings or SQL secrets.
- Never state “always available” or “production ready” based on a free hosted demo.

## 8. Pre-Submission Smoke-Test Checklist

- [ ] Public HTTPS URL loads and login/logout work.
- [ ] Text PDFs, scanned PDFs, and mixed PDFs pass the intended parser/OCR path; page numbers remain traceable in the knowledge base.
- [ ] Anonymous users cannot access protected pages.
- [ ] Doctor A cannot access Doctor B's synthetic patients/encounters/files unless explicitly permitted.
- [ ] Patient/encounter/note data survives web-service restart/redeploy.
- [ ] Uploaded synthetic image, text, PDF, and audio objects survive web-service restart.
- [ ] Storage files remain private; guessed keys do not disclose content.
- [ ] Selectable PDF text, scanned/mixed PDF pages, image OCR and audio transcription can be previewed/corrected before publishing knowledge; page references are retained for PDFs.
- [ ] Knowledge edits/deactivation refresh or remove stale embeddings/chunks.
- [ ] RAG results show sources and respect patient/document permissions.
- [ ] Priority changes ranking only after permission and relevance filters.
- [ ] Model settings can test, save, and activate an allowlisted model.
- [ ] Failed provider test preserves the previously active configuration.
- [ ] API credentials do not appear in UI, logs, traces, source code, or database in plaintext.
- [ ] Model/API quota exhaustion produces a clear deferred/error state with no paid fallback.
- [ ] Clinical extraction validates original text offsets and current vs historical/negated status.
- [ ] Reviewed JSON export is permission checked.
- [ ] SOW evaluation results distinguish Pass, Fail, and Not yet measured.
- [ ] README documents free-tier limitations and synthetic evaluator accounts.

## 9. Not Yet Confirmed

The following depend on actual implementation and free-provider accounts:
- Neon project region and remaining quotas.
- Neon Object Storage access method, private bucket policy, and Python/boto3 compatibility.
- Render build/start configuration after Django package names are set.
- Local embedding model install/runtime and memory use on the free web instance.
- PDF parser/page provenance and Poppler installation, OCR language/quality settings, and audio model feasibility.
- Current provider model IDs, privacy terms, free quota, and acceptance by Mirai Labs.
- Any needed fallback, if a primary free service does not pass tests.

**Status:** Deployment plan only. No hosted application or storage integration is claimed to be implemented or tested.
