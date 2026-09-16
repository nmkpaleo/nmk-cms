"""Source precedence, stable links, and strict GBIF matching."""
import copy
from urllib.parse import parse_qs, urlparse

import pytest
import requests
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import override_settings

from app.cms.models import Taxon, TaxonStatus, Identification, DrawerRegister
from app.cms.taxonomy.combined import TaxonomySyncService
from app.cms.taxonomy.gbif import GbifClient, GbifMatchError
from app.cms.tests.test_sync_now import authenticated_model_user, _field_slip, _http_get_factory
from app.cms.tests.test_taxon_workflow import make_accession_row
from django.contrib.auth import get_user_model
from crum import set_current_user

pytestmark = pytest.mark.django_db


class Response:
    def __init__(self, data):
        self.data = data
    def raise_for_status(self):
        pass
    def json(self):
        return self.data


def payload(name="Struthio", class_name="Aves", rank="GENUS"):
    return {
        "usage": {"key": "test-key", "canonicalName": name, "rank": rank,
                  "authorship": "Author 1900", "status": "ACCEPTED"},
        "classification": [{"rank": "KINGDOM", "name": "Animalia"},
                           {"rank": "PHYLUM", "name": "Chordata"},
                           {"rank": "CLASS", "name": class_name},
                           {"rank": "FAMILY", "name": "Testidae"}],
        "diagnostics": {"matchType": "EXACT", "confidence": 99}, "synonym": False,
    }


def service(data, now="", gbif_get=None):
    return TaxonomySyncService(
        http_get=_http_get_factory({
            "accepted": "taxon_name\ttaxon_rank\tfamily\n" + now,
            "synonyms": "syn_name\ttaxon_name\ttaxon_rank\n",
        }),
        gbif_get=gbif_get or (lambda url, **kwargs: Response(copy.deepcopy(data))),
    )


@pytest.mark.parametrize("source", ["LEGACY", "GBIF"])
@override_settings(TAXON_NOW_ACCEPTED_URL="accepted", TAXON_NOW_SYNONYMS_URL="synonyms")
def test_mammal_now_promotion_preserves_identification_and_drawer(source):
    taxon = Taxon.objects.create(taxon_name="Panthera", taxon_rank="genus", family="Felidae",
                                genus="Panthera", external_source=source, external_id=f"{source}:old")
    user = get_user_model().objects.get(username="sync-now-user")
    row = make_accession_row(user)
    set_current_user(user)
    identification = Identification.objects.create(accession_row=row, taxon_verbatim="Panthera")
    drawer = DrawerRegister.objects.create(code="TX", description="test", estimated_documents=1)
    drawer.taxa.add(taxon)
    svc = service(payload("Panthera", "Mammalia"), "Panthera\tgenus\tFelidae\n")
    preview = svc.preview()
    assert preview.counts["created"] == 0
    assert preview.counts["updated"] == 1
    assert preview.to_deactivate == []
    svc.sync(apply=True)
    taxon.refresh_from_db()
    identification.refresh_from_db()
    assert taxon.external_source == "NOW"
    assert taxon.is_active
    assert identification.taxon_record_id == taxon.pk
    assert drawer.taxa.get().pk == taxon.pk
    assert Taxon.objects.count() == 1
    assert svc.preview().counts["updated"] == 0


@pytest.mark.parametrize("class_name,name", [("Aves", "Struthio"), ("Mammalia", "Panthera")])
@override_settings(TAXON_NOW_ACCEPTED_URL="accepted", TAXON_NOW_SYNONYMS_URL="synonyms")
def test_gbif_import_and_repeat_for_local_name(class_name, name):
    _field_slip(name)
    svc = service(payload(name, class_name))
    assert svc.preview().counts["created"] == 1
    result = svc.sync(apply=True)
    taxon = Taxon.objects.get()
    assert taxon.class_name == class_name
    assert taxon.external_source == "GBIF"
    assert result.import_log.source == "NOW_GBIF"
    assert svc.preview().counts["created"] == 0
    assert svc.preview().counts["updated"] == 0


@override_settings(TAXON_NOW_ACCEPTED_URL="accepted", TAXON_NOW_SYNONYMS_URL="synonyms")
def test_non_mammal_gbif_overrides_now_homonym():
    _field_slip("Struthio")
    svc = service(payload(), "Struthio\tgenus\tWrongidae\n")
    svc.sync(apply=True)
    assert Taxon.objects.get().external_source == "GBIF"
    assert Taxon.objects.get().class_name == "Aves"


