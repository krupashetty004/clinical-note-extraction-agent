"""Small deterministic synthetic dataset for evaluation smoke tests.

All predictions are handcrafted fixtures. They are not model outputs and
must not be reported as clinical performance.
"""


def _span(note: str, evidence: str) -> dict:
    """Build exact, end-exclusive offsets for a known note substring."""
    start = note.find(evidence)
    if start < 0:
        raise ValueError("Synthetic evidence is not present in its note.")

    return {
        "evidence_text": evidence,
        "start_offset": start,
        "end_offset": start + len(evidence),
    }


def _gold_item(
    note: str,
    category: str,
    entity: str,
    evidence: str,
    *,
    status: str | None = None,
    icd10_code: str | None = None,
) -> dict:
    item = {
        "category": category,
        "entity": entity,
        **_span(note, evidence),
    }

    if status is not None:
        item["status"] = status

    if icd10_code is not None:
        item["icd10_code"] = icd10_code

    return item


def _prediction_item(
    note: str,
    category: str,
    entity: str,
    evidence: str,
    *,
    status: str | None = None,
    decision: str = "accepted",
    icd10_candidates: list[str] | None = None,
) -> dict:
    item = {
        "category": category,
        "entity": entity,
        **_span(note, evidence),
        "decision": decision,
        "icd10_candidates": list(icd10_candidates or []),
    }

    if status is not None:
        item["status"] = status

    return item


def build_synthetic_smoke_set() -> tuple[list[dict], list[dict]]:
    """Return matching gold and fixture-prediction cases.

    The small set deliberately includes a missed diagnosis, a false-positive
    diagnosis, a status error, uncertain/ruled-out findings, and several
    entity categories. It is a smoke test, not the SOW gold standard.
    """
    gold_cases: list[dict] = []
    prediction_cases: list[dict] = []

    def add_case(
        case_id: str,
        specialty: str,
        note: str,
        gold_items: list[dict],
        predicted_items: list[dict],
        *,
        expected_needs_review: bool,
        predicted_needs_review: bool,
    ) -> None:
        gold_cases.append(
            {
                "case_id": case_id,
                "specialty": specialty,
                "note": note,
                "gold_items": gold_items,
                "expected_needs_review": expected_needs_review,
            }
        )

        prediction_cases.append(
            {
                "case_id": case_id,
                "items": predicted_items,
                "needs_review": predicted_needs_review,
            }
        )

    # 1. Correct diagnosis, medication, evidence and code ranking.
    note = "Assessment: hypertension. Medication: lisinopril."

    add_case(
        "SYN-EVAL-001",
        "Cardiology",
        note,
        [
            _gold_item(
                note,
                "diagnosis",
                "hypertension",
                "hypertension",
                status="active",
                icd10_code="I10",
            ),
            _gold_item(
                note,
                "medication",
                "lisinopril",
                "lisinopril",
                status="current",
            ),
        ],
        [
            _prediction_item(
                note,
                "diagnosis",
                "hypertension",
                "hypertension",
                status="active",
                # Codes use the local ICDCode table's representation.
                icd10_candidates=["I10", "R030"],
            ),
            _prediction_item(
                note,
                "medication",
                "lisinopril",
                "lisinopril",
                status="current",
            ),
        ],
        expected_needs_review=False,
        predicted_needs_review=False,
    )

    # 2. Ruled-out diagnosis.
    note = "Assessment: diabetes was ruled out."

    add_case(
        "SYN-EVAL-002",
        "Endocrinology",
        note,
        [
            _gold_item(
                note,
                "diagnosis",
                "diabetes",
                "diabetes",
                status="ruled_out",
            ),
        ],
        [
            _prediction_item(
                note,
                "diagnosis",
                "diabetes",
                "diabetes",
                status="ruled_out",
                decision="needs_review",
            ),
        ],
        expected_needs_review=True,
        predicted_needs_review=True,
    )

    # 3. Uncertain diagnosis.
    note = "Assessment: possible pneumonia."

    add_case(
        "SYN-EVAL-003",
        "Respiratory Medicine",
        note,
        [
            _gold_item(
                note,
                "diagnosis",
                "pneumonia",
                "possible pneumonia",
                status="suspected",
            ),
        ],
        [
            _prediction_item(
                note,
                "diagnosis",
                "pneumonia",
                "possible pneumonia",
                status="suspected",
                decision="needs_review",
            ),
        ],
        expected_needs_review=True,
        predicted_needs_review=True,
    )

    # 4. Deliberately missed diagnosis.
    note = "Assessment: asthma and obesity."

    add_case(
        "SYN-EVAL-004",
        "General Medicine",
        note,
        [
            _gold_item(
                note,
                "diagnosis",
                "asthma",
                "asthma",
                status="active",
                icd10_code="J45909",
            ),
            _gold_item(
                note,
                "diagnosis",
                "obesity",
                "obesity",
                status="active",
                icd10_code="E669",
            ),
        ],
        [
            _prediction_item(
                note,
                "diagnosis",
                "asthma",
                "asthma",
                status="active",
                icd10_candidates=["J45909"],
            ),
        ],
        expected_needs_review=True,
        predicted_needs_review=True,
    )

    # 5. Allergy, procedure and vital sign.
    note = (
        "History: penicillin allergy. "
        "Plan: appendectomy. "
        "Vitals: temperature 38 C."
    )

    add_case(
        "SYN-EVAL-005",
        "Surgery",
        note,
        [
            _gold_item(
                note,
                "allergy",
                "penicillin allergy",
                "penicillin allergy",
            ),
            _gold_item(
                note,
                "procedure",
                "appendectomy",
                "appendectomy",
            ),
            _gold_item(
                note,
                "vital_sign",
                "temperature",
                "temperature 38 C",
            ),
        ],
        [
            _prediction_item(
                note,
                "allergy",
                "penicillin allergy",
                "penicillin allergy",
            ),
            _prediction_item(
                note,
                "procedure",
                "appendectomy",
                "appendectomy",
            ),
            _prediction_item(
                note,
                "vital_sign",
                "temperature",
                "temperature 38 C",
            ),
        ],
        expected_needs_review=False,
        predicted_needs_review=False,
    )

    # 6. Deliberately incorrect status: a historical label is predicted
    # for a diagnosis annotated as active.
    note = "Current assessment: migraine."

    add_case(
        "SYN-EVAL-006",
        "Neurology",
        note,
        [
            _gold_item(
                note,
                "diagnosis",
                "migraine",
                "migraine",
                status="active",
                icd10_code="G43909",
            ),
        ],
        [
            _prediction_item(
                note,
                "diagnosis",
                "migraine",
                "migraine",
                status="historical",
                icd10_candidates=["G43909"],
            ),
        ],
        expected_needs_review=True,
        predicted_needs_review=False,
    )

    # 7. Deliberately unsupported accepted diagnosis. The quoted span is
    # real, but "pneumonia" is not supported by that span.
    note = "Assessment: asthma controlled."

    add_case(
        "SYN-EVAL-007",
        "Pulmonology",
        note,
        [
            _gold_item(
                note,
                "diagnosis",
                "asthma",
                "asthma",
                status="active",
                icd10_code="J45909",
            ),
        ],
        [
            _prediction_item(
                note,
                "diagnosis",
                "asthma",
                "asthma",
                status="active",
                icd10_candidates=["J45909"],
            ),
            _prediction_item(
                note,
                "diagnosis",
                "pneumonia",
                "asthma",
                status="active",
            ),
        ],
        expected_needs_review=True,
        predicted_needs_review=False,
    )

    return gold_cases, prediction_cases


__all__ = ["build_synthetic_smoke_set"]