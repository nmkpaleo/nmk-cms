from __future__ import annotations

from django.contrib import admin
from django.contrib.admin.helpers import ACTION_CHECKBOX_NAME
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.middleware import SessionMiddleware
from django.http import HttpResponse
import pytest
from urllib.parse import urlencode

from crum import set_current_user
from django.test import RequestFactory, TransactionTestCase, override_settings
from django.urls import include, path, reverse

from cms.merge.constants import MergeStrategy
from cms.models import Accession, AccessionReference, Collection, Locality, Reference


urlpatterns = [
    path("", include("cms.urls")),
    path("", lambda request: HttpResponse(""), name="index"),
    path("accession/", lambda request: HttpResponse(""), name="accession_list"),
    path("locality/", lambda request: HttpResponse(""), name="locality_list"),
    path("place/", lambda request: HttpResponse(""), name="place_list"),
    path("reference/", lambda request: HttpResponse(""), name="reference_list"),
    path("accounts/logout/", lambda request: HttpResponse(""), name="account_logout"),
    path("admin/", admin.site.urls),
    path("admin/upload-scan/", lambda request: HttpResponse(""), name="admin-upload-scan"),
    path("admin/do-ocr/", lambda request: HttpResponse(""), name="admin-do-ocr"),
    path("admin/chatgpt-usage/", lambda request: HttpResponse(""), name="admin-chatgpt-usage"),
    path("merge/", include("cms.merge.urls")),
]

pytestmark = pytest.mark.django_db(transaction=True)


