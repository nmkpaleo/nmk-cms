from django.contrib.auth import get_user_model
from django.test import TransactionTestCase

from crum import impersonate

from cms.forms import AccessionReferenceFieldSelectionForm
from cms.merge.forms import FieldSelectionCandidate
from cms.models import Accession, AccessionReference, Collection, Locality, Reference


class AccessionReferenceFieldSelectionFormTests(TransactionTestCase):
    def setUp(self):
        self.user = get_user_model().objects.create(username="merge-user")
        with impersonate(self.user):
            self.collection = Collection.objects.create(
                abbreviation="COLL", description="Test Collection"
            )
            self.locality = Locality.objects.create(
                abbreviation="LOC", name="Locality"
            )
            self.reference = Reference.objects.create(
                title="Ref A", first_author="Author", year="2024"
            )
            self.alt_reference = Reference.objects.create(
                title="Ref B", first_author="Author", year="2024"
            )

    def _create_accession(self, specimen_no: int = 1) -> Accession:
        with impersonate(self.user):
            return Accession.objects.create(
                collection=self.collection,
                specimen_prefix=self.locality,
                specimen_no=specimen_no,
            )

    def _create_accession_reference(
        self,
        *,
        accession: Accession,
        reference: Reference,
        page: str | None = None,
    ) -> AccessionReference:
        with impersonate(self.user):
            return AccessionReference.objects.create(
                accession=accession, reference=reference, page=page
            )

    def _build_form(self, candidates):
        data = {}
        for field_name in AccessionReferenceFieldSelectionForm.merge_field_names:
            data[
                AccessionReferenceFieldSelectionForm.selection_field_name(field_name)
            ] = candidates[0].key
        return AccessionReferenceFieldSelectionForm(candidates=candidates, data=data)

    def test_requires_two_candidates(self):
        accession = self._create_accession()
        target = self._create_accession_reference(
            accession=accession, reference=self.reference
        )

        form = self._build_form(
            [FieldSelectionCandidate.from_instance(target, label="Target", role="target")]
        )

        self.assertFalse(form.is_valid())
        self.assertIn(
            "Select at least two accession references to merge.",
            form.non_field_errors(),
        )

    def test_requires_shared_accession(self):
        target_accession = self._create_accession(specimen_no=1)
        source_accession = self._create_accession(specimen_no=2)

        target = self._create_accession_reference(
            accession=target_accession, reference=self.reference
        )
        source = self._create_accession_reference(
            accession=source_accession, reference=self.alt_reference
        )

        form = self._build_form(
            [
                FieldSelectionCandidate.from_instance(target, label="Target", role="target"),
                FieldSelectionCandidate.from_instance(source, label="Source", role="source"),
            ]
        )

        self.assertFalse(form.is_valid())
        self.assertIn(
            "Accession references must belong to the same accession.",
            form.non_field_errors(),
        )

    def test_valid_for_shared_accession(self):
        accession = self._create_accession()

        target = self._create_accession_reference(
            accession=accession, reference=self.reference, page="1"
        )
        source = self._create_accession_reference(
            accession=accession, reference=self.alt_reference, page="2"
        )

        form = self._build_form(
            [
                FieldSelectionCandidate.from_instance(target, label="Target", role="target"),
                FieldSelectionCandidate.from_instance(source, label="Source", role="source"),
            ]
        )

        self.assertTrue(form.is_valid())
        strategy = form.build_strategy_map()
        self.assertIn("page", strategy["fields"])

