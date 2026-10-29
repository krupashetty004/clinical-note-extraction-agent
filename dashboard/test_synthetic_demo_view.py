"""Tests for the gated, local synthetic processing demonstration."""

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from dashboard.models import (
    ClinicalNote,
    ClinicalProcessingRun,
    Encounter,
    Patient,
    PatientAccess,
)


class SyntheticDemoViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.doctor = user_model.objects.create_user(
            username="synthetic_demo_doctor",
            password="Synthetic-Demo-Test-Password-712!",
        )
        cls.doctor.groups.add(Group.objects.get(name="Doctor"))

        cls.other_doctor = user_model.objects.create_user(
            username="synthetic_demo_other_doctor",
            password="Synthetic-Demo-Test-Password-813!",
        )
        cls.other_doctor.groups.add(Group.objects.get(name="Doctor"))

        cls.patient = Patient.objects.create(
            identifier="SYN-DEMO-001",
            display_name="Synthetic Demo Patient",
            created_by=cls.doctor,
        )
        PatientAccess.objects.create(
            patient=cls.patient,
            doctor=cls.doctor,
        )
        cls.encounter = Encounter.objects.create(
            patient=cls.patient,
            title="Synthetic demo encounter",
            encounter_date=timezone.now(),
            created_by=cls.doctor,
        )
        cls.note = ClinicalNote.objects.create(
            encounter=cls.encounter,
            version_number=1,
            original_text=(
                "Synthetic test note only. No real clinical data is present."
            ),
            source=ClinicalNote.Source.MANUAL,
            created_by=cls.doctor,
        )

    def setUp(self):
        self.client.force_login(self.doctor)

    @override_settings(SYNTHETIC_DEMO_ENABLED=True)
    def test_post_creates_persisted_demo_run_and_requires_review(self):
        response = self.client.post(
            reverse(
                "dashboard:run_synthetic_processing_demo",
                kwargs={"note_id": self.note.pk},
            ),
            follow=True,
        )

        self.assertEqual(response.status_code, 200)
        run = ClinicalProcessingRun.objects.get(clinical_note=self.note)
        self.assertEqual(
            run.execution_mode,
            ClinicalProcessingRun.ExecutionMode.SYNTHETIC_DEMO,
        )
        self.assertEqual(run.status, ClinicalProcessingRun.Status.NEEDS_REVIEW)
        self.assertEqual(run.extraction_result["items"], [])
        self.assertTrue(run.extraction_result["needs_review"])
        self.assertTrue(run.verification_result["needs_review"])
        self.assertContains(response, "Synthetic demonstration only")
        self.assertContains(response, "No AI model was called")

    @override_settings(SYNTHETIC_DEMO_ENABLED=False)
    def test_demo_is_disabled_by_default_and_creates_no_run(self):
        response = self.client.post(
            reverse(
                "dashboard:run_synthetic_processing_demo",
                kwargs={"note_id": self.note.pk},
            )
        )

        self.assertEqual(response.status_code, 404)
        self.assertFalse(
            ClinicalProcessingRun.objects.filter(clinical_note=self.note).exists()
        )

    @override_settings(SYNTHETIC_DEMO_ENABLED=True)
    def test_demo_endpoint_rejects_get(self):
        response = self.client.get(
            reverse(
                "dashboard:run_synthetic_processing_demo",
                kwargs={"note_id": self.note.pk},
            )
        )
        self.assertEqual(response.status_code, 405)

    @override_settings(SYNTHETIC_DEMO_ENABLED=True)
    def test_doctor_without_patient_access_cannot_run_demo(self):
        self.client.force_login(self.other_doctor)
        response = self.client.post(
            reverse(
                "dashboard:run_synthetic_processing_demo",
                kwargs={"note_id": self.note.pk},
            )
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(
            ClinicalProcessingRun.objects.filter(clinical_note=self.note).exists()
        )
