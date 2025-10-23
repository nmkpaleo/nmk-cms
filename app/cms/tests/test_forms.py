import pytest
from django.contrib.auth import get_user_model
from django.template.loader import render_to_string
from django.test import RequestFactory

from app.cms.forms import (
    AccessionForm,
    AccessionRowIdentificationForm,
    DrawerRegisterForm,
    TaxonWidget,
)
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

pytestmark = pytest.mark.django_db


def make_taxon(
    name: str,
    *,
    status: str = TaxonStatus.ACCEPTED,
    rank: str = TaxonRank.SPECIES,
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
        family="Familia",
        subfamily="",
        tribe="",
        genus=genus,
        species=species,
        infraspecific_epithet="",
        scientific_name_authorship="Author",
    )


def test_taxon_widget_queryset_filters_only_active_accepted():
    accepted = make_taxon("Acceptedus example")
    make_taxon(
        "Dormant example", is_active=False, external_id="NOW:species:Dormant example"
    )
    make_taxon(
        "Synonymus example",
        status=TaxonStatus.SYNONYM,
        accepted_taxon=accepted,
        external_id="NOW:syn:Synonymus example::accepted:Acceptedus example",
    )

    widget = TaxonWidget()
    queryset = widget.get_queryset()

    assert accepted in queryset
    assert queryset.filter(status=TaxonStatus.SYNONYM).count() == 0
    assert queryset.filter(is_active=False).count() == 0


def _make_accession_row():
    collection = Collection.objects.create(abbreviation="COL", description="Collection")
    locality = Locality.objects.create(abbreviation="LC", name="Locality")
    user_model = get_user_model()
    user = user_model.objects.create(username="curator")
    accession = Accession.objects.create(
        collection=collection,
        specimen_prefix=locality,
        specimen_no=1,
        accessioned_by=user,
    )
    return AccessionRow.objects.create(accession=accession)


def test_identification_form_defaults_taxon_from_record():
    accession_row = _make_accession_row()
    taxon = make_taxon(
        "Ferrequitherium sweeti", external_id="NOW:species:Ferrequitherium sweeti"
    )
    form = AccessionRowIdentificationForm(
        data={
            "identified_by": "",
            "taxon": "",
            "taxon_record": str(taxon.pk),
            "reference": "",
            "date_identified": "",
            "identification_qualifier": "",
            "verbatim_identification": "",
            "identification_remarks": "",
        },
        instance=Identification(accession_row=accession_row),
    )

    assert form.is_valid()
    assert form.cleaned_data["taxon"] == taxon.taxon_name
    assert form.cleaned_data["taxon_record"] == taxon


def test_drawer_register_form_limits_taxa_queryset():
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
    synonym = make_taxon(
        "Order synonym",
        rank=TaxonRank.ORDER,
        status=TaxonStatus.SYNONYM,
        accepted_taxon=order_taxon,
        external_id="NOW:syn:Order synonym::accepted:Ordertaxon example",
    )

    form = DrawerRegisterForm()
    taxa_queryset = form.fields["taxa"].queryset

    assert order_taxon in taxa_queryset
    assert synonym not in taxa_queryset
    assert not taxa_queryset.filter(is_active=False).exists()


def test_base_form_renders_w3_layout():
    collection = Collection.objects.create(abbreviation="COL", description="Collection")
    locality = Locality.objects.create(abbreviation="LC", name="Locality")
    user_model = get_user_model()
    user_model.objects.create(username="accessionist")

    request = RequestFactory().get("/accessions/new/")
    form = AccessionForm()
    html = render_to_string(
        "includes/base_form.html",
        {
            "form": form,
            "method": "post",
            "action": "/accessions/new/",
            "title": "Accession",
            "heading_id": "accession-form",
        },
        request=request,
    )

    assert "w3-card-4" in html
    assert "w3-button w3-blue" in html
    assert '<h1 id="accession-form"' in html


def test_base_form_marks_field_errors_accessibly():
    collection = Collection.objects.create(abbreviation="COL", description="Collection")
    locality = Locality.objects.create(abbreviation="LC", name="Locality")
    user_model = get_user_model()
    user = user_model.objects.create(username="creator")

    form = AccessionForm(
        data={
            "collection": "",
            "specimen_prefix": "",
            "specimen_no": "",
            "accessioned_by": user.pk,
        }
    )
    form.is_valid()

    request = RequestFactory().get("/accessions/new/")

    html = render_to_string(
        "includes/base_form.html",
        {
            "form": form,
            "method": "post",
            "action": "/accessions/new/",
            "title": "Accession",
            "heading_id": "accession-form",
        },
        request=request,
    )

    assert "aria-invalid=\"true\"" in html
    assert "role=\"alert\"" in html
