"""Connect validated diagnosis mentions to ICD-10 candidate retrieval."""

from typing import cast

from pydantic import BaseModel, ConfigDict, Field, StrictInt, StrictStr

from dashboard.extraction.coding_schema import (
    ICD10CodingResult,
    coding_result_from_lookup,
)
from dashboard.extraction.icd10_search import search_icd10
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
) -> DiagnosisCodingBatch:
    """Validate extraction output, then retrieve candidates for diagnoses.

    Original evidence and mention status are preserved in the output.
    Non-diagnosis mentions are not sent to ICD-10 retrieval.

    This function performs no database writes. A candidate is a
    reference suggestion, not confirmation that a diagnosis is
    clinically correct.
    """
    extraction = validate_extraction_output(payload, original_note)
    coded_diagnoses: list[CodedDiagnosisMention] = []

    for item in extraction.items:
        if item.category != "diagnosis":
            continue

        lookup = search_icd10(
            item.entity,
            limit=limit,
            minimum_lexical_score=minimum_lexical_score,
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