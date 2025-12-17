from urllib.parse import urlencode

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.test import TransactionTestCase, override_settings
from django.urls import reverse

from crum import impersonate

from cms.forms import FieldSlipMergeForm
from cms.models import Accession, AccessionFieldSlip, Collection, FieldSlip, Locality


call_command("migrate", verbosity=0, run_syncdb=True)


@override_settings(ALLOWED_HOSTS=["testserver", "localhost"])
class AccessionFieldSlipMergeViewTests(TransactionTestCase):
    def setUp(self):
        setup_user = get_user_model().objects.create_user(username="setup-user")
        with impersonate(setup_user):
            self.collection = Collection.objects.create(
                abbreviation="AC",
                description="Alpha Collection",
            )
            self.locality = Locality.objects.create(
                abbreviation="AL", name="Alpha Locality"
            )

        self.user_with_perm = get_user_model().objects.create_user(
            username="merge-user",
            password="test-pass",
            is_staff=True,
            is_superuser=True,
        )

        self.collection_managers = Group.objects.create(name="Collection Managers")
        fieldslip_ct = ContentType.objects.get_for_model(FieldSlip)
        self.merge_permission = Permission.objects.get(
            codename="can_merge", content_type=fieldslip_ct
        )

        self.manager_with_perm = get_user_model().objects.create_user(
            username="manager-merge-user",
            password="test-pass",
            is_staff=True,
        )
        self.manager_with_perm.groups.add(self.collection_managers)
        self.manager_with_perm.user_permissions.add(self.merge_permission)

        self.user_without_perm = get_user_model().objects.create_user(
            username="no-merge-user",
            password="test-pass",
        )
        self.user_without_perm.groups.add(self.collection_managers)

    def _create_accession(self) -> Accession:
        with impersonate(self.user_with_perm):
            return Accession.objects.create(
                collection=self.collection,
                specimen_prefix=self.locality,
                specimen_no=1,
            )

    def test_requires_merge_permission(self):
        accession = self._create_accession()
        with impersonate(self.user_with_perm):
            fieldslip = FieldSlip.objects.create(
                field_number="FS-1",
                verbatim_taxon="Taxon",
                verbatim_element="Element",
            )
        with impersonate(self.user_with_perm):
            AccessionFieldSlip.objects.create(accession=accession, fieldslip=fieldslip)

        self.client.force_login(self.user_without_perm)
        response = self.client.post(
            reverse("accession_merge_fieldslips", args=[accession.pk]),
            {"source": fieldslip.pk, "target": fieldslip.pk},
        )

        self.assertEqual(response.status_code, 403)

    @override_settings(MERGE_TOOL_FEATURE=True)
    def test_redirects_to_merge_field_selection(self):
        accession = self._create_accession()
        with impersonate(self.user_with_perm):
            target = FieldSlip.objects.create(
                field_number="FS-100",
                verbatim_taxon="Taxon",
                verbatim_element="Element",
            )
            source = FieldSlip.objects.create(
                field_number="FS-200",
                verbatim_taxon="Taxon",
                verbatim_element="Element",
            )
        with impersonate(self.user_with_perm):
            AccessionFieldSlip.objects.create(accession=accession, fieldslip=target)
            AccessionFieldSlip.objects.create(accession=accession, fieldslip=source)

        self.client.force_login(self.user_with_perm)
        response = self.client.post(
            reverse("accession_merge_fieldslips", args=[accession.pk]),
            {"target": target.pk, "source": source.pk},
        )

        cancel_url = reverse("accession_detail", kwargs={"pk": accession.pk})
        expected_query = urlencode(
            {
                "model": FieldSlip._meta.label,
                "target": target.pk,
                "candidates": f"{target.pk},{source.pk}",
                "cancel": cancel_url,
            }
        )
        expected_url = f"{reverse('merge:merge_field_selection')}?{expected_query}"

        self.assertRedirects(response, expected_url, fetch_redirect_response=False)
        self.assertTrue(FieldSlip.objects.filter(pk=source.pk).exists())
        self.assertEqual(
            AccessionFieldSlip.objects.filter(accession=accession).count(),
            2,
        )

    def test_rejects_fieldslip_not_linked_to_accession(self):
        accession = self._create_accession()
        with impersonate(self.user_with_perm):
            other_accession = Accession.objects.create(
                collection=self.collection,
                specimen_prefix=self.locality,
                specimen_no=2,
            )
        with impersonate(self.user_with_perm):
            target = FieldSlip.objects.create(
                field_number="FS-300",
                verbatim_taxon="Taxon",
                verbatim_element="Element",
            )
            unrelated = FieldSlip.objects.create(
                field_number="FS-400",
                verbatim_taxon="Taxon",
                verbatim_element="Element",
            )
        with impersonate(self.user_with_perm):
            AccessionFieldSlip.objects.create(accession=accession, fieldslip=target)
            AccessionFieldSlip.objects.create(accession=other_accession, fieldslip=unrelated)

        self.client.force_login(self.user_with_perm)
        response = self.client.post(
            reverse("accession_merge_fieldslips", args=[accession.pk]),
            {"target": target.pk, "source": unrelated.pk},
            follow=True,
        )

        self.assertRedirects(
            response, reverse("accession_detail", kwargs={"pk": accession.pk})
        )
        self.assertTrue(FieldSlip.objects.filter(pk=unrelated.pk).exists())
        self.assertEqual(
            AccessionFieldSlip.objects.filter(accession=accession).count(),
            1,
        )

    def test_merge_form_rejects_identical_selection(self):
        accession = self._create_accession()
        with impersonate(self.user_with_perm):
            slip = FieldSlip.objects.create(
                field_number="FS-900",
                verbatim_taxon="Taxon",
                verbatim_element="Element",
            )
        with impersonate(self.user_with_perm):
            AccessionFieldSlip.objects.create(accession=accession, fieldslip=slip)

        self.client.force_login(self.manager_with_perm)
        response = self.client.post(
            reverse("accession_merge_fieldslips", args=[accession.pk]),
            {"target": slip.pk, "source": slip.pk},
            follow=True,
        )

        self.assertRedirects(
            response, reverse("accession_detail", kwargs={"pk": accession.pk})
        )
        messages = list(response.wsgi_request._messages)
        self.assertTrue(
            any("Select two different field slips" in message.message for message in messages)
        )
        self.assertEqual(
            AccessionFieldSlip.objects.filter(accession=accession).count(),
            1,
        )

    def test_merge_form_rendered_for_permitted_user(self):
        accession = self._create_accession()
        with impersonate(self.user_with_perm):
            target = FieldSlip.objects.create(
                field_number="FS-500",
                verbatim_taxon="Taxon",
                verbatim_element="Element",
            )
            source = FieldSlip.objects.create(
                field_number="FS-600",
                verbatim_taxon="Taxon",
                verbatim_element="Element",
            )
            unrelated = FieldSlip.objects.create(
                field_number="FS-700",
                verbatim_taxon="Other Taxon",
                verbatim_element="Other Element",
            )

        with impersonate(self.user_with_perm):
            AccessionFieldSlip.objects.create(accession=accession, fieldslip=target)
            AccessionFieldSlip.objects.create(accession=accession, fieldslip=source)

        self.client.force_login(self.manager_with_perm)
        response = self.client.get(
            reverse("accession_detail", kwargs={"pk": accession.pk}), follow=True
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Merge field slips")
        self.assertContains(response, "name=\"target\"")
        self.assertContains(response, "name=\"source\"")

        merge_form = FieldSlipMergeForm(accession=accession)
        self.assertQuerySetEqual(
            merge_form.fields["target"].queryset.order_by("pk"),
            FieldSlip.objects.filter(pk__in=[target.pk, source.pk]).order_by("pk"),
            transform=lambda obj: obj,
        )

    def test_merge_form_hidden_with_fewer_than_two_links(self):
        accession = self._create_accession()
        with impersonate(self.user_with_perm):
            slip = FieldSlip.objects.create(
                field_number="FS-950", verbatim_taxon="Taxon", verbatim_element="Element"
            )
            AccessionFieldSlip.objects.create(accession=accession, fieldslip=slip)

        self.client.force_login(self.manager_with_perm)
        response = self.client.get(
            reverse("accession_detail", kwargs={"pk": accession.pk}), follow=True
        )

        self.assertNotContains(response, "Merge field slips")
        self.assertNotContains(
            response,
            reverse("accession_merge_fieldslips", args=[accession.pk]),
        )

    def test_merge_form_hidden_without_permission(self):
        accession = self._create_accession()
        with impersonate(self.user_with_perm):
            linked = FieldSlip.objects.create(
                field_number="FS-800",
                verbatim_taxon="Taxon",
                verbatim_element="Element",
            )
        with impersonate(self.user_with_perm):
            AccessionFieldSlip.objects.create(accession=accession, fieldslip=linked)

        self.client.force_login(self.user_without_perm)
        response = self.client.get(
            reverse("accession_detail", kwargs={"pk": accession.pk})
        )

        self.assertNotContains(
            response,
            reverse("accession_merge_fieldslips", args=[accession.pk]),
        )
