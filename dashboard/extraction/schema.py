"""Strict schemas and original-note evidence validation."""

import re
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
    model_validator,
)


EntityCategory = Literal[
    "diagnosis",
    "medication",
    "procedure",
    "allergy",
    "vital_sign",
]

DiagnosisStatus = Literal[
    "active",
    "historical",
    "ruled_out",
    "suspected",
]

MedicationStatus = Literal[
    "current",
    "discontinued",
    "newly_prescribed",
]

MentionStatus = DiagnosisStatus | MedicationStatus


class ExtractedItem(BaseModel):
    """One clinical mention with evidence in the original source note."""

    model_config = ConfigDict(extra="forbid")

    category: EntityCategory
    entity: StrictStr = Field(min_length=1)

    # Diagnoses and medications have their own status vocabularies.
    # Procedures, allergies, and vital signs have no status field
    # under the current SOW contract.
    status: MentionStatus | None = None

    evidence_text: StrictStr = Field(min_length=1)

    # Zero-based, end-exclusive offsets into the original Python string.
    start_offset: Annotated[StrictInt, Field(ge=0)]
    end_offset: Annotated[StrictInt, Field(gt=0)]

    # Values explicitly stated in the source, such as medication dose,
    # route/frequency, procedure date, allergy reaction, or vital/unit.
    attributes: dict[str, StrictStr] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_item_fields(self) -> "ExtractedItem":
        """Enforce status rules according to the entity category."""

        if not self.entity.strip():
            raise ValueError(
                "Entity must not be empty or whitespace-only."
            )

        if not self.evidence_text.strip():
            raise ValueError(
                "Evidence text must not be empty or whitespace-only."
            )

        if self.end_offset <= self.start_offset:
            raise ValueError(
                "end_offset must be greater than start_offset."
            )

        if self.category == "diagnosis":
            if self.status not in {
                "active",
                "historical",
                "ruled_out",
                "suspected",
            }:
                raise ValueError(
                    "Diagnosis status must be active, historical, "
                    "ruled_out, or suspected."
                )

        elif self.category == "medication":
            if self.status not in {
                "current",
                "discontinued",
                "newly_prescribed",
            }:
                raise ValueError(
                    "Medication status must be current, "
                    "discontinued, or newly_prescribed."
                )

        elif self.status is not None:
            raise ValueError(
                "Status is not defined for this entity category "
                "in the current extraction contract."
            )

        return self


class ExtractionResult(BaseModel):
    """Structured result returned by the extraction component."""

    model_config = ConfigDict(extra="forbid")

    items: list[ExtractedItem]
    needs_review: bool
    review_reasons: list[StrictStr]


