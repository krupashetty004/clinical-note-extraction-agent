"""Offline integrity audit for ICD-10 batch predictions.

This audit checks source/evidence integrity, coding-result contracts, candidate
rank/score fields, and exact membership in the imported ICD-10 reference table.
It does not measure clinical correctness or model performance.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence


def _load_jsonl(path: Path, *, id_field: str) -> list[dict[str, Any]]:
    """Load JSONL records and reject malformed or duplicate identifiers."""
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
                    f"{path.name}:{line_number} contains invalid JSON."
                ) from None
            if not isinstance(row, dict):
                raise ValueError(
                    f"{path.name}:{line_number} must be a JSON object."
                )
            record_id = row.get(id_field)
            if not isinstance(record_id, str) or not record_id.strip():
                raise ValueError(
                    f"{path.name}:{line_number} is missing {id_field}."
                )
            if record_id in seen:
                raise ValueError(
                    f"{path.name} contains duplicate {id_field} values."
                )
            seen.add(record_id)
            rows.append(row)
    return rows


def audit_icd10_batch(
    source_rows: Sequence[Mapping[str, Any]],
    prediction_rows: Sequence[Mapping[str, Any]],
    reference_codes: Mapping[str, str],
) -> dict[str, Any]:
    """Audit batch evidence and ICD-10 coding data without clinical claims."""
    errors: list[dict[str, Any]] = []
    source_by_id: dict[str, Mapping[str, Any]] = {}
    prediction_by_id: dict[str, Mapping[str, Any]] = {}

    def add_error(
        code: str,
        *,
        case_id: str | None = None,
        item_index: int | None = None,
        candidate_code: str | None = None,
    ) -> None:
        entry: dict[str, Any] = {"code": code}
        if case_id is not None:
            entry["case_id"] = case_id
        if item_index is not None:
            entry["item_index"] = item_index
        if candidate_code is not None:
            entry["candidate_code"] = candidate_code
        errors.append(entry)

    for index, row in enumerate(source_rows):
        record_id = row.get("record_id")
        if not isinstance(record_id, str) or not record_id.strip():
            add_error("source_record_id_missing", item_index=index)
            continue
        if record_id in source_by_id:
            add_error("duplicate_source_record_id", case_id=record_id)
            continue
        source_by_id[record_id] = row

    for index, row in enumerate(prediction_rows):
        case_id = row.get("case_id")
        if not isinstance(case_id, str) or not case_id.strip():
            add_error("prediction_case_id_missing", item_index=index)
            continue
        if case_id in prediction_by_id:
            add_error("duplicate_prediction_case_id", case_id=case_id)
            continue
        prediction_by_id[case_id] = row

    source_ids = set(source_by_id)
    prediction_ids = set(prediction_by_id)
    missing_predictions = sorted(source_ids - prediction_ids)
    unexpected_predictions = sorted(prediction_ids - source_ids)
    for case_id in missing_predictions:
        add_error("source_record_missing_prediction", case_id=case_id)
    for case_id in unexpected_predictions:
        add_error("prediction_without_source_record", case_id=case_id)

    coding_status_counts: Counter[str] = Counter()
    disposition_counts: Counter[str] = Counter()
    decision_counts: Counter[str] = Counter()
    diagnosis_count = 0
    evidence_checked = 0
    candidate_count = 0
    candidate_code_missing_count = 0
    description_mismatch_count = 0
    weak_candidate_accepted_count = 0
    no_match_accepted_count = 0
    suspected_accepted_count = 0
    ruled_out_accepted_count = 0
    rank_mismatch_count = 0
    score_invalid_count = 0
    candidate_list_mismatch_count = 0

    for case_id, prediction in prediction_by_id.items():
        source = source_by_id.get(case_id)
        if source is None:
            continue

        note = source.get("note_text")
        if not isinstance(note, str):
            add_error("source_note_missing_or_invalid", case_id=case_id)
            continue

        expected_hash = hashlib.sha256(note.encode("utf-8")).hexdigest()
        if prediction.get("note_sha256") != expected_hash:
            add_error("note_sha256_mismatch", case_id=case_id)

        items = prediction.get("items")
        if not isinstance(items, list):
            add_error("prediction_items_invalid", case_id=case_id)
            continue

        for item_index, item in enumerate(items):
            if not isinstance(item, dict):
                add_error(
                    "prediction_item_invalid",
                    case_id=case_id,
                    item_index=item_index,
                )
                continue

            evidence = item.get("evidence_text")
            start = item.get("start_offset")
            end = item.get("end_offset")
            valid_offsets = (
                isinstance(start, int)
                and not isinstance(start, bool)
                and isinstance(end, int)
                and not isinstance(end, bool)
                and 0 <= start < end <= len(note)
            )
            if not valid_offsets or not isinstance(evidence, str):
                add_error(
                    "evidence_span_invalid",
                    case_id=case_id,
                    item_index=item_index,
                )
            else:
                evidence_checked += 1
                if note[start:end] != evidence:
                    add_error(
                        "evidence_text_mismatch",
                        case_id=case_id,
                        item_index=item_index,
                    )

            if item.get("category") != "diagnosis":
                continue

            diagnosis_count += 1
            decision = item.get("decision")
            status = item.get("status")
            coding_status = item.get("icd10_status")
            disposition = item.get("icd10_candidate_disposition")
            reason = item.get("icd10_reason")
            codes = item.get("icd10_candidates")
            details = item.get("icd10_candidate_details")

            decision_counts[str(decision)] += 1
            coding_status_counts[str(coding_status)] += 1
            disposition_counts[str(disposition)] += 1

            if not isinstance(codes, list):
                add_error(
                    "candidate_code_list_invalid",
                    case_id=case_id,
                    item_index=item_index,
                )
                codes = []
            if not isinstance(details, list):
                add_error(
                    "candidate_detail_list_invalid",
                    case_id=case_id,
                    item_index=item_index,
                )
                details = []

            detail_codes = [
                candidate.get("code")
                for candidate in details
                if isinstance(candidate, dict)
            ]
            if len(detail_codes) != len(details) or codes != detail_codes:
                candidate_list_mismatch_count += 1
                add_error(
                    "candidate_code_detail_mismatch",
                    case_id=case_id,
                    item_index=item_index,
                )

            if coding_status == "candidates_found":
                if disposition != "threshold_met" or not details:
                    add_error(
                        "confident_coding_contract_invalid",
                        case_id=case_id,
                        item_index=item_index,
                    )
                if reason not in ("", None):
                    add_error(
                        "confident_coding_has_no_match_reason",
                        case_id=case_id,
                        item_index=item_index,
                    )
            elif coding_status == "no_confident_match":
                expected_disposition = (
                    "weak_matches_for_review" if details else "none"
                )
                if disposition != expected_disposition:
                    add_error(
                        "no_match_disposition_invalid",
                        case_id=case_id,
                        item_index=item_index,
                    )
                if not isinstance(reason, str) or not reason.strip():
                    add_error(
                        "no_match_reason_missing",
                        case_id=case_id,
                        item_index=item_index,
                    )
            elif coding_status == "not_available":
                if codes or details or disposition != "none":
                    add_error(
                        "missing_coding_result_has_candidates",
                        case_id=case_id,
                        item_index=item_index,
                    )
            else:
                add_error(
                    "coding_status_invalid",
                    case_id=case_id,
                    item_index=item_index,
                )

            if disposition == "weak_matches_for_review" and decision == "accepted":
                weak_candidate_accepted_count += 1
                add_error(
                    "weak_candidate_accepted",
                    case_id=case_id,
                    item_index=item_index,
                )
            if coding_status == "no_confident_match" and decision == "accepted":
                no_match_accepted_count += 1
                add_error(
                    "no_confident_match_accepted",
                    case_id=case_id,
                    item_index=item_index,
                )
            if status == "suspected" and decision == "accepted":
                suspected_accepted_count += 1
                add_error(
                    "suspected_diagnosis_accepted",
                    case_id=case_id,
                    item_index=item_index,
                )
            if status == "ruled_out" and decision == "accepted":
                ruled_out_accepted_count += 1
                add_error(
                    "ruled_out_diagnosis_accepted",
                    case_id=case_id,
                    item_index=item_index,
                )

            for rank, candidate in enumerate(details, start=1):
                if not isinstance(candidate, dict):
                    continue
                candidate_count += 1
                code = candidate.get("code")
                description = candidate.get("description")
                actual_rank = candidate.get("rank")

                if actual_rank != rank:
                    rank_mismatch_count += 1
                    add_error(
                        "candidate_rank_invalid",
                        case_id=case_id,
                        item_index=item_index,
                        candidate_code=code if isinstance(code, str) else None,
                    )

                for score_field in (
                    "lexical_score",
                    "semantic_score",
                    "combined_score",
                ):
                    score = candidate.get(score_field)
                    if score is None:
                        continue
                    if (
                        isinstance(score, bool)
                        or not isinstance(score, (int, float))
                        or not math.isfinite(score)
                        or not 0.0 <= score <= 1.0
                    ):
                        score_invalid_count += 1
                        add_error(
                            "candidate_score_invalid",
                            case_id=case_id,
                            item_index=item_index,
                            candidate_code=code if isinstance(code, str) else None,
                        )

                if not isinstance(code, str) or not code:
                    add_error(
                        "candidate_code_invalid",
                        case_id=case_id,
                        item_index=item_index,
                    )
                    continue
                reference_description = reference_codes.get(code)
                if reference_description is None:
                    candidate_code_missing_count += 1
                    add_error(
                        "candidate_code_missing_from_reference",
                        case_id=case_id,
                        item_index=item_index,
                        candidate_code=code,
                    )
                elif description != reference_description:
                    description_mismatch_count += 1
                    add_error(
                        "candidate_description_mismatch",
                        case_id=case_id,
                        item_index=item_index,
                        candidate_code=code,
                    )

    report = {
        "audit_type": "offline_icd10_batch_integrity",
        "clinical_accuracy_evaluated": False,
        "clinical_performance_claimed": False,
        "source_record_count": len(source_rows),
        "prediction_record_count": len(prediction_rows),
        "matched_record_count": len(source_ids & prediction_ids),
        "missing_prediction_count": len(missing_predictions),
        "unexpected_prediction_count": len(unexpected_predictions),
        "diagnosis_item_count": diagnosis_count,
        "evidence_spans_checked": evidence_checked,
        "candidate_count": candidate_count,
        "reference_code_count": len(reference_codes),
        "coding_status_counts": dict(sorted(coding_status_counts.items())),
        "candidate_disposition_counts": dict(sorted(disposition_counts.items())),
        "decision_counts": dict(sorted(decision_counts.items())),
        "candidate_code_missing_count": candidate_code_missing_count,
        "candidate_description_mismatch_count": description_mismatch_count,
        "candidate_rank_mismatch_count": rank_mismatch_count,
        "candidate_score_invalid_count": score_invalid_count,
        "candidate_code_detail_mismatch_count": candidate_list_mismatch_count,
        "weak_candidate_accepted_count": weak_candidate_accepted_count,
        "no_confident_match_accepted_count": no_match_accepted_count,
        "suspected_diagnosis_accepted_count": suspected_accepted_count,
        "ruled_out_diagnosis_accepted_count": ruled_out_accepted_count,
        "integrity_error_count": len(errors),
        "audit_status": "PASS" if not errors else "FAIL",
        "errors": errors,
        "limitations": [
            "This audit checks data integrity and decision-contract consistency only.",
            "Reference-table membership does not prove that a code is clinically appropriate.",
            "Retrieval thresholds are not calibrated clinical confidence scores.",
            "Synthetic data and local deterministic providers do not establish model performance.",
        ],
    }
    return report


def main(argv: Sequence[str] | None = None) -> int:
    """Run the audit against a source queue and batch prediction file."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--predictions", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)

    for path in (args.source, args.predictions):
        if not path.is_file():
            parser.error(f"Input file not found: {path}")
    if args.output.exists():
        parser.error(
            f"Output already exists; choose a new path: {args.output}"
        )

    if __package__ in {None, ""}:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

    import django

    django.setup()

    from dashboard.models import ICDCode

    source_rows = _load_jsonl(args.source, id_field="record_id")
    prediction_rows = _load_jsonl(args.predictions, id_field="case_id")
    reference_codes = dict(
        ICDCode.objects.values_list("code", "description")
    )
    if not reference_codes:
        parser.error(
            "The local ICDCode reference table is empty; import the approved "
            "reference table before running this audit."
        )

    report = audit_icd10_batch(
        source_rows,
        prediction_rows,
        reference_codes,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return 0 if report["audit_status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
