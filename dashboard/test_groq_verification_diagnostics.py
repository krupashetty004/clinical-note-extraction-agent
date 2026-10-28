"""Network-free tests for safe verification failure diagnostics."""

from django.test import SimpleTestCase

from dashboard.extraction.schema import ExtractionResult
from dashboard.extraction.verification import (
    VerificationOutputError,
    validate_verification_output,
)
from evaluation.run_groq_positive_smoke import (
    safe_error_code,
    safe_schema_issues,
)


class GroqVerificationDiagnosticsTests(SimpleTestCase):
    def setUp(self):
        self.note = "Synthetic note only."
        self.extraction = ExtractionResult.model_validate(
            {
                "items": [],
                "needs_review": False,
                "review_reasons": [],
            }
        )

    def test_verification_schema_failure_reports_safe_code(self):
        # needs_review is required by VerificationResult.
        with self.assertRaises(VerificationOutputError) as raised:
            validate_verification_output(
                {},
                self.extraction,
                self.note,
            )

        error = raised.exception
        self.assertEqual(error.code, "verification_schema_failed")
        self.assertEqual(safe_error_code(error), "verification_schema_failed")

        issues = safe_schema_issues(error)
        self.assertTrue(
            any(
                item["path"] == "needs_review"
                and item["type"] == "missing"
                for item in issues
            )
        )
        self.assertLessEqual(len(issues), 8)

    def test_verification_coverage_code_is_preserved(self):
        error = VerificationOutputError(
            "verification_coverage_failed",
            "Synthetic internal test message.",
        )

        self.assertEqual(
            safe_error_code(error),
            "verification_coverage_failed",
        )

    def test_unknown_validation_code_is_sanitized(self):
        error = VerificationOutputError(
            "PRIVATE_UNKNOWN_CODE",
            "Synthetic internal test message.",
        )

        self.assertEqual(
            safe_error_code(error),
            "verification_validation_failed",
        )