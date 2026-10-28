"""Network-free tests for sanitized extraction schema diagnostics."""

from django.test import SimpleTestCase

from dashboard.extraction.service import (
    ExtractionOutputError,
    validate_extraction_output,
)
from evaluation.run_groq_positive_smoke import safe_schema_issues


class GroqSafeSchemaDiagnosticsTests(SimpleTestCase):
    def test_missing_schema_field_is_reported_without_input_values(self):
        note = "Synthetic note only."
        payload = {
            "items": [
                {
                    "category": "diagnosis",
                    "entity": "PRIVATE_SYNTHETIC_MARKER",
                }
            ],
            "needs_review": False,
            "review_reasons": [],
        }

        with self.assertRaises(ExtractionOutputError) as raised:
            validate_extraction_output(payload, note)

        self.assertEqual(
            raised.exception.code,
            "schema_validation_failed",
        )

        issues = safe_schema_issues(raised.exception)

        self.assertTrue(issues)
        self.assertTrue(
            any(
                issue["path"] == "items.0.evidence_text"
                and issue["type"] == "missing"
                for issue in issues
            )
        )
        self.assertNotIn("PRIVATE_SYNTHETIC_MARKER", repr(issues))
        self.assertLessEqual(len(issues), 8)

    def test_unknown_field_name_and_value_are_not_disclosed(self):
        payload = {
            "items": [],
            "needs_review": False,
            "review_reasons": [],
            "SECRET_UNTRUSTED_FIELD": "do not disclose",
        }

        with self.assertRaises(ExtractionOutputError) as raised:
            validate_extraction_output(
                payload,
                "Synthetic note only.",
            )

        issues = safe_schema_issues(raised.exception)

        self.assertTrue(
            any(
                issue["path"] == "<unknown_field>"
                and issue["type"] == "extra_forbidden"
                for issue in issues
            )
        )
        self.assertNotIn("SECRET_UNTRUSTED_FIELD", repr(issues))
        self.assertNotIn("do not disclose", repr(issues))