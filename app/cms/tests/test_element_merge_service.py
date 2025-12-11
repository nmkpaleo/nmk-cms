from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase

from crum import impersonate

from cms.merge.services import merge_elements
from cms.models import Element, MergeLog


class ElementMergeServiceTests(TestCase):
    def setUp(self) -> None:
        user_model = get_user_model()
        self.user = user_model.objects.create(username="merge-user")
        self._impersonation = impersonate(self.user)
        self._impersonation.__enter__()

        self.parent = Element.objects.create(name="Parent")
        self.target = Element.objects.create(name="Target", parent_element=self.parent)
        self.source = Element.objects.create(name="Source", parent_element=None)

    def tearDown(self) -> None:
        self._impersonation.__exit__(None, None, None)
        super().tearDown()

    def test_merge_applies_field_selection_and_deletes_source(self) -> None:
        result = merge_elements(
            source=self.source,
            target=self.target,
            selected_fields={"name": "source", "parent_element": "target"},
        )

        self.target.refresh_from_db()
        self.assertEqual(self.target.name, "Source")
        self.assertEqual(self.target.parent_element, self.parent)
        self.assertFalse(Element.objects.filter(pk=self.source.pk).exists())
        self.assertIn("name", result.resolved_values)
        self.assertIn("parent_element", result.resolved_values)

    def test_merge_rejects_cycles_in_parent_selection(self) -> None:
        child = Element.objects.create(name="Child", parent_element=self.target)
        cyclic_source = Element.objects.create(name="Loop", parent_element=child)

        with self.assertRaises(ValidationError):
            merge_elements(
                source=cyclic_source,
                target=self.target,
                selected_fields={"parent_element": child},
            )

        self.assertTrue(Element.objects.filter(pk=cyclic_source.pk).exists())

    def test_merge_logs_history_entries(self) -> None:
        source_id = self.source.pk
        merge_elements(
            source=self.source,
            target=self.target,
            selected_fields={"name": "source"},
        )

        log = MergeLog.objects.filter(
            model_label="cms.element",
            source_pk=str(source_id),
            target_pk=str(self.target.pk),
        ).first()

        self.assertIsNotNone(log)
        self.assertIn("name", log.resolved_values.get("fields", {}))

    def test_merge_rejects_identical_candidates(self) -> None:
        with self.assertRaises(ValidationError):
            merge_elements(
                source=self.target,
                target=self.target,
                selected_fields={"name": "source"},
            )

