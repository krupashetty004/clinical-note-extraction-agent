"""Safe access to the prepared local MTSamples JSONL assets.

The prepared files are source inputs, not application fixtures. This module
validates their envelope and provenance without logging note text.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator


PACKAGE_ROOT = (
    Path(__file__).resolve().parents[2] / "mirai_dataset_preparation_pack"
)
REPOSITORY_ROOT = PACKAGE_ROOT.parent
LOCAL_DATA_ROOT = REPOSITORY_ROOT / ".dataset_working"
PREPARED_RECORDS_PATH = LOCAL_DATA_ROOT / "prepared" / "records.jsonl"
ANNOTATION_QUEUE_PATH = (
    LOCAL_DATA_ROOT / "annotations" / "annotation_template_100.jsonl"
)

REQUIRED_RECORD_FIELDS = {
    "record_id",
    "source_dataset",
    "source_url",
    "source_row_number",
    "specialty",
    "note_text",
}
REQUIRED_ANNOTATION_FIELDS = REQUIRED_RECORD_FIELDS | {
    "annotation_complete",
    "annotation_status",
    "gold_annotations",
    "adjudication_status",
}


@dataclass(frozen=True)
class DatasetRecord:
    """A validated source record with provenance retained."""

    record_id: str
    source_dataset: str
    source_url: str
    source_row_number: int
    specialty: str
    note_text: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class DatasetLoadResult:
    """Records loaded successfully and non-sensitive validation errors."""

    records: tuple[DatasetRecord, ...]
    errors: tuple[str, ...]
    path: Path

    @property
    def is_valid(self) -> bool:
        return not self.errors


def _read_lines(path: Path) -> Iterator[tuple[int, str]]:
    """Read JSONL using a small encoding fallback without exposing content."""
    last_error: UnicodeError | None = None
    for encoding in ("utf-8", "utf-8-sig", "cp1252"):
        try:
            with path.open("r", encoding=encoding) as handle:
                for line_number, line in enumerate(handle, start=1):
                    yield line_number, line
            return
        except UnicodeDecodeError as exc:
            last_error = exc
    raise ValueError(f"Could not decode dataset file: {path.name}") from last_error


def load_jsonl(
    path: Path,
    *,
    required_fields: set[str],
    max_errors: int = 100,
) -> DatasetLoadResult:
    """Load and validate prepared JSONL while skipping malformed rows.

    Error messages contain only line numbers, field names, and identifiers;
    they never include note text or complete source records.
    """
    if not path.is_file():
        return DatasetLoadResult(
            records=(),
            errors=(f"Dataset file not found: {path}",),
            path=path,
        )

    records: list[DatasetRecord] = []
    errors: list[str] = []
    seen_ids: set[str] = set()
    seen_source_rows: set[tuple[str, int]] = set()

    try:
        lines = _read_lines(path)
        for line_number, line in lines:
            if not line.strip():
                continue
            try:
                value = json.loads(line)
            except json.JSONDecodeError:
                if len(errors) < max_errors:
                    errors.append(f"line {line_number}: invalid JSON")
                continue
            if not isinstance(value, dict):
                if len(errors) < max_errors:
                    errors.append(f"line {line_number}: record is not an object")
                continue

            missing = sorted(required_fields - value.keys())
            record_id = value.get("record_id", f"line-{line_number}")
            if missing:
                if len(errors) < max_errors:
                    errors.append(
                        f"line {line_number} ({record_id}): missing fields "
                        + ", ".join(missing)
                    )
                continue
            if not isinstance(record_id, str) or not record_id.strip():
                if len(errors) < max_errors:
                    errors.append(f"line {line_number}: invalid record_id")
                continue
            if record_id in seen_ids:
                if len(errors) < max_errors:
                    errors.append(f"line {line_number} ({record_id}): duplicate record_id")
                continue
            if (
                not isinstance(value["note_text"], str)
                or not value["note_text"].strip()
            ):
                if len(errors) < max_errors:
                    errors.append(f"line {line_number} ({record_id}): invalid note_text")
                continue
            if (
                not isinstance(value["source_row_number"], int)
                or isinstance(value["source_row_number"], bool)
                or value["source_row_number"] < 1
            ):
                if len(errors) < max_errors:
                    errors.append(
                        f"line {line_number} ({record_id}): invalid source_row_number"
                    )
                continue
            if not all(
                isinstance(value[field], str) and value[field].strip()
                for field in ("source_dataset", "source_url", "specialty")
            ):
                if len(errors) < max_errors:
                    errors.append(
                        f"line {line_number} ({record_id}): invalid provenance fields"
                    )
                continue
            source_key = (value["source_dataset"], value["source_row_number"])
            if source_key in seen_source_rows:
                if len(errors) < max_errors:
                    errors.append(
                        f"line {line_number} ({record_id}): duplicate source row"
                    )
                continue
            if value["source_dataset"] == "kaggle:tboyle10/medicaltranscriptions":
                match = re.fullmatch(r"mtsamples-(\\d{5})-[0-9a-f]{16}", record_id)
                if not match or int(match.group(1)) != value["source_row_number"]:
                    if len(errors) < max_errors:
                        errors.append(
                            f"line {line_number} ({record_id}): record ID does not match source_row_number"
                        )
                    continue

            seen_ids.add(record_id)
            seen_source_rows.add(source_key)
            records.append(
                DatasetRecord(
                    record_id=record_id,
                    source_dataset=value["source_dataset"],
                    source_url=value["source_url"],
                    source_row_number=value["source_row_number"],
                    specialty=value["specialty"],
                    note_text=value["note_text"],
                    metadata=value,
                )
            )
    except (OSError, UnicodeError, ValueError) as exc:
        if len(errors) < max_errors:
            errors.append(str(exc))

    return DatasetLoadResult(tuple(records), tuple(errors), path)


def load_prepared_records(path: Path = PREPARED_RECORDS_PATH) -> DatasetLoadResult:
    """Load normalized source records."""
    return load_jsonl(path, required_fields=REQUIRED_RECORD_FIELDS)


def load_annotation_queue(path: Path = ANNOTATION_QUEUE_PATH) -> DatasetLoadResult:
    """Load the human annotation queue, preserving incomplete labels."""
    return load_jsonl(path, required_fields=REQUIRED_ANNOTATION_FIELDS)


AI_ANNOTATION_FIELDS = (
    "diagnoses",
    "procedures",
    "medications",
    "allergies",
    "vital_signs",
    "icd10_cm_codes",
)

GOLD_LABEL_SOURCES = {"human_annotated", "external_gold_standard"}


def _has_gold_label_provenance(metadata: dict[str, Any]) -> bool:
    """Require non-AI source, complete provenance, and independent qualification."""
    provenance = metadata.get("label_provenance")
    if metadata.get("label_source") not in GOLD_LABEL_SOURCES:
        return False
    if not isinstance(provenance, dict) or not all(
        isinstance(provenance.get(field), str) and provenance[field].strip()
        for field in ("dataset_version", "annotation_guidelines", "license_or_dua")
    ):
        return False
    if metadata.get("label_source") == "external_gold_standard":
        return metadata.get("annotation_complete") is True
    annotator = metadata.get("annotator_id")
    adjudicator = metadata.get("adjudicator_id")
    qualification = metadata.get("annotator_qualification")
    return (
        metadata.get("annotation_complete") is True
        and metadata.get("annotation_status") in {"complete", "adjudicated"}
        and metadata.get("adjudication_status") == "adjudicated"
        and isinstance(annotator, str)
        and bool(annotator.strip())
        and isinstance(adjudicator, str)
        and bool(adjudicator.strip())
        and annotator != adjudicator
        and isinstance(qualification, dict)
        and qualification.get("qualified") is True
        and isinstance(metadata.get("adjudication_notes"), str)
        and bool(metadata["adjudication_notes"].strip())
        and metadata.get("conflict_status") in {"resolved", "not_applicable"}
        and isinstance(metadata.get("conflict_notes"), str)
        and bool(metadata["conflict_notes"].strip())
    )


def _is_complete_ai_benchmark_record(metadata: dict[str, Any]) -> bool:
    """Require an explicitly completed, structurally complete AI annotation.

    Empty category lists are valid when the model explicitly completed the
    annotation; missing category lists are not equivalent to no findings.
    """
    annotations = metadata.get("gold_annotations")
    return (
        metadata.get("label_source") == "ai_model"
        and metadata.get("clinical_performance_eligible") is False
        and metadata.get("annotation_complete") is True
        and metadata.get("annotation_status") in {"complete", "adjudicated"}
        and isinstance(metadata.get("expected_needs_review"), bool)
        and isinstance(metadata.get("model_provider"), str)
        and bool(metadata["model_provider"].strip())
        and isinstance(metadata.get("model_id"), str)
        and bool(metadata["model_id"].strip())
        and isinstance(annotations, dict)
        and all(isinstance(annotations.get(field), list) for field in AI_ANNOTATION_FIELDS)
    )


def annotation_readiness(result: DatasetLoadResult) -> dict[str, Any]:
    """Return aggregate annotation readiness without returning note content."""
    complete = [
        record
        for record in result.records
        if record.metadata.get("annotation_complete") is True
    ]
    adjudicated = [
        record
        for record in complete
        if record.metadata.get("adjudication_status")
        in {"adjudicated", "not_required"}
    ]
    eligible = [
        record
        for record in complete
        if (
            record.metadata.get("clinical_performance_eligible") is True
            and _has_gold_label_provenance(record.metadata)
        )
    ]
    ai_benchmark_records = [
        record
        for record in result.records
        if _is_complete_ai_benchmark_record(record.metadata)
    ]
    specialty_count = len(
        {record.specialty for record in result.records if record.specialty}
    )
    return {
        "path": str(result.path),
        "records_loaded": len(result.records),
        "validation_errors": len(result.errors),
        "completed_annotations": len(complete),
        "adjudicated_annotations": len(adjudicated),
        "clinical_performance_eligible": len(eligible),
        "ai_generated_benchmark_records": len(ai_benchmark_records),
        "ai_generated_benchmark_ready": (
            bool(result.records)
            and not result.errors
            and len(ai_benchmark_records) == len(result.records)
        ),
        "specialties_in_queue": specialty_count,
        "minimum_specialties_required": 10,
        "specialty_coverage_met": specialty_count >= 10,
        "gold_evaluation_ready": bool(result.records)
        and not result.errors
        and specialty_count >= 10
        and len(eligible) == len(result.records),
    }


def build_evaluation_gold_cases(
    result: DatasetLoadResult,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Convert only qualified annotations into the metrics input format.

    Source specialty and keyword fields are deliberately not used as entity
    labels. An incomplete or non-eligible queue produces no cases and a
    machine-readable blocked reason instead of silently lowering a metric
    denominator.
    """
    readiness = annotation_readiness(result)
    if not readiness["gold_evaluation_ready"]:
        return [], {
            "eligible_case_count": 0,
            "metric_status": "blocked",
            "reason": (
                "Qualified, adjudicated entity annotations are not available "
                "for every queue record."
            ),
            "source_record_id_count": len(result.records),
            "source_record_id_sample": [
                record.record_id for record in result.records[:5]
            ],
            "specialties": sorted(
                {record.specialty for record in result.records if record.specialty},
            ),
        }

    category_map = {
        "diagnoses": "diagnosis",
        "procedures": "procedure",
        "medications": "medication",
        "allergies": "allergy",
        "vital_signs": "vital_sign",
    }
    cases: list[dict[str, Any]] = []
    for record in result.records:
        gold = record.metadata.get("gold_annotations")
        if not isinstance(gold, dict):
            return [], {
                "eligible_case_count": 0,
                "metric_status": "blocked",
                "reason": "A qualified record has no gold annotation object.",
            }

        items: list[dict[str, Any]] = []
        for source_category, category in category_map.items():
            category_items = gold.get(source_category)
            if not isinstance(category_items, list):
                return [], {
                    "eligible_case_count": 0,
                    "metric_status": "blocked",
                    "reason": f"Gold field '{source_category}' is not a list.",
                }
            for source_item in category_items:
                if not isinstance(source_item, dict):
                    return [], {
                        "eligible_case_count": 0,
                        "metric_status": "blocked",
                        "reason": "A gold entity is not an object.",
                    }
                item = dict(source_item)
                item["category"] = category
                if not isinstance(item.get("entity"), str):
                    item["entity"] = item.get("text", "")
                if not item["entity"].strip():
                    return [], {
                        "eligible_case_count": 0,
                        "metric_status": "blocked",
                        "reason": "A qualified gold entity has no entity text.",
                    }
                items.append(item)

        cases.append(
            {
                "case_id": record.record_id,
                "note": record.note_text,
                "gold_items": items,
                "expected_needs_review": False,
                "source_dataset": record.source_dataset,
                "source_row_number": record.source_row_number,
                "specialty": record.specialty,
            }
        )

    return cases, {
        "eligible_case_count": len(cases),
        "metric_status": "ready",
        "reason": "",
        "source_record_id_count": len(cases),
        "source_record_id_sample": [case["case_id"] for case in cases[:5]],
        "specialties": sorted(
            {case["specialty"] for case in cases if case["specialty"]},
        ),
    }
