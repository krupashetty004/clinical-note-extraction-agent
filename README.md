# AI-Powered Clinical Note Extraction and Coding Agent

> **Mirai Labs — Doctor Workspace Demo**
> A Django-based clinical note extraction, ICD-10 coding, and independent verification pipeline with a built-in doctor workspace UI.

---

## Quick Start (Local)

### Prerequisites

- Python 3.12+
- Windows / macOS / Linux

### 1. Clone and enter the project

```bash
cd clinical-note-extraction-agent
```

### 2. Create and activate a virtual environment

```bash
python -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate.ps1
# macOS / Linux
source .venv/bin/activate
```

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Apply database migrations and seed roles

```bash
python manage.py migrate
```

This creates an SQLite database at `db.sqlite3` and seeds the `Doctor` and `Administrator` workspace roles. No default user accounts or passwords are created.

### 5. Create a superuser (admin account)

```bash
python manage.py createsuperuser
```

Follow the prompts to set a username and password.

### 6. Create least-privilege workspace users

The superuser created above can access all application views. For day-to-day use, sign in to `/admin/`, create a separate non-superuser account, set its password, and assign exactly one workspace group:

- `Doctor` for patient, encounter, note processing, knowledge review and annotation tasks.
- `Administrator` for AI settings and administrator-only functions.

Do not share the superuser account for routine work. The login page does not publish demo usernames or passwords, and the application does not create default accounts automatically.

### 7. Start the development server

```bash
python manage.py runserver
```

Open **http://127.0.0.1:8000/** in your browser and sign in.

---

## Demo Workflow

### Create a patient and encounter

1. Log in at http://127.0.0.1:8000/
2. Go to **Patients → New Patient**
3. Create a **Patient**, then an **Encounter**, then add a **Clinical Note**

### Run AI extraction on a note

On the patient detail page, click **"Process with AI Agent"** (POST to `/notes/<id>/process/`).

- With no active AI configuration, or with the local synthetic configuration active, the **local offline extraction engine** (`LocalClinicalExtractionProvider`) is used and makes no network call.
- The Administrator **AI settings → Test connection** action uses a fixed synthetic note only. Groq tests run the configured model and validate its structured extraction response; the settings page does not send patient data.
- Provider activation is allowed only when the test passed for the exact same provider, model, temperature, token limit and credential fingerprint. Changing one of those values requires a new test.
- Groq choices currently include `openai/gpt-oss-20b`, `openai/gpt-oss-120b`, and `qwen/qwen3.8-27b`. Deprecated Llama model IDs were removed.
- Gemini is displayed as unsupported because its execution adapter is not implemented. Selecting an unsupported provider does not silently switch to another provider.
- To run Doctor notes through Groq, all of the following are required: `MIRAI_ENABLE_GROQ_PROVIDER=1` in the local development environment, `MIRAI_EXTERNAL_CLINICAL_DATA_APPROVED=1` after formal Mirai Labs privacy/security approval, an active Groq configuration, and a usable configured credential. If any condition is missing, the request is blocked and the doctor receives a visible message; it does not fall back silently.
- The active provider model, saved encrypted key, temperature and completion-token limit are passed to both Groq extraction and verification.

The run is saved and you are redirected to the processing run detail page.

### Review and export

1. On the processing run detail page, review extracted items.
2. Click **Approve** or **Reject** to complete review.
3. Click **"Export reviewed JSON"** to download the structured result as a JSON attachment.

### Optional: Run the synthetic demo

To use the built-in synthetic data demo (no real notes needed), set `MIRAI_ENABLE_SYNTHETIC_DEMO=1` in the local environment, then click **"Run synthetic demo"** on any patient detail page. The demo remains disabled by default.

---

## Knowledge Base

Go to **Knowledge Base → Upload Document** to add clinical guidelines, protocols, or reference documents (`.txt`, `.pdf`, `.md`, `.wav`, `.mp3`).

