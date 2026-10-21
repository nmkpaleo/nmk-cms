from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from cms.merge.services import (
    bulk_merge_duplicate_accession_references,
    combine_pages,
)
from cms.models import Accession, AccessionReference, Collection, Locality, Reference


class CombinePagesTests(TestCase):
    def test_sorted_unique_numeric(self):
        self.assertEqual(combine_pages(["110", "110", "100"]), "100, 110")

    def test_numeric_not_lexicographic(self):
        self.assertEqual(combine_pages(["100", "9"]), "9, 100")

    def test_splits_commas_and_ignores_empty(self):
        self.assertEqual(combine_pages(["5, 3", None, "", "3"]), "3, 5")

    def test_empty(self):
        self.assertEqual(combine_pages([None, ""]), "")


@override_settings(MERGE_TOOL_FEATURE=True)
class BulkMergeDuplicateAccessionReferenceTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.admin_user = User.objects.create_superuser("bulk-admin", "a@example.com", "pw")
        collection = Collection.objects.create(abbreviation="COLL", description="Test")
        locality = Locality.objects.create(abbreviation="LOC", name="Locality")
        self.acc1 = Accession.objects.create(collection=collection, specimen_prefix=locality, specimen_no=1)
        self.acc2 = Accession.objects.create(collection=collection, specimen_prefix=locality, specimen_no=2)
        self.ref_a = Reference.objects.create(title="Ref A", first_author="Author", year="2024")
        self.ref_b = Reference.objects.create(title="Ref B", first_author="Author", year="2024")

    def _make(self, accession, reference, page):
        return AccessionReference.objects.create(accession=accession, reference=reference, page=page)

    def test_merges_into_lowest_pk_with_combined_pages(self):
        first = self._make(self.acc1, self.ref_a, "110")
        self._make(self.acc1, self.ref_a, "110")
        self._make(self.acc1, self.ref_a, "100")
        other = self._make(self.acc1, self.ref_b, "7")
        other_acc = self._make(self.acc2, self.ref_a, "8")

        report = bulk_merge_duplicate_accession_references(user=self.admin_user)

        self.assertEqual((report.groups_found, report.groups_merged, report.rows_merged), (1, 1, 2))
        self.assertEqual(report.failures, [])
        self.assertEqual(
            AccessionReference.objects.filter(accession=self.acc1, reference=self.ref_a).count(), 1
        )
        first.refresh_from_db()
        self.assertEqual(first.page, "100, 110")
        other.refresh_from_db()
        other_acc.refresh_from_db()
        self.assertEqual((other.page, other_acc.page), ("7", "8"))

    def test_page_too_long_is_reported_and_group_untouched(self):
        self._make(self.acc1, self.ref_a, "1000, 2000")
        self._make(self.acc1, self.ref_a, "3000, 4000")

        report = bulk_merge_duplicate_accession_references(user=self.admin_user)

        self.assertEqual(report.groups_merged, 0)
        self.assertEqual(len(report.failures), 1)
        self.assertEqual(AccessionReference.objects.count(), 2)

    def test_no_duplicates(self):
        self._make(self.acc1, self.ref_a, "1")
        report = bulk_merge_duplicate_accession_references(user=self.admin_user)
        self.assertEqual(report.groups_found, 0)

    def test_admin_button_and_post(self):
        self._make(self.acc1, self.ref_a, "2")
        self._make(self.acc1, self.ref_a, "1")
        self.client.force_login(self.admin_user)

        url = reverse("admin:cms_accessionreference_merge_duplicates")
        changelist = self.client.get(reverse("admin:cms_accessionreference_changelist"))
        self.assertContains(changelist, url)

        self.assertEqual(self.client.get(url).status_code, 302)
        self.assertEqual(AccessionReference.objects.count(), 2)

        response = self.client.post(url, follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(AccessionReference.objects.get().page, "1, 2")

    def test_post_forbidden_without_permission(self):
        staff = get_user_model().objects.create_user("plain", "p@example.com", "pw", is_staff=True)
        self.client.force_login(staff)
        response = self.client.post(reverse("admin:cms_accessionreference_merge_duplicates"))
        self.assertEqual(response.status_code, 403)
