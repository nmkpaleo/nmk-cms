import itertools
import re
from html import unescape
from urllib.parse import parse_qs

import pytest
from crum import set_current_user
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.urls import reverse
from django.db import connection

from app.cms.models import (
    Accession,
    AccessionReference,
    AccessionRow,
    Collection,
    Identification,
    Locality,
    Reference,
    Storage,
    Taxon,
    TaxonRank,
)

pytestmark = pytest.mark.django_db


User = get_user_model()


@pytest.fixture
def collection_manager_user() -> User:
    """Create and set the current user for model save validation."""
    user = create_collection_manager_user(username="views-manager")
    set_current_user(user)
    try:
        yield user
    finally:
        set_current_user(None)


@pytest.fixture(autouse=True)
def authenticated_model_user(collection_manager_user: User) -> User:
    """Ensure a current user exists during model fixture/object creation."""
    return collection_manager_user


def create_locality(*, abbreviation: str, name: str, geological_times: list[str] | None = None) -> Locality:
    return Locality.objects.create(
        abbreviation=abbreviation,
        name=name,
        geological_times=geological_times or [],
    )


def create_accession(
    *, locality: Locality, specimen_no: int = 1, is_published: bool = True
) -> Accession:
    collection, _ = Collection.objects.get_or_create(
        abbreviation="COL",
        defaults={"description": "Collection"},
    )
    return Accession.objects.create(
        collection=collection,
        specimen_prefix=locality,
        specimen_no=specimen_no,
        is_published=is_published,
    )


_storage_counter = itertools.count(1)


def create_storage() -> Storage:
    index = next(_storage_counter)
    return Storage.objects.create(area=f"Storage {index}")


def create_accession_row(*, accession: Accession, specimen_suffix: str) -> AccessionRow:
    return AccessionRow.objects.create(
        accession=accession,
        storage=create_storage(),
        specimen_suffix=specimen_suffix,
    )


def create_collection_manager_user(*, username: str = "manager") -> User:
    user = User.objects.create_user(username=username, password="password123")
    group, _ = Group.objects.get_or_create(name="Collection Managers")
    user.groups.add(group)
    return user


def create_taxon(
    *,
    taxon_name: str,
    family: str,
    genus: str,
    species: str,
    subfamily: str = "",
    tribe: str = "",
) -> Taxon:
    return Taxon.objects.create(
        taxon_rank=TaxonRank.SPECIES,
        taxon_name=taxon_name,
        kingdom="Animalia",
        phylum="Chordata",
        class_name="Mammalia",
        order="Primates",
        superfamily="",
        family=family,
        subfamily=subfamily,
        tribe=tribe,
        genus=genus,
        species=species,
    )


def test_locality_list_includes_geological_times_and_accession_counts(client):
    miocene = create_locality(
        abbreviation="MI",
        name="Miocene Site",
        geological_times=[Locality.GeologicalTime.MIOCENE, Locality.GeologicalTime.PLIOCENE],
    )
    create_accession(locality=miocene, specimen_no=1)
    create_accession(locality=miocene, specimen_no=2)

    create_locality(abbreviation="HO", name="Holocene Site", geological_times=[Locality.GeologicalTime.HOLOCENE])

    response = client.get(reverse("locality_list"))

    assert response.status_code == 200
    rendered_localities = list(response.context["localities"])
    target = next(loc for loc in rendered_localities if loc.pk == miocene.pk)

    assert target.accession_count == 2
    assert target.geological_times_label_display() == "Miocene/Pliocene"
    content = response.content.decode()
    assert "Miocene/Pliocene" in content
    assert ">2<" in content


