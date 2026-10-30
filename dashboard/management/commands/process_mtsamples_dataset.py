"""Process the local MTSamples queue through the offline clinical agent."""
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from dashboard.extraction.dataset import ANNOTATION_QUEUE_PATH
from dashboard.extraction.dataset_batch import (
    DEFAULT_BATCH_OUTPUT_DIR,
    DatasetBatchError,
    run_dataset_batch,
)
from dashboard.models import ICDCode


class Command(BaseCommand):
    help = (
        "Run the local clinical extraction, ICD-10 retrieval and verification "
        "workflow over a prepared MTSamples annotation queue."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--input",
            type=Path,
            default=ANNOTATION_QUEUE_PATH,
            help="Path to the locally generated annotation_queue_100 JSONL.",
        )
        parser.add_argument(
            "--output-dir",
            type=Path,
            default=DEFAULT_BATCH_OUTPUT_DIR,
            help="Output directory inside the ignored .dataset_working directory.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Optional positive maximum number of notes to process.",
        )
        parser.add_argument(
            "--resume",
            action="store_true",
            help="Continue from the atomic results.jsonl checkpoint.",
        )
        parser.add_argument(
            "--overwrite",
            action="store_true",
            help="Replace existing predictions and operations for this batch.",
        )

    def handle(self, *args, **options):
        if options["resume"] and options["overwrite"]:
            raise CommandError("--resume and --overwrite cannot be used together.")

        if ICDCode.objects.count() == 0:
            raise CommandError(
                "The ICD-10-CM reference table is empty. Import the supplied "
                "reference first with: python manage.py import_icd10 "
                "--source data\\reference\\icd10cm-codes-2027.txt --apply"
            )

        try:
            result = run_dataset_batch(
                input_path=options["input"],
                output_dir=options["output_dir"],
                limit=options["limit"],
                resume=options["resume"],
                overwrite=options["overwrite"],
            )
        except DatasetBatchError as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(json.dumps(result, indent=2, sort_keys=True))
        self.stdout.write(
            self.style.SUCCESS(
                "Offline dataset processing completed. No patient records were created."
            )
        )
