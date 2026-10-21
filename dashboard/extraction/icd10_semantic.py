"""Local semantic retrieval for the official ICD-10-CM reference table.

The index contains code descriptions only, not patient clinical notes.
The vector index is a rebuildable local cache and is not committed to Git.
"""

import hashlib
import json
import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Callable

import numpy as np
from fastembed import TextEmbedding

from dashboard.models import ICDCode


MODEL_NAME = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIMENSIONS = 384
DEFAULT_BATCH_SIZE = 128
MAX_BATCH_SIZE = 512
MAX_QUERY_LENGTH = 200
MAX_RESULTS = 20


class SemanticIndexConfigurationError(RuntimeError):
    """Raised when cache locations are not configured."""


class SemanticIndexNotReadyError(RuntimeError):
    """Raised when the semantic index is absent or stale."""


@dataclass(frozen=True, slots=True)
class SemanticCandidate:
    """One ICD-10-CM record ranked by embedding similarity."""

    code: str
    description: str
    semantic_score: float


@dataclass(frozen=True, slots=True)
class SemanticIndexBuildReport:
    """Summary of a semantic index build."""

    row_count: int
    cache_directory: str
    reused_existing_index: bool


@dataclass(frozen=True, slots=True)
class _LoadedIndex:
    codes: tuple[str, ...]
    descriptions: tuple[str, ...]
    vectors: np.ndarray


def _index_directory() -> Path:
    """Return the configured index path without defaulting to C:."""
    configured = os.environ.get("ICD10_SEMANTIC_INDEX_DIR")

    if configured:
        return Path(configured).expanduser().resolve()

    fastembed_cache = os.environ.get("FASTEMBED_CACHE_PATH")

    if not fastembed_cache:
        raise SemanticIndexConfigurationError(
            "Set ICD10_SEMANTIC_INDEX_DIR or FASTEMBED_CACHE_PATH "
            "to a cache directory on the intended drive."
        )

    return (
        Path(fastembed_cache).expanduser().resolve().parent
        / "icd10-semantic-index"
    )


def _model_cache_directory() -> Path:
    """Return the FastEmbed model cache directory."""
    configured = os.environ.get("FASTEMBED_CACHE_PATH")

    if not configured:
        raise SemanticIndexConfigurationError(
            "Set FASTEMBED_CACHE_PATH to the existing model cache "
            "before using semantic retrieval."
        )

    path = Path(configured).expanduser().resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


@lru_cache(maxsize=1)
def _get_model(cache_directory: str) -> TextEmbedding:
    """Reuse one embedding model per process."""
    return TextEmbedding(
        model_name=MODEL_NAME,
        cache_dir=cache_directory,
    )


def _get_rows() -> tuple[tuple[str, str], ...]:
    """Read reference records in deterministic order."""
    return tuple(
        ICDCode.objects.order_by("code").values_list(
            "code",
            "description",
        )
    )


def _fingerprint_rows(rows: tuple[tuple[str, str], ...]) -> str:
    """Build a stable fingerprint of the reference-table contents."""
    digest = hashlib.sha256()

    for code, description in rows:
        digest.update(code.encode("utf-8"))
        digest.update(b"\0")
        digest.update(description.encode("utf-8"))
        digest.update(b"\n")

    return digest.hexdigest()


@lru_cache(maxsize=1)
def _current_database_snapshot() -> tuple[
    tuple[tuple[str, str], ...],
    str,
]:
    """Read and fingerprint the ICD reference table once per process."""
    rows = _get_rows()

    if not rows:
        raise SemanticIndexNotReadyError(
            "The ICD-10-CM reference table is empty. "
            "Import the reference table before building the index."
        )

    return rows, _fingerprint_rows(rows)


def _cache_files(cache_directory: Path) -> tuple[Path, Path]:
    return (
        cache_directory / "icd10-bge-small-v1.5-vectors.npy",
        cache_directory / "icd10-bge-small-v1.5-metadata.json",
    )


def _is_current_index(
    vector_path: Path,
    metadata_path: Path,
    *,
    fingerprint: str,
    row_count: int,
) -> bool:
    """Return whether an existing cache matches this source table."""
    if not vector_path.is_file() or not metadata_path.is_file():
        return False

    try:
        metadata = json.loads(
            metadata_path.read_text(encoding="utf-8")
        )

        if (
            metadata.get("model_name") != MODEL_NAME
            or metadata.get("source_fingerprint") != fingerprint
            or metadata.get("row_count") != row_count
            or metadata.get("embedding_dimensions")
            != EMBEDDING_DIMENSIONS
        ):
            return False

        vectors = np.load(vector_path, mmap_mode="r", allow_pickle=False)
        return vectors.shape == (row_count, EMBEDDING_DIMENSIONS)

    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return False


