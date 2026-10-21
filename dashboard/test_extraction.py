"""Synthetic tests for extraction schemas and evidence validation."""

from django.test import SimpleTestCase
from pydantic import ValidationError

from dashboard.extraction.schema import (
    ExtractionResult,
    ExtractedItem,
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