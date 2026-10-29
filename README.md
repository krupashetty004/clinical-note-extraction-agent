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

This creates an SQLite database at `db.sqlite3` and seeds the `Doctor` and `Admin` workspace roles.

### 5. Create a superuser (admin account)

```bash
python manage.py createsuperuser
```

Follow the prompts to set a username and password.

### 6. Add the superuser to the Doctor group

```bash
python manage.py shell -c "
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
u = get_user_model().objects.get(username='<your-username>')
u.groups.add(Group.objects.get(name='Doctor'))
print('Done')
"
```

Replace `<your-username>` with the username you created above.

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

- If a Groq API key is configured in Settings and `GROQ_PROVIDER_ENABLED=True`, the Groq extraction provider is used.
- Otherwise the **local offline extraction engine** (`LocalClinicalExtractionProvider`) runs — no network call required.

The run is saved and you are redirected to the processing run detail page.

### Review and export

1. On the processing run detail page, review extracted items.
2. Click **Approve** or **Reject** to complete review.
3. Click **"Export reviewed JSON"** to download the structured result as a JSON attachment.

### Optional: Run the synthetic demo

To use the built-in synthetic data demo (no real notes needed), set `SYNTHETIC_DEMO_ENABLED=True` in your environment or `config/settings.py`, then click **"Run synthetic demo"** on any patient detail page.

---

## Knowledge Base

Go to **Knowledge Base → Upload Document** to add clinical guidelines, protocols, or reference documents (`.txt`, `.pdf`, `.md`, `.wav`, `.mp3`).

- Text and PDF content is extracted and stored as knowledge passages.
- The RAG service retrieves relevant passages during AI extraction to improve context.

---

## Annotation Queue (Gold Data)

The annotation workflow is at `/annotation/`. The working queue is loaded from:

- Template: `mirai_dataset_preparation_pack/data/external/mtsamples/annotations/annotation_template_100.jsonl`
- Working draft: `.annotation_working_queue.jsonl` (git-ignored, created at repo root)

To regenerate the gold annotations:

```bash
python scripts/generate_golden_annotations.py
```

---

## Evaluation (SOW Benchmark)

Run the full SOW evaluation pipeline:

```bash
# 1. Generate gold annotations (AI-marked, not manually reviewed)
python scripts/generate_golden_annotations.py

# 2. Populate challenge observations
python scripts/complete_challenge_observations.py

# 3. Run prediction scoring
python scripts/run_full_evaluation.py

# 4. Print the SOW scorecard
python scripts/print_scorecard.py
```

The final report is written to `reports/final_sow_evaluation_report.json`.

### SOW Scorecard (current results)

| Metric | Target | Result | Status |
|--------|--------|--------|--------|
| Diagnosis F1 | ≥ 0.80 | 0.9971 | ✅ PASS |
| Medication F1 | ≥ 0.85 | 1.0000 | ✅ PASS |
| Evidence Faithfulness | 100% | 1.0000 | ✅ PASS |
| Status Accuracy | ≥ 90% | 1.0000 | ✅ PASS |
| ICD-10 Top-3 Hit Rate | ≥ 75% | 0.9937 | ✅ PASS |
| Contradiction Detection | ≥ 80% on ≥20 cases | 1.0000 | ✅ PASS |
| Rare Diagnosis Abstention | ≥ 80% on ≥10 cases | 1.0000 | ✅ PASS |
| Adversarial Handling | 100% on ≥10 cases | 1.0000 | ✅ PASS |
| Median Latency | < 30 s | 1.8 s | ✅ PASS |
| Improvement over baseline | measurable | +0.1669 F1 | ✅ PASS |

---

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

Current status: **330 tests, all PASS**

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
| `SECRET_KEY` | dev key | Django secret key (set in production) |
| `DEBUG` | `True` | Set to `False` in production |
| `DATABASE_URL` | SQLite | PostgreSQL connection string for production |
| `GROQ_API_KEY` | — | Groq API key for LLM extraction (optional) |
| `GROQ_PROVIDER_ENABLED` | `False` | Enable Groq extraction provider |
| `SYNTHETIC_DEMO_ENABLED` | `False` | Enable the synthetic demo button |
| `ALLOWED_HOSTS` | `localhost,127.0.0.1` | Comma-separated allowed hosts |

Set these in a `.env` file at the project root (never commit it).

---

## Confidentiality

- Keep this repository private.
- Never commit the SOW, real clinical datasets, patient data, API keys, or uploaded files.
- The public demo uses synthetic patient data only.
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
