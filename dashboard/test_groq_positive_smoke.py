"""Network-free tests for positive-case smoke-test assessment."""
from types import SimpleNamespace

from django.test import SimpleTestCase

from evaluation.run_groq_positive_smoke import assess_expected_findings


class PositiveSmokeAssessmentTests(SimpleTestCase):
    def setUp(self):
        self.items = [
            SimpleNamespace(
                category="diagnosis",
                entity="hypertension",
                status="active",
                evidence_text="hypertension",
            ),
            SimpleNamespace(
                category="medication",
                entity="lisinopril",
                status="current",
                evidence_text="lisinopril",
            ),
        ]

        self.checks = [
            SimpleNamespace(
                item_index=0,
                outcome="supported",
                status_check="correct",
            ),
            SimpleNamespace(
                item_index=1,
                outcome="supported",
                status_check="correct",
            ),
        ]

    def assess(self, *, items=None, checks=None, needs_review=False):
        extraction = SimpleNamespace(
            items=self.items if items is None else items,
        )
        verification = SimpleNamespace(
            item_checks=self.checks if checks is None else checks,
            needs_review=needs_review,
        )
        return assess_expected_findings(extraction, verification)

    def test_expected_findings_and_checks_pass(self):
        result = self.assess()

        self.assertTrue(result["ok"])
        self.assertTrue(result["expected_findings_found"])
        self.assertTrue(result["expected_findings_verified"])

    def test_missing_expected_finding_fails(self):
        result = self.assess(items=self.items[:1], checks=self.checks[:1])

        self.assertFalse(result["ok"])
        self.assertFalse(result["expected_findings_found"])

    def test_unsupported_verification_fails(self):
        checks = [
            self.checks[0],
            SimpleNamespace(
                item_index=1,
                outcome="unsupported",
                status_check="correct",
            ),
        ]
        result = self.assess(checks=checks)

        self.assertFalse(result["ok"])
        self.assertFalse(result["expected_findings_verified"])

    def test_review_requirement_prevents_pass(self):
        result = self.assess(needs_review=True)

        self.assertFalse(result["ok"])
        self.assertTrue(result["verification_requires_review"])