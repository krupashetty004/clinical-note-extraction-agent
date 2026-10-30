"""Shared helpers for provider configuration integrity."""
from __future__ import annotations

import hashlib
import json
import os
from typing import Any


def ai_configuration_fingerprint(
    configuration: Any,
    *,
    api_key: str | None = None,
) -> str:
    """Fingerprint all values used by a provider connection test.

    The API key is represented only by a one-way digest. Callers that already
    resolved an encrypted key may pass it explicitly so runtime validation uses
    the same credential rather than an environment fallback.
    """
    resolved_key = (
        api_key
        if api_key is not None
        else configuration.get_api_key()
        or os.environ.get("GROQ_API_KEY", "").strip()
    )
    payload = {
        "provider": configuration.provider,
        "model": configuration.model,
        "temperature": format(configuration.temperature, ".2f"),
        "max_tokens": configuration.max_tokens,
        "api_key_sha256": (
            hashlib.sha256(resolved_key.encode("utf-8")).hexdigest()
            if resolved_key
            else ""
        ),
    }
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
