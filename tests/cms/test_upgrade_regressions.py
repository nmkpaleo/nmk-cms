from __future__ import annotations

import os
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

pytestmark = pytest.mark.django_db

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.test import override_settings
from django.urls import reverse

from cms.models import CMSBackupJob, FieldSlip
from cms.resources import AccessionReferenceResource, AccessionResource, AccessionRowResource


class FieldSlipAutocompleteAuthTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="user", email="user@example.com", password="pass"
        )

    def test_anonymous_requests_are_rejected(self):
        response = self.client.get(reverse("fieldslip-autocomplete"))

        self.assertEqual(response.status_code, 403)

    def test_authenticated_requests_return_matches(self):
        with mock.patch("cms.models.get_current_user", return_value=self.user):
            FieldSlip.objects.create(
                field_number="FS-001",
                verbatim_taxon="Panthera leo",
                verbatim_element="Mandible",
            )

        self.client.login(username=self.user.username, password="pass")
        response = self.client.get(reverse("fieldslip-autocomplete"), {"q": "FS-001"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        texts = [result.get("text") for result in payload.get("results", [])]
        self.assertIn("FS-001", texts)


class FlatFileImportViewTests(TestCase):
    def setUp(self):
        self.staff = get_user_model().objects.create_user(
            username="staff", email="staff@example.com", password="pass", is_staff=True
        )
        self.user = get_user_model().objects.create_user(
            username="user", email="user2@example.com", password="pass"
        )

    def test_non_staff_are_redirected_from_import_view(self):
        self.client.login(username=self.user.username, password="pass")

        response = self.client.get(reverse("admin:flat-file-import"))

        self.assertEqual(response.status_code, 302)

    def test_staff_can_view_import_form(self):
        self.client.login(username=self.staff.username, password="pass")

        response = self.client.get(reverse("admin:flat-file-import"))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Flat File Import", content)
        self.assertIn("import_file", content)


class BackupAdminViewTests(TestCase):
    def setUp(self):
        self.backup_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.backup_dir.cleanup)
        self.superuser = get_user_model().objects.create_superuser(
            username="admin", email="admin@example.com", password="pass"
        )
        self.staff = get_user_model().objects.create_user(
            username="staff-backups", email="staff-backups@example.com", password="pass", is_staff=True
        )

    def test_only_superusers_can_open_backup_page(self):
        self.client.login(username=self.staff.username, password="pass")

        response = self.client.get(reverse("admin:cms-backups"))

        self.assertEqual(response.status_code, 403)

    def test_superuser_can_view_backup_page(self):
        self.client.login(username=self.superuser.username, password="pass")

        with override_settings(CMS_BACKUP_ROOT=self.backup_dir.name):
            response = self.client.get(reverse("admin:cms-backups"))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Back up CMS now", content)
        self.assertIn("Restore database", content)
        self.assertIn("Restore media files", content)
        self.assertIn('id="database_backup_file"', content)
        self.assertIn('id="files_backup_file"', content)
        self.assertIn('id="database_confirm"', content)
        self.assertIn('id="files_confirm"', content)

    def test_create_backup_posts_to_service(self):
        self.client.login(username=self.superuser.username, password="pass")
        with override_settings(CMS_BACKUP_ROOT=self.backup_dir.name):
            with mock.patch("cms.admin.backups.queue_backup_job", return_value=SimpleNamespace(pk=7)) as queue_job:
                response = self.client.post(reverse("admin:cms-backups"), {"action": "create"})

        self.assertEqual(response.status_code, 302)
        queue_job.assert_called_once_with(CMSBackupJob.Operation.CREATE, user=self.superuser)

    def test_restore_database_upload_posts_to_service(self):
        self.client.login(username=self.superuser.username, password="pass")
        upload = SimpleUploadedFile("paleocms_database.sql", b"SELECT 1;")

        with override_settings(CMS_BACKUP_ROOT=self.backup_dir.name):
            with mock.patch("cms.admin.backups.queue_backup_job", return_value=SimpleNamespace(pk=8)) as queue_job:
                response = self.client.post(
                    reverse("admin:cms-backups"),
                    {"action": "restore_database", "backup_file": upload, "confirm": "on"},
                )

        self.assertEqual(response.status_code, 302)
        queue_job.assert_called_once()
        args, kwargs = queue_job.call_args
        self.assertEqual(args, (CMSBackupJob.Operation.RESTORE_DATABASE,))
        self.assertEqual(kwargs["user"].pk, self.superuser.pk)
        self.assertEqual(kwargs["uploaded_file"].name, upload.name)

    def test_form_ids_remain_distinct_after_validation_error(self):
        self.client.force_login(self.superuser)
        upload = SimpleUploadedFile("not-a-dump.txt", b"invalid")

        with override_settings(CMS_BACKUP_ROOT=self.backup_dir.name):
            response = self.client.post(
                reverse("admin:cms-backups"),
                {"action": "restore_database", "backup_file": upload, "confirm": "on"},
            )

        content = response.content.decode()
        self.assertEqual(response.status_code, 200)
        self.assertIn('id="database_backup_file"', content)
        self.assertIn('id="files_backup_file"', content)
        self.assertIn('id="database_confirm"', content)
        self.assertIn('id="files_confirm"', content)

    def test_download_serves_backup_file(self):
        timestamp = "20261021_064037_abc123"
        path = Path(self.backup_dir.name) / f"paleocms_database_{timestamp}.sql"
        path.write_text("SELECT 1;")
        (Path(self.backup_dir.name) / f"paleocms_files_{timestamp}.tar.gz").write_bytes(b"archive")
        (Path(self.backup_dir.name) / f"paleocms_backup_{timestamp}.complete").touch()
        self.client.login(username=self.superuser.username, password="pass")

        with override_settings(CMS_BACKUP_ROOT=self.backup_dir.name):
            response = self.client.get(reverse("admin:cms-backup-download", args=[path.name]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response["Content-Disposition"],
            f'attachment; filename="{path.name}"',
        )


class ImportExportResourceConfigurationTests(TestCase):
    def test_accession_resource_exposes_has_duplicates_as_readonly(self):
        resource = AccessionResource()

        self.assertIn("has_duplicates", resource.fields)
        self.assertTrue(resource.fields["has_duplicates"].readonly)
        self.assertIn("has_duplicates", resource.Meta.export_order)
        self.assertIn("has_duplicates", resource.Meta.readonly_fields)

    def test_accession_row_and_reference_use_expected_identifiers(self):
        row_resource = AccessionRowResource()
        reference_resource = AccessionReferenceResource()

        self.assertEqual(row_resource.Meta.import_id_fields, ("accession", "specimen_suffix"))
        self.assertEqual(reference_resource.Meta.import_id_fields, ("accession", "reference"))
