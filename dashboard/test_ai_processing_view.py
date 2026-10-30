"""Tests for the AI processing view (run_ai_processing) and export_processing_run view."""

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


class AIProcessingViewTests(TestCase):
    """Integration tests for the AI Agent processing endpoint."""

    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        doctor_group = Group.objects.get(name="Doctor")

        cls.doctor = user_model.objects.create_user(
            username="ai_proc_doctor",
            password="AI-Proc-Test-Password-891!",
        )
        cls.doctor.groups.add(doctor_group)

        cls.other_doctor = user_model.objects.create_user(
            username="ai_proc_other_doctor",
            password="AI-Proc-Test-Password-992!",
        )
        cls.other_doctor.groups.add(doctor_group)

        cls.patient = Patient.objects.create(
            identifier="AI-PROC-001",
            display_name="AI Processing Test Patient",
            created_by=cls.doctor,
        )
        PatientAccess.objects.create(
            patient=cls.patient,
            doctor=cls.doctor,
        )

        cls.encounter = Encounter.objects.create(
            patient=cls.patient,
            title="AI processing encounter",
            encounter_date=timezone.now(),
            created_by=cls.doctor,
        )

        cls.note = ClinicalNote.objects.create(
            encounter=cls.encounter,
            version_number=1,
            original_text=(
                "Patient presents with hypertension and type 2 diabetes mellitus. "
                "Current medications include metformin and lisinopril. "
                "History of atrial fibrillation."
            ),
            source=ClinicalNote.Source.MANUAL,
            created_by=cls.doctor,
        )

    def setUp(self):
        self.client.force_login(self.doctor)

    # ------------------------------------------------------------------
    # Core behaviour — local provider path (no Groq configured)
    # ------------------------------------------------------------------

    @override_settings(GROQ_PROVIDER_ENABLED=False)
    def test_post_creates_ai_agent_run_and_redirects(self):
        """POST to run_ai_processing creates a run with execution_mode=ai_agent."""
        response = self.client.post(
            reverse("dashboard:run_ai_processing", kwargs={"note_id": self.note.pk}),
            follow=True,
        )
        self.assertEqual(response.status_code, 200)
        run = ClinicalProcessingRun.objects.filter(clinical_note=self.note).latest("created_at")
        self.assertEqual(run.execution_mode, ClinicalProcessingRun.ExecutionMode.AI_AGENT)

    @override_settings(GROQ_PROVIDER_ENABLED=False)
    def test_run_status_is_needs_review(self):
        """Newly created AI agent run should require review."""
        self.client.post(
            reverse("dashboard:run_ai_processing", kwargs={"note_id": self.note.pk}),
        )
        run = ClinicalProcessingRun.objects.filter(clinical_note=self.note).latest("created_at")
        self.assertEqual(run.status, ClinicalProcessingRun.Status.NEEDS_REVIEW)

    @override_settings(GROQ_PROVIDER_ENABLED=False)
    def test_run_extraction_result_is_dict(self):
        """Extraction result must be a dict with an 'items' key."""
        self.client.post(
            reverse("dashboard:run_ai_processing", kwargs={"note_id": self.note.pk}),
        )
        run = ClinicalProcessingRun.objects.filter(clinical_note=self.note).latest("created_at")
        self.assertIsInstance(run.extraction_result, dict)
        self.assertIn("items", run.extraction_result)

    @override_settings(GROQ_PROVIDER_ENABLED=False)
    def test_run_extracts_known_diagnoses_from_note(self):
        """LocalClinicalExtractionProvider should find hypertension in the note."""
        self.client.post(
            reverse("dashboard:run_ai_processing", kwargs={"note_id": self.note.pk}),
        )
        run = ClinicalProcessingRun.objects.filter(clinical_note=self.note).latest("created_at")
        entities = [item["entity"].lower() for item in run.extraction_result["items"]]
        self.assertTrue(
            any("hypertension" in e for e in entities),
            f"Expected 'hypertension' in extracted entities; got: {entities}",
        )

    @override_settings(GROQ_PROVIDER_ENABLED=False)
    def test_run_extracts_known_medications_from_note(self):
        """LocalClinicalExtractionProvider should find metformin in the note."""
        self.client.post(
            reverse("dashboard:run_ai_processing", kwargs={"note_id": self.note.pk}),
        )
        run = ClinicalProcessingRun.objects.filter(clinical_note=self.note).latest("created_at")
        entities = [item["entity"].lower() for item in run.extraction_result["items"]]
        self.assertTrue(
            any("metformin" in e for e in entities),
            f"Expected 'metformin' in extracted entities; got: {entities}",
        )

    # ------------------------------------------------------------------
    # Access control
    # ------------------------------------------------------------------

    @override_settings(GROQ_PROVIDER_ENABLED=False)
    def test_get_is_rejected(self):
        """Only POST should be accepted; GET returns 405."""
        response = self.client.get(
            reverse("dashboard:run_ai_processing", kwargs={"note_id": self.note.pk}),
        )
        self.assertEqual(response.status_code, 405)
        self.assertFalse(ClinicalProcessingRun.objects.filter(clinical_note=self.note).exists())

    @override_settings(GROQ_PROVIDER_ENABLED=False)
    def test_doctor_without_access_gets_404(self):
        """A doctor without patient access must receive 404."""
        self.client.force_login(self.other_doctor)
        response = self.client.post(
            reverse("dashboard:run_ai_processing", kwargs={"note_id": self.note.pk}),
        )
        self.assertEqual(response.status_code, 404)
        self.assertFalse(ClinicalProcessingRun.objects.filter(clinical_note=self.note).exists())

    def test_unauthenticated_user_is_redirected(self):
        """Unauthenticated users must be redirected to login."""
        self.client.logout()
        response = self.client.post(
            reverse("dashboard:run_ai_processing", kwargs={"note_id": self.note.pk}),
        )
        self.assertIn(response.status_code, (302, 403))

    # ------------------------------------------------------------------
    # Redirect target
    # ------------------------------------------------------------------

    @override_settings(GROQ_PROVIDER_ENABLED=False)
    def test_successful_post_redirects_to_processing_run_detail(self):
        """After creating a run the response should redirect to the run detail page."""
        response = self.client.post(
            reverse("dashboard:run_ai_processing", kwargs={"note_id": self.note.pk}),
        )
        self.assertEqual(response.status_code, 302)
        run = ClinicalProcessingRun.objects.filter(clinical_note=self.note).latest("created_at")
        self.assertIn(
            reverse("dashboard:processing_run_detail", kwargs={"run_id": run.pk}),
            response["Location"],
        )