@pytest.mark.skipif(connection.vendor == "sqlite", reason="JSONField contains lookup not supported on sqlite")
def test_locality_list_keeps_multiselect_geological_time_filters_on_pagination(client):
    selected_times = [
        Locality.GeologicalTime.MIOCENE,
        Locality.GeologicalTime.PLIOCENE,
    ]

    for index in range(12):
        geological_time = selected_times[index % len(selected_times)]
        create_locality(
            abbreviation=f"L{index:02d}",
            name=f"Locality {index:02d}",
            geological_times=[geological_time],
        )

    for index in range(3):
        create_locality(
            abbreviation=f"H{index:02d}",
            name=f"Holocene {index:02d}",
            geological_times=[Locality.GeologicalTime.HOLOCENE],
        )

    response = client.get(
        reverse("locality_list"),
        {"geological_times": selected_times, "page": 2},
    )

    assert response.status_code == 200
    page_obj = response.context["page_obj"]
    assert page_obj.paginator.count == 12
    assert page_obj.number == 2
    assert len(page_obj.object_list) == 2
    assert all(
        any(time in locality.geological_times for time in selected_times)
        for locality in page_obj.object_list
    )

    content = response.content.decode()
    hrefs = re.findall(r'href="([^"]+)"', content)
    assert any(
        parse_qs(unescape(href).lstrip("?")).get("page") == ["1"]
        and set(parse_qs(unescape(href).lstrip("?")).get("geological_times", []))
        == set(selected_times)
        for href in hrefs
    )


def test_accession_list_keeps_filters_on_pagination_and_page_two_results(client):
    filtered_locality = create_locality(abbreviation="AF", name="Accession Filtered")
    other_locality = create_locality(abbreviation="AO", name="Accession Other")

    for index in range(12):
        create_accession(locality=filtered_locality, specimen_no=index + 1)

    for index in range(5):
        create_accession(locality=other_locality, specimen_no=200 + index)

    response = client.get(
        reverse("accession_list"),
        {"specimen_prefix": filtered_locality.pk, "page": 2},
    )

    assert response.status_code == 200
    page_obj = response.context["page_obj"]
    assert page_obj.paginator.count == 12
    assert page_obj.number == 2
    assert len(page_obj.object_list) == 2
    assert all(
        accession.specimen_prefix_id == filtered_locality.pk
        for accession in page_obj.object_list
    )

    content = response.content.decode()
    hrefs = re.findall(r'href="([^"]+)"', content)
    assert any(
        parse_qs(unescape(href).lstrip("?")).get("specimen_prefix")
        == [str(filtered_locality.pk)]
        and parse_qs(unescape(href).lstrip("?")).get("page") == ["1"]
        for href in hrefs
    )


def test_locality_print_view_orders_two_columns_and_shows_legend(client):
    create_locality(abbreviation="AL", name="Alpha", geological_times=[Locality.GeologicalTime.MIOCENE])
    create_locality(abbreviation="BO", name="Beta", geological_times=[Locality.GeologicalTime.PLIOCENE])
    create_locality(abbreviation="CH", name="Gamma", geological_times=[Locality.GeologicalTime.PLEISTOCENE])

    response = client.get(reverse("locality_print"))

    assert response.status_code == 200
    rows = response.context["locality_rows"]
    assert rows[0][0]["name"] == "Alpha"
    assert rows[0][1]["name"] == "Beta"
    assert rows[1][0]["name"] == "Gamma"
    assert rows[1][1] is None
    legend_codes = {item["code"] for item in response.context["geological_time_legend"]}
    assert legend_codes == set(Locality.GeologicalTime.values)
    content = response.content.decode()
    assert "LIST OF CODE MARKS FOR KENYAN FOSSIL LOCALITIES" in content


def test_locality_detail_displays_geological_times(client):
    locality = create_locality(
        abbreviation="LP",
        name="Loop",
        geological_times=[
            Locality.GeologicalTime.MIOCENE,
            Locality.GeologicalTime.PLIOCENE,
        ],
    )

    response = client.get(reverse("locality_detail", args=[locality.pk]))

    assert response.status_code == 200
    content = response.content.decode()
    assert "Geological time" in content
    assert "Miocene/Pliocene" in content


