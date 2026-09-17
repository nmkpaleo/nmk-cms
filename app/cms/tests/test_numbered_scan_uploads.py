"""Upload regressions for scan filenames without timestamps."""

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from cms.models import Media


class NumberedScanUploadTests(TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        override = override_settings(MEDIA_ROOT=root)
        override.enable()
        self.addCleanup(override.disable)
        self.uploads_root = root / "uploads"
        for name in ("PENDING", "REJECTED"):
            patcher = patch(f"cms.upload_processing.{name}", self.uploads_root / name.lower())
            patcher.start()
            self.addCleanup(patcher.stop)
        self.user = get_user_model().objects.create_user(username="scan-uploader", is_staff=True)
        patcher = patch("cms.models.get_current_user", return_value=self.user)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.url = reverse("admin-upload-scan")

    def test_numbered_scans_enter_pending_without_scanning_lookup(self):
        self.client.force_login(self.user)
        filenames = [
            "4LT 1082726110849.png", "5LT 1082726110849.png",
            "6LT 1082726110849.png", "12ab 001.PNG",
        ]
        uploads = [SimpleUploadedFile(name, b"scan-data", content_type="image/png")
                   for name in filenames]
        with patch("cms.scanning_utils.find_scan_for_timestamp") as lookup:
            response = self.client.post(self.url, {"files": uploads})
        self.assertEqual(response.status_code, 302)
        lookup.assert_not_called()
        for filename in filenames:
            with self.subTest(filename=filename):
                pending = self.uploads_root / "pending" / filename
                self.assertEqual(pending.read_bytes(), b"scan-data")
                media = Media.objects.get(media_location=f"uploads/pending/{filename}")
                self.assertIsNone(media.scanning_id)

    def test_malformed_numbered_scan_names_are_rejected(self):
        self.client.force_login(self.user)
        filenames = ["LT 123.png", "4L 123.png", "4LTT 123.png",
                     "4LT123.png", "4LT  123.png", "4LT abc.png",
                     "4LT 123.jpg", "4LT 123_extra.png"]
        for filename in filenames:
            with self.subTest(filename=filename):
                upload = SimpleUploadedFile(filename, b"data", content_type="image/png")
                response = self.client.post(self.url, {"files": upload})
                self.assertEqual(response.status_code, 302)
                self.assertTrue((self.uploads_root / "rejected" / filename).exists())
        self.assertFalse(Media.objects.exists())

