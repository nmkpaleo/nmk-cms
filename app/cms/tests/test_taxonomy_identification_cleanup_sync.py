from unittest.mock import patch

import pytest
from django.contrib.auth.models import Group
from django.urls import reverse
from crum import set_current_user

from cms.models import Accession, AccessionRow, Collection, Identification, Locality, TaxonExternalSource


pytestmark = pytest.mark.django_db


def test_cleanup_sync_action_reports_failure(client, django_user_model):
    user = django_user_model.objects.create_user(username="manager", password="testpass123")
    managers, _ = Group.objects.get_or_create(name="Collection Managers")
    user.groups.add(managers)
    set_current_user(user)
    try:
        collection = Collection.objects.create(abbreviation="TS", description="Test")
        locality = Locality.objects.create(abbreviation="TL", name="Test")
        accession = Accession.objects.create(collection=collection, specimen_prefix=locality, specimen_no=1, accessioned_by=user)
        row = AccessionRow.objects.create(accession=accession, specimen_suffix="A")
        identification = Identification.objects.create(
            accession_row=row, taxon_verbatim="Unknownus", taxon="Unknownus"
        )
        with patch("cms.views.TaxonomySyncService.preview_for_name", side_effect=ValueError("no exact match")):
            client.force_login(user)
            response = client.post(reverse("taxonomy_identification_cleanup_report"), {"identification_id": identification.pk})
    finally:
        set_current_user(None)

    assert response.status_code == 302
    assert b"no exact match" in client.get(response.url).content
