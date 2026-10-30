"""Offline tests for the AI benchmark annotation runner; no provider calls."""
from __future__ import annotations

import json
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

from dashboard.extraction.dataset import (
    DatasetRecord,
    REQUIRED_RECORD_FIELDS,
    annotation_readiness,
    load_jsonl,
)
from evaluation.generate_ai_benchmark import (
    benchmark_case_to_queue_record,
    build_benchmark_case,
    is_synthetic_record,
    _safe_failure_diagnostics,
    validate_annotation_payload,
)


class AIBenchmarkGeneratorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.note = "Assessment: type 2 diabetes. Medication: metformin."
        self.diabetes_start = self.note.index("type 2 diabetes")
        self.metformin_start = self.note.index("metformin")
        self.record = DatasetRecord(
            record_id="SYN-001",
            source_dataset="synthetic:mirai-stage3",
            source_url="local://synthetic",
            source_row_number=1,
            specialty="Synthetic",
            note_text=self.note,
            metadata={
                "record_id": "SYN-001",
                "source_dataset": "synthetic:mirai-stage3",
                "source_url": "local://synthetic",
                "source_row_number": 1,
                "specialty": "Synthetic",
                "note_text": self.note,
                "annotation_complete": False,
            },
        )
        self.payload = {
            "items": [
                {
                    "category": "diagnosis",
                    "entity": "type 2 diabetes",
                    "status": "active",
                    "evidence_text": "type 2 diabetes",
                    "start_offset": self.diabetes_start,
                    "end_offset": self.diabetes_start + len("type 2 diabetes"),
                    "attributes": {},
                    "icd10_code": "E11.9",
                    "icd10_description": "Type 2 diabetes mellitus without complications",
                },
                {
                    "category": "medication",
                    "entity": "metformin",
                    "status": "current",
                    "evidence_text": "metformin",
                    "start_offset": self.metformin_start,
                    "end_offset": self.metformin_start + len("metformin"),
                    "attributes": {},
                },
            ],
            "expected_needs_review": False,
            "review_reasons": [],
        }

    def test_valid_payload_builds_ai_benchmark_case_with_provenance(self):
        case = build_benchmark_case(
            self.record,
            self.payload,
            model_provider="groq",
            model_id="synthetic-test-model",
            annotated_at_utc=datetime(2026, 1, 1, tzinfo=timezone.utc).isoformat(),
        )
        self.assertEqual(case["case_id"], "SYN-001")
        self.assertEqual(case["gold_items"][0]["icd10_code"], "E11.9")
        self.assertEqual(case["model_provider"], "groq")
        self.assertEqual(case["model_id"], "synthetic-test-model")
        self.assertEqual(case["label_source"], "ai_model")
        self.assertFalse(case["clinical_performance_eligible"])

    def test_rejects_mismatched_evidence_offsets(self):
        bad = {**self.payload, "items": [dict(self.payload["items"][0], start_offset=0)]}
        with self.assertRaisesRegex(ValueError, "evidence offsets"):
            validate_annotation_payload(self.note, bad)

    def test_requires_explicit_review_boolean_and_reasons(self):
        bad = {**self.payload, "expected_needs_review": "false"}
        with self.assertRaisesRegex(ValueError, "expected_needs_review"):
            validate_annotation_payload(self.note, bad)

    def test_rejects_invalid_category_specific_status(self):
        bad_item = dict(self.payload["items"][1], status="active")
        bad = {**self.payload, "items": [bad_item]}
        with self.assertRaisesRegex(ValueError, "invalid medication status"):
            validate_annotation_payload(self.note, bad)

    def test_rejects_code_without_description(self):
        bad_item = dict(self.payload["items"][0])
        bad_item.pop("icd10_description")
        bad = {**self.payload, "items": [bad_item]}
        with self.assertRaisesRegex(ValueError, "requires icd10_description"):
            validate_annotation_payload(self.note, bad)

    def test_empty_annotation_is_accepted_only_as_explicit_model_response(self):
        items, needs_review, reasons = validate_annotation_payload(
            self.note,
            {"items": [], "expected_needs_review": True, "review_reasons": ["Unclear note"]},
        )
        self.assertEqual(items, [])
        self.assertTrue(needs_review)
        self.assertEqual(reasons, ["Unclear note"])

    def test_queue_output_keeps_ai_labelled_data_separate_from_clinical_gold(self):
        case = build_benchmark_case(
            self.record, self.payload, model_provider="groq", model_id="synthetic-test-model"
        )
        queue_record = benchmark_case_to_queue_record(self.record, case)
        self.assertTrue(queue_record["annotation_complete"])
        self.assertEqual(queue_record["annotation_status"], "complete")
        self.assertEqual(queue_record["label_source"], "ai_model")
        self.assertFalse(queue_record["clinical_performance_eligible"])
        self.assertEqual(queue_record["label_provenance"]["model_or_provider"], "groq/synthetic-test-model")
        self.assertEqual(queue_record["label_provenance"]["generation_timestamp"], queue_record["annotation_timestamp_utc"])
        self.assertEqual(len(queue_record["gold_annotations"]["diagnoses"]), 1)
        self.assertEqual(len(queue_record["gold_annotations"]["medications"]), 1)
        self.assertEqual(queue_record["gold_annotations"]["icd10_cm_codes"][0]["code"], "E11.9")
        self.assertEqual(queue_record["adjudication_status"], "not_reviewed")

    def test_queue_record_is_recognized_as_ai_benchmark_not_clinical_gold(self):
        case = build_benchmark_case(
            self.record, self.payload, model_provider="groq", model_id="synthetic-test-model"
        )
        queue_record = benchmark_case_to_queue_record(self.record, case)
        with TemporaryDirectory() as temporary_directory:
            path = Path(temporary_directory) / "ai_queue.jsonl"
            path.write_text(json.dumps(queue_record) + "\n", encoding="utf-8")
            loaded = load_jsonl(path, required_fields=REQUIRED_RECORD_FIELDS)
            readiness = annotation_readiness(loaded)

        self.assertEqual(readiness["ai_generated_benchmark_records"], 1)
        self.assertTrue(readiness["ai_generated_benchmark_ready"])
        self.assertFalse(readiness["gold_evaluation_ready"])

    def test_failure_diagnostics_classify_bad_offsets_without_note_content(self):
        detail = _safe_failure_diagnostics(ValueError("item 1 evidence offsets do not match the source note"))
        self.assertEqual(detail["failure_phase"], "annotation_validation")
        self.assertEqual(detail["error_code"], "evidence_offsets_invalid")
        self.assertNotIn("note", " ".join(detail.keys()).casefold())
        self.assertNotIn("evidence offsets", str(detail).casefold())

    def test_failure_diagnostics_classify_provider_errors_without_message(self):
        from dashboard.extraction.groq_provider import GroqProviderError

        error = GroqProviderError("Groq request failed.", code="provider_failed")
        detail = _safe_failure_diagnostics(error)
        self.assertEqual(detail["failure_phase"], "provider_request")
        self.assertEqual(detail["error_code"], "provider_failed")
        self.assertNotIn("Groq request failed", str(detail))

    def test_source_gate_allows_only_explicit_synthetic_names(self):
        self.assertTrue(is_synthetic_record(self.record))
        external = DatasetRecord(
            record_id="EXT-1", source_dataset="kaggle:medicaltranscriptions",
            source_url="https://example.test", source_row_number=1,
            specialty="Surgery", note_text="note", metadata={},
        )
        self.assertFalse(is_synthetic_record(external))


if __name__ == "__main__":
    unittest.main()
