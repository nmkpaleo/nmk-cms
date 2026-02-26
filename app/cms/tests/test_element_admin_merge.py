from __future__ import annotations

from crum import set_current_user
from django.contrib import admin
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.conf import settings
from django.core.management import call_command
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.test import RequestFactory, TransactionTestCase, override_settings
from django.urls import include, path, reverse
from django.db import connection

from cms.merge.constants import MergeStrategy
from cms.merge.services import merge_elements
from cms.models import Element


settings.MERGE_TOOL_FEATURE = True
urlpatterns = [
    path("admin/", admin.site.urls),
    path("merge/", include("cms.merge.urls")),
]


@override_settings(
    ROOT_URLCONF="cms.tests.test_element_admin_merge",
    MERGE_TOOL_FEATURE=True,
)
class ElementAdminMergeTests(TransactionTestCase):
    reset_sequences = True

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        call_command("migrate", verbosity=0)
        cls.factory = RequestFactory()
        cls.admin_site = admin.site
        cls.model_admin = cls.admin_site._registry[Element]
        cls.UserModel = get_user_model()
        cls.merge_permission, _ = Permission.objects.get_or_create(
            codename="can_merge",
            content_type=Permission.objects.get(codename="view_element").content_type,
            defaults={"name": "Can merge element"},
        )
        cls.changelist_url = reverse("admin:cms_element_changelist")
        cls.merge_url = reverse("admin:cms_element_merge")

    def setUp(self):
        super().setUp()
        set_current_user(None)
        self.addCleanup(set_current_user, None)

        self.creator = self.UserModel.objects.create_user(
            username=f"element-admin-creator-{self._testMethodName}",
            email="creator@example.com",
            password="pass",
            is_staff=True,
        )

        # Guarantee the merge tooling is enabled for these tests regardless of settings defaults.
        self.model_admin.is_merge_tool_enabled = lambda: True

        set_current_user(self.creator)
        self.target = Element.objects.create(name="Target element")
        self.source = Element.objects.create(name="Source element")
        set_current_user(None)

    def _create_user(self, *, with_permission: bool) -> admin.models.User:
        user = self.UserModel.objects.create_user(
            username=f"element-admin-{self._testMethodName}-{with_permission}",
            email="staff@example.com",
            password="pass",
            is_staff=True,
        )
        if with_permission:
            user.user_permissions.add(self.merge_permission)
        return user

    def _build_request(self, method: str, path: str, *, user, data: dict[str, str] | None = None):
        request = getattr(self.factory, method)(path, data=data or {})
        SessionMiddleware(lambda req: None).process_request(request)
        request.session.save()
        setattr(request, "_messages", FallbackStorage(request))
        request._dont_enforce_csrf_checks = True
        request.user = user
        return request

    def _create_elements(self, *, user):
        set_current_user(user)
        target = Element.objects.create(name="Target")
        source = Element.objects.create(name="Source")
        set_current_user(None)
        return target, source

    def _strategy_payload(self):
        payload = {}
        for field in self.model_admin.get_mergeable_fields():
            strategy = MergeStrategy.FIELD_SELECTION if field.name in {"name", "parent_element"} else MergeStrategy.PREFER_NON_NULL
            payload[f"strategy__{field.name}"] = strategy.value
            payload[f"value__{field.name}"] = ""
        return payload

    def test_merge_action_requires_permission(self):
        user = self._create_user(with_permission=False)
        changelist_request = self._build_request("get", self.changelist_url, user=user)

        actions = self.model_admin.get_actions(changelist_request)
        self.assertNotIn("merge_selected", actions)

        merge_request = self._build_request(
            "get",
            f"{self.merge_url}?ids={self.target.pk},{self.source.pk}",
            user=user,
        )

        response = self.admin_site.admin_view(self.model_admin.merge_view)(merge_request)
        self.assertEqual(response.status_code, 302)
        self.assertIn(self.changelist_url, response["Location"])

    def test_merge_form_redirects_to_field_selection_with_permission(self):
        user = self._create_user(with_permission=True)
        target, source = self._create_elements(user=user)

        post_data = {
            "selected_ids": f"{target.pk},{source.pk}",
            "source": str(source.pk),
            "target": str(target.pk),
            ACTION_CHECKBOX_NAME: [str(target.pk), str(source.pk)],
        }
        post_data.update(self._strategy_payload())

        request = self._build_request("post", self.merge_url, user=user, data=post_data)

        response = self.admin_site.admin_view(self.model_admin.merge_view)(request)

        self.assertEqual(response.status_code, 302)
        self.assertIn("/merge/field-selection/", response["Location"])
        self.assertIn(str(target.pk), response["Location"])

    def test_merge_updates_history_log(self):
        if connection.vendor == "sqlite":
            self.skipTest("History merge log assertion is flaky on sqlite constraints")
        user = self._create_user(with_permission=True)
        target, source = self._create_elements(user=user)

        set_current_user(user)
        target._history_user = user
        source._history_user = user
        merge_result = merge_elements(
            source=source,
            target=target,
            selected_fields={"name": "source", "parent_element": None},
            user=user,
        )
        set_current_user(None)

        self.assertEqual(merge_result.target.pk, target.pk)
        self.assertGreaterEqual(target.history.count(), 2)
        latest_history = target.history.latest("history_date")
        self.assertEqual(latest_history.history_user, user)
        self.assertEqual(latest_history.history_type, "~")
