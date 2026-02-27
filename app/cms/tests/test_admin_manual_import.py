import os

import django
import pytest
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory

from cms.admin import (
    AccessionAdmin,
    AccessionManualImportFilter,
    ManualImportMediaFilter,
    MediaAdmin,
)
from cms.forms import ensure_manual_qc_permission
from cms.manual_import import import_manual_row
from cms.models import Accession, Collection, Locality, Media

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings_test")
os.environ.setdefault("DB_ENGINE", "django.db.backends.sqlite3")
django.setup()

pytestmark = pytest.mark.django_db


@pytest.fixture()
def staff_user():
    user_model = get_user_model()
    user, _ = user_model.objects.get_or_create(
        username="manual_admin",
        defaults={"email": "manual@example.com", "is_staff": True},
    )
    permission = ensure_manual_qc_permission()
    user.user_permissions.add(permission)
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    return user


@pytest.fixture()
def basic_user():
    user_model = get_user_model()
    user, _ = user_model.objects.get_or_create(
        username="basic_admin",
        defaults={"email": "basic@example.com", "is_staff": True},
    )
    return user


@pytest.fixture()
def request_factory():
    return RequestFactory()


@pytest.fixture()
def collection():
    collection, _ = Collection.objects.get_or_create(
        abbreviation="KNM",
        defaults={"description": "National Museums of Kenya"},
    )
    return collection


@pytest.fixture()
def locality():
    locality, _ = Locality.objects.get_or_create(
        abbreviation="ER",
        defaults={"name": "Koobi Fora"},
    )
    return locality


@pytest.fixture(autouse=True)
def _force_current_user(monkeypatch, staff_user):
    monkeypatch.setattr("cms.models.get_current_user", lambda: staff_user)
    return staff_user


def test_media_manual_import_properties():
    media = Media.objects.create(
        media_location="uploads/manual-meta.jpg",
        file_name="manual-meta.jpg",
        ocr_data={
            "_manual_import": {
                "source": "manual_qc",
                "row_id": "row-42",
                "created_by": "manual_admin",
                "created_on": "2024-02-01",
            }
        },
    )

    metadata = media.get_manual_import_metadata()
    assert metadata is not None
    assert media.is_manual_import is True
    assert media.manual_import_display() == "row-42 — manual_admin"


def test_media_admin_permissions_toggle_columns(request_factory, staff_user, basic_user):
    Media.objects.all().delete()
    manual_media = Media.objects.create(
        media_location="uploads/manual-column.jpg",
        file_name="manual-column.jpg",
        ocr_data={"_manual_import": {"source": "manual_qc", "row_id": "99"}},
    )
    Media.objects.create(media_location="uploads/regular.jpg", file_name="regular.jpg")

    media_admin = MediaAdmin(Media, admin.site)

    staff_request = request_factory.get("/admin/cms/media/")
    staff_request.user = staff_user
    staff_columns = media_admin.get_list_display(staff_request)
    assert "manual_import_badge" in staff_columns

    basic_request = request_factory.get("/admin/cms/media/")
    basic_request.user = basic_user
    basic_columns = media_admin.get_list_display(basic_request)
    assert "manual_import_badge" not in basic_columns

    staff_filter_request = request_factory.get("/admin/cms/media/", {"manual_import": "manual"})
    staff_filter_request.user = staff_user
    media_filter = ManualImportMediaFilter(
        staff_filter_request,
        staff_filter_request.GET.copy(),
        Media,
        media_admin,
    )
    filtered = media_filter.queryset(staff_filter_request, Media.objects.all())
    assert list(filtered) == [manual_media]




def test_media_admin_exposes_location_for_operator_visibility(request_factory, staff_user):
    media_admin = MediaAdmin(Media, admin.site)
    request = request_factory.get("/admin/cms/media/")
    request.user = staff_user

    list_display = media_admin.get_list_display(request)
    assert "media_location" in list_display
    assert "media_location" in media_admin.search_fields

def test_accession_admin_badge_and_filter(collection, locality, request_factory, staff_user, basic_user):
    Media.objects.all().delete()
    Accession.objects.all().delete()
    accession = Accession.objects.create(
        collection=collection,
        specimen_prefix=locality,
        specimen_no=101,
    )
    Media.objects.create(
        accession=accession,
        media_location="uploads/manual-accession.jpg",
        file_name="manual-accession.jpg",
        ocr_data={
            "_manual_import": {
                "source": "manual_qc",
                "row_id": "acc-101",
                "created_by": "manual_admin",
            }
        },
    )
    other_accession = Accession.objects.create(
        collection=collection,
        specimen_prefix=locality,
        specimen_no=102,
    )
    accession_admin = AccessionAdmin(Accession, admin.site)

    assert accession.is_manual_import is True
    assert other_accession.is_manual_import is False

    staff_request = request_factory.get("/admin/cms/accession/")
    staff_request.user = staff_user
    staff_columns = accession_admin.get_list_display(staff_request)
    assert "manual_import_badge" in staff_columns

    basic_request = request_factory.get("/admin/cms/accession/")
    basic_request.user = basic_user
    basic_columns = accession_admin.get_list_display(basic_request)
    assert "manual_import_badge" not in basic_columns

    staff_filter_request = request_factory.get("/admin/cms/accession/", {"manual_import": "manual"})
    staff_filter_request.user = staff_user
    accession_filter = AccessionManualImportFilter(
        staff_filter_request,
        staff_filter_request.GET.copy(),
        Accession,
        accession_admin,
    )
    filtered = accession_filter.queryset(staff_filter_request, Accession.objects.order_by("pk"))
    assert list(filtered) == [accession]


def test_manual_import_history_tracks_metadata(collection, locality, staff_user, monkeypatch):
    media = Media.objects.create(
        media_location="uploads/history-1.jpg",
        file_name="history-1.jpg",
    )

    accession = Accession.objects.create(
        collection=collection,
        specimen_prefix=locality,
        specimen_no=999,
        is_published=False,
    )

    def _fake_create(media_obj, **kwargs):
        return {"created": [{"accession_id": accession.pk}]}

    monkeypatch.setattr("cms.manual_import.create_accessions_from_media", _fake_create)

    row = {
        "id": "history-1",
        "collection_id": collection.abbreviation,
        "accession_number": "ER 999",
        "shelf": "Drawer",
        "taxon": "Test taxon",
        "body_parts": "Femur",
        "is_published": "No",
        "created_by": staff_user.username,
        "created_on": "2024-02-01T12:00:00",
    }

    import_manual_row(row, queryset=Media.objects.filter(pk=media.pk))

    media.refresh_from_db()
    history = media.history.latest()
    assert history.expert_checked_by_id == staff_user.pk
    assert history.expert_checked_on.date().isoformat() == "2024-02-01"
    assert media.is_manual_import is True
