import pytest

from app.cms.filters import AccessionFilter, DrawerRegisterFilter, LocalityFilter
from app.cms.models import (
    Accession,
    AccessionRow,
    Collection,
    DrawerRegister,
    Identification,
    Locality,
    Taxon,
    TaxonExternalSource,
    TaxonRank,
    TaxonStatus,
)

pytestmark = pytest.mark.django_db


def make_taxon(
    name: str,
    *,
    status: str = TaxonStatus.ACCEPTED,
    rank: str = TaxonRank.SPECIES,
    family: str = "Familia",
    is_active: bool = True,
    external_id: str | None = None,
    accepted_taxon: Taxon | None = None,
) -> Taxon:
    parts = name.split()
    genus = parts[0]
    species = parts[1] if len(parts) > 1 else parts[0]
    return Taxon.objects.create(
        external_source=TaxonExternalSource.NOW,
        external_id=external_id,
        author_year="Author 1900",
        status=status,
        accepted_taxon=accepted_taxon if status == TaxonStatus.SYNONYM else None,
        parent=None,
        is_active=is_active,
        source_version="v1",
        taxon_rank=rank,
        taxon_name=name,
        kingdom="Animalia",
        phylum="Chordata",
        class_name="Mammalia",
        order="Orderus",
        superfamily="",
        family=family,
        subfamily="",
        tribe="",
        genus=genus,
        species=species,
        infraspecific_epithet="",
        scientific_name_authorship="Author",
    )


def make_accession() -> Accession:
    collection = Collection.objects.create(abbreviation="COL", description="Collection")
    locality = Locality.objects.create(abbreviation="LC", name="Locality")
    accession = Accession.objects.create(
        collection=collection,
        specimen_prefix=locality,
        specimen_no=1,
    )
    return accession


def test_accession_filter_matches_taxon_record_name():
    accession = make_accession()
    accession_row = AccessionRow.objects.create(accession=accession)
    accepted = make_taxon(
        "Ferrequitherium sweeti", external_id="NOW:species:Ferrequitherium sweeti"
    )
    Identification.objects.create(
        accession_row=accession_row,
        taxon_verbatim=accepted.taxon_name,
    )
    synonym = make_taxon(
        "Ferrequitherium junior",
        status=TaxonStatus.SYNONYM,
        accepted_taxon=accepted,
        external_id="NOW:syn:Ferrequitherium junior::accepted:Ferrequitherium sweeti",
    )

    qs = Accession.objects.all()
    filterset = AccessionFilter(data={"taxon": synonym.taxon_name}, queryset=qs)

    assert accession in filterset.qs


def test_accession_filter_matches_verbatim_taxon_name_without_record():
    accession = make_accession()
    accession_row = AccessionRow.objects.create(accession=accession)
    Identification.objects.create(
        accession_row=accession_row,
        taxon_verbatim="Unmatchedus example",
    )

    qs = Accession.objects.all()
    filterset = AccessionFilter(data={"taxon": "Unmatched"}, queryset=qs)

    assert accession in filterset.qs


def test_accession_filter_family_uses_taxon_record_attribute():
    accession = make_accession()
    accession_row = AccessionRow.objects.create(accession=accession)
    accepted = make_taxon(
        "Familitaxon example",
        external_id="NOW:species:Familitaxon example",
        family="Testidae",
    )
    Identification.objects.create(
        accession_row=accession_row,
        taxon_verbatim=accepted.taxon_name,
    )

    qs = Accession.objects.all()
    filterset = AccessionFilter(data={"family": "Testid"}, queryset=qs)

    assert accession in filterset.qs


def test_drawer_register_filter_taxa_queryset_only_active_orders():
    order_taxon = make_taxon(
        "Ordertaxon example",
        rank=TaxonRank.ORDER,
        external_id="NOW:order:Ordertaxon example",
    )
    make_taxon(
        "Inactive order",
        rank=TaxonRank.ORDER,
        is_active=False,
        external_id="NOW:order:Inactive order",
    )
    make_taxon(
        "Order synonym",
        rank=TaxonRank.ORDER,
        status=TaxonStatus.SYNONYM,
        accepted_taxon=order_taxon,
        external_id="NOW:syn:Order synonym::accepted:Ordertaxon example",
    )

    filterset = DrawerRegisterFilter(data={}, queryset=DrawerRegister.objects.none())
    taxa_queryset = filterset.form.fields["taxa"].queryset

    assert order_taxon in taxa_queryset
    assert not taxa_queryset.filter(is_active=False).exists()
    assert not taxa_queryset.filter(status=TaxonStatus.SYNONYM).exists()


def test_locality_filter_geological_times_returns_matching_localities():
    alpha = Locality.objects.create(
        abbreviation="LA",
        name="Alpha",
        geological_times=[Locality.GeologicalTime.MIOCENE],
    )
    beta = Locality.objects.create(
        abbreviation="LB",
        name="Beta",
        geological_times=[Locality.GeologicalTime.HOLOCENE],
    )
    gamma = Locality.objects.create(
        abbreviation="LC",
        name="Gamma",
        geological_times=[
            Locality.GeologicalTime.MIOCENE,
            Locality.GeologicalTime.PLIOCENE,
        ],
    )

    filterset = LocalityFilter(
        data={"geological_times": [Locality.GeologicalTime.MIOCENE]},
        queryset=Locality.objects.all(),
    )

    assert set(filterset.qs) == {alpha, gamma}
    assert beta not in filterset.qs


def test_locality_filter_geological_times_accepts_multiple_values():
    alpha = Locality.objects.create(
        abbreviation="L1",
        name="Alpha",
        geological_times=[Locality.GeologicalTime.MIOCENE],
    )
    beta = Locality.objects.create(
        abbreviation="L2",
        name="Beta",
        geological_times=[Locality.GeologicalTime.PLIOCENE],
    )
    gamma = Locality.objects.create(
        abbreviation="L3",
        name="Gamma",
        geological_times=[Locality.GeologicalTime.PLEISTOCENE],
    )

    filterset = LocalityFilter(
        data={
            "geological_times": [
                Locality.GeologicalTime.PLIOCENE,
                Locality.GeologicalTime.PLEISTOCENE,
            ]
        },
        queryset=Locality.objects.all(),
    )

    assert set(filterset.qs) == {beta, gamma}
    assert alpha not in filterset.qs