def test_accession_row_print_view_populates_taxonomy_and_references(client):
    locality = create_locality(abbreviation="PR", name="Print Ridge")
    accession = create_accession(locality=locality, specimen_no=101)
    accession_row = create_accession_row(accession=accession, specimen_suffix="A")

    user = create_collection_manager_user(username="manager-print-ridge")
    client.force_login(user)

    taxon = create_taxon(
        taxon_name="Panthera leo",
        family="Felidae",
        genus="Panthera",
        species="leo",
        subfamily="Pantherinae",
        tribe="Pantherini",
    )
    Identification.objects.create(
        accession_row=accession_row,
        taxon_verbatim="Panthera leo",
        taxon="Panthera leo",
        taxon_record=taxon,
        identification_qualifier="cf.",
    )

    reference = Reference.objects.create(
        title="Big Cats",
        first_author="J. Researcher",
        year="2024",
        citation="Researcher 2024",
    )
    AccessionReference.objects.create(
        accession=accession,
        reference=reference,
        page="42",
    )

    response = client.get(reverse("accessionrow_print", args=[accession_row.pk]))

    assert response.status_code == 200
    taxonomy_values = response.context["taxonomy_values"]
    assert taxonomy_values["family"] == "Felidae"
    assert taxonomy_values["subfamily"] == "Pantherinae"
    assert taxonomy_values["tribe"] == "Pantherini"
    assert taxonomy_values["genus"] == "Panthera"
    assert taxonomy_values["species"] == "leo"
    assert response.context["has_taxonomy_values"] is True

    reference_entries = response.context["reference_entries"]
    assert len(reference_entries) == 1
    assert reference_entries[0]["reference"] == reference
    assert reference_entries[0]["page"] == "42"
    assert reference_entries[0]["citation"] == "Researcher 2024"
    assert response.context["can_edit"] is True


def test_accession_row_detail_hides_unpublished_accessions_from_public_users(client):
    locality = create_locality(abbreviation="PU", name="Print Unpublished")
    accession = create_accession(locality=locality, specimen_no=201, is_published=False)
    accession_row = create_accession_row(accession=accession, specimen_suffix="U")

    response = client.get(reverse("accessionrow_detail", args=[accession_row.pk]))

    assert response.status_code == 404


def test_accession_row_detail_shows_unpublished_accessions_to_editors(client):
    locality = create_locality(abbreviation="PE", name="Print Editor")
    accession = create_accession(locality=locality, specimen_no=202, is_published=False)
    accession_row = create_accession_row(accession=accession, specimen_suffix="E")

    user = create_collection_manager_user(username="manager-unpublished-accession")
    client.force_login(user)

    response = client.get(reverse("accessionrow_detail", args=[accession_row.pk]))

    assert response.status_code == 200


def test_accession_row_print_view_resolves_taxonomy_by_name_when_no_record(client):
    locality = create_locality(abbreviation="PN", name="Print Narrows")
    accession = create_accession(locality=locality, specimen_no=102)
    accession_row = create_accession_row(accession=accession, specimen_suffix="B")

    user = create_collection_manager_user(username="manager-print-narrows")
    client.force_login(user)

    create_taxon(
        taxon_name="Panthera tigris",
        family="Felidae",
        genus="Panthera",
        species="tigris",
    )
    Identification.objects.create(
        accession_row=accession_row,
        taxon_verbatim="Panthera tigris",
        taxon="Panthera tigris",
    )

    response = client.get(reverse("accessionrow_print", args=[accession_row.pk]))

    assert response.status_code == 200
    taxonomy_values = response.context["taxonomy_values"]
    assert taxonomy_values["family"] == "Felidae"
    assert taxonomy_values["genus"] == "Panthera"
    assert taxonomy_values["species"] == "tigris"
    assert response.context["has_taxonomy_values"] is True


def test_accession_row_print_view_uses_taxon_fallback_when_unresolved(client):
    locality = create_locality(abbreviation="PU", name="Print Unknown")
    accession = create_accession(locality=locality, specimen_no=103)
    accession_row = create_accession_row(accession=accession, specimen_suffix="C")

    user = create_collection_manager_user(username="manager-print-unknown")
    client.force_login(user)

    Identification.objects.create(
        accession_row=accession_row,
        taxon_verbatim="Mystery specimen",
        taxon="Mystery specimen",
        identification_qualifier="aff.",
    )

    response = client.get(reverse("accessionrow_print", args=[accession_row.pk]))

    assert response.status_code == 200
    assert response.context["has_taxonomy_values"] is False
    assert response.context["taxonomy_fallback_value"] == "Mystery specimen"
    assert response.context["identification_qualifier"] == "aff."


