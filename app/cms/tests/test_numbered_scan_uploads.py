"""Upload regressions for scan filenames without timestamps."""

from datetime import datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.messages import get_messages
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
                media = Media.objects.get(media_location=str(Path("uploads") / "pending" / filename))
                self.assertIsNone(media.scanning_id)

    def test_compact_timestamp_scans_enter_pending_with_timestamp_lookup(self):
        from cms.scanning_utils import NAIROBI_TZ

        self.client.force_login(self.user)
        filenames = [
            "2609211113551.png", "2609211113553.png",
            "2609211113551234567890.PNG",
        ]
        uploads = [SimpleUploadedFile(name, b"scan-data", content_type="image/png")
                   for name in filenames]
        with patch("cms.scanning_utils.auto_complete_scans"), patch(
            "cms.scanning_utils.find_scan_for_timestamp", return_value=None
        ) as lookup:
            response = self.client.post(self.url, {"files": uploads})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(lookup.call_count, len(filenames))
        for args in lookup.call_args_list:
            self.assertEqual(args.args, (datetime(2026, 9, 21, 11, 13, 55, tzinfo=NAIROBI_TZ),))
        for filename in filenames:
            with self.subTest(filename=filename):
                self.assertEqual((self.uploads_root / "pending" / filename).read_bytes(), b"scan-data")
                self.assertTrue(Media.objects.filter(file_name=filename).exists())

    def test_invalid_compact_timestamp_scans_are_rejected(self):
        self.client.force_login(self.user)
        filenames = [
            "260921111355.png", "260921111355x.png",
            "260921111355-1.png", "2609211113551_extra.png",
            "2613211113551.png", "2602301113551.png", "2609212513551.png",
        ]
        for filename in filenames:
            with self.subTest(filename=filename):
                upload = SimpleUploadedFile(filename, b"data", content_type="image/png")
                response = self.client.post(self.url, {"files": upload})
                self.assertEqual(response.status_code, 302)
                self.assertTrue((self.uploads_root / "rejected" / filename).exists())
        self.assertFalse(Media.objects.exists())

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

    def test_duplicate_is_skipped_in_each_upload_folder(self):
        self.client.force_login(self.user)
        for index, folder in enumerate(("pending", "ocr", "incoming", "failed", "rejected", "manual_qc")):
            with self.subTest(folder=folder):
                filename = f"9LT {index}123.png"
                existing = self.uploads_root / folder / filename
                existing.parent.mkdir(parents=True, exist_ok=True)
                existing.write_bytes(b"original")
                media = None
                if folder in ("pending", "ocr"):
                    media = Media.objects.create(
                        media_location=f"uploads/{folder}/{filename}",
                        ocr_data={"original": True},
                    )
                count = Media.objects.count()
                upload = SimpleUploadedFile(filename, b"replacement", content_type="image/png")
                response = self.client.post(self.url, {"files": upload}, follow=True)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(existing.read_bytes(), b"original")
                self.assertEqual(Media.objects.count(), count)
                self.assertEqual(
                    [str(message) for message in get_messages(response.wsgi_request)],
                    [f"Already uploaded {filename} into uploads/{folder} folder (1 of 1)"],
                )
                if media:
                    media.refresh_from_db()
                    self.assertEqual(media.ocr_data, {"original": True})

    def test_mixed_batch_skips_duplicate_and_uploads_new_file(self):
        self.client.force_login(self.user)
        old_name, new_name = "9LT 123.png", "10LT 123.png"
        Media.objects.create(media_location=f"uploads/ocr/{old_name}")
        uploads = [SimpleUploadedFile(name, b"new", content_type="image/png")
                   for name in (old_name, new_name, new_name)]
        response = self.client.post(self.url, {"files": uploads})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Media.objects.count(), 2)
        self.assertFalse((self.uploads_root / "pending" / old_name).exists())
        self.assertTrue((self.uploads_root / "pending" / new_name).exists())
        self.assertEqual(
            [str(message) for message in get_messages(response.wsgi_request)],
            [f"Already uploaded {old_name} into uploads/ocr folder (1 of 3)",
             f"Uploaded {new_name} (2 of 3)",
             f"Already uploaded {new_name} into uploads/pending folder (3 of 3)"],
        )

    def test_batch_indexes_files_once_and_stages_outside_incoming(self):
        from cms.upload_processing import process_file

        self.client.force_login(self.user)
        uploads = [SimpleUploadedFile(f"{i}LT 123.png", b"scan", content_type="image/png")
                   for i in (1, 2, 3)]
        sources = []

        def process_staged(path):
            self.assertNotIn(self.uploads_root, path.parents)
            sources.append(path)
            return process_file(path)

        original_rglob = Path.rglob
        traversals = []

        def tracked_rglob(path, pattern):
            traversals.append(path)
            return original_rglob(path, pattern)

        with patch("cms.views.process_file", side_effect=process_staged):
            with patch.object(Path, "rglob", tracked_rglob):
                response = self.client.post(self.url, {"files": uploads})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(traversals, [self.uploads_root])
        self.assertEqual(len(sources), 3)
        self.assertTrue(all(not path.parent.exists() for path in sources))

    def test_upload_lock_serializes_workers_and_releases_after_error(self):
        from concurrent.futures import ThreadPoolExecutor
        from threading import Event
        from cms.upload_processing import scan_upload_lock

        started, entered = Event(), Event()

        def worker():
            started.set()
            with scan_upload_lock():
                entered.set()

        with ThreadPoolExecutor(max_workers=1) as executor:
            with self.assertRaisesRegex(ValueError, "test failure"):
                with scan_upload_lock():
                    future = executor.submit(worker)
                    self.assertTrue(started.wait(5))
                    self.assertFalse(entered.wait(0.1))
                    raise ValueError("test failure")
            future.result(timeout=5)
        self.assertTrue(entered.is_set())

    def test_media_without_location_still_blocks_upload(self):
        self.client.force_login(self.user)
        filename = "9LT 123.png"
        Media.objects.create(file_name=filename, media_location="")
        upload = SimpleUploadedFile(filename, b"new", content_type="image/png")
        response = self.client.post(self.url, {"files": upload}, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Media.objects.count(), 1)
        self.assertFalse((self.uploads_root / "pending" / filename).exists())
        self.assertEqual(
            [str(message) for message in get_messages(response.wsgi_request)],
            [f"Already uploaded {filename} (folder not recorded) (1 of 1)"],
        )

    def test_watcher_preserves_existing_files_and_media(self):
        from types import SimpleNamespace
        from scripts.watch_uploads import UploadHandler

        for index, folder in enumerate(("pending", "ocr", "failed", "rejected", "manual_qc")):
            with self.subTest(folder=folder):
                filename = f"{index}LT 456.png"
                existing = self.uploads_root / folder / filename
                existing.parent.mkdir(parents=True, exist_ok=True)
                existing.write_bytes(b"original")
                media = Media.objects.create(
                    media_location=f"uploads/{folder}/{filename}",
                    ocr_data={"preserved": True},
                    ocr_status=Media.OCRStatus.COMPLETED,
                )
                incoming = self.uploads_root / "incoming" / filename
                incoming.parent.mkdir(parents=True, exist_ok=True)
                incoming.write_bytes(b"duplicate")
                count = Media.objects.count()
                with self.assertLogs("scripts.watch_uploads", level="INFO"):
                    UploadHandler().on_created(SimpleNamespace(is_directory=False, src_path=str(incoming)))
                self.assertEqual(existing.read_bytes(), b"original")
                self.assertEqual(incoming.read_bytes(), b"duplicate")
                self.assertEqual(Media.objects.count(), count)
                media.refresh_from_db()
                self.assertEqual(media.ocr_data, {"preserved": True})
                self.assertEqual(media.ocr_status, Media.OCRStatus.COMPLETED)

    def test_watcher_accepts_new_source_and_ignores_repeat_event(self):
        from types import SimpleNamespace
        from scripts.watch_uploads import UploadHandler

        filename = "1LT 456.png"
        incoming = self.uploads_root / "incoming" / filename
        incoming.parent.mkdir(parents=True, exist_ok=True)
        incoming.write_bytes(b"new scan")
        event = SimpleNamespace(is_directory=False, src_path=str(incoming))
        handler = UploadHandler()
        handler.on_created(event)
        handler.on_created(event)
        self.assertFalse(incoming.exists())
        self.assertEqual((self.uploads_root / "pending" / filename).read_bytes(), b"new scan")
        self.assertEqual(Media.objects.count(), 1)

    def test_watcher_detects_file_without_media_and_media_without_file(self):
        from types import SimpleNamespace
        from scripts.watch_uploads import UploadHandler

        for index, record_only in enumerate((True, False)):
            with self.subTest(record_only=record_only):
                filename = f"{index}LT 789.png"
                if record_only:
                    Media.objects.create(file_name=filename, media_location="")
                else:
                    existing = self.uploads_root / "ocr" / filename
                    existing.parent.mkdir(parents=True, exist_ok=True)
                    existing.write_bytes(b"original")
                incoming = self.uploads_root / "incoming" / filename
                incoming.parent.mkdir(parents=True, exist_ok=True)
                incoming.write_bytes(b"duplicate")
                count = Media.objects.count()
                with patch("scripts.watch_uploads.process_file") as process:
                    UploadHandler().on_created(SimpleNamespace(is_directory=False, src_path=str(incoming)))
                process.assert_not_called()
                self.assertTrue(incoming.exists())
                self.assertEqual(Media.objects.count(), count)
