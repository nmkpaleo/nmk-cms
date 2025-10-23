import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.urls import reverse

pytestmark = pytest.mark.django_db


def _create_user_with_groups(*group_names: str):
    user_model = get_user_model()
    user = user_model.objects.create_user(
        username=f"dashboard-user-{uuid.uuid4()}",
        email="user@example.com",
        password="password123",
    )
    for name in group_names:
        group, _ = Group.objects.get_or_create(name=name)
        user.groups.add(group)
    return user


def test_dashboard_displays_preparator_card(client):
    user = _create_user_with_groups("Preparators")
    client.force_login(user)

    response = client.get(reverse("dashboard"))

    assert response.status_code == 200
    content = response.content.decode()

    assert '<main class="w3-container' in content
    assert "fa-vials" in content
    assert "My active preparations" in content
    assert "w3-card-4" in content


def test_dashboard_collection_manager_sections(client):
    user = _create_user_with_groups("Collection Managers")
    client.force_login(user)

    response = client.get(reverse("dashboard"))

    assert response.status_code == 200
    content = response.content.decode()

    assert "Collection management" in content
    assert ("Generate batch" in content) or (
        "You do not currently have an active accession number series." in content
    )
    assert "Quality control queues" in content


def test_dashboard_intern_timer_and_scripts(client):
    user = _create_user_with_groups("Interns")
    client.force_login(user)

    response = client.get(reverse("dashboard"))

    assert response.status_code == 200
    content = response.content.decode()

    assert "My drawers" in content
    assert "scan-timer" in content
    assert "setInterval(updateTimers" in content
