"""Network-free tests for smoke-test failure-phase classification."""

from django.test import SimpleTestCase

from dashboard.extraction.service import ExtractionOutputError
from dashboard.extraction.verification import VerificationOutputError
from evaluation.run_groq_positive_smoke import safe_failure_phase


class GroqFailurePhaseTests(SimpleTestCase):
    def test_extraction_schema_failure_maps_to_schema_phase(self):
        error = ExtractionOutputError(
            "schema_validation_failed",
            "Synthetic test error.",
        )
        self.assertEqual(
            safe_failure_phase(error, "extraction_request"),
            "extraction_schema_validation",
        )

    def test_extraction_evidence_failure_maps_to_evidence_phase(self):
        error = ExtractionOutputError(
            "evidence_validation_failed",
            "Synthetic test error.",
        )
        self.assertEqual(
            safe_failure_phase(error, "extraction_schema_validation"),
            "evidence_offset_validation",
        )

    def test_verification_failure_maps_to_verification_phase(self):
        error = VerificationOutputError(
            "verification_schema_failed",
            "Synthetic test error.",
        )
        self.assertEqual(
            safe_failure_phase(error, "verification_request"),
            "verification_validation",
        )

    def test_provider_error_preserves_current_phase(self):
        error = RuntimeError("Synthetic internal test error.")
        self.assertEqual(
            safe_failure_phase(error, "extraction_request"),
            "extraction_request",
        )

    def test_unknown_extraction_code_preserves_current_phase(self):
        error = ExtractionOutputError(
            "PRIVATE_UNKNOWN_CODE",
            "Synthetic internal test error.",
        )
        self.assertEqual(
            safe_failure_phase(error, "extraction_request"),
            "extraction_request",
        )
