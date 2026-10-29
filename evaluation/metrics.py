"""Dependency-free evaluation metrics for clinical extraction outputs.

Entity matching is exact on category, normalized entity text, and original
note offsets. Evidence-span integrity verifies offsets and quoted text only;
it does not establish semantic clinical support.
"""

from collections import defaultdict
from collections.abc import Mapping, Sequence
from statistics import median
from typing import Any


ENTITY_CATEGORIES = (
    "diagnosis",
    "medication",
    "procedure",
    "allergy",
    "vital_sign",
)

STATUSES_WITH_ACCURACY_METRICS = {"diagnosis", "medication"}
VALID_DECISIONS = {"accepted", "rejected", "needs_review"}


def _normalize_entity(value: str) -> str:
    """Normalize case and repeated whitespace for exact entity matching."""
    return " ".join(value.casefold().split())


def _valid_span(note: str, item: Mapping[str, Any]) -> bool:
    """Return whether evidence exactly matches a valid source-note span."""
    evidence = item.get("evidence_text")
    start = item.get("start_offset")
    end = item.get("end_offset")

    if not isinstance(evidence, str) or not evidence.strip():
        return False

    if (
        isinstance(start, bool)
        or not isinstance(start, int)
        or isinstance(end, bool)
        or not isinstance(end, int)
    ):
        return False

    if start < 0 or end <= start or end > len(note):
        return False

    return note[start:end] == evidence


def _item_key(item: Mapping[str, Any]) -> tuple[object, ...]:
    """Return the fixed exact-matching key, excluding status and evidence."""
    return (
        item["category"],
        _normalize_entity(item["entity"]),
        item["start_offset"],
        item["end_offset"],
    )


def _ratio(numerator: int, denominator: int) -> float | None:
    """Return a rate, or None when no denominator exists."""
    if denominator == 0:
        return None
    return round(numerator / denominator, 6)


def _prf(
    true_positives: int,
    predicted_count: int,
    gold_count: int,
) -> dict[str, Any]:
    """Calculate precision, recall, and F1 with explicit empty-set handling."""
    precision = _ratio(true_positives, predicted_count)
    recall = _ratio(true_positives, gold_count)

    if precision is None or recall is None:
        f1 = None
    elif precision + recall == 0:
        f1 = 0.0
    else:
        f1 = round(
            2 * precision * recall / (precision + recall),
            6,
        )

    return {
        "true_positives": true_positives,
        "predicted_count": predicted_count,
        "gold_count": gold_count,
        "precision": precision,
        "recall": recall,
        "f1": f1,
    }


def _index_cases(
    cases: Sequence[Mapping[str, Any]],
    label: str,
) -> dict[str, Mapping[str, Any]]:
    """Validate case identifiers and create an index."""
    if isinstance(cases, (str, bytes)) or not isinstance(cases, Sequence):
        raise ValueError(f"{label} must be a sequence of case objects.")

    indexed: dict[str, Mapping[str, Any]] = {}

    for position, case in enumerate(cases):
        if not isinstance(case, Mapping):
            raise ValueError(
                f"{label} entry {position} must be an object."
            )

        case_id = case.get("case_id")
        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError(
                f"{label} entry {position} requires a nonblank case_id."
            )

        if case_id in indexed:
            raise ValueError(f"{label} contains a duplicate case_id.")

        indexed[case_id] = case

    return indexed


