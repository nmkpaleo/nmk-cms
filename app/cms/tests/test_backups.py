import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings

from cms import backups
from cms.models import CMSBackupJob


class BackupServiceTests(TestCase):
    def setUp(self):
        self.backup_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.backup_dir.cleanup)

    def test_backup_sets_are_unique_and_published_as_complete_pairs(self):
        def write_artifact(path):
            path.write_bytes(b"backup")

        with override_settings(CMS_BACKUP_ROOT=self.backup_dir.name):
            with (
                mock.patch("cms.backups.dump_database", side_effect=write_artifact),
                mock.patch("cms.backups.archive_media", side_effect=write_artifact),
            ):
                first = backups.create_backup_set()
                second = backups.create_backup_set()

            self.assertNotEqual(first.database_path, second.database_path)
            self.assertNotEqual(first.files_path, second.files_path)
            self.assertEqual(len(backups.list_backup_files()), 4)
            self.assertEqual(Path(self.backup_dir.name).stat().st_mode & 0o777, 0o700)

    def test_failed_backup_does_not_publish_partial_files(self):
        def write_artifact(path):
            path.write_bytes(b"partial")

        with override_settings(CMS_BACKUP_ROOT=self.backup_dir.name):
            with (
                mock.patch("cms.backups.dump_database", side_effect=write_artifact),
                mock.patch("cms.backups.archive_media", side_effect=RuntimeError("archive failed")),
            ):
                with self.assertRaisesRegex(RuntimeError, "archive failed"):
                    backups.create_backup_set()

            self.assertEqual(backups.list_backup_files(), [])
            self.assertEqual(list(Path(self.backup_dir.name).glob("paleocms_database_*.sql")), [])

    def test_restore_invokes_mysql_in_binary_mode(self):
        sql_path = Path(self.backup_dir.name) / "restore.sql"
        sql_path.write_text("SELECT 1;")

        with (
            override_settings(
                DATABASES={
                    "default": {
                        "ENGINE": "django.db.backends.mysql",
                        "NAME": "cms",
                        "USER": "cms_user",
                        "HOST": "db",
                        "PORT": "3306",
                    }
                }
            ),
            mock.patch("cms.backups._first_available", return_value="mysql"),
            mock.patch("cms.backups.subprocess.run") as run,
        ):
            backups.restore_database(sql_path)

        self.assertIn("--binary-mode", run.call_args.args[0])

    def test_database_dump_excludes_backup_job_state(self):
        output_path = Path(self.backup_dir.name) / "backup.sql"
        with (
            override_settings(
                DATABASES={
                    "default": {
                        "ENGINE": "django.db.backends.mysql",
                        "NAME": "cms",
                        "USER": "cms_user",
                    }
                }
            ),
            mock.patch("cms.backups._first_available", return_value="mysqldump"),
            mock.patch("cms.backups.subprocess.run") as run,
        ):
            backups.dump_database(output_path)

        self.assertIn("--ignore-table=cms.cms_cmsbackupjob", run.call_args.args[0])

    def test_backup_job_status_and_upload_are_persisted(self):
        upload = SimpleUploadedFile("restore.sql", b"SELECT 1;")
        with override_settings(CMS_BACKUP_ROOT=self.backup_dir.name):
            job = backups.queue_backup_job(
                CMSBackupJob.Operation.RESTORE_DATABASE,
                uploaded_file=upload,
            )
            source_path = Path(job.source_path)
            self.assertEqual(source_path.read_bytes(), b"SELECT 1;")
            self.assertEqual(source_path.stat().st_mode & 0o777, 0o600)

            with mock.patch("cms.backups.restore_database", side_effect=RuntimeError("restore failed")):
                self.assertTrue(backups.process_next_backup_job())

        job.refresh_from_db()
        self.assertEqual(job.status, CMSBackupJob.Status.FAILED)
        self.assertEqual(job.error, "restore failed")
        self.assertFalse(source_path.exists())

    def test_successful_job_persists_result(self):
        job = backups.queue_backup_job(CMSBackupJob.Operation.CREATE)
        backup_set = SimpleNamespace(
            database_path=Path("paleocms_database.sql"),
            files_path=Path("paleocms_files.tar.gz"),
        )

        with mock.patch("cms.backups.create_backup_set", return_value=backup_set):
            self.assertTrue(backups.process_next_backup_job())

        job.refresh_from_db()
        self.assertEqual(job.status, CMSBackupJob.Status.SUCCEEDED)
        self.assertIn("paleocms_database.sql", job.result)
