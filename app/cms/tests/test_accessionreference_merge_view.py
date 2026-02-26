from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TransactionTestCase, override_settings
from django.urls import reverse
from unittest.mock import patch

from crum import impersonate

from cms.models import (
    Accession,
    AccessionReference,
    Collection,
    Locality,
    MergeLog,
    Reference,
)




class AccessionReferenceMergeViewTests(TransactionTestCase):
    def setUp(self) -> None:
        collection_manager_ct = ContentType.objects.get_for_model(AccessionReference)
        self.merge_permission, _ = Permission.objects.get_or_create(
            codename="can_merge",
            content_type=collection_manager_ct,
            defaults={"name": "Can merge accession references"},
        )
        self.collection_managers = Group.objects.create(name="Collection Managers")
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
        self.user_with_perm.groups.add(self.collection_managers)

        self.user_without_perm = get_user_model().objects.create_user(
            username="manager-no-perm",
            password="pass",
            is_staff=True,
        )
        self.user_without_perm.groups.add(self.collection_managers)

        self.user_patcher = patch("cms.models.get_current_user", return_value=self.user_with_perm)
        self.user_patcher.start()
        self.addCleanup(self.user_patcher.stop)

        with impersonate(self.staff_user):
            self.collection = Collection.objects.create(
                abbreviation="AC", description="Alpha Collection"
            )
            self.locality = Locality.objects.create(abbreviation="AL", name="Alpha Locality")

    def _create_accession_with_references(self) -> tuple[Accession, list[AccessionReference]]:
        self.user_patcher = patch("cms.models.get_current_user", return_value=self.user_with_perm)
        self.user_patcher.start()
        self.addCleanup(self.user_patcher.stop)

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
        self.assertTrue(
            MergeLog.objects.filter(
                model_label="cms.accessionreference",
                target_pk=str(target.pk),
                source_pk=str(source.pk),
            ).exists()
        )

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

    @override_settings(MERGE_TOOL_FEATURE=True)
    def test_merge_button_visible_with_permission_and_multiple_references(self):
        accession, references = self._create_accession_with_references()
        self.client.force_login(self.user_with_perm)

        response = self.client.get(
            reverse("accession_detail", kwargs={"pk": accession.pk}), follow=True
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Merge references")
        self.assertContains(
            response, reverse("accession_merge_references", kwargs={"accession_id": accession.pk})
        )
        self.assertContains(response, 'name="selected_ids"')
        self.assertContains(response, 'name="target"')

    @override_settings(MERGE_TOOL_FEATURE=True)
    def test_merge_button_hidden_without_permission(self):
        accession, references = self._create_accession_with_references()
        self.client.force_login(self.user_without_perm)

        response = self.client.get(
            reverse("accession_detail", kwargs={"pk": accession.pk}), follow=True
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Merge references")
        self.assertNotContains(
            response, reverse("accession_merge_references", kwargs={"accession_id": accession.pk})
        )

    @override_settings(MERGE_TOOL_FEATURE=True)
    def test_merge_button_hidden_with_single_reference(self):
        self.user_patcher = patch("cms.models.get_current_user", return_value=self.user_with_perm)
        self.user_patcher.start()
        self.addCleanup(self.user_patcher.stop)

        with impersonate(self.staff_user):
            accession = Accession.objects.create(
                collection=self.collection,
                specimen_prefix=self.locality,
                specimen_no=3,
            )
            solo_ref = Reference.objects.create(title="Solo Ref", first_author="Author", year="2023")
            AccessionReference.objects.create(
                accession=accession, reference=solo_ref, page="9"
            )

        self.client.force_login(self.user_with_perm)
        response = self.client.get(
            reverse("accession_detail", kwargs={"pk": accession.pk}), follow=True
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Merge references")
        self.assertNotContains(
            response, reverse("accession_merge_references", kwargs={"accession_id": accession.pk})
        )
