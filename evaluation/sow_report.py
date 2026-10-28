"""Assemble a non-fabricating offline Mirai Labs SOW evaluation report."""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evaluation.metrics import (
    build_sow_evaluation_report,
    evaluate_dataset,
    evaluate_operational_metrics,
)


def _load_json(path: Path) -> Any:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-16"):
        try:
            return json.loads(raw.decode(encoding))
        except UnicodeDecodeError:
            continue
    raise ValueError(f"{path} is not valid UTF-8 or UTF-16 JSON")


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"{path}:{line_number} must contain an object")
            records.append(value)
    return records


def _validate_ai_benchmark_cases(
    cases: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[str]]:
    """Validate model-labelled cases without treating them as clinical gold."""
    valid: list[dict[str, Any]] = []
    errors: list[str] = []
    for index, case in enumerate(cases, start=1):
        prefix = f"case {index}"
        if case.get("label_source") != "ai_model":
            errors.append(f"{prefix}: label_source must be 'ai_model'")
            continue
        if case.get("clinical_performance_eligible") is not False:
            errors.append(f"{prefix}: clinical_performance_eligible must be false")
            continue
        note = case.get("note")
        items = case.get("gold_items")
        if not isinstance(case.get("case_id"), str) or not case["case_id"].strip():
            errors.append(f"{prefix}: case_id is required")
            continue
        if not isinstance(note, str) or not note:
            errors.append(f"{prefix}: note must be a non-empty string")
            continue
        if not isinstance(items, list):
            errors.append(f"{prefix}: gold_items must be a list")
            continue
        if not isinstance(case.get("expected_needs_review"), bool):
            errors.append(f"{prefix}: expected_needs_review must be a boolean")
            continue
        if not isinstance(case.get("model_provider"), str) or not case["model_provider"].strip():
            errors.append(f"{prefix}: model_provider is required")
            continue
        if not isinstance(case.get("model_id"), str) or not case["model_id"].strip():
            errors.append(f"{prefix}: model_id is required")
            continue
        case_valid = True
        for item_index, item in enumerate(items, start=1):
            if not isinstance(item, dict):
                errors.append(f"{prefix} item {item_index}: item must be an object")
                case_valid = False
                continue
            start = item.get("start_offset")
            end = item.get("end_offset")
            evidence = item.get("evidence_text")
            if (
                not isinstance(start, int)
                or isinstance(start, bool)
                or not isinstance(end, int)
                or isinstance(end, bool)
                or not isinstance(evidence, str)
                or start < 0
                or end < start
                or end > len(note)
                or note[start:end] != evidence
            ):
                errors.append(
                    f"{prefix} item {item_index}: evidence offsets do not "
                    "match the source note"
                )
                case_valid = False
        if case_valid:
            valid.append(case)
    return valid, errors


def _ai_benchmark_report(
    cases: list[dict[str, Any]],
    predictions: list[dict[str, Any]] | None,
) -> dict[str, Any]:
    if not cases:
        return {
            "status": "NOT EVALUATED",
            "reason": "No validated AI-generated benchmark labels supplied.",
            "clinical_performance_claimed": False,
        }
    if predictions is None:
        return {
            "status": "NOT EVALUATED",
            "reason": "AI-generated benchmark labels exist, but predictions are missing.",
            "case_count": len(cases),
            "clinical_performance_claimed": False,
        }
    try:
        metrics = evaluate_dataset(cases, predictions)
    except ValueError as exc:
        return {
            "status": "INVALID",
            "clinical_performance_claimed": False,
            "case_count": len(cases),
            "reason": str(exc),
        }
    return {
        "status": "AI_BENCHMARK_ONLY",
        "clinical_performance_claimed": False,
        "interpretation": (
            "Agreement with AI-generated labels; this is not independent "
            "clinical accuracy."
        ),
        "case_count": len(cases),
        "metrics": metrics,
    }


