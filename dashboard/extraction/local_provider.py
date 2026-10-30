"""Local clinical extraction and verification providers for the doctor workspace.

Provides offline, grounded clinical entity extraction and independent verification
when an external AI API is not active or configured.
"""
from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from dashboard.extraction.diagnosis_coding import DiagnosisCodingBatch
from dashboard.extraction.schema import (
    ExtractionResult,
    validate_item_status_context,
)

TOKEN_PATTERN = re.compile(r"[^\W_]+", re.UNICODE)


def _tokens(text: str) -> set[str]:
    return {token.casefold() for token in TOKEN_PATTERN.findall(text)}


# Dictionary of known clinical entity terms
CLINICAL_TERMS: dict[str, list[str]] = {
    "diagnoses": [
        "type 2 diabetes mellitus", "diabetes mellitus", "type 1 diabetes mellitus", "diabetes",
        "essential hypertension", "hypertension", "hyperlipidemia", "hypercholesterolemia",
        "coronary artery disease", "atrial fibrillation", "congestive heart failure", "heart failure",
        "myocardial infarction", "angina pectoris", "musculoskeletal injury", "chest pain",
        "shortness of breath", "dyspnea",
        "asthma", "chronic obstructive pulmonary disease", "copd", "pneumonia", "bronchitis",
        "hallux rigidus", "bunion", "degenerative joint disease", "osteoarthritis", "rheumatoid arthritis",
        "carpal tunnel syndrome", "scoliosis", "lumbar radiculopathy", "herniated disc",
        "gastroesophageal reflux disease", "gerd", "gastritis", "peptic ulcer disease",
        "diverticulitis", "appendicitis", "cholecystitis", "cholelithiasis", "pancreatitis",
        "chronic kidney disease", "acute kidney injury", "urinary tract infection", "hematuria",
        "benign prostatic hyperplasia", "nephrolithiasis", "kidney stones",
        "migraine", "headache", "epilepsy", "seizure disorder", "stroke", "cerebrovascular accident",
        "transient ischemic attack", "multiple sclerosis", "parkinson's disease", "neuropathy",
        "major depressive disorder", "depression", "generalized anxiety disorder", "anxiety",
        "bipolar disorder", "schizophrenia", "insomnia", "sleep apnea",
        "allergic rhinitis", "sinusitis", "otitis media", "pharyngitis", "tonsillitis",
        "cellulitis", "dermatitis", "eczema", "psoriasis", "melanoma", "basal cell carcinoma",
        "squamous cell carcinoma", "breast cancer", "prostate cancer", "lung cancer", "colon cancer",
        "anemia", "iron deficiency anemia", "thrombocytopenia", "leukocytosis", "deep vein thrombosis",
        "pulmonary embolism", "obesity", "morbid obesity", "hypothyroidism", "hyperthyroidism",
        "gout", "osteoporosis", "osteopenia", "cataract", "glaucoma", "macular degeneration",
        "fever", "cough", "fatigue", "nausea", "vomiting", "diarrhea", "constipation",
        "abdominal pain", "back pain", "neck pain", "joint pain", "swelling", "edema",
        "airway compromise", "foreign body",
    ],
    "medications": [
        "lisinopril", "metformin", "atorvastatin", "amlodipine", "metoprolol", "omeprazole",
        "losartan", "simvastatin", "gabapentin", "hydrochlorothiazide", "hydrocodone",
        "sertraline", "furosemide", "levothyroxine", "amoxicillin", "pantoprazole",
        "escitalopram", "prednisone", "rosuvastatin", "tamsulosin", "dextroamphetamine",
        "ibuprofen", "acetaminophen", "aspirin", "insulin", "warfarin", "clopidogrel",
        "ciprofloxacin", "azithromycin", "doxycycline", "cephalexin", "tramadol",
        "duloxetine", "albuterol", "fluticasone", "montelukast", "vicodin", "marcaine",
        "lidocaine", "propofol", "fentanyl", "morphine", "zofran", "ondansetron",
        "heparin", "lovenox", "enoxaparin", "apixaban", "eliquis", "rivaroxaban", "xarelto",
        "prevacid", "humulin", "diprivan", "proventil", "unasyn", "solu-medrol",
    ],
    "procedures": [
        "bunionectomy", "osteotomy", "screw fixation", "implant", "arthroplasty",
        "colonoscopy", "endoscopy", "biopsy", "resection", "excision", "incision",
        "ultrasound", "echocardiogram", "electrocardiogram", "ecg", "ekg", "x-ray",
        "ct scan", "mri", "intubation", "catheterization", "laparoscopy", "thoracotomy",
        "cholecystectomy", "appendectomy", "mastectomy", "lumpectomy", "hysterectomy",
        "prostatectomy", "nephrectomy", "craniotomy", "drainage", "irrigation",
        "debridement", "repair", "suture", "graft", "angioplasty", "stent", "coronary artery bypass",
        "tracheostomy",
    ],
    "allergies": [
        "penicillin", "amoxicillin", "sulfa", "sulfonamides", "latex", "codeine",
        "morphine", "aspirin", "nsaids", "iodine", "peanuts", "shellfish", "eggs", "tape"
    ],
    "vital_signs": [
        "blood pressure", "heart rate", "pulse", "respiratory rate", "temperature",
        "oxygen saturation", "o2 sat", "height", "weight", "bmi", "vital signs"
    ],
}


