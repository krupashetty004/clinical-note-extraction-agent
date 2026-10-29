"""Initialize the pinned ICD-10 reference data for the temporary demo."""

from hashlib import sha256
from pathlib import Path
from typing import Iterable

from django.conf import settings
from django.core.management import BaseCommand, CommandError, call_command

from dashboard.extraction.icd10 import iter_icd10_code_file
from dashboard.models import ICDCode


SOURCE_RELATIVE_PATH = (
    Path("data")
    / "reference"
    / "icd10cm-codes-2027.txt"
)

EXPECTED_RECORD_COUNT = 74879

EXPECTED_SOURCE_SHA256 = (
    "3C0583A38EE0E848F7DC0AC8CE88E8F001BBBA8C6385ED825D44D46F6E5297C9"
)


def _source_sha256(path: Path) -> str:
    """Calculate the source file's SHA-256 checksum without loading it whole."""
    digest = sha256()

    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest().upper()


def _fingerprint_rows(
    rows: Iterable[tuple[str, str]],
) -> str:
    """Create a deterministic fingerprint of code-description records."""
    digest = sha256()

    for code, description in rows:
        digest.update(code.encode("utf-8"))
        digest.update(b"\0")
        digest.update(description.encode("utf-8"))
        digest.update(b"\n")

    return digest.hexdigest()


class Command(BaseCommand):
    help = (
        "Initialize the temporary demo's ICD-10 reference table "
        "from its pinned source file."
    )

    def handle(self, *args, **options):
        source = Path(settings.BASE_DIR) / SOURCE_RELATIVE_PATH

        if not source.is_file():
            raise CommandError(
                "The pinned ICD-10 reference file is missing. "
                f"Expected: {source}"
            )

        try:
            source_hash = _source_sha256(source)
        except OSError as exc:
            raise CommandError(
                "Could not read the ICD-10 reference file."
            ) from exc

        if source_hash != EXPECTED_SOURCE_SHA256:
            raise CommandError(
                "The ICD-10 reference file checksum does not match "
                "the pinned source. No database changes were made."
            )

        try:
            source_rows = sorted(
                (record.code, record.description)
                for record in iter_icd10_code_file(source)
            )
        except (OSError, UnicodeError, ValueError) as exc:
            raise CommandError(
                "The ICD-10 reference file could not be validated."
            ) from exc

        source_count = len(source_rows)
        unique_code_count = len({code for code, _ in source_rows})

        if (
            source_count != EXPECTED_RECORD_COUNT
            or unique_code_count != EXPECTED_RECORD_COUNT
        ):
            raise CommandError(
                "The ICD-10 source record count or uniqueness check failed. "
                "No database changes were made."
            )

        source_fingerprint = _fingerprint_rows(source_rows)
        existing_count = ICDCode.objects.count()

        if existing_count == 0:
            self.stdout.write(
                "ICD-10 reference table is empty; importing pinned data."
            )

            # Reuse the existing validated, transactional importer.
            call_command(
                "import_icd10",
                source=source,
                apply=True,
                stdout=self.stdout,
                stderr=self.stderr,
            )

        elif existing_count != EXPECTED_RECORD_COUNT:
            raise CommandError(
                f"The ICD-10 table contains {existing_count} rows; "
                f"expected either 0 or {EXPECTED_RECORD_COUNT}. "
                "Refusing to import into a partially populated table."
            )

        database_rows = tuple(
            ICDCode.objects.order_by("code").values_list(
                "code",
                "description",
            )
        )

        if (
            len(database_rows) != EXPECTED_RECORD_COUNT
            or _fingerprint_rows(database_rows) != source_fingerprint
        ):
            raise CommandError(
                "The ICD-10 database contents do not match the pinned "
                "reference source. Manual investigation is required."
            )

        if existing_count == 0:
            self.stdout.write(
                self.style.SUCCESS(
                    "ICD-10 reference data initialized and verified."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    "ICD-10 reference data already matches the source; "
                    "no import was needed."
                )
            )