- Text files and selectable-text PDFs are extracted locally. Scanned PDFs are rendered locally with PDFium and OCR is attempted through Tesseract; an approved Groq vision fallback is available for up to 10 scanned pages. Each file is limited to 10 MB and PDFs to 100 pages.
- Image uploads try local Tesseract OCR first, then the same gated Groq vision path. No environment-key or Gemini fallback is permitted.
- Audio uploads (.wav, .mp3, .m4a, .ogg) use Groq's dedicated `whisper-large-v3-turbo` speech-to-text model only when both `MIRAI_ENABLE_GROQ_PROVIDER=1` and `MIRAI_EXTERNAL_CLINICAL_DATA_APPROVED=1` are enabled, and an active Groq credential has passed the synthetic configuration test. Audio uses this dedicated speech model rather than the chat/extraction model selected in Settings.
- OCR/audio results are drafts. For clinical-note uploads, the first submission populates the note editor and is rejected until the doctor reviews/corrects the transcription and submits again without re-uploading. Knowledge Base uploads remain inactive with `needs_review` until corrected and explicitly published.
- If a local or approved transcription path is unavailable, the upload is rejected with an actionable error. It never inserts a filename or placeholder as transcribed clinical text.
- Local scanned-PDF OCR requires the Tesseract executable to be installed and available on `PATH`; the Python dependencies include PyPDFium2 and Pillow. Verify the local Tesseract installation with `tesseract --version`.
- Local lexical RAG retrieval is connected to the Doctor clinical-note processing workflow. It selects up to three active manually entered or explicitly published passages and passes them separately from the original note to compatible providers.
- Uploaded documents remain inactive and excluded while `needs_review`; a doctor/administrator must review and publish them before retrieval.
- Retrieved document/version/chunk citations and scores are persisted with the processing run and shown in its detail page/export.
- Original-note evidence spans remain mandatory. Reference passages are context only and must never be used as evidence for a diagnosis or other extracted claim.
- The current RAG implementation is lexical; it does not yet use embeddings or pgvector. The deterministic local rules provider ignores the context, while the Groq adapter receives it separately.

## Private persistent file storage

Local development uses Django's local filesystem storage by default. For a hosted environment, configure a private Neon Object Storage bucket before enabling persistent source-file uploads. The application never makes source buckets public.

1. In Neon, create an Object Storage bucket and set its access to **private**.
2. Create a branch-scoped Neon credential with both `storage:read` and `storage:write` scopes. Keep the credentials in the deployment environment, not in Git.
3. Configure these environment variables in the local environment or Render service:

```text
MIRAI_ENABLE_NEON_OBJECT_STORAGE=1
NEON_STORAGE_BUCKET=<private bucket name>
AWS_ENDPOINT_URL_S3=<branch S3 endpoint from Neon>
AWS_REGION=<region from Neon>
AWS_ACCESS_KEY_ID=<scoped Neon access key>
AWS_SECRET_ACCESS_KEY=<scoped Neon secret>
```

4. Run the synthetic-only storage check:

```powershell
python manage.py check_neon_storage
```

The command writes, reads, and deletes a small synthetic test object. It does not use clinical content. The knowledge-base original-file download route checks Django authentication and role permissions and streams the file through the application; it does not display a public bucket URL.

When object storage is enabled but the required settings are incomplete, Django startup fails with the missing variable names. When running in production without object storage enabled, knowledge-file uploads are rejected rather than saved to Render's ephemeral filesystem. Local development remains on filesystem storage unless explicitly opted in.

The Neon Free plan currently lists 5 GB of Object Storage per project. Quotas and regional availability must be rechecked before a real deployment. Render Free uses an ephemeral filesystem and can restrict services that initiate unusually high outbound traffic; this integration is intended for a bounded synthetic demo, not production clinical data. Do not upload real patient information until Mirai Labs approves the hosting, storage, provider, and privacy/security design.

---

## Dataset preparation and annotation

The MTSamples preparation tools live in `mirai_dataset_preparation_pack/`. Place the CSV at:

