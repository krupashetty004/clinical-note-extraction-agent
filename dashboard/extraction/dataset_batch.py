"""Offline batch processing for the locally prepared MTSamples annotation queue.

This runner reuses the clinical extraction, ICD-10 retrieval, verification and
reconciliation workflow, but deliberately does not create Patient, Encounter,
ClinicalNote or ClinicalProcessingRun rows. It always uses local providers and
stores note-level outputs under the ignored .dataset_working directory.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
import time
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

from dashboard.extraction.dataset import (
    LOCAL_DATA_ROOT,
    annotation_readiness,
    build_evaluation_gold_cases,
    load_annotation_queue,
)
from dashboard.extraction.local_provider import (
    LocalClinicalExtractionProvider,
    LocalClinicalVerificationProvider,
)
from dashboard.extraction.orchestrator import run_agent_workflow

DEFAULT_BATCH_OUTPUT_DIR = LOCAL_DATA_ROOT / "runs" / "mtsamples"
PREDICTIONS_FILENAME = "predictions.jsonl"
OPERATIONS_FILENAME = "operations.jsonl"
REPORT_FILENAME = "report.json"
CHECKPOINT_FILENAME = "results.jsonl"
LOCAL_PROVIDER_ID = "local-clinical-rules-v1"


class DatasetBatchError(ValueError):
    """Raised when a dataset batch cannot be safely started or resumed."""


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                raise DatasetBatchError(
                    f"{path.name}:{line_number} contains invalid JSON."
                ) from None
            if not isinstance(value, dict):
                raise DatasetBatchError(
                    f"{path.name}:{line_number} must contain a JSON object."
                )
            record_id = value.get("case_id")
            if not isinstance(record_id, str) or not record_id.strip():
                raise DatasetBatchError(
                    f"{path.name}:{line_number} is missing case_id."
                )
            if record_id in seen:
                raise DatasetBatchError(
                    f"{path.name} contains duplicate case IDs."
                )
            seen.add(record_id)
            rows.append(value)
    return rows


def _write_jsonl_atomic(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
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


def _write_json_atomic(path: Path, payload: Mapping[str, Any]) -> None:
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
            json.dump(dict(payload), handle, indent=2, ensure_ascii=False)
            handle.write("\n")
        os.replace(temporary_name, path)
    finally:
        if temporary_name and os.path.exists(temporary_name):
            os.unlink(temporary_name)


def _validate_output_dir(output_dir: Path) -> Path:
    root = LOCAL_DATA_ROOT.resolve()
    candidate = output_dir.resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise DatasetBatchError(
            "Batch output must stay inside the Git-ignored .dataset_working directory."
        ) from exc
    return candidate


def _prediction_from_result(record, workflow_result) -> dict[str, Any]:
    decisions = {
        item.item_index: item.decision
        for item in workflow_result.item_dispositions
    }
    candidates_by_span: dict[tuple[int, int], list[str]] = {}
    if workflow_result.coding is not None:
        for mention in workflow_result.coding.diagnoses:
            candidate_codes = [
                candidate.code for candidate in mention.coding.candidates
            ]
            candidates_by_span[(mention.start_offset, mention.end_offset)] = (
                candidate_codes
            )

    predicted_items: list[dict[str, Any]] = []
    extraction = workflow_result.extraction
    if extraction is not None:
        for index, item in enumerate(extraction.items):
            predicted = item.model_dump(mode="json")
            predicted["decision"] = decisions.get(index, "needs_review")
            predicted["icd10_candidates"] = candidates_by_span.get(
                (item.start_offset, item.end_offset), []
            )
            predicted_items.append(predicted)

    return {
        "case_id": record.record_id,
        "source_dataset": record.source_dataset,
        "source_row_number": record.source_row_number,
        "specialty": record.specialty,
        "note_sha256": hashlib.sha256(
            record.note_text.encode("utf-8")
        ).hexdigest(),
        "items": predicted_items,
        "status": workflow_result.status,
        "needs_review": workflow_result.status != "completed",
        "failure_code": workflow_result.failure_code or "",
        "review_reasons": list(workflow_result.review_reasons),
    }


def _operation_from_result(
    record,
    workflow_result,
    *,
    latency_ms: float,
) -> dict[str, Any]:
    return {
        "case_id": record.record_id,
        "source_dataset": record.source_dataset,
        "specialty": record.specialty,
        "status": workflow_result.status,
        "latency_ms": round(max(0.0, latency_ms), 3),
        "extraction_attempts": workflow_result.extraction_attempts,
        "verification_attempts": workflow_result.verification_attempts,
        "provider_invocations": (
            workflow_result.extraction_attempts
            + workflow_result.verification_attempts
        ),
        "provider": "local",
        "provider_id": LOCAL_PROVIDER_ID,
        "failure_code": workflow_result.failure_code or "",
    }


def _build_report(
    *,
    source_path: Path,
    selected_records,
    predictions: list[dict[str, Any]],
    operations: list[dict[str, Any]],
    annotation_report: Mapping[str, Any],
    evaluation: Mapping[str, Any],
) -> dict[str, Any]:
    status_counts = Counter(row["status"] for row in operations)
    return {
        "report_type": "offline_dataset_batch_processing",
        "source_file": source_path.name,
        "source_sha256": hashlib.sha256(source_path.read_bytes()).hexdigest(),
        "provider": "local",
        "provider_id": LOCAL_PROVIDER_ID,
        "external_provider_calls": 0,
        "patient_records_created": 0,
        "clinical_processing_runs_created": 0,
        "records_selected": len(selected_records),
        "records_processed": len(predictions),
        "status_counts": dict(sorted(status_counts.items())),
        "annotation_readiness": {
            key: annotation_report[key]
            for key in (
                "records_loaded",
                "completed_annotations",
                "adjudicated_annotations",
                "clinical_performance_eligible",
                "ai_generated_benchmark_records",
                "specialties_in_queue",
                "gold_evaluation_ready",
            )
        },
        "evaluation": dict(evaluation),
        "limitations": [
            "This is offline batch execution, not a clinical accuracy result.",
            "AI-generated and unreviewed labels are not treated as clinical gold.",
            "Evidence integrity does not establish semantic clinical correctness.",
            "A doctor must review uncertain or rejected findings before clinical use.",
        ],
    }


def run_dataset_batch(
    *,
    input_path: Path,
    output_dir: Path = DEFAULT_BATCH_OUTPUT_DIR,
    limit: int | None = None,
    resume: bool = False,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Run the real local agent workflow over an annotation queue.

    Note text is read only from the supplied local JSONL file. It is never
    printed, included in reports, or sent to an external provider.
    """
    if limit is not None and (
        isinstance(limit, bool) or not isinstance(limit, int) or limit < 1
    ):
        raise DatasetBatchError("limit must be a positive integer.")

    source_path = Path(input_path).expanduser().resolve()
    loaded = load_annotation_queue(source_path)
    if loaded.errors:
        raise DatasetBatchError(
            f"Dataset validation failed with {len(loaded.errors)} error(s): "
            f"{loaded.errors[0]}"
        )
    if not loaded.records:
        raise DatasetBatchError("The dataset queue contains no usable records.")

    selected_records = list(loaded.records[:limit] if limit else loaded.records)
    selected_ids = {record.record_id for record in selected_records}
    output_root = _validate_output_dir(Path(output_dir))
    predictions_path = output_root / PREDICTIONS_FILENAME
    operations_path = output_root / OPERATIONS_FILENAME
    report_path = output_root / REPORT_FILENAME
    checkpoint_path = output_root / CHECKPOINT_FILENAME
    output_root.mkdir(parents=True, exist_ok=True)

    outputs_exist = any(
        path.exists()
        for path in (predictions_path, operations_path, checkpoint_path)
    )
    if resume and overwrite:
        raise DatasetBatchError("--resume and --overwrite cannot be used together.")
    if outputs_exist and not (resume or overwrite):
        raise DatasetBatchError(
            "Batch outputs already exist. Use --resume to continue or "
            "--overwrite to replace them."
        )

    predictions: list[dict[str, Any]] = []
    operations: list[dict[str, Any]] = []
    checkpoints: list[dict[str, Any]] = []
    completed_ids: set[str] = set()
    if resume:
        if not checkpoint_path.is_file():
            raise DatasetBatchError(
                "Resume requires the atomic results.jsonl checkpoint file."
            )
        checkpoints = _read_jsonl(checkpoint_path)
        for row in checkpoints:
            prediction = row.get("prediction")
            operation = row.get("operation")
            if not isinstance(prediction, dict) or not isinstance(operation, dict):
                raise DatasetBatchError(
                    "A checkpoint row is missing its prediction or operation object."
                )
            case_id = row["case_id"]
            if prediction.get("case_id") != case_id or operation.get("case_id") != case_id:
                raise DatasetBatchError(
                    "A checkpoint row contains mismatched case IDs."
                )
            predictions.append(prediction)
            operations.append(operation)
        completed_ids = {row["case_id"] for row in checkpoints}
        if not completed_ids.issubset(selected_ids):
            raise DatasetBatchError(
                "Existing batch outputs contain IDs outside the selected input records."
            )

    previously_processed_count = len(predictions)
    extraction_provider = LocalClinicalExtractionProvider()
    verification_provider = LocalClinicalVerificationProvider()

    for record in selected_records:
        if record.record_id in completed_ids:
            continue
        started = time.perf_counter()
        try:
            workflow_result = run_agent_workflow(
                extraction_provider=extraction_provider,
                verification_provider=verification_provider,
                original_note=record.note_text,
                max_extraction_attempts=2,
                max_verification_attempts=2,
            )
        except Exception as exc:
            # Keep the batch traceable without storing exception messages that
            # could contain note text, secrets, or provider-specific details.
            workflow_result = type(
                "SafeFailedWorkflowResult",
                (),
                {
                    "status": "failed",
                    "extraction_attempts": 0,
                    "verification_attempts": 0,
                    "extraction": None,
                    "coding": None,
                    "item_dispositions": (),
                    "review_reasons": (
                        "This record failed unexpectedly and requires review.",
                    ),
                    "failure_code": "dataset_batch_unexpected_failure",
                },
            )()
        latency_ms = (time.perf_counter() - started) * 1000.0
        prediction = _prediction_from_result(record, workflow_result)
        operation = _operation_from_result(
            record,
            workflow_result,
            latency_ms=latency_ms,
        )
        predictions.append(prediction)
        operations.append(operation)
        checkpoints.append(
            {
                "case_id": record.record_id,
                "prediction": prediction,
                "operation": operation,
            }
        )
        # One atomic checkpoint keeps predictions and operations in sync
        # if the batch is interrupted between records.
        _write_jsonl_atomic(checkpoint_path, checkpoints)
        completed_ids.add(record.record_id)

    # Materialize the separate, convenient projections from the checkpoint.
    _write_jsonl_atomic(predictions_path, predictions)
    _write_jsonl_atomic(operations_path, operations)

    queue_readiness = annotation_readiness(loaded)
    gold_cases, evaluation_input = build_evaluation_gold_cases(loaded)
    evaluation: dict[str, Any] = {
        "status": "NOT EVALUATED",
        "clinical_performance_claimed": False,
        "reason": "The source queue does not contain qualified clinical gold labels.",
    }
    if queue_readiness["gold_evaluation_ready"]:
        gold_by_id = {
            case["case_id"]: case for case in gold_cases
            if case["case_id"] in selected_ids
        }
        predictions_by_id = {
            row["case_id"]: row for row in predictions
            if row["case_id"] in selected_ids
        }
        if set(gold_by_id) == set(predictions_by_id) and gold_by_id:
            from evaluation.metrics import evaluate_dataset

            evaluation = {
                "status": "MEASURED_AGAINST_QUALIFIED_LABELS",
                "clinical_performance_claimed": True,
                "case_count": len(gold_by_id),
                "metrics": evaluate_dataset(
                    list(gold_by_id.values()),
                    list(predictions_by_id.values()),
                ),
            }
        else:
            evaluation = {
                "status": "NOT EVALUATED",
                "clinical_performance_claimed": False,
                "reason": "Qualified gold records do not match all selected predictions.",
            }

    report = _build_report(
        source_path=source_path,
        selected_records=selected_records,
        predictions=predictions,
        operations=operations,
        annotation_report=queue_readiness,
        evaluation={
            **dict(evaluation_input),
            **evaluation,
        },
    )
    _write_json_atomic(report_path, report)
    return {
        "records_selected": len(selected_records),
        "records_processed": len(predictions),
        "new_records_processed": len(predictions) - previously_processed_count,
        "predictions_path": str(predictions_path),
        "operations_path": str(operations_path),
        "report_path": str(report_path),
        "evaluation_status": report["evaluation"]["status"],
        "status_counts": report["status_counts"],
    }
