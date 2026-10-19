from types import SimpleNamespace
from unittest.mock import patch

import pytest
from django.contrib.auth.models import Group
from django.urls import reverse
from crum import set_current_user

from cms.models import (
    Accession,
    AccessionRow,
    Collection,
    Identification,
    Locality,
    Taxon,
    TaxonStatus,
)
from cms.taxonomy.combined import TaxonomySyncService
from cms.taxonomy.sync import AcceptedRecord, NowTaxonomySyncService, SynonymRecord, SyncIssue


pytestmark = pytest.mark.django_db


def _taxon(name, *, status=TaxonStatus.ACCEPTED, accepted_taxon=None):
    return Taxon.objects.create(
        taxon_name=name,
        taxon_rank="species",
        status=status,
        accepted_taxon=accepted_taxon,
        kingdom="Animalia",
        phylum="Chordata",
        class_name="Mammalia",
        order="Perissodactyla",
        family="Equidae",
        genus="Hipparion",
        species=name.split()[-1],
    )


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


def test_cleanup_sync_action_reports_success(client, django_user_model):
    user = django_user_model.objects.create_user(username="cleanup-manager", password="password")
    managers, _ = Group.objects.get_or_create(name="Collection Managers")
    user.groups.add(managers)
    set_current_user(user)
    try:
        collection = Collection.objects.create(abbreviation="TS", description="Test")
        locality = Locality.objects.create(abbreviation="TL", name="Test")
        accession = Accession.objects.create(
            collection=collection, specimen_prefix=locality, specimen_no=1, accessioned_by=user
        )
        row = AccessionRow.objects.create(accession=accession, specimen_suffix="A")
        identification = Identification.objects.create(
            accession_row=row, taxon_verbatim="Hipparion sitifense", taxon="Hipparion sitifense"
        )
        with (
            patch("cms.views.TaxonomySyncService.preview_for_name", return_value=object()),
            patch("cms.views.TaxonomySyncService._apply", return_value=SimpleNamespace(ok=True)),
        ):
            client.force_login(user)
            response = client.post(
                reverse("taxonomy_identification_cleanup_report"),
                {"identification_id": identification.pk},
            )
    finally:
        set_current_user(None)

    assert response.status_code == 302
    assert b"Taxon 'Hipparion sitifense' was synchronized." in client.get(response.url).content


def test_cleanup_sync_action_includes_issue_context(client, django_user_model):
    user = django_user_model.objects.create_user(username="cleanup-issue-manager", password="password")
    managers, _ = Group.objects.get_or_create(name="Collection Managers")
    user.groups.add(managers)
    set_current_user(user)
    try:
        collection = Collection.objects.create(abbreviation="TS", description="Test")
        locality = Locality.objects.create(abbreviation="TL", name="Test")
        accession = Accession.objects.create(
            collection=collection, specimen_prefix=locality, specimen_no=1, accessioned_by=user
        )
        row = AccessionRow.objects.create(accession=accession, specimen_suffix="A")
        identification = Identification.objects.create(
            accession_row=row, taxon_verbatim="Hipparion sitifense", taxon="Hipparion sitifense"
        )
        preview = SimpleNamespace(issues=[
            SyncIssue("unsafe-demotion", "Cannot demote an accepted taxon", {"name": "Hipparion sitifense"})
        ])
        with (
            patch("cms.views.TaxonomySyncService.preview_for_name", return_value=preview),
            patch("cms.views.TaxonomySyncService._apply", return_value=SimpleNamespace(ok=False)),
        ):
            client.force_login(user)
            response = client.post(
                reverse("taxonomy_identification_cleanup_report"),
                {"identification_id": identification.pk},
            )
    finally:
        set_current_user(None)

    assert response.status_code == 302
    warning_content = client.get(response.url).content
    assert b"unsafe-demotion: Cannot demote an accepted taxon" in warning_content
    assert b"name: Hipparion sitifense" in warning_content


def test_preview_for_name_ignores_self_synonym_and_repairs_local_self_link(monkeypatch):
    accepted = _taxon("Hipparion sitifense")
    first_synonym = _taxon(
        "Hipparion old",
        status=TaxonStatus.SYNONYM,
        accepted_taxon=accepted,
    )
    second_synonym = _taxon(
        "Hipparion ancient",
        status=TaxonStatus.SYNONYM,
        accepted_taxon=accepted,
    )
    Taxon.objects.filter(pk=accepted.pk).update(
        status=TaxonStatus.SYNONYM,
        accepted_taxon_id=accepted.pk,
    )
    accepted_record = AcceptedRecord(
        "NOW:species:Hipparion sitifense",
        "Hipparion sitifense",
        "species",
        "",
        "v1",
        {
            "class_name": "Mammalia",
            "order": "Perissodactyla",
            "family": "Equidae",
            "genus": "Hipparion",
            "species": "sitifense",
        },
    )
    self_synonym = SynonymRecord(
        "NOW:syn:species:Hipparion sitifense::accepted:Hipparion sitifense",
        "Hipparion sitifense",
        "Hipparion sitifense",
        accepted_record.external_id,
        "species",
        "",
        "v1",
        accepted_record.taxonomy,
    )
    service = TaxonomySyncService()
    monkeypatch.setattr(service, "_load_remote_records", lambda: ([accepted_record], [self_synonym]))

    preview = service.preview_for_name("Hipparion sitifense")

    assert preview.issues == []
    assert len(preview.accepted_to_update) == 1
    assert preview.synonyms_to_create == []
    assert preview.synonyms_to_update == []
    result = service._apply(preview)

    accepted.refresh_from_db()
    first_synonym.refresh_from_db()
    second_synonym.refresh_from_db()
    assert result.ok is True
    assert accepted.status == TaxonStatus.ACCEPTED
    assert accepted.accepted_taxon_id is None
    assert first_synonym.accepted_taxon_id == accepted.pk
    assert second_synonym.accepted_taxon_id == accepted.pk


def test_preview_still_blocks_real_demotion_of_accepted_taxon_with_synonyms():
    existing_accepted = _taxon("Hipparion sitifense")
    _taxon("Hipparion old", status=TaxonStatus.SYNONYM, accepted_taxon=existing_accepted)
    target = AcceptedRecord(
        "NOW:species:Hipparion target",
        "Hipparion target",
        "species",
        "",
        "v1",
        {"class_name": "Mammalia", "family": "Equidae", "genus": "Hipparion", "species": "target"},
    )
    actual_synonym = SynonymRecord(
        "NOW:syn:species:Hipparion sitifense::accepted:Hipparion target",
        "Hipparion sitifense",
        "Hipparion target",
        target.external_id,
        "species",
        "",
        "v1",
        target.taxonomy,
    )

    preview = NowTaxonomySyncService()._build_preview([target], [actual_synonym])

    assert any(issue.code == "unsafe-demotion" for issue in preview.issues)
    assert preview.synonyms_to_update == []
