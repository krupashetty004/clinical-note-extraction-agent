"""Tests for LocalClinicalExtractionProvider and LocalClinicalVerificationProvider."""

from unittest import TestCase as PureTestCase

from dashboard.extraction.local_provider import (
    LocalClinicalExtractionProvider,
    LocalClinicalVerificationProvider,
)
from dashboard.extraction.schema import ExtractionResult, ExtractedItem
from dashboard.extraction.diagnosis_coding import DiagnosisCodingBatch


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_valid_item(note: str, term: str, category: str, status: str) -> ExtractedItem:
    """Build an ExtractedItem with exact offsets grounded in note."""
    idx = note.lower().find(term.lower())
    if idx == -1:
        raise ValueError(f"{term!r} not found in note.")
    end = idx + len(term)
    return ExtractedItem(
        category=category,
        entity=note[idx:end],
        evidence_text=note[idx:end],
        start_offset=idx,
        end_offset=end,
        status=status,
        attributes={},
    )


def _make_extraction_result(items: list[ExtractedItem]) -> ExtractionResult:
    """Wrap a list of ExtractedItem objects into an ExtractionResult."""
    return ExtractionResult(items=items, needs_review=False, review_reasons=[])


def _make_invalid_extraction(items_data: list[dict]) -> ExtractionResult:
    """Build an ExtractionResult bypassing Pydantic validation (for failure tests)."""
    parsed_items = [
        ExtractedItem.model_construct(**item) for item in items_data
    ]
    return ExtractionResult.model_construct(
        items=parsed_items, needs_review=False, review_reasons=[]
    )


def _empty_coding() -> DiagnosisCodingBatch:
    return DiagnosisCodingBatch()


# ---------------------------------------------------------------------------
# LocalClinicalExtractionProvider
# ---------------------------------------------------------------------------

