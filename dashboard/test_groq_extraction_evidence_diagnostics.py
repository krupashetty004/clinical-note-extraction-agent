"""Network-free tests for safe extraction evidence diagnostics."""

from django.test import SimpleTestCase

from dashboard.extraction.service import (
    ExtractionOutputError,
    validate_extraction_output,
)
from evaluation.run_groq_positive_smoke import (
    safe_error_code,
    safe_error_detail,
)


class GroqExtractionEvidenceDiagnosticsTests(SimpleTestCase):
    NOTE = "Assessment: hypertension."

    def make_payload(self, *, evidence_text, start_offset, end_offset):
        return {
            "items": [
                {
                    "category": "diagnosis",
                    "entity": "hypertension",
                    "status": "active",
                    "evidence_text": evidence_text,
                    "start_offset": start_offset,
                    "end_offset": end_offset,
                    "attributes": {},
                }
            ],
            "needs_review": False,
            "review_reasons": [],
        }

    def assert_evidence_error(self, payload, expected_detail):
        with self.assertRaises(ExtractionOutputError) as raised:
            validate_extraction_output(payload, self.NOTE)

        error = raised.exception
        self.assertEqual(error.code, "evidence_validation_failed")
        self.assertEqual(
            safe_error_code(error),
            "evidence_validation_failed",
        )
        self.assertEqual(safe_error_detail(error), expected_detail)

    def test_out_of_bounds_offset_has_specific_detail(self):
        start = self.NOTE.index("hypertension")
        payload = self.make_payload(
            evidence_text="hypertension",
            start_offset=start,
            end_offset=len(self.NOTE) + 10,
        )

        self.assert_evidence_error(
            payload,
            "evidence_offset_out_of_bounds",
        )

    def test_evidence_text_offset_mismatch_has_specific_detail(self):
        payload = self.make_payload(
            evidence_text="hypertension",
            start_offset=0,
            end_offset=len("hypertension"),
        )

        self.assert_evidence_error(
            payload,
            "evidence_text_offset_mismatch",
        )