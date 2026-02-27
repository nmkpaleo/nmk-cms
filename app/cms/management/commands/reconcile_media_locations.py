from __future__ import annotations

from typing import Iterable

from crum import set_current_user
from django.contrib.auth import get_user_model
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError

from cms.models import Media


class Command(BaseCommand):
    help = (
        "Reconcile legacy Media.media_location paths when approved page-image files exist "
        "at /pages/approved/."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--limit",
            type=int,
            help="Process at most this many candidate media rows.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report updates without writing database changes.",
        )
        parser.add_argument(
            "--actor-username",
            type=str,
            help="Username used as the current/history user for persisted updates.",
        )

    def handle(self, *args, **options):
        limit: int | None = options.get("limit")
        dry_run: bool = options.get("dry_run", False)
        actor_username: str | None = options.get("actor_username")

        actor = self._resolve_actor(actor_username)
        if not dry_run and actor is None:
            raise CommandError("--actor-username is required when not using --dry-run.")

        candidates = self._candidate_queryset(limit)

        processed = 0
        updated = 0
        skipped_missing = 0
        skipped_non_page = 0

        for media in candidates:
            processed += 1
            current_name = media.media_location.name
            target_name = current_name.replace("/pages/", "/pages/approved/", 1)
            if target_name == current_name:
                skipped_non_page += 1
                continue
            if not default_storage.exists(target_name):
                skipped_missing += 1
                continue

            if dry_run:
                updated += 1
                continue

            media.media_location.name = target_name
            media._history_user = actor
            set_current_user(actor)
            try:
                media.save(update_fields=["media_location", "file_name", "format"])
            finally:
                set_current_user(None)
            updated += 1

        mode_prefix = "Dry run — " if dry_run else ""
        summary = (
            f"{mode_prefix}Processed {processed} media rows: {updated} updated, "
            f"{skipped_missing} skipped (approved file missing), "
            f"{skipped_non_page} skipped (already approved or non-page path)."
        )
        self.stdout.write(self.style.SUCCESS(summary))

    def _candidate_queryset(self, limit: int | None) -> Iterable[Media]:
        queryset = (
            Media.objects.filter(media_location__contains="/pages/")
            .exclude(media_location__contains="/pages/approved/")
            .order_by("pk")
        )
        if limit is not None:
            queryset = queryset[:limit]
        return queryset.iterator()

    def _resolve_actor(self, actor_username: str | None):
        if not actor_username:
            return None
        user_model = get_user_model()
        actor = user_model.objects.filter(username=actor_username).first()
        if actor is None:
            raise CommandError(f"Actor user '{actor_username}' does not exist.")
        return actor
