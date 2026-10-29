import collections

# Simple in‑memory credit tracker for Vision API calls.
# This is deliberately lightweight – it lives only for the process lifetime
# and is reset on each server start. It is sufficient for monitoring usage
# during development and test runs where we mock the external services.

_credit_counter = collections.Counter()

def increment_credit(provider: str) -> None:
    """Increment the credit usage counter for the given *provider*.

    Args:
        provider: Identifier of the vision provider, e.g. "groq" or "gemini".
    """
    _credit_counter[provider] += 1

def get_credits() -> dict:
    """Return a snapshot of the current credit usage.

    Returns a dict mapping provider names to the number of calls made.
    """
    return dict(_credit_counter)