class TestLocalClinicalExtractionProvider(PureTestCase):
    """Existing tests plus regression for explicit medication/allergy list parsing."""
    
    def setUp(self):
        self.provider = LocalClinicalExtractionProvider()

    # Existing tests ... (unchanged)
    """Unit tests for LocalClinicalExtractionProvider.extract()."""

    def setUp(self):
        self.provider = LocalClinicalExtractionProvider()

    # --- type safety ---

    def test_raises_type_error_for_none(self):
        with self.assertRaises(TypeError):
            self.provider.extract(None)

    def test_raises_type_error_for_bytes(self):
        with self.assertRaises(TypeError):
            self.provider.extract(b"some bytes")

    def test_raises_type_error_for_int(self):
        with self.assertRaises(TypeError):
            self.provider.extract(12345)

    # --- empty note ---

    def test_empty_string_returns_no_items(self):
        result = self.provider.extract("")
        self.assertEqual(result["items"], [])

    def test_empty_string_needs_review_is_false(self):
        result = self.provider.extract("")
        self.assertFalse(result["needs_review"])

    # --- diagnosis extraction ---

    def test_extracts_hypertension(self):
        note = "Patient has essential hypertension, well controlled."
        result = self.provider.extract(note)
        entities = [i["entity"].lower() for i in result["items"]]
        self.assertTrue(any("hypertension" in e for e in entities))

    def test_extracts_type_2_diabetes_mellitus(self):
        note = "Diagnosis: type 2 diabetes mellitus with peripheral neuropathy."
        result = self.provider.extract(note)
        entities = [i["entity"].lower() for i in result["items"]]
        self.assertTrue(any("diabetes" in e for e in entities))

    def test_extracts_asthma(self):
        note = "Known history of asthma since childhood."
        result = self.provider.extract(note)
        entities = [i["entity"].lower() for i in result["items"]]
        self.assertTrue(any("asthma" in e for e in entities))

    def test_diagnosis_active_status_when_no_context(self):
        note = "Patient has hypertension."
        result = self.provider.extract(note)
        diag = next(
            (i for i in result["items"] if "hypertension" in i["entity"].lower()),
            None,
        )
        self.assertIsNotNone(diag)
        self.assertEqual(diag["status"], "active")

    def test_diagnosis_historical_status(self):
        note = "History of hypertension before the current visit."
        result = self.provider.extract(note)
        diag = next(
            (i for i in result["items"] if "hypertension" in i["entity"].lower()),
            None,
        )
        self.assertIsNotNone(diag)
        self.assertEqual(diag["status"], "historical")

    def test_diagnosis_ruled_out_status(self):
        note = "No evidence of pneumonia was found on chest X-ray."
        result = self.provider.extract(note)
        diag = next(
            (i for i in result["items"] if "pneumonia" in i["entity"].lower()),
            None,
        )
        self.assertIsNotNone(diag)
        self.assertEqual(diag["status"], "ruled_out")

    def test_diagnosis_suspected_status(self):
        note = "Possible hypertension; pending further workup."
        result = self.provider.extract(note)
        diag = next(
            (i for i in result["items"] if "hypertension" in i["entity"].lower()),
            None,
        )
        self.assertIsNotNone(diag)
        self.assertEqual(diag["status"], "suspected")
    def test_extracts_suspected_musculoskeletal_injury(self):
        note = "Assessment: Possible musculoskeletal injury causing chest pain."

        result = self.provider.extract(note)

        item = next(
            (
                item for item in result["items"]
                if item["entity"].casefold() == "musculoskeletal injury"
            ),
            None,
        )

        self.assertIsNotNone(item)
        self.assertEqual(item["category"], "diagnosis")
        self.assertEqual(item["status"], "suspected")
        self.assertEqual(
            note[item["start_offset"]:item["end_offset"]],
            item["evidence_text"],
        )
    # --- medication extraction ---
    def test_extracts_labeled_blood_pressure_value_and_unit(self):
        note = "Vitals: Blood pressure 130/80 mmHg."

        result = self.provider.extract(note)

        item = next(
            (
                item for item in result["items"]
                if item["category"] == "vital_sign"
                and item["entity"].casefold() == "blood pressure"
            ),
            None,
        )

        self.assertIsNotNone(item)
        self.assertEqual(item["attributes"]["value"], "130/80")
        self.assertEqual(item["attributes"]["unit"], "mmHg")
        self.assertEqual(
            note[item["start_offset"]:item["end_offset"]],
            item["evidence_text"],
        )

    def test_generic_vital_sign_reading_does_not_require_review(self):
        note = "Objective: Vital signs are normal (130/80mmHg)."

        result = self.provider.extract(note)

        item = next(
            (
                item for item in result["items"]
                if item["category"] == "vital_sign"
                and item["attributes"].get("value") == "130/80"
            ),
            None,
        )

        self.assertIsNotNone(item)
        self.assertEqual(item["attributes"]["unit"], "mmHg")
        self.assertFalse(result["needs_review"])
        self.assertEqual(result["review_reasons"], [])
        self.assertEqual(
            note[item["start_offset"]:item["end_offset"]],
            item["evidence_text"],
        )
    def test_extracts_metformin(self):
        note = "Patient is on metformin 500mg twice daily for diabetes control."
        result = self.provider.extract(note)
        entities = [i["entity"].lower() for i in result["items"]]
        self.assertTrue(any("metformin" in e for e in entities))

    def test_extracts_lisinopril(self):
        note = "Continue lisinopril 10mg daily for blood pressure management."
        result = self.provider.extract(note)
        entities = [i["entity"].lower() for i in result["items"]]
        self.assertTrue(any("lisinopril" in e for e in entities))

    def test_medication_current_status_by_default(self):
        note = "Patient takes lisinopril for blood pressure."
        result = self.provider.extract(note)
        med = next(
            (i for i in result["items"] if "lisinopril" in i["entity"].lower()),
            None,
        )
        self.assertIsNotNone(med)
        self.assertEqual(med["status"], "current")

    def test_recommended_medication_requires_review(self):
        note = "Plan: Recommend aspirin for pain management."

        result = self.provider.extract(note)

        medication = next(
            (
                item for item in result["items"]
                if item["category"] == "medication"
                and item["entity"].casefold() == "aspirin"
            ),
            None,
        )

        self.assertIsNotNone(medication)
        self.assertEqual(medication["status"], "newly_prescribed")
        self.assertTrue(result["needs_review"])
        self.assertTrue(
            any(
                "prescription status is not explicit" in reason
                for reason in result["review_reasons"]
            )
        )
    def test_medication_discontinued_status(self):
        note = "Discontinued metformin due to GI intolerance."
        result = self.provider.extract(note)
        med = next(
            (i for i in result["items"] if "metformin" in i["entity"].lower()),
            None,
        )
        self.assertIsNotNone(med)
        self.assertEqual(med["status"], "discontinued")

    # --- offsets ---

    def test_offsets_match_evidence_in_note(self):
        note = "Patient has hypertension noted on exam."
        result = self.provider.extract(note)
        for item in result["items"]:
            start = item["start_offset"]
            end = item["end_offset"]
            self.assertEqual(
                note[start:end],
                item["evidence_text"],
                f"Offset mismatch for entity '{item['entity']}': "
                f"note[{start}:{end}]={note[start:end]!r} != {item['evidence_text']!r}",
            )

    def test_no_overlapping_spans(self):
        note = "Type 2 diabetes mellitus with hypertension and hyperlipidemia."
        result = self.provider.extract(note)
        spans = [(i["start_offset"], i["end_offset"]) for i in result["items"]]
        for idx_a, (s_a, e_a) in enumerate(spans):
            for idx_b, (s_b, e_b) in enumerate(spans):
                if idx_a >= idx_b:
                    continue
                overlap = max(s_a, s_b) < min(e_a, e_b)
                self.assertFalse(
                    overlap,
                    f"Overlapping spans: [{s_a}:{e_a}] and [{s_b}:{e_b}]",
                )

    def test_items_sorted_by_start_offset(self):
        note = (
            "Patient has hypertension, type 2 diabetes mellitus, "
            "and takes metformin and lisinopril daily."
        )
        result = self.provider.extract(note)
        offsets = [i["start_offset"] for i in result["items"]]
        self.assertEqual(offsets, sorted(offsets))

    # --- result schema keys ---

    def test_result_has_items_key(self):
        result = self.provider.extract("Patient has asthma.")
        self.assertIn("items", result)

    def test_result_has_needs_review_key(self):
        result = self.provider.extract("Patient has asthma.")
        self.assertIn("needs_review", result)

    def test_needs_review_is_bool(self):
        result = self.provider.extract("Patient has asthma.")
        self.assertIsInstance(result["needs_review"], bool)

    def test_each_item_has_required_keys(self):
        result = self.provider.extract("Patient has asthma and takes albuterol.")
        for item in result["items"]:
            for key in ("category", "entity", "evidence_text", "start_offset", "end_offset"):
                self.assertIn(key, item, f"Missing key '{key}' in item: {item}")

    # --- word boundary matching ---

    def test_does_not_match_partial_word(self):
        # "asthmatic" should NOT trigger a standalone "asthma" match
        note = "Patient is asthmatic with exercise-induced bronchospasm."
        result = self.provider.extract(note)
        exact_asthma = [
            i for i in result["items"]
            if i["entity"].lower() == "asthma"
        ]
        self.assertEqual(
            exact_asthma,
            [],
            "Provider should not extract 'asthma' as a standalone entity from 'asthmatic'",
        )

    # --- category field values ---

    def test_diagnosis_category_value(self):
        result = self.provider.extract("Patient has hypertension.")
        diag_items = [i for i in result["items"] if i["category"] == "diagnosis"]
        self.assertTrue(len(diag_items) > 0)

    def test_medication_category_value(self):
        result = self.provider.extract("Patient takes metformin daily.")
        med_items = [i for i in result["items"] if i["category"] == "medication"]
        self.assertTrue(len(med_items) > 0)


