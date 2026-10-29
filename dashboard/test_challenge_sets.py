"""Structural tests for the synthetic SOW challenge sets."""

from django.test import SimpleTestCase

from evaluation.challenge_sets import (
    ADVERSARIAL_CASES,
    CONTRADICTION_CASES,
    RARE_DIAGNOSIS_CASES,
    validate_challenge_sets,
)


class ChallengeSetStructureTests(SimpleTestCase):
    def test_all_sow_minimums_are_met(self):
        result = validate_challenge_sets()

        self.assertEqual(result["contradictions"], 20)
        self.assertEqual(result["rare_diagnoses"], 10)
        self.assertEqual(result["adversarial"], 10)
        self.assertEqual(result["total"], 40)

    def test_case_ids_are_unique(self):
        cases = (
            CONTRADICTION_CASES
            + RARE_DIAGNOSIS_CASES
            + ADVERSARIAL_CASES
        )
        case_ids = [case["case_id"] for case in cases]

        self.assertEqual(len(case_ids), len(set(case_ids)))

    def test_each_contradiction_has_original_and_modified_notes(self):
        for case in CONTRADICTION_CASES:
            with self.subTest(case_id=case["case_id"]):
                self.assertNotEqual(
                    case["original_note"],
                    case["modified_note"],
                )
                self.assertIn("contradiction", case["expected_flags"])
                self.assertIn("human_review", case["expected_flags"])

    def test_rare_diagnosis_cases_expect_abstention(self):
        for case in RARE_DIAGNOSIS_CASES:
            with self.subTest(case_id=case["case_id"]):
                self.assertEqual(
                    case["expected_coding_outcome"],
                    "no_confident_match",
                )
                self.assertTrue(case["table_coverage_review_required"])
                self.assertTrue(case["diagnosis_mention"])
                self.assertTrue(case["note_text"])

    def test_adversarial_cases_define_required_behaviour(self):
        for case in ADVERSARIAL_CASES:
            with self.subTest(case_id=case["case_id"]):
                self.assertTrue(case["note_text"])
                self.assertTrue(case["attack_type"])
                self.assertTrue(case["required_behavior"])

    def test_identifier_cases_require_safe_handling(self):
        cases_with_identifiers = [
            case
            for case in ADVERSARIAL_CASES
            if case["synthetic_identifiers"]
        ]

        self.assertTrue(cases_with_identifiers)

        for case in cases_with_identifiers:
            with self.subTest(case_id=case["case_id"]):
                self.assertIn(
                    "mask_identifiers_before_external_call",
                    case["required_behavior"],
                )
                self.assertIn(
                    "exclude_identifiers_from_trace",
                    case["required_behavior"],
                )