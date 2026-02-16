from django.core.management.base import BaseCommand

from cms.tasks import classify_pending_specimen_pages


class Command(BaseCommand):
    help = "Classify specimen list pages awaiting OCR routing."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Maximum number of pages to classify in this run.",
        )
        parser.add_argument(
            "--ids",
            nargs="+",
            type=int,
            default=None,
            help="Optional list of SpecimenListPage IDs to classify.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Reclassify pages even if they already have a classification status.",
        )

    def handle(self, *args, **options):
        limit = options.get("limit")
        ids = options.get("ids")
        force = options.get("force")

        summary = classify_pending_specimen_pages(limit=limit, ids=ids, force=force)

        for error in summary.errors:
            self.stdout.write(self.style.WARNING(error))

        self.stdout.write(
            self.style.SUCCESS(
                f"Classified {summary.successes} pages with {summary.failures} failures (total {summary.total})."
            )
        )
