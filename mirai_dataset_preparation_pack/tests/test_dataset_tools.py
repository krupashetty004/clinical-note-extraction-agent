"""Offline tests for the dataset-preparation tools using synthetic fixtures only."""
from __future__ import annotations
import csv
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

ANALYZER = load_module("analyze_mtsamples", ROOT / "scripts" / "analyze_mtsamples.py")
VALIDATOR = load_module("validate_annotations", ROOT / "scripts" / "validate_annotations.py")
WORKFLOW = load_module("annotation_workflow", ROOT / "scripts" / "annotation_workflow.py")


class AnalyzerTests(unittest.TestCase):
    def write_csv(self, directory: Path) -> Path:
        path = directory / "mtsamples.csv"
        headers = ["description", "medical_specialty", "sample_name", "transcription", "keywords"]
        rows = [
            ["Synthetic summary A", "Cardiology", "sample-a", "Assessment: hypertension.", "hypertension"],
            ["Synthetic summary B", "Neurology", "sample-b", "No headache reported.", "headache"],
            ["Synthetic summary C", "Cardiology", "sample-c", "Assessment: hypertension.", "hypertension"],
            ["Synthetic summary D", "Orthopedics", "sample-d", "Procedure: synthetic knee exam.", "knee"],
            ["Synthetic summary E", "", "sample-e", "", ""],
        ]
        with path.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.writer(handle)
            writer.writerow(headers)
            writer.writerows(rows)
        return path

    def test_analysis_outputs_report_records_and_unlabelled_template(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = self.write_csv(tmp_path)
            report = ANALYZER.analyze(
                source,
                tmp_path / "prepared",
                tmp_path / "annotations",
                tmp_path / "reports",
                annotation_limit=3,
                minimum_specialties=3,
            )
            self.assertEqual(report["source_rows_loaded"], 5)
            self.assertEqual(report["rows_with_nonempty_transcription"], 4)
            self.assertEqual(report["duplicate_nonempty_transcription_rows_after_casefold_strip"], 1)
            self.assertEqual(report["annotation_queue_created"], 3)
            self.assertFalse(report["annotation_queue_is_gold_labelled"])
            normalized = [json.loads(line) for line in (tmp_path / "prepared" / "records.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(normalized), 4)
            self.assertTrue(all(record["gold_annotations"] is None for record in normalized))
            queue = [json.loads(line) for line in (tmp_path / "annotations" / "annotation_template_3.jsonl").read_text(encoding="utf-8").splitlines()]
            self.assertEqual(len(queue), 3)
            self.assertTrue(all(item["annotation_complete"] is False for item in queue))
            markdown = (tmp_path / "reports" / "dataset_quality_report.md").read_text(encoding="utf-8")
            self.assertNotIn("Assessment: hypertension.", markdown)

    def test_missing_input_fails_explicitly(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(FileNotFoundError):
                ANALYZER.load_csv(Path(tmp) / "missing.csv")

    def test_annotation_queue_enforces_minimum_specialty_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = self.write_csv(tmp_path)
            with self.assertRaisesRegex(ValueError, "at least 4 are required"):
                ANALYZER.analyze(
                    source,
                    tmp_path / "prepared",
                    tmp_path / "annotations",
                    tmp_path / "reports",
                    annotation_limit=3,
                    minimum_specialties=4,
                )

    def test_annotation_queue_accepts_required_specialty_coverage(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = self.write_csv(tmp_path)
            report = ANALYZER.analyze(
                source,
                tmp_path / "prepared",
                tmp_path / "annotations",
                tmp_path / "reports",
                annotation_limit=3,
                minimum_specialties=3,
            )
            self.assertEqual(report["annotation_queue_specialty_count"], 3)
            self.assertTrue(report["annotation_queue_meets_minimum_specialties"])

    def test_invalid_minimum_specialty_coverage_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            source = self.write_csv(tmp)
            for invalid_value in (0, -1, True):
                with self.subTest(value=invalid_value):
                    with self.assertRaisesRegex(ValueError, "minimum_specialties"):
                        ANALYZER.analyze(
                            source,
                            tmp_path / "prepared",
                            tmp_path / "annotations",
                            tmp_path / "reports",
                            annotation_limit=3,
                            minimum_specialties=invalid_value,
                        )


class AnnotationValidatorTests(unittest.TestCase):
    def base_record(self):
        note = "Assessment: hypertension."
        start = note.index("hypertension")
        return {
            "record_id": "synthetic-test-1",
            "source_dataset": VALIDATOR.SOURCE_ID,
            "source_url": VALIDATOR.SOURCE_URL,
            "source_row_number": 1,
            "specialty": "Synthetic specialty",
            "note_text": note,
            "annotation_complete": True,
            "annotation_status": "complete",
            "annotator_id": "reviewer-test",
            "adjudication_status": "adjudicated",
            "conflict_status": "not_applicable",
            "conflict_notes": "No conflicting annotations identified.",
            "label_source": "human_annotated",
            "label_provenance": {
                "dataset_version": "1.0",
                "annotation_guidelines": "v1.0",
                "license_or_dua": "synthetic-open",
            },
            "gold_annotations": {
                "diagnoses": [{"entity": "hypertension", "status": "active", "evidence_text": "hypertension", "start_offset": start, "end_offset": start + len("hypertension")}],
                "procedures": [], "medications": [], "allergies": [], "vital_signs": [], "icd10_cm_codes": [],
            },
        }

    def test_correct_offsets_validate(self):
        self.assertEqual(VALIDATOR.validate_record(self.base_record(), 1), [])

    def test_mismatched_evidence_is_rejected(self):
        record = self.base_record()
        record["gold_annotations"]["diagnoses"][0]["evidence_text"] = "hypotension"
        errors = VALIDATOR.validate_record(record, 1)
        self.assertTrue(any("does not match note_text" in error for error in errors))

    def test_incomplete_annotation_is_not_counted_as_gold(self):
        record = self.base_record()
        record["annotation_complete"] = False
        record["gold_annotations"] = None
        self.assertEqual(VALIDATOR.validate_record(record, 1), [])

    def test_missing_provenance_is_rejected(self):
        record = self.base_record()
        record.pop("source_url")
        errors = VALIDATOR.validate_record(record, 1)
        self.assertTrue(any("source_url" in error for error in errors))

    def test_qualified_export_requires_adjudication_and_qualification(self):
        record = self.base_record()
        ready, errors = VALIDATOR.evaluation_ready_records([record])
        self.assertEqual(ready, [])
        self.assertTrue(any("adjudicator_id" in error for error in errors))

        record.update(
            {
                "annotation_status": "adjudicated",
                "adjudicator_id": "adjudicator-test",
                "adjudication_notes": "Synthetic independent adjudication.",
                "annotator_qualification": {
                    "qualified": True,
                    "basis": "Synthetic test qualification.",
                },
            }
        )
        ready, errors = VALIDATOR.evaluation_ready_records([record])
        self.assertEqual(errors, [])
        self.assertEqual(len(ready), 1)
        self.assertTrue(ready[0]["clinical_performance_eligible"])

    def test_evaluation_case_export_requires_explicit_review_label(self):
        record = self.base_record()
        record.update(
            {
                "annotation_status": "adjudicated",
                "adjudicator_id": "adjudicator-test",
                "adjudication_notes": "Synthetic independent adjudication.",
                "annotator_qualification": {"qualified": True},
                "expected_needs_review": False,
            }
        )

        cases, errors = VALIDATOR.evaluation_cases_from_records([record])

        self.assertEqual(errors, [])
        self.assertEqual(cases[0]["case_id"], "synthetic-test-1")
        self.assertTrue(cases[0]["gold_qualified"])
        self.assertEqual(cases[0]["gold_items"][0]["category"], "diagnosis")

    def test_invalid_icd_code_and_missing_entity_are_rejected(self):
        record = self.base_record()
        record["gold_annotations"]["diagnoses"][0].pop("entity")
        record["gold_annotations"]["icd10_cm_codes"] = [
            {"code": "not-a-code", "description": "Synthetic"}
        ]
        errors = VALIDATOR.validate_record(record, 1)
        self.assertTrue(any("requires a non-empty entity" in error for error in errors))
        self.assertTrue(any("icd10_cm_codes" in error for error in errors))

    def test_entity_must_be_grounded_in_evidence(self):
        record = self.base_record()
        record["gold_annotations"]["diagnoses"][0]["entity"] = "diabetes"
        errors = VALIDATOR.validate_record(record, 1)
        self.assertTrue(any("not grounded" in error for error in errors))

    def test_icd_reference_description_is_checked_when_supplied(self):
        record = self.base_record()
        record["gold_annotations"]["icd10_cm_codes"] = [
            {"code": "I10", "description": "Essential (primary) hypertension"}
        ]
        errors = VALIDATOR.validate_record(
            record,
            1,
            icd_reference={"I10": "Essential (primary) hypertension"},
        )
        self.assertEqual(errors, [])

        errors = VALIDATOR.validate_record(
            record,
            1,
            icd_reference={"I10": "Different description"},
        )
        self.assertTrue(any("description does not match" in error for error in errors))

    def test_conflicting_same_span_annotations_are_rejected(self):
        record = self.base_record()
        start = record["note_text"].index("hypertension")
        record["gold_annotations"]["diagnoses"].append(
            {
                "entity": "hypertension",
                "status": "ruled_out",
                "evidence_text": "hypertension",
                "start_offset": start,
                "end_offset": start + len("hypertension"),
            }
        )
        errors = VALIDATOR.validate_record(record, 1)
        self.assertTrue(any("conflicts with another annotation" in error for error in errors))


class AnnotationWorkflowTests(unittest.TestCase):
    def test_progress_distinguishes_annotation_adjudication_and_qualification(self):
        queue = [
            {
                "record_id": "one",
                "specialty": "Cardiology",
                "annotation_complete": False,
                "adjudication_status": "not_reviewed",
            },
            {
                "record_id": "two",
                "specialty": "Neurology",
                "annotation_complete": True,
                "adjudication_status": "adjudicated",
            },
        ]
        report = WORKFLOW.progress_report(queue)
        self.assertEqual(report["prepared_notes"], 2)
        self.assertEqual(report["annotated_notes"], 1)
        self.assertEqual(report["adjudicated_notes"], 1)
        self.assertEqual(report["qualified_notes"], 0)
        self.assertEqual(report["specialties_in_queue"], 2)

    def test_import_preserves_note_and_provenance(self):
        queue = [{
            "record_id": "one",
            "source_dataset": VALIDATOR.SOURCE_ID,
            "source_url": VALIDATOR.SOURCE_URL,
            "source_row_number": 1,
            "specialty": "Cardiology",
            "note_text": "Assessment: hypertension.",
            "source_keywords": "hypertension",
            "annotation_complete": False,
        }]
        imported = [dict(
            queue[0],
            annotation_complete=True,
            annotation_status="complete",
            annotator_id="a",
            adjudication_status="not_required",
            conflict_status="not_applicable",
            conflict_notes="No conflicts identified.",
            gold_annotations={
                "diagnoses": [{
                    "entity": "hypertension",
                    "status": "active",
                    "evidence_text": "hypertension",
                    "start_offset": 12,
                    "end_offset": 24,
                }],
                "procedures": [],
                "medications": [],
                "allergies": [],
                "vital_signs": [],
                "icd10_cm_codes": [],
            },
        )]
        merged = WORKFLOW.merge_import(queue, imported)
        self.assertTrue(merged[0]["annotation_complete"])
        imported[0]["note_text"] = "changed"
        with self.assertRaisesRegex(ValueError, "immutable field note_text"):
            WORKFLOW.merge_import(queue, imported)

    def test_keyword_suggestions_are_explicitly_unverified(self):
        records = [{
            "record_id": "one",
            "note_text": "Assessment: hypertension.",
            "source_keywords": "hypertension",
        }]
        suggestions = WORKFLOW.provisional_suggestions(records)
        self.assertTrue(suggestions[0]["suggestions_are_unverified"])
        self.assertFalse(suggestions[0]["items"][0]["verified"])

if __name__ == "__main__":
    unittest.main()
