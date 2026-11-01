"""Tests for the offline ICD-10 batch integrity audit."""
from __future__ import annotations

import hashlib
import unittest

from evaluation.audit_icd10_batch import audit_icd10_batch


class ICD10BatchAuditTests(unittest.TestCase):
    def setUp(self) -> None:
        self.note = "Assessment: essential hypertension."
        self.start = self.note.index("essential hypertension")
        self.end = self.start + len("essential hypertension")
        self.source_rows = [
            {
                "record_id": "SYN-001",
                "note_text": self.note,
            }
        ]
        self.reference_codes = {
            "I10": "Essential (primary) hypertension",
        }
        self.prediction_rows = [
            {
                "case_id": "SYN-001",
                "note_sha256": hashlib.sha256(
                    self.note.encode("utf-8")
                ).hexdigest(),
                "items": [
                    {
                        "category": "diagnosis",
                        "entity": "essential hypertension",
                        "status": "active",
                        "evidence_text": "essential hypertension",
                        "start_offset": self.start,
                        "end_offset": self.end,
                        "decision": "accepted",
                        "icd10_candidates": ["I10"],
                        "icd10_candidate_details": [
                            {
                                "code": "I10",
                                "description": (
                                    "Essential (primary) hypertension"
                                ),
                                "rank": 1,
                                "lexical_score": 1.0,
                                "semantic_score": 0.91,
                                "combined_score": 0.9685,
                            }
                        ],
                        "icd10_status": "candidates_found",
                        "icd10_candidate_disposition": "threshold_met",
                        "icd10_reason": "",
                    }
                ],
            }
        ]

    def audit(self):
        return audit_icd10_batch(
            self.source_rows,
            self.prediction_rows,
            self.reference_codes,
        )

    def test_valid_batch_passes_integrity_audit_without_claiming_accuracy(self):
        report = self.audit()

        self.assertEqual(report["audit_status"], "PASS")
        self.assertEqual(report["integrity_error_count"], 0)
        self.assertEqual(report["matched_record_count"], 1)
        self.assertEqual(report["diagnosis_item_count"], 1)
        self.assertEqual(report["evidence_spans_checked"], 1)
        self.assertEqual(report["candidate_count"], 1)
        self.assertFalse(report["clinical_accuracy_evaluated"])
        self.assertFalse(report["clinical_performance_claimed"])

    def test_flags_note_hash_and_evidence_span_mismatch(self):
        self.prediction_rows[0]["note_sha256"] = "incorrect"
        self.prediction_rows[0]["items"][0]["evidence_text"] = "hypertension"

        report = self.audit()
        codes = {item["code"] for item in report["errors"]}

        self.assertEqual(report["audit_status"], "FAIL")
        self.assertIn("note_sha256_mismatch", codes)
        self.assertIn("evidence_text_mismatch", codes)

    def test_flags_missing_reference_code_and_description_mismatch(self):
        candidate = self.prediction_rows[0]["items"][0][
            "icd10_candidate_details"
        ][0]
        candidate["description"] = "Wrong description"
        candidate["code"] = "Z999"
        self.prediction_rows[0]["items"][0]["icd10_candidates"] = ["Z999"]

        report = self.audit()
        codes = {item["code"] for item in report["errors"]}

        self.assertEqual(report["candidate_code_missing_count"], 1)
        self.assertIn("candidate_code_missing_from_reference", codes)
        self.assertIn("candidate_code_detail_mismatch", codes)

    def test_flags_candidate_description_mismatch_for_known_code(self):
        candidate = self.prediction_rows[0]["items"][0][
            "icd10_candidate_details"
        ][0]
        candidate["description"] = "Hypertension, unspecified"

        report = self.audit()

        self.assertEqual(
            report["candidate_description_mismatch_count"],
            1,
        )
        self.assertIn(
            "candidate_description_mismatch",
            {item["code"] for item in report["errors"]},
        )

    def test_flags_invalid_rank_and_scores(self):
        candidate = self.prediction_rows[0]["items"][0][
            "icd10_candidate_details"
        ][0]
        candidate["rank"] = 2
        candidate["lexical_score"] = 1.5

        report = self.audit()
        codes = {item["code"] for item in report["errors"]}

        self.assertEqual(report["candidate_rank_mismatch_count"], 1)
        self.assertEqual(report["candidate_score_invalid_count"], 1)
        self.assertIn("candidate_rank_invalid", codes)
        self.assertIn("candidate_score_invalid", codes)

    def test_flags_weak_candidate_accepted(self):
        item = self.prediction_rows[0]["items"][0]
        item["icd10_status"] = "no_confident_match"
        item["icd10_candidate_disposition"] = "weak_matches_for_review"
        item["icd10_reason"] = "Weak match; review required."

        report = self.audit()

        self.assertEqual(report["weak_candidate_accepted_count"], 1)
        self.assertIn(
            "weak_candidate_accepted",
            {item["code"] for item in report["errors"]},
        )

    def test_flags_no_match_accepted(self):
        item = self.prediction_rows[0]["items"][0]
        item["icd10_candidates"] = []
        item["icd10_candidate_details"] = []
        item["icd10_status"] = "no_confident_match"
        item["icd10_candidate_disposition"] = "none"
        item["icd10_reason"] = "No supported candidate."

        report = self.audit()

        self.assertEqual(report["no_confident_match_accepted_count"], 1)
        self.assertIn(
            "no_confident_match_accepted",
            {item["code"] for item in report["errors"]},
        )

    def test_flags_suspected_and_ruled_out_diagnoses_accepted(self):
        item = self.prediction_rows[0]["items"][0]
        item["status"] = "suspected"
        suspected_report = self.audit()
        self.assertEqual(
            suspected_report["suspected_diagnosis_accepted_count"],
            1,
        )

        item["status"] = "ruled_out"
        ruled_out_report = self.audit()
        self.assertEqual(
            ruled_out_report["ruled_out_diagnosis_accepted_count"],
            1,
        )

    def test_flags_missing_and_unexpected_prediction_records(self):
        extra = {
            "case_id": "SYN-002",
            "note_sha256": "does-not-matter",
            "items": [],
        }
        self.prediction_rows.append(extra)

        report = self.audit()
        codes = {item["code"] for item in report["errors"]}

        self.assertEqual(report["missing_prediction_count"], 0)
        self.assertEqual(report["unexpected_prediction_count"], 1)
        self.assertIn("prediction_without_source_record", codes)

    def test_no_confident_match_with_weak_candidates_is_a_valid_review_state(self):
        item = self.prediction_rows[0]["items"][0]
        item["decision"] = "needs_review"
        item["icd10_status"] = "no_confident_match"
        item["icd10_candidate_disposition"] = "weak_matches_for_review"
        item["icd10_reason"] = "Retrieval threshold not met."

        report = self.audit()

        self.assertEqual(report["audit_status"], "PASS")
        self.assertEqual(report["integrity_error_count"], 0)


if __name__ == "__main__":
    unittest.main()