# ---------------------------------------------------------------------------
# LocalClinicalVerificationProvider
# ---------------------------------------------------------------------------

class TestLocalClinicalVerificationProvider(PureTestCase):
    """Unit tests for LocalClinicalVerificationProvider.verify().

    The provider returns item_checks with keys:
        item_index, outcome, status_check, reason, evidence
    Failure cases (offset mismatch, ungrounded entity) set outcome='unsupported'.
    """

    def setUp(self):
        self.provider = LocalClinicalVerificationProvider()

    # --- type safety ---

    def test_raises_type_error_for_none_note(self):
        extraction = _make_extraction_result([])
        with self.assertRaises(TypeError):
            self.provider.verify(None, extraction, _empty_coding())

    def test_raises_type_error_for_int_note(self):
        extraction = _make_extraction_result([])
        with self.assertRaises(TypeError):
            self.provider.verify(42, extraction, _empty_coding())

    # --- valid items pass ---

    def test_valid_item_outcome_is_supported(self):
        note = "Patient has hypertension."
        item = _make_valid_item(note, "hypertension", "diagnosis", "active")
        extraction = _make_extraction_result([item])
        result = self.provider.verify(note, extraction, _empty_coding())
        self.assertEqual(result["item_checks"][0]["outcome"], "supported")

    def test_valid_item_does_not_trigger_needs_review(self):
        note = "Patient has hypertension."
        item = _make_valid_item(note, "hypertension", "diagnosis", "active")
        extraction = _make_extraction_result([item])
        result = self.provider.verify(note, extraction, _empty_coding())
        self.assertFalse(result["needs_review"])

    def test_empty_extraction_passes(self):
        note = "Patient has no complaints."
        extraction = _make_extraction_result([])
        result = self.provider.verify(note, extraction, _empty_coding())
        self.assertFalse(result["needs_review"])
        self.assertEqual(result["item_checks"], [])

    def test_multiple_valid_items_all_supported(self):
        note = "Patient has hypertension and takes metformin daily."
        items = [
            _make_valid_item(note, "hypertension", "diagnosis", "active"),
            _make_valid_item(note, "metformin", "medication", "current"),
        ]
        extraction = _make_extraction_result(items)
        result = self.provider.verify(note, extraction, _empty_coding())
        for check in result["item_checks"]:
            self.assertEqual(
                check["outcome"], "supported",
                f"Expected outcome=supported: {check}"
            )

    def test_valid_item_has_evidence_reference(self):
        note = "Patient has hypertension."
        item = _make_valid_item(note, "hypertension", "diagnosis", "active")
        extraction = _make_extraction_result([item])
        result = self.provider.verify(note, extraction, _empty_coding())
        check = result["item_checks"][0]
        self.assertTrue(len(check["evidence"]) > 0, "Supported item must have evidence references.")

    def test_valid_item_evidence_matches_note_span(self):
        note = "Patient has hypertension."
        item = _make_valid_item(note, "hypertension", "diagnosis", "active")
        extraction = _make_extraction_result([item])
        result = self.provider.verify(note, extraction, _empty_coding())
        check = result["item_checks"][0]
        for ev in check["evidence"]:
            self.assertEqual(
                note[ev["start_offset"]:ev["end_offset"]],
                ev["evidence_text"],
            )

    # --- offset mismatch triggers unsupported outcome ---

    def test_wrong_offset_is_unsupported(self):
        note = "Patient has hypertension."
        # character 0 is 'P', not 'hypertension'
        bad_item = _make_invalid_extraction([{
            "category": "diagnosis",
            "entity": "hypertension",
            "evidence_text": "hypertension",
            "start_offset": 0,
            "end_offset": 12,
            "status": "active",
            "attributes": {},
        }])
        result = self.provider.verify(note, bad_item, _empty_coding())
        self.assertNotEqual(result["item_checks"][0]["outcome"], "supported")
        self.assertTrue(result["needs_review"])

    def test_negative_start_offset_is_unsupported(self):
        note = "Patient has hypertension."
        bad_item = _make_invalid_extraction([{
            "category": "diagnosis",
            "entity": "hypertension",
            "evidence_text": "hypertension",
            "start_offset": -1,
            "end_offset": 12,
            "status": "active",
            "attributes": {},
        }])
        result = self.provider.verify(note, bad_item, _empty_coding())
        self.assertNotEqual(result["item_checks"][0]["outcome"], "supported")

    def test_end_beyond_note_length_is_unsupported(self):
        note = "Short."
        bad_item = _make_invalid_extraction([{
            "category": "diagnosis",
            "entity": "Short",
            "evidence_text": "Short",
            "start_offset": 0,
            "end_offset": 9999,
            "status": "active",
            "attributes": {},
        }])
        result = self.provider.verify(note, bad_item, _empty_coding())
        self.assertNotEqual(result["item_checks"][0]["outcome"], "supported")

    # --- entity not grounded in evidence ---

    def test_entity_not_in_evidence_is_unsupported(self):
        note = "Patient has hypertension."
        idx = note.lower().find("hypertension")
        bad_item = _make_invalid_extraction([{
            "category": "diagnosis",
            "entity": "diabetes",        # entity not in evidence_text
            "evidence_text": note[idx: idx + len("hypertension")],
            "start_offset": idx,
            "end_offset": idx + len("hypertension"),
            "status": "active",
            "attributes": {},
        }])
        result = self.provider.verify(note, bad_item, _empty_coding())
        self.assertNotEqual(result["item_checks"][0]["outcome"], "supported")
        self.assertTrue(result["needs_review"])

    # --- result schema ---

    def test_result_has_item_checks(self):
        note = "Patient has asthma."
        result = self.provider.verify(note, _make_extraction_result([]), _empty_coding())
        self.assertIn("item_checks", result)

    def test_result_has_needs_review(self):
        note = "Patient has asthma."
        result = self.provider.verify(note, _make_extraction_result([]), _empty_coding())
        self.assertIn("needs_review", result)

    def test_result_has_review_reasons(self):
        note = "Patient has asthma."
        result = self.provider.verify(note, _make_extraction_result([]), _empty_coding())
        self.assertIn("review_reasons", result)


    def test_omission_detection_detects_missing_term(self):
        """Verification should report a missing term that appears in the note but is not extracted."""
        note = "Patient suffers from asthma."
        # No items extracted
        extraction = _make_extraction_result([])
        result = self.provider.verify(note, extraction, _empty_coding())
        # Expect at least one omission (asthma)
        self.assertTrue(any('asthma' == om['entity'].lower() or 'asthma' == om['evidence']['evidence_text'].lower() for om in result['potential_omissions']))
        self.assertTrue(result['needs_review'])
        self.assertIn('Potential omissions detected.', result['review_reasons'])

    def test_omission_detection_avoids_partial_word(self):
        """Verification should not flag an omission when the term appears only as part of a larger word."""
        note = "The patient is asthmatic and reports shortness of breath."
        extraction = _make_extraction_result([])
        result = self.provider.verify(note, extraction, _empty_coding())
        # No omission for 'asthma' should be reported
        self.assertFalse(any('asthma' == om['entity'].lower() or 'asthma' == om['evidence']['evidence_text'].lower() for om in result['potential_omissions']))
        if result['needs_review']:
            self.assertTrue(all('asthma' != om['entity'].lower() and 'asthma' != om['evidence']['evidence_text'].lower() for om in result['potential_omissions']))

        note = "Patient has asthma."
        result = self.provider.verify(note, _make_extraction_result([]), _empty_coding())
        self.assertIn("potential_omissions", result)

    def test_needs_review_is_bool(self):
        note = "Patient has asthma."
        result = self.provider.verify(note, _make_extraction_result([]), _empty_coding())
        self.assertIsInstance(result["needs_review"], bool)

    def test_item_check_has_outcome_key(self):
        note = "Patient has hypertension."
        item = _make_valid_item(note, "hypertension", "diagnosis", "active")
        extraction = _make_extraction_result([item])
        result = self.provider.verify(note, extraction, _empty_coding())
        self.assertIn("outcome", result["item_checks"][0])

    def test_item_check_has_status_check_key(self):
        note = "Patient has hypertension."
        item = _make_valid_item(note, "hypertension", "diagnosis", "active")
        extraction = _make_extraction_result([item])
        result = self.provider.verify(note, extraction, _empty_coding())
        self.assertIn("status_check", result["item_checks"][0])

    def test_item_check_has_reason_key(self):
        note = "Patient has hypertension."
        item = _make_valid_item(note, "hypertension", "diagnosis", "active")
        extraction = _make_extraction_result([item])
        result = self.provider.verify(note, extraction, _empty_coding())
        self.assertIn("reason", result["item_checks"][0])

    def test_diagnosis_item_check_status_check_is_not_applicable(self):
        # Diagnoses should have status_check set (not 'not_applicable')
        note = "Patient has hypertension."
        item = _make_valid_item(note, "hypertension", "diagnosis", "active")
        extraction = _make_extraction_result([item])
        result = self.provider.verify(note, extraction, _empty_coding())
        self.assertNotEqual(result["item_checks"][0]["status_check"], "not_applicable")

    def test_procedure_item_check_status_check_is_not_applicable(self):
        # Procedures should have status_check='not_applicable'
        note = "Patient underwent colonoscopy for screening."
        item = _make_valid_item(note, "colonoscopy", "procedure", None)
        extraction = _make_extraction_result([item])
        result = self.provider.verify(note, extraction, _empty_coding())
        self.assertEqual(result["item_checks"][0]["status_check"], "not_applicable")
