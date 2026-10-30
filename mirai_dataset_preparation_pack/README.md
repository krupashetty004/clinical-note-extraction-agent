# Mirai Labs — Kaggle Dataset Preparation Pack

This package prepares a local, reproducible data workflow for the Mirai Labs Clinical Note Extraction and Coding Agent. It is deliberately separate from the existing repository's `data/` directory so no existing user files are overwritten.

## Selected primary dataset

**Kaggle: Medical Transcriptions (MTSamples)**
Dataset: https://www.kaggle.com/datasets/tboyle10/medicaltranscriptions
Owner shown on Kaggle: `tboyle10` / Tara Boyle
Kaggle's dataset page describes the data as sample medical transcriptions scraped from `mtsamples.com` and declares a **CC0: Public Domain** license. Check the current data card and the relevant terms again at the time of download. This package does not replace a license review.

Published dataset metadata and secondary documentation report about 4,999 rows, a six-column CSV, and fields typically named `description`, `medical_specialty`, `sample_name`, `transcription`, and `keywords` (some copies have a row index or a differently named identifier). The official CSV is listed around 17 MB. These figures are *pre-download metadata*, not measurements performed on a local copy. Run the analyzer to get the actual counts for your downloaded version.

### Important suitability assessment

MTSamples is a useful real-text, multi-specialty corpus for ingestion testing, specialty distribution analysis, and development. Its `medical_specialty` label is not a gold clinical entity annotation. Its `keywords` field is not a validated span-level annotation. The dataset does not appear to include verified diagnosis/procedure/medication/allergy/vital entity spans, assertion/status labels, or note-specific ICD-10-CM gold codes. Therefore:

- It can support a real-source transcription corpus and specialty-label coverage checks.
- It cannot, by itself, establish the SOW's entity F1, evidence-faithfulness, status-accuracy, contradiction-detection, rare-diagnosis abstention, or note-to-code top-3 accuracy targets.
- The generated 100-note file is an **annotation queue**, not a labelled gold dataset. All annotations start as unreviewed / null. Qualified human annotation and adjudication are still required for gold evaluation.
- Do not interpret it as fully privacy-cleared merely because the data card has a public-domain license. Inspect the downloaded text locally for potential personal information, and never send the text to an external AI API.

## One-time setup on Windows

The dataset-preparation tools are already part of this repository. From the repository root, place the supplied CSV at:

`mirai_dataset_preparation_pack\\data\\external\\mtsamples\\raw\\mtsamples.csv`

PowerShell:

```powershell
New-Item -ItemType Directory -Force .\\mirai_dataset_preparation_pack\\data\\external\\mtsamples\\raw | Out-Null
Copy-Item "C:\\path\\to\\mtsamples.csv" .\\mirai_dataset_preparation_pack\\data\\external\\mtsamples\\raw\\mtsamples.csv
```

Replace the source path with the location of your downloaded CSV. Do not add the raw CSV to Git. This repository is public, and the CSV contains clinical narratives.

### Analyze and prepare the CSV

The analyzer uses only Python's standard library. No API call or AI provider is used.

```powershell
python .\\mirai_dataset_preparation_pack\\scripts\\analyze_mtsamples.py
```

The default command requires at least 10 specialties in the 100-record annotation queue. A different threshold can be set explicitly:

```powershell
python .\\mirai_dataset_preparation_pack\\scripts\\analyze_mtsamples.py --minimum-specialties 10
```

Generated note-level files are written under the Git-ignored repository-root `.dataset_working\\` directory so they do not overwrite the tracked annotation template or get committed accidentally:

- `.dataset_working\\reports\\dataset_quality_report.md` — aggregate counts, missingness, specialty distribution, duplicate checks and suitability notes.
- `.dataset_working\\reports\\dataset_quality_report.json` — machine-readable audit report including the raw CSV SHA-256.
- `.dataset_working\\prepared\\records.jsonl` — normalized records with provenance and `gold_annotations: null`.
- `.dataset_working\\annotations\\annotation_template_100.jsonl` — 100 distinct notes selected deterministically across specialties. All begin unannotated.

The full note text exists only in local working files. The reports do not include note text. Review local data handling before any external processing. MTSamples specialty and keyword fields are not gold entity labels.

### Use the prepared queue in the clinical extraction workflow

The Doctor annotation page uses the generated local queue automatically. The saved draft is kept in `.dataset_working\\annotations\\.annotation_working_queue.jsonl`; the tracked template is not overwritten.

For ICD-10 coding, import the supplied reference into your local Django database once if the table is empty:

```powershell
python manage.py import_icd10 --source data\\reference\\icd10cm-codes-2027.txt --apply
```

Check that prepared records and the annotation queue are discoverable:

```powershell
python manage.py dataset_status
```

Run the 100-note queue through the application's **local** extraction, ICD-10 retrieval, independent verification and reconciliation workflow:

```powershell
python manage.py process_mtsamples_dataset --limit 100
```

This command never selects Groq, Gemini, or another external provider. It does not create Patient, Encounter, ClinicalNote, or ClinicalProcessingRun records. It stores note-level results only under the ignored `.dataset_working\\runs\\mtsamples\\` directory:

- `predictions.jsonl` — extracted entities, original-note evidence/offsets, candidate codes and source identifiers.
- `operations.jsonl` — per-note status, latency, attempts, provider identity and safe failure codes.
- `results.jsonl` — atomic checkpoint for resumable execution.
- `report.json` — aggregate counts and explicit evaluation status.

Use `--resume` to continue from the checkpoint after interruption, or `--overwrite` to start the batch outputs again. Do not commit these files because they contain note-linked extraction content.

The queue contains no trusted clinical gold labels by default. The batch report therefore marks clinical accuracy as **NOT EVALUATED** unless all selected records have qualified, independently sourced labels and the evaluation checks pass.

Validate the generated queue after trusted annotations have actually been supplied:

```powershell
python .\\mirai_dataset_preparation_pack\\scripts\\validate_annotations.py --input .\\.dataset_working\\annotations\\annotation_template_100.jsonl --require-complete
```

Show queue progress without treating unreviewed records as gold:

```powershell
python .\scripts\annotation_workflow.py --queue .\data\external\mtsamples\annotations\annotation_template_100.jsonl --progress
```

Import a reviewer export while preserving immutable note/provenance fields:

```powershell
python .\scripts\annotation_workflow.py `
  --queue .\data\external\mtsamples\annotations\annotation_template_100.jsonl `
  --import-annotations .\reviewer_export.jsonl `
  --merged-output .\merged_annotations.jsonl
```

Validate codes against the supplied reference and export qualified gold only:

```powershell
python .\scripts\validate_annotations.py `
  --input .\merged_annotations.jsonl `
  --icd-reference ..\data\reference\icd10cm-codes-2027.txt `
  --require-qualified `
  --export-qualified .\qualified.jsonl `
  --export-evaluation-cases .\evaluation_cases.jsonl
```

To run the package's own tests using synthetic test fixtures only:

```powershell
python -m unittest discover -s tests -v
```

## What this pack intentionally does not do

- It does not fabricate clinical labels, evidence spans, ICD-10-CM codes, or performance metrics.
- It does not call a language model or send any note text over the network.
- It does not merge or overwrite the existing project's code, database, or `data/` directory.
- It does not claim the 100-note SOW evaluation requirement is met until 100 suitable notes have complete, trusted labels and the required specialty coverage is verified.

## Provenance

See `SOURCE_ASSESSMENT.md` and `manifest.json`. Download date and actual file checksums/counts should be captured locally after obtaining the source file; no raw dataset was bundled into this preparation package.
