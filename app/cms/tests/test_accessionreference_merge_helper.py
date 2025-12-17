from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from crum import impersonate

from cms.merge.services import (
    build_accession_reference_field_selection_form,
    merge_accession_reference_candidates,
)
from cms.models import Accession, AccessionReference, Collection, Locality, MergeLog, Reference


class AccessionReferenceMergeHelperTests(TestCase):
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
        self.alt_reference = Reference.objects.create(
            title="Ref B", first_author="Author", year="2024"
        )

        self.target = AccessionReference.objects.create(
            accession=self.accession, reference=self.reference, page="1"
        )
        self.source = AccessionReference.objects.create(
            accession=self.accession, reference=self.alt_reference, page="2"
        )

    def tearDown(self) -> None:
        self._impersonation.__exit__(None, None, None)
        super().tearDown()

    def test_build_field_selection_form_respects_target(self) -> None:
        form = build_accession_reference_field_selection_form(
            candidate_ids=[self.target.pk, self.source.pk],
            target_id=self.target.pk,
        )

        self.assertEqual(len(form.candidates), 2)
        target_candidate = next(c for c in form.candidates if c.key == str(self.target.pk))
        self.assertEqual(target_candidate.role, "target")

    def test_build_field_selection_form_rejects_cross_accession(self) -> None:
        other_accession = Accession.objects.create(
            collection=self.collection,
            specimen_prefix=self.locality,
            specimen_no=2,
        )
        cross_source = AccessionReference.objects.create(
            accession=other_accession, reference=self.reference, page="3"
        )

        with self.assertRaises(ValidationError):
            build_accession_reference_field_selection_form(
                candidate_ids=[self.target.pk, cross_source.pk]
            )

    def test_merge_candidates_applies_field_selection(self) -> None:
        form = build_accession_reference_field_selection_form(
            candidate_ids=[self.target.pk, self.source.pk],
            target_id=self.target.pk,
            data={
                "select__reference": str(self.source.pk),
                "select__page": str(self.source.pk),
            },
        )
        self.assertTrue(form.is_valid())

        source_pk = self.source.pk
        results = merge_accession_reference_candidates(
            target=self.target, sources=[self.source], form=form, user=self.user
        )

        self.assertEqual(len(results), 1)
        self.target.refresh_from_db()
        self.assertEqual(self.target.reference, self.alt_reference)
        self.assertEqual(self.target.page, "2")
        self.assertFalse(AccessionReference.objects.filter(pk=source_pk).exists())
        log = MergeLog.objects.get(
            model_label="cms.accessionreference",
            source_pk=str(source_pk),
            target_pk=str(self.target.pk),
        )
        self.assertIn("page", log.resolved_values.get("fields", {}))
