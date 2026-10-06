from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from cms.models import AccessionReference, Identification, Reference


REFERENCE_FIELDS = (
    "title", "first_author", "year", "journal", "volume", "issue",
    "pages", "doi", "citation",
)


def reference_key(reference: Reference) -> tuple[str | None, ...]:
    values = []
    for name in REFERENCE_FIELDS:
        value = getattr(reference, name)
        values.append(" ".join(value.split()) if isinstance(value, str) else value)
    return tuple(values)


class Command(BaseCommand):
    help = "Preview or apply global exact-value Reference deduplication."

    def add_arguments(self, parser) -> None:  # pragma: no cover - argparse plumbing
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Repoint relations and delete duplicate References. Omit for a dry run.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        groups: dict[tuple[str | None, ...], list[Reference]] = {}
        for reference in Reference.objects.order_by("pk"):
            groups.setdefault(reference_key(reference), []).append(reference)

        duplicate_count = 0
        relation_count = 0
        for references in groups.values():
            if len(references) < 2:
                continue
            canonical, duplicates = references[0], references[1:]
            duplicate_count += len(duplicates)
            for duplicate in duplicates:
                accession_links = list(AccessionReference.objects.filter(reference=duplicate))
                relation_count += len(accession_links)
                if not options["apply"]:
                    continue
                for link in accession_links:
                    collision = AccessionReference.objects.filter(
                        accession=link.accession,
                        reference=canonical,
                    ).exclude(pk=link.pk).first()
                    if collision:
                        link.delete()
                    else:
                        AccessionReference.objects.filter(pk=link.pk).update(reference=canonical)
                Identification.objects.filter(reference=duplicate).update(reference=canonical)
                Reference.objects.filter(pk=duplicate.pk).delete()

        mode = "Applied" if options["apply"] else "Dry run"
        self.stdout.write(
            self.style.SUCCESS(
                f"{mode}: {duplicate_count} duplicate Reference(s), "
                f"{relation_count} accession-reference relation(s)."
            )
        )
