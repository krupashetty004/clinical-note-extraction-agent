"""Validation contract for independent clinical extraction verification.

This module validates a verifier's structured output. It does not call an
AI provider or determine clinical truth on its own.
"""

from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    StrictStr,
    ValidationError,
    model_validator,
)

from dashboard.extraction.schema import (
    EntityCategory,
    ExtractionResult,
    entity_evidence_is_grounded,
    validate_item_status_context,
    validate_evidence_spans,
)


VerificationOutcome = Literal[
    "supported",
    "unsupported",
    "contradicted",
    "uncertain",
]

StatusCheck = Literal[
    "correct",
    "incorrect",
    "uncertain",
    "not_applicable",
]


class EvidenceReference(BaseModel):
    """A quoted source span used by the verifier."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    evidence_text: StrictStr = Field(min_length=1)
    start_offset: Annotated[StrictInt, Field(ge=0)]
    end_offset: Annotated[StrictInt, Field(gt=0)]

    @model_validator(mode="after")
    def validate_span(self) -> "EvidenceReference":
        if not self.evidence_text.strip():
            raise ValueError("Evidence text must not be blank.")

        if self.end_offset <= self.start_offset:
            raise ValueError(
                "end_offset must be greater than start_offset."
            )

        return self


class ItemVerification(BaseModel):
    """Verification findings for one extracted item."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    item_index: Annotated[StrictInt, Field(ge=0)]
    outcome: VerificationOutcome
    status_check: StatusCheck
    reason: StrictStr = Field(min_length=1)
    evidence: tuple[EvidenceReference, ...] = ()

    @model_validator(mode="after")
    def validate_reason(self) -> "ItemVerification":
        if not self.reason.strip():
            raise ValueError("Verification reason must not be blank.")

        return self


class PotentialOmission(BaseModel):
    """A possible clinical mention missing from the extraction."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    category: EntityCategory
    entity: StrictStr = Field(min_length=1)
    evidence: EvidenceReference
    reason: StrictStr = Field(min_length=1)

    @model_validator(mode="after")
    def validate_text(self) -> "PotentialOmission":
        if not self.entity.strip():
            raise ValueError("Omission entity must not be blank.")

        if not self.reason.strip():
            raise ValueError("Omission reason must not be blank.")

        return self


class VerificationResult(BaseModel):
    """Structured response expected from a future verification pass."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    item_checks: tuple[ItemVerification, ...] = ()
    potential_omissions: tuple[PotentialOmission, ...] = ()
    needs_review: StrictBool
    review_reasons: tuple[StrictStr, ...] = ()

    @model_validator(mode="after")
    def validate_review_decision(self) -> "VerificationResult":
        """Prevent flagged findings from being silently accepted."""

        if any(not reason.strip() for reason in self.review_reasons):
            raise ValueError("Review reasons must not be blank.")

        unresolved_item = any(
            check.outcome != "supported"
            or check.status_check in {"incorrect", "uncertain"}
            for check in self.item_checks
        )

        review_required = (
            unresolved_item or bool(self.potential_omissions)
        )

        if self.needs_review and not self.review_reasons:
            raise ValueError(
                "A result needing review must include review reasons."
            )

        if not self.needs_review and (
            review_required or self.review_reasons
        ):
            raise ValueError(
                "Unresolved findings must be marked for human review."
            )

        return self


class VerificationOutputError(ValueError):
    """Raised when a verifier response fails contract validation."""

    def __init__(
        self,
        code: str,
        message: str,
        *,
        detail_code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.detail_code = detail_code


def validate_verification_output(
    payload: object,
    extraction: ExtractionResult,
    original_note: str,
) -> VerificationResult:
    """Validate verifier output against an extraction and its source note.

    Checks:
    - The original extraction's evidence spans are valid.
    - Every extracted item is checked exactly once.
    - Status checks match the entity category.
    - Evidence references match the exact original-note substring.
    - Unresolved findings cannot be marked as requiring no review.

    This validates structure and source references, not semantic correctness.
    """
    if not isinstance(original_note, str):
        raise TypeError("original_note must be a string.")

    if not isinstance(extraction, ExtractionResult):
        raise TypeError("extraction must be an ExtractionResult.")

    try:
        validate_evidence_spans(extraction, original_note)
    except (ValueError, TypeError) as exc:
        raise VerificationOutputError(
            "input_extraction_invalid",
            "The input extraction has invalid source evidence.",
        ) from exc

    try:
        result = VerificationResult.model_validate(payload)
    except ValidationError as exc:
        raise VerificationOutputError(
            "verification_schema_failed",
            "Verification output failed schema validation.",
        ) from exc

    # Every extracted item must be checked exactly once.
    indices = [check.item_index for check in result.item_checks]
    expected_indices = set(range(len(extraction.items)))

    if (
        len(indices) != len(set(indices))
        or set(indices) != expected_indices
    ):
        raise VerificationOutputError(
            "verification_coverage_failed",
            "Verification must check every extracted item exactly once.",
        )

    # Only diagnoses and medications have status fields in the contract.
    status_categories = {"diagnosis", "medication"}

    for check in result.item_checks:
        item = extraction.items[check.item_index]
        status_applies = item.category in status_categories

        if status_applies and check.status_check == "not_applicable":
            raise VerificationOutputError(
                "verification_status_check_invalid",
                "Diagnosis and medication status must be checked.",
            )

        if not status_applies and check.status_check != "not_applicable":
            raise VerificationOutputError(
                "verification_status_check_invalid",
                "Status checks are not applicable to this category.",
            )

        status_context_error = validate_item_status_context(
            item,
            original_note,
        )
        if status_context_error is not None and check.status_check == "correct":
            raise VerificationOutputError(
                "verification_status_check_invalid",
                "Verification marked a source status conflict as correct.",
                detail_code="status_context_mismatch",
            )

        if (
            check.outcome in {"supported", "contradicted"}
            and not check.evidence
        ):
            raise VerificationOutputError(
                "verification_evidence_failed",
                "Supported or contradicted findings require evidence.",
                detail_code="required_evidence_missing",
            )
        if check.evidence and not entity_evidence_is_grounded(
            item.entity,
            " ".join(
                reference.evidence_text
                for reference in check.evidence
            ),
        ):
            raise VerificationOutputError(
                "verification_evidence_failed",
                "Verification evidence does not support the extracted entity.",
                detail_code="evidence_entity_mismatch",
            )

    references = [
        reference
        for check in result.item_checks
        for reference in check.evidence
    ]
    references.extend(
        omission.evidence
        for omission in result.potential_omissions
    )

    for reference in references:
        if reference.end_offset > len(original_note):
            raise VerificationOutputError(
                "verification_evidence_failed",
                "A verification evidence span exceeds the original note.",
                detail_code="evidence_offset_out_of_bounds",
            )

        actual_text = original_note[
            reference.start_offset:reference.end_offset
        ]

        if actual_text != reference.evidence_text:
            raise VerificationOutputError(
                "verification_evidence_failed",
                "A verification evidence span does not match the original note.",
                detail_code="evidence_text_offset_mismatch",
            )

    for omission in result.potential_omissions:
        if not entity_evidence_is_grounded(
            omission.entity,
            omission.evidence.evidence_text,
        ):
            raise VerificationOutputError(
                "verification_evidence_failed",
                "Omission evidence does not support the omitted entity.",
                detail_code="evidence_entity_mismatch",
            )

    return result


__all__ = [
    "EvidenceReference",
    "ItemVerification",
    "PotentialOmission",
    "VerificationOutputError",
    "VerificationResult",
    "validate_verification_output",
]