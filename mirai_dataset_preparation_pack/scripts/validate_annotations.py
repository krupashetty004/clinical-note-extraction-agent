#!/usr/bin/env python3
"""Validate manually completed annotation JSONL without calling a model."""
from __future__ import annotations
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

REQUIRED_TYPES = ("diagnoses", "procedures", "medications", "allergies", "vital_signs", "icd10_cm_codes")
ENTITY_TYPES = ("diagnoses", "procedures", "medications", "allergies", "vital_signs")
SOURCE_ID = "kaggle:tboyle10/medicaltranscriptions"
SOURCE_URL = "https://www.kaggle.com/datasets/tboyle10/medicaltranscriptions/data"
CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9]{2,6}$")
DIAGNOSIS_STATUSES = {"active", "historical", "ruled_out", "suspected"}
MEDICATION_STATUSES = {"current", "discontinued", "newly_prescribed"}
CONFLICT_STATUSES = {"not_reviewed", "not_applicable", "resolved"}
TOKEN_PATTERN = re.compile(r"[^\W_]+(?:['’-][^\W_]+)*", re.UNICODE)


def load_icd_reference(path: Path | None) -> dict[str, str] | None:
    """Load the supplied fixed-width ICD-10-CM reference when requested."""
    if path is None:
        return None
    reference: dict[str, str] = {}
    with path.open("r", encoding="utf-8-sig") as handle:
        for line_number, line in enumerate(handle, start=1):
            value = line.rstrip("\r\n")
            if len(value) < 9:
                raise ValueError(f"ICD reference line {line_number} is too short")
            code = value[:7].strip().upper()
            description = value[8:].strip()
            if not CODE_PATTERN.fullmatch(code) or not description:
                raise ValueError(f"ICD reference line {line_number} is invalid")
            reference[code] = description
    return reference


def _tokens(value: str) -> set[str]:
    return {token.casefold() for token in TOKEN_PATTERN.findall(value)}


def validate_record(
    record: dict,
    line_number: int,
    *,
    icd_reference: dict[str, str] | None = None,
) -> list[str]:
    errors: list[str] = []
    prefix = f"line {line_number} ({record.get('record_id', 'unknown-id')}): "
    note_text = record.get("note_text")
    if not isinstance(note_text, str) or not note_text:
        return [prefix + "note_text must be a non-empty string"]
    if record.get("source_dataset") != SOURCE_ID:
        errors.append(prefix + "source_dataset does not match the declared source")
    if record.get("source_url") != SOURCE_URL:
        errors.append(prefix + "source_url does not match the declared source")
    if (
        isinstance(record.get("source_row_number"), bool)
        or not isinstance(record.get("source_row_number"), int)
        or record["source_row_number"] < 1
    ):
        errors.append(prefix + "source_row_number must be a positive integer")
    if not isinstance(record.get("record_id"), str) or not record["record_id"].strip():
        errors.append(prefix + "record_id must be a non-empty string")
    if not record.get("annotation_complete", False):
        return errors  # An unreviewed template is valid as a template, not as gold data.
    gold = record.get("gold_annotations")
    if not isinstance(gold, dict):
        return [prefix + "completed annotation requires a gold_annotations object"]
    for key in REQUIRED_TYPES:
        if not isinstance(gold.get(key), list):
            errors.append(prefix + f"completed annotation requires '{key}' to be a list (empty means reviewed and none found)")
    if errors:
        return errors
    for category in ENTITY_TYPES:
        seen_spans: dict[tuple[int, int], dict] = {}
        for index, item in enumerate(gold[category]):
            if not isinstance(item, dict):
                errors.append(prefix + f"{category}[{index}] must be an object")
                continue
            evidence = item.get("evidence_text")
            entity = item.get("entity")
            if not isinstance(entity, str) or not entity.strip():
                errors.append(prefix + f"{category}[{index}] requires a non-empty entity")
            start = item.get("start_offset")
            end = item.get("end_offset")
            if not isinstance(evidence, str) or not evidence:
                errors.append(prefix + f"{category}[{index}] requires non-empty evidence_text")
                continue
            if not isinstance(start, int) or isinstance(start, bool) or not isinstance(end, int) or isinstance(end, bool):
                errors.append(prefix + f"{category}[{index}] requires integer offsets")
                continue
            if start < 0 or end < start or end > len(note_text):
                errors.append(prefix + f"{category}[{index}] offsets are outside the note")
                continue
            if note_text[start:end] != evidence:
                errors.append(prefix + f"{category}[{index}] evidence_text does not match note_text at offsets")
            if isinstance(entity, str) and not _tokens(entity).issubset(
                _tokens(evidence)
            ):
                errors.append(
                    prefix
                    + f"{category}[{index}] entity is not grounded in evidence_text"
                )
            status = item.get("status")
            if category in {"diagnoses", "medications"} and (
                not isinstance(status, str) or not status.strip()
            ):
                errors.append(prefix + f"{category}[{index}] requires status/assertion")
            elif category == "diagnoses" and status not in DIAGNOSIS_STATUSES:
                errors.append(prefix + f"{category}[{index}] has unsupported status")
            elif category == "medications" and status not in MEDICATION_STATUSES:
                errors.append(prefix + f"{category}[{index}] has unsupported status")
            if category not in {"diagnoses", "medications"} and status is not None:
                errors.append(prefix + f"{category}[{index}] must not define status")
            span = (start, end)
            previous = seen_spans.get(span)
            if previous is not None and (
                previous.get("entity") != entity
                or previous.get("status") != status
            ):
                errors.append(
                    prefix
                    + f"{category}[{index}] conflicts with another annotation "
                    "at the same source span"
                )
            seen_spans[span] = item
    for code_item in gold["icd10_cm_codes"]:
        if (
            not isinstance(code_item, dict)
            or not isinstance(code_item.get("code"), str)
            or not CODE_PATTERN.fullmatch(code_item["code"].strip().upper())
        ):
            errors.append(prefix + "each icd10_cm_codes item must be an object containing a non-empty code string")
        elif not isinstance(code_item.get("description"), str) or not code_item["description"].strip():
            errors.append(prefix + "each ICD-10-CM code requires a reference description")
        elif icd_reference is not None:
            code = code_item["code"].strip().upper()
            description = code_item["description"].strip()
            if code not in icd_reference:
                errors.append(prefix + f"ICD-10-CM code {code} is absent from the supplied reference")
            elif icd_reference[code] != description:
                errors.append(prefix + f"ICD-10-CM description does not match code {code}")
    if record.get("adjudication_status") not in {"adjudicated", "not_required"}:
        errors.append(prefix + "completed record must set adjudication_status to 'adjudicated' or 'not_required'")
    if not isinstance(record.get("annotator_id"), str) or not record["annotator_id"].strip():
        errors.append(prefix + "completed record requires annotator_id (pseudonymous ID is acceptable)")
    conflict_status = record.get("conflict_status")
    if conflict_status not in CONFLICT_STATUSES:
        errors.append(
            prefix
            + "completed record requires conflict_status of "
            "'not_applicable' or 'resolved'"
        )
    if conflict_status == "resolved" and not (
        isinstance(record.get("conflict_notes"), str)
        and record["conflict_notes"].strip()
    ):
        errors.append(prefix + "resolved conflicts require conflict_notes")
    return errors


