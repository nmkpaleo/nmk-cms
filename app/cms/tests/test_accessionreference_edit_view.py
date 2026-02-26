"""Tests for editing AccessionReference Page(s) values."""

from crum import impersonate
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import TestCase
from django.urls import reverse

from cms.models import Accession, AccessionReference, Collection, Locality, Reference


User = get_user_model()


class AccessionReferenceEditViewTests(TestCase):
    def setUp(self) -> None:
        self.manager = User.objects.create_user(username="manager", password="pass1234")
        manager_group, _ = Group.objects.get_or_create(name="Collection Managers")
        self.manager.groups.add(manager_group)

        self.regular_user = User.objects.create_user(username="regular", password="pass1234")

        with impersonate(self.manager):
            self.collection = Collection.objects.create(
                abbreviation="COLL", description="Test Collection"
            )
            self.locality = Locality.objects.create(abbreviation="LOC", name="Locality")
            self.accession = Accession.objects.create(
                collection=self.collection,
                specimen_prefix=self.locality,
                specimen_no=1,
                is_published=True,
            )
            self.reference = Reference.objects.create(
                title="Ref A", first_author="Author", year="2024"
            )
            self.accession_reference = AccessionReference.objects.create(
                accession=self.accession,
                reference=self.reference,
                page="10",
            )

    def test_collection_manager_can_update_page(self):
        self.client.force_login(self.manager)
        url = reverse("accessionreference_edit", args=[self.accession_reference.pk])

        response = self.client.post(
            url,
            {
                "reference": self.accession_reference.reference_id,
                "page": "12",
            },
        )

        self.accession_reference.refresh_from_db()

        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.accession_reference.page, "12")
        self.assertEqual(
            response.headers["Location"],
            reverse("accession_detail", args=[self.accession_reference.accession_id]),
        )

    def test_edit_view_prefills_existing_page(self):
        self.client.force_login(self.manager)
        url = reverse("accessionreference_edit", args=[self.accession_reference.pk])

        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["form"].initial.get("page"), "10")

    def test_non_collection_manager_is_forbidden(self):
        self.client.force_login(self.regular_user)
        url = reverse("accessionreference_edit", args=[self.accession_reference.pk])

        response = self.client.get(url)

        self.assertEqual(response.status_code, 403)
