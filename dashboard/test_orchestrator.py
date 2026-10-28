"""Synthetic tests for the clinical workflow orchestrator."""

from unittest.mock import patch

from django.test import SimpleTestCase

from dashboard.extraction.diagnosis_coding import DiagnosisCodingBatch
from dashboard.extraction.orchestrator import run_agent_workflow


def valid_empty_extraction():
    """Build a valid extraction response with no findings."""
    return {
        "items": [],
        "needs_review": False,
        "review_reasons": [],
    }


def valid_empty_verification():
    """Build a valid verification response with no findings."""
    return {
        "item_checks": [],
        "potential_omissions": [],
        "needs_review": False,
        "review_reasons": [],
    }


class SyntheticExtractionProvider:
    """Deterministic extraction provider for tests."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def extract(self, input_text):
        self.calls += 1
        response = self.responses.pop(0)

        if isinstance(response, Exception):
            raise response

        return response


class SyntheticVerificationProvider:
    """Deterministic verification provider for tests."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def verify(self, original_note, extraction, coding):
        self.calls += 1
        response = self.responses.pop(0)

        if isinstance(response, Exception):
            raise response

        return response


class ProviderCodedError(RuntimeError):
    code = "provider-error-with-sensitive-details"


class SyntheticRateLimitError(RuntimeError):
    code = "provider_rate_limited"