def qualification_errors(
    record: dict,
    line_number: int,
    *,
    icd_reference: dict[str, str] | None = None,
) -> list[str]:
    """Return errors that prevent a completed record from gold evaluation."""
    errors = validate_record(
        record,
        line_number,
        icd_reference=icd_reference,
    )
    prefix = f"line {line_number} ({record.get('record_id', 'unknown-id')}): "
    if record.get("annotation_complete") is not True:
        errors.append(prefix + "record is not annotation_complete")
    if record.get("annotation_status") not in {"complete", "adjudicated"}:
        errors.append(prefix + "annotation_status must be complete or adjudicated")
    if record.get("adjudication_status") != "adjudicated":
        errors.append(prefix + "record requires adjudication_status='adjudicated'")
    if not isinstance(record.get("adjudicator_id"), str) or not record["adjudicator_id"].strip():
        errors.append(prefix + "record requires a pseudonymous adjudicator_id")
    if record.get("adjudicator_id") == record.get("annotator_id"):
        errors.append(prefix + "adjudicator_id must differ from annotator_id")
    if not isinstance(record.get("adjudication_notes"), str) or not record["adjudication_notes"].strip():
        errors.append(prefix + "record requires adjudication_notes")
    qualification = record.get("annotator_qualification")
    if not isinstance(qualification, dict) or qualification.get("qualified") is not True:
        errors.append(prefix + "record requires qualified annotator evidence")
    if record.get("conflict_status") not in {"resolved", "not_applicable"}:
        errors.append(prefix + "record requires reviewed conflict status")
    if not isinstance(record.get("conflict_notes"), str) or not record["conflict_notes"].strip():
        errors.append(prefix + "record requires conflict review notes")
    if record.get("label_source") not in {
        "human_annotated",
        "external_gold_standard",
    }:
        errors.append(
            prefix
            + "record requires label_source='human_annotated' or "
            "'external_gold_standard'; AI-generated labels are not clinical gold"
        )
    provenance = record.get("label_provenance")
    if not isinstance(provenance, dict) or not all(
        isinstance(provenance.get(field), str) and provenance[field].strip()
        for field in ("dataset_version", "annotation_guidelines", "license_or_dua")
    ):
        errors.append(
            prefix
            + "record requires label_provenance with dataset_version, "
            "annotation_guidelines, and license_or_dua"
        )
    return errors


def evaluation_ready_records(
    records: list[dict],
    *,
    icd_reference: dict[str, str] | None = None,
) -> tuple[list[dict], list[str]]:
    """Return only independently qualified records; never infer eligibility."""
    ready: list[dict] = []
    errors: list[str] = []
    for line_number, record in enumerate(records, start=1):
        record_errors = qualification_errors(
            record,
            line_number,
            icd_reference=icd_reference,
        )
        if record_errors:
            errors.extend(record_errors)
        else:
            exported = dict(record)
            exported["clinical_performance_eligible"] = True
            ready.append(exported)
    return ready, errors