`mirai_dataset_preparation_pack/data/external/mtsamples/raw/mtsamples.csv`

Then run from the repository root:

```powershell
python .\\mirai_dataset_preparation_pack\\scripts\\analyze_mtsamples.py
```

The analyzer prepares a full normalized local corpus, a deterministic 100-note specialty-balanced annotation queue, and aggregate quality reports under `.dataset_working/\`. That directory and the raw CSV are Git-ignored because they contain clinical narratives.

The 100-note queue starts unannotated. MTSamples specialty labels and keywords are not gold entity annotations. Never mark automatically generated labels as human gold or independently adjudicated. AI-generated labels may be tracked separately as provisional benchmark labels, not clinical gold.

The Doctor annotation workspace reads only the locally prepared queue under `.dataset_working/annotations/` and saves drafts to an ignored working file in that directory. It does not fall back to a note-bearing file tracked in Git. If the local queue is missing, the page explains how to prepare it. Source note text and annotations are never stored in Django sessions.

The annotation form treats source note text and provenance as immutable. Marking a draft complete does not make it clinical gold. Clinical-gold export requires qualified label provenance, independent adjudication, and source-span validation. Model-generated labels remain provisional/silver benchmark material and are never clinical gold.

### Process the prepared dataset through the clinical agent

First check that the local ICD-10-CM table is populated. On a fresh local database, import the repository's reference file once:

```powershell
python manage.py import_icd10 --source data\\reference\\icd10cm-codes-2027.txt --apply
```

Then inspect the dataset status and process the 100-record queue:

```powershell
python manage.py dataset_status
python manage.py process_mtsamples_dataset --limit 100
```

The batch command always uses the local dictionary extraction and verification providers. It reuses the same extraction, ICD-10 candidate retrieval, verification, reconciliation, bounded retry and abstention workflow, but does not create patient/encounter records or clinical processing runs.

Outputs are written only under `.dataset_working\\runs\\mtsamples\\`:
- `predictions.jsonl` — structured entity results, evidence offsets, ICD-10 candidates, and source IDs.
- `operations.jsonl` — status, duration, bounded attempt counts, provider identity and safe failure codes.
- `results.jsonl` — atomic per-note checkpoint used by the resume option.
- `manifest.json` — source-file SHA-256, provider identity, and selected record IDs used to prevent stale results from being resumed against a changed dataset.
- `report.json` — aggregate processing totals and an evaluation status.

Resume an interrupted batch with `--resume`; deliberately replace outputs with `--overwrite`. The batch does not call external AI providers. It does not claim clinical accuracy when qualified gold labels are unavailable.

---

## Evaluation status

The repository contains synthetic smoke tests, challenge observations and measured synthetic benchmark tooling. Their results are not interchangeable with independent clinical gold-standard evaluation.

Do not use the legacy generated scorecard as proof that the original acceptance targets have been met. The MTSamples source does not provide note-level gold entity spans, assertion labels, or validated ICD-10-CM labels. It therefore cannot independently establish diagnosis/medication F1, evidence faithfulness, status accuracy or coding accuracy without suitable validated annotations.

The current 100-record file in the repository must not be treated as 100 independently adjudicated clinical gold notes. Check `docs/evaluation-plan.md` before reporting evaluation results.

## Running Tests

```bash
# Full test suite
python manage.py test

# Specific modules
python manage.py test dashboard.test_local_provider
python manage.py test dashboard.test_ai_processing_view
python manage.py test evaluation

