from __future__ import annotations

import uuid

import pytest
from crum import impersonate
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client
from django.urls import reverse

from cms.models import DrawerRegister, Storage


pytestmark = pytest.mark.usefixtures("django_db_setup")


def _login_collection_manager() -> tuple[Client, object]:
    username = f"manager-{uuid.uuid4().hex}"
    user = get_user_model().objects.create_user(
        username=username, email=f"{username}@example.com", password="pass"
    )
    collection_managers, _ = Group.objects.get_or_create(name="Collection Managers")
    collection_managers.user_set.add(user)
    client = Client()
    assert client.login(username=username, password="pass")
    return client, user


def test_storage_detail_includes_history_tab_and_entries():
    client, user = _login_collection_manager()
    with impersonate(user):
        storage = Storage.objects.create(area="Archive A")

    response = client.get(reverse("storage_detail", args=[storage.pk]))

    assert response.status_code == 200
    tabs = response.context["storage_tabs"]
    assert len(tabs) == 2
    history_tab = [tab for tab in tabs if tab["id"] == "storage-history"][0]
    assert history_tab["slug"] == "storage-history"
    assert history_tab["template"] == "cms/tabs/storage_history.html"

    history_entries = response.context["history_entries"]
    assert len(history_entries) >= 1

    body = response.content.decode()
    assert 'id="storage-history-tab"' in body
    assert 'data-tab-target="storage-history-panel"' in body
    assert 'id="storage-history-panel"' in body


def test_drawer_detail_includes_change_log_tab():
    client, user = _login_collection_manager()
    with impersonate(user):
        drawer = DrawerRegister.objects.create(
            code="ABC", description="Drawer description", estimated_documents=5
        )

    response = client.get(reverse("drawerregister_detail", args=[drawer.pk]))

    assert response.status_code == 200
    tabs = response.context["drawer_tabs"]
    assert len(tabs) == 2
    history_tab = [tab for tab in tabs if tab["id"] == "drawer-history"][0]
    assert history_tab["slug"] == "drawer-history"
    assert history_tab["template"] == "cms/tabs/drawerregister_history.html"

    history_entries = response.context["history_entries"]
    assert len(history_entries) >= 1

    body = response.content.decode()
    assert 'id="drawer-history-tab"' in body
    assert 'data-tab-target="drawer-history-panel"' in body
    assert 'id="drawer-history-panel"' in body
    assert "Change log" in body
