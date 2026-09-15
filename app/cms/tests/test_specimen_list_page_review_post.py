import tempfile
import uuid
from unittest import mock

from crum import set_current_user
from django.contrib.auth import get_user_model
from django.contrib.messages import get_messages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from cms.models import Collection, Locality, Media, SpecimenListPage, SpecimenListPDF


class SpecimenListPageReviewPostTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username=f"reviewer-{uuid.uuid4().hex}",
            email="reviewer@example.com",
            password="pass",
        )
        self.client = Client()
        self.client.force_login(self.user)

    def _build_pdf(self) -> SpecimenListPDF:
        pdf_file = SimpleUploadedFile("specimen.pdf", b"%PDF-1.4", content_type="application/pdf")
        return SpecimenListPDF.objects.create(
            source_label="Specimen List",
            original_filename="specimen.pdf",
            stored_file=pdf_file,
        )

    def _build_page(self, media_root: str) -> SpecimenListPage:
        set_current_user(self.user)
        try:
            Collection.objects.get_or_create(abbreviation="KNM", defaults={"description": "Kenya National Museums"})
            Locality.objects.get_or_create(abbreviation="ER", defaults={"name": "East Rudolf"})
        finally:
            set_current_user(None)

        page = SpecimenListPage.objects.create(
            pdf=self._build_pdf(),
            page_number=1,
            page_type=SpecimenListPage.PageType.SPECIMEN_LIST_DETAILS,
        )
        image_file = SimpleUploadedFile("page.png", b"fake-image-data", content_type="image/png")
        with override_settings(MEDIA_ROOT=media_root):
            page.image_file.save("page.png", image_file, save=True)
        return page

    def test_approve_endpoint_moves_page_image_and_syncs_media(self):
        with tempfile.TemporaryDirectory() as media_root:
            page = self._build_page(media_root)

            set_current_user(self.user)
            try:
                media = Media.objects.create(
                    file_name="page.png",
                    type="document",
                    format="png",
                    media_location=page.image_file,
                )
            finally:
                set_current_user(None)

            with mock.patch("cms.views.SpecimenListPageReviewView._build_row_formset") as formset_mock, mock.patch(
                "cms.views.SpecimenListPageReviewView._save_row_formset"
            ), override_settings(MEDIA_ROOT=media_root):
                formset_mock.return_value.is_valid.return_value = True
                response = self.client.post(
                    reverse("specimen_list_page_review", args=[page.pk]),
                    data={"action": "approve"},
                )

            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.url, reverse("specimen_list_queue"))

            page.refresh_from_db()
            media.refresh_from_db()
            self.assertIn("/pages/approved/", page.image_file.name)
            self.assertEqual(media.media_location.name, page.image_file.name)

    def test_approve_endpoint_denies_users_without_approve_permission(self):
        with tempfile.TemporaryDirectory() as media_root:
            page = self._build_page(media_root)

            with mock.patch("cms.views.SpecimenListPageReviewView._build_row_formset") as formset_mock, mock.patch(
                "cms.views.SpecimenListPageReviewView._save_row_formset"
            ), mock.patch("cms.views.can_approve_specimen_list_page", return_value=False), override_settings(MEDIA_ROOT=media_root):
                formset_mock.return_value.is_valid.return_value = True
                response = self.client.post(
                    reverse("specimen_list_page_review", args=[page.pk]),
                    data={"action": "approve"},
                )

            self.assertEqual(response.status_code, 403)

    def test_approve_endpoint_shows_error_and_redirects_when_approve_service_fails(self):
        with tempfile.TemporaryDirectory() as media_root:
            page = self._build_page(media_root)

            with mock.patch("cms.views.SpecimenListPageReviewView._build_row_formset") as formset_mock, mock.patch(
                "cms.views.SpecimenListPageReviewView._save_row_formset"
            ), mock.patch("cms.views.approve_page", side_effect=RuntimeError("sync failed")), override_settings(
                MEDIA_ROOT=media_root
            ):
                formset_mock.return_value.is_valid.return_value = True
                response = self.client.post(
                    reverse("specimen_list_page_review", args=[page.pk]),
                    data={"action": "approve"},
                    follow=True,
                )

            self.assertEqual(response.status_code, 200)
            page.refresh_from_db()
            self.assertEqual(page.review_status, SpecimenListPage.ReviewStatus.PENDING)
            messages = [str(message) for message in get_messages(response.wsgi_request)]
            self.assertTrue(
                any("Page approval could not be completed because of a system error" in message for message in messages)
            )