def _validate_items(
    raw_items: object,
    *,
    case_id: str,
    label: str,
    note: str,
    is_gold: bool,
) -> list[dict[str, Any]]:
    """Validate the basic evaluation item contract."""
    if not isinstance(raw_items, list):
        raise ValueError(
            f"{label} items for case {case_id!r} must be a list."
        )

    validated: list[dict[str, Any]] = []

    for position, raw_item in enumerate(raw_items):
        if not isinstance(raw_item, Mapping):
            raise ValueError(
                f"{label} item {position} in case {case_id!r} "
                "must be an object."
            )

        item = dict(raw_item)
        category = item.get("category")
        entity = item.get("entity")
        evidence = item.get("evidence_text", "")
        start = item.get("start_offset")
        end = item.get("end_offset")

        if category not in ENTITY_CATEGORIES:
            raise ValueError(
                f"{label} item {position} in case {case_id!r} "
                "has an unsupported category."
            )

        if not isinstance(entity, str) or not entity.strip():
            raise ValueError(
                f"{label} item {position} in case {case_id!r} "
                "requires a nonblank entity."
            )

        if not isinstance(evidence, str):
            raise ValueError(
                f"{label} item {position} in case {case_id!r} "
                "requires string evidence_text."
            )

        if (
            isinstance(start, bool)
            or not isinstance(start, int)
            or isinstance(end, bool)
            or not isinstance(end, int)
        ):
            raise ValueError(
                f"{label} item {position} in case {case_id!r} "
                "requires integer offsets."
            )

        item["evidence_text"] = evidence

        status = item.get("status")
        if status is not None and not isinstance(status, str):
            raise ValueError(
                f"{label} item {position} in case {case_id!r} "
                "has an invalid status value."
            )

        if is_gold:
            if not evidence.strip() or not _valid_span(note, item):
                raise ValueError(
                    f"Gold item {position} in case {case_id!r} "
                    "has an invalid evidence span."
                )

            gold_code = item.get("icd10_code")
            if gold_code is not None and (
                category != "diagnosis"
                or not isinstance(gold_code, str)
                or not gold_code.strip()
            ):
                raise ValueError(
                    f"Gold item {position} in case {case_id!r} "
                    "has an invalid ICD-10 code."
                )
        else:
            decision = item.get("decision")
            if decision is not None and decision not in VALID_DECISIONS:
                raise ValueError(
                    f"Predicted item {position} in case {case_id!r} "
                    "has an invalid decision."
                )

            candidates = item.get("icd10_candidates", [])
            if (
                not isinstance(candidates, list)
                or any(
                    not isinstance(code, str) or not code.strip()
                    for code in candidates
                )
            ):
                raise ValueError(
                    f"Predicted item {position} in case {case_id!r} "
                    "has invalid ICD-10 candidates."
                )

        validated.append(item)

    return validated


