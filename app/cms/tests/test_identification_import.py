from crum import set_current_user
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import TestCase
from import_export.results import RowResult
from tablib import Dataset

from cms.models import Accession, AccessionRow, Collection, Identification, Locality
from cms.resources import IdentificationCreateResource, IdentificationUpdateResource


class IdentificationImportExportTests(TestCase):
    def setUp(self):
        user = get_user_model().objects.create_user(username="identification-import")
        set_current_user(user)
        self.addCleanup(set_current_user, None)

        self.collection = Collection.objects.create(
            abbreviation="COL",
            description="Test collection",
        )
        self.locality = Locality.objects.create(
            abbreviation="LOC",
            name="Test locality",
        )
        self.accession = Accession.objects.create(
            collection=self.collection,
            specimen_prefix=self.locality,
            specimen_no=1,
            accessioned_by=user,
        )
        self.accession_row = AccessionRow.objects.create(
            accession=self.accession,
            specimen_suffix="A",
        )

    def _update_dataset(self, identification_id, taxon_verbatim="Homo sapiens"):
        dataset = Dataset(
            headers=["id", "taxon_verbatim", "identification_qualifier"]
        )
        dataset.append([identification_id, taxon_verbatim, "cf."])
        return dataset

    def _create_dataset(self, include_id=False):
        headers = [
            "collection",
            "specimen_prefix",
            "specimen_no",
            "specimen_suffix",
            "taxon_verbatim",
            "identification_qualifier",
        ]
        if include_id:
            headers.insert(0, "id")
        dataset = Dataset(headers=headers)
        row = [
            self.collection.abbreviation,
            self.locality.abbreviation,
            self.accession.specimen_no,
            self.accession_row.specimen_suffix,
            "Homo sapiens",
            "cf.",
        ]
        if include_id:
            row.insert(0, "")
        dataset.append(row)
        return dataset

    def test_update_export_contains_only_identification_fields(self):
        identification = Identification.objects.create(
            accession_row=self.accession_row,
            taxon_verbatim="Homo sapiens",
            taxon="Homo sapiens",
        )

        dataset = IdentificationUpdateResource().export(
            queryset=Identification.objects.filter(pk=identification.pk)
        )

        self.assertEqual(dataset.headers[0], "id")
        self.assertNotIn("collection", dataset.headers)
        self.assertNotIn("specimen_prefix", dataset.headers)
        self.assertNotIn("accession_row", dataset.headers)
        self.assertEqual(str(dataset[0][0]), str(identification.pk))

    def test_update_import_matches_only_existing_identification_id(self):
        identification = Identification.objects.create(
            accession_row=self.accession_row,
            taxon_verbatim="Homo sapiens",
            taxon="Homo sapiens",
            identification_qualifier="cf.",
        )
        other_identification = Identification.objects.create(
            accession_row=self.accession_row,
            taxon_verbatim="Pan troglodytes",
            taxon="Pan troglodytes",
            identification_qualifier="aff.",
        )

        dataset = self._update_dataset(identification.pk, "Homo erectus")
        result = IdentificationUpdateResource().import_data(dataset, dry_run=False)

        self.assertFalse(result.has_errors())
        identification.refresh_from_db()
        other_identification.refresh_from_db()
        self.assertEqual(identification.taxon_verbatim, "Homo erectus")
        self.assertEqual(other_identification.taxon_verbatim, "Pan troglodytes")
        self.assertEqual(Identification.objects.count(), 2)

    def test_update_import_rejects_blank_and_unknown_ids(self):
        existing = Identification.objects.create(
            accession_row=self.accession_row,
            taxon_verbatim="Homo sapiens",
            taxon="Homo sapiens",
        )

        for identification_id in ("", "999999"):
            result = IdentificationUpdateResource().import_data(
                self._update_dataset(identification_id),
                dry_run=False,
            )
            self.assertTrue(result.has_errors())

        existing.refresh_from_db()
        self.assertEqual(existing.taxon_verbatim, "Homo sapiens")
        self.assertEqual(Identification.objects.count(), 1)

    def test_create_import_resolves_accession_row_and_always_creates(self):
        existing = Identification.objects.create(
            accession_row=self.accession_row,
            taxon_verbatim="Pan troglodytes",
            taxon="Pan troglodytes",
        )

        result = IdentificationCreateResource().import_data(
            self._create_dataset(),
            dry_run=False,
        )

        self.assertFalse(result.has_errors())
        self.assertFalse(result.has_validation_errors())
        self.assertEqual(result.rows[0].import_type, RowResult.IMPORT_TYPE_NEW)
        self.assertEqual(Identification.objects.count(), 2)
        created = Identification.objects.exclude(pk=existing.pk).get()
        self.assertEqual(created.accession_row, self.accession_row)
        self.assertEqual(created.taxon_verbatim, "Homo sapiens")

    def test_create_import_rejects_identification_id_column(self):
        result = IdentificationCreateResource().import_data(
            self._create_dataset(include_id=True),
            dry_run=False,
        )

        self.assertTrue(result.has_errors())
        self.assertFalse(Identification.objects.exists())

    def test_admin_offers_separate_imports_and_only_update_export(self):
        model_admin = admin.site._registry[Identification]

        self.assertEqual(
            model_admin.get_import_resource_classes(None),
            (IdentificationUpdateResource, IdentificationCreateResource),
        )
        self.assertEqual(
            model_admin.get_export_resource_classes(None),
            [IdentificationUpdateResource],
        )
