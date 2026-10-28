# Dataset source assessment — pre-download review

**Assessment date:** 2026-10-23
**Primary source required by Mirai Labs:** Kaggle
**Selected candidate:** Medical Transcriptions (MTSamples), `tboyle10/medicaltranscriptions`

## Source details observed from public metadata

- Kaggle source page: https://www.kaggle.com/datasets/tboyle10/medicaltranscriptions/data
- Dataset description: sample medical transcription text for multiple medical specialties.
- Declared license on Kaggle page: CC0: Public Domain.
- Kaggle page identifies `mtsamples.csv` and reports file size around 17.01 MB with six columns.
- A secondary dataset reference describes 4,999 rows and six variables covering note description, specialty, sample name, transcription, and keywords.
- Another secondary data inspection reports that some rows have missing transcription or keyword values. Exact missingness must be recomputed from the exact Kaggle version downloaded by the user.

## Suitability for Mirai Labs SOW

| Requirement | Availability in source metadata | Assessment |
|---|---|---|
| Free-text transcription | Yes, `transcription` | Useful after validating non-empty rows and text quality |
| Specialty labels | Yes, `medical_specialty` | Useful for corpus coverage; actual specialty count must be calculated from downloaded file |
| Descriptive context | `description`, `sample_name` | Useful metadata, not verified target labels |
| Keywords | `keywords` field | Weak/unspecified provenance; not gold entity annotations |
| Diagnosis/procedure/medication/allergy/vital gold spans | Not evidenced | Must not be assumed available |
| Assertion/status labels | Not evidenced | Requires trustworthy annotations |
| Source offsets for gold evidence | Not evidenced | Requires trustworthy annotations |
| Note-specific ICD-10-CM reference codes | Not evidenced | Cannot measure note-to-code top-3 accuracy from this corpus alone |
| Contradiction/adversarial labels | Not evidenced | Requires curated, adjudicated challenge cases |

## Decision

Use MTSamples as the **primary Kaggle-sourced text corpus** for data-ingestion and multi-specialty development. After downloading the exact Kaggle archive, run `scripts/analyze_mtsamples.py` and inspect the output before treating any row count, specialty count, or missing-value count as verified.

Do not claim this corpus on its own satisfies the SOW's labelled clinical evaluation requirement. Create a 100-record annotation queue from available distinct notes. Qualified review is still necessary for trusted entity/status/evidence/code labels. If the actual downloaded file provides fewer than ten specialties or fewer than 100 eligible distinct notes, the report must say so and the team must obtain an additional permitted dataset or revise the scope with Mirai Labs.

## Download/access limitation in the preparation environment

The current assistant execution environment could not retrieve the raw Kaggle archive because outbound dataset downloads are unavailable. This package therefore contains the downloader, local analyzer, validation workflow, and placeholders, **not a copy of the dataset**. Download the archive through Kaggle in your browser or run the downloader on your Windows machine if Kaggle CLI is already authenticated locally.
