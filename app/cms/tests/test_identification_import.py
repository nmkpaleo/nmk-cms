from crum import set_current_user
from django.contrib.auth import get_user_model
from django.test import TestCase
from import_export.results import RowResult
from tablib import Dataset

from cms.models import Accession, AccessionRow, Collection, Identification, Locality
from cms.resources import IdentificationResource


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

    def _dataset(self, identification_id, qualifier, taxon_verbatim="Homo sapiens"):
        dataset = Dataset(
            headers=[
                "id",
                "collection",
                "specimen_prefix",
                "specimen_no",
                "specimen_suffix",
                "identification_qualifier",
                "taxon_verbatim",
            ]
        )
        dataset.append(
            [
                identification_id,
                self.collection.abbreviation,
                self.locality.abbreviation,
                self.accession.specimen_no,
                self.accession_row.specimen_suffix,
                qualifier,
                taxon_verbatim,
            ]
        )
        return dataset

    def test_export_includes_identification_id(self):
        identification = Identification.objects.create(
            accession_row=self.accession_row,
            taxon_verbatim="Homo sapiens",
            taxon="Homo sapiens",
        )

        dataset = IdentificationResource().export(
            queryset=Identification.objects.filter(pk=identification.pk)
        )

        self.assertEqual(dataset.headers[:2], ["id", "collection"])
        self.assertIn("taxon_verbatim", dataset.headers)
        self.assertEqual(str(dataset[0][0]), str(identification.pk))

    def test_import_updates_identification_by_id(self):
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

        result = IdentificationResource().import_data(
            self._dataset(identification.pk, "sp."),
            dry_run=False,
        )

        self.assertFalse(result.has_errors())
        identification.refresh_from_db()
        other_identification.refresh_from_db()
        self.assertEqual(identification.identification_qualifier, "sp.")
        self.assertEqual(other_identification.identification_qualifier, "aff.")
        self.assertEqual(Identification.objects.count(), 2)

    def test_blank_id_creates_new_identification(self):
        existing = Identification.objects.create(
            accession_row=self.accession_row,
            taxon_verbatim="Homo sapiens",
            taxon="Homo sapiens",
        )

        result = IdentificationResource().import_data(
            self._dataset("", "cf.", "Pan troglodytes"),
            dry_run=False,
        )

        self.assertFalse(result.has_errors())
        self.assertFalse(
            result.has_validation_errors(),
            result.rows[0].validation_error,
        )
        self.assertEqual(result.rows[0].import_type, RowResult.IMPORT_TYPE_NEW)
        self.assertEqual(Identification.objects.count(), 2)
        self.assertEqual(
            Identification.objects.exclude(pk=existing.pk).get().accession_row,
            self.accession_row,
        )

    def test_missing_id_column_is_rejected(self):
        dataset = Dataset(
            headers=[
                "collection",
                "specimen_prefix",
                "specimen_no",
                "specimen_suffix",
                "identification_qualifier",
                "taxon_verbatim",
            ]
        )
        dataset.append(
            [
                self.collection.abbreviation,
                self.locality.abbreviation,
                self.accession.specimen_no,
                self.accession_row.specimen_suffix,
                "cf.",
                "Pan troglodytes",
            ]
        )

        result = IdentificationResource().import_data(dataset, dry_run=False)

        self.assertTrue(result.has_errors())
        self.assertFalse(Identification.objects.exists())
