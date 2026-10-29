"""Tests for keyword-based ICD-10-CM retrieval."""

from django.test import TestCase

from dashboard.extraction.icd10_search import search_icd10
from dashboard.models import ICDCode


class ICD10SearchTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        ICDCode.objects.bulk_create(
            [
                ICDCode(
                    code="TST001",
                    description=(
                        "Type 2 diabetes mellitus without complications"
                    ),
                ),
                ICDCode(
                    code="TST002",
                    description="Type 2 diabetes mellitus, unspecified",
                ),
                ICDCode(
                    code="TST003",
                    description="Headache, unspecified",
                ),
                ICDCode(
                    code="TST004",
                    description="Cholera due to Vibrio cholerae",
                ),
                ICDCode(
                    code="TST005",
                    description=(
                        "Cholera due to Vibrio cholerae "
                        "01, biovar cholerae"
                    ),
                ),
                ICDCode(
                    code="TST006",
                    description=(
                        "Cholera due to Vibrio cholerae "
                        "01, biovar eltor"
                    ),
                ),
                ICDCode(
                    code="TST007",
                    description="Condition, unspecified",
                ),
                ICDCode(
                    code="TST008",
                    description="Post COVID-19 condition, unspecified",
                ),
                ICDCode(
                    code="I10",
                    description="Essential (primary) hypertension",
                ),
                ICDCode(
                    code="R030",
                    description=(
                        "Elevated blood-pressure reading, without diagnosis "
                        "of hypertension"
                    ),
                ),
                ICDCode(
                    code="R031",
                    description="Nonspecific low blood-pressure reading",
                ),
            ]
        )

    def test_ranks_best_keyword_candidate_first(self):
        result = search_icd10(
            "Type 2 diabetes mellitus without complications"
        )

        self.assertEqual(result.status, "candidates_found")
        self.assertGreaterEqual(len(result.candidates), 1)
        self.assertEqual(result.candidates[0].code, "TST001")
        self.assertEqual(result.candidates[0].lexical_score, 1.0)

    def test_ranks_exact_word_sequence_above_variant(self):
        result = search_icd10(
            "Cholera due to Vibrio cholerae 01, biovar cholerae"
        )

        self.assertEqual(result.status, "candidates_found")
        self.assertEqual(result.candidates[0].code, "TST005")

        variant = next(
            candidate
            for candidate in result.candidates
            if candidate.code == "TST006"
        )
        self.assertLess(
            variant.lexical_score,
            result.candidates[0].lexical_score,
        )

    def test_filters_weak_candidates_when_a_strong_match_exists(self):
        result = search_icd10(
            "Post COVID-19 condition, unspecified"
        )

        self.assertEqual(result.status, "candidates_found")
        self.assertEqual(result.candidates[0].code, "TST008")
        self.assertNotIn(
            "TST007",
            [candidate.code for candidate in result.candidates],
        )

    def test_returns_no_confident_match_for_unknown_terms(self):
        result = search_icd10("xylophagia quasar syndrome")

        self.assertEqual(result.status, "no_confident_match")
        self.assertEqual(result.candidates, ())

    def test_returns_no_confident_match_for_weak_lexical_overlap(self):
        result = search_icd10("severe headache")

        self.assertEqual(result.status, "no_confident_match")
        self.assertGreaterEqual(len(result.candidates), 1)
        self.assertLess(
            result.candidates[0].lexical_score,
            0.6,
        )

    def test_ignores_case_and_consecutive_duplicate_terms(self):
        result = search_icd10("DIABETES diabetes")

        self.assertEqual(result.status, "candidates_found")
        self.assertEqual(result.candidates[0].lexical_score, 1.0)

    def test_empty_query_returns_no_confident_match(self):
        result = search_icd10("   ")

        self.assertEqual(result.status, "no_confident_match")
        self.assertEqual(result.candidates, ())

    def test_limit_controls_number_of_candidates(self):
        result = search_icd10(
            "type 2 diabetes mellitus",
            limit=1,
        )

        self.assertLessEqual(len(result.candidates), 1)

    def test_rejects_invalid_limit(self):
        with self.assertRaises(ValueError):
            search_icd10("headache", limit=0)

    def test_rejects_invalid_threshold(self):
        with self.assertRaises(ValueError):
            search_icd10(
                "headache",
                minimum_lexical_score=1.5,
            )

    def test_rejects_non_string_query(self):
        with self.assertRaises(TypeError):
            search_icd10(None)

    def test_high_blood_pressure_reading_prefers_elevated_reading(self):
        result = search_icd10("high blood pressure reading", limit=5)

        self.assertEqual(result.candidates[0].code, "R030")
        self.assertGreater(
            result.candidates[0].lexical_score,
            next(
                candidate.lexical_score
                for candidate in result.candidates
                if candidate.code == "R031"
            ),
        )
        self.assertNotEqual(result.candidates[0].code, "I10")

    def test_low_blood_pressure_reading_prefers_low_reading(self):
        result = search_icd10("low blood pressure reading", limit=5)

        self.assertEqual(result.candidates[0].code, "R031")

    def test_blood_pressure_regressions_preserve_existing_top_candidates(self):
        self.assertEqual(
            search_icd10("essential hypertension", limit=5).candidates[0].code,
            "I10",
        )
        self.assertEqual(
            search_icd10(
                "elevated blood pressure reading",
                limit=5,
            ).candidates[0].code,
            "R030",
        )

    def test_prefers_exact_specific_description_over_unspecified_variant(self):
        result = search_icd10(
            "Type 2 diabetes mellitus without complications",
            limit=5,
        )

        self.assertEqual(result.candidates[0].code, "TST001")
        self.assertGreater(
            result.candidates[0].lexical_score,
            next(
                candidate.lexical_score
                for candidate in result.candidates
                if candidate.code == "TST002"
            ),
        )

    def test_supports_common_non_diagnostic_synonyms(self):
        self.assertEqual(
            search_icd10("HTN").candidates[0].code,
            "I10",
        )
        self.assertEqual(
            search_icd10("high BP reading").candidates[0].code,
            "R030",
        )

    def test_abstains_for_negated_or_uncertain_queries(self):
        for query in (
            "no diabetes",
            "possible diabetes",
        ):
            with self.subTest(query=query):
                result = search_icd10(query)
                self.assertEqual(result.status, "no_confident_match")
                self.assertEqual(result.candidates, ())
                self.assertIsNotNone(result.reason)