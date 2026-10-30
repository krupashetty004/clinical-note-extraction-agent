"""Persistence boundary for clinical-note processing runs.

Coordinates the orchestrator with Django persistence.
Providers must be supplied explicitly by the caller.

The caller must authorize access to the note before invoking this service.
No external AI provider is configured automatically.
"""

import logging
import re
from collections import Counter

from django.utils import timezone

from dashboard.extraction.orchestrator import (
    VerificationProvider,
    run_agent_workflow,
)
from dashboard.extraction.pipeline import ExtractionProvider
from dashboard.extraction.rag_service import retrieve_knowledge_passages
from dashboard.models import ClinicalNote, ClinicalProcessingRun

logger = logging.getLogger(__name__)

_RAG_STOPWORDS = {
    "a", "about", "after", "again", "all", "also", "am", "an", "and",
    "are", "as", "at", "be", "been", "before", "being", "between", "but",
    "by", "can", "could", "did", "do", "does", "during", "for", "from",
    "had", "has", "have", "he", "her", "here", "hers", "him", "his",
    "how", "i", "if", "in", "into", "is", "it", "its", "may", "me",
    "might", "more", "most", "no", "not", "of", "on", "or", "our",
    "out", "over", "patient", "she", "should", "so", "some", "such",
    "than", "that", "the", "their", "them", "then", "there", "these",
    "they", "this", "those", "through", "to", "under", "up", "very",
    "was", "we", "were", "what", "when", "where", "which", "while",
    "who", "will", "with", "would", "you", "your",
}


def _build_knowledge_query(original_note: str, *, max_terms: int = 16) -> str:
    """Build a bounded lexical query without storing or logging note content."""
    tokens = [
        token.casefold()
        for token in re.findall(r"[^\\W_]+", original_note, flags=re.UNICODE)
        if len(token) > 2 and token.casefold() not in _RAG_STOPWORDS
    ]
    if not tokens:
        return ""
    counts = Counter(tokens)
    first_seen = {token: index for index, token in enumerate(tokens)}
    ranked = sorted(
        counts,
        key=lambda token: (-counts[token], first_seen[token], -len(token)),
    )
    return " ".join(ranked[:max_terms])


def _knowledge_reference_trace(passage: dict) -> dict:
    """Persist citation and chunk metadata, not the full reference text."""
    return {
        "document_id": passage["document_id"],
        "title": passage["title"],
        "version": passage["version"],
        "priority": passage["priority"],
        "source_type": passage["source_type"],
        "source_filename": passage["source_filename"],
        "source_citations": passage["source_citations"],
        "chunk_index": passage["chunk_index"],
        "start_offset": passage["start_offset"],
        "end_offset": passage["end_offset"],
        "score": passage["score"],
    }


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

    reference_context: list[dict] = []
    retrieval_status = "no_matches"
    try:
        retrieval_query = _build_knowledge_query(note.original_text)
        if retrieval_query:
            passages = retrieve_knowledge_passages(
                retrieval_query,
                top_k=3,
                min_score=0.15,
            )
            if passages:
                retrieval_status = "retrieved"
                reference_context = [
                    {
                        **_knowledge_reference_trace(passage),
                        "text": passage["text"],
                    }
                    for passage in passages
                ]
    except Exception as exc:
        # Retrieval is supplementary. Preserve the clinical workflow and
        # record only a safe status; never log query or document content.
        retrieval_status = "unavailable"
        logger.warning(
            "Knowledge retrieval unavailable (exception_type=%s).",
            type(exc).__name__,
        )

    run.knowledge_retrieval_status = retrieval_status
    run.knowledge_references = [
        _knowledge_reference_trace(item)
        for item in reference_context
    ]
    run.save(
        update_fields=[
            "status",
            "started_at",
            "knowledge_retrieval_status",
            "knowledge_references",
        ]
    )

    try:
        workflow_kwargs = {
            "max_extraction_attempts": max_extraction_attempts,
            "max_verification_attempts": max_verification_attempts,
        }
        if reference_context:
            workflow_kwargs["reference_context"] = reference_context
        result = run_agent_workflow(
            extraction_provider,
            verification_provider,
            note.original_text,
            **workflow_kwargs,
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
            "knowledge_references",
            "knowledge_retrieval_status",
            "item_dispositions",
            "review_reasons",
            "failure_code",
            "finished_at",
        ]
    )

    return run


__all__ = ["process_clinical_note"]