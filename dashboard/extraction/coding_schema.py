"""Validated result contract for ICD-10-CM candidate retrieval."""

from typing import TYPE_CHECKING, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    FiniteFloat,
    StrictInt,
    StrictStr,
    model_validator,
)

if TYPE_CHECKING:
    from dashboard.extraction.icd10_search import ICD10LookupResult


CodingStatus = Literal[
    "candidates_found",
    "no_confident_match",
]

CandidateDisposition = Literal[
    "threshold_met",
    "weak_matches_for_review",
    "none",
]


class ICD10CodeCandidate(BaseModel):
    """One candidate from the ICD-10-CM reference table."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    code: StrictStr = Field(
        min_length=3,
        max_length=7,
        pattern=r"^[A-Z][A-Z0-9]{2,6}$",
    )
    description: StrictStr = Field(min_length=1)
    lexical_score: FiniteFloat = Field(ge=0.0, le=1.0)

    semantic_score: FiniteFloat | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    combined_score: FiniteFloat | None = Field(
        default=None,
        ge=0.0,
        le=1.0,
    )
    rank: StrictInt = Field(ge=1)


class ICD10CodingResult(BaseModel):
    """Validated result of ICD-10-CM diagnosis candidate retrieval."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    query: StrictStr = Field(max_length=200)
    status: CodingStatus
    candidate_disposition: CandidateDisposition
    candidates: tuple[ICD10CodeCandidate, ...]
    reason: StrictStr | None = None

    @model_validator(mode="after")
    def validate_result_consistency(self) -> "ICD10CodingResult":
        """Validate candidate uniqueness, ranking and result status."""

        codes = [candidate.code for candidate in self.candidates]

        if len(codes) != len(set(codes)):
            raise ValueError("Candidate codes must be unique.")

        expected_ranks = list(range(1, len(self.candidates) + 1))
        actual_ranks = [
            candidate.rank for candidate in self.candidates
        ]

        if actual_ranks != expected_ranks:
            raise ValueError(
                "Candidate ranks must be consecutive, starting at 1."
            )

        scores = [
            (
                candidate.combined_score
                if candidate.combined_score is not None
                else candidate.lexical_score
            )
            for candidate in self.candidates
        ]

        if any(
            scores[index] < scores[index + 1]
            for index in range(len(scores) - 1)
        ):
            raise ValueError(
                "Candidates must be ordered by descending retrieval score."
            )

        if self.status == "candidates_found":
            if not self.candidates:
                raise ValueError(
                    "candidates_found requires at least one candidate."
                )

            if self.candidate_disposition != "threshold_met":
                raise ValueError(
                    "candidates_found requires threshold_met disposition."
                )

            if self.reason is not None:
                raise ValueError(
                    "A confident retrieval result must not have "
                    "a no-match reason."
                )

        else:
            if not self.reason or not self.reason.strip():
                raise ValueError(
                    "no_confident_match requires an explanatory reason."
                )

            if self.candidates:
                if (
                    self.candidate_disposition
                    != "weak_matches_for_review"
                ):
                    raise ValueError(
                        "Weak candidates must be marked for review only."
                    )
            elif self.candidate_disposition != "none":
                raise ValueError(
                    "An empty candidate list must use disposition 'none'."
                )

        return self


def coding_result_from_lookup(
    result: "ICD10LookupResult",
) -> ICD10CodingResult:
    """Convert lookup results into the validated coding-result schema."""

    candidates = tuple(
        ICD10CodeCandidate(
            code=candidate.code,
            description=candidate.description,
            lexical_score=candidate.lexical_score,
            semantic_score=candidate.semantic_score,
            combined_score=candidate.combined_score,
            rank=index,
        )
        for index, candidate in enumerate(
            result.candidates,
            start=1,
        )
    )

    if result.status == "candidates_found":
        disposition: CandidateDisposition = "threshold_met"
    elif candidates:
        disposition = "weak_matches_for_review"
    else:
        disposition = "none"

    return ICD10CodingResult(
        query=result.query,
        status=result.status,
        candidate_disposition=disposition,
        candidates=candidates,
        reason=result.reason if result.status != "candidates_found" else None,
    )