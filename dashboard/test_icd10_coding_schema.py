"""Tests for the structured ICD-10 coding-result contract."""

from django.test import SimpleTestCase
from pydantic import ValidationError

from dashboard.extraction.coding_schema import (
    ICD10CodeCandidate,
    ICD10CodingResult,
    coding_result_from_lookup,
)
from dashboard.extraction.icd10_search import (
    ICD10Candidate,
    ICD10LookupResult,
)


class ICD10CodingSchemaTests(SimpleTestCase):
    def test_converts_qualifying_lookup_result(self):
        lookup = ICD10LookupResult(
            query="example diagnosis",
            status="candidates_found",
            candidates=(
                ICD10Candidate(
                    code="A000",
                    description="Example diagnosis",
                    lexical_score=1.0,
                ),
            ),
        )

        result = coding_result_from_lookup(lookup)

        self.assertEqual(result.status, "candidates_found")
        self.assertEqual(
            result.candidate_disposition,
            "threshold_met",
        )
        self.assertEqual(result.candidates[0].rank, 1)
        self.assertEqual(result.candidates[0].code, "A000")

    def test_marks_weak_suggestions_for_review_only(self):
        lookup = ICD10LookupResult(
            query="xylophagia quasar syndrome",
            status="no_confident_match",
            candidates=(
                ICD10Candidate(
                    code="D6861",
                    description="Antiphospholipid syndrome",
                    lexical_score=0.3533,
                ),
            ),
            reason="No candidate met the configured lexical threshold.",
        )

        result = coding_result_from_lookup(lookup)

        self.assertEqual(result.status, "no_confident_match")
        self.assertEqual(
            result.candidate_disposition,
            "weak_matches_for_review",
        )
        self.assertEqual(len(result.candidates), 1)

    def test_represents_no_candidates_explicitly(self):
        lookup = ICD10LookupResult(
            query="unmatched query",
            status="no_confident_match",
            candidates=(),
            reason="No ICD-10-CM descriptions matched the query terms.",
        )

        result = coding_result_from_lookup(lookup)

        self.assertEqual(result.candidate_disposition, "none")
        self.assertEqual(result.candidates, ())

    def test_rejects_invalid_code_format(self):
        with self.assertRaises(ValidationError):
            ICD10CodeCandidate(
                code="bad-code",
                description="Example",
                lexical_score=1.0,
                rank=1,
            )

    def test_rejects_score_outside_range(self):
        with self.assertRaises(ValidationError):
            ICD10CodeCandidate(
                code="A000",
                description="Example",
                lexical_score=1.2,
                rank=1,
            )

    def test_rejects_nonconsecutive_ranks(self):
        candidate = ICD10CodeCandidate(
            code="A000",
            description="Example",
            lexical_score=1.0,
            rank=2,
        )

        with self.assertRaises(ValidationError):
            ICD10CodingResult(
                query="example",
                status="candidates_found",
                candidate_disposition="threshold_met",
                candidates=(candidate,),
            )

    def test_rejects_weak_candidates_marked_as_threshold_met(self):
        candidate = ICD10CodeCandidate(
            code="D6861",
            description="Antiphospholipid syndrome",
            lexical_score=0.3533,
            rank=1,
        )

        with self.assertRaises(ValidationError):
            ICD10CodingResult(
                query="unmatched diagnosis",
                status="no_confident_match",
                candidate_disposition="threshold_met",
                candidates=(candidate,),
                reason="No candidate met the configured threshold.",
            )

    def test_rejects_no_match_without_a_reason(self):
        with self.assertRaises(ValidationError):
            ICD10CodingResult(
                query="unmatched diagnosis",
                status="no_confident_match",
                candidate_disposition="none",
                candidates=(),
            )