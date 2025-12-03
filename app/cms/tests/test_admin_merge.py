from __future__ import annotations

from contextlib import contextmanager
from urllib.parse import parse_qs, urlparse

from django.contrib import admin
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.contrib.admin.models import LogEntry
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.contrib.sites.models import Site
from django.contrib.sites.management import create_default_site
from django.contrib.sessions.models import Session
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.db import connection, models
from django.core.management import call_command
from django.db.models.signals import post_migrate
from django.http import HttpResponse, HttpResponseRedirect
from django.test import RequestFactory, TransactionTestCase, override_settings
from django.test.utils import isolate_apps
from django.urls import include, path
from unittest.mock import patch
from uuid import uuid4
from crum import set_current_user

from cms.admin import MergeAdminActionMixin
from cms import admin_merge
from cms.admin_merge import MergeAdminMixin
from cms.merge.constants import MergeStrategy
from cms.merge.mixins import MergeMixin
from cms.models import MergeLog
from cms import models as cms_models


test_admin_site = admin.site
urlpatterns = [
    path("admin/", test_admin_site.urls),
    path("admin/upload-scan/", lambda request: HttpResponse(""), name="admin-upload-scan"),
    path("admin/do-ocr/", lambda request: HttpResponse(""), name="admin-do-ocr"),
    path("admin/chatgpt-usage/", lambda request: HttpResponse(""), name="admin-chatgpt-usage"),
    path("merge/", include("cms.merge.urls")),
]