def evaluation_cases_from_records(
    records: list[dict],
    *,
    icd_reference: dict[str, str] | None = None,
) -> tuple[list[dict], list[str]]:
    """Convert qualified annotations to the evaluator's gold-case format."""
    qualified, errors = evaluation_ready_records(
        records,
        icd_reference=icd_reference,
    )
    cases: list[dict] = []
    for record in qualified:
        prefix = f"{record.get('record_id', 'unknown-id')}: "
        expected_review = record.get("expected_needs_review")
        if not isinstance(expected_review, bool):
            errors.append(prefix + "requires explicit expected_needs_review")
            continue
        annotations = record["gold_annotations"]
        items: list[dict] = []
        category_map = {
            "diagnoses": "diagnosis",
            "procedures": "procedure",
            "medications": "medication",
            "allergies": "allergy",
            "vital_signs": "vital_sign",
        }
        for source_category, category in category_map.items():
            for item in annotations[source_category]:
                exported = dict(item)
                exported["category"] = category
                items.append(exported)
        cases.append(
            {
                "case_id": record["record_id"],
                "note": record["note_text"],
                "gold_items": items,
                "expected_needs_review": expected_review,
                "gold_qualified": True,
                "source_dataset": record["source_dataset"],
                "source_row_number": record["source_row_number"],
            }
        )
    return cases, errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="Annotation JSONL file")
    parser.add_argument("--require-complete", action="store_true", help="Fail if any record remains unannotated or unaudjudicated")
    parser.add_argument("--export-qualified", type=Path, help="Write only independently qualified gold records")
    parser.add_argument("--export-evaluation-cases", type=Path, help="Write qualified records in evaluation gold-case format")
    parser.add_argument("--require-qualified", action="store_true", help="Fail unless every record is independently qualified gold")
    parser.add_argument("--icd-reference", type=Path, help="Optional fixed-width ICD-10-CM reference for exact code/description validation")
    args = parser.parse_args(argv)
    if not args.input.is_file():
        print(f"ANNOTATION_VALIDATION_FAILED: file not found: {args.input}", file=sys.stderr)
        return 2
    try:
        icd_reference = load_icd_reference(args.icd_reference)
    except (OSError, ValueError) as exc:
        print(f"ANNOTATION_VALIDATION_FAILED: {exc}", file=sys.stderr)
        return 2
    records = []
    errors: list[str] = []
    with args.input.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                errors.append(f"line {line_number}: invalid JSON: {exc.msg}")
                continue
            if not isinstance(item, dict):
                errors.append(f"line {line_number}: record must be a JSON object")
                continue
            records.append(item)
            errors.extend(
                validate_record(
                    item,
                    line_number,
                    icd_reference=icd_reference,
                )
            )
    ids = [r.get("record_id") for r in records]
    duplicate_ids = [record_id for record_id, count in Counter(ids).items() if count > 1]
    if duplicate_ids:
        errors.append(f"duplicate record_id values found: {len(duplicate_ids)}")
    complete = [r for r in records if r.get("annotation_complete") is True]
    qualified, qualification_errors_found = evaluation_ready_records(
        records,
        icd_reference=icd_reference,
    )
    if args.export_qualified:
        args.export_qualified.parent.mkdir(parents=True, exist_ok=True)
        with args.export_qualified.open("w", encoding="utf-8", newline="\n") as handle:
            for record in qualified:
                handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
    if args.export_evaluation_cases:
        cases, case_errors = evaluation_cases_from_records(
            records,
            icd_reference=icd_reference,
        )
        errors.extend(case_errors if args.require_qualified else [])
        args.export_evaluation_cases.parent.mkdir(parents=True, exist_ok=True)
        with args.export_evaluation_cases.open("w", encoding="utf-8", newline="\n") as handle:
            for case in cases:
                handle.write(json.dumps(case, ensure_ascii=False, sort_keys=True) + "\n")
    errors.extend(qualification_errors_found if args.require_qualified else [])
    complete_specialties = {r.get("specialty") for r in complete if r.get("specialty")}
    print(json.dumps({
        "records_loaded": len(records),
        "completed_annotations": len(complete),
        "unreviewed_or_incomplete": len(records) - len(complete),
        "specialties_among_completed": len(complete_specialties),
        "duplicate_record_ids": len(duplicate_ids),
        "qualified_gold_records": len(qualified),
        "qualification_errors": len(qualification_errors_found),
        "validation_errors": len(errors),
        "gold_evaluation_ready": (
            not errors
            and len(qualified) > 0
            and (not args.require_complete or len(complete) == len(records))
            and (not args.require_qualified or len(qualified) == len(records))
        ),
    }, indent=2))
    for error in errors[:50]:
        print(f"ERROR: {error}", file=sys.stderr)
    if len(errors) > 50:
        print(f"... {len(errors) - 50} additional errors suppressed", file=sys.stderr)
    if args.require_complete and len(complete) != len(records):
        print("ERROR: --require-complete set but some records remain incomplete.", file=sys.stderr)
        return 1
    return 1 if errors else 0

if __name__ == "__main__":
    raise SystemExit(main())
