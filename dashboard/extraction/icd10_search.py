"""Hybrid lexical and semantic ICD-10-CM candidate retrieval."""

import math
import re
import unicodedata
from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Literal

from django.db.models import Q

from dashboard.models import ICDCode


_SEARCH_STOP_WORDS = {"a", "an", "the", "of"}
_MAX_QUERY_LENGTH = 200
_MAX_RESULTS = 20

_DEFAULT_MINIMUM_LEXICAL_SCORE = 0.6
_DEFAULT_MINIMUM_SEMANTIC_SCORE = 0.83
_DEFAULT_LEXICAL_WEIGHT = 0.65

# This is a retrieval synonym, not a clinical assertion. Keep it phrase
# scoped so "low blood pressure" continues to match the low-reading code.
_LEXICAL_PHRASE_SYNONYMS = (
    (re.compile(r"\bhigh\s+blood\s+pressure\b"), "elevated blood pressure"),
    (re.compile(r"\bhigh\s+bp\b"), "elevated blood pressure"),
    (re.compile(r"\bhtn\b"), "hypertension"),
    (
        re.compile(r"\bdiabetes\s+mellitus\s+type\s+2\b"),
        "type 2 diabetes mellitus",
    ),
)
_NEGATED_QUERY_PATTERN = re.compile(
    r"^\s*(?:no|not|without|denies|denied|negative for)\b|"
    r"\bruled\s+out\s*$",
    re.IGNORECASE,
)
_UNCERTAIN_QUERY_PATTERN = re.compile(
    r"^\s*(?:possible|possibly|suspected|likely|may have|might have|"
    r"question of|concern for)\b",
    re.IGNORECASE,
)

@dataclass(frozen=True, slots=True)
class ICD10Candidate:
    """One ICD-10 candidate and its available retrieval scores."""

    code: str
    description: str
    lexical_score: float
    semantic_score: float | None = None
    combined_score: float | None = None


@dataclass(frozen=True, slots=True)
class ICD10LookupResult:
    """Outcome of lexical or hybrid candidate retrieval."""

    query: str
    status: Literal["candidates_found", "no_confident_match"]
    candidates: tuple[ICD10Candidate, ...]
    reason: str | None = None


def _tokenize_diagnosis(text: str) -> tuple[str, ...]:
    """Normalize words while preserving their order and frequency."""
    normalized = unicodedata.normalize("NFKC", text).lower()
    for pattern, replacement in _LEXICAL_PHRASE_SYNONYMS:
        normalized = pattern.sub(replacement, normalized)

    raw_tokens = re.findall(r"[^\W_]+", normalized, flags=re.UNICODE)
    filtered = [
        token
        for token in raw_tokens
        if token not in _SEARCH_STOP_WORDS
    ]

    # Collapse only consecutive duplicate terms.
    tokens: list[str] = []
    for token in filtered:
        if not tokens or tokens[-1] != token:
            tokens.append(token)

    return tuple(tokens)


def _score_description(
    query_tokens: tuple[str, ...],
    description: str,
) -> float:
    """Score lexical token coverage and word-order similarity.

    This score is a retrieval signal, not a probability or a measure
    of clinical correctness.
    """
    description_tokens = _tokenize_diagnosis(description)

    if not query_tokens:
        return 0.0

    unique_query_terms = set(query_tokens)
    description_terms = set(description_tokens)

    coverage = (
        len(unique_query_terms & description_terms)
        / len(unique_query_terms)
    )

    if len(query_tokens) < 3:
        return round(coverage, 4)

    order_similarity = SequenceMatcher(
        None,
        query_tokens,
        description_tokens,
        autojunk=False,
    ).ratio()

    score = 0.7 * coverage + 0.3 * order_similarity
    return round(score, 4)


def _is_exact_description_match(
    query_tokens: tuple[str, ...],
    description: str,
) -> bool:
    return query_tokens == _tokenize_diagnosis(description)


def _specificity_tiebreak(
    query_tokens: tuple[str, ...],
    description: str,
) -> tuple[int, int]:
    """Prefer exact descriptions, then descriptions with fewer extra terms."""
    description_tokens = _tokenize_diagnosis(description)
    return (
        int(_is_exact_description_match(query_tokens, description)),
        -max(0, len(description_tokens) - len(query_tokens)),
    )


