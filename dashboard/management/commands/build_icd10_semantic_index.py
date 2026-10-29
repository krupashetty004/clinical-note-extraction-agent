"""Build the local semantic index for ICD-10-CM descriptions."""

from django.core.management.base import BaseCommand, CommandError

from dashboard.extraction.icd10_semantic import build_semantic_index


class Command(BaseCommand):
    help = "Build or refresh the local ICD-10-CM semantic index."

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Rebuild the index even when the cache is current.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=128,
            help="Number of descriptions embedded per batch (1-512).",
        )

    def handle(self, *args, **options):
        def report_progress(completed: int, total: int) -> None:
            self.stdout.write(
                f"Embedded {completed:,} of {total:,} descriptions."
            )

        try:
            report = build_semantic_index(
                force=options["force"],
                batch_size=options["batch_size"],
                progress_callback=report_progress,
            )
        except Exception as exc:
            raise CommandError(
                f"Could not build the ICD-10-CM semantic index: {exc}"
            ) from exc

        if report.reused_existing_index:
            self.stdout.write(
                self.style.SUCCESS(
                    "Reused an up-to-date semantic index."
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    "Semantic index built successfully."
                )
            )

        self.stdout.write(f"ICD records: {report.row_count:,}")
        self.stdout.write(f"Cache directory: {report.cache_directory}")