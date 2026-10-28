"""Synthetic tests for extraction schemas and evidence validation."""

from django.test import SimpleTestCase
from pydantic import ValidationError

from dashboard.extraction.schema import (
    ExtractionResult,
    ExtractedItem,
    validate_item_status_context,
    validate_evidence_spans,
)

from dashboard.extraction.pipeline import (
    ExtractionProviderError,
    run_extraction,
)

from dashboard.extraction.service import (
    ExtractionOutputError,
    validate_extraction_output,
)


class ExtractionSchemaTests(SimpleTestCase):
    def make_item(
        self,
        note: str,
        evidence: str,
        **overrides,
    ) -> ExtractedItem:
        """Build a valid synthetic item unless fields are overridden."""
        start = note.find(evidence)

        if start < 0:
            raise ValueError("Test evidence is not present in the note.")

        data = {
            "category": "diagnosis",
            "entity": "headache",
            "status": "active",
            "evidence_text": evidence,
            "start_offset": start,
            "end_offset": start + len(evidence),
            "attributes": {},
        }
        data.update(overrides)

        return ExtractedItem.model_validate(data)

    def make_result(self, item: ExtractedItem) -> ExtractionResult:
        return ExtractionResult.model_validate(
            {
                "items": [item],
                "needs_review": False,
                "review_reasons": [],
            }
        )

    def test_accepts_valid_extraction_and_evidence(self):
        note = "The patient reports a mild headache today."
        item = self.make_item(note, "mild headache")
        result = self.make_result(item)

        validate_evidence_spans(result, note)

        self.assertEqual(item.category, "diagnosis")
        self.assertEqual(
            note[item.start_offset:item.end_offset],
            "mild headache",
        )

    def test_rejects_unknown_entity_category(self):
        note = "The patient reports a headache."
        start = note.index("headache")

        with self.assertRaises(ValidationError):
            self.make_item(
                note,
                "headache",
                category="unsupported_category",
                start_offset=start,
                end_offset=start + len("headache"),
            )

    def test_rejects_unknown_mention_status(self):
        note = "The patient reports a headache."

        with self.assertRaises(ValidationError):
            self.make_item(note, "headache", status="maybe")

    def test_rejects_negative_start_offset(self):
        note = "The patient reports a headache."

        with self.assertRaises(ValidationError):
            self.make_item(
                note,
                "headache",
                start_offset=-1,
            )

    def test_rejects_end_offset_not_after_start(self):
        note = "The patient reports a headache."
        start = note.index("headache")

        with self.assertRaises(ValidationError):
            self.make_item(
                note,
                "headache",
                start_offset=start,
                end_offset=start,
            )

    def test_rejects_evidence_beyond_note_length(self):
        note = "Headache reported."
        item = self.make_item(
            note,
            "Headache",
            end_offset=len(note) + 1,
        )
        result = self.make_result(item)

        with self.assertRaisesRegex(
            ValueError,
            "end_offset exceeds",
        ):
            validate_evidence_spans(result, note)

    def test_rejects_evidence_that_does_not_match_offsets(self):
        note = "The patient reports a headache."
        item = self.make_item(
            note,
            "headache",
            evidence_text="fever",
        )
        result = self.make_result(item)

        with self.assertRaisesRegex(
            ValueError,
            "does not match",
        ):
            validate_evidence_spans(result, note)

    def test_uses_correct_occurrence_of_repeated_phrase(self):
        note = (
            "The term headache appears historically. "
            "The term headache is reported today."
        )

        first_start = note.index("headache")
        second_start = note.rindex("headache")

        item = ExtractedItem(
            category="diagnosis",
            entity="headache",
            status="active",
            evidence_text="headache",
            start_offset=second_start,
            end_offset=second_start + len("headache"),
        )
        result = self.make_result(item)

        validate_evidence_spans(result, note)

        self.assertGreater(second_start, first_start)
        self.assertEqual(
            note[item.start_offset:item.end_offset],
            "headache",
        )

    def test_rejects_extra_unexpected_schema_fields(self):
        note = "The patient reports a headache."
        start = note.index("headache")

        data = {
            "category": "diagnosis",
            "entity": "headache",
            "status": "active",
            "evidence_text": "headache",
            "start_offset": start,
            "end_offset": start + len("headache"),
            "unexpected_field": "not allowed",
        }

        with self.assertRaises(ValidationError):
            ExtractedItem.model_validate(data)

    def test_allows_empty_result_for_a_note_with_no_findings(self):
        result = ExtractionResult.model_validate(
            {
                "items": [],
                "needs_review": False,
                "review_reasons": [],
            }
        )

        validate_evidence_spans(result, "No supported mentions.")
        self.assertEqual(result.items, [])

    def test_validates_all_sow_entity_categories_against_evidence(self):
        note = (
            "Assessment: diabetes. "
            "Medication: metformin. "
            "Plan: appendectomy. "
            "Allergy: penicillin allergy. "
            "Vitals: temperature 38 C."
        )
        values = [
            ("diagnosis", "diabetes", "active", "diabetes"),
            ("medication", "metformin", "current", "metformin"),
            ("procedure", "appendectomy", None, "appendectomy"),
            ("allergy", "penicillin allergy", None, "penicillin allergy"),
            ("vital_sign", "temperature", None, "temperature 38 C"),
        ]
        items = []
        for category, entity, status, evidence in values:
            start = note.index(evidence)
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

        result = ExtractionResult.model_validate(
            {
                "items": items,
                "needs_review": False,
                "review_reasons": [],
            }
        )

        validate_evidence_spans(result, note)

    def test_rejects_fabricated_entity_with_valid_source_span(self):
        note = "Assessment: diabetes."
        item = self.make_item(
            note,
            "diabetes",
            entity="heart failure",
        )

        with self.assertRaisesRegex(ValueError, "does not contain"):
            validate_evidence_spans(self.make_result(item), note)

    def test_requires_all_entity_tokens_in_evidence(self):
        note = "Assessment: diabetes."
        item = self.make_item(
            note,
            "diabetes",
            entity="type 2 diabetes",
        )

        with self.assertRaisesRegex(ValueError, "does not contain"):
            validate_evidence_spans(self.make_result(item), note)

    def test_uses_unicode_code_point_offsets_and_entity_tokens(self):
        note = "😀 Assessment: café-au-lait macule."
        evidence = "café-au-lait macule"
        start = note.index(evidence)
        item = ExtractedItem(
            category="diagnosis",
            entity="café-au-lait macule",
            status="active",
            evidence_text=evidence,
            start_offset=start,
            end_offset=start + len(evidence),
        )

        validate_evidence_spans(self.make_result(item), note)
        self.assertEqual(
            note[item.start_offset:item.end_offset],
            evidence,
        )

    def test_rejects_fabricated_attribute_not_in_evidence(self):
        note = "Medication: metformin."
        start = note.index("metformin")
        item = ExtractedItem(
            category="medication",
            entity="metformin",
            status="current",
            evidence_text="metformin",
            start_offset=start,
            end_offset=start + len("metformin"),
            attributes={"dose": "500 mg"},
        )

        with self.assertRaisesRegex(ValueError, "attribute"):
            validate_evidence_spans(self.make_result(item), note)

    def test_detects_active_status_conflict_without_dropping_source_mention(self):
        cases = (
            "Assessment: no diabetes.",
            "Assessment: possible diabetes.",
            "History of diabetes.",
        )
        for note in cases:
            with self.subTest(note=note):
                item = self.make_item(
                    note,
                    "diabetes",
                    entity="diabetes",
                    status="active",
                )
                self.assertIsNotNone(
                    validate_item_status_context(item, note)
                )

    def test_detects_missing_context_for_historical_and_suspected_findings(self):
        for status in ("historical", "suspected", "ruled_out"):
            with self.subTest(status=status):
                note = "Assessment: diabetes."
                item = self.make_item(
                    note,
                    "diabetes",
                    entity="diabetes",
                    status=status,
                )
                self.assertIsNotNone(
                    validate_item_status_context(item, note)
                )

    def test_does_not_mix_semicolon_separated_historical_and_current_context(self):
        note = "History of diabetes; current diabetes."
        evidence = "current diabetes"
        item = self.make_item(
            note,
            evidence,
            entity="diabetes",
            status="active",
        )

        self.assertIsNone(validate_item_status_context(item, note))

