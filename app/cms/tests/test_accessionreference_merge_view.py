from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.test import TransactionTestCase, override_settings
from django.urls import reverse

from crum import impersonate

from cms.models import Accession, AccessionReference, Collection, Locality, Reference


call_command("migrate", verbosity=0, run_syncdb=True)


class AccessionReferenceMergeViewTests(TransactionTestCase):
    def setUp(self) -> None:
        collection_manager_ct = ContentType.objects.get_for_model(AccessionReference)
        self.merge_permission, _ = Permission.objects.get_or_create(
            codename="can_merge",
            content_type=collection_manager_ct,
            defaults={"name": "Can merge accession references"},
        )
        self.staff_user = get_user_model().objects.create_user(
            username="staff-merge",
            password="pass",
            is_staff=True,
            is_superuser=True,
        )
        self.user_with_perm = get_user_model().objects.create_user(
            username="manager-merge",
            password="pass",
            is_staff=True,
        )
        self.user_with_perm.user_permissions.add(self.merge_permission)

        self.user_without_perm = get_user_model().objects.create_user(
            username="manager-no-perm",
            password="pass",
            is_staff=True,
        )

        with impersonate(self.staff_user):
            self.collection = Collection.objects.create(
                abbreviation="AC", description="Alpha Collection"
            )
            self.locality = Locality.objects.create(abbreviation="AL", name="Alpha Locality")

    def _create_accession_with_references(self) -> tuple[Accession, list[AccessionReference]]:
        with impersonate(self.staff_user):
            accession = Accession.objects.create(
                collection=self.collection,
                specimen_prefix=self.locality,
                specimen_no=1,
            )
            ref_one = Reference.objects.create(
                title="Ref One", first_author="Author", year="2021"
            )
            ref_two = Reference.objects.create(
                title="Ref Two", first_author="Author", year="2022"
            )

            target = AccessionReference.objects.create(
                accession=accession, reference=ref_one, page="1"
            )
            source = AccessionReference.objects.create(
                accession=accession, reference=ref_two, page="2"
            )

        return accession, [target, source]

    @override_settings(MERGE_TOOL_FEATURE=True)
    def test_prepare_renders_field_selection(self):
        accession, references = self._create_accession_with_references()
        target, source = references

        self.client.force_login(self.user_with_perm)
        response = self.client.post(
            reverse("accession_merge_references", args=[accession.pk]),
            {
                "stage": "prepare",
                "selected_ids": [str(target.pk), str(source.pk)],
                "target": str(target.pk),
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "cms/accession_reference_merge.html")
        self.assertContains(response, "Select preferred values")
        self.assertContains(response, target.reference.title)

    @override_settings(MERGE_TOOL_FEATURE=True)
    def test_confirm_merges_references(self):
        accession, references = self._create_accession_with_references()
        target, source = references

        self.client.force_login(self.user_with_perm)
        response = self.client.post(
            reverse("accession_merge_references", args=[accession.pk]),
            {
                "stage": "confirm",
                "selected_ids": [str(target.pk), str(source.pk)],
                "target": str(target.pk),
                "select__reference": str(source.pk),
                "select__page": str(source.pk),
            },
        )

        self.assertRedirects(response, reverse("accession_detail", args=[accession.pk]))
        target.refresh_from_db()
        self.assertEqual(target.reference, source.reference)
        self.assertEqual(target.page, source.page)
        self.assertFalse(AccessionReference.objects.filter(pk=source.pk).exists())

    @override_settings(MERGE_TOOL_FEATURE=True)
    def test_rejects_requests_without_permission(self):
        accession, references = self._create_accession_with_references()
        target, source = references

        self.client.force_login(self.user_without_perm)
        response = self.client.post(
            reverse("accession_merge_references", args=[accession.pk]),
            {
                "stage": "prepare",
                "selected_ids": [str(target.pk), str(source.pk)],
                "target": str(target.pk),
            },
        )

        self.assertEqual(response.status_code, 403)

    @override_settings(MERGE_TOOL_FEATURE=True)
    def test_rejects_single_candidate_selection(self):
        accession, references = self._create_accession_with_references()
        (target,) = references[:1]

        self.client.force_login(self.user_with_perm)
        response = self.client.post(
            reverse("accession_merge_references", args=[accession.pk]),
            {
                "stage": "prepare",
                "selected_ids": [str(target.pk)],
                "target": str(target.pk),
            },
            follow=False,
        )

        self.assertEqual(response.status_code, 302)
        self.assertIn("#accession-reference-merge", response["Location"])
        self.assertTrue(
            AccessionReference.objects.filter(accession=accession).filter(pk=target.pk).exists()
        )