def _load_validator():
    path = (
        Path(__file__).resolve().parent.parent
        / "mirai_dataset_preparation_pack"
        / "scripts"
        / "validate_annotations.py"
    )
    spec = importlib.util.spec_from_file_location("sow_annotation_validator", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load annotation validator.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def qualified_gold_from_queue(queue_path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return qualified evaluation cases and explicit queue blockers."""
    validator = _load_validator()
    records = _load_jsonl(queue_path)
    qualified, errors = validator.evaluation_cases_from_records(records)
    progress = {
        "prepared_notes": len(records),
        "annotated_notes": sum(
            record.get("annotation_complete") is True for record in records
        ),
        "adjudicated_notes": sum(
            record.get("adjudication_status") == "adjudicated"
            for record in records
        ),
        "qualified_notes": len(qualified),
        "qualification_errors": len(errors),
        "gold_evaluation_ready": bool(records) and len(qualified) == len(records),
    }
    return qualified, progress


def build_report(
    *,
    queue_path: Path,
    challenge_report: dict[str, Any],
    smoke_report: dict[str, Any],
    agent_predictions: list[dict[str, Any]] | None = None,
    baseline_predictions: list[dict[str, Any]] | None = None,
    agent_operations: list[dict[str, Any]] | None = None,
    baseline_operations: list[dict[str, Any]] | None = None,
    poor_cases: list[dict[str, Any]] | None = None,
    ai_benchmark_cases: list[dict[str, Any]] | None = None,
    ai_benchmark_predictions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a report whose clinical metrics require qualified queue records."""
    gold_cases, queue_progress = qualified_gold_from_queue(queue_path)
    validated_benchmark_cases: list[dict[str, Any]] = []
    benchmark_errors: list[str] = []
    if ai_benchmark_cases is not None:
        validated_benchmark_cases, benchmark_errors = _validate_ai_benchmark_cases(
            ai_benchmark_cases
        )

    report: dict[str, Any] = {
        "report_type": "mirai_labs_sow_evaluation",
        "clinical_accuracy_claimed": False,
        "queue_progress": queue_progress,
        "challenge_sets": challenge_report,
        "synthetic_smoke": {
            "status": "VALIDATION_ONLY",
            "clinical_performance_claimed": False,
            "report": smoke_report,
        },
        "ai_generated_benchmark": _ai_benchmark_report(
            validated_benchmark_cases,
            ai_benchmark_predictions,
        ),
        "blockers": [],
    }
    if benchmark_errors:
        report["ai_generated_benchmark"] = {
            "status": "INVALID",
            "clinical_performance_claimed": False,
            "errors": benchmark_errors[:20],
            "error_count": len(benchmark_errors),
        }

    if not gold_cases:
        report["clinical_metrics"] = {
            "status": "NOT EVALUATED",
            "reason": "No qualified gold labels are available.",
        }
        report["baseline"] = {
            "status": "NOT EVALUATED",
            "reason": "No qualified gold labels or baseline predictions are available.",
        }
        report["blockers"].append(
            "Complete and adjudicate the 100-note queue with qualified annotators."
        )
    else:
        if agent_predictions is None:
            report["clinical_metrics"] = {
                "status": "NOT EVALUATED",
                "reason": "Qualified gold exists but agent predictions are missing.",
            }
        else:
            report["clinical_metrics"] = build_sow_evaluation_report(
                gold_cases,
                agent_predictions,
                baseline_predictions=baseline_predictions,
                agent_operational_records=agent_operations,
                baseline_operational_records=baseline_operations,
                challenge_report=challenge_report,
                case_results=poor_cases,
            )
        report["baseline"] = {
            "status": (
                "MEASURED"
                if baseline_predictions is not None
                else "NOT EVALUATED"
            ),
            "reason": (
                None
                if baseline_predictions is not None
                else "Comparable baseline predictions are missing."
            ),
        }

    report["operations"] = {
        "agent": (
            evaluate_operational_metrics(agent_operations)
            if agent_operations is not None
            else {"status": "NOT EVALUATED", "reason": "No agent run records supplied."}
        ),
        "baseline": (
            evaluate_operational_metrics(
                baseline_operations,
                system_name="baseline",
            )
            if baseline_operations is not None
            else {
                "status": "NOT EVALUATED",
                "reason": "No baseline run records supplied.",
            }
        ),
    }
    report["poor_cases"] = (
        build_sow_evaluation_report(
            gold_cases,
            agent_predictions,
            case_results=poor_cases,
        )["three_poor_performing_cases"]
        if gold_cases and agent_predictions is not None and poor_cases is not None
        else {
            "status": "NOT EVALUATED",
            "cases": [],
            "reason": "Requires qualified gold and measured case errors.",
        }
    )
    if challenge_report.get("overall_status") == "Not yet measured":
        report["blockers"].append(
            "Record independent observations for all 40 challenge cases."
        )
    if baseline_predictions is None:
        report["blockers"].append(
            "Run the naive single-prompt baseline on the same qualified cases."
        )
    if agent_operations is None:
        report["blockers"].append(
            "Record provider latency, calls, retries, and failure outcomes."
        )
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", type=Path, required=True)
    parser.add_argument("--challenge-report", type=Path, required=True)
    parser.add_argument("--smoke-report", type=Path, required=True)
    parser.add_argument("--agent-predictions", type=Path)
    parser.add_argument("--baseline-predictions", type=Path)
    parser.add_argument("--agent-operations", type=Path)
    parser.add_argument("--baseline-operations", type=Path)
    parser.add_argument("--poor-cases", type=Path)
    parser.add_argument(
        "--ai-benchmark-cases",
        type=Path,
        help="Optional model-labelled cases reported separately from clinical gold.",
    )
    parser.add_argument(
        "--ai-benchmark-predictions",
        type=Path,
        help="Optional predictions paired with --ai-benchmark-cases.",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        report = build_report(
            queue_path=args.queue,
            challenge_report=_load_json(args.challenge_report),
            smoke_report=_load_json(args.smoke_report),
            agent_predictions=(
                _load_jsonl(args.agent_predictions)
                if args.agent_predictions
                else None
            ),
            baseline_predictions=(
                _load_jsonl(args.baseline_predictions)
                if args.baseline_predictions
                else None
            ),
            agent_operations=(
                _load_jsonl(args.agent_operations)
                if args.agent_operations
                else None
            ),
            baseline_operations=(
                _load_jsonl(args.baseline_operations)
                if args.baseline_operations
                else None
            ),
            poor_cases=(
                _load_jsonl(args.poor_cases)
                if args.poor_cases
                else None
            ),
            ai_benchmark_cases=(
                _load_jsonl(args.ai_benchmark_cases)
                if args.ai_benchmark_cases
                else None
            ),
            ai_benchmark_predictions=(
                _load_jsonl(args.ai_benchmark_predictions)
                if args.ai_benchmark_predictions
                else None
            ),
        )
        if args.output.exists():
            raise FileExistsError(f"Refusing to overwrite existing file: {args.output}")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(report, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(json.dumps({
            "output": str(args.output),
            "clinical_status": report["clinical_metrics"]["status"],
            "prepared_notes": report["queue_progress"]["prepared_notes"],
            "qualified_notes": report["queue_progress"]["qualified_notes"],
            "challenge_status": report["challenge_sets"].get("overall_status"),
        }, indent=2))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"SOW_EVALUATION_FAILED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