class AgentWorkflowTests(SimpleTestCase):
    def setUp(self):
        self.note = "Synthetic note for orchestration testing."

        self.coding_patcher = patch(
            "dashboard.extraction.orchestrator.code_diagnoses",
            return_value=DiagnosisCodingBatch(diagnoses=()),
        )
        self.mock_coding = self.coding_patcher.start()
        self.addCleanup(self.coding_patcher.stop)

    def test_empty_note_findings_complete_successfully(self):
        extraction_provider = SyntheticExtractionProvider(
            [valid_empty_extraction()]
        )
        verification_provider = SyntheticVerificationProvider(
            [valid_empty_verification()]
        )

        result = run_agent_workflow(
            extraction_provider,
            verification_provider,
            self.note,
        )

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.extraction_attempts, 1)
        self.assertEqual(result.verification_attempts, 1)
        self.assertEqual(result.item_dispositions, ())
        self.assertIsNone(result.failure_code)
        self.mock_coding.assert_called_once()

    def test_invalid_extraction_is_retried_within_limit(self):
        extraction_provider = SyntheticExtractionProvider(
            [
                {
                    "items": "invalid",
                    "needs_review": False,
                    "review_reasons": [],
                },
                valid_empty_extraction(),
            ]
        )
        verification_provider = SyntheticVerificationProvider(
            [valid_empty_verification()]
        )

        result = run_agent_workflow(
            extraction_provider,
            verification_provider,
            self.note,
            max_extraction_attempts=2,
        )

        self.assertEqual(result.status, "completed")
        self.assertEqual(extraction_provider.calls, 2)
        self.assertEqual(result.extraction_attempts, 2)

    def test_extraction_failure_stops_after_attempt_limit(self):
        extraction_provider = SyntheticExtractionProvider(
            [
                {
                    "items": "invalid",
                    "needs_review": False,
                    "review_reasons": [],
                },
                {
                    "items": "still invalid",
                    "needs_review": False,
                    "review_reasons": [],
                },
            ]
        )
        verification_provider = SyntheticVerificationProvider([])

        result = run_agent_workflow(
            extraction_provider,
            verification_provider,
            self.note,
            max_extraction_attempts=2,
        )

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.extraction_attempts, 2)
        self.assertEqual(
            result.failure_code,
            "schema_validation_failed",
        )
        self.assertEqual(verification_provider.calls, 0)
        self.mock_coding.assert_not_called()

    def test_verification_failure_requires_review(self):
        extraction_provider = SyntheticExtractionProvider(
            [valid_empty_extraction()]
        )
        verification_provider = SyntheticVerificationProvider(
            [
                RuntimeError("synthetic private provider error"),
                RuntimeError("synthetic private provider error"),
            ]
        )

        result = run_agent_workflow(
            extraction_provider,
            verification_provider,
            self.note,
            max_verification_attempts=2,
        )

        self.assertEqual(result.status, "needs_review")
        self.assertEqual(result.verification_attempts, 2)
        self.assertEqual(result.failure_code, "verification_failed")
        self.assertIsNone(result.verification)
        self.assertTrue(result.review_reasons)
        self.assertNotIn(
            "synthetic private provider error",
            str(result),
        )

    def test_unrecognized_provider_failure_code_is_sanitized(self):
        extraction_provider = SyntheticExtractionProvider(
            [valid_empty_extraction()]
        )
        verification_provider = SyntheticVerificationProvider(
            [ProviderCodedError(), ProviderCodedError()]
        )

        result = run_agent_workflow(
            extraction_provider,
            verification_provider,
            self.note,
            max_verification_attempts=2,
        )

        self.assertEqual(result.failure_code, "verification_failed")

    def test_safe_provider_failure_category_is_preserved(self):
        extraction_provider = SyntheticExtractionProvider(
            [valid_empty_extraction()]
        )
        verification_provider = SyntheticVerificationProvider(
            [
                SyntheticRateLimitError("synthetic private rate-limit details"),
                SyntheticRateLimitError("synthetic private rate-limit details"),
            ]
        )

        result = run_agent_workflow(
            extraction_provider,
            verification_provider,
            self.note,
            max_verification_attempts=2,
        )

        self.assertEqual(result.status, "needs_review")
        self.assertEqual(result.failure_code, "provider_rate_limited")
        self.assertNotIn("synthetic private rate-limit details", str(result))

    def test_malformed_verification_is_retried_and_keeps_safe_code(self):
        extraction_provider = SyntheticExtractionProvider(
            [valid_empty_extraction()]
        )
        verification_provider = SyntheticVerificationProvider(
            [{}, {}]
        )

        result = run_agent_workflow(
            extraction_provider,
            verification_provider,
            self.note,
            max_verification_attempts=2,
        )

        self.assertEqual(result.status, "needs_review")
        self.assertEqual(result.verification_attempts, 2)
        self.assertEqual(result.failure_code, "verification_schema_failed")
        self.assertIsNone(result.verification)

    def test_verification_timeout_is_bounded_and_safely_classified(self):
        extraction_provider = SyntheticExtractionProvider(
            [valid_empty_extraction()]
        )
        verification_provider = SyntheticVerificationProvider(
            [TimeoutError(), TimeoutError(), TimeoutError()]
        )

        result = run_agent_workflow(
            extraction_provider,
            verification_provider,
            self.note,
            max_verification_attempts=3,
        )

        self.assertEqual(result.status, "needs_review")
        self.assertEqual(result.verification_attempts, 3)
        self.assertEqual(result.failure_code, "verification_timeout")
        self.assertNotIn("TimeoutError", str(result))

    def test_unsupported_item_is_not_accepted(self):
        note = "Assessment: headache."
        evidence = "headache"
        start = note.index(evidence)

        extraction_payload = {
            "items": [
                {
                    "category": "diagnosis",
                    "entity": "headache",
                    "status": "active",
                    "evidence_text": evidence,
                    "start_offset": start,
                    "end_offset": start + len(evidence),
                    "attributes": {},
                }
            ],
            "needs_review": False,
            "review_reasons": [],
        }

        verification_payload = {
            "item_checks": [
                {
                    "item_index": 0,
                    "outcome": "unsupported",
                    "status_check": "correct",
                    "reason": (
                        "The mention is not supported as a diagnosis."
                    ),
                    "evidence": [
                        {
                            "evidence_text": evidence,
                            "start_offset": start,
                            "end_offset": start + len(evidence),
                        }
                    ],
                }
            ],
            "potential_omissions": [],
            "needs_review": True,
            "review_reasons": [
                "An unsupported diagnosis requires review."
            ],
        }

        result = run_agent_workflow(
            SyntheticExtractionProvider([extraction_payload]),
            SyntheticVerificationProvider([verification_payload]),
            note,
        )

        self.assertEqual(result.status, "needs_review")
        self.assertEqual(len(result.item_dispositions), 1)
        self.assertEqual(
            result.item_dispositions[0].decision,
            "rejected",
        )

    def _run_diagnosis_scenario(
        self,
        *,
        note,
        extraction_evidence,
        status,
        verification_outcome,
        status_check,
        verification_evidence=None,
    ):
        """Run one synthetic diagnosis through the workflow."""
        extraction_start = note.index(extraction_evidence)

        extraction_payload = {
            "items": [
                {
                    "category": "diagnosis",
                    "entity": "diabetes",
                    "status": status,
                    "evidence_text": extraction_evidence,
                    "start_offset": extraction_start,
                    "end_offset": (
                        extraction_start + len(extraction_evidence)
                    ),
                    "attributes": {},
                }
            ],
            "needs_review": False,
            "review_reasons": [],
        }

        cited_evidence = verification_evidence or extraction_evidence
        verification_start = note.index(cited_evidence)

        verification_payload = {
            "item_checks": [
                {
                    "item_index": 0,
                    "outcome": verification_outcome,
                    "status_check": status_check,
                    "reason": "Synthetic verification finding.",
                    "evidence": [
                        {
                            "evidence_text": cited_evidence,
                            "start_offset": verification_start,
                            "end_offset": (
                                verification_start + len(cited_evidence)
                            ),
                        }
                    ],
                }
            ],
            "potential_omissions": [],
            "needs_review": True,
            "review_reasons": [
                "Synthetic scenario requires human review."
            ],
        }

        return run_agent_workflow(
            SyntheticExtractionProvider([extraction_payload]),
            SyntheticVerificationProvider([verification_payload]),
            note,
        )

    def test_negated_diagnosis_is_not_accepted_as_active(self):
        note = "Assessment: no evidence of diabetes."

        result = self._run_diagnosis_scenario(
            note=note,
            extraction_evidence="diabetes",
            status="active",
            verification_outcome="contradicted",
            status_check="incorrect",
            verification_evidence="no evidence of diabetes",
        )

        self.assertEqual(result.status, "needs_review")
        self.assertEqual(len(result.item_dispositions), 1)
        self.assertEqual(
            result.item_dispositions[0].decision,
            "rejected",
        )

    def test_uncertain_diagnosis_requires_human_review(self):
        note = "Assessment: possible diabetes."

        result = self._run_diagnosis_scenario(
            note=note,
            extraction_evidence="possible diabetes",
            status="suspected",
            verification_outcome="uncertain",
            status_check="correct",
        )

        self.assertEqual(result.status, "needs_review")
        self.assertEqual(
            result.item_dispositions[0].decision,
            "needs_review",
        )

    def test_incorrect_diagnosis_status_requires_review(self):
        note = "History of diabetes; no current diagnosis."

        result = self._run_diagnosis_scenario(
            note=note,
            extraction_evidence="diabetes",
            status="active",
            verification_outcome="supported",
            status_check="incorrect",
            verification_evidence=note,
        )

        self.assertEqual(result.status, "needs_review")
        self.assertEqual(
            result.item_dispositions[0].decision,
            "needs_review",
        )
        self.assertIn(
            "Status verification was incorrect.",
            result.item_dispositions[0].reasons,
        )

    def test_unexpected_verification_validator_error_is_not_retried(self):
        extraction_provider = SyntheticExtractionProvider(
            [valid_empty_extraction()]
        )
        verification_provider = SyntheticVerificationProvider(
            [valid_empty_verification()]
        )

        with patch(
            "dashboard.extraction.orchestrator.validate_verification_output",
            side_effect=RuntimeError(
                "Synthetic validator programming error."
            ),
        ):
            with self.assertRaisesRegex(
                RuntimeError,
                "Synthetic validator programming error",
            ):
                run_agent_workflow(
                    extraction_provider,
                    verification_provider,
                    self.note,
                    max_verification_attempts=3,
                )

        self.assertEqual(verification_provider.calls, 1)

    def test_potentially_omitted_diagnosis_requires_review(self):
        note = "Assessment: diabetes and hypertension."
        evidence = "hypertension"
        start = note.index(evidence)

        extraction_payload = {
            "items": [],
            "needs_review": False,
            "review_reasons": [],
        }

        verification_payload = {
            "item_checks": [],
            "potential_omissions": [
                {
                    "category": "diagnosis",
                    "entity": "hypertension",
                    "evidence": {
                        "evidence_text": evidence,
                        "start_offset": start,
                        "end_offset": start + len(evidence),
                    },
                    "reason": (
                        "A possible diagnosis was omitted from extraction."
                    ),
                }
            ],
            "needs_review": True,
            "review_reasons": [
                "A possible omitted diagnosis requires review."
            ],
        }

        result = run_agent_workflow(
            SyntheticExtractionProvider([extraction_payload]),
            SyntheticVerificationProvider([verification_payload]),
            note,
        )

        self.assertEqual(result.status, "needs_review")
        self.assertIn(
            "Potential omission requires review: hypertension.",
            result.review_reasons,
        )