def build_semantic_index(
    *,
    force: bool = False,
    batch_size: int = DEFAULT_BATCH_SIZE,
    progress_callback: Callable[[int, int], None] | None = None,
) -> SemanticIndexBuildReport:
    """Embed ICD descriptions and save a rebuildable local index.

    The vector matrix is written incrementally to reduce peak memory use.
    The metadata is replaced only after the new vector file is complete.
    """
    if not isinstance(batch_size, int) or isinstance(batch_size, bool):
        raise TypeError("batch_size must be an integer.")

    if not 1 <= batch_size <= MAX_BATCH_SIZE:
        raise ValueError(
            f"batch_size must be between 1 and {MAX_BATCH_SIZE}."
        )

    rows = _get_rows()

    if not rows:
        raise SemanticIndexNotReadyError(
            "The ICD-10-CM reference table is empty. "
            "Import the reference table before building the index."
        )

    fingerprint = _fingerprint_rows(rows)
    cache_directory = _index_directory()
    cache_directory.mkdir(parents=True, exist_ok=True)

    vector_path, metadata_path = _cache_files(cache_directory)

    if not force and _is_current_index(
        vector_path,
        metadata_path,
        fingerprint=fingerprint,
        row_count=len(rows),
    ):
        return SemanticIndexBuildReport(
            row_count=len(rows),
            cache_directory=str(cache_directory),
            reused_existing_index=True,
        )

    temporary_vector_path = cache_directory / (
        "icd10-bge-small-v1.5-vectors.building.npy"
    )
    temporary_metadata_path = cache_directory / (
        "icd10-bge-small-v1.5-metadata.building.json"
    )

    temporary_vector_path.unlink(missing_ok=True)
    temporary_metadata_path.unlink(missing_ok=True)

    model = _get_model(str(_model_cache_directory()))

    vector_matrix = np.lib.format.open_memmap(
        temporary_vector_path,
        mode="w+",
        dtype=np.float32,
        shape=(len(rows), EMBEDDING_DIMENSIONS),
    )

    try:
        for start in range(0, len(rows), batch_size):
            batch = rows[start : start + batch_size]

            passages = [
                f"passage: {code}. {description}"
                for code, description in batch
            ]

            embeddings = np.asarray(
                list(model.embed(passages, batch_size=batch_size)),
                dtype=np.float32,
            )

            expected_shape = (len(batch), EMBEDDING_DIMENSIONS)

            if embeddings.shape != expected_shape:
                raise RuntimeError(
                    "Embedding model returned an unexpected vector shape."
                )

            # Store normalized vectors so dot products approximate cosine
            # similarity during search.
            norms = np.linalg.norm(embeddings, axis=1, keepdims=True)

            if np.any(norms == 0):
                raise RuntimeError(
                    "Embedding model returned a zero-length vector."
                )

            embeddings /= norms
            vector_matrix[start : start + len(batch)] = embeddings

            completed = start + len(batch)

            if progress_callback and (
                completed % 5000 == 0 or completed == len(rows)
            ):
                progress_callback(completed, len(rows))

        vector_matrix.flush()

    finally:
        del vector_matrix

    metadata = {
        "model_name": MODEL_NAME,
        "embedding_dimensions": EMBEDDING_DIMENSIONS,
        "row_count": len(rows),
        "source_fingerprint": fingerprint,
        "records": [
            {"code": code, "description": description}
            for code, description in rows
        ],
    }

    try:
        temporary_metadata_path.write_text(
            json.dumps(metadata, ensure_ascii=False),
            encoding="utf-8",
        )

        os.replace(temporary_vector_path, vector_path)
        os.replace(temporary_metadata_path, metadata_path)

    except OSError:
        # Leave no partial temporary files after a failed build.
        temporary_vector_path.unlink(missing_ok=True)
        temporary_metadata_path.unlink(missing_ok=True)
        raise

    _current_database_snapshot.cache_clear()
    _load_index.cache_clear()

    return SemanticIndexBuildReport(
        row_count=len(rows),
        cache_directory=str(cache_directory),
        reused_existing_index=False,
    )


