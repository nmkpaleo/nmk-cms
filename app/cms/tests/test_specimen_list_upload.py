from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TransactionTestCase, override_settings
from django.urls import reverse

from cms.models import SpecimenListPDF




class SpecimenListUploadViewTests(TransactionTestCase):
    def setUp(self) -> None:
        self.user = get_user_model().objects.create_user(
            username="specimen-uploader",
            password="pass",
            is_staff=True,
        )
        permission = Permission.objects.get(codename="add_specimenlistpdf")
        self.user.user_permissions.add(permission)

    @override_settings(SPECIMEN_LIST_DPI=72)
    def test_upload_creates_pdf_records_and_queues_processing(self):
        with TemporaryDirectory() as temp_dir:
            with override_settings(MEDIA_ROOT=temp_dir):
                pdf_one = SimpleUploadedFile(
                    "specimen-1.pdf",
                    b"%PDF-1.4\n%%EOF",
                    content_type="application/pdf",
                )
                pdf_two = SimpleUploadedFile(
                    "specimen-2.pdf",
                    b"%PDF-1.4\n%%EOF",
                    content_type="application/pdf",
                )

                self.client.force_login(self.user)
                with patch("cms.views.queue_specimen_list_processing") as queued:
                    response = self.client.post(
                        reverse("specimen_list_upload"),
                        {
                            "source_label": "  Batch Alpha  ",
                            "files": [pdf_one, pdf_two],
                        },
                    )

                self.assertEqual(response.status_code, 302)
                self.assertEqual(SpecimenListPDF.objects.count(), 2)
                stored = SpecimenListPDF.objects.order_by("original_filename")
                self.assertEqual(stored[0].source_label, "Batch Alpha")
                self.assertTrue(stored[0].stored_file.name)
                self.assertEqual(queued.call_count, 2)
                for call in queued.call_args_list:
                    self.assertIsInstance(call.args[0], int)

    def test_upload_requires_files(self):
        with TemporaryDirectory() as temp_dir:
            with override_settings(MEDIA_ROOT=temp_dir):
                self.client.force_login(self.user)
                response = self.client.post(
                    reverse("specimen_list_upload"),
                    {
                        "source_label": "Batch",
                    },
                )

                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "No file was submitted")
