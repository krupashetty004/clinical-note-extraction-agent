"""Connect validated diagnosis mentions to hybrid ICD-10 retrieval."""

from typing import cast

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

from dashboard.extraction.coding_schema import (
    ICD10CodingResult,
    coding_result_from_lookup,
)
from dashboard.extraction.icd10_search import (
    ICD10LookupResult,
    search_hybrid_icd10,
    search_icd10,
)
from dashboard.extraction.schema import DiagnosisStatus
from dashboard.extraction.service import validate_extraction_output


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
            lookup = search_hybrid_icd10(
                item.entity,
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