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

Place this folder in your project root as `dataset-preparation` (or another non-conflicting name). Do not merge this package into the existing `data/` folder; your repository already has local data files that must be preserved.

### Option A — Kaggle CLI already installed and authenticated locally

From PowerShell inside this package folder:

```powershell
.\scripts\download_mtsamples.ps1
```

The script checks for existing files and refuses to overwrite them. It uses locally configured Kaggle CLI authentication if available; it never prints credentials. It does not install software or ask you to paste tokens.

### Option B — Manual browser download

1. Sign in to Kaggle in your browser and open https://www.kaggle.com/datasets/tboyle10/medicaltranscriptions/data
2. Download the dataset ZIP.
3. Extract the archive and copy the original `mtsamples.csv` into:
   `data\external\mtsamples\raw\mtsamples.csv`
4. Keep the downloaded ZIP locally if needed for provenance, but do not put credentials in this folder.

### Analyze and prepare the downloaded file

This package uses only Python's standard library; no package installation is needed.

```powershell
python .\scripts\analyze_mtsamples.py
```

Expected outputs, after the raw CSV is supplied:

- `reports\dataset_quality_report.md` — counts, missingness, specialties, duplicates, suitability checks.
- `reports\dataset_quality_report.json` — machine-readable report.
- `data\external\mtsamples\prepared\records.jsonl` — normalized records with source provenance, deterministic splits, and explicit `gold_annotations: null`.
- `data\external\mtsamples\annotations\annotation_template_100.jsonl` — up to 100 distinct notes selected breadth-first across specialties for human labelling. Each starts with `annotation_complete: false`; it is not gold data.

Validate annotations after qualified reviewers complete the template:

```powershell
python .\scripts\validate_annotations.py --input .\data\external\mtsamples\annotations\annotation_template_100.jsonl --require-complete
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
