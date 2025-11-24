import uuid

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.test import Client
from django.urls import reverse

from cms.models import Accession, AccessionRow, Collection, Locality

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


def _create_accession_row() -> AccessionRow:
    collection = Collection.objects.create(
        abbreviation="COL", description="Collection"
    )
    locality = Locality.objects.create(
        abbreviation="AB", name="Alpha", geological_times=[]
    )
    accession = Accession.objects.create(
        collection=collection,
        specimen_prefix=locality,
        specimen_no=1,
        instance_number=1,
    )
    return AccessionRow.objects.create(accession=accession, specimen_suffix="A")


def test_print_views_render_for_collection_manager():
    client, _user = _login_collection_manager()
    accession_row = _create_accession_row()

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
    assert "nmk-print-card" in small_response.content.decode()
    assert "References" not in small_response.content.decode()


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
