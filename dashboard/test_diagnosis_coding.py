"""Integration tests for diagnosis mention coding."""

from unittest.mock import patch

from django.test import TestCase
from pydantic import ValidationError

from dashboard.extraction.coding_schema import ICD10CodingResult
from dashboard.extraction.diagnosis_coding import code_diagnoses
from dashboard.extraction.service import ExtractionOutputError
from dashboard.models import ICDCode


class DiagnosisCodingIntegrationTests(TestCase):
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
                    description="Placeholder syndrome",
                ),
            ]
        )

    def make_payload(
        self,
        note,
        *,
        category="diagnosis",
        entity="Type 2 diabetes mellitus without complications",
        evidence="Type 2 diabetes mellitus without complications",
        status="active",
    ):
        start = note.index(evidence)

        return {
            "items": [
                {
                    "category": category,
                    "entity": entity,
                    "status": status,
                    "evidence_text": evidence,
                    "start_offset": start,
                    "end_offset": start + len(evidence),
                    "attributes": {},
                }
            ],
            "needs_review": False,
            "review_reasons": [],
        }

    def test_codes_diagnosis_and_preserves_original_evidence(self):
        note = (
            "Assessment: "
            "Type 2 diabetes mellitus without complications."
        )
        payload = self.make_payload(note)

        result = code_diagnoses(payload, note)

        self.assertEqual(len(result.diagnoses), 1)

        mention = result.diagnoses[0]
        self.assertEqual(
            mention.evidence_text,
            "Type 2 diabetes mellitus without complications",
        )
        self.assertEqual(
            note[mention.start_offset:mention.end_offset],
            mention.evidence_text,
        )
        self.assertEqual(
            mention.coding.candidates[0].code,
            "TST001",
        )
        self.assertEqual(
            mention.coding.status,
            "candidates_found",
        )

    def test_preserves_historical_status(self):
        note = (
            "History: Type 2 diabetes mellitus without complications."
        )
        payload = self.make_payload(note, status="historical")

        result = code_diagnoses(payload, note)

        self.assertEqual(
            result.diagnoses[0].status,
            "historical",
        )
        self.assertEqual(
            result.diagnoses[0].coding.candidates[0].code,
            "TST001",
        )

    def test_does_not_code_non_diagnosis_mentions(self):
        note = "Medication: metformin."
        payload = self.make_payload(
            note,
            category="medication",
            entity="metformin",
            evidence="metformin",
            status="current",
        )

        result = code_diagnoses(payload, note)

        self.assertEqual(result.diagnoses, ())

    def test_rejects_invalid_evidence_before_lookup(self):
        note = (
            "Assessment: "
            "Type 2 diabetes mellitus without complications."
        )
        payload = self.make_payload(note)
        payload["items"][0]["evidence_text"] = "unsupported phrase"

        with patch(
            "dashboard.extraction.diagnosis_coding.search_icd10"
        ) as mocked_search:
            with self.assertRaises(ExtractionOutputError):
                code_diagnoses(payload, note)

        mocked_search.assert_not_called()

    def test_marks_weak_candidates_for_review(self):
        note = "Assessment: orphan syndrome."
        payload = self.make_payload(
            note,
            entity="orphan syndrome",
            evidence="orphan syndrome",
        )

        result = code_diagnoses(payload, note)
        coding = result.diagnoses[0].coding

        self.assertIsInstance(coding, ICD10CodingResult)
        self.assertEqual(
            coding.status,
            "no_confident_match",
        )
        self.assertEqual(
            coding.candidate_disposition,
            "weak_matches_for_review",
        )
        self.assertEqual(
            coding.candidates[0].code,
            "TST002",
        )