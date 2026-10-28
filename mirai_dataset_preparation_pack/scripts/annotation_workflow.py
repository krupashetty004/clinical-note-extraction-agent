#!/usr/bin/env python3
"""Manage local MTSamples annotation imports, progress, and safe exports.

This tool never turns suggestions into gold labels. Imported annotations must
retain the queue's immutable note/provenance fields and are validated before
being exported or counted as qualified.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

PACKAGE_ROOT = Path(__file__).resolve().parents[1]
VALIDATOR_PATH = Path(__file__).with_name("validate_annotations.py")
if __package__ in {None, ""}:
    sys.path.insert(0, str(VALIDATOR_PATH.parent.parent.parent))

import importlib.util


def _load_validator():
    spec = importlib.util.spec_from_file_location(
        "validate_annotations_for_workflow",
        VALIDATOR_PATH,
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Could not load annotation validator.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


VALIDATOR = _load_validator()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    """Load JSONL records and reject malformed or duplicate IDs."""
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON") from exc
            if not isinstance(record, dict):
                raise ValueError(f"{path}:{line_number}: record must be an object")
            record_id = record.get("record_id")
            if not isinstance(record_id, str) or not record_id.strip():
                raise ValueError(f"{path}:{line_number}: record_id is required")
            if record_id in seen:
                raise ValueError(f"{path}:{line_number}: duplicate record_id")
            seen.add(record_id)
            records.append(record)
    return records


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    """Write deterministic UTF-8 JSONL, refusing accidental overwrite."""
    if path.exists():
        raise FileExistsError(f"Refusing to overwrite existing file: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(
                json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n"
            )


def progress_report(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize preparation, annotation, adjudication, qualification, and specialties."""
    specialty_counts = Counter(
        record.get("specialty") or "Unknown / missing specialty"
        for record in records
    )
    annotated = [
        record for record in records
        if record.get("annotation_complete") is True
    ]
    adjudicated = [
        record for record in records
        if record.get("adjudication_status") == "adjudicated"
    ]
    qualified, qualification_errors = VALIDATOR.evaluation_ready_records(records)
    return {
        "prepared_notes": len(records),
        "annotated_notes": len(annotated),
        "adjudicated_notes": len(adjudicated),
        "qualified_notes": len(qualified),
        "remaining_annotation": len(records) - len(annotated),
        "remaining_adjudication": len(records) - len(adjudicated),
        "qualification_errors": len(qualification_errors),
        "specialties_total": len(
            [name for name in specialty_counts if name != "Unknown / missing specialty"]
        ),
        "specialties_in_queue": len(
            {
                record.get("specialty")
                for record in records
                if record.get("specialty")
            }
        ),
        "specialty_counts": dict(sorted(specialty_counts.items())),
        "gold_ready": bool(records) and len(qualified) == len(records),
    }


def merge_import(
    queue: list[dict[str, Any]],
    incoming: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Merge reviewer fields while preserving immutable queue/source fields."""
    queue_by_id = {record["record_id"]: record for record in queue}
    if set(record["record_id"] for record in incoming) - set(queue_by_id):
        raise ValueError("Imported records contain IDs outside the annotation queue.")

    immutable = {
        "record_id",
        "source_dataset",
        "source_url",
        "source_row_number",
        "specialty",
        "note_text",
        "source_keywords",
    }
    merged = []
    incoming_by_id = {record["record_id"]: record for record in incoming}
    for original in queue:
        update = incoming_by_id.get(original["record_id"])
        if update is None:
            merged.append(original)
            continue
        for field in immutable:
            if update.get(field) != original.get(field):
                raise ValueError(
                    f"Imported record {original['record_id']} changes immutable field {field}."
                )
        validation_errors = VALIDATOR.validate_record(update, 0)
        if validation_errors:
            raise ValueError(
                f"Imported record {original['record_id']} is invalid: "
                + "; ".join(validation_errors)
            )
        combined = dict(original)
        for key, value in update.items():
            if key not in immutable:
                combined[key] = value
        merged.append(combined)
    return merged


def provisional_suggestions(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Create clearly unverified keyword suggestions outside gold_annotations."""
    suggestions: list[dict[str, Any]] = []
    for record in records:
        raw_keywords = record.get("source_keywords") or ""
        terms = [term.strip() for term in raw_keywords.split(",") if term.strip()]
        items = []
        for term in terms:
            start = record["note_text"].casefold().find(term.casefold())
            if start >= 0:
                evidence = record["note_text"][start:start + len(term)]
                items.append(
                    {
                        "term": term,
                        "evidence_text": evidence,
                        "start_offset": start,
                        "end_offset": start + len(evidence),
                        "verified": False,
                        "source": "source_keywords",
                    }
                )
        suggestions.append(
            {
                "record_id": record["record_id"],
                "suggestions_are_unverified": True,
                "items": items,
            }
        )
    return suggestions


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--queue", type=Path, required=True)
    parser.add_argument("--import-annotations", type=Path)
    parser.add_argument("--merged-output", type=Path)
    parser.add_argument("--progress", action="store_true")
    parser.add_argument("--export-qualified", type=Path)
    parser.add_argument("--suggestions", type=Path)
    args = parser.parse_args(argv)

    try:
        queue = load_jsonl(args.queue)
        if args.import_annotations:
            imported = load_jsonl(args.import_annotations)
            queue = merge_import(queue, imported)
        if args.merged_output:
            write_jsonl(args.merged_output, queue)
        if args.export_qualified:
            qualified, errors = VALIDATOR.evaluation_ready_records(queue)
            if errors:
                raise ValueError(
                    f"{len(errors)} records are not qualified; refusing gold export."
                )
            write_jsonl(args.export_qualified, qualified)
        if args.suggestions:
            write_jsonl(args.suggestions, provisional_suggestions(queue))
        if args.progress or not any(
            (args.merged_output, args.export_qualified, args.suggestions)
        ):
            print(json.dumps(progress_report(queue), indent=2, sort_keys=True))
    except (OSError, ValueError) as exc:
        print(f"ANNOTATION_WORKFLOW_FAILED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
