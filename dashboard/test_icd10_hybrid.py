"""Tests for hybrid ICD-10-CM retrieval."""

from unittest.mock import patch

from django.test import TestCase

from dashboard.extraction.icd10_search import search_hybrid_icd10
from dashboard.extraction.icd10_semantic import SemanticCandidate
from dashboard.models import ICDCode


class HybridICD10SearchTests(TestCase):
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
            ]
        )

    @patch("dashboard.extraction.icd10_semantic.search_semantic_icd10")
    def test_combines_lexical_and_semantic_scores(self, mock_semantic):
        mock_semantic.return_value = (
            SemanticCandidate(
                code="TST001",
                description=(
                    "Type 2 diabetes mellitus without complications"
                ),
                semantic_score=0.91,
            ),
            SemanticCandidate(
                code="TST002",
                description="Type 2 diabetes mellitus, unspecified",
                semantic_score=0.86,
            ),
        )

        result = search_hybrid_icd10(
            "Type 2 diabetes mellitus without complications"
        )

        self.assertEqual(result.status, "candidates_found")
        self.assertEqual(result.candidates[0].code, "TST001")
        self.assertEqual(result.candidates[0].lexical_score, 1.0)
        self.assertEqual(result.candidates[0].semantic_score, 0.91)
        self.assertAlmostEqual(
            result.candidates[0].combined_score,
            0.65 * 1.0 + 0.35 * 0.91,
        )

    @patch("dashboard.extraction.icd10_semantic.search_semantic_icd10")
    def test_semantics_can_retrieve_alternate_wording(self, mock_semantic):
        mock_semantic.return_value = (
            SemanticCandidate(
                code="TST001",
                description=(
                    "Type 2 diabetes mellitus without complications"
                ),
                semantic_score=0.85,
            ),
        )

        result = search_hybrid_icd10("high blood sugar disorder")

        self.assertEqual(result.status, "candidates_found")
        self.assertEqual(result.candidates[0].code, "TST001")
        self.assertEqual(result.candidates[0].lexical_score, 0.0)
        self.assertEqual(result.candidates[0].semantic_score, 0.85)

    @patch("dashboard.extraction.icd10_semantic.search_semantic_icd10")
    def test_weak_semantic_similarity_does_not_count_as_confident(
        self,
        mock_semantic,
    ):
        mock_semantic.return_value = (
            SemanticCandidate(
                code="TST003",
                description="Headache, unspecified",
                semantic_score=0.812,
            ),
        )

        result = search_hybrid_icd10("xylophagia quasar syndrome")

        self.assertEqual(result.status, "no_confident_match")
        self.assertEqual(result.candidates[0].code, "TST003")
        self.assertLess(
            result.candidates[0].semantic_score,
            0.83,
        )
        self.assertIn("review only", result.reason)

    @patch("dashboard.extraction.icd10_semantic.search_semantic_icd10")
    def test_exact_lexical_match_can_pass_without_semantic_result(
        self,
        mock_semantic,
    ):
        mock_semantic.return_value = ()

        result = search_hybrid_icd10(
            "Type 2 diabetes mellitus without complications"
        )

        self.assertEqual(result.status, "candidates_found")
        self.assertEqual(result.candidates[0].code, "TST001")
        self.assertEqual(result.candidates[0].lexical_score, 1.0)
        self.assertIsNone(result.candidates[0].semantic_score)

    def test_rejects_invalid_semantic_threshold(self):
        with self.assertRaises(ValueError):
            search_hybrid_icd10(
                "headache",
                minimum_semantic_score=1.5,
            )

    @patch("dashboard.extraction.icd10_semantic.search_semantic_icd10")
    def test_empty_query_does_not_invoke_semantic_search(
        self,
        mock_semantic,
    ):
        result = search_hybrid_icd10("   ")

        self.assertEqual(result.status, "no_confident_match")
        self.assertEqual(result.candidates, ())
        mock_semantic.assert_not_called()