"""Validate and import an ICD-10-CM code-description file."""

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from dashboard.extraction.icd10 import iter_icd10_code_file
from dashboard.models import ICDCode


class Command(BaseCommand):
    help = (
        "Validate an ICD-10-CM reference file, then optionally import "
        "its codes and descriptions."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--source",
            type=Path,
            required=True,
            help="Path to the fixed-width ICD-10-CM code file.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=1000,
            help="Number of records to process per database batch.",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Write validated records to the database.",
        )

    def handle(self, *args, **options):
        source = options["source"]
        batch_size = options["batch_size"]
        apply_changes = options["apply"]

        if not source.is_file():
            raise CommandError(
                f"Reference file does not exist: {source}"
            )

        if batch_size < 1:
            raise CommandError("--batch-size must be greater than zero.")

        # Pass 1: validate the complete input before any database writes.
        total_records = 0
        seen_codes = set()
        duplicate_codes = []

        try:
            for record in iter_icd10_code_file(source):
                total_records += 1

                if record.code in seen_codes:
                    if record.code not in duplicate_codes:
                        duplicate_codes.append(record.code)
                else:
                    seen_codes.add(record.code)

        except (OSError, UnicodeError, ValueError) as exc:
            raise CommandError(
                f"Source validation failed: {exc}"
            ) from exc

        if total_records == 0:
            raise CommandError("The source file contains no records.")

        if duplicate_codes:
            examples = ", ".join(duplicate_codes[:10])
            raise CommandError(
                "Duplicate codes were found in the source. "
                f"Examples: {examples}"
            )

        self.stdout.write(f"Source file: {source.name}")
        self.stdout.write(f"Records parsed: {total_records}")
        self.stdout.write(f"Unique codes: {len(seen_codes)}")
        self.stdout.write(self.style.SUCCESS("Validation result: PASS"))

        if not apply_changes:
            self.stdout.write(
                "Mode: validation only; database unchanged. "
                "Pass --apply to import."
            )
            return

        if not connection.features.supports_update_conflicts:
            raise CommandError(
                "This database backend does not support the upsert "
                "operation required for safe repeatable imports."
            )

        created_count = 0
        refreshed_count = 0
        imported_count = 0
        batch = []
        imported_codes = set()

        def flush_batch():
            nonlocal created_count, refreshed_count

            if not batch:
                return

            codes = [item.code for item in batch]

            existing_codes = set(
                ICDCode.objects.filter(
                    code__in=codes
                ).values_list("code", flat=True)
            )

            # Insert new rows and refresh descriptions for existing codes.
            ICDCode.objects.bulk_create(
                batch,
                batch_size=batch_size,
                update_conflicts=True,
                update_fields=["description"],
                unique_fields=["code"],
            )

            created_count += len(codes) - len(existing_codes)
            refreshed_count += len(existing_codes)
            batch.clear()

        # Pass 2: write atomically. If parsing or database operations fail,
        # Django rolls back the entire import rather than leaving partial data.
        try:
            with transaction.atomic():
                for record in iter_icd10_code_file(source):
                    if record.code in imported_codes:
                        raise CommandError(
                            "Duplicate code encountered during import; "
                            "the transaction was rolled back."
                        )

                    imported_codes.add(record.code)
                    batch.append(
                        ICDCode(
                            code=record.code,
                            description=record.description,
                        )
                    )
                    imported_count += 1

                    if len(batch) >= batch_size:
                        flush_batch()

                flush_batch()

                if imported_count != total_records:
                    raise CommandError(
                        "The source changed between validation and import. "
                        "The transaction was rolled back."
                    )

        except (OSError, UnicodeError, ValueError) as exc:
            raise CommandError(
                f"Import failed and the transaction was rolled back: {exc}"
            ) from exc

        self.stdout.write(
            self.style.SUCCESS("Import completed successfully.")
        )
        self.stdout.write(f"Records processed: {imported_count}")
        self.stdout.write(f"New codes inserted: {created_count}")
        self.stdout.write(
            f"Existing code rows refreshed: {refreshed_count}"
        )
        self.stdout.write(
            f"Total codes in database: {ICDCode.objects.count()}"
        )