class EvidenceSpanValidationError(ValueError):
    """Typed evidence-span failure, without exposing source text."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code


_WORD_PATTERN = re.compile(r"[^\W_]+", re.UNICODE)
_NEGATION_CUES = (
    "no ",
    "no evidence of",
    "denies ",
    "denied ",
    "without ",
    "negative for",
    "not ",
    "never ",
    "ruled out",
    "has not been diagnosed",
)
_HISTORICAL_CUES = (
    "history of",
    "historical",
    "previously",
    "formerly",
    "in the past",
    "remote ",
)
_UNCERTAINTY_CUES = (
    "possible ",
    "possibly ",
    "suspected ",
    "likely ",
    "may have",
    "might have",
    "question of",
    "concern for",
)
_CURRENT_CUES = (
    "current ",
    "currently ",
    "active ",
    "present ",
)
_DISCONTINUED_CUES = (
    "discontinued",
    "stopped",
    "held",
    "no longer taking",
)
_NEW_MEDICATION_CUES = (
    "new prescription",
    "newly prescribed",
    "prescribed",
    "started",
    "begin ",
    "began ",
)


def _normalized_tokens(value: str) -> set[str]:
    return set(_WORD_PATTERN.findall(value.casefold()))


def entity_evidence_is_grounded(entity: str, evidence_text: str) -> bool:
    """Return whether every entity token occurs in cited evidence."""
    entity_tokens = _normalized_tokens(entity)
    evidence_tokens = _normalized_tokens(evidence_text)
    return bool(entity_tokens) and entity_tokens <= evidence_tokens


def _context_for_span(note: str, start: int, end: int) -> str:
    """Return the sentence or line containing a source span."""
    left_boundary = max(
        note.rfind(".", 0, start),
        note.rfind("!", 0, start),
        note.rfind("?", 0, start),
        note.rfind(";", 0, start),
        note.rfind("\n", 0, start),
    )
    right_candidates = [
        position
        for position in (
            note.find(".", end),
            note.find("!", end),
            note.find("?", end),
            note.find(";", end),
            note.find("\n", end),
        )
        if position >= 0
    ]
    right_boundary = min(right_candidates, default=len(note))
    return note[left_boundary + 1:right_boundary + 1].casefold()


def _contains_cue(context: str, cues: tuple[str, ...]) -> bool:
    return any(cue in context for cue in cues)


def _validate_item_grounding(
    item: ExtractedItem,
    original_note: str,
) -> None:
    """Reject fabricated entities, attributes, or status context."""
    if not entity_evidence_is_grounded(
        item.entity,
        item.evidence_text,
    ):
        raise EvidenceSpanValidationError(
            "evidence_entity_mismatch",
            "The evidence does not contain the extracted entity.",
        )

    for attribute_name, attribute_value in item.attributes.items():
        if not attribute_name.strip() or not attribute_value.strip():
            raise EvidenceSpanValidationError(
                "evidence_attribute_invalid",
                "Evidence attributes must have non-blank names and values.",
            )
        if attribute_value.casefold() not in item.evidence_text.casefold():
            raise EvidenceSpanValidationError(
                "evidence_attribute_mismatch",
                "An extracted attribute is not present in the evidence.",
            )

def validate_item_status_context(
    item: ExtractedItem,
    original_note: str,
) -> str | None:
    """Return a status-context error without rejecting extraction output.

    Status reconciliation belongs to the independent verifier. Extraction
    must retain a source-grounded mention even when its predicted status is
    wrong, so the verifier can flag it for review.
    """
    context = _context_for_span(
        original_note,
        item.start_offset,
        item.end_offset,
    )
    if item.category == "diagnosis":
        if item.status == "active" and (
            _contains_cue(context, _NEGATION_CUES)
            or _contains_cue(context, _HISTORICAL_CUES)
            or _contains_cue(context, _UNCERTAINTY_CUES)
        ):
            return (
                "Active diagnosis evidence conflicts with its source context."
            )
        if item.status == "historical":
            if _contains_cue(context, _CURRENT_CUES):
                return (
                    "Historical diagnosis status conflicts with current "
                    "source context."
                )
            if not _contains_cue(context, _HISTORICAL_CUES):
                return (
                    "Historical diagnosis status lacks historical source "
                    "context."
                )
        if item.status == "suspected" and not _contains_cue(
            context, _UNCERTAINTY_CUES
        ):
            return (
                "Suspected diagnosis status lacks uncertainty source context."
            )
        if item.status == "ruled_out" and not _contains_cue(
            context, _NEGATION_CUES
        ):
            return (
                "Ruled-out diagnosis status lacks negating source context."
            )
    elif item.category == "medication":
        if item.status == "current" and (
            _contains_cue(context, _DISCONTINUED_CUES)
            or _contains_cue(context, _HISTORICAL_CUES)
            or _contains_cue(context, _UNCERTAINTY_CUES)
        ):
            return "Current medication status conflicts with source context."
        if item.status == "discontinued" and not _contains_cue(
            context, _DISCONTINUED_CUES
        ):
            return "Discontinued medication status lacks source context."
        if item.status == "newly_prescribed" and not _contains_cue(
            context, _NEW_MEDICATION_CUES
        ):
            return "New medication status lacks prescription source context."
    return None


def validate_evidence_spans(
    result: ExtractionResult,
    original_note: str,
) -> None:
    """Validate exact evidence text and offsets against the original note.

    Raises:
        TypeError: If original_note is not a string.
        ValueError: If evidence is outside the note or differs from
            the original substring.

    An exact substring match does not prove semantic support.
    """
    if not isinstance(original_note, str):
        raise TypeError("original_note must be a string.")

    for index, item in enumerate(result.items):
        if item.end_offset > len(original_note):
            raise EvidenceSpanValidationError(
                "evidence_offset_out_of_bounds",
                f"Item {index}: end_offset exceeds the original note length.",
            )

        actual_evidence = original_note[
            item.start_offset:item.end_offset
        ]

        if actual_evidence != item.evidence_text:
            raise EvidenceSpanValidationError(
                "evidence_text_offset_mismatch",
                f"Item {index}: evidence_text does not match "
                "the original note at the supplied offsets.",
            )

        _validate_item_grounding(item, original_note)
