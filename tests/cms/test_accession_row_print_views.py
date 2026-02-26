import uuid

import pytest
from crum import set_current_user
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client
from django.urls import reverse

from cms.models import Accession, AccessionRow, Collection, Locality

pytestmark = pytest.mark.django_db


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


def _create_accession_row(user: object | None = None) -> AccessionRow:
    created_user = None
    if user is None:
        created_user = get_user_model().objects.create_user(
            username=f"system-{uuid.uuid4().hex}",
            email="system@example.com",
            password="pass",
        )
        created_user.is_superuser = True
        created_user.save(update_fields=["is_superuser"])

    set_current_user(user or created_user)
    try:
        collection, _ = Collection.objects.get_or_create(
            abbreviation="COL", defaults={"description": "Collection"}
        )
        locality, _ = Locality.objects.get_or_create(
            abbreviation="AB", defaults={"name": "Alpha", "geological_times": []}
        )
        accession, _ = Accession.objects.get_or_create(
            collection=collection,
            specimen_prefix=locality,
            specimen_no=1,
            instance_number=1,
        )
        accession_row, _ = AccessionRow.objects.get_or_create(
            accession=accession, specimen_suffix="A"
        )
        return accession_row
    finally:
        set_current_user(None)


def test_print_views_render_for_collection_manager():
    client, _user = _login_collection_manager()
    accession_row = _create_accession_row(_user)

    big_response = client.get(
        reverse("accessionrow_print", args=[accession_row.pk])
    )
    small_response = client.get(
        reverse("accessionrow_print_small", args=[accession_row.pk])
    )

    assert big_response.status_code == 200
    assert small_response.status_code == 200
    assert big_response.context["qr_target_url"] == f"http://testserver{accession_row.get_absolute_url()}"
    assert small_response.context["qr_target_url"] == f"http://testserver{accession_row.get_absolute_url()}"
    assert "nmk-print-card" in big_response.content.decode()
    small_html = small_response.content.decode()
    assert "nmk-print-card" in small_html
    assert "<th scope=\"row\">References</th>" not in small_html


def test_print_view_requires_collection_manager_permissions():
    client = Client()
    accession_row = _create_accession_row()

    # anonymous redirect to login
    response = client.get(reverse("accessionrow_print", args=[accession_row.pk]))
    assert response.status_code == 302

    # logged-in user without group receives permission denial
    user = get_user_model().objects.create_user(
        username="regular-user", email="regular@example.com", password="pass"
    )
    assert client.login(username=user.username, password="pass")
    forbidden_response = client.get(
        reverse("accessionrow_print", args=[accession_row.pk])
    )
    assert forbidden_response.status_code == 403
