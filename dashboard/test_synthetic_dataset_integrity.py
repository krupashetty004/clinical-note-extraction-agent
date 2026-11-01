"""Regression coverage for synthetic reference and AI annotation separation."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from dashboard.extraction.dataset import (
    REQUIRED_ANNOTATION_FIELDS,
    annotation_readiness,
    build_evaluation_gold_cases,
    load_jsonl,
)
from evaluation.generate_ai_benchmark import (
    DEFAULT_CASES_PATH,
    DEFAULT_INPUT_PATH,
    DEFAULT_QUEUE_PATH,
    is_synthetic_record,
)
from scripts import generate_golden_annotations, prepare_100_synthetic_dataset


class SyntheticDatasetIntegrityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.records = prepare_100_synthetic_dataset.generate_100_records()
        cls.records_by_id = {row["record_id"]: row for row in cls.records}

    def test_generator_creates_100_synthetic_records_across_10_specialties(self) -> None:
        self.assertEqual(len(self.records), 100)
        self.assertEqual(len({row["specialty"] for row in self.records}), 10)
        for row in self.records:
            self.assertEqual(row["source_dataset"], "synthetic:mirai-clinical-notes-v1")
            self.assertEqual(row["source_url"], "local://synthetic")
            self.assertTrue(is_synthetic_record(
                _dataset_record_for_synthetic_input(row)
            ))

    def test_reference_fixtures_are_not_claimed_as_human_or_clinical_gold(self) -> None:
        prohibited_fields = {
            "annotator_id",
            "adjudicator_id",
            "annotator_qualification",
        }
        for row in self.records:
            self.assertEqual(row["label_source"], "synthetic_reference_fixture")
            self.assertEqual(row["adjudication_status"], "not_reviewed")
            self.assertFalse(row["clinical_performance_eligible"])
            self.assertFalse(row["gold_evaluation_ready"])
            self.assertFalse(row["label_provenance"]["is_human_gold"])
            self.assertTrue(prohibited_fields.isdisjoint(row))

    def test_fixture_codes_are_only_emitted_when_reference_descriptions_exist(self) -> None:
        icd_reference = prepare_100_synthetic_dataset.ICD_REF
        for row in self.records:
            for item in row["gold_annotations"]["diagnoses"]:
                if "icd10_code" in item:
                    self.assertIn(item["icd10_code"], icd_reference)
            for item in row["gold_annotations"]["icd10_cm_codes"]:
                self.assertEqual(item["description"], icd_reference[item["code"]])
                self.assertNotEqual(item["description"], "Unspecified")

    def test_every_reference_entity_span_matches_its_synthetic_note(self) -> None:
        category_map = {
            "diagnoses": "diagnosis",
            "medications": "medication",
            "procedures": "procedure",
            "allergies": "allergy",
            "vital_signs": "vital_sign",
        }
        for row in self.records:
            for group, category in category_map.items():
                for item in row["gold_annotations"][group]:
                    start = item["start_offset"]
                    end = item["end_offset"]
                    self.assertEqual(item["evidence_text"], row["note_text"][start:end])
                    self.assertEqual(item["entity"], row["note_text"][start:end])

    def test_offline_review_corrections_cover_omitted_note_entities(self):
        cardio_followup = self.records_by_id["mirai-synth-002"]
        cardio_medications = {
            item["entity"].casefold()
            for item in cardio_followup["gold_annotations"]["medications"]
        }
        self.assertIn("carvedilol", cardio_medications)

        post_mi = self.records_by_id["mirai-synth-004"]
        self.assertIn(
            "lipid panel",
            [item["entity"].casefold() for item in post_mi["gold_annotations"]["procedures"]],
        )

        hypertensive_urgency = self.records_by_id["mirai-synth-007"]
        self.assertIn(
            "hypertensive urgency",
            [item["entity"].casefold() for item in hypertensive_urgency["gold_annotations"]["diagnoses"]],
        )
        self.assertIn(
            "labetalol",
            [item["entity"].casefold() for item in hypertensive_urgency["gold_annotations"]["medications"]],
        )

        t1_diabetes = self.records_by_id["mirai-synth-033"]
        self.assertIn(
            "insulin lispro",
            [item["entity"].casefold() for item in t1_diabetes["gold_annotations"]["medications"]],
        )

        kidney_disease = self.records_by_id["mirai-synth-037"]
        self.assertIn(
            "glimepiride",
            [item["entity"].casefold() for item in kidney_disease["gold_annotations"]["medications"]],
        )
        self.assertNotIn(
            "hypertension",
            [item["entity"].casefold() for item in kidney_disease["gold_annotations"]["diagnoses"]],
        )

        pancreatic_cancer = self.records_by_id["mirai-synth-086"]
        self.assertIn(
            "pancreatic cancer",
            [item["entity"].casefold() for item in pancreatic_cancer["gold_annotations"]["diagnoses"]],
        )

        renal_artery_stenosis = self.records_by_id["mirai-synth-097"]
        self.assertIn(
            "renal artery stenosis",
            [item["entity"].casefold() for item in renal_artery_stenosis["gold_annotations"]["diagnoses"]],
        )

        fatty_liver = self.records_by_id["mirai-synth-099"]
        self.assertIn(
            "nonalcoholic fatty liver disease",
            [item["entity"].casefold() for item in fatty_liver["gold_annotations"]["diagnoses"]],
        )

    def test_offline_review_provenance_does_not_claim_human_gold(self):
        for row in self.records:
            provenance = row["label_provenance"]
            self.assertEqual(provenance["review_method"], "offline_source_text_audit")
            self.assertEqual(provenance["review_batch_count"], 10)
            self.assertEqual(provenance["review_batch_size"], 10)
            self.assertEqual(provenance["review_batch_number"], ((int(row["source_row_number"]) - 1) // 10) + 1)
            self.assertEqual(provenance["review_batch_record_number"], ((int(row["source_row_number"]) - 1) % 10) + 1)
            self.assertFalse(provenance["is_human_gold"])
            self.assertFalse(row["clinical_performance_eligible"])
            self.assertEqual(row["adjudication_status"], "not_reviewed")

    def test_ai_input_contains_no_prelabelled_annotations(self) -> None:
        fixture = self.records[0]
        ai_input = prepare_100_synthetic_dataset.build_ai_input_record(fixture)
        self.assertEqual(ai_input["record_id"], fixture["record_id"])
        self.assertEqual(ai_input["note_text"], fixture["note_text"])
        self.assertNotIn("gold_annotations", ai_input)
        self.assertNotIn("label_source", ai_input)
        self.assertNotIn("label_provenance", ai_input)
        self.assertNotIn("clinical_performance_eligible", ai_input)

    def test_known_medication_and_procedure_categories_are_corrected(self) -> None:
        cardiology_hypertensive_urgency = self.records_by_id["mirai-synth-007"]
        self.assertIn(
            "labetalol",
            [item["entity"].casefold() for item in cardiology_hypertensive_urgency["gold_annotations"]["medications"]],
        )
        self.assertEqual(cardiology_hypertensive_urgency["gold_annotations"]["procedures"], [])

        angina_followup = self.records_by_id["mirai-synth-010"]
        self.assertIn(
            "nitroglycerin",
            [item["entity"].casefold() for item in angina_followup["gold_annotations"]["medications"]],
        )
        self.assertIn(
            "isosorbide mononitrate",
            [item["entity"].casefold() for item in angina_followup["gold_annotations"]["medications"]],
        )
        self.assertEqual(angina_followup["gold_annotations"]["procedures"], [])

        migraine_case = self.records_by_id["mirai-synth-020"]
        self.assertIn(
            "cgrp antagonist",
            [item["entity"].casefold() for item in migraine_case["gold_annotations"]["medications"]],
        )
        self.assertEqual(migraine_case["gold_annotations"]["procedures"], [])

    def test_exercise_advice_is_not_a_procedure_but_iv_hydration_is(self) -> None:
        exercise_case = self.records_by_id["mirai-synth-057"]
        self.assertEqual(exercise_case["gold_annotations"]["procedures"], [])

        hydration_case = self.records_by_id["mirai-synth-096"]
        procedure_entities = [
            item["entity"].casefold()
            for item in hydration_case["gold_annotations"]["procedures"]
        ]
        self.assertIn("intravenous normal saline hydration", procedure_entities)

    def test_generated_synthetic_references_cannot_unlock_clinical_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "synthetic_references.jsonl"
            path.write_text(
                "".join(json.dumps(row) + "\n" for row in self.records),
                encoding="utf-8",
            )
            loaded = load_jsonl(path, required_fields=REQUIRED_ANNOTATION_FIELDS)

        self.assertEqual(loaded.errors, ())
        readiness = annotation_readiness(loaded)
        self.assertEqual(readiness["records_loaded"], 100)
        self.assertEqual(readiness["clinical_performance_eligible"], 0)
        self.assertFalse(readiness["gold_evaluation_ready"])
        cases, report = build_evaluation_gold_cases(loaded)
        self.assertEqual(cases, [])
        self.assertEqual(report["metric_status"], "blocked")

    def test_legacy_golden_script_refuses_to_generate_gold_labels(self) -> None:
        self.assertEqual(generate_golden_annotations.main([]), 2)

    def test_ai_benchmark_defaults_use_git_ignored_local_workspace(self) -> None:
        self.assertEqual(DEFAULT_INPUT_PATH, Path(".dataset_working/synthetic/ai_input_100.jsonl"))
        self.assertEqual(DEFAULT_CASES_PATH, Path(".dataset_working/ai_benchmark/cases.jsonl"))
        self.assertEqual(DEFAULT_QUEUE_PATH, Path(".dataset_working/ai_benchmark/annotations.jsonl"))

    def test_legacy_note_level_annotation_template_is_not_tracked(self) -> None:
        repository_root = Path(__file__).resolve().parents[1]
        legacy_template = (
            repository_root
            / "mirai_dataset_preparation_pack"
            / "data"
            / "external"
            / "mtsamples"
            / "annotations"
            / "annotation_template_100.jsonl"
        )
        self.assertFalse(legacy_template.exists())
        gitignore = repository_root / ".gitignore"
        self.assertIn(
            "mirai_dataset_preparation_pack/data/external/mtsamples/annotations/*.jsonl",
            gitignore.read_text(encoding="utf-8"),
        )


def _dataset_record_for_synthetic_input(row: dict[str, object]):
    """Construct the minimal immutable record expected by the source gate."""
    from dashboard.extraction.dataset import DatasetRecord

    return DatasetRecord(
        record_id=str(row["record_id"]),
        source_dataset=str(row["source_dataset"]),
        source_url=str(row["source_url"]),
        source_row_number=int(row["source_row_number"]),
        specialty=str(row["specialty"]),
        note_text=str(row["note_text"]),
        metadata=row,
    )


if __name__ == "__main__":
    unittest.main()