class LocalClinicalExtractionProvider:
    """Extract clinical entities strictly grounded in the original source note."""

    def extract(
        self,
        original_note: str,
        *,
        reference_context: Sequence[Mapping[str, Any]] = (),
    ) -> dict[str, Any]:
        if not isinstance(original_note, str):
            raise TypeError("original_note must be a string.")

        text_lower = original_note.lower()
        items: list[dict[str, Any]] = []
        occupied_spans: list[tuple[int, int]] = []
        needs_review = False
        review_reasons: list[str] = []

        def overlaps(s: int, e: int) -> bool:
            return any(max(s, os) < min(e, oe) for os, oe in occupied_spans)

        category_map = {
            "diagnoses": "diagnosis",
            "medications": "medication",
            "procedures": "procedure",
            "allergies": "allergy",
            "vital_signs": "vital_sign",
        }

        # Detect a negative allergy statement
        if re.search(r"No known drug allergies", original_note, flags=re.IGNORECASE):
            span = re.search(r"No known drug allergies", original_note, flags=re.IGNORECASE)
            start, end = span.start(), span.end()
            if not overlaps(start, end):
                items.append({
                    "category": "allergy",
                    "entity": "no known drug allergies",
                    "evidence_text": original_note[start:end],
                    "start_offset": start,
                    "end_offset": end,
                    "status": None,
                    "attributes": {},
                })
                occupied_spans.append((start, end))
        for group_key, terms in CLINICAL_TERMS.items():
            category = category_map[group_key]
            for term in sorted(terms, key=len, reverse=True):
                cursor = 0
                while True:
                    idx = text_lower.find(term, cursor)
                    if idx == -1:
                        break
                    end = idx + len(term)
                    cursor = end

                    prev_char = text_lower[idx - 1] if idx > 0 else " "
                    next_char = text_lower[end] if end < len(text_lower) else " "
                    if prev_char.isalnum() or next_char.isalnum():
                        continue

                    if overlaps(idx, end):
                        continue

                    evidence = original_note[idx:end]
                    entity = evidence
                    attributes: dict[str, str] = {}
                    if category == "vital_sign" and term == "blood pressure":
                        reading = re.match(
                            r"\s*(?::|is|of|was)?\s*"
                            r"(\d{2,3}\s*/\s*\d{2,3})"
                            r"(?:\s*(mmHg))?",
                            original_note[end:],
                            flags=re.IGNORECASE,
                        )

                        if reading:
                            expanded_end = end + reading.end()

                            if not overlaps(idx, expanded_end):
                                end = expanded_end
                                evidence = original_note[idx:end]
                                attributes["value"] = reading.group(1)

                                if reading.group(2):
                                    attributes["unit"] = reading.group(2)

                    elif category == "vital_sign" and term == "vital signs":
                        sentence_end_candidates = [
                            position
                            for position in (
                                original_note.find(".", end),
                                original_note.find("!", end),
                                original_note.find("?", end),
                                original_note.find("\n", end),
                            )
                            if position >= 0
                        ]

                        sentence_end = min(
                            sentence_end_candidates,
                            default=len(original_note),
                        )

                        reading = re.search(
                            r"(\d{2,3}\s*/\s*\d{2,3})\s*(mmHg)\b\)?",
                            original_note[end:sentence_end],
                            flags=re.IGNORECASE,
                        )

                        if reading:
                            expanded_end = end + reading.end()

                            if not overlaps(idx, expanded_end):
                                end = expanded_end
                                evidence = original_note[idx:end]
                                attributes["value"] = reading.group(1)
                                attributes["unit"] = reading.group(2)

                    context_start = max(
                        text_lower.rfind(".", 0, idx),
                        text_lower.rfind("!", 0, idx),
                        text_lower.rfind("?", 0, idx),
                        text_lower.rfind("\n", 0, idx),
                    ) + 1
                    context_end = min(
                        [
                            position
                            for position in (
                                text_lower.find(".", end),
                                text_lower.find("!", end),
                                text_lower.find("?", end),
                                text_lower.find("\n", end),
                            )
                            if position >= 0
                        ],
                        default=len(text_lower),
                    )
                    window = text_lower[context_start:context_end]
                    preceding_context = text_lower[max(context_start, idx - 50):idx]
                    historical_context = preceding_context.replace(
                        "history of present illness", ""
                    )
                    status = None

                    if category == "diagnosis":
                        if any(w in historical_context for w in ["history of", "hx of", "past history", "prior"]):
                            status = "historical"
                        elif any(w in preceding_context for w in ["no evidence of", "ruled out", "negative for", "denies"]):
                            status = "ruled_out"
                        elif any(w in preceding_context for w in ["possible", "probable", "rule out", "suspected", "question of"]):
                            status = "suspected"
                        else:
                            status = "active"

                    elif category == "medication":
                        if any(
                            w in window
                            for w in ["discontinued", "stopped", "off", "d/c"]
                        ):
                            status = "discontinued"

                        elif any(
                            w in window
                            for w in ["started on", "prescribed", "begin", "newly"]
                        ):
                            status = "newly_prescribed"

                        elif any(
                            w in window
                            for w in ["recommend", "advised to take"]
                        ):
                            status = "newly_prescribed"

                            reason = (
                                "Medication is recommended, but its prescription "
                                "status is not explicit; confirm before acceptance."
                            )

                            if reason not in review_reasons:
                                needs_review = True
                                review_reasons.append(reason)

                        else:
                            status = "current"

                    if category == "procedure" and re.search(
                        r"\b(if|would|could|should|may|might|require)\b", window
                    ):
                        reason = (
                            "Procedure mention has conditional or planned context; "
                            "confirm whether it was performed."
                        )
                        if reason not in review_reasons:
                            needs_review = True
                            review_reasons.append(reason)

                    items.append({
                        "category": category,
                        "entity": entity,
                        "evidence_text": evidence,
                        "start_offset": idx,
                        "end_offset": end,
                        "status": status,
                        "attributes": attributes,
                    })
                    occupied_spans.append((idx, end))

        # Capture documented procedural verb forms and the removal event without
        # inferring a normalized procedure that the source text does not state.
        for pattern in (
            re.compile(r"\bintubat(?:ion|ed)\b", re.IGNORECASE),
            re.compile(r"\bextubat(?:ion|ed)\b", re.IGNORECASE),
            re.compile(
                r"\b(?:fishbone|fish bone)\b[^.\n]{0,100}?\bremoved\b",
                re.IGNORECASE,
            ),
        ):
            for match in pattern.finditer(original_note):
                start, end = match.span()
                if any(
                    item["category"] == "procedure"
                    and max(start, item["start_offset"])
                    < min(end, item["end_offset"])
                    for item in items
                ):
                    continue
                evidence = original_note[start:end]
                items.append({
                    "category": "procedure",
                    "entity": evidence,
                    "evidence_text": evidence,
                    "start_offset": start,
                    "end_offset": end,
                    "status": None,
                    "attributes": {},
                })
                occupied_spans.append((start, end))

        # Sort by start offset
        items.sort(key=lambda x: x["start_offset"])

        return {
            "items": items,
            "needs_review": needs_review,
            "review_reasons": review_reasons,
        }

