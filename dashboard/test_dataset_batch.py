"""Tests for local MTSamples batch processing; all notes are synthetic fixtures."""
from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase

from dashboard.extraction.dataset_batch import (
    DatasetBatchError,
    run_dataset_batch,
)


class FakeItem:
    category = "diagnosis"
    entity = "hypertension"
    start_offset = 12
    end_offset = 24
    evidence_text = "hypertension"

    def model_dump(self, mode="json"):
        return {
            "category": self.category,
            "entity": self.entity,
            "status": "active",
            "evidence_text": self.evidence_text,
            "start_offset": self.start_offset,
            "end_offset": self.end_offset,
            "attributes": {},
        }


def fake_workflow_result(status="completed"):
    return SimpleNamespace(
        status=status,
        extraction_attempts=1,
        verification_attempts=1,
        extraction=SimpleNamespace(items=[FakeItem()]),
        coding=SimpleNamespace(diagnoses=[]),
        item_dispositions=[SimpleNamespace(item_index=0, decision="accepted")],
        review_reasons=(),
        failure_code=None,
    )


class DatasetBatchTests(SimpleTestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.local_data_root = self.root / ".dataset_working"
        self.input_path = self.root / "annotation_template_100.jsonl"
        self.output_dir = self.local_data_root / "runs" / "test-batch"
        note_one = "Assessment: hypertension."
        note_two = "Assessment: hypertension; follow-up requested."
        rows = [
            self._queue_record("case-001", note_one, 1, "Cardiology"),
            self._queue_record("case-002", note_two, 2, "Neurology"),
        ]
        self.input_path.write_text(
            "".join(json.dumps(row) + "\n" for row in rows),
            encoding="utf-8",
        )
        self.local_root_patch = patch(
            "dashboard.extraction.dataset_batch.LOCAL_DATA_ROOT",
            self.local_data_root,
        )
        self.local_root_patch.start()
        self.addCleanup(self.local_root_patch.stop)

    @staticmethod
    def _queue_record(record_id, note, row_number, specialty):
        return {
            "record_id": record_id,
            "source_dataset": "synthetic:mirai-tests",
            "source_url": "local://synthetic",
            "source_row_number": row_number,
            "specialty": specialty,
            "note_text": note,
            "annotation_complete": False,
            "annotation_status": "not_annotated",
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

    @patch("dashboard.extraction.dataset_batch.run_agent_workflow")
    def test_processes_queue_locally_and_writes_traceable_outputs(self, mock_run):
        mock_run.side_effect = [
            fake_workflow_result("completed"),
            fake_workflow_result("needs_review"),
        ]

        result = run_dataset_batch(
            input_path=self.input_path,
            output_dir=self.output_dir,
        )

        predictions = [
            json.loads(line)
            for line in (self.output_dir / "predictions.jsonl").read_text(
                encoding="utf-8"
            ).splitlines()
        ]
        operations = [
            json.loads(line)
            for line in (self.output_dir / "operations.jsonl").read_text(
                encoding="utf-8"
            ).splitlines()
        ]
        report = json.loads(
            (self.output_dir / "report.json").read_text(encoding="utf-8")
        )

        self.assertEqual(result["records_selected"], 2)
        self.assertEqual(result["records_processed"], 2)
        self.assertEqual(result["new_records_processed"], 2)
        self.assertEqual([row["case_id"] for row in predictions], ["case-001", "case-002"])
        self.assertEqual(predictions[0]["items"][0]["decision"], "accepted")
        self.assertEqual(predictions[0]["source_row_number"], 1)
        self.assertEqual(predictions[0]["specialty"], "Cardiology")
        self.assertTrue(predictions[0]["note_sha256"])
        self.assertEqual(operations[0]["provider"], "local")
        self.assertEqual(operations[0]["provider_invocations"], 2)
        self.assertEqual(report["external_provider_calls"], 0)
        self.assertEqual(report["patient_records_created"], 0)
        self.assertEqual(report["clinical_processing_runs_created"], 0)
        self.assertEqual(result["evaluation_status"], "NOT EVALUATED")
        self.assertFalse(report["evaluation"]["clinical_performance_claimed"])
        self.assertEqual(mock_run.call_count, 2)
        for call in mock_run.call_args_list:
            self.assertEqual(
                call.kwargs["extraction_provider"].__class__.__name__,
                "LocalClinicalExtractionProvider",
            )
            self.assertEqual(
                call.kwargs["verification_provider"].__class__.__name__,
                "LocalClinicalVerificationProvider",
            )

        # Aggregate files never contain entire source notes.
        serialized = json.dumps(report) + json.dumps(operations)
        self.assertNotIn("Assessment: hypertension", serialized)

    @patch("dashboard.extraction.dataset_batch.run_agent_workflow")
    def test_resume_skips_previously_completed_case_ids(self, mock_run):
        mock_run.side_effect = [
            fake_workflow_result("completed"),
            fake_workflow_result("completed"),
        ]
        first = run_dataset_batch(
            input_path=self.input_path,
            output_dir=self.output_dir,
            limit=1,
        )
        self.assertEqual(first["new_records_processed"], 1)
        mock_run.reset_mock()
        mock_run.return_value = fake_workflow_result("completed")

        second = run_dataset_batch(
            input_path=self.input_path,
            output_dir=self.output_dir,
            limit=2,
            resume=True,
        )

        rows = (self.output_dir / "predictions.jsonl").read_text(
            encoding="utf-8"
        ).splitlines()
        self.assertEqual(second["records_processed"], 2)
        self.assertEqual(second["new_records_processed"], 1)
        self.assertEqual(len(rows), 2)
        self.assertEqual(mock_run.call_count, 1)

    def test_refuses_existing_outputs_without_resume_or_overwrite(self):
        self.output_dir.mkdir(parents=True)
        (self.output_dir / "predictions.jsonl").write_text("", encoding="utf-8")
        with self.assertRaisesRegex(DatasetBatchError, "outputs already exist"):
            run_dataset_batch(
                input_path=self.input_path,
                output_dir=self.output_dir,
            )

    def test_refuses_output_outside_git_ignored_workspace(self):
        outside = self.root / "public-output"
        with self.assertRaisesRegex(DatasetBatchError, "inside the Git-ignored"):
            run_dataset_batch(
                input_path=self.input_path,
                output_dir=outside,
            )

    @patch("dashboard.extraction.dataset_batch.run_agent_workflow")
    def test_rejects_invalid_dataset_before_provider_execution(self, mock_run):
        self.input_path.write_text('{"record_id": "missing-fields"}\n', encoding="utf-8")
        with self.assertRaisesRegex(DatasetBatchError, "Dataset validation failed"):
            run_dataset_batch(
                input_path=self.input_path,
                output_dir=self.output_dir,
            )
        mock_run.assert_not_called()

    def test_requires_existing_outputs_for_resume(self):
        with self.assertRaisesRegex(DatasetBatchError, "requires the atomic results.jsonl checkpoint"):
            run_dataset_batch(
                input_path=self.input_path,
                output_dir=self.output_dir,
                resume=True,
            )

    def test_rejects_invalid_limit(self):
        for invalid in (0, -1, True, "2"):
            with self.subTest(limit=invalid):
                with self.assertRaises(DatasetBatchError):
                    run_dataset_batch(
                        input_path=self.input_path,
                        output_dir=self.output_dir,
                        limit=invalid,
                    )