@lru_cache(maxsize=1)
def _load_index(
    cache_directory: str,
    expected_fingerprint: str,
) -> _LoadedIndex:
    """Load a validated vector cache using memory mapping."""
    directory = Path(cache_directory)
    vector_path, metadata_path = _cache_files(directory)

    if not vector_path.is_file() or not metadata_path.is_file():
        raise SemanticIndexNotReadyError(
            "The ICD-10-CM semantic index has not been built. "
            "Run: python manage.py build_icd10_semantic_index"
        )

    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))

        if metadata.get("model_name") != MODEL_NAME:
            raise SemanticIndexNotReadyError(
                "The cached embedding model does not match the configured model. "
                "Rebuild the ICD-10-CM semantic index."
            )

        if metadata.get("source_fingerprint") != expected_fingerprint:
            raise SemanticIndexNotReadyError(
                "The ICD-10-CM table has changed since the semantic index "
                "was built. Rebuild the semantic index."
            )

        records = metadata["records"]
        codes = tuple(record["code"] for record in records)
        descriptions = tuple(
            record["description"] for record in records
        )

        vectors = np.load(
            vector_path,
            mmap_mode="r",
            allow_pickle=False,
        )

    except SemanticIndexNotReadyError:
        raise
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise SemanticIndexNotReadyError(
            "The ICD-10-CM semantic cache is invalid. "
            "Rebuild the semantic index."
        ) from exc

    if (
        len(codes) != len(descriptions)
        or len(codes) != vectors.shape[0]
        or vectors.shape != (len(codes), EMBEDDING_DIMENSIONS)
    ):
        raise SemanticIndexNotReadyError(
            "The ICD-10-CM semantic cache has inconsistent dimensions. "
            "Rebuild the semantic index."
        )

    return _LoadedIndex(
        codes=codes,
        descriptions=descriptions,
        vectors=vectors,
    )


def search_semantic_icd10(
    query: str,
    *,
    limit: int = 20,
) -> tuple[SemanticCandidate, ...]:
    """Return the highest-similarity ICD-10 candidates.

    Results are semantic retrieval suggestions, not clinical confirmation.
    The hybrid search applies separate provisional retrieval thresholds.
    """
    if not isinstance(query, str):
        raise TypeError("Diagnosis query must be a string.")

    if not isinstance(limit, int) or isinstance(limit, bool):
        raise TypeError("limit must be an integer.")

    if not 1 <= limit <= MAX_RESULTS:
        raise ValueError(
            f"limit must be between 1 and {MAX_RESULTS}."
        )

    cleaned_query = query.strip()

    if len(cleaned_query) > MAX_QUERY_LENGTH:
        raise ValueError(
            f"Diagnosis query cannot exceed {MAX_QUERY_LENGTH} characters."
        )

    if not cleaned_query:
        return ()

    rows, fingerprint = _current_database_snapshot()
    if not rows:
        return ()

    cache_directory = _index_directory()

    index = _load_index(
        str(cache_directory),
        fingerprint,
    )

    model = _get_model(str(_model_cache_directory()))

    query_embeddings = list(
        model.embed([f"query: {cleaned_query}"], batch_size=1)
    )

    if len(query_embeddings) != 1:
        raise RuntimeError("Embedding model returned no query vector.")

    query_vector = np.asarray(
        query_embeddings[0],
        dtype=np.float32,
    )

    if query_vector.shape != (EMBEDDING_DIMENSIONS,):
        raise RuntimeError(
            "Embedding model returned an unexpected query dimension."
        )

    query_norm = float(np.linalg.norm(query_vector))

    if query_norm == 0:
        raise RuntimeError("Embedding model returned a zero query vector.")

    query_vector /= query_norm

    # The index is normalized, so dot product computes cosine similarity.
    similarities = index.vectors @ query_vector

    top_count = min(limit, len(index.codes))

    if top_count == len(index.codes):
        candidate_indices = np.argsort(similarities)[::-1]
    else:
        candidate_indices = np.argpartition(
            similarities,
            -top_count,
        )[-top_count:]
        candidate_indices = candidate_indices[
            np.argsort(similarities[candidate_indices])[::-1]
        ]

    results = []

    for candidate_index in candidate_indices:
        index_position = int(candidate_index)
        score = float(similarities[index_position])

        # The downstream schema represents scores on the range [0, 1].
        score = max(0.0, min(1.0, score))

        results.append(
            SemanticCandidate(
                code=index.codes[index_position],
                description=index.descriptions[index_position],
                semantic_score=round(score, 6),
            )
        )

    return tuple(results)


__all__ = [
    "SemanticCandidate",
    "SemanticIndexBuildReport",
    "SemanticIndexConfigurationError",
    "SemanticIndexNotReadyError",
    "build_semantic_index",
    "search_semantic_icd10",
]