@override_settings(ROOT_URLCONF="cms.tests.test_admin_merge")
class MergeAdminWorkflowTests(TransactionTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        post_migrate.disconnect(
            create_default_site,
            dispatch_uid="django.contrib.sites.management.create_default_site",
        )
        with connection.schema_editor() as editor:
            try:
                editor.create_model(Site)
            except Exception:
                # Table may already exist when migrations have been applied.
                pass

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        call_command("migrate", "sites", verbosity=0)
        if not Site.objects.filter(pk=1).exists():
            Site.objects.create(pk=1, domain="example.com", name="example.com")

    def setUp(self):
        super().setUp()
        with connection.schema_editor() as editor:
            try:
                editor.create_model(Site)
            except Exception:
                pass
        if not Site.objects.filter(pk=1).exists():
            Site.objects.create(pk=1, domain="example.com", name="example.com")
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        core_models = [
            ContentType,
            Permission,
            Group,
            get_user_model(),
            Session,
            MergeLog,
            LogEntry,
            Site,
        ]
        existing_tables = set(connection.introspection.table_names())
        with connection.schema_editor(atomic=False) as schema_editor:
            for model in core_models:
                if model._meta.db_table not in existing_tables:
                    schema_editor.create_model(model)
                    existing_tables.add(model._meta.db_table)

        class MergeableRecord(MergeMixin):
            name = models.CharField(max_length=64)
            email = models.EmailField(blank=True)
            notes = models.TextField(blank=True)

            merge_fields = {
                "name": MergeStrategy.LAST_WRITE,
                "email": MergeStrategy.PREFER_NON_NULL,
            }

            class Meta:
                app_label = "cms"

            def __str__(self) -> str:
                return self.name

        class MergeableRecordAdmin(MergeAdminActionMixin, MergeAdminMixin, admin.ModelAdmin):
            list_display = ("name", "email")

        cls.Model = MergeableRecord
        cls.Admin = MergeableRecordAdmin

        connection.disable_constraint_checking()
        try:
            with connection.schema_editor(atomic=False) as schema_editor:
                existing_tables = connection.introspection.table_names()
                if MergeableRecord._meta.db_table in existing_tables:
                    schema_editor.delete_model(MergeableRecord)
                schema_editor.create_model(MergeableRecord)
        finally:
            connection.enable_constraint_checking()

        test_admin_site.register(MergeableRecord, MergeableRecordAdmin)

        model_admin = test_admin_site._registry[MergeableRecord]
        cls.app_label = model_admin.opts.app_label
        cls.model_name = model_admin.opts.model_name
        cls.changelist_url = f"/admin/{cls.app_label}/{cls.model_name}/"
        cls.merge_url = f"/admin/{cls.app_label}/{cls.model_name}/merge/"
        cls.admin_site = test_admin_site
        cls.model_admin = model_admin
        content_type = ContentType.objects.get_for_model(MergeableRecord)
        cls.merge_permission, _ = Permission.objects.get_or_create(
            codename="can_merge",
            name="Can merge mergeable records",
            content_type=content_type,
        )
        cls.merge_content_type_kwargs = {
            "app_label": content_type.app_label,
            "model": content_type.model,
        }
        cls.merge_content_type_name = content_type.name
        cls.UserModel = get_user_model()

    @classmethod
    def tearDownClass(cls):
        cls.admin_site.unregister(cls.Model)
        connection.disable_constraint_checking()
        try:
            with connection.schema_editor(atomic=False) as schema_editor:
                schema_editor.delete_model(cls.Model)
        finally:
            connection.enable_constraint_checking()
        super().tearDownClass()

    def setUp(self):
        self.target = self.Model.objects.create(
            name="Target",
            email="target@example.com",
            notes="Keep",
        )
        self.source = self.Model.objects.create(
            name="Source",
            email="",
            notes="",
        )

        self.model_admin = self.__class__.model_admin
        self.factory = RequestFactory()

    def _login(self, *, with_permission: bool):
        user = self.UserModel.objects.create_user(
            username=f"merge-user-{uuid4()}",
            password="pass",
            is_staff=True,
        )
        if with_permission:
            content_type, _ = ContentType.objects.get_or_create(
                defaults={"name": self.merge_content_type_name},
                **self.merge_content_type_kwargs,
            )
            permission, _ = Permission.objects.get_or_create(
                codename=self.merge_permission.codename,
                content_type=content_type,
                defaults={"name": self.merge_permission.name},
            )
            user.user_permissions.add(permission)
        return user

    def _build_request(self, method: str, path: str, *, data: dict[str, str] | None = None, user=None):
        factory = self.factory
        request = getattr(factory, method)(path, data=data or {})
        SessionMiddleware(lambda req: None).process_request(request)
        request.session.save()
        setattr(request, "_messages", FallbackStorage(request))
        request._dont_enforce_csrf_checks = True
        request.user = user
        return request

    def test_merge_action_requires_permission(self):
        user = self._login(with_permission=False)
        changelist_request = self._build_request("get", self.changelist_url, user=user)

        actions = self.model_admin.get_actions(changelist_request)
        self.assertNotIn("merge_selected", actions)

        merge_request = self._build_request(
            "get",
            f"{self.merge_url}?ids={self.target.pk},{self.source.pk}",
            user=user,
        )
        with self._override_admin_urls():
            response = self.admin_site.admin_view(self.model_admin.merge_view)(merge_request)
        self.assertEqual(response.status_code, 302)
        self.assertIn(self.changelist_url, response["Location"])

    @override_settings(MERGE_TOOL_FEATURE=True)
    def test_merge_action_redirects_with_all_selected_ids(self):
        user = self._login(with_permission=True)
        extra_source = self.Model.objects.create(
            name="Extra", email="extra@example.com", notes=""
        )

        post_data = {
            "action": "merge_selected",
            ACTION_CHECKBOX_NAME: [
                str(self.target.pk),
                str(self.source.pk),
                str(extra_source.pk),
            ],
        }
        queryset = self.Model._default_manager.filter(
            pk__in=[self.target.pk, self.source.pk, extra_source.pk]
        )
        action_request = self._build_request(
            "post", self.changelist_url, data=post_data, user=user
        )

        with self._override_admin_urls():
            response = self.model_admin.merge_selected(action_request, queryset)

        self.assertEqual(response.status_code, 302)
        parsed = parse_qs(urlparse(response["Location"]).query)
        self.assertEqual(
            parsed.get("ids"),
            ["{},{},{}".format(self.target.pk, self.source.pk, extra_source.pk)],
        )

    @override_settings(MERGE_TOOL_FEATURE=True)
    def test_admin_merge_workflow_executes_merge(self):
        user = self._login(with_permission=True)

        post_data = {
            "action": "merge_selected",
            ACTION_CHECKBOX_NAME: [str(self.target.pk), str(self.source.pk)],
        }
        queryset = self.Model._default_manager.filter(pk__in=[self.target.pk, self.source.pk])
        action_request = self._build_request("post", self.changelist_url, data=post_data, user=user)
        with self._override_admin_urls():
            response = self.model_admin.merge_selected(action_request, queryset)
        self.assertEqual(response.status_code, 302)
        self.assertIn(self.merge_url, response["Location"])

        form_data = {
            "selected_ids": f"{self.target.pk},{self.source.pk}",
            "source": str(self.source.pk),
            "target": str(self.target.pk),
            "strategy__name": MergeStrategy.LAST_WRITE.value,
            "value__name": "",
            "strategy__email": MergeStrategy.PREFER_NON_NULL.value,
            "value__email": "",
            "strategy__notes": MergeStrategy.PREFER_NON_NULL.value,
            "value__notes": "",
        }
        merge_request = self._build_request("post", self.merge_url, data=form_data, user=user)
        with self._override_admin_urls():
            response = self.admin_site.admin_view(self.model_admin.merge_view)(merge_request)
        self.assertEqual(response.status_code, 302)

        self.target.refresh_from_db()
        self.assertEqual(self.target.name, "Source")
        self.assertEqual(self.target.email, "target@example.com")

        self.assertFalse(self.Model.objects.filter(pk=self.source.pk).exists())
        self.assertTrue(MergeLog.objects.filter(target_pk=str(self.target.pk)).exists())

    @override_settings(MERGE_TOOL_FEATURE=True)
    def test_field_selection_strategy_redirects_to_per_field_flow(self):
        user = self._login(with_permission=True)

        with connection.schema_editor() as editor:
            try:
                editor.create_model(Site)
            except Exception:
                pass

        original_merge_fields = self.Model.merge_fields.copy()
        self.addCleanup(lambda: setattr(self.Model, "merge_fields", original_merge_fields))
        self.Model.merge_fields = {
            "name": MergeStrategy.FIELD_SELECTION,
            "email": MergeStrategy.PREFER_NON_NULL,
            "notes": MergeStrategy.PREFER_NON_NULL,
        }

        form_data = {
            "selected_ids": f"{self.target.pk},{self.source.pk}",
            "source": str(self.source.pk),
            "target": str(self.target.pk),
            "strategy__name": MergeStrategy.FIELD_SELECTION.value,
            "value__name": "",
            "strategy__email": MergeStrategy.PREFER_NON_NULL.value,
            "value__email": "",
            "strategy__notes": MergeStrategy.PREFER_NON_NULL.value,
            "value__notes": "",
        }

        merge_request = self._build_request("post", self.merge_url, data=form_data, user=user)

        with self._override_admin_urls(), patch("cms.merge.merge_records") as merge_records_mock:
            response = self.admin_site.admin_view(self.model_admin.merge_view)(merge_request)

        self.assertEqual(response.status_code, 302)
        self.assertIn("/merge/field-selection/", response["Location"])
        merge_records_mock.assert_not_called()

    @override_settings(MERGE_TOOL_FEATURE=True)
    def test_manual_action_prompts_for_target_selection(self):
        user = self._login(with_permission=True)

        post_data = {
            "action": "merge_records_action",
            ACTION_CHECKBOX_NAME: [str(self.target.pk), str(self.source.pk)],
        }
        queryset = self.Model._default_manager.filter(
            pk__in=[self.target.pk, self.source.pk]
        ).order_by("pk")
        action_request = self._build_request(
            "post", self.changelist_url, data=post_data, user=user
        )

        with self._override_admin_urls():
            response = self.model_admin.merge_records_action(
                action_request, queryset
            )
        self.assertIsNotNone(response)

    @override_settings(MERGE_TOOL_FEATURE=True)
    def test_merge_view_includes_field_selection_help(self):
        user = self._login(with_permission=True)
        request = self._build_request(
            "get",
            f"{self.merge_url}?ids={self.target.pk},{self.source.pk}",
            user=user,
        )

        with self._override_admin_urls():
            response = self.admin_site.admin_view(self.model_admin.merge_view)(request)

        self.assertEqual(response.status_code, 200)
        with self._override_admin_urls():
            self.model_admin.is_merge_tool_enabled = lambda *args, **kwargs: True
            merge_fields = self.model_admin.get_mergeable_fields()
            form = self.model_admin.merge_form_class(
                model=self.Model,
                merge_fields=merge_fields,
                initial={
                    "selected_ids": f"{self.target.pk},{self.source.pk}",
                    "source": str(self.source.pk),
                    "target": str(self.target.pk),
                },
            )
            context = self.model_admin._build_merge_context(
                request,
                form=form,
                selected_ids=[str(self.target.pk), str(self.source.pk)],
                source_obj=form.get_bound_instance("source"),
                target_obj=form.get_bound_instance("target"),
                merge_fields=merge_fields,
            )
        self.assertIn("/merge/field-selection/", context.get("field_selection_url", ""))

    @override_settings(MERGE_TOOL_FEATURE=True)
    def test_merge_form_normalises_selected_ids_and_requires_distinct_records(self):
        merge_fields = self.model_admin.get_mergeable_fields()
        form = self.model_admin.merge_form_class(
            model=self.Model,
            merge_fields=merge_fields,
            data={
                "selected_ids": f"{self.target.pk},{self.source.pk},{self.target.pk}",
                "source": str(self.source.pk),
                "target": str(self.target.pk),
                "strategy__name": MergeStrategy.LAST_WRITE.value,
                "value__name": "",
                "strategy__email": MergeStrategy.PREFER_NON_NULL.value,
                "value__email": "",
                "strategy__notes": MergeStrategy.PREFER_NON_NULL.value,
                "value__notes": "",
            },
        )

        self.assertTrue(form.is_valid())
        self.assertEqual(form.selected_ids, [str(self.target.pk), str(self.source.pk)])

    @override_settings(MERGE_TOOL_FEATURE=True)
    def test_field_selection_payload_uses_normalised_selected_ids(self):
        user = self._login(with_permission=True)

        original_merge_fields = self.Model.merge_fields.copy()
        self.addCleanup(lambda: setattr(self.Model, "merge_fields", original_merge_fields))
        self.Model.merge_fields = {
            "name": MergeStrategy.FIELD_SELECTION,
            "email": MergeStrategy.PREFER_NON_NULL,
            "notes": MergeStrategy.PREFER_NON_NULL,
        }

        form_data = {
            "selected_ids": f"{self.source.pk},{self.target.pk},{self.source.pk}",
            "source": str(self.source.pk),
            "target": str(self.target.pk),
            "strategy__name": MergeStrategy.FIELD_SELECTION.value,
            "value__name": "",
            "strategy__email": MergeStrategy.PREFER_NON_NULL.value,
            "value__email": "",
            "strategy__notes": MergeStrategy.PREFER_NON_NULL.value,
            "value__notes": "",
        }

        merge_request = self._build_request("post", self.merge_url, data=form_data, user=user)

        with self._override_admin_urls(), patch("cms.merge.merge_records") as merge_records_mock:
            response = self.admin_site.admin_view(self.model_admin.merge_view)(merge_request)

        self.assertEqual(response.status_code, 302)
        self.assertIn("/merge/field-selection/", response["Location"])
        query = parse_qs(urlparse(response["Location"]).query)
        self.assertEqual(
            query.get("candidates"),
            [f"{self.target.pk},{self.source.pk}"],
        )
        self.assertEqual(query.get("target"), [str(self.target.pk)])
        merge_records_mock.assert_not_called()

    @override_settings(MERGE_TOOL_FEATURE=True)
    def test_field_selection_redirect_includes_all_candidates(self):
        user = self._login(with_permission=True)
        extra_source = self.Model.objects.create(
            name="Extra", email="extra@example.com", notes=""
        )

        original_merge_fields = self.Model.merge_fields.copy()
        self.addCleanup(lambda: setattr(self.Model, "merge_fields", original_merge_fields))
        self.Model.merge_fields = {
            "name": MergeStrategy.FIELD_SELECTION,
            "email": MergeStrategy.PREFER_NON_NULL,
            "notes": MergeStrategy.PREFER_NON_NULL,
        }

        form_data = {
            "selected_ids": f"{self.target.pk},{self.source.pk},{extra_source.pk}",
            "source": str(self.source.pk),
            "target": str(self.target.pk),
            "strategy__name": MergeStrategy.FIELD_SELECTION.value,
            "value__name": "",
            "strategy__email": MergeStrategy.PREFER_NON_NULL.value,
            "value__email": "",
            "strategy__notes": MergeStrategy.PREFER_NON_NULL.value,
            "value__notes": "",
        }

        merge_request = self._build_request("post", self.merge_url, data=form_data, user=user)

        with self._override_admin_urls(), patch("cms.merge.merge_records") as merge_records_mock:
            response = self.admin_site.admin_view(self.model_admin.merge_view)(merge_request)

        self.assertEqual(response.status_code, 302)
        query = parse_qs(urlparse(response["Location"]).query)
        self.assertEqual(
            query.get("candidates"),
            [f"{self.target.pk},{self.source.pk},{extra_source.pk}"],
        )
        self.assertEqual(query.get("target"), [str(self.target.pk)])
        merge_records_mock.assert_not_called()

    @override_settings(MERGE_TOOL_FEATURE=True)
    def test_admin_merge_handles_multiple_sources(self):
        user = self._login(with_permission=True)
        extra_source = self.Model.objects.create(
            name="Extra Source",
            email="extra@example.com",
            notes="Extra notes",
        )

        form_data = {
            "selected_ids": f"{self.target.pk},{self.source.pk},{extra_source.pk}",
            "source": str(self.source.pk),
            "target": str(self.target.pk),
            "strategy__name": MergeStrategy.LAST_WRITE.value,
            "value__name": "",
            "strategy__email": MergeStrategy.LAST_WRITE.value,
            "value__email": "",
            "strategy__notes": MergeStrategy.LAST_WRITE.value,
            "value__notes": "",
        }

        merge_request = self._build_request("post", self.merge_url, data=form_data, user=user)
        with self._override_admin_urls():
            response = self.admin_site.admin_view(self.model_admin.merge_view)(merge_request)

        self.assertEqual(response.status_code, 302)

        self.target.refresh_from_db()
        self.assertEqual(self.target.name, "Extra Source")
        self.assertEqual(self.target.email, "extra@example.com")
        self.assertEqual(self.target.notes, "Extra notes")
        self.assertEqual(self.Model.objects.count(), 1)
        self.assertEqual(
            MergeLog.objects.filter(target_pk=str(self.target.pk)).count(),
            2,
        )

    @override_settings(MERGE_TOOL_FEATURE=True)
    def test_admin_merge_logs_each_source_with_snapshots(self):
        user = self._login(with_permission=True)
        extra_source = self.Model.objects.create(
            name="Extra Source",
            email="extra@example.com",
            notes="Extra notes",
        )

        form_data = {
            "selected_ids": f"{self.target.pk},{self.source.pk},{extra_source.pk}",
            "source": str(self.source.pk),
            "target": str(self.target.pk),
            "strategy__name": MergeStrategy.LAST_WRITE.value,
            "value__name": "",
            "strategy__email": MergeStrategy.LAST_WRITE.value,
            "value__email": "",
            "strategy__notes": MergeStrategy.LAST_WRITE.value,
            "value__notes": "",
        }

        merge_request = self._build_request("post", self.merge_url, data=form_data, user=user)
        with self._override_admin_urls():
            response = self.admin_site.admin_view(self.model_admin.merge_view)(merge_request)

        self.assertEqual(response.status_code, 302)

        log_entries = MergeLog.objects.filter(target_pk=str(self.target.pk)).order_by(
            "executed_at"
        )
        self.assertEqual(log_entries.count(), 2)
        self.assertEqual(
            {entry.source_pk for entry in log_entries},
            {str(self.source.pk), str(extra_source.pk)},
        )
        for entry in log_entries:
            self.assertIsNotNone(entry.source_snapshot)
            self.assertTrue(entry.resolved_values.get("fields"))
            self.assertEqual(entry.target_pk, str(self.target.pk))

    @override_settings(MERGE_TOOL_FEATURE=True)
    def test_merge_view_rejects_multi_source_post_without_permission(self):
        user = self._login(with_permission=False)
        extra_source = self.Model.objects.create(
            name="Extra", email="extra@example.com", notes=""
        )

        form_data = {
            "selected_ids": f"{self.target.pk},{self.source.pk},{extra_source.pk}",
            "source": str(self.source.pk),
            "target": str(self.target.pk),
            "strategy__name": MergeStrategy.LAST_WRITE.value,
            "value__name": "",
            "strategy__email": MergeStrategy.LAST_WRITE.value,
            "value__email": "",
            "strategy__notes": MergeStrategy.LAST_WRITE.value,
            "value__notes": "",
        }

        merge_request = self._build_request("post", self.merge_url, data=form_data, user=user)

        with self._override_admin_urls():
            response = self.admin_site.admin_view(self.model_admin.merge_view)(merge_request)

        self.assertEqual(response.status_code, 302)
        self.assertIn(self.changelist_url, response["Location"])
        self.assertEqual(self.Model.objects.count(), 3)
        self.assertFalse(MergeLog.objects.exists())

    @override_settings(MERGE_TOOL_FEATURE=True)
    def test_admin_merge_archives_each_source(self):
        user = self._login(with_permission=True)
        extra_source = self.Model.objects.create(
            name="Extra Source",
            email="extra@example.com",
            notes="Extra notes",
        )

        form_data = {
            "selected_ids": f"{self.target.pk},{self.source.pk},{extra_source.pk}",
            "source": str(self.source.pk),
            "target": str(self.target.pk),
            "strategy__name": MergeStrategy.LAST_WRITE.value,
            "value__name": "",
            "strategy__email": MergeStrategy.LAST_WRITE.value,
            "value__email": "",
            "strategy__notes": MergeStrategy.LAST_WRITE.value,
            "value__notes": "",
        }

        merge_request = self._build_request("post", self.merge_url, data=form_data, user=user)

        archived_sources: list[int | None] = []

        def _record_archive(_self, source_instance):
            archived_sources.append(getattr(source_instance, "pk", None))

        with self._override_admin_urls(), patch.object(
            self.Model, "archive_source_instance", autospec=True, side_effect=_record_archive
        ) as archive_mock:
            response = self.admin_site.admin_view(self.model_admin.merge_view)(merge_request)

        self.assertEqual(response.status_code, 302)
        self.assertEqual(archive_mock.call_count, 2)
        self.assertEqual(set(archived_sources), {self.source.pk, extra_source.pk})

    @override_settings(MERGE_TOOL_FEATURE=True)
    def test_admin_merge_stops_processing_after_failure(self):
        user = self._login(with_permission=True)
        failing_source = self.Model.objects.create(
            name="Failing", email="fail@example.com", notes=""
        )

        form_data = {
            "selected_ids": f"{self.target.pk},{self.source.pk},{failing_source.pk}",
            "source": str(self.source.pk),
            "target": str(self.target.pk),
            "strategy__name": MergeStrategy.LAST_WRITE.value,
            "value__name": "",
            "strategy__email": MergeStrategy.LAST_WRITE.value,
            "value__email": "",
            "strategy__notes": MergeStrategy.LAST_WRITE.value,
            "value__notes": "",
        }

        original_merge = admin_merge.merge_records

        call_counter = {"index": 0}

        def _merge_with_failure(source, target, strategy_map, user=None, archive=True):
            if call_counter["index"] == 0:
                call_counter["index"] += 1
                return original_merge(source, target, strategy_map, user=user, archive=archive)
            raise RuntimeError("boom")

        merge_request = self._build_request("post", self.merge_url, data=form_data, user=user)

        with self._override_admin_urls(), patch(
            "cms.admin_merge.merge_records", side_effect=_merge_with_failure
        ) as merge_mock:
            response = self.admin_site.admin_view(self.model_admin.merge_view)(merge_request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(merge_mock.call_count, 2)
        self.assertTrue(
            any("Merge failed" in str(message) for message in merge_request._messages)
        )
        self.target.refresh_from_db()
        self.assertEqual(self.target.name, "Source")
        self.assertTrue(self.Model.objects.filter(pk=failing_source.pk).exists())
        self.assertEqual(MergeLog.objects.filter(target_pk=str(self.target.pk)).count(), 1)
    @contextmanager
    def _override_admin_urls(self):
        def resolve(name, *args, **kwargs):
            if name == f"admin:{self.app_label}_{self.model_name}_merge":
                return self.merge_url
            if name == f"admin:{self.app_label}_{self.model_name}_changelist":
                return self.changelist_url
            if name == f"admin:{self.app_label}_{self.model_name}_change":
                object_id = None
                if args:
                    object_id = args[0]
                else:
                    object_id = kwargs.get("object_id") or kwargs.get("pk")
                return f"/admin/{self.app_label}/{self.model_name}/{object_id}/change/"
            if name == "admin:app_list":
                return "/admin/app_list/"
            if name == "merge:merge_candidate_search":
                return "/merge/search/"
            if name == "merge:merge_field_selection":
                return "/merge/field-selection/"
            return name

        with patch("cms.admin.reverse", side_effect=resolve), patch(
            "cms.admin_merge.reverse", side_effect=resolve
        ) as mock_reverse, patch(
            "cms.admin_merge.redirect",
            side_effect=lambda to, *args, **kwargs: HttpResponseRedirect(
                resolve(to, *args, **kwargs) if isinstance(to, str) else to
            ),
        ):
            yield mock_reverse


@override_settings(MERGE_TOOL_FEATURE=True)
class FieldSelectionAdminActionRedirectTests(TransactionTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

        cls.factory = RequestFactory()
        cls.admin_site = admin.site

        existing_tables = set(connection.introspection.table_names())
        if Site._meta.db_table not in existing_tables:
            call_command("migrate", "sites", verbosity=0)

        core_models = [
            ContentType,
            Permission,
            Group,
            get_user_model(),
            Session,
            MergeLog,
            LogEntry,
        ]
        existing_tables = set(connection.introspection.table_names())
        with connection.schema_editor(atomic=False) as schema_editor:
            for model in core_models:
                if model._meta.db_table not in existing_tables:
                    schema_editor.create_model(model)
                    existing_tables.add(model._meta.db_table)

            for model in (
                cms_models.FieldSlip,
                cms_models.FieldSlip.history.model,
                cms_models.Storage,
                cms_models.Storage.history.model,
                cms_models.Reference,
                cms_models.Reference.history.model,
            ):
                if model._meta.db_table not in existing_tables:
                    schema_editor.create_model(model)
                    existing_tables.add(model._meta.db_table)

    def setUp(self):
        super().setUp()
        self.user = get_user_model().objects.create_user(
            username=f"merge-user-{uuid4()}", email="merge@example.com", password="pass"
        )
        for model in (cms_models.FieldSlip, cms_models.Storage, cms_models.Reference):
            content_type = ContentType.objects.get_for_model(model)
            permission, _ = Permission.objects.get_or_create(
                codename="can_merge",
                content_type=content_type,
                defaults={"name": "Can merge records"},
            )
            self.user.user_permissions.add(permission)

    def tearDown(self):
        set_current_user(None)
        super().tearDown()

    def _build_request(self, method: str, path: str, *, data=None, user=None):
        request = getattr(self.factory, method)(path, data=data or {})
        SessionMiddleware(lambda req: None).process_request(request)
        request.session.save()
        setattr(request, "_messages", FallbackStorage(request))
        request._dont_enforce_csrf_checks = True
        request.user = user
        return request

    @contextmanager
    def _override_admin_urls(self, model):
        app_label = model._meta.app_label
        model_name = model._meta.model_name

        def resolve(name, *args, **kwargs):
            if name == f"admin:{app_label}_{model_name}_changelist":
                return f"/admin/{app_label}/{model_name}/"
            if name == f"admin:{app_label}_{model_name}_merge":
                return f"/admin/{app_label}/{model_name}/merge/"
            if name == "merge:merge_field_selection":
                return "/merge/field-selection/"
            return name

        with patch("cms.admin.reverse", side_effect=resolve), patch(
            "cms.admin.redirect",
            side_effect=lambda to, *args, **kwargs: HttpResponseRedirect(
                resolve(to, *args, **kwargs) if isinstance(to, str) else to
            ),
        ):
            yield

    def _build_objects(self, model, *, required_fields):
        set_current_user(self.user)
        target = model.objects.create(**required_fields["target"])
        source = model.objects.create(**required_fields["source"])
        set_current_user(None)
        return target, source

    def _assert_field_selection_redirect(self, model, *, required_fields):
        admin_instance = self.admin_site._registry[model]
        target, source = self._build_objects(model, required_fields=required_fields)

        queryset = model._default_manager.filter(pk__in=[target.pk, source.pk]).order_by("pk")
        post_data = {
            "action": "merge_records_action",
            ACTION_CHECKBOX_NAME: [str(target.pk), str(source.pk)],
        }

        action_request = self._build_request(
            "post", f"/admin/{model._meta.app_label}/{model._meta.model_name}/", data=post_data, user=self.user
        )

        with self._override_admin_urls(model):
            response = admin_instance.merge_records_action(action_request, queryset)

        self.assertEqual(response.status_code, 200)
        self.assertIn("Field selection is required", response.content.decode())

        confirm_data = {
            "action": "merge_records_action",
            ACTION_CHECKBOX_NAME: [str(target.pk), str(source.pk)],
            "merge_confirmed": "yes",
            "merge_target": str(target.pk),
        }
        confirm_request = self._build_request(
            "post",
            f"/admin/{model._meta.app_label}/{model._meta.model_name}/",
            data=confirm_data,
            user=self.user,
        )

        with self._override_admin_urls(model), patch("cms.merge.merge_records") as merge_mock:
            response = admin_instance.merge_records_action(confirm_request, queryset)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/merge/field-selection/", response["Location"])
        merge_mock.assert_not_called()

    def test_field_selection_models_redirect_before_merge(self):
        test_matrix = [
            (
                cms_models.FieldSlip,
                {
                    "target": {
                        "field_number": "FS-001",
                        "verbatim_taxon": "Target taxon",
                        "verbatim_element": "Target element",
                    },
                    "source": {
                        "field_number": "FS-002",
                        "verbatim_taxon": "Source taxon",
                        "verbatim_element": "Source element",
                    },
                },
            ),
            (
                cms_models.Storage,
                {
                    "target": {"area": "Area A"},
                    "source": {"area": "Area B"},
                },
            ),
            (
                cms_models.Reference,
                {
                    "target": {
                        "title": "Target title",
                        "citation": "Target citation",
                        "first_author": "Author",
                        "year": "2024",
                    },
                    "source": {
                        "title": "Source title",
                        "citation": "Source citation",
                        "first_author": "Author",
                        "year": "2023",
                    },
                },
            ),
        ]

        for model, required_fields in test_matrix:
            with self.subTest(model=model.__name__):
                self._assert_field_selection_redirect(model, required_fields=required_fields)
