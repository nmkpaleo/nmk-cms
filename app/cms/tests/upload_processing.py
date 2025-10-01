"""Tests for upload processing timestamp handling."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone as django_timezone

from cms import scanning_utils
from cms.models import DrawerRegister, Media, Scanning
from cms.upload_processing import process_file


class UploadProcessingTests(TestCase):
    """Tests for the file watcher processing logic."""

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="intern", password="pass")
        patcher = patch("cms.models.get_current_user", return_value=self.user)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.drawer = DrawerRegister.objects.create(
            code="DRW", description="Drawer", estimated_documents=1
        )
        start = scanning_utils.nairobi_now() - timedelta(minutes=5)
        end = start + timedelta(minutes=10)
        self.scanning = Scanning.objects.create(
            drawer=self.drawer, user=self.user, start_time=start, end_time=end
        )

    def test_scanning_lookup_uses_creation_time(self):
        incoming = Path(settings.MEDIA_ROOT) / "uploads" / "incoming"
        incoming.mkdir(parents=True, exist_ok=True)
        filename = "2025-09-09(1).png"
        src = incoming / filename
        src.write_bytes(b"data")
        created = scanning_utils.to_nairobi(self.scanning.start_time) + timedelta(minutes=1)
        stat_result = SimpleNamespace(
            st_birthtime=created.timestamp(),
            st_mtime=created.timestamp() + 60,
            st_ctime=created.timestamp() + 120,
            st_mode=0,
        )

        def fake_fromtimestamp(timestamp):
            self.assertEqual(timestamp, stat_result.st_birthtime)
            return datetime.fromtimestamp(timestamp, tz=timezone.utc).replace(tzinfo=None)

        original_to_nairobi = scanning_utils.to_nairobi
        call_counter = {"count": 0}

        def wrapped_to_nairobi(dt):
            self.assertFalse(django_timezone.is_naive(dt))
            if call_counter["count"] == 0:
                self.assertEqual(dt.tzinfo, timezone.utc)
            call_counter["count"] += 1
            return original_to_nairobi(dt)

        with patch("cms.upload_processing._fromtimestamp_utc", side_effect=fake_fromtimestamp):
            with patch("cms.scanning_utils.to_nairobi", side_effect=wrapped_to_nairobi):
                original_stat = Path.stat

                def fake_stat(path_self):
                    if path_self == src:
                        return stat_result
                    return original_stat(path_self)

                with patch("pathlib.Path.stat", new=fake_stat):
                    process_file(src)
        media = Media.objects.get(media_location=f"uploads/pending/{filename}")
        self.assertEqual(media.scanning, self.scanning)
        import shutil
        shutil.rmtree(incoming.parent)

    def test_missing_birthtime_aborts_processing(self):
        incoming = Path(settings.MEDIA_ROOT) / "uploads" / "incoming"
        incoming.mkdir(parents=True, exist_ok=True)
        filename = "2025-09-09(2).png"
        src = incoming / filename
        src.write_bytes(b"data")
        stat_result = SimpleNamespace(st_mode=0)

        original_stat = Path.stat

        def fake_stat(path_self):
            if path_self == src:
                return stat_result
            return original_stat(path_self)

        with patch("pathlib.Path.stat", new=fake_stat):
            with self.assertRaises(AttributeError):
                process_file(src)

        self.assertFalse(Media.objects.filter(media_location=f"uploads/pending/{filename}").exists())
        import shutil
        shutil.rmtree(incoming.parent)


__all__ = ["UploadProcessingTests"]
