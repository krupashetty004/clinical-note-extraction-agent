"""Network-free unit tests for the Groq adapter contracts."""
from __future__ import annotations

import json
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

from dashboard.extraction.diagnosis_coding import DiagnosisCodingBatch
from dashboard.extraction.groq_provider import (
    GroqAnnotationProvider,
    GroqExtractionProvider,
    GroqProviderConfigurationError,
    GroqProviderError,
    GroqVerificationProvider,
)
from dashboard.extraction.schema import ExtractionResult


def fake_client(content: str) -> MagicMock:
    client = MagicMock()
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )
    return client


EMPTY_EXTRACTION = {
    "items": [],
    "needs_review": True,
    "review_reasons": ["Synthetic adapter test only; manual review required."],
}
EMPTY_VERIFICATION = {
    "item_checks": [],
    "potential_omissions": [],
    "needs_review": True,
    "review_reasons": ["Synthetic adapter test only; verification is simulated."],
}


class GroqProviderTests(SimpleTestCase):
    def test_extraction_provider_returns_json_object_and_uses_no_sdk_retries(self):
        client = fake_client(json.dumps(EMPTY_EXTRACTION))
        provider = GroqExtractionProvider(client=client, model="unit-test-model")
        note = "Synthetic note only. No clinical findings."

        result = provider.extract(note)

        self.assertEqual(result, EMPTY_EXTRACTION)
        kwargs = client.chat.completions.create.call_args.kwargs
        self.assertEqual(kwargs["model"], "unit-test-model")
        self.assertEqual(kwargs["response_format"], {"type": "json_object"})
        self.assertIn(note, kwargs["messages"][1]["content"])

    def test_annotation_provider_returns_json_and_exposes_model_provenance(self):
        expected = {
            "items": [],
            "expected_needs_review": True,
            "review_reasons": ["Synthetic adapter test only."],
        }
        client = fake_client(json.dumps(expected))
        provider = GroqAnnotationProvider(client=client, model="synthetic-test-model")

        result = provider.annotate("Synthetic note only.")

        self.assertEqual(result, expected)
        self.assertEqual(provider.model_id, "synthetic-test-model")
        kwargs = client.chat.completions.create.call_args.kwargs
        self.assertEqual(kwargs["model"], "synthetic-test-model")
        self.assertEqual(kwargs["response_format"], {"type": "json_object"})

    def test_gpt_oss_annotation_uses_strict_json_schema(self):
        expected = {"items": [], "expected_needs_review": True, "review_reasons": []}
        client = fake_client(json.dumps(expected))
        provider = GroqAnnotationProvider(client=client, model="openai/gpt-oss-20b")

        result = provider.annotate("Synthetic note only.")

        self.assertEqual(result["items"], [])
        response_format = client.chat.completions.create.call_args.kwargs["response_format"]
        self.assertEqual(response_format["type"], "json_schema")
        self.assertTrue(response_format["json_schema"]["strict"])
        self.assertFalse(response_format["json_schema"]["schema"]["additionalProperties"])

    def test_annotation_provider_computes_offsets_from_unique_exact_evidence(self):
        note = "Synthetic note: Penicillin allergy is documented in the chart."
        evidence = "Penicillin allergy is documented"
        payload = {
            "items": [{
                "category": "allergy",
                "entity": "Penicillin allergy",
                "status": None,
                "evidence_text": evidence,
                "attributes": {"dose": None, "context": "documented", "reaction": None},
                "icd10_code": None,
                "icd10_description": None,
            }],
            "expected_needs_review": False,
            "review_reasons": [],
        }
        provider = GroqAnnotationProvider(client=fake_client(json.dumps(payload)), model="openai/gpt-oss-20b")

        result = provider.annotate(note)
        item = result["items"][0]
        self.assertEqual(item["start_offset"], note.index(evidence))
        self.assertEqual(item["end_offset"], note.index(evidence) + len(evidence))
        self.assertEqual(item["offset_resolution"], "computed_from_unique_exact_evidence")
        self.assertEqual(item["attributes"], {"context": "documented"})

    def test_annotation_provider_rejects_ambiguous_evidence(self):
        note = "Synthetic note: pain improved, but pain returned."
        payload = {
            "items": [{
                "category": "allergy", "entity": "pain", "status": None,
                "evidence_text": "pain", "attributes": {},
                "icd10_code": None, "icd10_description": None,
            }],
            "expected_needs_review": True,
            "review_reasons": ["Repeated evidence phrase"],
        }
        provider = GroqAnnotationProvider(client=fake_client(json.dumps(payload)), model="openai/gpt-oss-20b")
        with self.assertRaisesRegex(ValueError, "ambiguous"):
            provider.annotate(note)

    def test_annotation_provider_rejects_blank_note_without_call(self):
        client = fake_client(json.dumps({"items": [], "expected_needs_review": True, "review_reasons": []}))
        provider = GroqAnnotationProvider(client=client, model="synthetic-test-model")
        with self.assertRaises(ValueError):
            provider.annotate("   ")
        client.chat.completions.create.assert_not_called()

    def test_verification_provider_serializes_validated_inputs(self):
        client = fake_client(json.dumps(EMPTY_VERIFICATION))
        provider = GroqVerificationProvider(client=client, model="unit-test-model")
        extraction = ExtractionResult.model_validate(EMPTY_EXTRACTION)

        result = provider.verify(
            "Synthetic note only.", extraction, DiagnosisCodingBatch(diagnoses=())
        )

        self.assertEqual(result, EMPTY_VERIFICATION)
        user_message = client.chat.completions.create.call_args.kwargs["messages"][1]["content"]
        self.assertIn('"coding_candidates"', user_message)
        self.assertIn('"original_note"', user_message)
        self.assertEqual(
            client.chat.completions.create.call_args.kwargs["response_format"],
            {"type": "json_object"},
        )

    def test_gpt_oss_verification_uses_strict_json_schema(self):
        client = fake_client(json.dumps(EMPTY_VERIFICATION))
        provider = GroqVerificationProvider(
            client=client,
            model="openai/gpt-oss-20b",
        )
        extraction = ExtractionResult.model_validate(EMPTY_EXTRACTION)

        result = provider.verify(
            "Synthetic note only.",
            extraction,
            DiagnosisCodingBatch(diagnoses=()),
        )

        self.assertEqual(result, EMPTY_VERIFICATION)
        response_format = client.chat.completions.create.call_args.kwargs["response_format"]
        self.assertEqual(response_format["type"], "json_schema")
        self.assertTrue(response_format["json_schema"]["strict"])
        schema = response_format["json_schema"]["schema"]
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(
            set(schema["required"]),
            {"item_checks", "potential_omissions", "needs_review", "review_reasons"},
        )

    def test_invalid_json_is_rejected_without_echoing_provider_content(self):
        secret_marker = "SYNTHETIC_PRIVATE_RESPONSE_MARKER"
        provider = GroqExtractionProvider(client=fake_client(secret_marker))

        with self.assertRaises(GroqProviderError) as raised:
            provider.extract("Synthetic note only.")

        self.assertNotIn(secret_marker, str(raised.exception))
        self.assertEqual(raised.exception.code, "provider_invalid_json")

    def test_request_error_is_sanitized(self):
        client = MagicMock()
        client.chat.completions.create.side_effect = RuntimeError(
            "SYNTHETIC_PRIVATE_REQUEST_DETAIL"
        )
        provider = GroqExtractionProvider(client=client)

        with self.assertRaises(GroqProviderError) as raised:
            provider.extract("Synthetic note only.")

        self.assertNotIn("SYNTHETIC_PRIVATE_REQUEST_DETAIL", str(raised.exception))

    def test_rate_limit_status_is_classified_without_provider_details(self):
        class SyntheticRateLimitError(RuntimeError):
            status_code = 429

        client = MagicMock()
        client.chat.completions.create.side_effect = SyntheticRateLimitError(
            "SYNTHETIC_PRIVATE_RATE_LIMIT_DETAIL"
        )
        provider = GroqExtractionProvider(client=client)

        with self.assertRaises(GroqProviderError) as raised:
            provider.extract("Synthetic note only.")

        self.assertEqual(raised.exception.code, "provider_rate_limited")
        self.assertNotIn("SYNTHETIC_PRIVATE_RATE_LIMIT_DETAIL", str(raised.exception))

    def test_auth_status_is_classified_without_provider_details(self):
        class SyntheticAuthError(RuntimeError):
            status_code = 401

        client = MagicMock()
        client.chat.completions.create.side_effect = SyntheticAuthError(
            "SYNTHETIC_PRIVATE_AUTH_DETAIL"
        )
        provider = GroqExtractionProvider(client=client)

        with self.assertRaises(GroqProviderError) as raised:
            provider.extract("Synthetic note only.")

        self.assertEqual(raised.exception.code, "provider_authentication_failed")
        self.assertNotIn("SYNTHETIC_PRIVATE_AUTH_DETAIL", str(raised.exception))

    def test_timeout_is_classified_without_provider_details(self):
        client = MagicMock()
        client.chat.completions.create.side_effect = TimeoutError(
            "SYNTHETIC_PRIVATE_TIMEOUT_DETAIL"
        )
        provider = GroqExtractionProvider(client=client)

        with self.assertRaises(GroqProviderError) as raised:
            provider.extract("Synthetic note only.")

        self.assertEqual(raised.exception.code, "provider_timeout")
        self.assertNotIn(
            "SYNTHETIC_PRIVATE_TIMEOUT_DETAIL",
            str(raised.exception),
        )

    @override_settings(GROQ_PROVIDER_ENABLED=False)
    def test_provider_creation_is_blocked_when_disabled(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": "test-only-not-a-real-key"}):
            with self.assertRaises(GroqProviderConfigurationError):
                GroqExtractionProvider()

    @override_settings(GROQ_PROVIDER_ENABLED=True)
    def test_provider_creation_requires_api_key(self):
        with patch.dict(os.environ, {"GROQ_API_KEY": ""}):
            with self.assertRaises(GroqProviderConfigurationError):
                GroqExtractionProvider()

    def test_blank_input_is_rejected_before_call(self):
        client = fake_client(json.dumps(EMPTY_EXTRACTION))
        provider = GroqExtractionProvider(client=client)
        with self.assertRaises(ValueError):
            provider.extract("   ")
        client.chat.completions.create.assert_not_called()
