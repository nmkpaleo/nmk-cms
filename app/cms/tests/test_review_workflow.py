from __future__ import annotations

import pytest
from crum import set_current_user
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from cms.models import Collection, Locality, SpecimenListPage, SpecimenListPDF, SpecimenListRowCandidate
from cms.services.review_approval import approve_page

pytestmark = pytest.mark.usefixtures("django_db_setup")


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
        set_current_user(self.user)
        try:
            Collection.objects.get_or_create(
                abbreviation="KNM",
                defaults={"description": "Kenya National Museums"},
            )
            Locality.objects.get_or_create(
                abbreviation="ER",
                defaults={"name": "East Rudolf"},
            )
        finally:
            set_current_user(None)

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

    @override_settings(FEATURE_REVIEW_UI_ENABLED=True)
    def test_queue_filters_still_render_after_inferred_side_portion_approval(self):
        self.client.login(username="reviewer", password="pass")

        row = SpecimenListRowCandidate.objects.create(
            page=self.page,
            row_index=0,
            data={
                "accession_number": "KNM-ER 12345",
                "taxon": "Homo",
                "element": "Lt femur prox",
            },
        )

        approve_page(page=self.page, reviewer=self.user)
        row.refresh_from_db()

        response = self.client.get(reverse("specimen_list_queue"), {"pipeline_status": "approved"})

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Specimen List")
        self.assertEqual((row.data.get("_draft") or {}).get("data", {}).get("side"), "left")
        self.assertEqual((row.data.get("_draft") or {}).get("data", {}).get("portion"), "proximal")
