"""Network-free tests for verification evidence failure diagnostics."""

from django.test import SimpleTestCase

from dashboard.extraction.schema import ExtractionResult
from dashboard.extraction.verification import (
    VerificationOutputError,
    validate_verification_output,
)
from evaluation.run_groq_positive_smoke import safe_error_code, safe_error_detail


class VerificationEvidenceDiagnosticsTests(SimpleTestCase):
    NOTE = "Assessment: hypertension."

    def setUp(self):
        start = self.NOTE.index("hypertension")
        self.extraction = ExtractionResult.model_validate(
            {
                "items": [
                    {
                        "category": "diagnosis",
                        "entity": "hypertension",
                        "status": "active",
                        "evidence_text": "hypertension",
                        "start_offset": start,
                        "end_offset": start + len("hypertension"),
                        "attributes": {},
                    }
                ],
                "needs_review": False,
                "review_reasons": [],
            }
        )

    def verify_with_evidence(self, evidence):
        payload = {
            "item_checks": [
                {
                    "item_index": 0,
                    "outcome": "supported",
                    "status_check": "correct",
                    "reason": "Synthetic test evidence check.",
                    "evidence": evidence,
                }
            ],
            "potential_omissions": [],
            "needs_review": False,
            "review_reasons": [],
        }

        return validate_verification_output(
            payload,
            self.extraction,
            self.NOTE,
        )

    def assert_failure_detail(self, expected_detail, evidence):
        with self.assertRaises(VerificationOutputError) as raised:
            self.verify_with_evidence(evidence)

        self.assertEqual(
            raised.exception.code,
            "verification_evidence_failed",
        )
        self.assertEqual(
            safe_error_code(raised.exception),
            "verification_evidence_failed",
        )
        self.assertEqual(
            safe_error_detail(raised.exception),
            expected_detail,
        )

    def test_supported_result_requires_evidence(self):
        self.assert_failure_detail("required_evidence_missing", [])

    def test_evidence_offset_must_not_exceed_note_length(self):
        self.assert_failure_detail(
            "evidence_offset_out_of_bounds",
            [
                {
                    "evidence_text": "hypertension",
                    "start_offset": 0,
                    "end_offset": 999,
                }
            ],
        )

    def test_evidence_text_must_match_source_offsets(self):
        self.assert_failure_detail(
            "evidence_text_offset_mismatch",
            [
                {
                    "evidence_text": "hypertension",
                    "start_offset": 0,
                    "end_offset": 12,
                }
            ],
        )