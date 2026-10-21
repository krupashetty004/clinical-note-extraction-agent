"""Interfaces for clinical extraction providers.

Providers return untrusted structured data. The extraction service
must validate that data before any result is accepted or persisted.

No external AI provider is implemented in this module.
"""

from typing import Protocol


class ExtractionProvider(Protocol):
    """Contract implemented by synthetic or real extraction providers."""

    def extract(self, input_text: str) -> object:
        """Return structured extraction data for the supplied text.

        Args:
            input_text: Text supplied to the extraction component.

        Returns:
            An untrusted Python object, usually a dictionary.

        Implementations must not persist extraction results.
        Callers must validate the returned data before using it.
        """
        ...