@pytest.mark.parametrize("problem", ["fuzzy", "higher", "none", "class", "rank", "timeout", "null", "list", "malformed"])
@override_settings(TAXON_NOW_ACCEPTED_URL="accepted", TAXON_NOW_SYNONYMS_URL="synonyms")
def test_unsafe_or_failed_gbif_match_preserves_existing_taxon(problem):
    taxon = Taxon.objects.create(taxon_name="Struthio", taxon_rank="genus", external_source="NOW", external_id="old")
    data = payload()
    if problem in {"fuzzy", "higher", "none"}:
        data["diagnostics"]["matchType"] = problem.upper()
    elif problem == "class":
        data["classification"] = []
    elif problem == "rank":
        data["usage"]["rank"] = "SPECIES"
    def get(url, **kwargs):
        if problem == "timeout":
            raise requests.exceptions.Timeout("test timeout")
        if problem == "null":
            return Response(None)
        if problem == "list":
            return Response([])
        if problem == "malformed":
            return Response({"usage": [], "classification": [None], "diagnostics": {}})
        return Response(data)
    svc = service(data, gbif_get=get)
    preview = svc.preview()
    assert preview.counts["created"] == 0
    assert preview.counts["updated"] == 0
    assert preview.counts["deactivated"] == 0
    assert preview.issues[0].code == "gbif-match"
    svc.sync(apply=True)
    taxon.refresh_from_db()
    assert taxon.is_active


def test_gbif_rejects_non_string_classification_and_accepted_names():
    client = GbifClient(lambda url, **kwargs: Response(None))
    malformed_classification = payload()
    malformed_classification["classification"][2]["name"] = 42
    with pytest.raises(GbifMatchError):
        client.parse(malformed_classification, "Struthio", "genus")

    malformed_accepted = payload("Felis leo", "Mammalia", "SPECIES")
    malformed_accepted["synonym"] = True
    malformed_accepted["usage"]["status"] = "SYNONYM"
    malformed_accepted["acceptedUsage"] = {
        "key": "lion", "canonicalName": 42, "rank": "SPECIES"
    }
    with pytest.raises(GbifMatchError):
        client.parse(malformed_accepted, "Felis leo", "species")

    malformed_optional = payload()
    malformed_optional["usage"]["authorship"] = ["not", "text"]
    with pytest.raises(GbifMatchError):
        client.parse(malformed_optional, "Struthio", "genus")


@override_settings(TAXON_NOW_ACCEPTED_URL="accepted", TAXON_NOW_SYNONYMS_URL="synonyms")
def test_gbif_synonym_uses_now_accepted_target_and_links_identification():
    data = payload("Felis leo", "Mammalia", "SPECIES")
    data["usage"]["status"] = "SYNONYM"
    data["synonym"] = True
    data["acceptedUsage"] = {"key": "lion", "canonicalName": "Panthera leo", "rank": "SPECIES"}
    user = get_user_model().objects.get(username="sync-now-user")
    row = make_accession_row(user)
    set_current_user(user)
    ident = Identification.objects.create(accession_row=row, taxon_verbatim="Felis leo")
    svc = service(data, "Panthera leo\tspecies\tFelidae\n")
    svc.sync(apply=True)
    accepted = Taxon.objects.get(taxon_name="Panthera leo")
    synonym = Taxon.objects.get(taxon_name="Felis leo")
    assert accepted.external_source == "NOW"
    assert synonym.external_source == "GBIF"
    assert synonym.accepted_taxon_id == accepted.pk
    ident.refresh_from_db()
    assert ident.taxon_record_id == accepted.pk
    ident.save()
    assert ident.taxon_record_id == accepted.pk


def test_name_rank_uniqueness_is_source_independent():
    Taxon.objects.create(taxon_name="Struthio", taxon_rank="genus", external_source="LEGACY")
    with pytest.raises(ValidationError):
        Taxon.objects.create(taxon_name="  STRUTHIO  ", taxon_rank="GENUS", external_source="GBIF")
    Taxon.objects.create(taxon_name="Struthio", taxon_rank="family", external_source="GBIF")
    assert Taxon.objects.count() == 2


def test_gbif_request_uses_checklist_rank_and_timeout():
    calls = []
    def get(url, **kwargs):
        calls.append((url, kwargs))
        return Response(payload())
    client = GbifClient(get)
    client.match("Struthio", "genus")
    client.match("STRUTHIO", "GENUS")
    assert len(calls) == 1
    query = parse_qs(urlparse(calls[0][0]).query)
    assert query["checklistKey"] == ["7ddf754f-d193-4cc9-b351-99906754a03b"]
    assert query["taxonRank"] == ["GENUS"]
    assert calls[0][1]["timeout"] == 15


@override_settings(TAXON_NOW_ACCEPTED_URL="accepted", TAXON_NOW_SYNONYMS_URL="synonyms")
def test_gbif_accepted_name_change_preserves_old_row_as_synonym():
    old = Taxon.objects.create(
        taxon_name="Felis leo", taxon_rank="species", external_source="GBIF",
        external_id="GBIF:7ddf754f-d193-4cc9-b351-99906754a03b:lion",
    )
    data = payload("Felis leo", "Mammalia", "SPECIES")
    data["synonym"] = True
    data["usage"]["status"] = "SYNONYM"
    data["acceptedUsage"] = {"key": "lion", "canonicalName": "Panthera leo", "rank": "SPECIES"}
    svc = service(data)
    preview = svc.preview()
    assert preview.counts["created"] == 1
    assert preview.counts["updated"] == 1
    svc.sync(apply=True)
    old.refresh_from_db()
    assert old.status == "synonym"
    assert old.accepted_taxon.taxon_name == "Panthera leo"
    assert old.accepted_taxon_id != old.pk
    assert Taxon.objects.count() == 2


