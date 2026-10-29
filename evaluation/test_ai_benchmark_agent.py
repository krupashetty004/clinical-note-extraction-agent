from __future__ import annotations

from django.test import SimpleTestCase

from dashboard.extraction.orchestrator import AgentWorkflowResult
from evaluation.run_ai_benchmark_agent import (
    validate_benchmark_cases,
    build_operation_record,
    build_prediction_case,
)


class AIBenchmarkAgentRunnerTests(SimpleTestCase):
    def make_case(self, **overrides):
        case = {
            "case_id": "synthetic-001",
            "note": "Synthetic note: hypertension.",
            "gold_items": [],
            "label_source": "ai_model",
            "clinical_performance_eligible": False,
            "source_dataset": "synthetic:mirai-stage6",
        }
        case.update(overrides)
        return case

    def test_accepts_synthetic_ai_benchmark_case(self):
        result = validate_benchmark_cases(
            [self.make_case()],
            approved_external_processing=False,
        )
        self.assertEqual(result[0]["case_id"], "synthetic-001")

    def test_blocks_non_synthetic_without_approval(self):
        with self.assertRaisesRegex(ValueError, "Non-synthetic notes are blocked"):
            validate_benchmark_cases(
                [self.make_case(source_dataset="mtsamples")],
                approved_external_processing=False,
            )

    def test_rejects_human_label_as_ai_benchmark(self):
        with self.assertRaisesRegex(ValueError, "not labelled as AI-generated"):
            validate_benchmark_cases(
                [self.make_case(label_source="human")],
                approved_external_processing=False,
            )

    def test_failed_workflow_requires_review(self):
        result = AgentWorkflowResult(
            status="failed",
            extraction_attempts=2,
            verification_attempts=0,
            extraction=None,
            coding=None,
            verification=None,
            item_dispositions=(),
            review_reasons=("safe summary",),
            failure_code="provider_failed",
        )
        prediction = build_prediction_case("synthetic-001", result)
        self.assertTrue(prediction["needs_review"])
        self.assertEqual(prediction["items"], [])

    def test_operation_record_contains_measured_fields(self):
        result = AgentWorkflowResult(
            status="completed",
            extraction_attempts=1,
            verification_attempts=1,
            extraction=None,
            coding=None,
            verification=None,
            item_dispositions=(),
            review_reasons=(),
            failure_code=None,
        )
        record = build_operation_record(
            "synthetic-001",
            result,
            latency_ms=123.4,
            model_id="unit-test-model",
        )
        self.assertEqual(record["model_calls"], 2)
        self.assertEqual(record["retry_count"], 0)
        self.assertEqual(record["latency_ms"], 123.4)
        self.assertNotIn("note", record)