class ExtractionServiceTests(SimpleTestCase):
    """Tests for the provider-independent extraction service."""

    def setUp(self):
        self.note = (
            "Synthetic note: patient reports mild headache today."
        )
        start = self.note.index("mild headache")

        self.valid_payload = {
            "items": [
                {
                    "category": "diagnosis",
                    "entity": "headache",
                    "status": "active",
                    "evidence_text": "mild headache",
                    "start_offset": start,
                    "end_offset": start + len("mild headache"),
                    "attributes": {},
                }
            ],
            "needs_review": False,
            "review_reasons": [],
        }

    def test_accepts_valid_payload_and_evidence(self):
        result = validate_extraction_output(
            self.valid_payload,
            self.note,
        )

        self.assertEqual(len(result.items), 1)
        self.assertEqual(
            result.items[0].evidence_text,
            "mild headache",
        )

    def test_rejects_invalid_schema(self):
        payload = {
            "items": [
                {
                    "category": "invalid_category",
                    "entity": "headache",
                    "status": "active",
                    "evidence_text": "mild headache",
                    "start_offset": 29,
                    "end_offset": 42,
                }
            ],
            "needs_review": False,
            "review_reasons": [],
        }

        with self.assertRaises(ExtractionOutputError) as context:
            validate_extraction_output(payload, self.note)

        self.assertEqual(
            context.exception.code,
            "schema_validation_failed",
        )

    def test_rejects_evidence_mismatch(self):
        payload = {
            **self.valid_payload,
            "items": [
                {
                    **self.valid_payload["items"][0],
                    "evidence_text": "fever",
                }
            ],
        }

        with self.assertRaises(ExtractionOutputError) as context:
            validate_extraction_output(payload, self.note)

        self.assertEqual(
            context.exception.code,
            "evidence_validation_failed",
        )

    def test_rejects_evidence_outside_note(self):
        payload = {
            **self.valid_payload,
            "items": [
                {
                    **self.valid_payload["items"][0],
                    "end_offset": len(self.note) + 10,
                }
            ],
        }

        with self.assertRaises(ExtractionOutputError) as context:
            validate_extraction_output(payload, self.note)

        self.assertEqual(
            context.exception.code,
            "evidence_validation_failed",
        )

    def test_rejects_non_string_original_note(self):
        with self.assertRaises(TypeError):
            validate_extraction_output(
                self.valid_payload,
                None,
            )

    def test_error_message_does_not_expose_note_text(self):
        payload = {
            **self.valid_payload,
            "items": [
                {
                    **self.valid_payload["items"][0],
                    "evidence_text": "unsupported phrase",
                }
            ],
        }

        with self.assertRaises(ExtractionOutputError) as context:
            validate_extraction_output(payload, self.note)

        self.assertNotIn(self.note, str(context.exception))
        self.assertNotIn(
            "unsupported phrase",
            str(context.exception),
        )

