import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client
from django.urls import reverse

from cms.models import AccessionNumberSeries, Organisation, UserOrganisation

pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return Client()


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


def _dashboard_response_for_collection_manager(client, monkeypatch, *, has_active_series: bool):
    user = _create_user_with_groups("Collection Managers")
    monkeypatch.setattr("cms.models.get_current_user", lambda: user)

    organisation = Organisation.objects.create(
        name="Dashboard Org", code=f"org-{uuid.uuid4().hex[:8]}"
    )
    UserOrganisation.objects.create(user=user, organisation=organisation)

    if has_active_series:
        AccessionNumberSeries.objects.create(
            user=user,
            organisation=organisation,
            start_from=1,
            end_at=10,
            current_number=1,
            is_active=True,
        )

    client.force_login(user)
    return client.get(reverse("dashboard"))


def test_dashboard_sets_active_series_flag_for_manager(client, monkeypatch):
    response = _dashboard_response_for_collection_manager(
        client, monkeypatch, has_active_series=True
    )

    assert response.context["has_active_series"] is True
    content = response.content.decode()

    assert reverse("accession-wizard") in content
    assert 'aria-disabled="false"' in content


def test_dashboard_disables_create_single_accession_without_series(client, monkeypatch):
    response = _dashboard_response_for_collection_manager(
        client, monkeypatch, has_active_series=False
    )

    assert response.context["has_active_series"] is False
    content = response.content.decode()

    assert reverse("accession-wizard") not in content
    assert 'aria-disabled="true"' in content
    assert "w3-disabled" in content


def test_dashboard_superuser_can_create_single_accession_without_series(client):
    user_model = get_user_model()
    admin = user_model.objects.create_superuser(
        username="dashboard-admin", password="password123"
    )
    client.force_login(admin)

    response = client.get(reverse("dashboard"))

    assert response.context["has_active_series"] is False
    content = response.content.decode()

    assert reverse("accession-wizard") in content
    assert 'aria-disabled="false"' in content
