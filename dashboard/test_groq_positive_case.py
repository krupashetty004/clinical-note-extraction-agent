"""Positive-case tests for the Groq adapter using mocked responses.

These tests make no network requests and use synthetic text only.
"""
from __future__ import annotations

import copy
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from django.test import SimpleTestCase

from dashboard.extraction.diagnosis_coding import DiagnosisCodingBatch
from dashboard.extraction.groq_provider import (
    GroqExtractionProvider,
    GroqVerificationProvider,
)
from dashboard.extraction.schema import validate_evidence_spans
from dashboard.extraction.service import (
    ExtractionOutputError,
    validate_extraction_output,
)
from dashboard.extraction.verification import validate_verification_output


SYNTHETIC_NOTE = (
    "Assessment: hypertension. Current medication: lisinopril."
)


def fake_client(content: str) -> MagicMock:
    """Return a mocked Groq client with a predetermined JSON response."""
    client = MagicMock()
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content)
            )
        ]
    )
    return client


def make_item(
    note: str,
    *,
    category: str,
    entity: str,
    status: str,
    evidence: str,
) -> dict:
    """Build an extraction item with offsets derived from the source note."""
    start = note.index(evidence)

    return {
        "category": category,
        "entity": entity,
        "status": status,
        "evidence_text": evidence,
        "start_offset": start,
        "end_offset": start + len(evidence),
        "attributes": {},
    }


class GroqPositiveCaseTests(SimpleTestCase):
    def setUp(self) -> None:
        self.note = SYNTHETIC_NOTE

        self.extraction_payload = {
            "items": [
                make_item(
                    self.note,
                    category="diagnosis",
                    entity="hypertension",
                    status="active",
                    evidence="hypertension",
                ),
                make_item(
                    self.note,
                    category="medication",
                    entity="lisinopril",
                    status="current",
                    evidence="lisinopril",
                ),
            ],
            "needs_review": False,
            "review_reasons": [],
        }

        self.verification_payload = {
            "item_checks": [
                {
                    "item_index": index,
                    "outcome": "supported",
                    "status_check": "correct",
                    "reason": (
                        "The cited synthetic note supports this item."
                    ),
                    "evidence": [
                        {
                            "evidence_text": item["evidence_text"],
                            "start_offset": item["start_offset"],
                            "end_offset": item["end_offset"],
                        }
                    ],
                }
                for index, item in enumerate(
                    self.extraction_payload["items"]
                )
            ],
            "potential_omissions": [],
            "needs_review": False,
            "review_reasons": [],
        }

    def test_positive_extraction_passes_existing_validation(self):
        client = fake_client(json.dumps(self.extraction_payload))
        provider = GroqExtractionProvider(
            client=client,
            model="unit-test-model",
        )

        extraction_payload = provider.extract(self.note)
        extraction = validate_extraction_output(
            extraction_payload,
            self.note,
        )

        self.assertEqual(
            [item.entity for item in extraction.items],
            ["hypertension", "lisinopril"],
        )
        self.assertEqual(
            [item.category for item in extraction.items],
            ["diagnosis", "medication"],
        )
        self.assertEqual(
            [item.status for item in extraction.items],
            ["active", "current"],
        )

        validate_evidence_spans(extraction, self.note)

        for item in extraction.items:
            self.assertEqual(
                self.note[item.start_offset:item.end_offset],
                item.evidence_text,
            )

        request = client.chat.completions.create.call_args.kwargs
        self.assertEqual(request["model"], "unit-test-model")
        self.assertEqual(
            request["response_format"],
            {"type": "json_object"},
        )
        client.chat.completions.create.assert_called_once()

    def test_positive_verification_passes_existing_validation(self):
        extraction = validate_extraction_output(
            self.extraction_payload,
            self.note,
        )

        client = fake_client(json.dumps(self.verification_payload))
        provider = GroqVerificationProvider(
            client=client,
            model="unit-test-model",
        )

        verification_payload = provider.verify(
            self.note,
            extraction,
            DiagnosisCodingBatch(diagnoses=()),
        )

        verification = validate_verification_output(
            verification_payload,
            extraction,
            self.note,
        )

        self.assertEqual(len(verification.item_checks), 2)
        self.assertEqual(
            [check.outcome for check in verification.item_checks],
            ["supported", "supported"],
        )
        self.assertEqual(
            [check.status_check for check in verification.item_checks],
            ["correct", "correct"],
        )
        self.assertFalse(verification.needs_review)
        client.chat.completions.create.assert_called_once()

    def test_mismatched_evidence_is_rejected(self):
        invalid_payload = copy.deepcopy(self.extraction_payload)

        # Preserve the hypertension offsets but replace its evidence text.
        invalid_payload["items"][0]["evidence_text"] = "lisinopril"

        with self.assertRaises(ExtractionOutputError) as raised:
            validate_extraction_output(invalid_payload, self.note)

        self.assertEqual(
            raised.exception.code,
            "evidence_validation_failed",
        )