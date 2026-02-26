from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from cms.forms import AccessionNumberSeriesAdminForm
from cms.models import AccessionNumberSeries, Organisation, UserOrganisation


class DashboardGenerateBatchButtonStateTests(TestCase):
    def setUp(self):
        self.User = get_user_model()
        self.collection_manager_group = Group.objects.create(name="Collection Managers")
        self.nmk_org, _ = Organisation.objects.get_or_create(
            code="nmk", defaults={"name": "NMK"}
        )

    def _create_manager(self, username: str = "manager"):
        user = self.User.objects.create_user(username=username, password="pass")
        self.collection_manager_group.user_set.add(user)
        UserOrganisation.objects.create(user=user, organisation=self.nmk_org)
        return user

    def test_collection_manager_without_active_series_sees_enabled_generate_batch(self):
        manager = self._create_manager()
        self.client.login(username=manager.username, password="pass")

        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn(reverse("accession-generate-batch"), content)
        self.assertIn('aria-disabled="false"', content)
        self.assertIn(reverse("accession-generate-batch"), content)

    def test_collection_manager_with_active_series_sees_disabled_generate_batch(self):
        manager = self._create_manager()
        AccessionNumberSeries.objects.create(
            user=manager,
            start_from=1,
            end_at=10,
            current_number=1,
            is_active=True,
            organisation=self.nmk_org,
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
        self.nmk_org, _ = Organisation.objects.get_or_create(
            code="nmk", defaults={"name": "NMK"}
        )

    def _create_manager(self, username: str = "manager"):
        user = self.User.objects.create_user(username=username, password="pass")
        self.collection_manager_group.user_set.add(user)
        UserOrganisation.objects.create(user=user, organisation=self.nmk_org)
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
            organisation=self.nmk_org,
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
        self.nmk_org, _ = Organisation.objects.get_or_create(
            code="nmk", defaults={"name": "NMK"}
        )
        self.tbi_org, _ = Organisation.objects.get_or_create(
            code="tbi", defaults={"name": "TBI"}
        )
        UserOrganisation.objects.create(user=self.manager, organisation=self.nmk_org)

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

    def test_organisation_defaults_to_user_membership(self):
        form = AccessionNumberSeriesAdminForm(request_user=self.manager)

        organisation_field = form.fields.get("organisation")
        self.assertIsNotNone(organisation_field)
        self.assertEqual(organisation_field.initial, self.nmk_org)
        self.assertTrue(organisation_field.widget.is_hidden)

    def test_user_field_hidden_and_scoped_to_request_user(self):
        form = AccessionNumberSeriesAdminForm(request_user=self.manager)

        user_field = form.fields["user"]
        self.assertTrue(user_field.widget.is_hidden)
        self.assertEqual(list(user_field.queryset), [self.manager])
        self.assertEqual(user_field.initial, self.manager)

    def test_mismatched_organisation_rejected(self):
        form = AccessionNumberSeriesAdminForm(
            data={
                "user": str(self.manager.pk),
                "organisation": str(self.tbi_org.pk),
                "count": "5",
                "is_active": "True",
                "start_from": "",
                "current_number": "",
            },
            request_user=self.manager,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("organisation", form.errors)

    def test_numbering_respects_shared_and_tbi_pools(self):
        shared_owner = self.User.objects.create_user(username="shared-owner", password="pass")
        tbi_user = self.User.objects.create_user(username="TBI", password="pass")
        UserOrganisation.objects.create(user=shared_owner, organisation=self.nmk_org)
        UserOrganisation.objects.create(user=tbi_user, organisation=self.tbi_org)
        AccessionNumberSeries.objects.create(
            user=shared_owner,
            start_from=1,
            end_at=10,
            current_number=5,
            is_active=True,
            organisation=self.nmk_org,
        )
        AccessionNumberSeries.objects.create(
            user=tbi_user,
            start_from=1_000_000,
            end_at=1_000_004,
            current_number=1_000_002,
            is_active=True,
            organisation=self.tbi_org,
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

    def test_tbi_pool_used_for_all_tbi_members(self):
        tbi_member = self.User.objects.create_user(
            username="tbi-member", password="pass"
        )
        UserOrganisation.objects.create(user=tbi_member, organisation=self.tbi_org)

        form = AccessionNumberSeriesAdminForm(
            data={
                "user": str(tbi_member.pk),
                "count": "2",
                "is_active": "True",
                "start_from": "",
                "current_number": "",
            },
            request_user=tbi_member,
        )

        self.assertTrue(form.is_valid(), form.errors)
        series = form.save()

        self.assertEqual(series.start_from, 1_000_000)
        self.assertEqual(series.current_number, 1_000_000)
        self.assertEqual(series.end_at, 1_000_001)
        self.assertEqual(series.organisation, self.tbi_org)

    def test_superuser_user_queryset_scoped_to_selected_organisation(self):
        superuser = self.User.objects.create_superuser(
            username="admin", email="admin@example.com", password="pass"
        )
        other_user = self.User.objects.create_user(username="other", password="pass")
        UserOrganisation.objects.create(user=other_user, organisation=self.tbi_org)

        form = AccessionNumberSeriesAdminForm(
            data={
                "organisation": str(self.tbi_org.pk),
                "user": str(other_user.pk),
                "count": "5",
                "is_active": "True",
                "start_from": "",
                "current_number": "",
            },
            request_user=superuser,
        )

        self.assertQuerySetEqual(
            form.fields["user"].queryset.order_by("pk"),
            [other_user.pk],
            lambda user: user.pk,
        )

        self.assertIn(
            (other_user.pk, str(other_user)), list(form.fields["user"].widget.choices)
        )

        option = form.fields["user"].widget.create_option(
            "user",
            other_user.pk,
            str(other_user),
            False,
            0,
        )
        self.assertEqual(
            option.get("attrs", {}).get("data-organisation"), str(self.tbi_org.pk)
        )

    def test_superuser_add_form_defaults_to_blank_user_and_organisation(self):
        superuser = self.User.objects.create_superuser(
            username="admin", email="admin@example.com", password="pass"
        )
        other_user = self.User.objects.create_user(username="other", password="pass")
        UserOrganisation.objects.create(user=other_user, organisation=self.tbi_org)

        form = AccessionNumberSeriesAdminForm(request_user=superuser)

        self.assertIsNone(form.initial.get("organisation"))
        self.assertIsNone(form.initial.get("user"))

        user_choices = list(form.fields["user"].widget.choices)
        self.assertTrue(user_choices)
        first_value, first_label = user_choices[0]
        self.assertEqual(first_value, "")
        self.assertEqual(first_label, "---------")

    def test_widget_metadata_exposes_tbi_organisation(self):
        form = AccessionNumberSeriesAdminForm()

        attrs = form.fields["user"].widget.attrs

        self.assertEqual(attrs.get("data-tbi-org-id"), str(self.tbi_org.pk))
