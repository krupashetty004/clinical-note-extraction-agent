"""Provider invocation and validation pipeline."""

from dashboard.extraction.providers import ExtractionProvider
from dashboard.extraction.schema import ExtractionResult
from dashboard.extraction.service import (
    ExtractionOutputError,
    validate_extraction_output,
)


class ExtractionProviderError(RuntimeError):
    """Raised when a provider fails to return an extraction payload."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "provider_failed",
    ) -> None:
        super().__init__(message)
        self.code = code


def run_extraction(
    provider: ExtractionProvider,
    original_note: str,
) -> ExtractionResult:
    """Run a provider and validate its output against the original note.

    This function does not save data or call a provider automatically.
    The caller supplies the provider implementation explicitly.
    """
    if not isinstance(original_note, str):
        raise TypeError("original_note must be a string.")

    try:
        payload = provider.extract(original_note)
    except TimeoutError as exc:
        raise ExtractionProviderError(
            "The extraction provider timed out.",
            code="provider_timeout",
        ) from exc
    except Exception as exc:
        # Do not include provider exception details because they could
        # contain note text, credentials, or other sensitive values.
        provider_code = getattr(exc, "code", "provider_failed")
        if provider_code == "provider_timeout":
            raise ExtractionProviderError(
                "The extraction provider timed out.",
                code="provider_timeout",
            ) from exc
        raise ExtractionProviderError(
            "The extraction provider failed."
        ) from exc

    # Schema and evidence errors remain distinguishable from provider
    # failures through ExtractionOutputError.code.
    return validate_extraction_output(payload, original_note)


__all__ = [
    "ExtractionOutputError",
    "ExtractionProviderError",
    "run_extraction",
]