class ExportProcessingRunViewTests(TestCase):
    """Tests for the export_processing_run JSON attachment view."""

    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()
        doctor_group = Group.objects.get(name="Doctor")

        cls.doctor = user_model.objects.create_user(
            username="export_run_doctor",
            password="Export-Run-Test-Password-331!",
        )
        cls.doctor.groups.add(doctor_group)

        cls.other_doctor = user_model.objects.create_user(
            username="export_run_other_doctor",
            password="Export-Run-Test-Password-432!",
        )
        cls.other_doctor.groups.add(doctor_group)

        cls.patient = Patient.objects.create(
            identifier="EXPORT-RUN-001",
            display_name="Export Run Test Patient",
            created_by=cls.doctor,
        )
        PatientAccess.objects.create(
            patient=cls.patient,
            doctor=cls.doctor,
        )

        cls.encounter = Encounter.objects.create(
            patient=cls.patient,
            title="Export run encounter",
            encounter_date=timezone.now(),
            created_by=cls.doctor,
        )

        cls.note = ClinicalNote.objects.create(
            encounter=cls.encounter,
            version_number=1,
            original_text="Synthetic test note for export view test.",
            source=ClinicalNote.Source.MANUAL,
            created_by=cls.doctor,
        )

        cls.processing_run = ClinicalProcessingRun.objects.create(
            clinical_note=cls.note,
            created_by=cls.doctor,
            status=ClinicalProcessingRun.Status.COMPLETED,
            execution_mode=ClinicalProcessingRun.ExecutionMode.AI_AGENT,
            extraction_result={
                "items": [
                    {
                        "category": "diagnosis",
                        "entity": "hypertension",
                        "evidence_text": "hypertension",
                        "start_offset": 0,
                        "end_offset": 12,
                        "status": "active",
                    }
                ],
                "needs_review": False,
            },
            review_reasons=[],
        )

    def setUp(self):
        self.client.force_login(self.doctor)

    def test_export_returns_json_attachment(self):
        """Export endpoint returns 200 with application/json content type."""
        response = self.client.get(
            reverse("dashboard:export_processing_run", kwargs={"run_id": self.processing_run.pk}),
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("application/json", response["Content-Type"])

    def test_export_response_has_attachment_disposition(self):
        """Content-Disposition header must indicate a file attachment."""
        response = self.client.get(
            reverse("dashboard:export_processing_run", kwargs={"run_id": self.processing_run.pk}),
        )
        self.assertIn("attachment", response.get("Content-Disposition", ""))
        self.assertIn(".json", response.get("Content-Disposition", ""))

    def test_export_payload_contains_required_keys(self):
        """JSON payload must contain core keys per spec."""
        import json
        response = self.client.get(
            reverse("dashboard:export_processing_run", kwargs={"run_id": self.processing_run.pk}),
        )
        payload = json.loads(response.content)
        for key in ("export_type", "run_id", "execution_mode", "patient", "encounter",
                    "clinical_note", "extraction_result", "knowledge_retrieval", "review"):
            self.assertIn(key, payload, f"Missing key: {key}")

    def test_export_execution_mode_is_ai_agent(self):
        """Exported payload execution_mode should match the run's mode."""
        import json
        response = self.client.get(
            reverse("dashboard:export_processing_run", kwargs={"run_id": self.processing_run.pk}),
        )
        payload = json.loads(response.content)
        self.assertEqual(payload["execution_mode"], "ai_agent")

    def test_export_blocked_for_doctor_without_access(self):
        """A doctor without patient access must receive 404."""
        self.client.force_login(self.other_doctor)
        response = self.client.get(
            reverse("dashboard:export_processing_run", kwargs={"run_id": self.processing_run.pk}),
        )
        self.assertEqual(response.status_code, 404)

    def test_export_unauthenticated_is_redirected(self):
        """Unauthenticated users must not receive exported clinical data."""
        self.client.logout()
        response = self.client.get(
            reverse("dashboard:export_processing_run", kwargs={"run_id": self.processing_run.pk}),
        )
        self.assertIn(response.status_code, (302, 403))
