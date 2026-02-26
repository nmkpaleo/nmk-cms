from __future__ import annotations

import os
from unittest import mock

import pytest

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

pytestmark = pytest.mark.django_db

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from cms.models import FieldSlip
from cms.resources import AccessionReferenceResource, AccessionResource, AccessionRowResource


class FieldSlipAutocompleteAuthTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user(
            username="user", email="user@example.com", password="pass"
        )

    def test_anonymous_requests_are_rejected(self):
        response = self.client.get(reverse("fieldslip-autocomplete"))

        self.assertEqual(response.status_code, 403)

    def test_authenticated_requests_return_matches(self):
        with mock.patch("cms.models.get_current_user", return_value=self.user):
            FieldSlip.objects.create(
                field_number="FS-001",
                verbatim_taxon="Panthera leo",
                verbatim_element="Mandible",
            )

        self.client.login(username=self.user.username, password="pass")
        response = self.client.get(reverse("fieldslip-autocomplete"), {"q": "FS-001"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        texts = [result.get("text") for result in payload.get("results", [])]
        self.assertIn("FS-001", texts)


class FlatFileImportViewTests(TestCase):
    def setUp(self):
        self.staff = get_user_model().objects.create_user(
            username="staff", email="staff@example.com", password="pass", is_staff=True
        )
        self.user = get_user_model().objects.create_user(
            username="user", email="user2@example.com", password="pass"
        )

    def test_non_staff_are_redirected_from_import_view(self):
        self.client.login(username=self.user.username, password="pass")

        response = self.client.get(reverse("admin:flat-file-import"))

        self.assertEqual(response.status_code, 302)

    def test_staff_can_view_import_form(self):
        self.client.login(username=self.staff.username, password="pass")

        response = self.client.get(reverse("admin:flat-file-import"))

        self.assertEqual(response.status_code, 200)
        content = response.content.decode()
        self.assertIn("Flat File Import", content)
        self.assertIn("import_file", content)


class ImportExportResourceConfigurationTests(TestCase):
    def test_accession_resource_exposes_has_duplicates_as_readonly(self):
        resource = AccessionResource()

        self.assertIn("has_duplicates", resource.fields)
        self.assertTrue(resource.fields["has_duplicates"].readonly)
        self.assertIn("has_duplicates", resource.Meta.export_order)
        self.assertIn("has_duplicates", resource.Meta.readonly_fields)

    def test_accession_row_and_reference_use_expected_identifiers(self):
        row_resource = AccessionRowResource()
        reference_resource = AccessionReferenceResource()

        self.assertEqual(row_resource.Meta.import_id_fields, ("accession", "specimen_suffix"))
        self.assertEqual(reference_resource.Meta.import_id_fields, ("accession", "reference"))
