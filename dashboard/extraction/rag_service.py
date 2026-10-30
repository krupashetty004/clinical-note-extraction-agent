"""Local RAG retrieval service for doctor-managed reference knowledge.

Complies with architecture.md Section 5.5:
- Hybrid keyword / lexical matching with priority-aware ranking.
- Hard filters on document status (active only, published only).
- Priority modulates ordering among relevant eligible results without promoting irrelevant text.
- Returns traceable chunk references with document title, version, and citations.
"""
from __future__ import annotations

import re
from typing import Any

from dashboard.models import KnowledgeDocument

TOKEN_PATTERN = re.compile(r"[^\W_]+", re.UNICODE)


def _tokenize(text: str) -> set[str]:
    return {token.casefold() for token in TOKEN_PATTERN.findall(text)}


def chunk_text(
    text: str,
    chunk_size: int = 350,
    overlap: int = 50,
) -> list[dict[str, Any]]:
    """Split content into overlapping, traceable chunks preserving offsets."""
    if not text or not text.strip():
        return []

    chunks: list[dict[str, Any]] = []
    # If text has double newlines (paragraphs), split on paragraphs first
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]

    cursor = 0
    chunk_idx = 1

    for p in paragraphs:
        start_offset = text.find(p, cursor)
        if start_offset == -1:
            start_offset = cursor
        end_offset = start_offset + len(p)
        cursor = end_offset

        if len(p) <= chunk_size:
            chunks.append({
                "chunk_index": chunk_idx,
                "text": p,
                "start_offset": start_offset,
                "end_offset": end_offset,
            })
            chunk_idx += 1
        else:
            # Sub-chunk long paragraphs
            p_cursor = 0
            while p_cursor < len(p):
                p_end = min(p_cursor + chunk_size, len(p))
                sub_text = p[p_cursor:p_end]
                chunks.append({
                    "chunk_index": chunk_idx,
                    "text": sub_text,
                    "start_offset": start_offset + p_cursor,
                    "end_offset": start_offset + p_end,
                })
                chunk_idx += 1
                if p_end == len(p):
                    break
                p_cursor += max(1, chunk_size - overlap)

    return chunks


def score_passage(query_tokens: set[str], passage: str) -> float:
    """Calculate normalized token coverage and lexical relevance."""
    if not query_tokens or not passage:
        return 0.0

    passage_tokens = _tokenize(passage)
    if not passage_tokens:
        return 0.0

    matched = query_tokens.intersection(passage_tokens)
    if not matched:
        return 0.0

    # Recall on query terms (coverage)
    coverage = len(matched) / len(query_tokens)
    # Density in passage
    density = len(matched) / len(passage_tokens)

    return round(0.75 * coverage + 0.25 * min(1.0, density * 5), 4)


def retrieve_knowledge_passages(
    query: str,
    *,
    top_k: int = 3,
    min_score: float = 0.15,
) -> list[dict[str, Any]]:
    """Retrieve scored, filtered reference passages from published documents."""
    if not isinstance(query, str):
        raise TypeError("query must be a string.")
    if isinstance(top_k, bool) or not isinstance(top_k, int) or not 1 <= top_k <= 20:
        raise ValueError("top_k must be an integer between 1 and 20.")
    if (
        isinstance(min_score, bool)
        or not isinstance(min_score, (int, float))
        or not 0.0 <= min_score <= 1.0
    ):
        raise ValueError("min_score must be between 0 and 1.")

    query_tokens = _tokenize(query)
    if not query_tokens:
        return []

    # Retrieval is restricted to explicitly approved active documents.
    # Uploads start as needs_review/inactive and never enter RAG until a
    # doctor or administrator publishes them through the knowledge UI.
    documents = KnowledgeDocument.objects.filter(
        is_active=True,
        ingestion_status__in={"manual", "published"},
    )

    scored_candidates: list[dict[str, Any]] = []

    for doc in documents:
        content = doc.content or ""
        doc_priority = doc.priority or 0
        chunks = chunk_text(content)

        # Also check title match
        title_score = score_passage(query_tokens, doc.title)

        for chunk in chunks:
            base_score = score_passage(query_tokens, chunk["text"])
            combined_base = max(base_score, 0.5 * title_score + 0.5 * base_score)

            if combined_base < min_score:
                continue

            # Architecture.md Section 5.5:
            # Priority should modulate ordering among relevant eligible results;
            # bounded multiplier between 1.0 and 1.3
            priority_boost = 1.0 + 0.06 * min(doc_priority, 5)
            final_score = round(combined_base * priority_boost, 4)

            scored_candidates.append({
                "document_id": doc.pk,
                "title": doc.title,
                "version": doc.version_number,
                "priority": doc_priority,
                "source_type": doc.source_type,
                "source_filename": doc.source_filename,
                "source_citations": doc.source_citations,
                "chunk_index": chunk["chunk_index"],
                "start_offset": chunk["start_offset"],
                "end_offset": chunk["end_offset"],
                "text": chunk["text"],
                "score": final_score,
            })

    # Sort descending by score, then document priority
    scored_candidates.sort(key=lambda x: (-x["score"], -x["priority"], x["document_id"]))

    return scored_candidates[:top_k]
