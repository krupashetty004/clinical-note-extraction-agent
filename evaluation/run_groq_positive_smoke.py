"""Explicit positive-case Groq smoke test using fixed synthetic text.

This script makes at most two API requests. It never reads patient records,
prints raw provider responses, or claims clinical performance.
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
from dashboard.extraction.service import (
    ExtractionOutputError,
    validate_extraction_output,
)
from dashboard.extraction.verification import (
    VerificationOutputError,
    validate_verification_output,
)


SYNTHETIC_NOTE = (
    "Assessment: hypertension. Current medication: lisinopril."
)

EXPECTED_FINDINGS = (
    {
        "category": "diagnosis",
        "entity": "hypertension",
        "status": "active",
    },
    {
        "category": "medication",
        "entity": "lisinopril",
        "status": "current",
    },
)


def _normalize(value: object) -> str:
    """Normalize enum/string values for deterministic comparisons."""
    value = getattr(value, "value", value)
    return " ".join(str(value).casefold().split())


def assess_expected_findings(extraction, verification) -> dict[str, object]:
    """Check expected entities and the verifier's corresponding decisions.

    This checks the reported model outputs; it does not independently prove
    clinical correctness or semantic evidence support.
    """
    checks_by_index = {
        check.item_index: check
        for check in verification.item_checks
    }

    details: list[dict[str, object]] = []

    for expected in EXPECTED_FINDINGS:
        matching_index = None

        for index, item in enumerate(extraction.items):
            if (
                _normalize(item.category) == expected["category"]
                and _normalize(item.entity) == expected["entity"]
                and _normalize(item.status) == expected["status"]
                and expected["entity"] in _normalize(item.evidence_text)
            ):
                matching_index = index
                break

        check = (
            checks_by_index.get(matching_index)
            if matching_index is not None
            else None
        )

        verifier_supported = (
            check is not None
            and _normalize(check.outcome) == "supported"
            and _normalize(check.status_check) == "correct"
        )

        details.append(
            {
                "category": expected["category"],
                "expected_entity": expected["entity"],
                "expected_status": expected["status"],
                "extracted": matching_index is not None,
                "verification_supported": verifier_supported,
            }
        )

    all_extracted = all(item["extracted"] for item in details)
    all_verified = all(
        item["verification_supported"] for item in details
    )
    review_required = bool(verification.needs_review)

    return {
        "ok": all_extracted and all_verified and not review_required,
        "expected_findings_found": all_extracted,
        "expected_findings_verified": all_verified,
        "verification_requires_review": review_required,
        "expected_findings": details,
    }



_SAFE_SCHEMA_FIELDS = {
    "items", "needs_review", "review_reasons",
    "category", "entity", "status", "evidence_text",
    "start_offset", "end_offset", "attributes",
}


_SAFE_SCHEMA_ERROR_TYPES = {
    "missing", "extra_forbidden", "literal_error",
    "int_type", "int_parsing", "bool_type",
    "string_type", "string_too_short", "list_type",
    "dict_type", "greater_than", "greater_than_equal",
    "model_type", "value_error", "string_pattern_mismatch",
}


def safe_schema_issues(exc: BaseException) -> list[dict[str, str]]:
    """Return bounded schema paths and error types, never raw input values."""
    cause = exc.__cause__
    errors_method = getattr(cause, "errors", None)

    if not callable(errors_method):
        return []

    try:
        errors = errors_method(
            include_input=False,
            include_context=False,
            include_url=False,
        )
    except Exception:
        return []

    safe_issues = []

    for issue in errors[:8]:
        raw_location = issue.get("loc", ())
        parts = []

        if isinstance(raw_location, (tuple, list)):
            for part in raw_location:
                if isinstance(part, int) and not isinstance(part, bool):
                    parts.append(str(part) if 0 <= part <= 1000 else "<index>")
                elif isinstance(part, str):
                    parts.append(
                        part if part in _SAFE_SCHEMA_FIELDS else "<unknown_field>"
                    )
                else:
                    parts.append("<other>")

        raw_type = issue.get("type")
        safe_type = (
            raw_type
            if isinstance(raw_type, str)
            and raw_type in _SAFE_SCHEMA_ERROR_TYPES
            else "other_validation_error"
        )

        safe_issues.append({
            "path": ".".join(parts) if parts else "<root>",
            "type": safe_type,
        })

    return safe_issues




def safe_error_code(exc: BaseException) -> str | None:
    """Return a known validation code without exposing exception contents."""
    if isinstance(exc, ExtractionOutputError):
        allowed = {
            "schema_validation_failed",
            "evidence_validation_failed",
        }
        return (
            exc.code
            if exc.code in allowed
            else "extraction_validation_failed"
        )

    if isinstance(exc, VerificationOutputError):
        allowed = {
            "input_extraction_invalid",
            "verification_schema_failed",
            "verification_coverage_failed",
            "verification_status_check_invalid",
            "verification_evidence_failed",
        }
        return (
            exc.code
            if exc.code in allowed
            else "verification_validation_failed"
        )

    return None

def safe_error_detail(exc: BaseException) -> str | None:
    """Return only allowlisted validation detail codes."""
    if isinstance(exc, ExtractionOutputError):
        allowed = {
            "evidence_offset_out_of_bounds",
            "evidence_text_offset_mismatch",
        }
    elif isinstance(exc, VerificationOutputError):
        allowed = {
            "required_evidence_missing",
            "evidence_offset_out_of_bounds",
            "evidence_text_offset_mismatch",
        }
    else:
        return None

    detail = getattr(exc, "detail_code", None)
    return detail if detail in allowed else None


def safe_failure_phase(
    exc: BaseException,
    current_phase: str,
) -> str:
    """Classify typed validation errors without exposing exception content."""
    if isinstance(exc, ExtractionOutputError):
        if exc.code == "evidence_validation_failed":
            return "evidence_offset_validation"
        if exc.code == "schema_validation_failed":
            return "extraction_schema_validation"
    elif isinstance(exc, VerificationOutputError):
        return "verification_validation"

    return current_phase



def main() -> int:
    model = getattr(settings, "GROQ_MODEL", "openai/gpt-oss-20b")

    # Check the safety/configuration gates before initializing a provider.
    if (
        not settings.DEBUG
        or not getattr(settings, "GROQ_PROVIDER_ENABLED", False)
    ):
        print(json.dumps({
            "ok": False,
            "reason": (
                "Provider disabled. A local DEBUG environment and explicit "
                "provider opt-in are required."
            ),
            "api_requests_started": 0,
        }, indent=2))
        return 2

    if not os.environ.get("GROQ_API_KEY", "").strip():
        print(json.dumps({
            "ok": False,
            "reason": "GROQ_API_KEY is not configured.",
            "api_requests_started": 0,
        }, indent=2))
        return 2

    api_requests_started = 0
    api_requests_completed = 0
    phase = "provider_initialization"

    try:
        extraction_provider = GroqExtractionProvider()
        verification_provider = GroqVerificationProvider()

        phase = "extraction_request"
        # Request 1: extraction.
        api_requests_started += 1
        extraction_payload = extraction_provider.extract(SYNTHETIC_NOTE)
        api_requests_completed += 1

        phase = "extraction_schema_validation"
        extraction = validate_extraction_output(
            extraction_payload,
            SYNTHETIC_NOTE,
        )
        phase = "evidence_offset_validation"
        validate_evidence_spans(extraction, SYNTHETIC_NOTE)

        phase = "verification_request"
        # Request 2: independent verification of the extraction.
        # Diagnosis coding is deliberately outside this smoke test.
        coding = DiagnosisCodingBatch(diagnoses=())

        api_requests_started += 1
        verification_payload = verification_provider.verify(
            SYNTHETIC_NOTE,
            extraction,
            coding,
        )
        api_requests_completed += 1

        phase = "verification_validation"
        verification = validate_verification_output(
            verification_payload,
            extraction,
            SYNTHETIC_NOTE,
        )

        phase = "expected_finding_assessment"
        assessment = assess_expected_findings(
            extraction,
            verification,
        )

    except Exception as exc:
        # Report only safe error classifications, never raw provider details.
        error_code = safe_error_code(exc)
        failure_phase = safe_failure_phase(exc, phase)

        print(json.dumps({
            "ok": False,
            "model": model,
            "input_kind": "fixed_synthetic_text_only",
            "api_requests_started": api_requests_started,
            "api_requests_completed": api_requests_completed,
            "failure_phase": failure_phase,
            "error_type": type(exc).__name__,
            "error_code": error_code,
            "error_detail": safe_error_detail(exc),
            "schema_issues": safe_schema_issues(exc) if error_code in {"schema_validation_failed", "verification_schema_failed"} else [],
            "reason": "Smoke test failed; sensitive details were suppressed.",
            "clinical_performance_claimed": False,
        }, indent=2))
        return 1

    report = {
        **assessment,
        "model": model,
        "input_kind": "fixed_synthetic_text_only",
        "api_requests_started": api_requests_started,
        "api_requests_completed": api_requests_completed,
        "extracted_item_count": len(extraction.items),
        "extraction_schema_validated": True,
        "evidence_offsets_validated": True,
        "verification_schema_validated": True,
        "verification_item_check_count": len(verification.item_checks),
        "clinical_performance_claimed": False,
        "limitations": [
            "One synthetic note is not a quality evaluation.",
            "Exact offsets do not prove semantic evidence support.",
            "The verifier's judgments are model outputs, not independent ground truth.",
            "This script does not evaluate ICD-10-CM coding accuracy.",
            "No patient database or patient records were accessed.",
        ],
    }

    print(json.dumps(report, indent=2))
    return 0 if assessment["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
