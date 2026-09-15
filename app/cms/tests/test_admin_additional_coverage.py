from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest
from crum import set_current_user
from django.contrib import admin, messages
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.messages.storage.fallback import FallbackStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.http import HttpResponse
from django.test import RequestFactory
from django.urls import reverse

from cms import admin as cms_admin
from cms.models import SpecimenListPDF, Taxon

pytestmark = pytest.mark.django_db


def _attach_messages(request):
    setattr(request, "session", {})
    setattr(request, "_messages", FallbackStorage(request))


def _staff_user():
    user = get_user_model().objects.create_user(username="staff", password="x", is_staff=True)
    return user


def _superuser():
    return get_user_model().objects.create_superuser(username="admin", email="a@example.com", password="x")


def test_taxonomy_sync_preview_requires_permission():
    request = RequestFactory().get("/admin/taxonomy/sync/preview/")
    request.user = _staff_user()
    _attach_messages(request)

    with pytest.raises(Exception):
        cms_admin._taxonomy_sync_preview_view(request)


def test_taxonomy_sync_preview_success_renders_template(monkeypatch):
    user = _superuser()
    request = RequestFactory().get("/admin/taxonomy/sync/preview/")
    request.user = user
    _attach_messages(request)

    preview = SimpleNamespace(
        accepted_to_create=[],
        accepted_to_update=[],
        synonyms_to_create=[],
        synonyms_to_update=[],
        to_deactivate=[],
        issues=[],
        counts={"created": 1},
        source_version="v1",
    )

    monkeypatch.setattr(cms_admin.admin.site, "each_context", lambda _req: {"site_title": "x"})
    with patch("cms.admin.NowTaxonomySyncService") as service_cls:
        service_cls.return_value.preview.return_value = preview
        response = cms_admin._taxonomy_sync_preview_view(request)

    assert response.status_code == 200
    assert response.template_name == "admin/taxonomy/sync_preview.html"


def test_taxonomy_sync_apply_get_redirects_preview(monkeypatch):
    user = _superuser()
    request = RequestFactory().get("/admin/taxonomy/sync/apply/")
    request.user = user
    _attach_messages(request)

    response = cms_admin._taxonomy_sync_apply_view(request)
    assert response.status_code == 302


@pytest.mark.parametrize("button,method_name", [("_start_split", "can_split"), ("_requeue_pages", "can_requeue")])
def test_specimen_list_pdf_admin_post_buttons_queue_jobs(button, method_name, monkeypatch):
    user = _superuser()
    set_current_user(user)
    pdf = SpecimenListPDF.objects.create(
        source_label="Batch",
        original_filename="batch.pdf",
        stored_file=SimpleUploadedFile("batch.pdf", b"%PDF-1.4", content_type="application/pdf"),
    )

    request = RequestFactory().post(f"/admin/cms/specimenlistpdf/{pdf.pk}/change/", data={button: "1"})
    request.user = user
    _attach_messages(request)

    admin_instance = cms_admin.SpecimenListPDFAdmin(SpecimenListPDF, admin.site)
    monkeypatch.setattr(admin_instance, "has_change_permission", lambda *_args, **_kwargs: True)
    mock_pdf = Mock(spec=SpecimenListPDF)
    setattr(mock_pdf, method_name, lambda: True)
    monkeypatch.setattr(admin_instance, "get_object", lambda *_args, **_kwargs: mock_pdf)

    with patch("cms.admin.queue_specimen_list_processing") as queue_mock:
        response = admin_instance.changeform_view(request, object_id=str(pdf.pk))

    assert response.status_code == 302
    queue_mock.assert_called_once()


def test_flat_file_import_post_success_redirects(monkeypatch):
    user = _staff_user()
    request = RequestFactory().post("/admin/import/flat-file/", data={})
    request.user = user
    request.FILES["import_file"] = SimpleUploadedFile("x.csv", b"a,b\n1,2\n", content_type="text/csv")
    _attach_messages(request)

    monkeypatch.setattr(cms_admin.admin.site, "each_context", lambda _req: {})
    with patch("cms.admin.import_flat_file", return_value=3):
        response = cms_admin.flat_file_import_view(request)

    assert response.status_code == 302


def test_flat_file_import_post_failure_renders_form(monkeypatch):
    user = _staff_user()
    request = RequestFactory().post("/admin/import/flat-file/", data={})
    request.user = user
    request.FILES["import_file"] = SimpleUploadedFile("x.csv", b"a,b\n1,2\n", content_type="text/csv")
    _attach_messages(request)

    monkeypatch.setattr(cms_admin.admin.site, "each_context", lambda _req: {})
    with patch("cms.admin.import_flat_file", side_effect=RuntimeError("boom")):
        response = cms_admin.flat_file_import_view(request)

    assert response.status_code == 200
    assert "Flat File Import" in response.rendered_content
