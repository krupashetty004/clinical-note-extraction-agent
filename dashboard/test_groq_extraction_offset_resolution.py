"""Regression tests for safe local evidence-offset resolution."""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

from django.test import SimpleTestCase

from dashboard.extraction.groq_provider import GroqExtractionProvider


def fake_client(content: str) -> MagicMock:
    client = MagicMock()
    client.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))]
    )
    return client


class GroqExtractionOffsetTests(SimpleTestCase):
    def test_offsets_are_recomputed_from_unique_exact_evidence(self):
        note = "Synthetic note: hypertension is documented."
        payload = {
            "items": [{
                "category": "diagnosis",
                "entity": "hypertension",
                "status": "active",
                "evidence_text": "hypertension",
                "attributes": {},
                "start_offset": 999,
                "end_offset": 1000,
            }],
            "needs_review": False,
            "review_reasons": [],
        }
        provider = GroqExtractionProvider(client=fake_client(json.dumps(payload)))

        result = provider.extract(note)

        start = note.index("hypertension")
        self.assertEqual(result["items"][0]["start_offset"], start)
        self.assertEqual(result["items"][0]["end_offset"], start + len("hypertension"))

    def test_ambiguous_evidence_is_omitted_and_requires_review(self):
        note = "Synthetic note: headache improved; headache returned."
        payload = {
            "items": [{
                "category": "diagnosis",
                "entity": "headache",
                "status": "active",
                "evidence_text": "headache",
                "attributes": {},
            }],
            "needs_review": False,
            "review_reasons": [],
        }
        provider = GroqExtractionProvider(client=fake_client(json.dumps(payload)))

        result = provider.extract(note)

        self.assertEqual(result["items"], [])
        self.assertTrue(result["needs_review"])
        self.assertTrue(result["review_reasons"])

    def test_missing_evidence_is_omitted_and_requires_review(self):
        note = "Synthetic note: fever is present."
        payload = {
            "items": [{
                "category": "diagnosis",
                "entity": "pneumonia",
                "status": "active",
                "evidence_text": "pneumonia",
                "attributes": {},
            }],
            "needs_review": False,
            "review_reasons": [],
        }
        provider = GroqExtractionProvider(client=fake_client(json.dumps(payload)))

        result = provider.extract(note)

        self.assertEqual(result["items"], [])
        self.assertTrue(result["needs_review"])
        self.assertTrue(result["review_reasons"])
