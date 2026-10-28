"""Synthetic tests for the evaluation metrics."""

from django.test import SimpleTestCase
from pathlib import Path
import json
import tempfile

from evaluation.metrics import evaluate_dataset
from evaluation.metrics import (
    build_sow_evaluation_report,
    compare_system_metrics,
    evaluate_operational_metrics,
    evaluate_qualified_dataset,
    select_poor_performing_cases,
)
from evaluation.sow_report import build_report


def make_case_pair():
    """Build a small manually labelled synthetic evaluation case."""
    note = "Assessment: diabetes. Medication: metformin."

    diabetes = "diabetes"
    diabetes_start = note.index(diabetes)

    metformin = "metformin"
    metformin_start = note.index(metformin)

    gold = [
        {
            "case_id": "SYN-EVAL-001",
            "note": note,
            "gold_items": [
                {
                    "category": "diagnosis",
                    "entity": "diabetes",
                    "status": "active",
                    "evidence_text": diabetes,
                    "start_offset": diabetes_start,
                    "end_offset": diabetes_start + len(diabetes),
                    "icd10_code": "E119",
                },
                {
                    "category": "medication",
                    "entity": "metformin",
                    "status": "current",
                    "evidence_text": metformin,
                    "start_offset": metformin_start,
                    "end_offset": metformin_start + len(metformin),
                },
            ],
            "expected_needs_review": False,
        }
    ]

    predictions = [
        {
            "case_id": "SYN-EVAL-001",
            "items": [
                {
                    "category": "diagnosis",
                    "entity": "DIABETES",
                    "status": "active",
                    "evidence_text": diabetes,
                    "start_offset": diabetes_start,
                    "end_offset": diabetes_start + len(diabetes),
                    "decision": "accepted",
                    "icd10_candidates": ["E119", "R739"],
                },
                {
                    "category": "medication",
                    "entity": "metformin",
                    "status": "current",
                    "evidence_text": metformin,
                    "start_offset": metformin_start,
                    "end_offset": metformin_start + len(metformin),
                    "decision": "accepted",
                    "icd10_candidates": [],
                },
            ],
            "needs_review": False,
        }
    ]

    return gold, predictions


