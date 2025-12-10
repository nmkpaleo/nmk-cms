from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TransactionTestCase, override_settings
from django.urls import reverse

from crum import impersonate

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

        self.user_without_perm = get_user_model().objects.create_user(
            username="no-merge-user",
            password="test-pass",
        )

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

    def test_merges_fieldslips_and_redirects(self):
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

        self.assertRedirects(
            response, reverse("accession_detail", kwargs={"pk": accession.pk})
        )
        self.assertTrue(FieldSlip.objects.filter(pk=target.pk).exists())
        self.assertFalse(FieldSlip.objects.filter(pk=source.pk).exists())
        self.assertEqual(
            AccessionFieldSlip.objects.filter(accession=accession).count(),
            1,
        )
        self.assertEqual(
            AccessionFieldSlip.objects.filter(accession=accession, fieldslip=target).count(),
            1,
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