@override_settings(TAXON_NOW_ACCEPTED_URL="accepted", TAXON_NOW_SYNONYMS_URL="synonyms")
def test_gbif_outage_does_not_replace_known_bird_with_now_homonym():
    taxon = Taxon.objects.create(taxon_name="Struthio", taxon_rank="genus", class_name="Aves",
                                external_source="GBIF", external_id="GBIF:bird")
    def get(url, **kwargs):
        raise requests.exceptions.Timeout("unavailable")
    preview = service(payload(), "Struthio\tgenus\tWrongidae\n", gbif_get=get).preview()
    assert preview.counts["created"] == 0
    assert preview.counts["updated"] == 0
    assert preview.counts["deactivated"] == 0
    assert preview.issues[0].code == "gbif-match"


@override_settings(TAXON_GBIF_WORKERS=2)
def test_gbif_lookups_run_in_bounded_concurrent_batches():
    from threading import Barrier, Lock
    barrier = Barrier(2)
    lock = Lock()
    active = peak = 0

    def http_get(url, **kwargs):
        nonlocal active, peak
        name = parse_qs(urlparse(url).query)["scientificName"][0]
        with lock:
            active += 1
            peak = max(peak, active)
        try:
            barrier.wait(timeout=5)
            return Response(payload(name))
        finally:
            with lock:
                active -= 1

    names = [(f"Bird{i}", "genus") for i in range(6)]
    results = list(GbifClient(http_get=http_get).match_many(names))
    assert peak == 2
    assert [name for name, rank, result in results] == [name for name, rank in names]
    assert all(not isinstance(result, Exception) for name, rank, result in results)


@override_settings(TAXON_GBIF_WORKERS=2)
def test_gbif_outage_stops_requests_and_reports_every_deferred_name():
    from unittest.mock import Mock
    http_get = Mock(side_effect=requests.exceptions.Timeout("unavailable"))
    names = [(f"Bird{i}", "genus") for i in range(20)]
    results = list(GbifClient(http_get=http_get).match_many(names))
    assert http_get.call_count == 2
    assert len(results) == len(names)
    assert all(isinstance(result, requests.exceptions.RequestException) for name, rank, result in results)


@override_settings(TAXON_GBIF_WORKERS=2)
def test_gbif_name_misses_do_not_stop_remaining_lookups():
    from unittest.mock import Mock
    http_get = Mock(return_value=Response({"diagnostics": {"matchType": "NONE"}}))
    results = list(GbifClient(http_get=http_get).match_many([(f"Unknown{i}", "") for i in range(5)]))
    assert http_get.call_count == 5
    assert all(isinstance(result, ValueError) for name, rank, result in results)


@override_settings(TAXON_NOW_ACCEPTED_URL="accepted", TAXON_NOW_SYNONYMS_URL="synonyms")
def test_gbif_null_authorship_and_malformed_accepted_usage_are_safe():
    _field_slip("Struthio")
    data = payload()
    data["usage"]["authorship"] = None
    result = service(data).sync(apply=True)
    assert result.import_log.counts["created"] == 1
    assert Taxon.objects.get().author_year == ""

    bad = payload("Felis leo", "Mammalia", "SPECIES")
    bad["synonym"] = True
    bad["usage"]["status"] = "SYNONYM"
    bad["acceptedUsage"] = []
    preview = service(bad).preview()
    assert preview.issues[0].code == "gbif-match"


@override_settings(TAXON_NOW_ACCEPTED_URL="accepted", TAXON_NOW_SYNONYMS_URL="synonyms")
def test_whitespace_verbatim_uses_legacy_taxon_for_gbif_lookup():
    user = get_user_model().objects.get(username="sync-now-user")
    row = make_accession_row(user)
    set_current_user(user)
    identification = Identification.objects.create(accession_row=row, taxon_verbatim="Struthio")
    Identification.objects.filter(pk=identification.pk).update(taxon_verbatim="   ", taxon="Struthio")
    preview = service(payload()).preview()
    assert preview.counts["created"] == 1


@override_settings(TAXON_NOW_ACCEPTED_URL="accepted", TAXON_NOW_SYNONYMS_URL="synonyms")
def test_combined_source_version_includes_gbif_response_hash():
    _field_slip("Struthio")
    preview = service(payload()).preview()
    assert "GBIF:7ddf754f-d193-4cc9-b351-99906754a03b:" in preview.source_version
    assert not preview.source_version.endswith("7ddf754f-d193-4cc9-b351-99906754a03b")


@override_settings(TAXON_NOW_ACCEPTED_URL="accepted", TAXON_NOW_SYNONYMS_URL="synonyms")
def test_gbif_outage_does_not_import_unestablished_now_mammal_homonym():
    _field_slip("Struthio")

    def get(url, **kwargs):
        raise requests.exceptions.Timeout("unavailable")

    preview = service(
        payload(), "Struthio\tgenus\tMammalidae\n", gbif_get=get
    ).preview()
    assert preview.counts["created"] == 0
    assert preview.issues[0].code == "gbif-match"