def test_accession_row_print_view_redirects_anonymous_user(client):
    locality = create_locality(abbreviation="PZ", name="Print Zero")
    accession = create_accession(locality=locality, specimen_no=109)
    accession_row = create_accession_row(accession=accession, specimen_suffix="I")

    response = client.get(reverse("accessionrow_print", args=[accession_row.pk]))

    assert response.status_code == 302
    assert "login" in response.headers["Location"]


def test_accession_row_print_view_forbids_read_only_user(client):
    locality = create_locality(abbreviation="PY", name="Print Yankee")
    accession = create_accession(locality=locality, specimen_no=110)
    accession_row = create_accession_row(accession=accession, specimen_suffix="J")

    user = User.objects.create_user(username="read-only", password="password123")
    client.force_login(user)

    response = client.get(reverse("accessionrow_print", args=[accession_row.pk]))

    assert response.status_code == 403


def test_accession_row_print_shows_storage_for_editors(client):
    locality = create_locality(abbreviation="PS", name="Print Storage")
    accession = create_accession(locality=locality, specimen_no=106)
    accession_row = create_accession_row(accession=accession, specimen_suffix="F")

    user = create_collection_manager_user(username="manager-print")
    client.force_login(user)

    response = client.get(reverse("accessionrow_print", args=[accession_row.pk]))

    assert response.status_code == 200
    assert response.context["can_edit"] is True

    content = response.content.decode()
    assert "Storage" in content


def test_accession_row_detail_includes_print_button_for_editors(client):
    locality = create_locality(abbreviation="PD", name="Print Delta")
    accession = create_accession(locality=locality, specimen_no=104)
    accession_row = create_accession_row(accession=accession, specimen_suffix="D")

    user = create_collection_manager_user()
    client.force_login(user)

    response = client.get(reverse("accessionrow_detail", args=[accession_row.pk]))

    assert response.status_code == 200
    content = response.content.decode()
    print_url = reverse("accessionrow_print", args=[accession_row.pk])
    assert f'href="{print_url}"' in content
    assert "<th scope=\"row\">Storage</th>" in content


def test_accession_row_detail_hides_print_button_for_read_only_users(client):
    locality = create_locality(abbreviation="PE", name="Print Echo")
    accession = create_accession(locality=locality, specimen_no=105)
    accession_row = create_accession_row(accession=accession, specimen_suffix="E")

    response = client.get(reverse("accessionrow_detail", args=[accession_row.pk]))

    assert response.status_code == 200
    content = response.content.decode()
    print_url = reverse("accessionrow_print", args=[accession_row.pk])
    assert f'href="{print_url}"' not in content
    assert "<th scope=\"row\">Storage</th>" not in content


def test_accession_detail_hides_storage_column_for_read_only_users(client):
    locality = create_locality(abbreviation="AD", name="Accession Delta")
    accession = create_accession(locality=locality, specimen_no=107)
    create_accession_row(accession=accession, specimen_suffix="G")

    response = client.get(reverse("accession_detail", args=[accession.pk]))

    assert response.status_code == 200
    content = response.content.decode()
    assert "<th scope=\"col\">Storage</th>" not in content


def test_accession_detail_shows_storage_column_for_editors(client):
    locality = create_locality(abbreviation="AE", name="Accession Echo")
    accession = create_accession(locality=locality, specimen_no=108)
    create_accession_row(accession=accession, specimen_suffix="H")

    user = create_collection_manager_user(username="manager-accession")
    client.force_login(user)

    response = client.get(reverse("accession_detail", args=[accession.pk]))

    assert response.status_code == 200
    content = response.content.decode()
    assert "<th scope=\"col\">Storage</th>" in content