def search_icd10(
    query: str,
    *,
    limit: int = 5,
    minimum_lexical_score: float = _DEFAULT_MINIMUM_LEXICAL_SCORE,
) -> ICD10LookupResult:
    """Search ICD-10-CM descriptions using lexical matching.

    Strong lexical candidates are returned when they meet the
    threshold. If none qualify, weak candidates may be returned
    for review with status='no_confident_match'.
    """
    if not isinstance(query, str):
        raise TypeError("Diagnosis query must be a string.")

    if not isinstance(limit, int) or isinstance(limit, bool):
        raise TypeError("limit must be an integer.")

    if not 1 <= limit <= _MAX_RESULTS:
        raise ValueError(
            f"limit must be between 1 and {_MAX_RESULTS}."
        )

    if (
        isinstance(minimum_lexical_score, bool)
        or not isinstance(minimum_lexical_score, (int, float))
        or not math.isfinite(minimum_lexical_score)
        or not 0.0 <= minimum_lexical_score <= 1.0
    ):
        raise ValueError(
            "minimum_lexical_score must be a finite number "
            "between 0 and 1."
        )

    cleaned_query = query.strip()

    if len(cleaned_query) > _MAX_QUERY_LENGTH:
        raise ValueError(
            f"Diagnosis query cannot exceed {_MAX_QUERY_LENGTH} characters."
        )

    query_tokens = _tokenize_diagnosis(cleaned_query)

    if not query_tokens:
        return ICD10LookupResult(
            query=cleaned_query,
            status="no_confident_match",
            candidates=(),
            reason="The query contains no searchable diagnosis terms.",
        )

    if _NEGATED_QUERY_PATTERN.search(cleaned_query):
        return ICD10LookupResult(
            query=cleaned_query,
            status="no_confident_match",
            candidates=(),
            reason="Negated diagnosis terms are not eligible for confident coding.",
        )

    if _UNCERTAIN_QUERY_PATTERN.search(cleaned_query):
        return ICD10LookupResult(
            query=cleaned_query,
            status="no_confident_match",
            candidates=(),
            reason=(
                "Uncertain diagnosis terms require review before confident "
                "coding."
            ),
        )

    # Narrow the database results before scoring descriptions.
    matching_descriptions = Q()

    for token in set(query_tokens):
        matching_descriptions |= Q(description__icontains=token)

    rows = ICDCode.objects.filter(
        matching_descriptions
    ).values_list("code", "description")

    ranked: list[ICD10Candidate] = []

    for code, description in rows.iterator():
        score = _score_description(query_tokens, description)

        if score > 0:
            ranked.append(
                ICD10Candidate(
                    code=code,
                    description=description,
                    lexical_score=score,
                )
            )

    ranked.sort(
        key=lambda candidate: (
            -candidate.lexical_score,
            tuple(
                -value
                for value in _specificity_tiebreak(
                    query_tokens,
                    candidate.description,
                )
            ),
            candidate.code,
        )
    )

    if not ranked:
        return ICD10LookupResult(
            query=cleaned_query,
            status="no_confident_match",
            candidates=(),
            reason="No ICD-10-CM descriptions matched the query terms.",
        )

    qualifying = [
        candidate
        for candidate in ranked
        if candidate.lexical_score >= minimum_lexical_score
    ]

    if qualifying:
        return ICD10LookupResult(
            query=cleaned_query,
            status="candidates_found",
            candidates=tuple(qualifying[:limit]),
        )

    return ICD10LookupResult(
        query=cleaned_query,
        status="no_confident_match",
        candidates=tuple(ranked[:limit]),
        reason=(
            "No candidate met the configured lexical threshold. "
            "Returned weak matches are for review only."
        ),
    )


