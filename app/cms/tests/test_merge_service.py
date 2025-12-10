from __future__ import annotations

from unittest import mock

from django.contrib.auth.models import Group, Permission, User
from django.contrib.contenttypes.models import ContentType
from django.contrib.sites.models import Site
from django.db import connection, models
from django.test import TransactionTestCase
from django.test.utils import isolate_apps

from cms.merge.constants import MergeStrategy
from cms.merge.engine import MergeResult
from cms.merge.mixins import MergeMixin
from cms.services.merge import FieldSelectionMergeService, merge_with_field_selection


@isolate_apps("cms")
class FieldSelectionMergeServiceTests(TransactionTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        if ContentType._meta.db_table not in connection.introspection.table_names():
            with connection.schema_editor() as schema_editor:
                schema_editor.create_model(ContentType)

        for model in (Permission, Group, User, Site):
            if model._meta.db_table in connection.introspection.table_names():
                continue
            with connection.schema_editor() as schema_editor:
                schema_editor.create_model(model)

        class MergeSubject(MergeMixin):
            title = models.CharField(max_length=64)
            description = models.TextField(blank=True)

            merge_fields = {
                "title": MergeStrategy.FIELD_SELECTION,
                "description": MergeStrategy.PREFER_NON_NULL,
            }

            class Meta:
                app_label = "cms"

        cls.MergeSubject = MergeSubject

        with connection.schema_editor() as schema_editor:
            schema_editor.create_model(MergeSubject)

    @classmethod
    def tearDownClass(cls):
        for model in (Site, User, Group, Permission, ContentType):
            if model._meta.db_table in connection.introspection.table_names():
                with connection.schema_editor() as schema_editor:
                    try:
                        schema_editor.delete_model(model)
                    except Exception:
                        pass

        with connection.schema_editor() as schema_editor:
            schema_editor.delete_model(cls.MergeSubject)
        super().tearDownClass()

    def setUp(self) -> None:
        self.target = self.MergeSubject.objects.create(
            title="Target", description="Existing description"
        )
        self.source_one = self.MergeSubject.objects.create(
            title="Source One", description="Source description"
        )
        self.source_two = self.MergeSubject.objects.create(
            title="Source Two", description="Source Two description"
        )

    def test_merges_sources_with_field_selection_strategy_map(self) -> None:
        service = FieldSelectionMergeService(self.MergeSubject)
        selections = {"title": str(self.source_two.pk)}

        merge_result = MergeResult(target=self.target, resolved_values={}, relation_actions={})

        with mock.patch("cms.services.merge.merge_records", return_value=merge_result) as merge_mock:
            results = service.merge(
                target=self.target,
                sources=[self.source_one, self.source_two],
                selections=selections,
                user=None,
                archive=True,
            )

        self.assertEqual(len(results), 2)
        merge_mock.assert_called()

        last_call_kwargs = merge_mock.call_args.kwargs
        self.assertEqual(last_call_kwargs["target"], self.target)
        self.assertEqual(last_call_kwargs["user"], None)
        self.assertTrue(last_call_kwargs["archive"])

        strategy_map = last_call_kwargs["strategy_map"]
        self.assertIn("title", strategy_map["fields"])
        self.assertEqual(
            strategy_map["fields"]["title"],
            {
                "strategy": MergeStrategy.FIELD_SELECTION.value,
                "selected_from": "source",
                "value": self.source_two.title,
            },
        )

    def test_merge_with_field_selection_wrapper_validates_fields(self) -> None:
        selections = {"description": str(self.source_one.pk)}

        with self.assertRaises(ValueError):
            merge_with_field_selection(
                model=self.MergeSubject,
                target=self.target,
                sources=[self.source_one],
                selections=selections,
            )
