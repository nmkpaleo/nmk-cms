"""Apply the reviewed snapshot and commit valid dependency groups despite issues."""
from dataclasses import replace
from unittest.mock import Mock

import pytest
from django.contrib.auth import get_user_model
from django.db import OperationalError, connection
from django.test import RequestFactory

from cms import admin as cms_admin
from cms.models import Taxon
from cms.taxonomy.sync import AcceptedRecord, AcceptedUpdate, SynonymUpdate, SynonymRecord, SyncPreview, SyncIssue, NowTaxonomySyncService
from cms.taxonomy.snapshot import catalogue_fingerprint, sign_preview, apply_signed_preview, PreviewUnavailable
from cms.tests.test_sync_now import authenticated_model_user

pytestmark = pytest.mark.django_db


def record(name="Struthio", **changes):
    base = AcceptedRecord("NOW:genus:" + name, name, "genus", "Author", "v1", {"family": "Testidae"})
    return replace(base, **changes)


def preview(records, synonyms=None, issues=None):
    return SyncPreview(records, [], synonyms or [], [], [], issues or [], "v1")


def user():
    person = get_user_model().objects.get(username="sync-now-user")
    person.is_staff = person.is_superuser = True
    person.save()
    return person


def test_apply_keeps_valid_records_when_another_group_hits_database_constraint():
    occupied = Taxon.objects.create(taxon_name="Occupied", taxon_rank="genus")
    proposed = preview([record("Occupied"), record("Good", author_year="A" * 302)])
    log = NowTaxonomySyncService()._apply(proposed)
    assert Taxon.objects.get(taxon_name="Good").author_year == "A" * 302
    assert Taxon.objects.get(pk=occupied.pk).external_source == "LEGACY"
    assert log.counts["created"] == 1
    assert log.counts["issues"] == 1
    assert log.ok is False
    assert proposed.accepted_to_create == [record("Good", author_year="A" * 302)]
    assert log.report_json["issues"][0]["taxa"] == ["Occupied"]


def test_failed_synonym_rolls_back_its_accepted_group_only():
    target = record("Related")
    synonym = SynonymRecord("NOW:syn:Bad", "Bad", "Related", target.external_id, "genus",
                            "Author", "v1", {"family": "X" * 256})
    proposed = preview([target, record("Independent")], [synonym])
    log = NowTaxonomySyncService()._apply(proposed)
    assert set(Taxon.objects.values_list("taxon_name", flat=True)) == {"Independent"}
    assert log.counts["created"] == 1
    assert log.counts["synonym_links"] == 0
    assert set(proposed.issues[0].context["taxa"]) == {"Related", "Bad"}


def test_apply_post_saves_valid_changes_with_issues_without_fetching_sources(monkeypatch):
    person = user()
    proposed = preview([record()], issues=[SyncIssue("gbif-match", "No exact match", {"name": "Unknown"})])
    token = sign_preview(proposed, person.pk, catalogue_fingerprint())
    service = NowTaxonomySyncService(http_get=Mock(side_effect=AssertionError("Unexpected HTTP")))
    service.preview = Mock(side_effect=AssertionError("Apply must use the reviewed preview"))
    monkeypatch.setattr(cms_admin, "TaxonomySyncService", lambda: service)
    monkeypatch.setattr(cms_admin.admin.site, "each_context", lambda request: {})
    request = RequestFactory().post("/taxonomy/sync/apply/", {"preview_token": token})
    request.user = person
    response = cms_admin._taxonomy_sync_apply_view(request)
    response.render()
    assert response.status_code == 200
    assert response.template_name == "admin/taxonomy/sync_result.html"
    assert response.context_data["counts"]["created"] == 1
    assert b"Valid changes were saved" in response.content
    assert b"Apply sync" not in response.content
    assert Taxon.objects.filter(taxon_name="Struthio").exists()
    service.preview.assert_not_called()
    service.http_get.assert_not_called()
    with pytest.raises(PreviewUnavailable, match="catalogue changed"):
        apply_signed_preview(token, person.pk, service)


@pytest.mark.parametrize("problem", ["tampered", "other-user", "changed", "expired"])
def test_snapshot_rejects_unreviewed_or_outdated_changes(problem, monkeypatch):
    person = user()
    token = sign_preview(preview([record()]), person.pk, catalogue_fingerprint())
    person_id = person.pk
    if problem == "tampered":
        token += "bad"
    elif problem == "other-user":
        person_id += 1
    elif problem == "expired":
        import importlib
        snapshot = importlib.import_module("cms.taxonomy.snapshot")
        monkeypatch.setattr(snapshot, "MAX_AGE", -1)
    else:
        Taxon.objects.create(taxon_name="Another", taxon_rank="genus")
    with pytest.raises(PreviewUnavailable):
        apply_signed_preview(token, person_id, NowTaxonomySyncService())
    assert not Taxon.objects.filter(taxon_name="Struthio").exists()


