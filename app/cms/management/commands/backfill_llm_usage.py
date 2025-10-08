from __future__ import annotations

from django.core.management.base import BaseCommand

from cms.models import LLMUsageRecord, Media


class Command(BaseCommand):
    help = "Backfill LLM usage records from stored OCR payloads."

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            help="Process at most this many usage payloads.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change without saving records.",
        )

    def handle(self, *args, **options):
        limit: int | None = options.get("limit")
        dry_run: bool = options.get("dry_run", False)

        queryset = Media.objects.filter(ocr_data__isnull=False).order_by("pk")

        processed = 0
        created = 0
        updated = 0
        skipped = 0

        for media in queryset.iterator():
            ocr_data = media.ocr_data or {}
            if not isinstance(ocr_data, dict):
                skipped += 1
                continue

            usage_payload = ocr_data.get("usage")
            if not isinstance(usage_payload, dict):
                skipped += 1
                continue

            if limit is not None and processed >= limit:
                break

            processed += 1
            defaults = LLMUsageRecord.defaults_from_payload(usage_payload)

            if dry_run:
                if LLMUsageRecord.objects.filter(media=media).exists():
                    updated += 1
                else:
                    created += 1
                continue

            _, created_flag = LLMUsageRecord.objects.update_or_create(
                media=media,
                defaults=defaults,
            )
            if created_flag:
                created += 1
            else:
                updated += 1

        summary = (
            f"Processed {processed} usage payloads: "
            f"{created} created, {updated} updated, {skipped} skipped."
        )
        if dry_run:
            summary = f"Dry run — {summary} No changes saved."

        self.stdout.write(self.style.SUCCESS(summary))
