from __future__ import annotations

from io import StringIO

import pytest
from crum import set_current_user
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management import CommandError, call_command
from django.test import override_settings

from cms.models import Media


pytestmark = pytest.mark.django_db


def _build_reviewer():
    user_model = get_user_model()
    return user_model.objects.create(username="media-reconcile-reviewer")


def test_reconcile_media_locations_dry_run_reports_without_writing(tmp_path):
    reviewer = _build_reviewer()
    with override_settings(MEDIA_ROOT=tmp_path):
        old_name = "uploads/specimen_lists/pages/page_001.png"
        approved_name = "uploads/specimen_lists/pages/approved/page_001.png"
        default_storage.save(old_name, ContentFile(b"old"))
        default_storage.save(approved_name, ContentFile(b"approved"))

        set_current_user(reviewer)
        try:
            media = Media.objects.create(
                file_name="page_001.png",
                type="document",
                format="png",
                media_location=old_name,
            )
        finally:
            set_current_user(None)

        out = StringIO()
        call_command("reconcile_media_locations", "--dry-run", stdout=out)

        media.refresh_from_db()
        assert media.media_location.name == old_name
        assert "Dry run — Processed 1 media rows: 1 updated" in out.getvalue()


def test_reconcile_media_locations_updates_location_and_history_user(tmp_path):
    reviewer = _build_reviewer()
    with override_settings(MEDIA_ROOT=tmp_path):
        old_name = "uploads/specimen_lists/pages/page_002.png"
        approved_name = "uploads/specimen_lists/pages/approved/page_002.png"
        default_storage.save(old_name, ContentFile(b"old"))
        default_storage.save(approved_name, ContentFile(b"approved"))

        set_current_user(reviewer)
        try:
            media = Media.objects.create(
                file_name="page_002.png",
                type="document",
                format="png",
                media_location=old_name,
            )
        finally:
            set_current_user(None)

        out = StringIO()
        call_command(
            "reconcile_media_locations",
            "--actor-username",
            reviewer.username,
            stdout=out,
        )

        media.refresh_from_db()
        assert media.media_location.name == approved_name
        latest_history = media.history.latest()
        assert latest_history.media_location == approved_name
        assert latest_history.history_user == reviewer
        assert "Processed 1 media rows: 1 updated" in out.getvalue()


def test_reconcile_media_locations_requires_actor_for_non_dry_run(tmp_path):
    reviewer = _build_reviewer()
    with override_settings(MEDIA_ROOT=tmp_path):
        old_name = "uploads/specimen_lists/pages/page_003.png"
        approved_name = "uploads/specimen_lists/pages/approved/page_003.png"
        default_storage.save(old_name, ContentFile(b"old"))
        default_storage.save(approved_name, ContentFile(b"approved"))

        set_current_user(reviewer)
        try:
            Media.objects.create(
                file_name="page_003.png",
                type="document",
                format="png",
                media_location=old_name,
            )
        finally:
            set_current_user(None)

        with pytest.raises(CommandError, match="--actor-username is required"):
            call_command("reconcile_media_locations")
