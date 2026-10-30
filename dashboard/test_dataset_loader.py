import json
from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import SimpleTestCase

from dashboard.extraction.dataset import (
    REQUIRED_RECORD_FIELDS,
    annotation_readiness,
    build_evaluation_gold_cases,
    load_jsonl,
)


class DatasetLoaderTests(SimpleTestCase):
    def _write(self, rows: list[object]) -> Path:
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / "records.jsonl"
        path.write_text(
            "\n".join(json.dumps(row) for row in rows) + "\n",
            encoding="utf-8",
        )
        return path

    def test_loader_skips_malformed_rows_without_exposing_note_text(self):
        note = "private clinical text must not appear in errors"
        path = self._write(
            [
                {
                    "record_id": "valid-1",
                    "source_dataset": "local:test",
                    "source_url": "https://example.test",
                    "source_row_number": 1,
                    "specialty": "General Medicine",
                    "note_text": note,
                },
                {"record_id": "invalid-1"},
                "not an object",
                {"record_id": "broken-json"},
            ]
        )
        path.write_text(
            path.read_text(encoding="utf-8") + '{"record_id":',
            encoding="utf-8",
        )

        result = load_jsonl(path, required_fields=REQUIRED_RECORD_FIELDS)

        self.assertEqual([record.record_id for record in result.records], ["valid-1"])
        self.assertTrue(result.errors)
        self.assertNotIn(note, " ".join(result.errors))

    def test_mtsamples_record_id_must_match_source_row(self):
        path = self._write(
            [
                {
                    "record_id": "mtsamples-00002-0123456789abcdef",
                    "source_dataset": "kaggle:tboyle10/medicaltranscriptions",
                    "source_url": "https://www.kaggle.com/datasets/tboyle10/medicaltranscriptions/data",
                    "source_row_number": 3,
                    "specialty": "Synthetic Specialty",
                    "note_text": "Synthetic assessment note.",
                }
            ]
        )

        result = load_jsonl(path, required_fields=REQUIRED_RECORD_FIELDS)

        self.assertEqual(result.records, ())
        self.assertTrue(any("does not match source_row_number" in error for error in result.errors))

    def test_duplicate_source_rows_are_rejected_even_with_distinct_ids(self):
        common = {
            "source_dataset": "synthetic:mirai-test",
            "source_url": "https://example.invalid/synthetic",
            "source_row_number": 1,
            "specialty": "Synthetic Specialty",
            "note_text": "Synthetic assessment note.",
        }
        path = self._write(
            [
                {"record_id": "synthetic-1", **common},
                {"record_id": "synthetic-2", **common},
            ]
        )

        result = load_jsonl(path, required_fields=REQUIRED_RECORD_FIELDS)

        self.assertEqual(len(result.records), 1)
        self.assertTrue(any("duplicate source row" in error for error in result.errors))

    def test_readiness_requires_eligible_completed_annotations(self):
        path = self._write(
            [
                {
                    "record_id": "queue-1",
                    "source_dataset": "local:test",
                    "source_url": "https://example.test",
                    "source_row_number": 1,
                    "specialty": "Surgery",
                    "note_text": "note",
                    "annotation_complete": True,
                    "adjudication_status": "adjudicated",
                    "clinical_performance_eligible": False,
                }
            ]
        )
        result = load_jsonl(path, required_fields=REQUIRED_RECORD_FIELDS)

        readiness = annotation_readiness(result)

        self.assertEqual(readiness["completed_annotations"], 1)
        self.assertFalse(readiness["gold_evaluation_ready"])
        self.assertEqual(readiness["ai_generated_benchmark_records"], 0)
        self.assertFalse(readiness["ai_generated_benchmark_ready"])

    def test_unqualified_queue_is_blocked_without_metric_cases(self):
        path = self._write(
            [
                {
                    "record_id": "queue-1",
                    "source_dataset": "local:test",
                    "source_url": "https://example.test",
                    "source_row_number": 1,
                    "specialty": "Surgery",
                    "note_text": "note",
                    "annotation_complete": False,
                    "annotation_status": "not_annotated",
                    "gold_annotations": None,
                    "adjudication_status": "not_reviewed",
                }
            ]
        )
        result = load_jsonl(
            path,
            required_fields=REQUIRED_RECORD_FIELDS
            | {
                "annotation_complete",
                "annotation_status",
                "gold_annotations",
                "adjudication_status",
            },
        )

        cases, report = build_evaluation_gold_cases(result)

        self.assertEqual(cases, [])
        self.assertEqual(report["metric_status"], "blocked")
        self.assertEqual(report["eligible_case_count"], 0)

    def test_human_labels_need_distinct_qualified_adjudicator_and_review_notes(self):
        metadata = {
            "label_source": "human_annotated",
            "label_provenance": {
                "dataset_version": "synthetic-v1",
                "annotation_guidelines": "synthetic-guidelines-v1",
                "license_or_dua": "synthetic-test-only",
            },
            "annotation_complete": True,
            "annotation_status": "adjudicated",
            "adjudication_status": "adjudicated",
            "annotator_id": "annotator-1",
            "adjudicator_id": "annotator-1",
            "annotator_qualification": {"qualified": True},
            "adjudication_notes": "Synthetic adjudication record.",
            "conflict_status": "not_applicable",
            "conflict_notes": "Synthetic conflict check.",
        }
        path = self._write(
            [
                {
                    "record_id": "synthetic-gold-1",
                    "source_dataset": "synthetic:mirai-test",
                    "source_url": "https://example.invalid/synthetic",
                    "source_row_number": 1,
                    "specialty": "Synthetic Specialty",
                    "note_text": "Synthetic assessment note.",
                    "annotation_complete": True,
                    "annotation_status": "adjudicated",
                    "adjudication_status": "adjudicated",
                    "clinical_performance_eligible": True,
                    "gold_annotations": {
                        "diagnoses": [],
                        "procedures": [],
                        "medications": [],
                        "allergies": [],
                        "vital_signs": [],
                        "icd10_cm_codes": [],
                    },
                    **metadata,
                }
            ]
        )
        result = load_jsonl(
            path,
            required_fields=REQUIRED_RECORD_FIELDS | {
                "annotation_complete",
                "annotation_status",
                "gold_annotations",
                "adjudication_status",
            },
        )
        readiness = annotation_readiness(result)
        self.assertEqual(readiness["clinical_performance_eligible"], 0)
        self.assertFalse(readiness["gold_evaluation_ready"])

    def test_ai_benchmark_status_is_separate_from_gold_readiness(self):
        path = self._write(
            [
                {
                    "record_id": "benchmark-1",
                    "source_dataset": "local:test",
                    "source_url": "https://example.test",
                    "source_row_number": 1,
                    "specialty": "Surgery",
                    "note_text": "note",
                    "annotation_complete": False,
                    "annotation_status": "not_annotated",
                    "gold_annotations": None,
                    "adjudication_status": "not_reviewed",
                    "label_source": "ai_model",
                    "clinical_performance_eligible": False,
                }
            ]
        )
        result = load_jsonl(
            path,
            required_fields=REQUIRED_RECORD_FIELDS
            | {
                "annotation_complete",
                "annotation_status",
                "gold_annotations",
                "adjudication_status",
            },
        )

        readiness = annotation_readiness(result)

        self.assertFalse(readiness["ai_generated_benchmark_ready"])
        self.assertEqual(readiness["ai_generated_benchmark_records"], 0)
        self.assertFalse(readiness["gold_evaluation_ready"])

    def test_ai_benchmark_ready_requires_completed_annotation_payload_and_provenance(self):
        annotation_categories = {
            "diagnoses": [],
            "procedures": [],
            "medications": [],
            "allergies": [],
            "vital_signs": [],
            "icd10_cm_codes": [],
        }
        path = self._write(
            [
                {
                    "record_id": "benchmark-complete-1",
                    "source_dataset": "local:test",
                    "source_url": "https://example.test",
                    "source_row_number": 1,
                    "specialty": "Surgery",
                    "note_text": "note",
                    "annotation_complete": True,
                    "annotation_status": "complete",
                    "gold_annotations": annotation_categories,
                    "adjudication_status": "not_required",
                    "expected_needs_review": False,
                    "label_source": "ai_model",
                    "clinical_performance_eligible": False,
                    "model_provider": "test-provider",
                    "model_id": "synthetic-model-v1",
                }
            ]
        )
        result = load_jsonl(
            path,
            required_fields=REQUIRED_RECORD_FIELDS
            | {
                "annotation_complete",
                "annotation_status",
                "gold_annotations",
                "adjudication_status",
            },
        )

        readiness = annotation_readiness(result)

        self.assertTrue(readiness["ai_generated_benchmark_ready"])
        self.assertEqual(readiness["ai_generated_benchmark_records"], 1)
        self.assertFalse(readiness["gold_evaluation_ready"])
