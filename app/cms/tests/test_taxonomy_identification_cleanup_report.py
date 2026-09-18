from datetime import date

import pytest
from crum import set_current_user
from django.contrib.auth.models import Group
from django.urls import reverse

from cms.models import Accession, AccessionRow, Collection, Identification, Locality


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


def test_cleanup_report_lists_only_current_qualified_identifications(client, django_user_model):
    user = django_user_model.objects.create_user(username="manager", password="testpass123")
    managers, _ = Group.objects.get_or_create(name="Collection Managers")
    user.groups.add(managers)
    set_current_user(user)
    try:
        row = _accession_row(user)
        old_qualified = Identification.objects.create(
            accession_row=row, taxon_verbatim="cf. Struthio", date_identified=date(2020, 1, 1)
        )
        current_clean = Identification.objects.create(
            accession_row=row, taxon_verbatim="Struthio", date_identified=date(2024, 1, 1)
        )
        qualified_row = _accession_row(user, specimen_no=2)
        current_qualified = Identification.objects.create(
            accession_row=qualified_row, taxon_verbatim="Struthio", identification_qualifier="cf."
        )
        nr_row = _accession_row(user, specimen_no=3)
        current_nr = Identification.objects.create(accession_row=nr_row, taxon_verbatim="nr. Struthio")
    finally:
        set_current_user(None)

    client.force_login(user)
    response = client.get(reverse("taxonomy_identification_cleanup_report"))

    assert response.status_code == 200
    shown = list(response.context["identifications"])
    assert shown == [current_qualified, current_nr]
    assert b"cf. Struthio" not in response.content
    assert reverse("identification_edit", args=[current_qualified.pk]).encode() in response.content
    assert reverse("identification_edit", args=[current_nr.pk]).encode() in response.content


def test_cleanup_report_requires_collection_manager(client, django_user_model):
    user = django_user_model.objects.create_user(username="regular", password="testpass123")
    client.force_login(user)

    response = client.get(reverse("taxonomy_identification_cleanup_report"))

    assert response.status_code == 302
