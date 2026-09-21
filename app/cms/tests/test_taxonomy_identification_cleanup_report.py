from datetime import date

import pytest
from crum import set_current_user
from django.contrib.auth.models import Group
from django.urls import reverse

from cms.models import Accession, AccessionRow, Collection, Identification, Locality, Reference, Taxon, TaxonExternalSource


pytestmark = pytest.mark.django_db


def _accession_row(user, specimen_no=1):
    collection, _ = Collection.objects.get_or_create(
        abbreviation="TC", defaults={"description": "Test collection"}
    )
    locality, _ = Locality.objects.get_or_create(
        abbreviation="TR", defaults={"name": "Test report locality"}
    )
    accession = Accession.objects.create(
        collection=collection, specimen_prefix=locality, specimen_no=specimen_no, accessioned_by=user
    )
    return AccessionRow.objects.create(accession=accession, specimen_suffix="A")


def test_cleanup_report_lists_missing_and_unmatched_current_taxa(client, django_user_model):
    user = django_user_model.objects.create_user(username="manager", password="testpass123")
    managers, _ = Group.objects.get_or_create(name="Collection Managers")
    user.groups.add(managers)
    set_current_user(user)
    try:
        Taxon.objects.create(
            taxon_name="Struthio", taxon_rank="genus", external_source=TaxonExternalSource.GBIF
        )
        valid_row = _accession_row(user)
        Identification.objects.create(
            accession_row=valid_row,
            taxon_verbatim="Old unknown taxon",
            taxon="Old unknown taxon",
            date_identified=date(2020, 1, 1),
        )
        valid_qualified = Identification.objects.create(
            accession_row=valid_row,
            taxon_verbatim="Struthio",
            identification_qualifier="cf.",
            date_identified=date(2024, 1, 1),
        )
        dated_row = _accession_row(user, specimen_no=5)
        newer_reference = Reference.objects.create(
            title="Newer reference", first_author="Author", year="2024", citation="Author 2024"
        )
        older_reference = Reference.objects.create(
            title="Older reference", first_author="Author", year="1999", citation="Author 1999"
        )
        Identification.objects.create(
            accession_row=dated_row,
            taxon_verbatim="Dated unknown taxon",
            taxon="Dated unknown taxon",
            reference=newer_reference,
            date_identified=date(2024, 1, 1),
        )
        Identification.objects.create(
            accession_row=dated_row,
            taxon_verbatim="Struthio",
            reference=older_reference,
            date_identified=date(2024, 1, 1),
        )
        whitespace_row = _accession_row(user, specimen_no=4)
        whitespace_valid = Identification.objects.create(
            accession_row=whitespace_row, taxon_verbatim="Struthio"
        )
        Identification.objects.filter(pk=whitespace_valid.pk).update(
            taxon="Struthio\t ", taxon_record=None
        )
        unmatched_row = _accession_row(user, specimen_no=2)
        unmatched = Identification.objects.create(
            accession_row=unmatched_row, taxon_verbatim="Unknownus", taxon="Unknownus"
        )
        missing_row = _accession_row(user, specimen_no=3)
        missing = Identification.objects.create(accession_row=missing_row, taxon_verbatim="Aves")
        Identification.objects.filter(pk=missing.pk).update(taxon="")
    finally:
        set_current_user(None)

    client.force_login(user)
    response = client.get(reverse("taxonomy_identification_cleanup_report"))

    assert response.status_code == 200
    shown = list(response.context["identifications"])
    assert shown == [unmatched, missing]
    assert whitespace_valid not in shown
    assert b"Struthio" not in response.content
    assert b"Taxon does not match GBIF/NOW taxonomy" in response.content
    assert b"Taxon is empty" in response.content
    assert reverse("identification_edit", args=[unmatched.pk]).encode() in response.content
    assert reverse("identification_edit", args=[missing.pk]).encode() in response.content


def test_cleanup_report_requires_collection_manager(client, django_user_model):
    user = django_user_model.objects.create_user(username="regular", password="testpass123")
    client.force_login(user)

    response = client.get(reverse("taxonomy_identification_cleanup_report"))

    assert response.status_code == 302
