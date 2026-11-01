"""Connect validated diagnosis mentions to hybrid ICD-10 retrieval."""

import re
from typing import cast

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

from dashboard.extraction.coding_schema import (
    ICD10CodingResult,
    coding_result_from_lookup,
)
from dashboard.extraction.icd10_search import (
    ICD10Candidate,
    ICD10LookupResult,
    search_hybrid_icd10,
    search_icd10,
)
from dashboard.extraction.schema import DiagnosisStatus, ExtractedItem
from dashboard.extraction.service import validate_extraction_output


# These words describe a generic code title rather than a clinical subtype.
# Keep "other" out: it is a classification qualifier and must be supported.
_GENERIC_CODE_DESCRIPTOR_TERMS = frozenset({
    "a", "an", "the", "of", "to", "due", "and", "or",
    "disease", "disorder", "syndrome", "condition",
    "unspecified", "organism",
})

# ICD-10-CM sometimes expresses the same documented concept with paired
# descriptor terms. These equivalences are deliberately narrow.
_CODE_DESCRIPTOR_EQUIVALENTS = {
    "primary": frozenset({"essential"}),
    "essential": frozenset({"primary"}),
}


def _sentence_context(note: str, start: int, end: int) -> str:
    """Return the sentence containing a diagnosis mention."""
    left = max(
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
    right = min(right_candidates, default=len(note))
    return note[left + 1:right + 1].casefold()


def _diagnosis_retrieval_query(
    item: ExtractedItem,
    original_note: str,
) -> str:
    """Include one explicit local subtype modifier in the ICD search query.

    Only a small allowlist of clinical modifiers immediately preceding the
    extracted diagnosis is eligible. This avoids pulling unrelated words
    from the whole sentence into lexical retrieval.
    """
    contextual_descriptors = {
        "acute",
        "chronic",
        "subacute",
        "recurrent",
        "paroxysmal",
        "persistent",
        "permanent",
        "relapsing-remitting",
        "primary",
        "secondary",
        "essential",
        "resistant",
        "benign",
        "malignant",
        "idiopathic",
        "congenital",
    }
    context = _sentence_context(
        original_note,
        item.start_offset,
        item.end_offset,
    )
    entity_start = context.casefold().find(item.entity.casefold())
    if entity_start <= 0:
        return item.entity

    prefix_tokens = re.findall(
        r"[a-z]+(?:-[a-z]+)*",
        context[:entity_start].casefold(),
    )
    modifier = next(
        (
            token
            for token in reversed(prefix_tokens[-5:])
            if token in contextual_descriptors
        ),
        None,
    )
    return f"{modifier} {item.entity}" if modifier else item.entity


def _candidate_specificity_is_supported(
    candidate: ICD10Candidate,
    item: ExtractedItem,
    original_note: str,
) -> bool:
    """Reject candidate qualifiers absent from the source sentence.

    Historical mention status supports the descriptor "old". This check is
    deliberately conservative and does not infer clinical synonyms.
    """
    context = _sentence_context(
        original_note,
        item.start_offset,
        item.end_offset,
    )
    context_tokens = set(re.findall(r"[a-z]+", context))
    description_tokens = set(
        re.findall(r"[a-z]+", candidate.description.casefold())
    )

    # Do not accept a candidate merely because it shares one common word
    # with the diagnosis. Every meaningful descriptor in the code title
    # must be supported by the source sentence. This catches modifiers
    # outside a hand-maintained list (for example, renovascular,
    # susceptibility, typhoid, and dyskinesia).
    unsupported = (
        description_tokens
        - context_tokens
        - _GENERIC_CODE_DESCRIPTOR_TERMS
    )

    # Preserve a narrowly documented terminology equivalence:
    # "essential hypertension" may map to "essential (primary) hypertension".
    for token in tuple(unsupported):
        equivalents = _CODE_DESCRIPTOR_EQUIVALENTS.get(token, frozenset())
        if equivalents & context_tokens:
            unsupported.discard(token)

    if item.status == "historical":
        unsupported.discard("old")

    return not unsupported


def _apply_specificity_guard(
    lookup: ICD10LookupResult,
    item: ExtractedItem,
    original_note: str,
    *,
    limit: int,
    minimum_lexical_score: float,
    minimum_semantic_score: float,
) -> ICD10LookupResult:
    """Keep only candidates whose explicit qualifiers are source-supported."""
    if not lookup.candidates:
        return lookup

    supported = tuple(
        candidate
        for candidate in lookup.candidates
        if _candidate_specificity_is_supported(
            candidate,
            item,
            original_note,
        )
    )

    if not supported:
        return ICD10LookupResult(
            query=lookup.query,
            status="no_confident_match",
            candidates=tuple(lookup.candidates[:limit]),
            reason=(
                "Candidate descriptions add clinical specificity that is "
                "not supported by the diagnosis sentence. Manual review is required."
            ),
        )

    qualifying = tuple(
        candidate
        for candidate in supported
        if (
            candidate.lexical_score >= minimum_lexical_score
            or (
                candidate.semantic_score is not None
                and candidate.semantic_score >= minimum_semantic_score
            )
        )
    )

    if lookup.status == "candidates_found" and qualifying:
        return ICD10LookupResult(
            query=lookup.query,
            status="candidates_found",
            candidates=qualifying[:limit],
        )

    return ICD10LookupResult(
        query=lookup.query,
        status="no_confident_match",
        candidates=supported[:limit],
        reason=(
            lookup.reason
            or "No context-supported candidate met the configured retrieval threshold."
        ),
    )


class CodedDiagnosisMention(BaseModel):
    """A diagnosis mention paired with candidates, not a confirmed code."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    entity: StrictStr = Field(min_length=1)
    status: DiagnosisStatus
    evidence_text: StrictStr = Field(min_length=1)
    start_offset: StrictInt = Field(ge=0)
    end_offset: StrictInt = Field(gt=0)
    coding: ICD10CodingResult


class DiagnosisCodingBatch(BaseModel):
    """Coding results for diagnosis mentions in one validated extraction."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    diagnoses: tuple[CodedDiagnosisMention, ...] = ()


def code_diagnoses(
    payload: object,
    original_note: str,
    *,
    limit: int = 5,
    minimum_lexical_score: float = 0.6,
    minimum_semantic_score: float = 0.83,
) -> DiagnosisCodingBatch:
    """Validate extraction output and retrieve hybrid ICD-10 candidates.

    Original evidence and mention status are preserved.
    Non-diagnosis mentions are not sent to ICD-10 retrieval.

    Candidate codes are suggestions, not confirmed diagnoses.
    The semantic threshold is provisional and requires evaluation
    against labelled examples.
    """
    extraction = validate_extraction_output(payload, original_note)
    coded_diagnoses: list[CodedDiagnosisMention] = []

    for item in extraction.items:
        if item.category != "diagnosis":
            continue

        if item.status == "ruled_out":
            lookup = ICD10LookupResult(
                query=item.entity,
                status="no_confident_match",
                candidates=(),
                reason=(
                    "Ruled-out diagnoses are retained for review and are "
                    "not coded as confirmed conditions."
                ),
            )
        else:
            # Retrieve a wider pool so unsupported specific candidates do not
            # hide a lower-ranked generic or context-compatible alternative.
            pool_limit = min(20, max(limit * 4, limit))
            retrieval_query = _diagnosis_retrieval_query(
                item,
                original_note,
            )
            lookup = search_hybrid_icd10(
                retrieval_query,
                limit=pool_limit,
                minimum_lexical_score=minimum_lexical_score,
                minimum_semantic_score=minimum_semantic_score,
            )
            lookup = _apply_specificity_guard(
                lookup,
                item,
                original_note,
                limit=limit,
                minimum_lexical_score=minimum_lexical_score,
                minimum_semantic_score=minimum_semantic_score,
            )

        coded_diagnoses.append(
            CodedDiagnosisMention(
                entity=item.entity,
                status=cast(DiagnosisStatus, item.status),
                evidence_text=item.evidence_text,
                start_offset=item.start_offset,
                end_offset=item.end_offset,
                coding=coding_result_from_lookup(lookup),
            )
        )

    return DiagnosisCodingBatch(
        diagnoses=tuple(coded_diagnoses),
    )
