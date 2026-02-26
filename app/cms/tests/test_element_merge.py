from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from crum import impersonate

from cms.merge.services import merge_elements
from cms.models import Element, MergeLog




class ElementMergeEndToEndTests(TestCase):
    def setUp(self) -> None:
        user_model = get_user_model()
        self.user = user_model.objects.create(username="merge-runner")
        self._impersonation = impersonate(self.user)
        self._impersonation.__enter__()

        self.parent = Element.objects.create(name="Parent")
        self.target = Element.objects.create(name="Target", parent_element=self.parent)
        self.source = Element.objects.create(name="Source")

    def tearDown(self) -> None:
        self._impersonation.__exit__(None, None, None)
        super().tearDown()

    def test_rejects_unknown_fields(self) -> None:
        with self.assertRaises(ValidationError):
            merge_elements(source=self.source, target=self.target, selected_fields={"foo": "bar"})

        self.assertTrue(Element.objects.filter(pk=self.source.pk).exists())
        self.assertEqual(Element.objects.get(pk=self.target.pk).name, "Target")

    def test_accepts_explicit_parent_primary_key(self) -> None:
        child_parent = Element.objects.create(name="New Parent")

        merge_elements(
            source=self.source,
            target=self.target,
            selected_fields={"parent_element": child_parent.pk, "name": "target"},
        )

        self.target.refresh_from_db()
        self.assertEqual(self.target.parent_element, child_parent)
        self.assertEqual(self.target.name, "Target")

    def test_dry_run_leaves_records_unchanged_and_skips_logging(self) -> None:
        merge_elements(
            source=self.source,
            target=self.target,
            selected_fields={"name": "source"},
            dry_run=True,
        )

        self.target.refresh_from_db()
        self.source.refresh_from_db()

        self.assertEqual(self.target.name, "Target")
        self.assertTrue(Element.objects.filter(pk=self.source.pk).exists())
        self.assertFalse(
            MergeLog.objects.filter(
                model_label="cms.element",
                source_pk=str(self.source.pk),
                target_pk=str(self.target.pk),
            ).exists()
        )