@override_settings(
    ROOT_URLCONF="cms.tests.test_accessionreference_admin_merge",
    MERGE_TOOL_FEATURE=True,
)
class AccessionReferenceAdminMergeTests(TransactionTestCase):
    reset_sequences = False

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.factory = RequestFactory()
        cls.admin_site = admin.site
        cls.model_admin = cls.admin_site._registry[AccessionReference]
        cls.model_admin.is_merge_tool_enabled = lambda: True
        cls.admin_site._urls = None
        cls.UserModel = get_user_model()
        accession_ct = ContentType.objects.get_for_model(AccessionReference)
        cls.change_permission, _ = Permission.objects.get_or_create(
            codename="change_accessionreference",
            content_type=accession_ct,
            defaults={"name": "Can change accession reference"},
        )
        cls.changelist_url = reverse("admin:cms_accessionreference_changelist")
        opts = cls.model_admin.opts
        cls.merge_url = f"/admin/{opts.app_label}/{opts.model_name}/merge/"

    def setUp(self):
        super().setUp()
        self.creator = self.UserModel.objects.create_user(
            username=f"creator-{self._testMethodName}",
            email="creator@example.com",
            password="pass",
            is_staff=True,
        )
        set_current_user(self.creator)
        self.addCleanup(set_current_user, None)
        self.collection = Collection.objects.create(abbreviation="COLL", description="Test")
        self.locality = Locality.objects.create(abbreviation="LOC", name="Locality")
        self.accession = Accession.objects.create(
            collection=self.collection,
            specimen_prefix=self.locality,
            specimen_no=1,
        )
        self.alt_accession = Accession.objects.create(
            collection=self.collection,
            specimen_prefix=self.locality,
            specimen_no=2,
        )
        self.reference = Reference.objects.create(title="Ref A", first_author="Author", year="2024")
        self.alt_reference = Reference.objects.create(title="Ref B", first_author="Author", year="2024")
        set_current_user(None)

    def _build_request(self, method: str, path: str, *, user, data: dict[str, str] | None = None):
        request = getattr(self.factory, method)(path, data=data or {})
        SessionMiddleware(lambda req: None).process_request(request)
        request.session.save()
        setattr(request, "_messages", FallbackStorage(request))
        request._dont_enforce_csrf_checks = True
        request.user = user
        return request

    def _create_user(self, *, with_permission: bool):
        if with_permission:
            return self.UserModel.objects.create_superuser(
                username=f"accessionref-admin-{self._testMethodName}-{with_permission}",
                email="staff@example.com",
                password="pass",
            )
        return self.UserModel.objects.create_user(
            username=f"accessionref-admin-{self._testMethodName}-{with_permission}",
            email="staff@example.com",
            password="pass",
            is_staff=True,
        )

    def _create_references(self):
        set_current_user(self.creator)
        target = AccessionReference.objects.create(
            accession=self.accession,
            reference=self.reference,
            page="1",
        )
        source = AccessionReference.objects.create(
            accession=self.accession,
            reference=self.alt_reference,
            page="2",
        )
        set_current_user(None)
        return target, source

    def _merge_post_data(self, target, source, *, strategy: MergeStrategy):
        post_data = {
            "selected_ids": f"{target.pk},{source.pk}",
            "source": str(source.pk),
            "target": str(target.pk),
            ACTION_CHECKBOX_NAME: [str(target.pk), str(source.pk)],
        }
        for field in self.model_admin.get_mergeable_fields():
            post_data[f"strategy__{field.name}"] = strategy.value
            post_data[f"value__{field.name}"] = ""
        return post_data

    def test_merge_action_requires_change_permission(self):
        user = self._create_user(with_permission=False)
        changelist_request = self._build_request("get", self.changelist_url, user=user)

        actions = self.model_admin.get_actions(changelist_request)
        self.assertNotIn("merge_selected", actions)

        target, source = self._create_references()
        merge_request = self._build_request(
            "get",
            f"{self.merge_url}?ids={target.pk},{source.pk}",
            user=user,
        )

        response = self.admin_site.admin_view(self.model_admin.merge_view)(merge_request)
        self.assertEqual(response.status_code, 302)
        self.assertIn(self.changelist_url, response["Location"])

    def test_merge_view_merges_records_with_permission(self):
        user = self._create_user(with_permission=True)
        target, source = self._create_references()

        post_data = self._merge_post_data(
            target, source, strategy=MergeStrategy.PREFER_NON_NULL
        )
        request = self._build_request("post", self.merge_url, user=user, data=post_data)

        response = self.admin_site.admin_view(self.model_admin.merge_view)(request)
        messages = [str(message) for message in request._messages]

        self.assertEqual(response.status_code, 302, messages)
        self.assertIn(reverse("admin:cms_accessionreference_change", args=[target.pk]), response["Location"])
        self.assertFalse(AccessionReference.objects.filter(pk=source.pk).exists())
        target.refresh_from_db()
        self.assertEqual(target.reference, self.reference)
        self.assertEqual(target.page, "1")

    def test_merge_view_redirects_to_field_selection_by_default(self):
        user = self._create_user(with_permission=True)
        target, source = self._create_references()

        post_data = self._merge_post_data(
            target, source, strategy=MergeStrategy.FIELD_SELECTION
        )
        request = self._build_request("post", self.merge_url, user=user, data=post_data)

        response = self.admin_site.admin_view(self.model_admin.merge_view)(request)

        cancel_url = reverse("admin:cms_accessionreference_changelist")
        expected_query = urlencode(
            {
                "model": f"{AccessionReference._meta.app_label}.{AccessionReference._meta.model_name}",
                "target": target.pk,
                "candidates": f"{target.pk},{source.pk}",
                "cancel": cancel_url,
            }
        )
        expected_url = f"{reverse('merge:merge_field_selection')}?{expected_query}"

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], expected_url)
        self.assertTrue(AccessionReference.objects.filter(pk=target.pk).exists())
        self.assertTrue(AccessionReference.objects.filter(pk=source.pk).exists())

    def test_merge_view_blocks_cross_accession_merge(self):
        user = self._create_user(with_permission=True)
        target, source = self._create_references()
        set_current_user(self.creator)
        cross_source = AccessionReference.objects.create(
            accession=self.alt_accession, reference=self.reference, page="3"
        )
        set_current_user(None)

        post_data = self._merge_post_data(
            target, cross_source, strategy=MergeStrategy.LAST_WRITE
        )
        request = self._build_request("post", self.merge_url, user=user, data=post_data)

        response = self.admin_site.admin_view(self.model_admin.merge_view)(request)

        self.assertEqual(response.status_code, 200)
        messages = list(request._messages)
        self.assertTrue(any("same accession" in str(message) for message in messages))
        self.assertTrue(AccessionReference.objects.filter(pk=cross_source.pk).exists())
