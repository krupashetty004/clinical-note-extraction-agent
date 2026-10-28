"""Provider-independent validation of clinical extraction results."""

from pydantic import ValidationError

from dashboard.extraction.schema import (
    EvidenceSpanValidationError,
    ExtractionResult,
    validate_evidence_spans,
)


class ExtractionOutputError(ValueError):
    """Raised when extraction output fails validation."""

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


def validate_extraction_output(
    payload: object,
    original_note: str,
) -> ExtractionResult:
    """Validate structured output and evidence against the source note.

    Args:
        payload: Structured extraction data, normally a dictionary.
        original_note: The unchanged original clinical note.

    Returns:
        A validated ExtractionResult.

    Raises:
        TypeError: If original_note is not a string.
        ExtractionOutputError: If schema or evidence validation fails.

    This function does not call a model or persist any data.
    Error messages deliberately avoid including note text or the
    submitted payload.
    """
    if not isinstance(original_note, str):
        raise TypeError("original_note must be a string.")

    # Step 1: Validate the structured output contract.
    try:
        result = ExtractionResult.model_validate(payload)
    except ValidationError as exc:
        raise ExtractionOutputError(
            code="schema_validation_failed",
            message="Structured extraction output failed schema validation.",
        ) from exc

    # Step 2: Check source-span integrity against the original note.
    try:
        validate_evidence_spans(result, original_note)
    except (ValueError, TypeError) as exc:
        detail_code = (
            exc.code
            if isinstance(exc, EvidenceSpanValidationError)
            else None
        )
        raise ExtractionOutputError(
            code="evidence_validation_failed",
            message="Evidence text or offsets failed source validation.",
            detail_code=detail_code,
        ) from exc

    # Nothing is persisted here. Callers receive only a fully
    # schema-validated result with valid source spans.
    return result