def search_hybrid_icd10(
    query: str,
    *,
    limit: int = 5,
    minimum_lexical_score: float = _DEFAULT_MINIMUM_LEXICAL_SCORE,
    minimum_semantic_score: float = _DEFAULT_MINIMUM_SEMANTIC_SCORE,
) -> ICD10LookupResult:
    """Combine lexical and semantic ICD-10-CM retrieval.

    Existing lexical retrieval remains available independently.
    Semantic results supplement lexical candidates.

    Thresholds are provisional retrieval settings, not clinically
    validated confidence levels.
    """
    if not isinstance(query, str):
        raise TypeError("Diagnosis query must be a string.")

    if not isinstance(limit, int) or isinstance(limit, bool):
        raise TypeError("limit must be an integer.")

    if not 1 <= limit <= _MAX_RESULTS:
        raise ValueError(
            f"limit must be between 1 and {_MAX_RESULTS}."
        )

    if (
        isinstance(minimum_semantic_score, bool)
        or not isinstance(minimum_semantic_score, (int, float))
        or not math.isfinite(minimum_semantic_score)
        or not 0.0 <= minimum_semantic_score <= 1.0
    ):
        raise ValueError(
            "minimum_semantic_score must be a finite number "
            "between 0 and 1."
        )

    # Validate and retrieve lexical results without changing the
    # existing lexical scoring algorithm.
    lexical_result = search_icd10(
        query,
        limit=_MAX_RESULTS,
        minimum_lexical_score=minimum_lexical_score,
    )

    if not lexical_result.query:
        return ICD10LookupResult(
            query=lexical_result.query,
            status="no_confident_match",
            candidates=(),
            reason=lexical_result.reason,
        )

    # Import lazily so lexical-only callers do not need the embedding
    # model loaded or the semantic index built.
    # Import lazily so lexical-only callers do not need the embedding
    # model loaded or the semantic index built.
    from dashboard.extraction.icd10_semantic import (
        SemanticIndexConfigurationError,
        SemanticIndexNotReadyError,
        search_semantic_icd10,
    )

    try:
        semantic_candidates = search_semantic_icd10(
            lexical_result.query,
            limit=_MAX_RESULTS,
        )
    except (
        SemanticIndexConfigurationError,
        SemanticIndexNotReadyError,
    ):
        # Preserve lexical results, but clearly disclose that semantic
        # retrieval was unavailable. Do not hide unrelated exceptions.
        fallback_reason = (
            "Semantic retrieval is unavailable; returning lexical-only "
            "candidates for review."
        )

        if lexical_result.reason:
            fallback_reason = (
                f"{lexical_result.reason} {fallback_reason}"
            )

        return ICD10LookupResult(
            query=lexical_result.query,
            status=lexical_result.status,
            candidates=tuple(lexical_result.candidates[:limit]),
            reason=fallback_reason,
        )

    lexical_by_code = {
        candidate.code: candidate
        for candidate in lexical_result.candidates
    }
    semantic_by_code = {
        candidate.code: candidate
        for candidate in semantic_candidates
    }

    # Merge both candidate sources by unique ICD-10 code.
    merged: list[ICD10Candidate] = []

    for code in lexical_by_code.keys() | semantic_by_code.keys():
        lexical = lexical_by_code.get(code)
        semantic = semantic_by_code.get(code)

        lexical_score = (
            lexical.lexical_score
            if lexical is not None
            else 0.0
        )

        semantic_score = (
            semantic.semantic_score
            if semantic is not None
            else None
        )

        if lexical is not None and semantic_score is not None:
            combined_score = (
                _DEFAULT_LEXICAL_WEIGHT * lexical_score
                + (1.0 - _DEFAULT_LEXICAL_WEIGHT) * semantic_score
            )
        elif lexical is not None:
            combined_score = lexical_score
        else:
            combined_score = semantic_score or 0.0

        description = (
            lexical.description
            if lexical is not None
            else semantic.description
        )

        merged.append(
            ICD10Candidate(
                code=code,
                description=description,
                lexical_score=round(lexical_score, 6),
                semantic_score=(
                    round(semantic_score, 6)
                    if semantic_score is not None
                    else None
                ),
                combined_score=round(combined_score, 6),
            )
        )

    # Use a deterministic order when scores are tied.
    merged.sort(
        key=lambda candidate: (
            -(candidate.combined_score or 0.0),
            candidate.code,
        )
    )

    # Either retrieval method can qualify a candidate. The semantic
    # threshold remains provisional and requires later evaluation.
    qualifying = [
        candidate
        for candidate in merged
        if (
            candidate.lexical_score >= minimum_lexical_score
            or (
                candidate.semantic_score is not None
                and candidate.semantic_score >= minimum_semantic_score
            )
        )
    ]

    if qualifying:
        return ICD10LookupResult(
            query=lexical_result.query,
            status="candidates_found",
            candidates=tuple(qualifying[:limit]),
        )

    weak_candidates = tuple(merged[:limit])

    if weak_candidates:
        reason = (
            "No candidate met the lexical or semantic threshold. "
            "Returned weak matches are for review only."
        )
    else:
        reason = (
            "Neither lexical nor semantic retrieval returned candidates."
        )

    return ICD10LookupResult(
        query=lexical_result.query,
        status="no_confident_match",
        candidates=weak_candidates,
        reason=reason,
    )


__all__ = [
    "ICD10Candidate",
    "ICD10LookupResult",
    "search_icd10",
    "search_hybrid_icd10",
]