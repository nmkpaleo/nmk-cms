import pytest
from crum import set_current_user
from django.contrib import admin
from django.contrib.auth import get_user_model

from app.cms.models import (
    Accession,
    AccessionRow,
    Collection,
    Identification,
    Locality,
    Taxon,
    TaxonExternalSource,
    TaxonRank,
    TaxonStatus,
)
from app.cms.views import attach_accession_summaries


pytestmark = pytest.mark.django_db


def make_taxon(name: str) -> Taxon:
    parts = name.split()
    genus = parts[0]
    species = parts[1] if len(parts) > 1 else parts[0]
    return Taxon.objects.create(
        external_source=TaxonExternalSource.NOW,
        external_id=f"NOW:species:{name}",
        author_year="Author 1900",
        status=TaxonStatus.ACCEPTED,
        accepted_taxon=None,
        parent=None,
        is_active=True,
        source_version="v1",
        taxon_rank=TaxonRank.SPECIES,
        taxon_name=name,
        kingdom="Animalia",
        phylum="Chordata",
        class_name="Mammalia",
        order="Orderus",
        superfamily="",
        family="Familia",
        subfamily="",
        tribe="",
        genus=genus,
        species=species,
        infraspecific_epithet="",
        scientific_name_authorship="Author",
    )


def make_accession_row(user) -> AccessionRow:
    set_current_user(user)
    collection = Collection.objects.create(abbreviation="TX", description="Taxon tests")
    locality = Locality.objects.create(abbreviation="TL", name="Taxon Locality")
    accession = Accession.objects.create(
        collection=collection,
        specimen_prefix=locality,
        specimen_no=1,
        accessioned_by=user,
    )
    accession_row = AccessionRow.objects.create(accession=accession)
    set_current_user(None)
    return accession_row


def test_attach_accession_summaries_prefers_controlled_taxon_name():
    user_model = get_user_model()
    user = user_model.objects.create(username="summary-user")
    accession_row = make_accession_row(user)
    set_current_user(user)
    controlled_taxon = make_taxon("Controlledus example")
    Identification.objects.create(
        accession_row=accession_row,
        taxon_verbatim="Verbatim only",
    )
    Identification.objects.create(
        accession_row=accession_row,
        taxon_verbatim="Alternate entry",
        taxon_record=controlled_taxon,
    )
    set_current_user(None)

    accession = accession_row.accession
    attach_accession_summaries([accession])

    assert accession.taxa_list == ["Alternate entry", "Verbatim only"]


def test_admin_displays_taxonomy_fields_readonly():
    user_model = get_user_model()
    user = user_model.objects.create(username="admin-user")
    accession_row = make_accession_row(user)
    set_current_user(user)
    taxon = make_taxon("Displayus example")

    identification = Identification.objects.create(
        accession_row=accession_row,
        taxon_verbatim="Recorded text",
        taxon_record=taxon,
    )
    set_current_user(None)

    identification_admin = admin.site._registry[Identification]
    assert identification_admin.preferred_taxon_name_display(identification) == "Recorded text"
    assert identification_admin.verbatim_taxon_display(identification) == "Recorded text"
    assert "taxon_record" in identification_admin.readonly_fields

