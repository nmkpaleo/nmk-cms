from django.conf import settings
from django.core.management.base import BaseCommand

from cms.tasks import (
    run_specimen_list_ocr_queue,
    run_specimen_list_row_extraction_queue,
)


class Command(BaseCommand):
    help = "Run raw OCR and row extraction queues for specimen list pages."

    def add_arguments(self, parser):
        parser.add_argument(
            "--stage",
            choices=["raw", "rows", "both"],
            default="both",
            help="Which stage to run: raw OCR, row extraction, or both.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Maximum number of pages to process per stage in this run.",
        )
        parser.add_argument(
            "--ids",
            nargs="+",
            type=int,
            default=None,
            help="Optional list of SpecimenListPage IDs to process.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Re-run OCR/extraction even if results already exist.",
        )

    def handle(self, *args, **options):
        stage = options.get("stage")
        limit = options.get("limit")
        ids = options.get("ids")
        force = options.get("force")

        raw_limit = limit or getattr(settings, "SPECIMEN_LIST_OCR_BATCH_SIZE", None)
        row_limit = limit or getattr(settings, "SPECIMEN_LIST_ROW_EXTRACTION_BATCH_SIZE", None)

        if stage in {"raw", "both"}:
            summary = run_specimen_list_ocr_queue(limit=raw_limit, ids=ids, force=force)
            for error in summary.errors:
                self.stdout.write(self.style.WARNING(error))
            self.stdout.write(
                self.style.SUCCESS(
                    f"OCR: {summary.successes} succeeded, {summary.failures} failed (total {summary.total})."
                )
            )

        if stage in {"rows", "both"}:
            summary = run_specimen_list_row_extraction_queue(limit=row_limit, ids=ids, force=force)
            for error in summary.errors:
                self.stdout.write(self.style.WARNING(error))
            self.stdout.write(
                self.style.SUCCESS(
                    f"Rows: {summary.successes} succeeded, {summary.failures} failed (total {summary.total})."
                )
            )
