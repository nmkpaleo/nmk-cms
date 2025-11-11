import itertools

import pytest
from django.urls import reverse

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


def create_locality(*, abbreviation: str, name: str, geological_times: list[str] | None = None) -> Locality:
    return Locality.objects.create(
        abbreviation=abbreviation,
        name=name,
        geological_times=geological_times or [],
    )


def create_accession(*, locality: Locality, specimen_no: int = 1) -> Accession:
    collection, _ = Collection.objects.get_or_create(
        abbreviation="COL",
        defaults={"description": "Collection"},
    )
    return Accession.objects.create(
        collection=collection,
        specimen_prefix=locality,
        specimen_no=specimen_no,
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


def test_accession_row_print_view_resolves_taxonomy_by_name_when_no_record(client):
    locality = create_locality(abbreviation="PN", name="Print Narrows")
    accession = create_accession(locality=locality, specimen_no=102)
    accession_row = create_accession_row(accession=accession, specimen_suffix="B")

    create_taxon(
        taxon_name="Panthera tigris",
        family="Felidae",
        genus="Panthera",
        species="tigris",
    )
    Identification.objects.create(
        accession_row=accession_row,
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

    Identification.objects.create(
        accession_row=accession_row,
        taxon="Mystery specimen",
        identification_qualifier="aff.",
    )

    response = client.get(reverse("accessionrow_print", args=[accession_row.pk]))

    assert response.status_code == 200
    assert response.context["has_taxonomy_values"] is False
    assert response.context["taxonomy_fallback_value"] == "Mystery specimen"
    assert response.context["identification_qualifier"] == "aff."


def test_accession_row_detail_includes_print_button(client):
    locality = create_locality(abbreviation="PD", name="Print Delta")
    accession = create_accession(locality=locality, specimen_no=104)
    accession_row = create_accession_row(accession=accession, specimen_suffix="D")

    response = client.get(reverse("accessionrow_detail", args=[accession_row.pk]))

    assert response.status_code == 200
    content = response.content.decode()
    print_url = reverse("accessionrow_print", args=[accession_row.pk])
    assert f'href="{print_url}"' in content