class LocalClinicalVerificationProvider:
    """Verify evidence integrity, offsets, contradictions, and status.

    Returns a payload conforming to the VerificationResult schema expected
    by the orchestrator's validate_verification_output() contract:
    each item_check must include item_index, outcome, status_check, reason,
    and evidence fields.
    """

    # Categories that carry a status field in the extraction contract.
    _STATUS_CATEGORIES = {"diagnosis", "medication"}

    def verify(
        self,
        original_note: str,
        extraction: ExtractionResult,
        coding: DiagnosisCodingBatch,
    ) -> dict[str, Any]:
        if not isinstance(original_note, str):
            raise TypeError("original_note must be a string.")

        item_checks: list[dict[str, Any]] = []
        needs_review = False
        review_reasons: list[str] = []

        for index, item in enumerate(extraction.items):
            start = item.start_offset
            end = item.end_offset
            evidence = item.evidence_text
            status_applies = item.category in self._STATUS_CATEGORIES

            # Check offset and evidence validity
            if (
                start < 0
                or end > len(original_note)
                or end <= start
                or original_note[start:end] != evidence
            ):
                item_checks.append({
                    "item_index": index,
                    "outcome": "unsupported",
                    "status_check": "correct" if status_applies else "not_applicable",
                    "reason": "Evidence text does not match original note at specified character offsets.",
                    "evidence": [],
                })
                needs_review = True
                review_reasons.append(f"Item #{index} offset mismatch.")
                continue

            # Check grounding of entity tokens in evidence
            if not _tokens(item.entity).issubset(_tokens(evidence)):
                item_checks.append({
                    "item_index": index,
                    "outcome": "unsupported",
                    "status_check": "correct" if status_applies else "not_applicable",
                    "reason": "Entity is not grounded in the quoted evidence text.",
                    "evidence": [],
                })
                needs_review = True
                review_reasons.append(f"Item #{index} entity ungrounded in evidence.")
                continue

            # Build evidence reference for supported items
            evidence_ref = {
                "evidence_text": evidence,
                "start_offset": start,
                "end_offset": end,
            }

            # Determine status_check for diagnoses and medications
            if status_applies:
                status_ctx_err = validate_item_status_context(item, original_note)
                if status_ctx_err is not None:
                    status_check = "incorrect"
                    review_reasons.append(f"Item #{index} status context conflict: {status_ctx_err}")
                else:
                    status_check = "correct"
                    # Check for contextual contradictions in a short window before the span
                    window = original_note[max(0, start - 60): start].lower()
                    if item.category == "diagnosis":
                        if item.status == "active" and any(
                            w in window
                            for w in ["no evidence of", "ruled out", "negative for", "denies", "not"]
                        ):
                            status_check = "uncertain"
                            review_reasons.append(f"Item #{index} active status may conflict with negation context.")
                        elif item.status == "historical" and any(
                            w in window for w in ["history of", "hx of", "past", "prior"]
                        ):
                            status_check = "correct"
                        elif item.status == "ruled_out" and not any(
                            w in window
                            for w in ["no evidence of", "ruled out", "negative for", "denies", "not"]
                        ):
                            status_check = "uncertain"
                        elif item.status == "suspected" and not any(
                            w in window
                            for w in ["possible", "probable", "suspected", "question of", "rule out"]
                        ):
                            status_check = "uncertain"
                    elif item.category == "medication":
                        if item.status == "discontinued" and not any(
                            w in window for w in ["discontinued", "stopped", "off", "d/c"]
                        ):
                            status_check = "uncertain"
            else:
                status_check = "not_applicable"

            item_checks.append({
                "item_index": index,
                "outcome": "supported",
                "status_check": status_check,
                "reason": "Evidence directly supports the extracted entity in the original note.",
                "evidence": [evidence_ref],
            })

            if status_check in {"incorrect", "uncertain"}:
                needs_review = True

        if needs_review and not review_reasons:
            review_reasons.append("One or more items require clinical review.")

        # Identify known source-grounded terms not represented in the extraction.
        potential_omissions: list[dict[str, Any]] = []

        extracted_entities = {
            item.entity.casefold()
            for item in extraction.items
        }

        category_map = {
            "diagnoses": "diagnosis",
            "medications": "medication",
            "procedures": "procedure",
            "allergies": "allergy",
            "vital_signs": "vital_sign",
        }

        # Prevent duplicate reports for the same category and source span.
        seen_spans: set[tuple[str, int, int]] = set()

        # Track reported spans to avoid flagging overlapping, less-specific
        # terms when a longer clinical term has already been reported.
        reported_spans: dict[str, list[tuple[int, int]]] = {}

        for group_key, terms in CLINICAL_TERMS.items():
            category = category_map[group_key]

            # Prefer specific, longer phrases over their substrings.
            for term in sorted(set(terms), key=len, reverse=True):
                normalized_term = term.casefold()

                # This entity is already represented in the extraction.
                if normalized_term in extracted_entities:
                    continue

                pattern = re.compile(
                    rf"\b{re.escape(term)}\b",
                    flags=re.IGNORECASE,
                )

                for match in pattern.finditer(original_note):
                    start, end = match.span()
                    span_key = (category, start, end)

                    if span_key in seen_spans:
                        continue

                    seen_spans.add(span_key)

                    # Skip a term whose source span is already covered
                    # by an extracted item in the same category.
                    covered_by_extraction = any(
                        item.category == category
                        and item.start_offset <= start
                        and end <= item.end_offset
                        for item in extraction.items
                    )

                    if covered_by_extraction:
                        continue

                    # Avoid duplicate omission reports for overlapping terms.
                    category_spans = reported_spans.setdefault(
                        category, []
                    )

                    overlaps_reported = any(
                        max(start, previous_start)
                        < min(end, previous_end)
                        for previous_start, previous_end in category_spans
                    )

                    if overlaps_reported:
                        continue

                    evidence_text = original_note[start:end]

                    potential_omissions.append(
                        {
                            "category": category,
                            "entity": term,
                            "evidence": {
                                "evidence_text": evidence_text,
                                "start_offset": start,
                                "end_offset": end,
                            },
                            "reason": (
                                f"Potentially missed {category} mention: "
                                f"'{term}'."
                            ),
                        }
                    )

                    category_spans.append((start, end))

        # Any unresolved potential omission requires human review.
        if potential_omissions:
            needs_review = True

            reason = "Potential omissions detected."
            if reason not in review_reasons:
                review_reasons.append(reason)

        return {
            "item_checks": item_checks,
            "potential_omissions": potential_omissions,
            "needs_review": needs_review,
            "review_reasons": review_reasons,
        }
