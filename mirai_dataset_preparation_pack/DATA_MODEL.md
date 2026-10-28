# Prepared record and annotation model

`prepared/records.jsonl` records are normalized copies of source rows. Important fields:

- `record_id`: stable identifier derived from source row number, specialty, and text hash.
- `source_dataset`, `source_url`, `source_row_number`, `source_record_id`: source provenance.
- `specialty`: source-supplied specialty label; not an extracted disease label.
- `source_keywords`: original source keywords; never treated as gold entity annotations.
- `note_text`: source transcription.
- `annotation_status: not_annotated`, `gold_annotations: null`, `clinical_performance_eligible: false`: explicit signals not to use this record as labelled gold truth yet.
- `split`: deterministic train/validation/test organizational split by specialty. These splits are not a valid clinical evaluation split until trusted labels exist.

`annotations/annotation_template_100.jsonl` is an annotation queue. A reviewer should set `annotation_complete` to `true` only after required annotation fields have been reviewed. For each entity category, an empty list means a reviewer checked and found no entity in that category; `null` means not yet annotated. Entity records should contain the entity text, status/assertion where applicable, `evidence_text`, `start_offset`, and `end_offset`. Offsets are Python character offsets into `note_text`, end-exclusive. `icd10_cm_codes` should only include independently verified reference codes and descriptions. `adjudication_status` must be updated by the approved review process.

The queue also tracks `conflict_status` and `conflict_notes`. Completed records must explicitly mark conflicts as `not_applicable` or `resolved`; resolved conflicts require notes. Diagnosis statuses are `active`, `historical`, `ruled_out`, or `suspected`; medication statuses are `current`, `discontinued`, or `newly_prescribed`. Procedures, allergies, and vital signs do not use a status field under the current extraction contract.

Use `scripts/annotation_workflow.py` to import reviewer updates without allowing note text or provenance changes, report progress, export only qualified records, and create optional keyword suggestions. Suggestions are always outside `gold_annotations` and carry `verified: false`; a human must confirm or reject them.

Do not set `clinical_performance_eligible` to true until annotation completeness, evidence offsets, coding labels (where applicable), and adjudication requirements have been independently checked. The validator enforces evidence offsets but cannot establish clinical correctness or code validity.
