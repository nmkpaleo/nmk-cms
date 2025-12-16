from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from crum import impersonate

from cms.merge.constants import MergeStrategy
from cms.merge.services import (
    build_accession_reference_strategy_map,
    merge_accession_references,
)
from cms.models import Accession, AccessionReference, Collection, Locality, MergeLog, Reference


class AccessionReferenceMergeServiceTests(TestCase):
    def setUp(self) -> None:
        user_model = get_user_model()
        self.user = user_model.objects.create(username="merge-user")
        self._impersonation = impersonate(self.user)
        self._impersonation.__enter__()

        self.collection = Collection.objects.create(abbreviation="COLL", description="Test")
        self.locality = Locality.objects.create(abbreviation="LOC", name="Locality")
        self.accession = Accession.objects.create(
            collection=self.collection,
            specimen_prefix=self.locality,
            specimen_no=1,
        )
        self.reference = Reference.objects.create(title="Ref A", first_author="Author", year="2024")
        self.alt_reference = Reference.objects.create(title="Ref B", first_author="Author", year="2024")

        self.target = AccessionReference.objects.create(
            accession=self.accession, reference=self.reference, page="1"
        )
        self.source = AccessionReference.objects.create(
            accession=self.accession, reference=self.alt_reference, page="2"
        )

    def tearDown(self) -> None:
        self._impersonation.__exit__(None, None, None)
        super().tearDown()

    def test_merge_applies_field_selection_and_logs(self) -> None:
        strategy_map = {
            "fields": {
                "reference": {
                    "strategy": MergeStrategy.FIELD_SELECTION.value,
                    "selected_from": "source",
                    "value": self.alt_reference,
                },
                "page": {
                    "strategy": MergeStrategy.FIELD_SELECTION.value,
                    "selected_from": "source",
                    "value": "2",
                },
            }
        }

        source_pk = self.source.pk

        result = merge_accession_references(
            source=self.source,
            target=self.target,
            strategy_map=strategy_map,
            user=self.user,
        )

        self.target.refresh_from_db()
        self.assertEqual(self.target.reference, self.alt_reference)
        self.assertEqual(self.target.page, "2")
        self.assertFalse(AccessionReference.objects.filter(pk=self.source.pk).exists())
        self.assertIn("reference", result.resolved_values)
        self.assertIn("page", result.resolved_values)

        log = MergeLog.objects.get(
            model_label="cms.accessionreference",
            source_pk=str(source_pk),
            target_pk=str(self.target.pk),
        )
        self.assertIn("reference", log.resolved_values.get("fields", {}))

    def test_merge_rejects_mismatched_accession(self) -> None:
        other_accession = Accession.objects.create(
            collection=self.collection,
            specimen_prefix=self.locality,
            specimen_no=2,
        )
        other_source = AccessionReference.objects.create(
            accession=other_accession, reference=self.reference
        )

        with self.assertRaises(ValidationError):
            merge_accession_references(source=other_source, target=self.target)

    def test_build_strategy_map_restricts_fields(self) -> None:
        with self.assertRaises(ValidationError):
            build_accession_reference_strategy_map(
                selected_fields={"invalid": "source"},
                source=self.source,
                target=self.target,
            )

    def test_dry_run_keeps_source_and_target(self) -> None:
        merge_accession_references(
            source=self.source,
            target=self.target,
            selected_fields={"page": "source"},
            dry_run=True,
        )

        self.target.refresh_from_db()
        self.assertEqual(self.target.page, "1")
        self.assertTrue(AccessionReference.objects.filter(pk=self.source.pk).exists())