def evaluate_dataset(
    gold_cases: Sequence[Mapping[str, Any]],
    predicted_cases: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Evaluate predictions against a manually labelled gold dataset.

    Gold case format:
        {
            "case_id": "SYN-001",
            "note": "Assessment: diabetes.",
            "gold_items": [
                {
                    "category": "diagnosis",
                    "entity": "diabetes",
                    "status": "active",
                    "evidence_text": "diabetes",
                    "start_offset": 11,
                    "end_offset": 19,
                    "icd10_code": "E119"
                }
            ],
            "expected_needs_review": False
        }

    Prediction case format:
        {
            "case_id": "SYN-001",
            "items": [
                {
                    "category": "diagnosis",
                    "entity": "diabetes",
                    "status": "active",
                    "evidence_text": "diabetes",
                    "start_offset": 11,
                    "end_offset": 19,
                    "decision": "accepted",
                    "icd10_candidates": ["E119", "R739"]
                }
            ],
            "needs_review": False
        }

    All gold cases must have exactly one corresponding prediction case.
    Failed processing cases should be represented explicitly with an empty
    items list and needs_review=True.
    """
    gold_by_id = _index_cases(gold_cases, "Gold dataset")
    predicted_by_id = _index_cases(predicted_cases, "Predictions")

    if gold_by_id.keys() != predicted_by_id.keys():
        raise ValueError(
            "Gold and prediction case_id sets must match exactly."
        )

    category_counts: dict[str, dict[str, int]] = {
        category: {"true_positives": 0, "predicted_count": 0, "gold_count": 0}
        for category in ENTITY_CATEGORIES
    }
    category_counts["all"] = {
        "true_positives": 0,
        "predicted_count": 0,
        "gold_count": 0,
    }

    evidence_valid_count = 0
    predicted_item_count = 0

    status_correct_count = 0
    status_total_count = 0

    accepted_count = 0
    accepted_correct_count = 0

    icd_total_count = 0
    icd_top1_correct = 0
    icd_top3_correct = 0

    review_tp = 0
    review_fp = 0
    review_fn = 0
    review_tn = 0

    for case_id, gold_case in gold_by_id.items():
        prediction_case = predicted_by_id[case_id]

        note = gold_case.get("note")
        if not isinstance(note, str):
            raise ValueError(
                f"Gold case {case_id!r} requires a string note."
            )

        expected_review = gold_case.get("expected_needs_review")
        observed_review = prediction_case.get("needs_review")

        if not isinstance(expected_review, bool):
            raise ValueError(
                f"Gold case {case_id!r} requires boolean "
                "expected_needs_review."
            )

        if not isinstance(observed_review, bool):
            raise ValueError(
                f"Prediction case {case_id!r} requires boolean needs_review."
            )

        gold_items = _validate_items(
            gold_case.get("gold_items"),
            case_id=case_id,
            label="Gold",
            note=note,
            is_gold=True,
        )
        predicted_items = _validate_items(
            prediction_case.get("items"),
            case_id=case_id,
            label="Predicted",
            note=note,
            is_gold=False,
        )

        gold_by_key: dict[tuple[object, ...], list[tuple[int, dict[str, Any]]]] = (
            defaultdict(list)
        )
        predicted_by_key: dict[
            tuple[object, ...], list[tuple[int, dict[str, Any]]]
        ] = defaultdict(list)

        for index, item in enumerate(gold_items):
            gold_by_key[_item_key(item)].append((index, item))

        for index, item in enumerate(predicted_items):
            predicted_by_key[_item_key(item)].append((index, item))
            predicted_item_count += 1

            if _valid_span(note, item):
                evidence_valid_count += 1

        matched_prediction_indices: set[int] = set()
        matched_gold_to_prediction: dict[
            int, tuple[int, dict[str, Any]]
        ] = {}
        matched_pairs: list[
            tuple[dict[str, Any], dict[str, Any]]
        ] = []

        for key, gold_group in gold_by_key.items():
            predicted_group = predicted_by_key.get(key, [])
            matched_count = min(len(gold_group), len(predicted_group))

            category = str(key[0])
            category_counts[category]["gold_count"] += len(gold_group)
            category_counts[category]["predicted_count"] += len(
                predicted_by_key.get(key, [])
            )
            category_counts[category]["true_positives"] += matched_count

            for (gold_index, gold_item), (
                prediction_index,
                predicted_item,
            ) in zip(
                gold_group[:matched_count],
                predicted_group[:matched_count],
            ):
                matched_prediction_indices.add(prediction_index)
                matched_gold_to_prediction[gold_index] = (
                    prediction_index,
                    predicted_item,
                )
                matched_pairs.append((gold_item, predicted_item))

        # Count prediction-only entities, including false positives.
        for key, predicted_group in predicted_by_key.items():
            if key not in gold_by_key:
                category = str(key[0])
                category_counts[category]["predicted_count"] += len(
                    predicted_group
                )

        for category in ENTITY_CATEGORIES:
            category_counts[category]["gold_count"] += 0

        # Calculate status accuracy only for matched diagnoses/medications
        # whose gold record defines a status.
        for gold_item, predicted_item in matched_pairs:
            if (
                predicted_item.get("decision") == "accepted"
                and gold_item["category"] in STATUSES_WITH_ACCURACY_METRICS
                and gold_item.get("status") is not None
            ):
                status_total_count += 1

                if predicted_item.get("status") == gold_item.get("status"):
                    status_correct_count += 1

        # Accepted-item agreement is measured only where the prediction
        # explicitly marks the item as accepted.
        for prediction_index, item in enumerate(predicted_items):
            if item.get("decision") == "accepted":
                accepted_count += 1
                if (
                    prediction_index in matched_prediction_indices
                    and _valid_span(note, item)
                ):
                    accepted_correct_count += 1

        # Coding denominator includes every gold diagnosis with a label.
        # A missing/missed diagnosis therefore counts as a coding miss.
        for gold_index, gold_item in enumerate(gold_items):
            expected_code = gold_item.get("icd10_code")
            if gold_item["category"] != "diagnosis" or not expected_code:
                continue

            icd_total_count += 1
            paired = matched_gold_to_prediction.get(gold_index)

            if paired is None:
                continue

            predicted_item = paired[1]
            candidates = [
                code.upper()
                for code in predicted_item.get("icd10_candidates", [])
            ]
            target = expected_code.upper()

            if candidates and candidates[0] == target:
                icd_top1_correct += 1
            if target in candidates[:3]:
                icd_top3_correct += 1

        if expected_review and observed_review:
            review_tp += 1
        elif not expected_review and observed_review:
            review_fp += 1
        elif expected_review and not observed_review:
            review_fn += 1
        else:
            review_tn += 1

    total_tp = sum(
        category_counts[category]["true_positives"]
        for category in ENTITY_CATEGORIES
    )
    total_predicted = sum(
        category_counts[category]["predicted_count"]
        for category in ENTITY_CATEGORIES
    )
    total_gold = sum(
        category_counts[category]["gold_count"]
        for category in ENTITY_CATEGORIES
    )

    category_metrics = {
        category: _prf(
            category_counts[category]["true_positives"],
            category_counts[category]["predicted_count"],
            category_counts[category]["gold_count"],
        )
        for category in ENTITY_CATEGORIES
    }
    category_metrics["all"] = _prf(
        total_tp,
        total_predicted,
        total_gold,
    )

    return {
        "case_count": len(gold_by_id),
        "matching_rule": (
            "Exact category, case/whitespace-normalized entity, and "
            "exact original-note start/end offsets."
        ),
        "category_metrics": category_metrics,
        "evidence_span_integrity": {
            "valid_spans": evidence_valid_count,
            "predicted_items": predicted_item_count,
            "rate": _ratio(evidence_valid_count, predicted_item_count),
            "limitation": (
                "Exact substring integrity does not by itself prove "
                "semantic clinical support."
            ),
        },
        "accepted_item_gold_match_rate": {
            "correctly_matched": accepted_correct_count,
            "accepted_items": accepted_count,
            "rate": _ratio(accepted_correct_count, accepted_count),
            "limitation": (
                "This is a gold-match proxy, not a substitute for "
                "manual semantic evidence review."
            ),
        },
        "status_accuracy": {
            "correct": status_correct_count,
            "matched_items_with_gold_status": status_total_count,
            "accuracy": _ratio(status_correct_count, status_total_count),
        },
        "icd10": {
            "top1_correct": icd_top1_correct,
            "top3_correct": icd_top3_correct,
            "labelled_diagnoses": icd_total_count,
            "top1_accuracy": _ratio(icd_top1_correct, icd_total_count),
            "top3_accuracy": _ratio(icd_top3_correct, icd_total_count),
        },
        "review_detection": {
            **_prf(
                review_tp,
                review_tp + review_fp,
                review_tp + review_fn,
            ),
            "false_positives": review_fp,
            "false_negatives": review_fn,
            "true_negatives": review_tn,
        },
    }


def _measured_numbers(
    records: Sequence[Mapping[str, Any]],
    field: str,
) -> list[float]:
    values: list[float] = []
    for record in records:
        value = record.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            continue
        if value >= 0:
            values.append(float(value))
    return values


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(
        len(ordered) - 1,
        max(0, round((len(ordered) - 1) * percentile)),
    )
    return round(ordered[index], 6)


def evaluate_operational_metrics(
    records: Sequence[Mapping[str, Any]],
    *,
    system_name: str = "agent",
) -> dict[str, Any]:
    """Summarize only recorded operational measurements.

    Missing latency, call, retry, and failure fields remain unmeasured rather
    than being treated as zero. This function does not execute providers.
    """
    if isinstance(records, (str, bytes)) or not isinstance(records, Sequence):
        raise ValueError("records must be a sequence of objects.")
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            raise ValueError(f"records[{index}] must be an object.")

    latencies = _measured_numbers(records, "latency_ms")
    calls = _measured_numbers(records, "model_calls")
    retries = _measured_numbers(records, "retry_count")
    failures = [
        record for record in records
        if isinstance(record.get("failure_code"), str)
        and bool(record.get("failure_code"))
    ]
    completed = [
        record for record in records
        if record.get("status") in {"completed", "needs_review"}
    ]

    return {
        "system": system_name,
        "record_count": len(records),
        "measured_latency_records": len(latencies),
        "latency_ms": {
            "median": round(median(latencies), 6) if latencies else None,
            "p95": _percentile(latencies, 0.95),
            "under_30_seconds_rate": (
                _ratio(sum(value < 30000 for value in latencies), len(latencies))
                if latencies else None
            ),
        },
        "model_calls": {
            "measured_records": len(calls),
            "total": int(sum(calls)) if calls else None,
            "average": round(sum(calls) / len(calls), 6) if calls else None,
        },
        "retries": {
            "measured_records": len(retries),
            "total": int(sum(retries)) if retries else None,
            "average": round(sum(retries) / len(retries), 6) if retries else None,
        },
        "failures": {
            "records_with_failure_code": len(failures),
            "rate": _ratio(len(failures), len(records)),
            "completed_or_reviewable_records": len(completed),
        },
        "limitations": [
            "Metrics reflect recorded runs only; missing operational fields are not imputed.",
            "Latency and call counts are not evidence of clinical quality.",
        ],
    }


def compare_system_metrics(
    agent_records: Sequence[Mapping[str, Any]],
    baseline_records: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Compare measured operational summaries without claiming superiority."""
    agent = evaluate_operational_metrics(agent_records, system_name="agent")
    baseline = evaluate_operational_metrics(
        baseline_records,
        system_name="baseline",
    )
    return {
        "agent": agent,
        "baseline": baseline,
        "comparison_status": (
            "measured"
            if agent["record_count"] and baseline["record_count"]
            else "Not yet measured"
        ),
        "limitation": (
            "Operational comparison is descriptive; clinical superiority "
            "requires the same qualified gold cases and paired evaluation."
        ),
    }


def select_poor_performing_cases(
    case_results: Sequence[Mapping[str, Any]],
    *,
    limit: int = 3,
) -> list[dict[str, Any]]:
    """Return recorded poor cases, ranked by observed error burden.

    Cases must explicitly contain measured error fields. No case is labelled
    poor merely because data is missing.
    """
    if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
        raise ValueError("limit must be a positive integer.")
    scored: list[tuple[int, dict[str, Any]]] = []
    for index, raw in enumerate(case_results):
        if not isinstance(raw, Mapping):
            raise ValueError(f"case_results[{index}] must be an object.")
        if raw.get("gold_qualified") is not True:
            continue
        error_count = raw.get("error_count")
        if isinstance(error_count, bool) or not isinstance(error_count, int):
            continue
        if error_count <= 0:
            continue
        scored.append((error_count, dict(raw)))
    scored.sort(
        key=lambda pair: (
            -pair[0],
            str(pair[1].get("case_id", "")),
        )
    )
    return [case for _score, case in scored[:limit]]


def evaluate_qualified_dataset(
    gold_cases: Sequence[Mapping[str, Any]],
    predicted_cases: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Evaluate only cases explicitly marked as independently qualified gold."""
    if not gold_cases:
        raise ValueError("No qualified gold cases were supplied.")
    for index, case in enumerate(gold_cases):
        if not isinstance(case, Mapping) or case.get("gold_qualified") is not True:
            raise ValueError(
                f"Gold case {index} is not explicitly qualified."
            )
    result = evaluate_dataset(gold_cases, predicted_cases)
    result["gold_qualification"] = {
        "qualified_cases": len(gold_cases),
        "source": "caller-supplied qualified annotations",
        "clinical_accuracy_claimed": False,
    }
    return result


def build_sow_evaluation_report(
    gold_cases: Sequence[Mapping[str, Any]],
    agent_predictions: Sequence[Mapping[str, Any]],
    *,
    baseline_predictions: Sequence[Mapping[str, Any]] | None = None,
    agent_operational_records: Sequence[Mapping[str, Any]] | None = None,
    baseline_operational_records: Sequence[Mapping[str, Any]] | None = None,
    challenge_report: Mapping[str, Any] | None = None,
    case_results: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build a non-fabricating SOW report from qualified and recorded inputs."""
    agent = evaluate_qualified_dataset(gold_cases, agent_predictions)
    baseline = (
        evaluate_qualified_dataset(gold_cases, baseline_predictions)
        if baseline_predictions is not None
        else None
    )
    report: dict[str, Any] = {
        "clinical_accuracy_claimed": False,
        "gold_cases": len(gold_cases),
        "agent": agent,
        "baseline": baseline,
        "operational": (
            evaluate_operational_metrics(agent_operational_records)
            if agent_operational_records is not None
            else None
        ),
        "baseline_operational": (
            evaluate_operational_metrics(
                baseline_operational_records,
                system_name="baseline",
            )
            if baseline_operational_records is not None
            else None
        ),
        "challenge_sets": dict(challenge_report) if challenge_report is not None else None,
        "three_poor_performing_cases": (
            select_poor_performing_cases(case_results)
            if case_results is not None
            else []
        ),
        "limitations": [
            "Clinical targets are computed only from explicitly qualified gold cases.",
            "No score is inferred for missing baseline, challenge, operational, or poor-case inputs.",
            "Human adjudication and provider execution remain external prerequisites.",
        ],
    }
    if baseline is None:
        report["baseline_status"] = "Not yet measured"
    else:
        report["baseline_status"] = "Measured descriptively"
    if challenge_report is None:
        report["challenge_status"] = "Not yet measured"
    else:
        report["challenge_status"] = "Recorded challenge report supplied"
    return report


__all__ = [
    "compare_system_metrics",
    "build_sow_evaluation_report",
    "evaluate_dataset",
    "evaluate_qualified_dataset",
    "evaluate_operational_metrics",
    "select_poor_performing_cases",
]