def test_fatal_apply_error_renders_visible_error_without_redirect(monkeypatch):
    person = user()
    token = sign_preview(preview([record()]), person.pk, catalogue_fingerprint())
    service = NowTaxonomySyncService()
    monkeypatch.setattr(service, "_apply", Mock(side_effect=OperationalError("database unavailable")))
    monkeypatch.setattr(cms_admin, "TaxonomySyncService", lambda: service)
    monkeypatch.setattr(cms_admin.admin.site, "each_context", lambda request: {})
    request = RequestFactory().post("/taxonomy/sync/apply/", {"preview_token": token})
    request.user = person
    response = cms_admin._taxonomy_sync_apply_view(request)
    response.render()
    assert response.status_code == 500
    assert b"database unavailable" in response.content
    assert b"No changes from this request were saved" in response.content
    assert "Location" not in response


def test_snapshot_applies_updates_synonyms_and_deactivations():
    person = user()
    existing = Taxon.objects.create(taxon_name="Existing", taxon_rank="genus",
                                    external_source="NOW", external_id="NOW:genus:Existing", author_year="Old")
    obsolete = Taxon.objects.create(taxon_name="Gone", taxon_rank="genus", external_source="NOW",
                                    external_id="NOW:genus:Gone")
    target = record("Existing", author_year="New")
    synonym = SynonymRecord("NOW:syn:Alias", "Alias", "Existing", target.external_id,
                            "genus", "Author", "v1", {"family": "Testidae"})
    proposed = SyncPreview([record("New")], [AcceptedUpdate(existing, target, {"author_year": "New"})],
                           [synonym], [], [obsolete], [], "v1")
    token = sign_preview(proposed, person.pk, catalogue_fingerprint())
    result = apply_signed_preview(token, person.pk, NowTaxonomySyncService())
    existing.refresh_from_db()
    obsolete.refresh_from_db()
    assert existing.author_year == "New"
    assert Taxon.objects.get(taxon_name="Alias").accepted_taxon_id == existing.pk
    assert obsolete.is_active is False
    assert result.import_log.counts["created"] == 2
    assert result.import_log.counts["updated"] == 1
    assert result.import_log.counts["deactivated"] == 1


@pytest.mark.parametrize("existing_synonym", [False, True])
def test_apply_resolves_accepted_taxon_when_bulk_insert_does_not_return_ids(monkeypatch, existing_synonym):
    # MySQL inserts rows without populating the bulk-created objects' primary keys.
    monkeypatch.setattr(type(connection.features), "can_return_rows_from_bulk_insert", False)
    target = record("Accepted")
    synonym = SynonymRecord("NOW:syn:Alias", "Alias", target.name, target.external_id,
                            "genus", "Author", "v1", {"family": "Testidae"})
    proposed = preview([target], [synonym])
    if existing_synonym:
        old_target = Taxon.objects.create(taxon_name="Old", taxon_rank="genus")
        alias = Taxon.objects.create(taxon_name="Alias", taxon_rank="genus", status="synonym",
                                     accepted_taxon=old_target, external_source="NOW", external_id=synonym.external_id)
        proposed.synonyms_to_create = []
        proposed.synonyms_to_update = [SynonymUpdate(alias, synonym, {"accepted_taxon": target.external_id})]
    log = NowTaxonomySyncService()._apply(proposed)
    accepted = Taxon.objects.get(taxon_name="Accepted")
    assert Taxon.objects.get(taxon_name="Alias").accepted_taxon_id == accepted.pk
    assert log.counts["created"] == (1 if existing_synonym else 2)
    assert log.counts["updated"] == (1 if existing_synonym else 0)
    assert log.counts["issues"] == 0