class ExtractionPipelineTests(SimpleTestCase):
    """Test provider invocation using synthetic output only."""

    class SyntheticProvider:
        def __init__(self, payload=None, error=None):
            self.payload = payload
            self.error = error
            self.called = False

        def extract(self, input_text):
            self.called = True

            if self.error is not None:
                raise self.error

            return self.payload

    def setUp(self):
        self.note = "Synthetic note: patient reports mild headache."
        start = self.note.index("mild headache")

        self.valid_payload = {
            "items": [
                {
                    "category": "diagnosis",
                    "entity": "headache",
                    "status": "active",
                    "evidence_text": "mild headache",
                    "start_offset": start,
                    "end_offset": start + len("mild headache"),
                    "attributes": {},
                }
            ],
            "needs_review": False,
            "review_reasons": [],
        }

    def test_valid_synthetic_output_passes_validation(self):
        provider = self.SyntheticProvider(
            payload=self.valid_payload
        )

        result = run_extraction(provider, self.note)

        self.assertTrue(provider.called)
        self.assertEqual(len(result.items), 1)
        self.assertEqual(
            result.items[0].evidence_text,
            "mild headache",
        )

    def test_invalid_evidence_is_rejected(self):
        invalid_payload = {
            **self.valid_payload,
            "items": [
                {
                    **self.valid_payload["items"][0],
                    "evidence_text": "fever",
                }
            ],
        }
        provider = self.SyntheticProvider(payload=invalid_payload)

        with self.assertRaises(ExtractionOutputError) as context:
            run_extraction(provider, self.note)

        self.assertTrue(provider.called)
        self.assertEqual(
            context.exception.code,
            "evidence_validation_failed",
        )

    def test_provider_failure_is_reported_without_details(self):
        provider = self.SyntheticProvider(
            error=RuntimeError("synthetic private failure details")
        )

        with self.assertRaises(ExtractionProviderError) as context:
            run_extraction(provider, self.note)

        self.assertTrue(provider.called)
        self.assertNotIn(
            "synthetic private failure details",
            str(context.exception),
        )

    def test_provider_timeout_has_a_safe_timeout_code(self):
        provider = self.SyntheticProvider(
            error=TimeoutError("synthetic timeout details")
        )

        with self.assertRaises(ExtractionProviderError) as context:
            run_extraction(provider, self.note)

        self.assertEqual(context.exception.code, "provider_timeout")
        self.assertNotIn("synthetic timeout details", str(context.exception))

    def test_non_string_note_is_rejected_before_provider_call(self):
        provider = self.SyntheticProvider(
            payload=self.valid_payload
        )

        with self.assertRaises(TypeError):
            run_extraction(provider, None)

        self.assertFalse(provider.called)

    def test_provider_output_with_invalid_schema_is_rejected(self):
        provider = self.SyntheticProvider(
            payload={"items": "not a list"}
        )

        with self.assertRaises(ExtractionOutputError) as context:
            run_extraction(provider, self.note)

        self.assertEqual(
            context.exception.code,
            "schema_validation_failed",
        )