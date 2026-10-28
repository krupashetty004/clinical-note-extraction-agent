"""Persistence boundary for clinical-note processing runs.

Coordinates the orchestrator with Django persistence.
Providers must be supplied explicitly by the caller.

The caller must authorize access to the note before invoking this service.
No external AI provider is configured automatically.
"""

import logging

from django.utils import timezone

from dashboard.extraction.orchestrator import (
    VerificationProvider,
    run_agent_workflow,
)
from dashboard.extraction.pipeline import ExtractionProvider
from dashboard.models import ClinicalNote, ClinicalProcessingRun

logger = logging.getLogger(__name__)


def process_clinical_note(
    note: ClinicalNote,
    initiated_by,
    *,
    extraction_provider: ExtractionProvider,
    verification_provider: VerificationProvider,
    max_extraction_attempts: int = 2,
    max_verification_attempts: int = 2,
    execution_mode: str = ClinicalProcessingRun.ExecutionMode.UNKNOWN,
) -> ClinicalProcessingRun:
    """Create, execute, and persist one processing run.

    Each invocation creates a separate run. The original clinical note
    is never modified.

    The caller is responsible for authorization and supplying explicitly
    configured provider implementations.
    """
    if not isinstance(note, ClinicalNote):
        raise TypeError("note must be a ClinicalNote instance.")

    if note.pk is None:
        raise ValueError("Save the clinical note before processing it.")

    if not getattr(initiated_by, "is_authenticated", False):
        raise PermissionError(
            "An authenticated user is required to process a note."
        )

    if execution_mode not in ClinicalProcessingRun.ExecutionMode.values:
        raise ValueError("execution_mode must be a supported processing mode.")

    run = ClinicalProcessingRun.objects.create(
        clinical_note=note,
        created_by=initiated_by,
        status=ClinicalProcessingRun.Status.PENDING,
        execution_mode=execution_mode,
    )

    run.status = ClinicalProcessingRun.Status.RUNNING
    run.started_at = timezone.now()
    run.save(update_fields=["status", "started_at"])

    try:
        result = run_agent_workflow(
            extraction_provider,
            verification_provider,
            note.original_text,
            max_extraction_attempts=max_extraction_attempts,
            max_verification_attempts=max_verification_attempts,
        )
    except Exception as exc:
        # Log only the exception class, never its message or clinical text.
        logger.error(
            "Clinical processing failed (exception_type=%s).",
            type(exc).__name__,
        )

        # Do not persist exception details because they could contain
        # sensitive note content, credentials, or provider information.
        run.status = ClinicalProcessingRun.Status.FAILED
        run.failure_code = "processing_service_failed"
        run.review_reasons = [
            "Processing failed unexpectedly; manual review is required."
        ]
        run.finished_at = timezone.now()

        run.save(
            update_fields=[
                "status",
                "failure_code",
                "review_reasons",
                "finished_at",
            ]
        )
        return run

    # Persist the attempt counts and structured outputs.
    run.extraction_attempts = result.extraction_attempts
    run.verification_attempts = result.verification_attempts

    run.extraction_result = (
        result.extraction.model_dump(mode="json")
        if result.extraction is not None
        else None
    )

    run.coding_result = (
        result.coding.model_dump(mode="json")
        if result.coding is not None
        else None
    )

    run.verification_result = (
        result.verification.model_dump(mode="json")
        if result.verification is not None
        else None
    )

    run.item_dispositions = [
        disposition.model_dump(mode="json")
        for disposition in result.item_dispositions
    ]

    run.review_reasons = list(result.review_reasons)
    run.failure_code = result.failure_code or ""

    status_mapping = {
        "completed": ClinicalProcessingRun.Status.COMPLETED,
        "needs_review": ClinicalProcessingRun.Status.NEEDS_REVIEW,
        "failed": ClinicalProcessingRun.Status.FAILED,
    }

    run.status = status_mapping[result.status]
    run.finished_at = timezone.now()

    run.save(
        update_fields=[
            "status",
            "extraction_attempts",
            "verification_attempts",
            "extraction_result",
            "coding_result",
            "verification_result",
            "item_dispositions",
            "review_reasons",
            "failure_code",
            "finished_at",
        ]
    )

    return run


__all__ = ["process_clinical_note"]