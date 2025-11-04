import pytest
from django.urls import reverse

from app.cms.models import Accession, Collection, Locality

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
    assert target.geological_times_abbreviation_display() == "M/Pi"
    content = response.content.decode()
    assert "M/Pi" in content
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