class EvaluationMetricsTests(SimpleTestCase):
    def setUp(self):
        # The report tests only need an empty queue to prove clinical gold is
        # unavailable. Use a temporary synthetic fixture instead of any local
        # source dataset that is intentionally excluded from version control.
        self._temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._temporary_directory.cleanup)
        self._queue_file = Path(self._temporary_directory.name) / "synthetic_empty_queue.jsonl"
        self._queue_file.write_text("", encoding="utf-8")

    def _queue_path(self) -> Path:
        return self._queue_file

    def test_ai_benchmark_is_reported_separately_from_clinical_gold(self):
        note = "Assessment: diabetes."
        benchmark_cases = [
            {
                "case_id": "AI-BENCH-001",
                "note": note,
                "gold_items": [
                    {
                        "category": "diagnosis",
                        "entity": "diabetes",
                        "status": "active",
                        "evidence_text": "diabetes",
                        "start_offset": note.index("diabetes"),
                        "end_offset": note.index("diabetes") + len("diabetes"),
                    }
                ],
                "label_source": "ai_model",
                "clinical_performance_eligible": False,
                "expected_needs_review": False,
                "model_provider": "test-provider",
                "model_id": "synthetic-model-v1",
            }
        ]

        report = build_report(
            queue_path=self._queue_path(),
            challenge_report={"overall_status": "Not yet measured"},
            smoke_report={},
            ai_benchmark_cases=benchmark_cases,
        )

        self.assertEqual(
            report["ai_generated_benchmark"]["status"],
            "NOT EVALUATED",
        )
        self.assertFalse(report["ai_generated_benchmark"]["clinical_performance_claimed"])
        self.assertEqual(report["clinical_metrics"]["status"], "NOT EVALUATED")

    def test_ai_benchmark_predictions_are_scored_without_clinical_gold_qualification(self):
        gold, predictions = make_case_pair()
        gold[0].update(
            {
                "label_source": "ai_model",
                "clinical_performance_eligible": False,
                "model_provider": "test-provider",
                "model_id": "synthetic-model-v1",
            }
        )

        report = build_report(
            queue_path=self._queue_path(),
            challenge_report={"overall_status": "Not yet measured"},
            smoke_report={},
            ai_benchmark_cases=gold,
            ai_benchmark_predictions=predictions,
        )

        benchmark = report["ai_generated_benchmark"]
        self.assertEqual(benchmark["status"], "AI_BENCHMARK_ONLY")
        self.assertFalse(benchmark["clinical_performance_claimed"])
        self.assertEqual(benchmark["metrics"]["case_count"], 1)
        self.assertEqual(benchmark["metrics"]["category_metrics"]["all"]["f1"], 1.0)
        self.assertEqual(report["clinical_metrics"]["status"], "NOT EVALUATED")

    def test_ai_benchmark_rejects_mismatched_source_offsets(self):
        report = build_report(
            queue_path=self._queue_path(),
            challenge_report={},
            smoke_report={},
            ai_benchmark_cases=[
                {
                    "case_id": "AI-BENCH-INVALID",
                    "note": "Assessment: diabetes.",
                    "gold_items": [
                        {
                            "category": "diagnosis",
                            "entity": "diabetes",
                            "evidence_text": "not diabetes",
                            "start_offset": 0,
                            "end_offset": 12,
                        }
                    ],
                    "label_source": "ai_model",
                    "clinical_performance_eligible": False,
                    "expected_needs_review": False,
                    "model_provider": "test-provider",
                    "model_id": "synthetic-model-v1",
                }
            ],
        )

        self.assertEqual(report["ai_generated_benchmark"]["status"], "INVALID")
        self.assertFalse(report["ai_generated_benchmark"]["clinical_performance_claimed"])

    def test_perfect_predictions_have_perfect_entity_metrics(self):
        gold, predictions = make_case_pair()

        result = evaluate_dataset(gold, predictions)

        self.assertEqual(result["case_count"], 1)
        self.assertEqual(
            result["category_metrics"]["diagnosis"]["f1"],
            1.0,
        )
        self.assertEqual(
            result["category_metrics"]["medication"]["f1"],
            1.0,
        )
        self.assertEqual(
            result["category_metrics"]["all"]["f1"],
            1.0,
        )

    def test_valid_spans_and_accepted_items_are_scored(self):
        gold, predictions = make_case_pair()

        result = evaluate_dataset(gold, predictions)

        self.assertEqual(
            result["evidence_span_integrity"]["rate"],
            1.0,
        )
        self.assertEqual(
            result["accepted_item_gold_match_rate"]["rate"],
            1.0,
        )
        self.assertEqual(
            result["status_accuracy"]["accuracy"],
            1.0,
        )

    def test_icd10_top1_and_top3_are_calculated(self):
        gold, predictions = make_case_pair()

        predictions[0]["items"][0]["icd10_candidates"] = [
            "R739",
            "E119",
        ]

        result = evaluate_dataset(gold, predictions)

        self.assertEqual(result["icd10"]["labelled_diagnoses"], 1)
        self.assertEqual(result["icd10"]["top1_accuracy"], 0.0)
        self.assertEqual(result["icd10"]["top3_accuracy"], 1.0)

    def test_false_positive_reduces_precision(self):
        gold, predictions = make_case_pair()

                # Add a mention that is present in the note but absent from gold.
        note = gold[0]["note"] + " Fever reported."
        gold[0]["note"] = note

        false_entity = "Fever"
        start = note.index(false_entity)

        predictions[0]["items"].append(
            {
                "category": "diagnosis",
                "entity": "fever",
                "status": "active",
                "evidence_text": false_entity,
                "start_offset": start,
                "end_offset": start + len(false_entity),
                "decision": "accepted",
                "icd10_candidates": [],
            }
        )

        result = evaluate_dataset(gold, predictions)
        metrics = result["category_metrics"]["diagnosis"]

        self.assertEqual(metrics["true_positives"], 1)
        self.assertEqual(metrics["predicted_count"], 2)
        self.assertEqual(metrics["gold_count"], 1)
        self.assertEqual(metrics["precision"], 0.5)
        self.assertEqual(metrics["recall"], 1.0)
        self.assertEqual(metrics["f1"], 0.666667)

    def test_invalid_evidence_span_is_not_counted_as_valid(self):
        gold, predictions = make_case_pair()

        predictions[0]["items"][0]["evidence_text"] = "blood sugar"

        result = evaluate_dataset(gold, predictions)

        self.assertEqual(
            result["evidence_span_integrity"]["valid_spans"],
            1,
        )
        self.assertEqual(
            result["evidence_span_integrity"]["predicted_items"],
            2,
        )
        self.assertEqual(
            result["evidence_span_integrity"]["rate"],
            0.5,
        )
        self.assertEqual(
            result["accepted_item_gold_match_rate"]["rate"],
            0.5,
        )

    def test_status_mismatch_is_counted_separately(self):
        gold, predictions = make_case_pair()

        predictions[0]["items"][0]["status"] = "historical"

        result = evaluate_dataset(gold, predictions)

        self.assertEqual(
            result["category_metrics"]["diagnosis"]["true_positives"],
            1,
        )
        self.assertEqual(
            result["status_accuracy"]["correct"],
            1,
        )
        self.assertEqual(
            result["status_accuracy"]["matched_items_with_gold_status"],
            2,
        )
        self.assertEqual(
            result["status_accuracy"]["accuracy"],
            0.5,
        )

    def test_missed_review_decision_counts_as_false_negative(self):
        gold, predictions = make_case_pair()

        gold[0]["expected_needs_review"] = True
        predictions[0]["needs_review"] = False

        result = evaluate_dataset(gold, predictions)
        review = result["review_detection"]

        self.assertEqual(review["true_positives"], 0)
        self.assertEqual(review["false_negatives"], 1)
        self.assertEqual(review["recall"], 0.0)
        self.assertEqual(review["true_negatives"], 0)

    def test_rejects_mismatched_case_identifiers(self):
        gold, predictions = make_case_pair()
        predictions[0]["case_id"] = "SYN-EVAL-OTHER"

        with self.assertRaisesRegex(ValueError, "case_id sets"):
            evaluate_dataset(gold, predictions)

    def test_rejects_invalid_gold_evidence(self):
        gold, predictions = make_case_pair()
        gold[0]["gold_items"][0]["evidence_text"] = "not in the span"

        with self.assertRaisesRegex(ValueError, "invalid evidence span"):
            evaluate_dataset(gold, predictions)
    def test_status_accuracy_excludes_items_needing_review(self):
        gold, predictions = make_case_pair()

        predictions[0]["items"][0]["decision"] = "needs_review"

        result = evaluate_dataset(gold, predictions)

        self.assertEqual(
            result["status_accuracy"]["matched_items_with_gold_status"],
            1,
        )
        self.assertEqual(
            result["status_accuracy"]["correct"],
            1,
        )
        self.assertEqual(
            result["status_accuracy"]["accuracy"],
            1.0,
        )

    def test_operational_metrics_do_not_impute_missing_measurements(self):
        result = evaluate_operational_metrics(
            [
                {
                    "case_id": "A",
                    "status": "completed",
                    "latency_ms": 1000,
                    "model_calls": 2,
                    "retry_count": 1,
                },
                {"case_id": "B", "status": "needs_review"},
            ]
        )

        self.assertEqual(result["latency_ms"]["median"], 1000.0)
        self.assertEqual(result["model_calls"]["total"], 2)
        self.assertEqual(result["retries"]["total"], 1)
        self.assertEqual(result["latency_ms"]["p95"], 1000.0)
        self.assertEqual(result["failures"]["rate"], 0.0)

    def test_compare_systems_is_descriptive(self):
        result = compare_system_metrics(
            [{"case_id": "A", "latency_ms": 1000}],
            [{"case_id": "A", "latency_ms": 2000}],
        )

        self.assertEqual(result["comparison_status"], "measured")
        self.assertEqual(
            result["agent"]["latency_ms"]["median"],
            1000.0,
        )
        self.assertIn("clinical superiority", result["limitation"])

    def test_poor_cases_require_qualified_gold_and_observed_errors(self):
        result = select_poor_performing_cases(
            [
                {"case_id": "unqualified", "gold_qualified": False, "error_count": 99},
                {"case_id": "good", "gold_qualified": True, "error_count": 0},
                {"case_id": "poor", "gold_qualified": True, "error_count": 2},
            ]
        )

        self.assertEqual([case["case_id"] for case in result], ["poor"])

    def test_qualified_evaluation_rejects_unqualified_gold(self):
        gold, predictions = make_case_pair()
        with self.assertRaisesRegex(ValueError, "not explicitly qualified"):
            evaluate_qualified_dataset(gold, predictions)

    def test_sow_report_leaves_missing_inputs_unmeasured(self):
        gold, predictions = make_case_pair()
        gold[0]["gold_qualified"] = True

        result = build_sow_evaluation_report(gold, predictions)

        self.assertIsNone(result["baseline"])
        self.assertEqual(result["baseline_status"], "Not yet measured")
        self.assertIsNone(result["operational"])
        self.assertEqual(result["three_poor_performing_cases"], [])

    def test_full_sow_report_blocks_clinical_metrics_without_qualified_queue(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            queue_path = Path(temporary_directory) / "queue.jsonl"
            queue_path.write_text(
                json.dumps(
                    {
                        "record_id": "QUEUE-001",
                        "source_dataset": (
                            "kaggle:tboyle10/medicaltranscriptions"
                        ),
                        "source_url": (
                            "https://www.kaggle.com/datasets/"
                            "tboyle10/medicaltranscriptions/data"
                        ),
                        "source_row_number": 1,
                        "note_text": "Synthetic note.",
                        "annotation_complete": False,
                        "adjudication_status": "not_reviewed",
                        "gold_annotations": {
                            "diagnoses": None,
                            "procedures": None,
                            "medications": None,
                            "allergies": None,
                            "vital_signs": None,
                            "icd10_cm_codes": None,
                        },
                    }
                )
                + "\n",
                encoding="utf-8",
            )

            report = build_report(
                queue_path=queue_path,
                challenge_report={"overall_status": "Not yet measured"},
                smoke_report={"clinical_performance_claimed": False},
            )

        self.assertEqual(report["clinical_metrics"]["status"], "NOT EVALUATED")
        self.assertEqual(report["queue_progress"]["qualified_notes"], 0)
        self.assertEqual(report["operations"]["agent"]["status"], "NOT EVALUATED")
        self.assertEqual(report["poor_cases"]["status"], "NOT EVALUATED")

    def test_full_sow_report_retains_recorded_operational_metrics(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            queue_path = Path(temporary_directory) / "queue.jsonl"
            queue_path.write_text("", encoding="utf-8")
            report = build_report(
                queue_path=queue_path,
                challenge_report={"overall_status": "Not yet measured"},
                smoke_report={"clinical_performance_claimed": False},
                agent_operations=[
                    {
                        "latency_ms": 1200,
                        "model_calls": 2,
                        "retry_count": 1,
                        "status": "needs_review",
                    }
                ],
            )

        self.assertEqual(
            report["operations"]["agent"]["latency_ms"]["median"],
            1200.0,
        )
        self.assertEqual(report["operations"]["agent"]["model_calls"]["total"], 2)
        self.assertEqual(report["operations"]["agent"]["retries"]["total"], 1)