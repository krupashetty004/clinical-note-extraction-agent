"""Strict schemas and original-note evidence validation."""

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
            raise ValueError(
                f"Item {index}: end_offset exceeds the original note length."
            )

        actual_evidence = original_note[
            item.start_offset:item.end_offset
        ]

        if actual_evidence != item.evidence_text:
            raise ValueError(
                f"Item {index}: evidence_text does not match "
                "the original note at the supplied offsets."
            )