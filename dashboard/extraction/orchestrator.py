"""Provider-independent orchestration for clinical note processing.

This module coordinates extraction, ICD-10 candidate retrieval,
verification, reconciliation, and human-review decisions.

It does not persist records, call an external provider automatically,
or treat schema validity as proof of clinical correctness.
"""

from collections.abc import Mapping, Sequence
from typing import Any, Literal, Protocol

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    StrictStr,
)

import logging

from dashboard.extraction.coding_schema import ICD10CodingResult
from dashboard.extraction.diagnosis_coding import (
    DiagnosisCodingBatch,
    code_diagnoses,
)
from dashboard.extraction.pipeline import (
    ExtractionProviderError,
    run_extraction,
)
from dashboard.extraction.providers import ExtractionProvider
from dashboard.extraction.schema import ExtractionResult
from dashboard.extraction.service import ExtractionOutputError
from dashboard.extraction.verification import (
    VerificationOutputError,
    VerificationResult,
    validate_verification_output,
)


logger = logging.getLogger(__name__)


_SAFE_VERIFICATION_FAILURE_CODES = frozenset({
    "provider_timeout",
    "provider_failed",
    "provider_bad_request",
    "provider_authentication_failed",
    "provider_permission_denied",
    "provider_resource_not_found",
    "provider_request_too_large",
    "provider_rate_limited",
    "provider_server_error",
    "provider_connection_error",
    "provider_response_shape_invalid",
    "provider_empty_response",
    "provider_invalid_json",
    "provider_invalid_json_shape",
    "verification_timeout",
    "verification_failed",
})


def _safe_verification_failure_code(error: Exception) -> str:
    """Return only allowlisted provider failure categories."""
    code = getattr(error, "code", "verification_failed")
    if code == "provider_timeout":
        return "verification_timeout"
    if code in _SAFE_VERIFICATION_FAILURE_CODES:
        return code
    return "verification_failed"


class VerificationProvider(Protocol):
    """Contract for a separate verifier implementation."""

    def verify(
        self,
        original_note: str,
        extraction: ExtractionResult,
        coding: DiagnosisCodingBatch,
        *,
        reference_context: Sequence[Mapping[str, Any]] = (),
    ) -> object:
        """Return untrusted structured verification data."""
        ...


WorkflowStatus = Literal["completed", "needs_review", "failed"]
ItemDecision = Literal["accepted", "rejected", "needs_review"]


class ItemDisposition(BaseModel):
    """Reconciliation decision for one extracted item."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    item_index: StrictInt = Field(ge=0)
    decision: ItemDecision
    reasons: tuple[StrictStr, ...] = ()


class AgentWorkflowResult(BaseModel):
    """Outcome of one orchestration run."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    status: WorkflowStatus
    extraction_attempts: StrictInt = Field(ge=0)
    verification_attempts: StrictInt = Field(ge=0)
    extraction: ExtractionResult | None = None
    coding: DiagnosisCodingBatch | None = None
    verification: VerificationResult | None = None
    item_dispositions: tuple[ItemDisposition, ...] = ()
    review_reasons: tuple[StrictStr, ...] = ()
    failure_code: StrictStr | None = None


