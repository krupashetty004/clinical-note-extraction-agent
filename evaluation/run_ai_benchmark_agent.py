"""Run the extraction/coding agent on validated AI-benchmark cases.

Predictions and operational measurements are stored separately.
AI-generated references are not independent clinical gold.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Mapping, Sequence

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
import django
from django.apps import apps

if not apps.ready:
    django.setup()

from dashboard.extraction.groq_provider import (
    GroqExtractionProvider,
    GroqProviderConfigurationError,
    GroqVerificationProvider,
)
from dashboard.extraction.orchestrator import (
    AgentWorkflowResult,
    run_agent_workflow,
)

DEFAULT_PREDICTIONS_PATH = Path("evaluation/ai_benchmark_predictions.jsonl")
DEFAULT_OPERATIONS_PATH = Path("evaluation/ai_benchmark_operations.jsonl")

SYNTHETIC_PREFIXES = ("synthetic:", "local:synthetic", "local:test")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()

    with path.open("r", encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue

            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                raise ValueError(
                    f"{path.name}:{line_number} contains invalid JSON"
                ) from None

            if not isinstance(row, dict):
                raise ValueError(
                    f"{path.name}:{line_number} must contain an object"
                )

            case_id = row.get("case_id")
            if not isinstance(case_id, str) or not case_id.strip():
                raise ValueError(
                    f"{path.name}:{line_number} requires case_id"
                )
            if case_id in seen:
                raise ValueError(f"{path.name} contains duplicate case IDs")

            seen.add(case_id)
            rows.append(row)

    return rows


def validate_benchmark_cases(
    cases: Sequence[Mapping[str, Any]],
    *,
    approved_external_processing: bool,
) -> list[dict[str, Any]]:
    if not cases:
        raise ValueError("No benchmark cases were supplied")

    validated: list[dict[str, Any]] = []

    for index, source in enumerate(cases, start=1):
        case = dict(source)
        case_id = case.get("case_id")
        note = case.get("note")
        source_dataset = case.get("source_dataset")

        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError(f"Case {index} requires a nonblank case_id")
        if not isinstance(note, str) or not note.strip():
            raise ValueError(f"Case {case_id} requires nonblank note text")
        if case.get("label_source") != "ai_model":
            raise ValueError(f"Case {case_id} is not labelled as AI-generated")
        if case.get("clinical_performance_eligible") is not False:
            raise ValueError(
                f"Case {case_id} must not be marked clinical-gold eligible"
            )
        if not isinstance(case.get("gold_items"), list):
            raise ValueError(f"Case {case_id} requires gold_items")
        if not isinstance(source_dataset, str) or not source_dataset.strip():
            raise ValueError(
                f"Case {case_id} requires source_dataset provenance"
            )

        is_synthetic = source_dataset.strip().casefold().startswith(
            SYNTHETIC_PREFIXES
        )
        if not is_synthetic and not approved_external_processing:
            raise ValueError(
                "Non-synthetic notes are blocked; confirm dataset-owner "
                "approval before using --approved-external-processing"
            )

        validated.append(case)

    return validated


def build_prediction_case(
    case_id: str,
    result: AgentWorkflowResult,
) -> dict[str, Any]:
    """Convert a workflow result to the evaluation prediction schema."""
    predicted_items: list[dict[str, Any]] = []

    if result.extraction is not None:
        decisions = {
            item.item_index: item.decision
            for item in result.item_dispositions
        }
        candidates_by_span = {
            (mention.start_offset, mention.end_offset): [
                candidate.code for candidate in mention.coding.candidates
            ]
            for mention in (
                result.coding.diagnoses if result.coding else ()
            )
        }

        for index, extracted in enumerate(result.extraction.items):
            item = extracted.model_dump(mode="json")
            item["decision"] = decisions.get(index, "needs_review")
            item["icd10_candidates"] = candidates_by_span.get(
                (extracted.start_offset, extracted.end_offset), []
            )
            predicted_items.append(item)

    return {
        "case_id": case_id,
        "items": predicted_items,
        "needs_review": result.status != "completed",
    }


def build_operation_record(
    case_id: str,
    result: AgentWorkflowResult,
    *,
    latency_ms: float,
    model_id: str,
) -> dict[str, Any]:
    extraction_attempts = result.extraction_attempts
    verification_attempts = result.verification_attempts

    record: dict[str, Any] = {
        "case_id": case_id,
        "status": result.status,
        "latency_ms": round(max(0.0, latency_ms), 3),
        "model_calls": extraction_attempts + verification_attempts,
        "retry_count": (
            max(0, extraction_attempts - 1)
            + max(0, verification_attempts - 1)
        ),
        "extraction_attempts": extraction_attempts,
        "verification_attempts": verification_attempts,
        "model_provider": "groq",
        "model_id": model_id,
    }

    if result.failure_code:
        record["failure_code"] = result.failure_code

    return record


def write_jsonl_atomic(
    path: Path,
    rows: Sequence[Mapping[str, Any]],
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            newline="\n",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_name = handle.name
            for row in rows:
                handle.write(json.dumps(dict(row), ensure_ascii=False) + "\n")

        os.replace(temporary_name, path)
    finally:
        if temporary_name and os.path.exists(temporary_name):
            os.unlink(temporary_name)


def run_cases(
    cases: Sequence[Mapping[str, Any]],
    *,
    extraction_provider: Any,
    verification_provider: Any,
    model_id: str,
    max_extraction_attempts: int = 2,
    max_verification_attempts: int = 2,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    predictions: list[dict[str, Any]] = []
    operations: list[dict[str, Any]] = []

    for case in cases:
        case_id = str(case["case_id"])
        started = time.perf_counter()

        result = run_agent_workflow(
            extraction_provider,
            verification_provider,
            str(case["note"]),
            max_extraction_attempts=max_extraction_attempts,
            max_verification_attempts=max_verification_attempts,
        )

        elapsed_ms = (time.perf_counter() - started) * 1000
        predictions.append(build_prediction_case(case_id, result))
        operations.append(
            build_operation_record(
                case_id,
                result,
                latency_ms=elapsed_ms,
                model_id=model_id,
            )
        )

        print(
            f"Processed {case_id}: status={result.status}; "
            "note content omitted."
        )

    return predictions, operations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, default=DEFAULT_PREDICTIONS_PATH)
    parser.add_argument(
        "--operations-output", type=Path, default=DEFAULT_OPERATIONS_PATH
    )
    parser.add_argument("--model")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument(
        "--approved-external-processing",
        action="store_true",
        help="Attest that the dataset owner approved external processing.",
    )
    args = parser.parse_args(argv)

    if args.limit < 1:
        parser.error("--limit must be at least 1")
    if args.output.resolve() == args.operations_output.resolve():
        parser.error("Output paths must be different")

    for path in (args.output, args.operations_output):
        if path.exists():
            parser.error(f"Refusing to overwrite existing output: {path}")

    try:
        source_cases = read_jsonl(args.input)
        cases = validate_benchmark_cases(
            source_cases[:args.limit],
            approved_external_processing=args.approved_external_processing,
        )
    except (OSError, ValueError) as exc:
        print(f"INPUT_VALIDATION_FAILED: {exc}", file=sys.stderr)
        return 2

    try:
        extraction_provider = GroqExtractionProvider(model=args.model)
        verification_provider = GroqVerificationProvider(model=args.model)
        model_id = extraction_provider.model_id
    except Exception as exc:
        print(
            f"AI agent initialization failed ({type(exc).__name__}); "
            "details suppressed.",
            file=sys.stderr,
        )
        return 2

    try:
        predictions, operations = run_cases(
            cases,
            extraction_provider=extraction_provider,
            verification_provider=verification_provider,
            model_id=model_id,
        )
        write_jsonl_atomic(args.output, predictions)
        write_jsonl_atomic(args.operations_output, operations)
    except Exception as exc:
        print(
            f"AGENT_RUN_FAILED: {type(exc).__name__}; details suppressed.",
            file=sys.stderr,
        )
        return 1

    failed = sum(row["status"] == "failed" for row in operations)
    needs_review = sum(
        row["status"] == "needs_review" for row in operations
    )

    print("\nAI benchmark agent run summary")
    print(f"Cases processed: {len(cases)}")
    print(f"Completed: {len(cases) - failed - needs_review}")
    print(f"Needs review: {needs_review}")
    print(f"Failed: {failed}")
    print("Clinical performance claimed: false")
    print(f"Predictions: {args.output}")
    print(f"Operations: {args.operations_output}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())