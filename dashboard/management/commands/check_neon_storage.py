"""Run a synthetic-only upload/read/delete check against the configured storage."""

from __future__ import annotations

from uuid import uuid4

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = (
        "Upload, read, and delete one synthetic object to verify private Neon "
        "Object Storage connectivity."
    )

    def handle(self, *args, **options):
        if not getattr(settings, "NEON_OBJECT_STORAGE_ENABLED", False):
            raise CommandError(
                "Neon Object Storage is disabled. Set "
                "MIRAI_ENABLE_NEON_OBJECT_STORAGE=1 and configure the required "
                "AWS_* and NEON_STORAGE_BUCKET environment variables."
            )

        payload = b"mirai-object-storage-smoke-test-v1"
        object_name = f"mirai-storage-smoke/{uuid4().hex}.txt"
        saved_name = None

        try:
            saved_name = default_storage.save(
                object_name,
                ContentFile(payload),
            )
            with default_storage.open(saved_name, "rb") as stored:
                actual = stored.read()
            if actual != payload:
                raise ValueError("Synthetic object content did not match.")

            default_storage.delete(saved_name)
            if default_storage.exists(saved_name):
                raise ValueError("Synthetic smoke-test object was not deleted.")
        except Exception as exc:
            if saved_name:
                try:
                    default_storage.delete(saved_name)
                except Exception:
                    pass
            raise CommandError(
                "Private object storage smoke test failed "
                f"(error_type={type(exc).__name__}). "
                "Credential values and provider response details were not printed."
            ) from None

        self.stdout.write(
            self.style.SUCCESS(
                "Private object storage synthetic test object uploaded, read, and deleted."
            )
        )
