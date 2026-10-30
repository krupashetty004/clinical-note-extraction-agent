"""Synthetic integration tests for processing-service persistence."""

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone

from dashboard.extraction.processing_service import process_clinical_note
from dashboard.models import (
    ClinicalNote,
    ClinicalProcessingRun,
    Encounter,
    KnowledgeDocument,
    Patient,
)


def empty_extraction():
    return {
        "items": [],
        "needs_review": False,
        "review_reasons": [],
    }


def empty_verification():
    return {
        "item_checks": [],
        "potential_omissions": [],
        "needs_review": False,
        "review_reasons": [],
    }


class SyntheticExtractionProvider:
    def __init__(self):
        self.reference_context = []

    def extract(self, input_text, *, reference_context=()):
        self.reference_context = list(reference_context)
        return empty_extraction()


class SyntheticVerificationProvider:
    def __init__(self):
        self.reference_context = []

    def verify(self, original_note, extraction, coding, *, reference_context=()):
        self.reference_context = list(reference_context)
        return empty_verification()


class FailingVerificationProvider:
    def verify(self, original_note, extraction, coding, *, reference_context=()):
        raise RuntimeError("Synthetic internal failure details")


class TimeoutVerificationProvider:
    def verify(self, original_note, extraction, coding, *, reference_context=()):
        raise TimeoutError("Synthetic timeout details")


class ProcessingServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        user_model = get_user_model()

        cls.doctor = user_model.objects.create_user(
            username="processing_service_doctor",
            password="Synthetic-Test-Password-943!",
        )

        cls.patient = Patient.objects.create(
            identifier="SYN-SERVICE-001",
            display_name="Synthetic Service Patient",
            created_by=cls.doctor,
        )

        cls.encounter = Encounter.objects.create(
            patient=cls.patient,
            title="Synthetic service encounter",
            encounter_date=timezone.now(),
            created_by=cls.doctor,
        )

        cls.note = ClinicalNote.objects.create(
            encounter=cls.encounter,
            version_number=1,
            original_text=(
                "Synthetic clinical note: no findings were supplied "
                "to the test extraction provider."
            ),
            created_by=cls.doctor,
        )

    def test_successful_run_persists_structured_results(self):
        original_text = self.note.original_text

        run = process_clinical_note(
            self.note,
            self.doctor,
            extraction_provider=SyntheticExtractionProvider(),
            verification_provider=SyntheticVerificationProvider(),
        )

        run.refresh_from_db()

        self.assertEqual(
            run.status,
            ClinicalProcessingRun.Status.COMPLETED,
        )
        self.assertEqual(run.extraction_attempts, 1)
        self.assertEqual(run.verification_attempts, 1)
        self.assertEqual(run.extraction_result["items"], [])
        self.assertEqual(run.coding_result["diagnoses"], [])
        self.assertEqual(run.verification_result["item_checks"], [])
        self.assertEqual(run.failure_code, "")
        self.assertIsNotNone(run.started_at)
        self.assertIsNotNone(run.finished_at)

        self.note.refresh_from_db()
        self.assertEqual(self.note.original_text, original_text)

    def test_verification_failure_persists_needs_review(self):
        run = process_clinical_note(
            self.note,
            self.doctor,
            extraction_provider=SyntheticExtractionProvider(),
            verification_provider=FailingVerificationProvider(),
            max_verification_attempts=2,
        )

        run.refresh_from_db()

        self.assertEqual(
            run.status,
            ClinicalProcessingRun.Status.NEEDS_REVIEW,
        )
        self.assertEqual(run.verification_attempts, 2)
        self.assertEqual(run.failure_code, "verification_failed")
        self.assertIsNone(run.verification_result)
        self.assertTrue(run.review_reasons)
        self.assertNotIn(
            "Synthetic internal failure details",
            str(run.review_reasons),
        )

    def test_verification_timeout_persists_safe_failure_code(self):
        run = process_clinical_note(
            self.note,
            self.doctor,
            extraction_provider=SyntheticExtractionProvider(),
            verification_provider=TimeoutVerificationProvider(),
            max_verification_attempts=2,
        )

        run.refresh_from_db()

        self.assertEqual(
            run.status,
            ClinicalProcessingRun.Status.NEEDS_REVIEW,
        )
        self.assertEqual(run.failure_code, "verification_timeout")
        self.assertEqual(run.verification_attempts, 2)
        self.assertNotIn(
            "Synthetic timeout details",
            str(run.review_reasons),
        )

    def test_processing_retrieves_approved_knowledge_and_persists_trace(self):
        note = ClinicalNote.objects.create(
            encounter=self.encounter,
            version_number=2,
            original_text="Assessment: hypertension. Current medication: lisinopril.",
            created_by=self.doctor,
        )
        document = KnowledgeDocument.objects.create(
            title="Hypertension treatment guideline",
            content=(
                "Hypertension treatment may include lisinopril and other "
                "appropriate antihypertensive medicines."
            ),
            ingestion_status="published",
            is_active=True,
            created_by=self.doctor,
        )
        extraction_provider = SyntheticExtractionProvider()
        verification_provider = SyntheticVerificationProvider()

        run = process_clinical_note(
            note,
            self.doctor,
            extraction_provider=extraction_provider,
            verification_provider=verification_provider,
        )
        run.refresh_from_db()

        self.assertEqual(run.knowledge_retrieval_status, "retrieved")
        self.assertEqual(len(run.knowledge_references), 1)
        self.assertEqual(
            run.knowledge_references[0]["document_id"],
            document.pk,
        )
        self.assertNotIn("text", run.knowledge_references[0])
        self.assertEqual(
            extraction_provider.reference_context[0]["document_id"],
            document.pk,
        )
        self.assertEqual(
            verification_provider.reference_context[0]["document_id"],
            document.pk,
        )

    def test_retrieval_failure_does_not_stop_note_processing(self):
        with __import__("unittest").mock.patch(
            "dashboard.extraction.processing_service.retrieve_knowledge_passages",
            side_effect=RuntimeError("synthetic internal retrieval error"),
        ):
            run = process_clinical_note(
                self.note,
                self.doctor,
                extraction_provider=SyntheticExtractionProvider(),
                verification_provider=SyntheticVerificationProvider(),
            )

        run.refresh_from_db()
        self.assertEqual(run.knowledge_retrieval_status, "unavailable")
        self.assertEqual(run.knowledge_references, [])
        self.assertEqual(run.status, ClinicalProcessingRun.Status.COMPLETED)

    def test_separate_invocations_create_separate_runs(self):
        providers = {
            "extraction_provider": SyntheticExtractionProvider(),
            "verification_provider": SyntheticVerificationProvider(),
        }

        first = process_clinical_note(
            self.note,
            self.doctor,
            **providers,
        )
        second = process_clinical_note(
            self.note,
            self.doctor,
            **providers,
        )

        self.assertNotEqual(first.pk, second.pk)
        self.assertEqual(
            ClinicalProcessingRun.objects.filter(
                clinical_note=self.note,
            ).count(),
            2,
        )