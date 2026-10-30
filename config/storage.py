"""Validated configuration for optional private Neon Object Storage."""

from __future__ import annotations

from collections.abc import Mapping
from urllib.parse import urlsplit


LOCAL_STORAGE_BACKEND = "django.core.files.storage.FileSystemStorage"
NEON_STORAGE_BACKEND = "storages.backends.s3.S3Storage"
NEON_OBJECT_STORAGE_REGIONS = frozenset({
    "us-east-2",
    "us-east-1",
    "eu-central-1",
    "ap-southeast-1",
})


def neon_object_storage_enabled(environment: Mapping[str, str]) -> bool:
    """Read the explicit opt-in flag and reject ambiguous values."""
    value = environment.get("MIRAI_ENABLE_NEON_OBJECT_STORAGE", "").strip().casefold()
    if value in {"", "0", "false", "no", "off"}:
        return False
    if value in {"1", "true", "yes", "on"}:
        return True
    raise RuntimeError(
        "MIRAI_ENABLE_NEON_OBJECT_STORAGE must be set to 1 or 0."
    )


def build_default_storage_config(
    environment: Mapping[str, str],
) -> dict[str, object]:
    """Build a local default or an explicitly configured private S3 backend.

    Neon bucket privacy is controlled in Neon, not by S3 object ACLs.
    Therefore the backend deliberately sends no ACL and signs generated URLs.
    """
    if not neon_object_storage_enabled(environment):
        return {"BACKEND": LOCAL_STORAGE_BACKEND}

    required = (
        "NEON_STORAGE_BUCKET",
        "AWS_ENDPOINT_URL_S3",
        "AWS_REGION",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
    )
    values = {
        name: environment.get(name, "").strip()
        for name in required
    }
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise RuntimeError(
            "Neon Object Storage is enabled but required environment variables "
            f"are missing: {', '.join(missing)}."
        )

    if values["AWS_REGION"] not in NEON_OBJECT_STORAGE_REGIONS:
        supported = ", ".join(sorted(NEON_OBJECT_STORAGE_REGIONS))
        raise RuntimeError(
            "AWS_REGION is not currently supported by Neon Object Storage. "
            f"Supported regions: {supported}."
        )

    endpoint = urlsplit(values["AWS_ENDPOINT_URL_S3"])
    if (
        endpoint.scheme != "https"
        or not endpoint.hostname
        or endpoint.username
        or endpoint.password
        or endpoint.query
        or endpoint.fragment
        or endpoint.path not in {"", "/"}
    ):
        raise RuntimeError(
            "AWS_ENDPOINT_URL_S3 must be an HTTPS endpoint URL without credentials, "
            "a path, query string, or fragment."
        )

    return {
        "BACKEND": NEON_STORAGE_BACKEND,
        "OPTIONS": {
            "bucket_name": values["NEON_STORAGE_BUCKET"],
            "endpoint_url": values["AWS_ENDPOINT_URL_S3"].rstrip("/"),
            "region_name": values["AWS_REGION"],
            "access_key": values["AWS_ACCESS_KEY_ID"],
            "secret_key": values["AWS_SECRET_ACCESS_KEY"],
            "addressing_style": "path",
            "signature_version": "s3v4",
            "default_acl": None,
            "querystring_auth": True,
            "querystring_expire": 300,
            "file_overwrite": False,
            "custom_domain": None,
            "use_ssl": True,
            "verify": True,
        },
    }
