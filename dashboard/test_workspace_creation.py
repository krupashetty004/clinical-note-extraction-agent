"""Tests for doctor workspace patient, encounter, and multimodal note creation."""

from io import BytesIO
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from dashboard.models import (
    ClinicalNote,
    Encounter,
    Patient,
    PatientAccess,
)


class DoctorWorkspaceCreationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        cls.doctor = user_model.objects.create_user(
            username="test_dr_creator",
            password="Doctor-Creator-Password-101!",
        )
        cls.doctor.groups.add(Group.objects.get(name="Doctor"))

        cls.other_doctor = user_model.objects.create_user(
            username="test_dr_other",
            password="Doctor-Other-Password-202!",
        )
        cls.doctor.groups.add(Group.objects.get(name="Doctor"))

    def setUp(self):
        self.client.force_login(self.doctor)

    def test_doctor_can_create_patient(self):
        """Doctor registers a new patient from the front-end form."""
        response = self.client.post(
            reverse("dashboard:patient_create"),
            {
                "identifier": "PAT-NEW-101",
                "display_name": "Alice Springs (Synthetic)",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        patient = Patient.objects.get(identifier="PAT-NEW-101")
        self.assertEqual(patient.display_name, "Alice Springs (Synthetic)")
        self.assertEqual(patient.created_by, self.doctor)

        # Confirm access is automatically granted to the creator doctor
        self.assertTrue(
            PatientAccess.objects.filter(
                patient=patient,
                doctor=self.doctor,
            ).exists()
        )

    def test_doctor_can_create_encounter_for_patient(self):
        """Doctor creates an encounter for an accessible patient."""
        patient = Patient.objects.create(
            identifier="PAT-ENC-202",
            display_name="Bob Builder",
            created_by=self.doctor,
        )
        PatientAccess.objects.create(patient=patient, doctor=self.doctor)

        response = self.client.post(
            reverse("dashboard:encounter_create", kwargs={"patient_id": patient.pk}),
            {
                "title": "Initial Cardiology Assessment",
                "encounter_date": "2026-10-28T14:30",
                "status": "open",
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        encounter = Encounter.objects.get(patient=patient, title="Initial Cardiology Assessment")
        self.assertEqual(encounter.created_by, self.doctor)
        self.assertEqual(encounter.status, Encounter.Status.OPEN)

    def test_doctor_can_upload_multimodal_text_file_as_note(self):
        """Doctor uploads a text file note to an encounter."""
        patient = Patient.objects.create(
            identifier="PAT-NOTE-303",
            display_name="Charlie Chaplin",
            created_by=self.doctor,
        )
        PatientAccess.objects.create(patient=patient, doctor=self.doctor)
        encounter = Encounter.objects.create(
            patient=patient,
            title="Follow-up Visit",
            encounter_date=timezone.now(),
            created_by=self.doctor,
        )

        note_file = SimpleUploadedFile(
            "clinical_summary.txt",
            b"Patient has essential hypertension and takes lisinopril 10mg daily.",
            content_type="text/plain",
        )

        response = self.client.post(
            reverse("dashboard:clinical_note_create", kwargs={"encounter_id": encounter.pk}),
            {
                "source_file": note_file,
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        note = ClinicalNote.objects.get(encounter=encounter)
        self.assertIn("hypertension", note.original_text)
        self.assertIn("lisinopril", note.original_text)

    def test_image_upload_without_tesseract_rejects_untranscribed_content(self):
        """Unreadable images must not create notes from filename placeholders."""
        patient = Patient.objects.create(
            identifier="PAT-IMG-404",
            display_name="David Copperfield",
            created_by=self.doctor,
        )
        PatientAccess.objects.create(patient=patient, doctor=self.doctor)
        encounter = Encounter.objects.create(
            patient=patient,
            title="Dermatology Scan",
            encounter_date=timezone.now(),
            created_by=self.doctor,
        )

        image_file = SimpleUploadedFile(
            "clinical_scan.png",
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xdc\xccY\xe7\x00\x00\x00\x00IEND\xaeB`\x82",
            content_type="image/png",
        )

        response = self.client.post(
            reverse("dashboard:clinical_note_create", kwargs={"encounter_id": encounter.pk}),
            {
                "source_file": image_file,
            },
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No image transcription was produced")
        self.assertFalse(ClinicalNote.objects.filter(encounter=encounter).exists())

    def test_permitted_doctor_can_delete_patient_and_clean_knowledge_base(self):
        """Creator doctor can delete patient, cleaning up notes and related knowledge-base citations."""
        from dashboard.models import KnowledgeDocument
        patient = Patient.objects.create(
            identifier="PAT-DEL-505",
            display_name="Eve Adams",
            created_by=self.doctor,
        )
        PatientAccess.objects.create(patient=patient, doctor=self.doctor)
        encounter = Encounter.objects.create(
            patient=patient,
            title="Checkup",
            encounter_date=timezone.now(),
            created_by=self.doctor,
        )
        ClinicalNote.objects.create(
            encounter=encounter,
            original_text="Patient has mild asthma.",
            source=ClinicalNote.Source.MANUAL,
            created_by=self.doctor,
        )

        # Create a knowledge document referencing this patient
        kb_doc = KnowledgeDocument.objects.create(
            title="Guidance for PAT-DEL-505",
            summary="Clinical protocol for PAT-DEL-505",
            content="Follow standard protocol.",
            created_by=self.doctor,
        )

        response = self.client.post(
            reverse("dashboard:patient_delete", kwargs={"patient_id": patient.pk}),
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(Patient.objects.filter(identifier="PAT-DEL-505").exists())
        self.assertFalse(Encounter.objects.filter(patient_id=patient.pk).exists())
        self.assertFalse(KnowledgeDocument.objects.filter(title__icontains="PAT-DEL-505").exists())

    def test_unauthorized_doctor_cannot_delete_patient(self):
        """Another doctor cannot delete a patient they did not create."""
        patient = Patient.objects.create(
            identifier="PAT-SEC-606",
            display_name="Frank Miller",
            created_by=self.doctor,
        )
        PatientAccess.objects.create(patient=patient, doctor=self.doctor)
        PatientAccess.objects.create(patient=patient, doctor=self.other_doctor)

        self.client.force_login(self.other_doctor)
        response = self.client.post(
            reverse("dashboard:patient_delete", kwargs={"patient_id": patient.pk}),
        )
        self.assertEqual(response.status_code, 403)
        self.assertTrue(Patient.objects.filter(identifier="PAT-SEC-606").exists())
