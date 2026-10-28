"""Explicit API smoke test using one fixed synthetic note only.

Invoke only after setting GROQ_API_KEY and explicitly enabling the provider
for a local DEBUG environment. The command never reads a database or patient
records, and it does not print the model's raw response.
"""
from __future__ import annotations

import json
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

import django
django.setup()

from django.conf import settings

from dashboard.extraction.diagnosis_coding import DiagnosisCodingBatch
from dashboard.extraction.groq_provider import (
    GroqExtractionProvider,
    GroqVerificationProvider,
)
from dashboard.extraction.schema import validate_evidence_spans
from dashboard.extraction.service import validate_extraction_output
from dashboard.extraction.verification import validate_verification_output

SYNTHETIC_NOTE = (
    "Synthetic API smoke-test text only. No clinical findings are provided. "
    "Do not infer or invent a diagnosis, medication, procedure, allergy, or vital sign."
)


def main() -> int:
    if not settings.DEBUG or not getattr(settings, "GROQ_PROVIDER_ENABLED", False):
        print(json.dumps({
            "ok": False,
            "reason": "Provider disabled. Use a local DEBUG environment and explicitly enable the synthetic API smoke test.",
        }, indent=2))
        return 2

    if not os.environ.get("GROQ_API_KEY", "").strip():
        print(json.dumps({"ok": False, "reason": "GROQ_API_KEY is not configured."}, indent=2))
        return 2

    try:
        extraction_payload = GroqExtractionProvider().extract(SYNTHETIC_NOTE)
        extraction = validate_extraction_output(extraction_payload, SYNTHETIC_NOTE)
        validate_evidence_spans(extraction, SYNTHETIC_NOTE)
        coding = DiagnosisCodingBatch(diagnoses=())
        verification_payload = GroqVerificationProvider().verify(
            SYNTHETIC_NOTE, extraction, coding
        )
        verification = validate_verification_output(
            verification_payload, extraction, SYNTHETIC_NOTE
        )
    except Exception as exc:
        # Never print the exception message: SDK errors may include request data.
        print(json.dumps({
            "ok": False,
            "error_type": type(exc).__name__,
            "reason": "Synthetic API smoke test failed; raw provider details were suppressed.",
        }, indent=2))
        return 1

    report = {
        "ok": True,
        "model": getattr(settings, "GROQ_MODEL", "openai/gpt-oss-20b"),
        "input_kind": "fixed_synthetic_text_only",
        "network_call_made": True,
        "extraction_schema_validated": True,
        "evidence_offsets_validated": True,
        "verification_schema_validated": True,
        "extracted_item_count": len(extraction.items),
        "extraction_requires_review": extraction.needs_review,
        "verification_requires_review": verification.needs_review,
        "clinical_performance_claimed": False,
        "limitations": [
            "One synthetic smoke test is not a quality evaluation.",
            "Passing schema and offset validation does not prove clinical correctness.",
            "No patient database or patient records were accessed.",
        ],
    }
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