@pytest.mark.parametrize("existing_synonym", [False, True])
def test_synonym_target_uses_source_and_id(existing_synonym):
    target = Taxon.objects.create(taxon_name="Accepted", taxon_rank="genus",
                                 external_source="NOW", external_id="shared")
    collision = Taxon.objects.create(taxon_name="Unrelated", taxon_rank="genus",
                                    external_source="PBDB", external_id="shared")
    synonym = SynonymRecord("alias", "Alias", "Accepted", "shared", "genus", "", "v1", {},
                            external_source="GBIF", accepted_external_source="NOW")
    proposed = preview([], [synonym])
    if existing_synonym:
        alias = Taxon.objects.create(taxon_name="Alias", taxon_rank="genus", status="synonym",
                                     accepted_taxon=collision, external_source="GBIF", external_id="alias")
        proposed.synonyms_to_create = []
        proposed.synonyms_to_update = [SynonymUpdate(alias, synonym, {"accepted_taxon": "shared"})]
    result = apply_signed_preview(sign_preview(proposed, user().pk, catalogue_fingerprint()),
                                  user().pk, NowTaxonomySyncService())
    assert Taxon.objects.get(taxon_name="Alias").accepted_taxon_id == target.pk
    assert result.import_log.counts["issues"] == 0


def test_preview_does_not_reuse_another_sources_external_id():
    from cms.tests.test_sync_now import _field_slip
    _field_slip("Incoming")
    other = Taxon.objects.create(taxon_name="Unrelated", taxon_rank="genus",
                                external_source="PBDB", external_id="shared")
    incoming = record("Incoming", external_id="shared")
    proposed = NowTaxonomySyncService()._build_preview([incoming], [])
    assert proposed.accepted_to_create == [incoming]
    assert proposed.accepted_to_update == []
    NowTaxonomySyncService()._apply(proposed)
    other.refresh_from_db()
    assert other.taxon_name == "Unrelated"
    assert other.external_source == "PBDB"


def test_snapshot_locks_all_fingerprinted_tables_before_apply(monkeypatch):
    from django.db.models.query import QuerySet
    from cms.models import Identification, FieldSlip
    locked = []
    original = QuerySet.select_for_update

    def lock(queryset, *args, **kwargs):
        locked.append(queryset.model)
        return original(queryset, *args, **kwargs)

    person = user()
    service = NowTaxonomySyncService()
    original_apply = service._apply

    def apply(proposed):
        assert locked == [Taxon, Identification, FieldSlip]
        return original_apply(proposed)

    monkeypatch.setattr(QuerySet, "select_for_update", lock)
    monkeypatch.setattr(service, "_apply", apply)
    token = sign_preview(preview([record()]), person.pk, catalogue_fingerprint())
    apply_signed_preview(token, person.pk, service)


@pytest.mark.parametrize("table", ["identification", "field_slip"])
def test_snapshot_rejects_changed_related_names(table):
    from cms.models import Identification
    from cms.tests.test_sync_now import _field_slip
    from cms.tests.test_taxon_workflow import make_accession_row
    person = user()
    if table == "field_slip":
        obj = _field_slip("Original")
        field = "verbatim_taxon"
    else:
        from crum import set_current_user
        row = make_accession_row(person)
        set_current_user(person)
        obj = Identification.objects.create(accession_row=row, taxon_verbatim="Original")
        field = "taxon_verbatim"
    token = sign_preview(preview([record()]), person.pk, catalogue_fingerprint())
    type(obj).objects.filter(pk=obj.pk).update(**{field: "Changed"})
    with pytest.raises(PreviewUnavailable, match="catalogue changed"):
        apply_signed_preview(token, person.pk, NowTaxonomySyncService())
    assert Taxon.objects.count() == 0



def test_long_now_names_have_bounded_stable_ids_and_apply():
    from cms.taxonomy.sync import build_accepted_external_id, build_synonym_external_id
    name = "Accepted" + "a" * 247
    alias = "Alias" + "b" * 250
    target_id = build_accepted_external_id(name, "genus")
    alias_id = build_synonym_external_id(alias, name)
    assert len(target_id) <= 191
    assert len(alias_id) <= 191
    assert target_id == build_accepted_external_id(name, "genus")
    assert target_id != build_accepted_external_id(name[:-1] + "z", "genus")
    assert alias_id != build_synonym_external_id(alias, name[:-1] + "z")
    assert build_accepted_external_id("Panthera", "genus") == "NOW:genus:Panthera"
    assert build_synonym_external_id("Leo", "Panthera") == "NOW:syn:Leo::accepted:Panthera"
    target = record(name, external_id=target_id)
    synonym = SynonymRecord(alias_id, alias, name, target_id, "genus", "", "v1", {})
    log = NowTaxonomySyncService()._apply(preview([target], [synonym]))
    assert log.counts["created"] == 2
    assert log.counts["issues"] == 0
    assert Taxon.objects.get(external_id=alias_id).accepted_taxon_id == Taxon.objects.get(external_id=target_id).pk
