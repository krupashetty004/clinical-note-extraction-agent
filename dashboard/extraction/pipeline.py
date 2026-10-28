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


# Preserve only stable provider categories defined by our adapter. Provider
# exception text and arbitrary third-party error codes are never surfaced.
_SAFE_PROVIDER_FAILURE_CODES = frozenset({
    "provider_timeout",
    "provider_failed",
    "provider_bad_request",
    "provider_authentication_failed",
    "provider_permission_denied",
    "provider_resource_not_found",
    "provider_request_too_large",
    "provider_rate_limited",
    "provider_server_error",
    "provider_connection_error",
    "provider_response_shape_invalid",
    "provider_empty_response",
    "provider_invalid_json",
    "provider_invalid_json_shape",
})


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
        if provider_code not in _SAFE_PROVIDER_FAILURE_CODES:
            provider_code = "provider_failed"
        message = (
            "The extraction provider timed out."
            if provider_code == "provider_timeout"
            else "The extraction provider failed."
        )
        raise ExtractionProviderError(
            message,
            code=provider_code,
        ) from exc

    # Schema and evidence errors remain distinguishable from provider
    # failures through ExtractionOutputError.code.
    return validate_extraction_output(payload, original_note)


__all__ = [
    "ExtractionOutputError",
    "ExtractionProviderError",
    "run_extraction",
]