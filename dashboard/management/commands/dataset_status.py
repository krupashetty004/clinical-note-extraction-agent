"""Report local prepared-dataset and annotation-queue readiness."""

import json

from django.core.management import BaseCommand

from dashboard.extraction.dataset import (
    annotation_readiness,
    build_evaluation_gold_cases,
    load_annotation_queue,
    load_prepared_records,
)


class Command(BaseCommand):
    help = "Validate the prepared local dataset and report annotation readiness."

    def handle(self, *args, **options):
        prepared = load_prepared_records()
        queue = load_annotation_queue()
        _, evaluation = build_evaluation_gold_cases(queue)
        payload = {
            "prepared_records": {
                "path": str(prepared.path),
                "records_loaded": len(prepared.records),
                "validation_errors": len(prepared.errors),
                "specialties": len(
                    {record.specialty for record in prepared.records if record.specialty}
                ),
            },
            "annotation_queue": annotation_readiness(queue),
            "evaluation_input": evaluation,
        }
        self.stdout.write(json.dumps(payload, indent=2, sort_keys=True))
        if prepared.errors or queue.errors:
            raise SystemExit(1)
