from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace

from django.db import models
from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.contrib.sessions.models import Session
from django.contrib.sites.models import Site
from django.db import connection, models
from django.test import RequestFactory, SimpleTestCase, TransactionTestCase, override_settings
from django.urls import reverse
from django.test.utils import isolate_apps
from unittest import mock
from uuid import uuid4

from crum import set_current_user

from cms.merge.constants import MergeStrategy
from cms.merge.engine import merge_records
from cms.merge.forms import FieldSelectionForm
from cms.merge.mixins import MergeMixin
from cms.merge.views import FieldSelectionMergeView
from cms.models import MergeLog
from cms import models as cms_models
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


@override_settings(MERGE_TOOL_FEATURE=True)
class FieldSelectionViewMultiSourceTests(TransactionTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.factory = RequestFactory()
        existing_tables = set(connection.introspection.table_names())
        core_models = [
            ContentType,
            Group,
            Permission,
            LogEntry,
            Session,
            get_user_model(),
            Site,
            MergeLog,
            cms_models.Storage,
            cms_models.Storage.history.model,
        ]

        with connection.schema_editor(atomic=False) as schema_editor:
            for model in core_models:
                if model._meta.db_table not in existing_tables:
                    schema_editor.create_model(model)
                    existing_tables.add(model._meta.db_table)

    def setUp(self):
        super().setUp()
        self.user = get_user_model().objects.create_user(
            username=f"merge-user-{uuid4()}",
            email="merge@example.com",
            password="pass",
            is_staff=True,
        )
        content_type = ContentType.objects.get_for_model(cms_models.Storage)
        permission, _ = Permission.objects.get_or_create(
            codename="can_merge",
            content_type=content_type,
            defaults={"name": "Can merge storage records"},
        )
        self.user.user_permissions.add(permission)

    def tearDown(self):
        set_current_user(None)
        super().tearDown()

    def _build_request(self, data):
        request = self.factory.post("/merge/field-selection/", data=data)
        SessionMiddleware(lambda req: None).process_request(request)
        request.session.save()
        setattr(request, "_messages", FallbackStorage(request))
        request._dont_enforce_csrf_checks = True
        request.user = self.user
        return request

    def test_field_selection_merges_all_sources(self):
        set_current_user(self.user)
        target = cms_models.Storage.objects.create(area="Target")
        source_one = cms_models.Storage.objects.create(area="Source One")
        source_two = cms_models.Storage.objects.create(area="Source Two")
        set_current_user(None)

        view = FieldSelectionMergeView()
        merge_fields = view.get_mergeable_fields(cms_models.Storage)
        selection_field = FieldSelectionForm.selection_field_name("area")
        data = {
            "model": cms_models.Storage._meta.label,
            "target": str(target.pk),
            "candidates": ",".join(
                [str(target.pk), str(source_one.pk), str(source_two.pk)]
            ),
            selection_field: str(source_two.pk),
            "cancel": "/admin/cms/storage/",
        }
        for field in merge_fields:
            field_name = FieldSelectionForm.selection_field_name(field.name)
            data.setdefault(field_name, str(target.pk))

        request = self._build_request(data)

        with mock.patch(
            "cms.merge.views.reverse",
            side_effect=lambda name, *args, **kwargs: (
                "/merge/field-selection/"
                if name == "merge:merge_field_selection"
                else (
                    f"/admin/{name.split(':', 1)[1]}/{(args[0] if args else kwargs.get('object_id') or kwargs.get('pk') or '')}/"
                    if name.startswith("admin:")
                    else name
                )
            ),
        ), mock.patch("cms.merge.views.merge_records") as merge_mock:

            def _perform_merge(source, target, strategy_map, user=None, archive=True):
                area_config = strategy_map.get("fields", {}).get("area", {})
                resolved_area = area_config.get("value") or getattr(source, "area", None)
                if resolved_area is not None:
                    target.area = resolved_area
                return SimpleNamespace(target=target, resolved_values={}, relation_actions={})

            merge_mock.side_effect = _perform_merge
            response = FieldSelectionMergeView.as_view()(request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(merge_mock.call_count, 2)
        self.assertEqual(
            [call.kwargs["source"].pk for call in merge_mock.call_args_list],
            [source_one.pk, source_two.pk],
        )
        self.assertEqual(
            merge_mock.call_args_list[0].kwargs["strategy_map"]["fields"]["area"].get("value"),
            "Source Two",
        )
