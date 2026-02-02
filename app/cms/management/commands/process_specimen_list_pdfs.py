from django.core.management.base import BaseCommand

from cms.models import SpecimenListPDF
from cms.upload_processing import process_specimen_list_pdf


class Command(BaseCommand):
    help = "Process queued specimen list PDFs and create page records."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            default=None,
            help="Maximum number of PDFs to process in this run.",
        )
        parser.add_argument(
            "--ids",
            nargs="+",
            type=int,
            default=None,
            help="Optional list of SpecimenListPDF IDs to process.",
        )

    def handle(self, *args, **options):
        limit = options.get("limit")
        ids = options.get("ids")

        queryset = SpecimenListPDF.objects.filter(
            status__in=[SpecimenListPDF.Status.UPLOADED, SpecimenListPDF.Status.ERROR]
        ).order_by("uploaded_at")

        if ids:
            queryset = queryset.filter(id__in=ids)

        if limit:
            queryset = queryset[:limit]

        total = 0
        for pdf in queryset:
            total += 1
            self.stdout.write(
                self.style.NOTICE(
                    f"Processing specimen list PDF {pdf.id} ({pdf.original_filename})"
                )
            )
            process_specimen_list_pdf(pdf.id)

        self.stdout.write(self.style.SUCCESS(f"Processed {total} specimen list PDFs."))