def _unique_reasons(*groups: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    """Combine nonblank reasons while preserving their original order."""
    result: list[str] = []

    for group in groups:
        for reason in group:
            cleaned = reason.strip()
            if cleaned and cleaned not in result:
                result.append(cleaned)

    return tuple(result)


def _failed_result(
    *,
    code: str,
    message: str,
    extraction_attempts: int,
    verification_attempts: int = 0,
    extraction: ExtractionResult | None = None,
    coding: DiagnosisCodingBatch | None = None,
) -> AgentWorkflowResult:
    """Build a failure result without exposing underlying exception text."""
    return AgentWorkflowResult(
        status="failed",
        extraction_attempts=extraction_attempts,
        verification_attempts=verification_attempts,
        extraction=extraction,
        coding=coding,
        failure_code=code,
        review_reasons=(message,),
    )


def _reconcile(
    extraction: ExtractionResult,
    coding: DiagnosisCodingBatch,
    verification: VerificationResult,
) -> tuple[ItemDisposition, ...]:
    """Apply deterministic review rules to independently verified items."""
    checks_by_index = {
        check.item_index: check
        for check in verification.item_checks
    }

    coding_by_span = {
        (mention.start_offset, mention.end_offset): mention.coding
        for mention in coding.diagnoses
    }

    dispositions: list[ItemDisposition] = []

    for index, item in enumerate(extraction.items):
        check = checks_by_index[index]
        reasons: list[str] = []

        # An unsupported or contradicted claim must not be accepted.
        if check.outcome in {"unsupported", "contradicted"}:
            reasons.append(check.reason)
            dispositions.append(
                ItemDisposition(
                    item_index=index,
                    decision="rejected",
                    reasons=tuple(reasons),
                )
            )
            continue

        # Uncertain findings and incorrect status need human review.
        if (
            check.outcome != "supported"
            or check.status_check in {"incorrect", "uncertain"}
        ):
            reasons.append(check.reason)

            if check.status_check in {"incorrect", "uncertain"}:
                reasons.append(
                    f"Status verification was {check.status_check}."
                )

            dispositions.append(
                ItemDisposition(
                    item_index=index,
                    decision="needs_review",
                    reasons=_unique_reasons(reasons),
                )
            )
            continue

        # A diagnosis with no reliable code candidate is not silently
        # considered fully resolved.
        if item.category == "diagnosis":
            coding_result: ICD10CodingResult | None = coding_by_span.get(
                (item.start_offset, item.end_offset)
            )

            if coding_result is None:
                dispositions.append(
                    ItemDisposition(
                        item_index=index,
                        decision="needs_review",
                        reasons=(
                            "No ICD-10 coding result was available "
                            "for this diagnosis.",
                        ),
                    )
                )
                continue

            if coding_result.status == "no_confident_match":
                dispositions.append(
                    ItemDisposition(
                        item_index=index,
                        decision="needs_review",
                        reasons=(
                            coding_result.reason
                            or "No confident ICD-10 candidate was found.",
                        ),
                    )
                )
                continue

        dispositions.append(
            ItemDisposition(
                item_index=index,
                decision="accepted",
            )
        )

    return tuple(dispositions)


def run_agent_workflow(
    extraction_provider: ExtractionProvider,
    verification_provider: VerificationProvider,
    original_note: str,
    *,
    reference_context: Sequence[Mapping[str, Any]] = (),
    max_extraction_attempts: int = 2,
    max_verification_attempts: int = 2,
) -> AgentWorkflowResult:
    """Run extraction, coding, verification, and reconciliation.

    Attempt limits are total attempts, not extra retries. Both limits
    must be between one and three inclusive.

    Provider exceptions and validation failures are retried only within
    the configured limit. Error messages never include exception details.
    """
    if not isinstance(original_note, str):
        raise TypeError("original_note must be a string.")

    if not original_note.strip():
        raise ValueError("original_note must not be blank.")

    for name, value in (
        ("max_extraction_attempts", max_extraction_attempts),
        ("max_verification_attempts", max_verification_attempts),
    ):
        if isinstance(value, bool) or not isinstance(value, int):
            raise TypeError(f"{name} must be an integer.")
        if not 1 <= value <= 3:
            raise ValueError(f"{name} must be between 1 and 3.")

    extraction: ExtractionResult | None = None
    extraction_attempts = 0
    last_extraction_error: Exception | None = None

    # Phase 1: extract and validate, with bounded recovery.
    for extraction_attempts in range(1, max_extraction_attempts + 1):
        try:
            if reference_context:
                extraction = run_extraction(
                    extraction_provider,
                    original_note,
                    reference_context=reference_context,
                )
            else:
                extraction = run_extraction(
                    extraction_provider,
                    original_note,
                )
            break
        except (ExtractionProviderError, ExtractionOutputError) as exc:
            last_extraction_error = exc
            logger.warning(
                "Extraction attempt rejected (attempt=%s, code=%s).",
                extraction_attempts,
                getattr(exc, "code", "extraction_validation_failed"),
            )

    if extraction is None:
        failure_code = getattr(
            last_extraction_error,
            "code",
            "extraction_failed",
        )
        return _failed_result(
            code=failure_code,
            message=(
                "Extraction could not be validated within "
                "the configured attempt limit."
            ),
            extraction_attempts=extraction_attempts,
        )

    # Phase 2: retrieve diagnosis-code candidates.
    try:
        coding = code_diagnoses(
            extraction.model_dump(mode="python"),
            original_note,
        )
    except Exception as exc:
        logger.error(
            "ICD candidate retrieval failed (exception_type=%s).",
            type(exc).__name__,
        )
        return _failed_result(
            code="coding_failed",
            message=(
                "ICD-10 candidate retrieval failed. "
                "The result requires review."
            ),
            extraction_attempts=extraction_attempts,
            extraction=extraction,
        )

    # Phase 3: call the separate verifier and validate its output.
    verification: VerificationResult | None = None
    verification_attempts = 0
    last_verification_code = "verification_failed"

    for verification_attempts in range(
        1,
        max_verification_attempts + 1,
    ):
        # Phase A: invoke the provider.
        # The provider's exception message is deliberately not logged.
        try:
            if reference_context:
                verification_payload = verification_provider.verify(
                    original_note,
                    extraction,
                    coding,
                    reference_context=reference_context,
                )
            else:
                verification_payload = verification_provider.verify(
                    original_note,
                    extraction,
                    coding,
                )
        except TimeoutError:
            last_verification_code = "verification_timeout"
            logger.warning(
                "Verification provider timed out (attempt=%s).",
                verification_attempts,
            )
            continue
        except Exception as exc:
            last_verification_code = _safe_verification_failure_code(exc)
            logger.warning(
                "Verification provider invocation failed "
                "(attempt=%s, code=%s).",
                verification_attempts,
                last_verification_code,
            )
            continue

        # Phase B: validate the provider's response.
        # Retry only recognized verification-contract failures.
        try:
            verification = validate_verification_output(
                verification_payload,
                extraction,
                original_note,
            )
        except VerificationOutputError as exc:
            last_verification_code = exc.code
            logger.warning(
                "Verification output rejected (attempt=%s, code=%s).",
                verification_attempts,
                exc.code,
            )
            continue

        # Both invocation and validation succeeded.
        break

    if verification is None:
        return AgentWorkflowResult(
            status="needs_review",
            extraction_attempts=extraction_attempts,
            verification_attempts=verification_attempts,
            extraction=extraction,
            coding=coding,
            verification=None,
            item_dispositions=tuple(
                ItemDisposition(
                    item_index=index,
                    decision="needs_review",
                    reasons=(
                        "Independent verification did not complete.",
                    ),
                )
                for index in range(len(extraction.items))
            ),
            review_reasons=(
                "Independent verification did not complete within "
                "the configured attempt limit.",
            ),
            failure_code=last_verification_code,
        )

    # Phase 4: reconcile each item and determine the workflow outcome.
    dispositions = _reconcile(
        extraction,
        coding,
        verification,
    )

    item_review_reasons = [
        reason
        for disposition in dispositions
        if disposition.decision != "accepted"
        for reason in disposition.reasons
    ]

    omission_reasons = [
        f"Potential omission requires review: {omission.entity}."
        for omission in verification.potential_omissions
    ]

    review_reasons = _unique_reasons(
        extraction.review_reasons,
        verification.review_reasons,
        item_review_reasons,
        omission_reasons,
    )

    needs_review = (
        extraction.needs_review
        or verification.needs_review
        or bool(verification.potential_omissions)
        or any(
            item.decision != "accepted"
            for item in dispositions
        )
    )

    return AgentWorkflowResult(
        status="needs_review" if needs_review else "completed",
        extraction_attempts=extraction_attempts,
        verification_attempts=verification_attempts,
        extraction=extraction,
        coding=coding,
        verification=verification,
        item_dispositions=dispositions,
        review_reasons=review_reasons,
    )


__all__ = [
    "AgentWorkflowResult",
    "ItemDisposition",
    "VerificationProvider",
    "run_agent_workflow",
]