from __future__ import annotations

from datetime import datetime, timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from cms.models import SpecimenListPage

SPECIMEN_LIST_LOCK_TTL_SECONDS = getattr(
    settings, "SPECIMEN_LIST_LOCK_TTL_SECONDS", 900
)


def lock_is_expired(locked_at: datetime | None) -> bool:
    if not locked_at:
        return True
    expires_at = locked_at + timedelta(seconds=SPECIMEN_LIST_LOCK_TTL_SECONDS)
    return timezone.now() >= expires_at


def acquire_review_lock(
    *,
    page_id: int,
    reviewer,
    allow_override: bool = False,
) -> SpecimenListPage:
    with transaction.atomic():
        page = (
            SpecimenListPage.objects.select_for_update()
            .select_related("pdf", "assigned_reviewer")
            .get(pk=page_id)
        )
        if page.assigned_reviewer and page.assigned_reviewer != reviewer:
            if not allow_override and not lock_is_expired(page.locked_at):
                return page

        now_time = timezone.now()
        page.assigned_reviewer = reviewer
        page.locked_at = now_time
        page.pipeline_status = SpecimenListPage.PipelineStatus.IN_REVIEW
        page.review_status = SpecimenListPage.ReviewStatus.IN_REVIEW
        page.save(
            update_fields=[
                "assigned_reviewer",
                "locked_at",
                "pipeline_status",
                "review_status",
            ]
        )
        return page


def release_review_lock(
    *,
    page_id: int,
    reviewer,
    allow_override: bool = False,
) -> SpecimenListPage:
    with transaction.atomic():
        page = (
            SpecimenListPage.objects.select_for_update()
            .select_related("pdf", "assigned_reviewer")
            .get(pk=page_id)
        )
        if page.assigned_reviewer and page.assigned_reviewer != reviewer:
            if not allow_override and not lock_is_expired(page.locked_at):
                return page

        page.assigned_reviewer = None
        page.locked_at = None
        page.pipeline_status = SpecimenListPage.PipelineStatus.PENDING
        page.review_status = SpecimenListPage.ReviewStatus.PENDING
        page.save(
            update_fields=[
                "assigned_reviewer",
                "locked_at",
                "pipeline_status",
                "review_status",
            ]
        )
        return page
