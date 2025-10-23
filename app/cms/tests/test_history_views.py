import pytest
from django.contrib.auth.models import Group
from django.urls import reverse

from app.cms.models import Media, MediaQCLog, Storage

pytestmark = pytest.mark.django_db


def _create_storage_with_history(monkeypatch, user):
    monkeypatch.setattr("app.cms.models.get_current_user", lambda: user)
    storage = Storage.objects.create(area="Vault A")
    storage.area = "Vault B"
    storage.save()
    return storage


@pytest.fixture
def collection_manager(django_user_model):
    user = django_user_model.objects.create_user(username="manager", password="pass")
    group, _ = Group.objects.get_or_create(name="Collection Managers")
    group.user_set.add(user)
    return user


def test_storage_history_requires_collection_manager(client, django_user_model, collection_manager, monkeypatch):
    storage = _create_storage_with_history(monkeypatch, collection_manager)
    viewer = django_user_model.objects.create_user(username="viewer", password="pass")
    client.force_login(viewer)
    response = client.get(reverse("storage_detail", args=[storage.pk]))
    assert response.status_code == 403


def test_storage_history_renders_shared_table(client, collection_manager, monkeypatch):
    storage = _create_storage_with_history(monkeypatch, collection_manager)
    client.force_login(collection_manager)
    response = client.get(reverse("storage_detail", args=[storage.pk]))
    html = response.content.decode()
    assert response.status_code == 200
    assert "w3-table-all" in html
    assert "fa-solid fa-pen-to-square" in html or "fa-solid fa-circle-plus" in html
    assert "Vault B" in html


@pytest.fixture
def staff_user(django_user_model):
    return django_user_model.objects.create_user(username="staff", password="pass", is_staff=True)


def _create_qc_logs(monkeypatch, staff):
    monkeypatch.setattr("app.cms.models.get_current_user", lambda: staff)
    media = Media.objects.create(media_location="uploads/history.png", file_name="history.png")
    MediaQCLog.objects.create(
        media=media,
        change_type=MediaQCLog.ChangeType.STATUS,
        field_name="qc_status",
        old_value={"qc_status": "pending_intern"},
        new_value={"qc_status": "pending_expert"},
        description="Status updated",
        changed_by=staff,
    )
    MediaQCLog.objects.create(
        media=media,
        change_type=MediaQCLog.ChangeType.OCR_DATA,
        description="OCR refreshed",
        changed_by=staff,
    )
    return media


def test_media_qc_history_requires_staff(client, django_user_model):
    user = django_user_model.objects.create_user(username="user", password="pass")
    client.force_login(user)
    response = client.get(reverse("media_qc_history"))
    assert response.status_code == 403


def test_media_qc_history_filters_and_layout(client, staff_user, monkeypatch):
    media = _create_qc_logs(monkeypatch, staff_user)
    client.force_login(staff_user)

    response = client.get(reverse("media_qc_history"))
    html = response.content.decode()
    assert response.status_code == 200
    assert "w3-table-all" in html
    assert "fa-solid fa-clock-rotate-left" in html
    assert "Status updated" in html

    filtered = client.get(
        reverse("media_qc_history"),
        {"change_type": MediaQCLog.ChangeType.STATUS, "media": str(media.uuid)},
    )
    filtered_html = filtered.content.decode()
    assert filtered.status_code == 200
    assert "Status updated" in filtered_html
    assert "OCR refreshed" not in filtered_html
    assert f'value="{MediaQCLog.ChangeType.STATUS}" selected' in filtered_html
