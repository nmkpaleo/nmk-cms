from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from cms.forms import AccessionNumberSeriesAdminForm
from cms.models import AccessionNumberSeries


class DashboardGenerateBatchButtonStateTests(TestCase):
    def setUp(self):
        self.User = get_user_model()
        self.collection_manager_group = Group.objects.create(name="Collection Managers")

    def _create_manager(self, username: str = "manager"):
        user = self.User.objects.create_user(username=username, password="pass")
        self.collection_manager_group.user_set.add(user)
        return user

    def test_collection_manager_without_active_series_sees_enabled_generate_batch(self):
        manager = self._create_manager()
        self.client.login(username=manager.username, password="pass")

        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn(reverse("accession-generate-batch"), content)
        self.assertIn('aria-disabled="false"', content)
        self.assertNotIn("w3-disabled", content)

    def test_collection_manager_with_active_series_sees_disabled_generate_batch(self):
        manager = self._create_manager()
        AccessionNumberSeries.objects.create(
            user=manager,
            start_from=1,
            end_at=10,
            current_number=1,
            is_active=True,
        )

        self.client.login(username=manager.username, password="pass")
        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('aria-disabled="true"', content)
        self.assertIn('tabindex="-1"', content)
        self.assertNotIn(reverse("accession-generate-batch"), content)

    def test_superuser_sees_enabled_generate_batch(self):
        admin = self.User.objects.create_superuser(
            username="admin", email="admin@example.com", password="pass"
        )
        self.client.login(username=admin.username, password="pass")

        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn(reverse("accession-generate-batch"), content)
        self.assertIn('aria-disabled="false"', content)


class DashboardCreateSingleButtonStateTests(TestCase):
    def setUp(self):
        self.User = get_user_model()
        self.collection_manager_group = Group.objects.create(name="Collection Managers")

    def _create_manager(self, username: str = "manager"):
        user = self.User.objects.create_user(username=username, password="pass")
        self.collection_manager_group.user_set.add(user)
        return user

    def test_collection_manager_without_active_series_sees_disabled_create_single(self):
        manager = self._create_manager()
        self.client.login(username=manager.username, password="pass")

        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn('aria-disabled="true"', content)
        self.assertIn('tabindex="-1"', content)
        self.assertNotIn(reverse("accession-wizard"), content)

    def test_collection_manager_with_active_series_sees_enabled_create_single(self):
        manager = self._create_manager()
        AccessionNumberSeries.objects.create(
            user=manager,
            start_from=1,
            end_at=10,
            current_number=1,
            is_active=True,
        )

        self.client.login(username=manager.username, password="pass")
        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn(reverse("accession-wizard"), content)
        self.assertIn('aria-disabled="false"', content)


class AccessionNumberSeriesAdminFormTests(TestCase):
    def setUp(self):
        self.User = get_user_model()
        self.manager = self.User.objects.create_user(username="manager", password="pass")

    def test_count_cap_enforced(self):
        form = AccessionNumberSeriesAdminForm(
            data={
                "user": str(self.manager.pk),
                "count": "101",
                "is_active": "True",
                "start_from": "",
                "current_number": "",
            },
            request_user=self.manager,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("count", form.errors)
        self.assertIn(
            "You can generate up to 100 accession numbers at a time.",
            form.errors["count"],
        )

    def test_prefix_fields_are_optional_or_absent(self):
        form = AccessionNumberSeriesAdminForm(request_user=self.manager)

        for field_name in ("collection", "specimen_prefix"):
            if field_name in form.fields:
                self.assertFalse(
                    form.fields[field_name].required,
                    f"{field_name} should not be required",
                )
            else:
                # Fields are intentionally omitted from the form
                self.assertNotIn(field_name, form.fields)

    def test_start_and_current_fields_readonly_for_new_series(self):
        form = AccessionNumberSeriesAdminForm(request_user=self.manager)

        self.assertTrue(form.fields["start_from"].disabled)
        self.assertTrue(form.fields["current_number"].disabled)
        self.assertFalse(form.fields["start_from"].required)
        self.assertFalse(form.fields["current_number"].required)

    def test_user_field_hidden_and_scoped_to_request_user(self):
        form = AccessionNumberSeriesAdminForm(request_user=self.manager)

        user_field = form.fields["user"]
        self.assertTrue(user_field.widget.is_hidden)
        self.assertEqual(list(user_field.queryset), [self.manager])
        self.assertEqual(user_field.initial, self.manager)

    def test_numbering_respects_shared_and_tbi_pools(self):
        shared_owner = self.User.objects.create_user(username="shared-owner", password="pass")
        tbi_user = self.User.objects.create_user(username="TBI", password="pass")
        AccessionNumberSeries.objects.create(
            user=shared_owner,
            start_from=1,
            end_at=10,
            current_number=5,
            is_active=True,
        )
        AccessionNumberSeries.objects.create(
            user=tbi_user,
            start_from=1_000_000,
            end_at=1_000_004,
            current_number=1_000_002,
            is_active=True,
        )

        shared_form = AccessionNumberSeriesAdminForm(
            data={
                "user": str(self.manager.pk),
                "count": "3",
                "is_active": "True",
                "start_from": "",
                "current_number": "",
            },
            request_user=self.manager,
        )
        self.assertTrue(shared_form.is_valid())
        shared_series = shared_form.save()
        self.assertEqual(shared_series.start_from, 11)
        self.assertEqual(shared_series.current_number, 11)
        self.assertEqual(shared_series.end_at, 13)

        tbi_form = AccessionNumberSeriesAdminForm(
            data={
                "user": str(tbi_user.pk),
                "count": "2",
                "is_active": "True",
                "start_from": "",
                "current_number": "",
            },
            request_user=tbi_user,
        )
        self.assertTrue(tbi_form.is_valid())
        tbi_series = tbi_form.save()
        self.assertEqual(tbi_series.start_from, 1_000_005)
        self.assertEqual(tbi_series.current_number, 1_000_005)
        self.assertEqual(tbi_series.end_at, 1_000_006)
