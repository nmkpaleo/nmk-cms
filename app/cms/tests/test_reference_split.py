from crum import impersonate
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse

from cms.models import (
    Accession,
    AccessionReference,
    AccessionRow,
    Collection,
    Identification,
    Locality,
    Reference,
)


class ReferenceSplitAdminTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.admin_user = user_model.objects.create_superuser(
            username="reference-split-admin",
            email="admin@example.com",
            password="password",
        )
        with impersonate(self.admin_user):
            collection = Collection.objects.create(
                abbreviation="COLL",
                description="Test collection",
            )
            locality = Locality.objects.create(abbreviation="LOC", name="Test locality")
            accession = Accession.objects.create(
                collection=collection,
                specimen_prefix=locality,
                specimen_no=1,
            )
            accession_row = AccessionRow.objects.create(
                accession=accession,
                specimen_suffix="-",
            )
            self.reference = Reference.objects.create(
                title="Shared title",
                first_author="Author",
                year="2024",
                journal="Journal",
                citation="Citation one 1999 | Citation two 2000 | Citation three",
            )
            AccessionReference.objects.create(
                accession=accession,
                reference=self.reference,
                page="12",
            )
            Identification.objects.create(
                accession_row=accession_row,
                reference=self.reference,
                taxon_verbatim="Test taxon",
                taxon="Test taxon",
            )

    def test_admin_split_button_preview_and_split_preserve_relations(self):
        self.client.force_login(self.admin_user)
        split_url = reverse("admin:cms_reference_split_pipe")

        changelist_response = self.client.get(reverse("admin:cms_reference_changelist"))
        self.assertContains(changelist_response, split_url)
        self.assertContains(changelist_response, "Split References by |")

        preview_response = self.client.get(split_url)
        self.assertContains(preview_response, "Citation one 1999 | Citation two 2000 | Citation three")
        self.assertContains(preview_response, "Citation two 2000")
        self.assertContains(preview_response, "Citation three")

        with impersonate(self.admin_user):
            response = self.client.post(
                split_url,
                {
                    "confirm": "yes",
                    "preview_token": preview_response.context["preview_token"],
                },
            )

        self.assertRedirects(response, reverse("admin:cms_reference_changelist"))
        citations = [
            "Citation one 1999",
            "Citation two 2000",
            "Citation three",
        ]
        split_references = Reference.objects.filter(citation__in=citations)
        self.assertEqual(split_references.count(), 3)
        self.assertEqual(
            {
                reference.citation: (
                    reference.title,
                    reference.first_author,
                    reference.year,
                )
                for reference in split_references
            },
            {
                "Citation one 1999": ("Citation one 1999", "Citation one 1999", "1999"),
                "Citation two 2000": ("Citation two 2000", "Citation two 2000", "2000"),
                "Citation three": ("Citation three", "Citation three", None),
            },
        )
        self.assertEqual(
            set(split_references.values_list("journal", flat=True)),
            {"Journal"},
        )
        self.assertEqual(
            AccessionReference.objects.filter(reference__in=split_references).count(),
            3,
        )
        self.assertEqual(
            set(
                AccessionReference.objects.filter(reference__in=split_references)
                .values_list("page", flat=True)
            ),
            {"12"},
        )
        identifications = Identification.objects.filter(reference__in=split_references)
        self.assertEqual(identifications.count(), 3)
        self.assertEqual(
            set(identifications.values_list("taxon", flat=True)),
            {"Test taxon"},
        )

    def test_split_requires_all_creation_permissions_and_hides_button(self):
        user_model = get_user_model()
        staff_user = user_model.objects.create_user(
            username="reference-split-staff",
            is_staff=True,
        )
        required_codenames = {
            "change_reference",
            "add_reference",
            "add_accessionreference",
            "add_identification",
        }
        permissions = list(
            Permission.objects.filter(
                content_type__app_label="cms", codename__in=required_codenames
            )
        )
        self.assertEqual(
            {permission.codename for permission in permissions}, required_codenames
        )

        split_url = reverse("admin:cms_reference_split_pipe")
        changelist_url = reverse("admin:cms_reference_changelist")
        for missing_codename in required_codenames:
            staff_user.user_permissions.set(
                [
                    permission
                    for permission in permissions
                    if permission.codename != missing_codename
                ]
            )
            self.client.force_login(staff_user)

            self.assertEqual(self.client.get(split_url).status_code, 403)
            if missing_codename != "change_reference":
                changelist_response = self.client.get(changelist_url)
                self.assertNotContains(changelist_response, split_url)

    def test_confirmation_requires_the_unchanged_preview(self):
        self.client.force_login(self.admin_user)
        split_url = reverse("admin:cms_reference_split_pipe")
        preview_response = self.client.get(split_url)
        preview_token = preview_response.context["preview_token"]

        with impersonate(self.admin_user):
            self.reference.citation = "Changed citation one | Changed citation two"
            self.reference.save(update_fields=["citation"])
            added_reference = Reference.objects.create(
                title="Unreviewed work",
                first_author="Unreviewed author",
                citation="Unreviewed citation one | Unreviewed citation two",
            )
        with impersonate(self.admin_user):
            response = self.client.post(
                split_url,
                {"confirm": "yes", "preview_token": preview_token},
            )

        self.assertRedirects(response, split_url)
        self.reference.refresh_from_db()
        self.assertEqual(
            self.reference.citation, "Changed citation one | Changed citation two"
        )
        self.assertEqual(Reference.objects.count(), 2)
        added_reference.refresh_from_db()
        self.assertEqual(
            added_reference.citation,
            "Unreviewed citation one | Unreviewed citation two",
        )

    def test_oversized_parts_are_reported_and_not_split(self):
        oversized_part = "x" * 256
        with impersonate(self.admin_user):
            self.reference.citation = f"{oversized_part} | Valid citation"
            self.reference.save(update_fields=["citation"])
            with self.assertRaises(ValidationError):
                self.reference.split_by_pipe()
        self.client.force_login(self.admin_user)
        split_url = reverse("admin:cms_reference_split_pipe")

        preview_response = self.client.get(split_url)
        self.assertContains(preview_response, "exceed 255 characters")
        self.assertNotContains(preview_response, "name=\"confirm\"")
        with impersonate(self.admin_user):
            response = self.client.post(
                split_url,
                {
                    "confirm": "yes",
                    "preview_token": preview_response.context["preview_token"],
                },
            )

        self.assertRedirects(response, split_url)
        self.assertEqual(Reference.objects.count(), 1)
        self.reference.refresh_from_db()
        self.assertEqual(self.reference.citation, f"{oversized_part} | Valid citation")
