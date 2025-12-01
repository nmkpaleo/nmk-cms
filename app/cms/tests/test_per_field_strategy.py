from __future__ import annotations

from dataclasses import dataclass

from django.db import models
from django.test import SimpleTestCase
from django.test.utils import isolate_apps
from unittest import mock

from cms.merge.constants import MergeStrategy
from cms.merge.engine import merge_records
from cms.merge.mixins import MergeMixin
from cms.merge.strategies import FieldSelectionStrategy, UNCHANGED


@dataclass
class DummyModel:
    name: str
    description: str | None = None


class FieldSelectionStrategyTests(SimpleTestCase):
    def setUp(self):
        self.strategy = FieldSelectionStrategy()
        self.source = DummyModel(name="Source", description="from source")
        self.target = DummyModel(name="Target", description="from target")

    def test_applies_explicit_value(self):
        resolution = self.strategy(
            field_name="name",
            source=self.source,
            target=self.target,
            source_value=self.source.name,
            target_value=self.target.name,
            options={"value": "Chosen"},
        )

        self.assertEqual(resolution.value, "Chosen")
        self.assertIn("user-selected", resolution.note.lower())

    def test_respects_selected_from_source_and_target(self):
        source_resolution = self.strategy(
            field_name="description",
            source=self.source,
            target=self.target,
            source_value=self.source.description,
            target_value=self.target.description,
            options={"selected_from": "source"},
        )
        self.assertEqual(source_resolution.value, "from source")

        target_resolution = self.strategy(
            field_name="description",
            source=self.source,
            target=self.target,
            source_value=self.source.description,
            target_value=self.target.description,
            options={"selected_from": "target"},
        )
        self.assertEqual(target_resolution.value, "from target")

    def test_returns_unchanged_when_no_choice(self):
        resolution = self.strategy(
            field_name="description",
            source=self.source,
            target=self.target,
            source_value=self.source.description,
            target_value=self.target.description,
            options={},
        )

        self.assertIs(resolution.value, UNCHANGED)
        self.assertIn("unchanged", resolution.note.lower())


@isolate_apps("cms")
class FieldSelectionMergeIntegrationTests(SimpleTestCase):
    databases = {"default"}

    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        class DummyManager(models.Manager):
            def __init__(self):
                super().__init__()
                self._objects = {}

            def register(self, instance):
                self._objects[instance.pk] = instance

            def get(self, pk):  # type: ignore[override]
                return self._objects[pk]

            def __get__(self, instance, owner):
                return self

        class MergeSubject(MergeMixin):
            objects = DummyManager()

            title = models.CharField(max_length=128)
            code = models.CharField(max_length=32, blank=True)

            class Meta:
                app_label = "cms"
                managed = False

            def save(self, *args, **kwargs):
                return None

            def refresh_from_db(self, *args, **kwargs):
                return None

            def delete(self, *args, **kwargs):
                return None

        cls.MergeSubject = MergeSubject
        cls.manager = MergeSubject.objects

    def setUp(self):
        self.target = self.MergeSubject(title="Existing", code="ABC")
        self.target.pk = 1
        self.source = self.MergeSubject(title="Incoming", code="SRC")
        self.source.pk = 2
        self.manager.register(self.target)
        self.manager.register(self.source)

    def test_field_selection_merge_updates_log(self):
        strategy_map = {
            "fields": {
                "title": {
                    "strategy": MergeStrategy.FIELD_SELECTION.value,
                    "selected_from": "source",
                },
                "code": {
                    "strategy": MergeStrategy.FIELD_SELECTION.value,
                    "selected_from": "target",
                },
            }
        }

        with mock.patch("cms.merge.engine._log_merge") as log_merge_mock:
            result = merge_records(
                self.source,
                self.target,
                strategy_map,
                user=None,
                archive=False,
            )

        self.assertEqual(self.target.title, "Incoming")
        self.assertEqual(self.target.code, "ABC")

        self.assertIn("title", result.resolved_values)
        self.assertEqual(result.resolved_values["title"].value, "Incoming")
        self.assertEqual(result.resolved_values["code"].value, "ABC")

        log_merge_mock.assert_called_once()
        payload = log_merge_mock.call_args.kwargs
        self.assertEqual(payload["resolved_fields"]["title"]["value"], "Incoming")
        self.assertEqual(payload["resolved_fields"]["code"]["value"], "ABC")
        title_strategy = payload["strategy_map"]["fields"]["title"]
        code_strategy = payload["strategy_map"]["fields"]["code"]
        self.assertEqual(title_strategy["strategy"], MergeStrategy.FIELD_SELECTION.value)
        self.assertEqual(code_strategy["strategy"], MergeStrategy.FIELD_SELECTION.value)
        self.assertEqual(title_strategy.get("options", {}).get("selected_from"), "source")
        self.assertEqual(code_strategy.get("options", {}).get("selected_from"), "target")
