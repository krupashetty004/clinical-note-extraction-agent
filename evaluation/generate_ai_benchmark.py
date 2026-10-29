"""Generate a separately labelled AI benchmark from local note records.

This command sends note text to the configured external Groq provider only when
explicitly enabled. Non-synthetic input is blocked unless the caller explicitly
attests that external processing has been approved. AI annotations are not
independent clinical ground truth.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dashboard.extraction.dataset import (
    ANNOTATION_QUEUE_PATH,
    DatasetRecord,
    REQUIRED_RECORD_FIELDS,
    load_jsonl,
)

ANNOTATION_VERSION = "mirai-ai-benchmark-v1"
ENTITY_CATEGORIES = {"diagnosis", "medication", "procedure", "allergy", "vital_sign"}
DIAGNOSIS_STATUSES = {"active", "historical", "ruled_out", "suspected"}
MEDICATION_STATUSES = {"current", "discontinued", "newly_prescribed"}
QUEUE_CATEGORY_MAP = {
    "diagnosis": "diagnoses",
    "procedure": "procedures",
    "medication": "medications",
    "allergy": "allergies",
    "vital_sign": "vital_signs",
}
DEFAULT_CASES_PATH = Path("evaluation/ai_benchmark_cases.jsonl")
DEFAULT_QUEUE_PATH = Path(
    "mirai_dataset_preparation_pack/data/external/mtsamples/annotations/ai_benchmark_annotations.jsonl"
)


def is_synthetic_record(record: DatasetRecord) -> bool:
    """Only known explicitly synthetic/local-test sources bypass the approval gate."""
    value = record.source_dataset.strip().casefold()
    return value.startswith(("synthetic:", "local:synthetic", "local:test"))


def validate_annotation_payload(note: str, payload: object) -> tuple[list[dict[str, Any]], bool, list[str]]:
    """Validate the model payload without attempting to repair unsupported spans."""
    if not isinstance(note, str) or not note.strip():
        raise ValueError("source note must be a non-empty string")
    if not isinstance(payload, dict):
        raise ValueError("annotation response must be a JSON object")

    raw_items = payload.get("items")
    needs_review = payload.get("expected_needs_review")
    reasons = payload.get("review_reasons")
    if not isinstance(raw_items, list):
        raise ValueError("items must be a list")
    if not isinstance(needs_review, bool):
        raise ValueError("expected_needs_review must be a boolean")
    if not isinstance(reasons, list) or any(not isinstance(value, str) for value in reasons):
        raise ValueError("review_reasons must be an array of strings")

    items: list[dict[str, Any]] = []
    for index, raw in enumerate(raw_items, start=1):
        label = f"item {index}"
        if not isinstance(raw, dict):
            raise ValueError(f"{label} must be an object")
        category = raw.get("category")
        entity = raw.get("entity")
        evidence = raw.get("evidence_text")
        start = raw.get("start_offset")
        end = raw.get("end_offset")
        status = raw.get("status")
        attributes = raw.get("attributes", {})

        if category not in ENTITY_CATEGORIES:
            raise ValueError(f"{label} has an unsupported category")
        if not isinstance(entity, str) or not entity.strip():
            raise ValueError(f"{label} requires a non-empty entity")
        if not isinstance(evidence, str) or not evidence:
            raise ValueError(f"{label} requires evidence_text")
        if (
            isinstance(start, bool) or not isinstance(start, int)
            or isinstance(end, bool) or not isinstance(end, int)
            or start < 0 or end <= start or end > len(note)
            or note[start:end] != evidence
        ):
            raise ValueError(f"{label} evidence offsets do not match the source note")
        if category == "diagnosis" and status not in DIAGNOSIS_STATUSES:
            raise ValueError(f"{label} has an invalid diagnosis status")
        if category == "medication" and status not in MEDICATION_STATUSES:
            raise ValueError(f"{label} has an invalid medication status")
        if category not in {"diagnosis", "medication"} and status is not None:
            raise ValueError(f"{label} status must be null for this category")
        if not isinstance(attributes, dict) or any(
            not isinstance(key, str) or not isinstance(value, str)
            for key, value in attributes.items()
        ):
            raise ValueError(f"{label} attributes must contain only string values")

        item: dict[str, Any] = {
            "category": category,
            "entity": entity.strip(),
            "status": status,
            "evidence_text": evidence,
            "start_offset": start,
            "end_offset": end,
            "attributes": attributes,
        }
        if raw.get("offset_resolution") == "computed_from_unique_exact_evidence":
            item["offset_resolution"] = "computed_from_unique_exact_evidence"
        code = raw.get("icd10_code")
        description = raw.get("icd10_description")
        if code is not None:
            if category != "diagnosis" or not isinstance(code, str) or not code.strip():
                raise ValueError(f"{label} has an invalid ICD-10-CM code field")
            if not isinstance(description, str) or not description.strip():
                raise ValueError(f"{label} requires icd10_description when a code is provided")
            item["icd10_code"] = code.strip()
            item["icd10_description"] = description.strip()
        elif description is not None:
            raise ValueError(f"{label} has a description without an ICD-10-CM code")
        items.append(item)

    return items, needs_review, [reason.strip() for reason in reasons if reason.strip()]


def build_benchmark_case(
    record: DatasetRecord,
    payload: object,
    *,
    model_provider: str,
    model_id: str,
    annotated_at_utc: str | None = None,
) -> dict[str, Any]:
    items, needs_review, review_reasons = validate_annotation_payload(record.note_text, payload)
    if not model_provider.strip() or not model_id.strip():
        raise ValueError("model provider and model ID are required for provenance")
    return {
        "case_id": record.record_id,
        "note": record.note_text,
        "gold_items": items,
        "expected_needs_review": needs_review,
        "review_reasons": review_reasons,
        "label_source": "ai_model",
        "clinical_performance_eligible": False,
        "model_provider": model_provider,
        "model_id": model_id,
        "annotation_version": ANNOTATION_VERSION,
        "annotation_timestamp_utc": annotated_at_utc or datetime.now(timezone.utc).isoformat(),
        "source_dataset": record.source_dataset,
        "source_url": record.source_url,
        "source_row_number": record.source_row_number,
        "specialty": record.specialty,
    }


def benchmark_case_to_queue_record(record: DatasetRecord, case: Mapping[str, Any]) -> dict[str, Any]:
    """Convert one benchmark case to the existing annotation-queue envelope."""
    annotations: dict[str, list[dict[str, Any]]] = {
        "diagnoses": [], "procedures": [], "medications": [], "allergies": [],
        "vital_signs": [], "icd10_cm_codes": [],
    }
    for item in case["gold_items"]:
        category_key = QUEUE_CATEGORY_MAP[item["category"]]
        queue_item = {
            key: item[key]
            for key in ("entity", "status", "evidence_text", "start_offset", "end_offset", "attributes", "offset_resolution")
            if key in item
        }
        annotations[category_key].append(queue_item)
        if item.get("icd10_code"):
            annotations["icd10_cm_codes"].append({
                "code": item["icd10_code"],
                "description": item["icd10_description"],
            })

    output = dict(record.metadata)
    output.update({
        "annotation_complete": True,
        "annotation_status": "complete",
        "gold_annotations": annotations,
        "adjudication_status": "not_reviewed",
        "expected_needs_review": case["expected_needs_review"],
        "label_source": "ai_model",
        "clinical_performance_eligible": False,
        "model_provider": case["model_provider"],
        "model_id": case["model_id"],
        "annotation_version": case["annotation_version"],
        "annotation_timestamp_utc": case["annotation_timestamp_utc"],
        "review_reasons": case.get("review_reasons", []),
    })
    return output


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path.name}:{line_number} must contain a JSON object")
            rows.append(value)
    return rows


def _write_jsonl_atomic(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", dir=path.parent,
            prefix=f".{path.name}.", suffix=".tmp", delete=False,
        ) as handle:
            temporary_name = handle.name
            for row in rows:
                handle.write(json.dumps(dict(row), ensure_ascii=False) + "\n")
        os.replace(temporary_name, path)
    finally:
        if temporary_name and os.path.exists(temporary_name):
            os.unlink(temporary_name)


def _persist_outputs(
    cases_path: Path,
    queue_path: Path,
    failures_path: Path,
    records: Sequence[DatasetRecord],
    cases_by_id: Mapping[str, dict[str, Any]],
    failures_by_id: Mapping[str, dict[str, Any]],
) -> None:
    ordered_cases = [cases_by_id[r.record_id] for r in records if r.record_id in cases_by_id]
    source_by_id = {record.record_id: record for record in records}
    queue_rows = [benchmark_case_to_queue_record(source_by_id[case["case_id"]], case) for case in ordered_cases]
    ordered_failures = [failures_by_id[r.record_id] for r in records if r.record_id in failures_by_id]
    _write_jsonl_atomic(cases_path, ordered_cases)
    _write_jsonl_atomic(queue_path, queue_rows)
    _write_jsonl_atomic(failures_path, ordered_failures)


def _safe_source_check(records: Sequence[DatasetRecord], approved_external: bool) -> str | None:
    external = [record for record in records if not is_synthetic_record(record)]
    if external and not approved_external:
        return (
            "Non-synthetic source notes were blocked from external processing. "
            "Verify that the data owner has approved the dataset and provider; "
            "only then rerun with --approved-external-processing."
        )
    return None


def _load_existing_cases(path: Path, records_by_id: Mapping[str, DatasetRecord]) -> dict[str, dict[str, Any]]:
    cases: dict[str, dict[str, Any]] = {}
    for case in _read_jsonl(path):
        case_id = case.get("case_id")
        if not isinstance(case_id, str) or case_id not in records_by_id:
            raise ValueError("existing benchmark output contains an unknown case_id")
        if case_id in cases:
            raise ValueError("existing benchmark output contains duplicate case_id values")
        if case.get("note") != records_by_id[case_id].note_text:
            raise ValueError("existing benchmark case does not match the input source note")
        # Revalidate saved annotations before reusing them.
        validate_annotation_payload(case["note"], {
            "items": case.get("gold_items"),
            "expected_needs_review": case.get("expected_needs_review"),
            "review_reasons": case.get("review_reasons", []),
        })
        if (
            case.get("label_source") != "ai_model"
            or case.get("clinical_performance_eligible") is not False
            or not isinstance(case.get("model_provider"), str)
            or not isinstance(case.get("model_id"), str)
        ):
            raise ValueError("existing benchmark output is missing AI provenance")
        cases[case_id] = case
    return cases


def _safe_failure_diagnostics(exc: Exception) -> dict[str, str]:
    """Classify failures without recording notes, prompts, responses, or exception text."""
    # Provider messages and SDK exceptions may contain request details. Store only
    # a small allowlisted code, and classify local validation messages by fixed
    # substrings emitted by validate_annotation_payload().
    try:
        from dashboard.extraction.groq_provider import GroqProviderError
    except ImportError:  # pragma: no cover - provider import is part of this app
        GroqProviderError = ()  # type: ignore[assignment,misc]

    if isinstance(exc, GroqProviderError):
        allowed_codes = {
            "provider_timeout",
            "provider_failed",
            "provider_bad_request",
            "provider_authentication_failed",
            "provider_permission_denied",
            "provider_resource_not_found",
            "provider_request_too_large",
            "provider_rate_limited",
            "provider_server_error",
            "provider_connection_error",
            "provider_response_shape_invalid",
            "provider_empty_response",
            "provider_invalid_json",
            "provider_invalid_json_shape",
        }
        code = getattr(exc, "code", "provider_failed")
        if code not in allowed_codes:
            code = "provider_failed"
        phase = "provider_response" if code.startswith(("provider_response", "provider_empty", "provider_invalid_json")) else "provider_request"
        return {
            "failure_phase": phase,
            "error_type": "GroqProviderError",
            "error_code": code,
        }

    if isinstance(exc, ValueError):
        message = str(exc).casefold()
        classifications = (
            ("evidence offsets do not match", "evidence_offsets_invalid"),
            ("evidence text is ambiguous", "evidence_text_ambiguous"),
            ("unsupported category", "unsupported_category"),
            ("invalid diagnosis status", "invalid_diagnosis_status"),
            ("invalid medication status", "invalid_medication_status"),
            ("status must be null", "unexpected_status"),
            ("requires a non-empty entity", "entity_missing"),
            ("requires evidence_text", "evidence_missing"),
            ("items must be a list", "items_not_a_list"),
            ("expected_needs_review", "review_flag_invalid"),
            ("review_reasons", "review_reasons_invalid"),
            ("icd-10-cm code field", "icd10_code_invalid"),
            ("requires icd10_description", "icd10_description_missing"),
            ("description without an icd-10-cm code", "icd10_description_without_code"),
            ("attributes", "attributes_invalid"),
            ("annotation response must be a json object", "response_schema_invalid"),
        )
        code = next((code for phrase, code in classifications if phrase in message), "annotation_validation_failed")
        return {
            "failure_phase": "annotation_validation",
            "error_type": "ValueError",
            "error_code": code,
        }

    return {
        "failure_phase": "annotation_generation",
        "error_type": type(exc).__name__ if type(exc).__name__.isalnum() else "UnexpectedError",
        "error_code": "unexpected_generation_error",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ANNOTATION_QUEUE_PATH)
    parser.add_argument("--output", type=Path, default=DEFAULT_CASES_PATH)
    parser.add_argument("--queue-output", type=Path, default=DEFAULT_QUEUE_PATH)
    parser.add_argument("--model", help="Optional Groq model ID; otherwise use GROQ_MODEL")
    parser.add_argument("--limit", type=int, default=5, help="Maximum source records to target; default 5 for pilot")
    parser.add_argument("--retries", type=int, choices=(0, 1, 2), default=1, help="Additional attempts for each note")
    parser.add_argument("--resume", action="store_true", help="Resume existing validated output without overwriting prior cases")
    parser.add_argument(
        "--approved-external-processing", action="store_true",
        help="Attest that the dataset owner approved sending non-synthetic note text to the configured external provider",
    )
    args = parser.parse_args(argv)
    if args.limit < 1:
        parser.error("--limit must be at least 1")
    if args.output.resolve() == args.queue_output.resolve():
        parser.error("--output and --queue-output must be different files")
    failures_path = args.output.with_suffix(args.output.suffix + ".failures.jsonl")
    output_paths = (args.output, args.queue_output, failures_path)
    if not args.resume and any(path.exists() for path in output_paths):
        parser.error("an output already exists; choose a new path or use --resume")
    if args.resume and args.queue_output.exists() and not args.output.exists():
        parser.error("queue output exists without benchmark output; refusing ambiguous resume")

    loaded = load_jsonl(args.input, required_fields=REQUIRED_RECORD_FIELDS)
    if loaded.errors:
        print("Input validation failed:")
        for error in loaded.errors:
            print(f"  - {error}")
        return 2
    if not loaded.records:
        print("Input dataset contains no valid records.")
        return 2

    source_records = tuple(loaded.records)
    selected_records = source_records[:args.limit]
    approval_error = _safe_source_check(selected_records, args.approved_external_processing)
    if approval_error:
        print(approval_error)
        return 2

    source_by_id = {record.record_id: record for record in source_records}
    try:
        cases_by_id = _load_existing_cases(args.output, source_by_id) if args.resume else {}
        failure_rows = _read_jsonl(failures_path) if args.resume else []
        failures_by_id = {
            row["case_id"]: row for row in failure_rows
            if isinstance(row.get("case_id"), str) and row["case_id"] in source_by_id
        }
    except (OSError, ValueError, json.JSONDecodeError, KeyError) as exc:
        print(f"Existing output could not be resumed ({type(exc).__name__}).")
        return 2

    # Provider construction is deferred until after input and safety checks.
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
    try:
        import django
        django.setup()
        from dashboard.extraction.groq_provider import GroqAnnotationProvider
        provider = GroqAnnotationProvider(model=args.model)
        model_id = provider.model_id
    except Exception as exc:
        print(
            "AI provider initialization failed ("
            f"{type(exc).__name__}). Check local opt-in, SDK installation, "
            "GROQ_API_KEY, and GROQ_MODEL."
        )
        return 2

    attempted = 0
    succeeded = 0
    failed = 0
    max_attempts = args.retries + 1
    selected_ids = {record.record_id for record in selected_records}
    for record in selected_records:
        if record.record_id in cases_by_id:
            continue
        attempted += 1
        case: dict[str, Any] | None = None
        final_diagnostics = {
            "failure_phase": "annotation_generation",
            "error_type": "UnknownError",
            "error_code": "unexpected_generation_error",
        }
        attempt_diagnostics: list[dict[str, Any]] = []
        for attempt_number in range(1, max_attempts + 1):
            try:
                payload = provider.annotate(record.note_text)
                case = build_benchmark_case(
                    record, payload, model_provider="groq", model_id=model_id,
                )
                break
            except Exception as exc:
                final_diagnostics = _safe_failure_diagnostics(exc)
                attempt_diagnostics.append({"attempt": attempt_number, **final_diagnostics})
        if case is None:
            failed += 1
            failures_by_id[record.record_id] = {
                "case_id": record.record_id,
                "attempts": max_attempts,
                **final_diagnostics,
                "attempt_diagnostics": attempt_diagnostics,
                "annotation_version": ANNOTATION_VERSION,
                "failed_at_utc": datetime.now(timezone.utc).isoformat(),
            }
            print(
                f"Failed annotation for {record.record_id} "
                f"({final_diagnostics['error_type']}: {final_diagnostics['error_code']}); "
                "note content omitted."
            )
        else:
            succeeded += 1
            cases_by_id[record.record_id] = case
            failures_by_id.pop(record.record_id, None)
            print(f"Annotated {record.record_id}; model output validated.")
        _persist_outputs(
            args.output, args.queue_output, failures_path,
            source_records, cases_by_id, failures_by_id,
        )

    print("\nAI benchmark generation summary")
    print(f"Input records: {len(source_records)}")
    print(f"Targeted by --limit: {len(selected_records)}")
    print(f"Already present and validated: {sum(record.record_id in cases_by_id for record in selected_records) - succeeded}")
    print(f"Newly attempted: {attempted}")
    print(f"Newly generated: {succeeded}")
    print(f"Failed this run: {failed}")
    print(f"Validated benchmark cases total: {len(cases_by_id)}")
    print("Clinical-human-gold eligibility: false for every generated case")
    print(f"Benchmark output: {args.output}")
    print(f"Queue-format output: {args.queue_output}")
    print(f"Failure summary: {failures_path}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
