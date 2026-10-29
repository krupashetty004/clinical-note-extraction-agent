"""Access-control tests for processing-run detail pages."""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from dashboard.extraction.local_provider import (
    LocalClinicalExtractionProvider,
    LocalClinicalVerificationProvider,
)
from dashboard.extraction.processing_service import process_clinical_note
from dashboard.models import (
    ClinicalNote,
    ClinicalProcessingRun,
    Encounter,
    Patient,
    PatientAccess,
)


class ProcessingRunViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        doctor_group = Group.objects.get(name="Doctor")

        cls.doctor_a = user_model.objects.create_user(
            username="run_view_doctor_a",
            password="Synthetic-Run-Test-Password-481!",
        )
        cls.doctor_a.groups.add(doctor_group)

        cls.doctor_b = user_model.objects.create_user(
            username="run_view_doctor_b",
            password="Synthetic-Run-Test-Password-582!",
        )
        cls.doctor_b.groups.add(doctor_group)

        cls.patient = Patient.objects.create(
            identifier="SYN-RUN-VIEW-001",
            display_name="Synthetic Run View Patient",
            created_by=cls.doctor_a,
        )

        PatientAccess.objects.create(
            patient=cls.patient,
            doctor=cls.doctor_a,
        )

        cls.encounter = Encounter.objects.create(
            patient=cls.patient,
            title="Synthetic run-view encounter",
            encounter_date=timezone.now(),
            created_by=cls.doctor_a,
        )

        cls.note = ClinicalNote.objects.create(
            encounter=cls.encounter,
            version_number=1,
            original_text="Synthetic test note; no real clinical data.",
            created_by=cls.doctor_a,
        )

        cls.processing_run = ClinicalProcessingRun.objects.create(
            clinical_note=cls.note,
            created_by=cls.doctor_a,
            status=ClinicalProcessingRun.Status.NEEDS_REVIEW,
            extraction_result={"items": []},
            review_reasons=["Synthetic review test."],
        )

    def test_completed_local_run_does_not_show_unavailable_review_form(self):
        note = ClinicalNote.objects.create(
            encounter=self.encounter,
            version_number=2,
            original_text="No findings are documented in this synthetic note.",
            created_by=self.doctor_a,
        )

        run = process_clinical_note(
            note,
            self.doctor_a,
            extraction_provider=LocalClinicalExtractionProvider(),
            verification_provider=LocalClinicalVerificationProvider(),
            execution_mode=ClinicalProcessingRun.ExecutionMode.AI_AGENT,
        )

        self.assertEqual(run.status, ClinicalProcessingRun.Status.COMPLETED)
        self.assertEqual(
            run.review_decision,
            ClinicalProcessingRun.ReviewDecision.PENDING,
        )

        self.client.force_login(self.doctor_a)
        response = self.client.get(
            reverse(
                "dashboard:processing_run_detail",
                kwargs={"run_id": run.pk},
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Save review decision")

    def test_authorized_doctor_can_view_processing_run(self):
        self.client.force_login(self.doctor_a)

        response = self.client.get(
            reverse(
                "dashboard:processing_run_detail",
                kwargs={"run_id": self.processing_run.pk},
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Processing run #")
        self.assertContains(response, "Synthetic Run View Patient")
        self.assertContains(response, "Synthetic review test.")
        self.assertContains(response, "Save review decision")


    def test_other_doctor_cannot_view_processing_run(self):
        self.client.force_login(self.doctor_b)

        response = self.client.get(
            reverse(
                "dashboard:processing_run_detail",
                kwargs={"run_id": self.processing_run.pk},
            )
        )

        self.assertEqual(response.status_code, 404)

    def test_authorized_doctor_can_record_approval(self):
        self.client.force_login(self.doctor_a)

        response = self.client.post(
            reverse(
                "dashboard:review_processing_run",
                kwargs={"run_id": self.processing_run.pk},
            ),
            {"decision": "approved", "comment": "Synthetic review complete."},
        )

        self.assertRedirects(
            response,
            reverse(
                "dashboard:processing_run_detail",
                kwargs={"run_id": self.processing_run.pk},
            ),
        )
        self.processing_run.refresh_from_db()
        self.assertEqual(
            self.processing_run.review_decision,
            ClinicalProcessingRun.ReviewDecision.APPROVED,
        )
        self.assertEqual(
            self.processing_run.status,
            ClinicalProcessingRun.Status.COMPLETED,
        )
        self.assertEqual(self.processing_run.reviewed_by, self.doctor_a)
        self.assertEqual(
            self.processing_run.reviewer_comment,
            "Synthetic review complete.",
        )

    def test_authorized_doctor_can_record_rejection_and_complete_review_cycle(self):
        self.client.force_login(self.doctor_a)

        response = self.client.post(
            reverse(
                "dashboard:review_processing_run",
                kwargs={"run_id": self.processing_run.pk},
            ),
            {"decision": "rejected", "comment": "Synthetic review rejected."},
        )

        self.assertRedirects(
            response,
            reverse(
                "dashboard:processing_run_detail",
                kwargs={"run_id": self.processing_run.pk},
            ),
        )
        self.processing_run.refresh_from_db()
        self.assertEqual(
            self.processing_run.review_decision,
            ClinicalProcessingRun.ReviewDecision.REJECTED,
        )
        self.assertEqual(
            self.processing_run.status,
            ClinicalProcessingRun.Status.COMPLETED,
        )
        self.assertEqual(self.processing_run.reviewed_by, self.doctor_a)
        self.assertIsNotNone(self.processing_run.reviewed_at)
        self.assertEqual(
            self.processing_run.reviewer_comment,
            "Synthetic review rejected.",
        )
        self.assertFalse(
            ClinicalProcessingRun.objects.filter(
                pk=self.processing_run.pk,
                status=ClinicalProcessingRun.Status.NEEDS_REVIEW,
            ).exists()
        )

    def test_other_doctor_cannot_record_review(self):
        self.client.force_login(self.doctor_b)

        response = self.client.post(
            reverse(
                "dashboard:review_processing_run",
                kwargs={"run_id": self.processing_run.pk},
            ),
            {"decision": "approved"},
        )

        self.assertEqual(response.status_code, 404)
        self.processing_run.refresh_from_db()
        self.assertEqual(
            self.processing_run.review_decision,
            ClinicalProcessingRun.ReviewDecision.PENDING,
        )

    def test_finalized_review_cannot_be_overwritten(self):
        self.processing_run.status = ClinicalProcessingRun.Status.COMPLETED
        self.processing_run.review_decision = (
            ClinicalProcessingRun.ReviewDecision.APPROVED
        )
        self.processing_run.reviewed_by = self.doctor_a
        self.processing_run.reviewed_at = timezone.now()
        self.processing_run.save(
            update_fields=[
                "status",
                "review_decision",
                "reviewed_by",
                "reviewed_at",
            ]
        )

        self.client.force_login(self.doctor_a)
        response = self.client.post(
            reverse(
                "dashboard:review_processing_run",
                kwargs={"run_id": self.processing_run.pk},
            ),
            {"decision": "rejected", "comment": "Overwrite attempt."},
        )

        self.assertEqual(response.status_code, 404)
        self.processing_run.refresh_from_db()
        self.assertEqual(
            self.processing_run.review_decision,
            ClinicalProcessingRun.ReviewDecision.APPROVED,
        )
        self.assertEqual(
            self.processing_run.reviewer_comment,
            "",
        )

    def test_failed_run_cannot_be_marked_reviewed(self):
        self.processing_run.status = ClinicalProcessingRun.Status.FAILED
        self.processing_run.save(update_fields=["status"])

        self.client.force_login(self.doctor_a)
        response = self.client.post(
            reverse(
                "dashboard:review_processing_run",
                kwargs={"run_id": self.processing_run.pk},
            ),
            {"decision": "approved"},
        )

        self.assertEqual(response.status_code, 404)
        self.processing_run.refresh_from_db()
        self.assertEqual(
            self.processing_run.review_decision,
            ClinicalProcessingRun.ReviewDecision.PENDING,
        )
