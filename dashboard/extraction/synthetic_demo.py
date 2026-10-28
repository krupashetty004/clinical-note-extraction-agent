"""Deterministic, non-clinical providers for local integration testing only.

These providers do not inspect clinical content or call an AI model. They
always return no extracted items and require human review. Never use them for
clinical decisions or as evidence of model quality.
"""


class SyntheticDemoExtractionProvider:
    """Return an intentionally empty result for UI plumbing tests."""

    def extract(self, input_text: str) -> dict:
        if not isinstance(input_text, str):
            raise TypeError("input_text must be a string.")

        return {
            "items": [],
            "needs_review": True,
            "review_reasons": [
                "Synthetic demonstration only: no AI model was called and "
                "no clinical findings were extracted. Review the original "
                "note manually.",
            ],
        }


class SyntheticDemoVerificationProvider:
    """Return a review-required placeholder, not a clinical verification."""

    def verify(self, original_note, extraction, coding) -> dict:
        if not isinstance(original_note, str):
            raise TypeError("original_note must be a string.")

        return {
            "item_checks": [],
            "potential_omissions": [],
            "needs_review": True,
            "review_reasons": [
                "Synthetic demonstration only: independent clinical "
                "verification was not performed.",
            ],
        }