# Mirai dataset pack tests (no Django context needed)
python -m unittest discover -s mirai_dataset_preparation_pack/tests -v
```

Run the automated checks in GitHub Actions for the exact branch/commit being reviewed. Do not rely on a stale test count in this README.

---

## Project Structure

```
clinical-note-extraction-agent/
├── config/                  # Django settings and WSGI/ASGI entrypoints
├── dashboard/               # Main Django app
│   ├── extraction/          # Core pipeline
│   │   ├── local_provider.py    # Offline extraction + verification (no API)
│   │   ├── rag_service.py       # Priority-aware lexical RAG retrieval
│   │   ├── schema.py            # Pydantic schemas for extraction output
│   │   ├── verification.py      # Independent verification contract
│   │   ├── orchestrator.py      # Agent workflow coordination
│   │   ├── processing_service.py # Django persistence layer
│   │   └── diagnosis_coding.py  # ICD-10 hybrid search
│   ├── templates/dashboard/     # Django HTML templates
│   ├── models.py                # Patient, Encounter, ClinicalNote, ProcessingRun, etc.
│   ├── views.py                 # All request handlers
│   └── urls.py                  # URL routing
├── evaluation/              # SOW benchmark tooling
│   ├── agent_predictions.jsonl
│   ├── baseline_predictions.jsonl
│   ├── challenge_observations.json
│   └── sow_report.py
├── scripts/                 # One-off pipeline scripts
│   ├── generate_golden_annotations.py
│   ├── complete_challenge_observations.py
│   ├── run_full_evaluation.py
│   └── print_scorecard.py
├── reports/                 # Generated evaluation reports
│   └── final_sow_evaluation_report.json
├── data/
│   └── reference/
│       └── icd10cm-codes-2027.txt   # 74,879 ICD-10 codes (canonical reference)
├── mirai_dataset_preparation_pack/  # Dataset preparation and annotation tools
└── docs/                    # Architecture, requirements, evaluation plan docs
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DJANGO_SECRET_KEY` | local-only development key | Required secure Django signing key in production |
| `DJANGO_ENV` | `development` | Set to `production` for hosted environments |
| `DJANGO_DEBUG` | environment-dependent | Must be `0` in production |
| `DATABASE_URL` | local SQLite | Persistent PostgreSQL connection string in production |
| `DJANGO_ALLOWED_HOSTS` | `127.0.0.1,localhost` | Comma-separated allowed hosts when DEBUG is off |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | empty | Comma-separated HTTPS origins when required |
| `GROQ_API_KEY` | — | Optional Groq credential; settings-page credentials are encrypted at rest |
| `MIRAI_ENABLE_GROQ_PROVIDER` | `0` | Local Groq adapter opt-in; DEBUG-only |
| `MIRAI_EXTERNAL_CLINICAL_DATA_APPROVED` | `0` | Separate approval gate for external Doctor-note processing; do not enable before formal privacy/security approval |
| `MIRAI_ENABLE_SYNTHETIC_DEMO` | `0` | Enable the local synthetic demo in DEBUG mode |

Set these in a `.env` file at the project root (never commit it).

---

## Confidentiality

- This repository is currently public. Treat every committed file as publicly accessible.
- Never commit the raw MTSamples CSV, normalized note-level records, annotation queues containing note text, the SOW, patient data, API keys, or uploaded files.
- Keep raw and generated dataset files in the Git-ignored local `.dataset_working/` directory. The tracked repository contains only an empty `.gitkeep` in the source annotation folder.
- Removing a sensitive file from the latest branch does not erase earlier Git history. Treat prior historical copies as exposed until repository history is reviewed and appropriately remediated.
- The public demo must use synthetic patient data only.
- No default demo usernames/passwords are stored in source code or exposed on the login page. Provision accounts explicitly; use a separate least-privilege Doctor account for routine work.
- Never bootstrap users with known passwords or grant administrator roles automatically.
- All clinical processing runs require doctor authentication and explicit patient access grants.

---

## Architecture

See [`docs/architecture.md`](docs/architecture.md) for the full system diagram and data flow.

**Pipeline summary:**

```
ClinicalNote.original_text
    → LocalClinicalExtractionProvider (or GroqExtractionProvider)
    → code_diagnoses()           ← ICD-10 hybrid lexical+semantic search
    → LocalClinicalVerificationProvider
    → validate_verification_output()
    → _reconcile()               ← deterministic item disposition
    → ClinicalProcessingRun (persisted, awaits doctor review)
    → export_processing_run()    ← JSON attachment on approval
```
