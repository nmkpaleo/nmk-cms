from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse
from unittest.mock import patch

from cms.models import AccessionNumberSeries, Organisation, UserOrganisation


class GenerateAccessionBatchViewTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.manager = User.objects.create_user(username="manager", password="pass")
        self.superuser = User.objects.create_superuser(
            username="admin", email="admin@example.com", password="pass"
        )
        self.nmk_org, _ = Organisation.objects.get_or_create(
            code="nmk", defaults={"name": "NMK"}
        )
        UserOrganisation.objects.create(user=self.manager, organisation=self.nmk_org)
        UserOrganisation.objects.create(user=self.superuser, organisation=self.nmk_org)
        self.collection_manager_group = Group.objects.create(name="Collection Managers")
        self.collection_manager_group.user_set.add(self.manager)
        self.url = reverse("accession-generate-batch")

        self.current_user = self.manager
        self.user_patcher = patch(
            "cms.models.get_current_user", side_effect=lambda: self.current_user
        )
        self.user_patcher.start()
        self.addCleanup(self.user_patcher.stop)

    def test_get_renders_hidden_user_with_collection_manager(self):
        self.client.login(username="manager", password="pass")
        self.current_user = self.manager

        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)

        form = response.context["form"]
        self.assertIn("user", form.fields)
        self.assertTrue(form.fields["user"].widget.is_hidden)
        self.assertEqual(form.fields["count"].max_value, 100)

    def test_start_and_current_numbers_prefilled(self):
        self.client.login(username="manager", password="pass")
        self.current_user = self.manager

        response = self.client.get(self.url)

        form = response.context["form"]
        self.assertEqual(form.initial.get("start_from"), 1)
        self.assertEqual(form.initial.get("current_number"), 1)
        self.assertContains(response, "id_start_from")
        self.assertContains(response, "value=\"1\"")

    def test_collection_manager_redirected_when_active_series_exists(self):
        self.current_user = self.manager
        AccessionNumberSeries.objects.create(
            user=self.manager,
            start_from=1,
            end_at=10,
            current_number=1,
            is_active=True,
            organisation=self.nmk_org,
        )

        self.client.login(username="manager", password="pass")
        response = self.client.get(self.url, follow=True)

        self.assertRedirects(response, reverse("dashboard"))
        self.assertContains(response, "active accession number series")

    def test_successful_series_creation_uses_request_user(self):
        self.client.login(username="manager", password="pass")
        self.current_user = self.manager

        response = self.client.post(
            self.url,
            {
                "count": "5",
                "start_from": "",
                "current_number": "",
                "is_active": "True",
                "user": str(self.manager.pk),
            },
            follow=True,
        )

        self.assertRedirects(response, reverse("accession-wizard"))
        series = AccessionNumberSeries.objects.get(user=self.manager)
        self.assertEqual(series.start_from, 1)
        self.assertEqual(series.current_number, 1)
        self.assertEqual(series.end_at, 5)

    def test_rejects_counts_above_cap(self):
        self.client.login(username="manager", password="pass")
        self.current_user = self.manager

        response = self.client.post(
            self.url,
            {
                "count": "101",
                "start_from": "",
                "current_number": "",
                "is_active": "True",
                "user": str(self.manager.pk),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertFormError(
            response, "form", "count", "You can generate up to 100 accession numbers at a time."
        )

    def test_superuser_can_create_series_even_with_existing_one(self):
        self.current_user = self.superuser
        AccessionNumberSeries.objects.create(
            user=self.superuser,
            start_from=50,
            end_at=60,
            current_number=55,
            is_active=True,
            organisation=self.nmk_org,
        )

        self.client.login(username="admin", password="pass")
        response = self.client.post(
            self.url,
            {
                "count": "2",
                "start_from": "",
                "current_number": "",
                "is_active": "True",
                "user": str(self.superuser.pk),
            },
            follow=True,
        )

        self.assertRedirects(response, reverse("accession-wizard"))
        series = AccessionNumberSeries.objects.filter(user=self.superuser).order_by("start_from").last()
        self.assertEqual(series.start_from, 61)
        self.assertEqual(series.end_at, 62)
