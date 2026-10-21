"""Tests for the independent verification output contract."""

from django.test import SimpleTestCase

from dashboard.extraction.schema import ExtractionResult
from dashboard.extraction.verification import (
    VerificationOutputError,
    validate_verification_output,
)


class VerificationContractTests(SimpleTestCase):
    NOTE = (
        "Assessment: diabetes. "
        "Medication: metformin. "
        "Allergy: penicillin allergy."
    )

    def make_extraction(self):
        items = []

        for category, entity, status, evidence in [
            ("diagnosis", "diabetes", "active", "diabetes"),
            ("medication", "metformin", "current", "metformin"),
        ]:
            start = self.NOTE.index(evidence)
            items.append(
                {
                    "category": category,
                    "entity": entity,
                    "status": status,
                    "evidence_text": evidence,
                    "start_offset": start,
                    "end_offset": start + len(evidence),
                    "attributes": {},
                }
            )

        return ExtractionResult.model_validate(
            {
                "items": items,
                "needs_review": False,
                "review_reasons": [],
            }
        )

    def make_payload(self):
        extraction = self.make_extraction()
        checks = []

        for index, item in enumerate(extraction.items):
            checks.append(
                {
                    "item_index": index,
                    "outcome": "supported",
                    "status_check": "correct",
                    "reason": "The cited text supports this mention.",
                    "evidence": [
                        {
                            "evidence_text": item.evidence_text,
                            "start_offset": item.start_offset,
                            "end_offset": item.end_offset,
                        }
                    ],
                }
            )

        payload = {
            "item_checks": checks,
            "potential_omissions": [],
            "needs_review": False,
            "review_reasons": [],
        }

        return extraction, payload

    def test_accepts_complete_verification(self):
        extraction, payload = self.make_payload()

        result = validate_verification_output(
            payload,
            extraction,
            self.NOTE,
        )

        self.assertEqual(len(result.item_checks), 2)
        self.assertEqual(
            [check.item_index for check in result.item_checks],
            [0, 1],
        )
        self.assertFalse(result.needs_review)

    def test_rejects_missing_item_check(self):
        extraction, payload = self.make_payload()
        payload["item_checks"].pop()

        with self.assertRaises(VerificationOutputError) as context:
            validate_verification_output(
                payload,
                extraction,
                self.NOTE,
            )

        self.assertEqual(
            context.exception.code,
            "verification_coverage_failed",
        )

    def test_rejects_duplicate_item_checks(self):
        extraction, payload = self.make_payload()
        payload["item_checks"].append(
            payload["item_checks"][0].copy()
        )

        with self.assertRaises(VerificationOutputError) as context:
            validate_verification_output(
                payload,
                extraction,
                self.NOTE,
            )

        self.assertEqual(
            context.exception.code,
            "verification_coverage_failed",
        )

    def test_rejects_evidence_that_does_not_match_note(self):
        extraction, payload = self.make_payload()
        payload["item_checks"][0]["evidence"][0][
            "evidence_text"
        ] = "unsupported phrase"

        with self.assertRaises(VerificationOutputError) as context:
            validate_verification_output(
                payload,
                extraction,
                self.NOTE,
            )

        self.assertEqual(
            context.exception.code,
            "verification_evidence_failed",
        )

    def test_rejects_evidence_outside_note(self):
        extraction, payload = self.make_payload()
        start = len(self.NOTE) + 1

        payload["item_checks"][0]["evidence"][0].update(
            {
                "start_offset": start,
                "end_offset": start + len("diabetes"),
            }
        )

        with self.assertRaises(VerificationOutputError) as context:
            validate_verification_output(
                payload,
                extraction,
                self.NOTE,
            )

        self.assertEqual(
            context.exception.code,
            "verification_evidence_failed",
        )

    def test_requires_status_check_for_diagnosis_and_medication(self):
        extraction, payload = self.make_payload()
        payload["item_checks"][0]["status_check"] = "not_applicable"

        with self.assertRaises(VerificationOutputError) as context:
            validate_verification_output(
                payload,
                extraction,
                self.NOTE,
            )

        self.assertEqual(
            context.exception.code,
            "verification_status_check_invalid",
        )

    def test_rejects_unresolved_item_without_review(self):
        extraction, payload = self.make_payload()
        payload["item_checks"][0]["outcome"] = "unsupported"

        with self.assertRaises(VerificationOutputError) as context:
            validate_verification_output(
                payload,
                extraction,
                self.NOTE,
            )

        self.assertEqual(
            context.exception.code,
            "verification_schema_failed",
        )

    def test_review_requires_a_reason(self):
        extraction, payload = self.make_payload()
        payload["needs_review"] = True

        with self.assertRaises(VerificationOutputError) as context:
            validate_verification_output(
                payload,
                extraction,
                self.NOTE,
            )

        self.assertEqual(
            context.exception.code,
            "verification_schema_failed",
        )

    def test_accepts_supported_potential_omission_for_review(self):
        extraction, payload = self.make_payload()
        evidence = "penicillin allergy"
        start = self.NOTE.index(evidence)

        payload["potential_omissions"] = [
            {
                "category": "allergy",
                "entity": "penicillin allergy",
                "evidence": {
                    "evidence_text": evidence,
                    "start_offset": start,
                    "end_offset": start + len(evidence),
                },
                "reason": (
                    "This mention may be missing from extraction."
                ),
            }
        ]
        payload["needs_review"] = True
        payload["review_reasons"] = [
            "A possible omitted allergy requires review."
        ]

        result = validate_verification_output(
            payload,
            extraction,
            self.NOTE,
        )

        self.assertTrue(result.needs_review)
        self.assertEqual(len(result.potential_omissions), 1)
        self.assertEqual(
            result.potential_omissions[0].entity,
            "penicillin allergy",
        )

    def test_rejects_omission_with_invalid_evidence(self):
        extraction, payload = self.make_payload()

        payload["potential_omissions"] = [
            {
                "category": "allergy",
                "entity": "penicillin allergy",
                "evidence": {
                    "evidence_text": "not in source note",
                    "start_offset": 0,
                    "end_offset": len("not in source note"),
                },
                "reason": (
                    "A possible omitted allergy requires review."
                ),
            }
        ]
        payload["needs_review"] = True
        payload["review_reasons"] = [
            "A possible omitted allergy requires review."
        ]

        with self.assertRaises(VerificationOutputError) as context:
            validate_verification_output(
                payload,
                extraction,
                self.NOTE,
            )

        self.assertEqual(
            context.exception.code,
            "verification_evidence_failed",
        )