from __future__ import annotations

import os

import pytest
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from cms.models import SpecimenListPage, SpecimenListPDF

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

pytestmark = pytest.mark.django_db


class ReviewWorkflowFeatureFlagTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="reviewer", email="reviewer@example.com", password="pass"
        )

        self.pdf = SpecimenListPDF.objects.create(
            source_label="Specimen List",
            original_filename="sample.pdf",
            stored_file="uploads/specimen_lists/original/sample.pdf",
        )
        self.page = SpecimenListPage.objects.create(
            pdf=self.pdf,
            page_number=1,
            page_type=SpecimenListPage.PageType.SPECIMEN_LIST_DETAILS,
        )

    @override_settings(FEATURE_REVIEW_UI_ENABLED=False)
    def test_review_queue_is_hidden_when_feature_flag_disabled(self):
        self.client.login(username="reviewer", password="pass")

        response = self.client.get(reverse("specimen_list_queue"))

        self.assertEqual(response.status_code, 404)

    @override_settings(FEATURE_REVIEW_UI_ENABLED=True)
    def test_back_to_queue_button_is_visible_in_edit_mode(self):
        self.client.login(username="reviewer", password="pass")

        response = self.client.get(reverse("specimen_list_page_review", args=[self.page.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Back to queue")
        self.assertContains(response, reverse("specimen_list_queue"))
