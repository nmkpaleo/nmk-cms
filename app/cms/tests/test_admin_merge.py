from __future__ import annotations

from contextlib import contextmanager

from django.contrib import admin
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.contrib.admin.sites import AdminSite
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.db import connection, models
from django.http import HttpResponse, HttpResponseRedirect
from django.test import RequestFactory, TransactionTestCase, override_settings
from django.test.utils import isolate_apps
from django.urls import path
from unittest.mock import patch

from cms.admin import MergeAdminActionMixin
from cms.admin_merge import MergeAdminMixin
from cms.merge.constants import MergeStrategy
from cms.merge.mixins import MergeMixin
from cms.models import MergeLog


test_admin_site = AdminSite(name="merge-admin-test")
urlpatterns = [
    path("admin/", test_admin_site.urls),
    path("admin/upload-scan/", lambda request: HttpResponse(""), name="admin-upload-scan"),
]


@isolate_apps("cms")
@override_settings(ROOT_URLCONF="cms.tests.test_admin_merge")
class MergeAdminWorkflowTests(TransactionTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()

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
            username="merge-user" if with_permission else "limited-user",
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
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Choose a target record", response.content)
        self.assertIn(b"<th scope=\"col\">Record</th>", response.content)
        self.assertIn(b"<th scope=\"col\">Name</th>", response.content)

        confirm_data = {
            "action": "merge_records_action",
            "merge_confirmed": "yes",
            "merge_target": str(self.source.pk),
            ACTION_CHECKBOX_NAME: [str(self.target.pk), str(self.source.pk)],
        }
        confirm_request = self._build_request(
            "post", self.changelist_url, data=confirm_data, user=user
        )

        with self._override_admin_urls():
            self.model_admin.merge_records_action(confirm_request, queryset)

        self.source.refresh_from_db()
        self.assertEqual(self.source.email, "target@example.com")
        self.assertEqual(self.source.name, "Target")
        self.assertFalse(self.Model.objects.filter(pk=self.target.pk).exists())
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
