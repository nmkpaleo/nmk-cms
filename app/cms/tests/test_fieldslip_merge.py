from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase

from crum import impersonate

from cms.merge.engine import merge_records
from cms.models import (
    Accession,
    AccessionFieldSlip,
    Collection,
    FieldSlip,
    Locality,
)


class FieldSlipMergeDeduplicationTests(TestCase):

    def setUp(self) -> None:
        user_model = get_user_model()
        self.user = user_model.objects.create(username="merge-admin")

        self._impersonation = impersonate(self.user)
        self._impersonation.__enter__()

        self.collection = Collection.objects.create(
            abbreviation="AA",
            description="Alpha Collection",
        )
        self.locality = Locality.objects.create(
            abbreviation="AL",
            name="Alpha Locality",
        )
        self.target = FieldSlip.objects.create(
            field_number="FS-001",
            verbatim_taxon="Taxon",
            verbatim_element="Element",
        )
        self.source = FieldSlip.objects.create(
            field_number="FS-002",
            verbatim_taxon="Taxon",
            verbatim_element="Element",
        )
        self.accession_one = Accession.objects.create(
            collection=self.collection,
            specimen_prefix=self.locality,
            specimen_no=1,
        )
        self.accession_two = Accession.objects.create(
            collection=self.collection,
            specimen_prefix=self.locality,
            specimen_no=2,
        )

    def tearDown(self) -> None:
        self._impersonation.__exit__(None, None, None)
        super().tearDown()

    def test_merge_skips_duplicate_accession_links(self) -> None:
        AccessionFieldSlip.objects.create(
            accession=self.accession_one,
            fieldslip=self.target,
        )
        AccessionFieldSlip.objects.create(
            accession=self.accession_one,
            fieldslip=self.source,
        )
        AccessionFieldSlip.objects.create(
            accession=self.accession_two,
            fieldslip=self.source,
        )

        result = merge_records(
            self.source,
            self.target,
            strategy_map=None,
            archive=False,
        )

        target_links = list(
            AccessionFieldSlip.objects.filter(fieldslip=self.target)
            .order_by("accession_id")
            .values_list("accession_id", flat=True)
        )
        self.assertEqual(
            target_links,
            [self.accession_one.id, self.accession_two.id],
        )
        self.assertFalse(
            AccessionFieldSlip.objects.filter(fieldslip=self.source).exists()
        )
        self.assertEqual(
            AccessionFieldSlip.objects.count(),
            2,
        )

        relation_log = result.relation_actions.get("accession_links", {})
        self.assertEqual(relation_log.get("updated"), 1)
        self.assertEqual(relation_log.get("deleted"), 1)
        self.assertEqual(relation_log.get("skipped"), 1)
