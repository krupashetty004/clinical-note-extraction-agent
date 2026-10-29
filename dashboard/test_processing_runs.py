"""Tests for clinical processing-run persistence."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from dashboard.models import (
    ClinicalNote,
    ClinicalProcessingRun,
    Encounter,
    Patient,
)


class ClinicalProcessingRunTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()

        cls.user = user_model.objects.create_user(
            username="synthetic_processing_doctor",
            password="Synthetic-Test-Password-842!",
        )

        cls.patient = Patient.objects.create(
            identifier="SYN-PROC-001",
            display_name="Synthetic Processing Patient",
            created_by=cls.user,
        )

        cls.encounter = Encounter.objects.create(
            patient=cls.patient,
            title="Synthetic processing encounter",
            encounter_date=timezone.now(),
            created_by=cls.user,
        )

        cls.note_v1 = ClinicalNote.objects.create(
            encounter=cls.encounter,
            version_number=1,
            original_text=(
                "Synthetic note version one: headache reported."
            ),
            created_by=cls.user,
        )

    def test_new_run_has_pending_status_and_zero_attempts(self):
        run = ClinicalProcessingRun.objects.create(
            clinical_note=self.note_v1,
            created_by=self.user,
        )

        saved_run = ClinicalProcessingRun.objects.get(pk=run.pk)

        self.assertEqual(
            saved_run.status,
            ClinicalProcessingRun.Status.PENDING,
        )
        self.assertEqual(saved_run.extraction_attempts, 0)
        self.assertEqual(saved_run.verification_attempts, 0)
        self.assertEqual(saved_run.failure_code, "")
        self.assertIsNone(saved_run.finished_at)

    def test_processing_results_persist_as_structured_json(self):
        extraction_result = {
            "items": [],
            "needs_review": False,
            "review_reasons": [],
        }
        coding_result = {"diagnoses": []}
        verification_result = {
            "item_checks": [],
            "potential_omissions": [],
            "needs_review": False,
            "review_reasons": [],
        }
        item_dispositions = [
            {
                "item_index": 0,
                "decision": "needs_review",
                "reasons": ["Synthetic review test."],
            }
        ]
        review_reasons = ["Synthetic review test."]

        run = ClinicalProcessingRun.objects.create(
            clinical_note=self.note_v1,
            created_by=self.user,
            status=ClinicalProcessingRun.Status.NEEDS_REVIEW,
            extraction_attempts=1,
            verification_attempts=2,
            extraction_result=extraction_result,
            coding_result=coding_result,
            verification_result=verification_result,
            item_dispositions=item_dispositions,
            review_reasons=review_reasons,
        )

        saved_run = ClinicalProcessingRun.objects.get(pk=run.pk)

        self.assertEqual(saved_run.extraction_result, extraction_result)
        self.assertEqual(saved_run.coding_result, coding_result)
        self.assertEqual(
            saved_run.verification_result,
            verification_result,
        )
        self.assertEqual(saved_run.item_dispositions, item_dispositions)
        self.assertEqual(saved_run.review_reasons, review_reasons)
        self.assertEqual(saved_run.extraction_attempts, 1)
        self.assertEqual(saved_run.verification_attempts, 2)

    def test_processing_runs_remain_attached_to_note_versions(self):
        note_v2 = ClinicalNote.objects.create(
            encounter=self.encounter,
            version_number=2,
            original_text=(
                "Synthetic note version two: headache resolved."
            ),
            created_by=self.user,
        )

        run_v1 = ClinicalProcessingRun.objects.create(
            clinical_note=self.note_v1,
            created_by=self.user,
            status=ClinicalProcessingRun.Status.COMPLETED,
        )
        run_v2 = ClinicalProcessingRun.objects.create(
            clinical_note=note_v2,
            created_by=self.user,
            status=ClinicalProcessingRun.Status.NEEDS_REVIEW,
        )

        self.assertEqual(
            run_v1.clinical_note.version_number,
            1,
        )
        self.assertEqual(
            run_v2.clinical_note.version_number,
            2,
        )
        self.assertEqual(
            self.encounter.notes.count(),
            2,
        )
        self.assertNotEqual(
            run_v1.clinical_note.original_text,
            run_v2.clinical_note.original_text,
        )