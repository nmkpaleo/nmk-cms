import io

import pytest
from crum import set_current_user
from django.contrib.auth import get_user_model
from django.test import override_settings

from app.cms.models import (
    Accession, AccessionRow, Collection, DrawerRegister, FieldSlip,
    Identification, Locality, Taxon, TaxonExternalSource, TaxonStatus, TaxonomyImport,
)
from app.cms.taxonomy.sync import NowTaxonomySyncService, build_taxon_from_record


@pytest.fixture(autouse=True)
def authenticated_model_user(db):
    """Ensure model saves in sync tests have a current user."""
    user_model = get_user_model()
    user, _ = user_model.objects.get_or_create(username="sync-now-user")
    set_current_user(user)
    try:
        yield
    finally:
        set_current_user(None)


class _StaticResponse:
    def __init__(self, text: str) -> None:
        self.text = text
        self.status_code = 200
        self.encoding = None

    def raise_for_status(self) -> None:  # pragma: no cover - simple placeholder
        return None


def _http_get_factory(mapping):
    def _http_get(url: str):
        try:
            text = mapping[url]
        except KeyError as exc:  # pragma: no cover - defensive
            raise AssertionError(f"Unexpected URL requested: {url}") from exc
        return _StaticResponse(text)

    return _http_get


@pytest.mark.django_db
@override_settings(
    TAXON_NOW_ACCEPTED_URL="https://example.com/accepted.tsv",
    TAXON_NOW_SYNONYMS_URL="https://example.com/synonyms.tsv",
    TAXON_SYNC_DEACTIVATE_MISSING=True,
)
def test_now_sync_creates_updates_and_deactivates(db):
    _field_slip("Newcanis junior")
    accepted_existing = Taxon.objects.create(
        external_source=TaxonExternalSource.NOW,
        external_id="NOW:species:Herpestes major",
        author_year="Old Author",
        status=TaxonStatus.ACCEPTED,
        is_active=False,
        source_version="old",
        taxon_rank="species",
        taxon_name="Herpestes major",
        kingdom="Animalia",
        phylum="Chordata",
        class_name="Mammalia",
        order="Old order",
        superfamily="",
        family="Outdated Family",
        subfamily="",
        tribe="",
        genus="OldGenus",
        species="major",
    )
    synonym_existing = Taxon.objects.create(
        external_source=TaxonExternalSource.NOW,
        external_id="NOW:syn:Herpestes majorus::accepted:Herpestes major",
        author_year="Old Syn Author",
        status=TaxonStatus.SYNONYM,
        accepted_taxon=accepted_existing,
        is_active=False,
        source_version="old",
        taxon_rank="species",
        taxon_name="Herpestes majorus",
        kingdom="Animalia",
        phylum="Chordata",
        class_name="Mammalia",
        order="Old order",
        superfamily="",
        family="Outdated Family",
        subfamily="",
        tribe="",
        genus="OldGenus",
        species="majorus",
    )
    to_deactivate = Taxon.objects.create(
        external_source=TaxonExternalSource.NOW,
        external_id="NOW:species:Obsolete taxon",
        author_year="Removed",
        status=TaxonStatus.ACCEPTED,
        is_active=True,
        source_version="old",
        taxon_rank="species",
        taxon_name="Obsolete taxon",
        kingdom="Animalia",
        phylum="Chordata",
        class_name="Mammalia",
        order="Carnivora",
        family="Herpestidae",
        genus="Obsolete",
        species="taxon",
    )

    accepted_tsv = "\n".join(
        [
            "taxon_name\ttaxon_rank\torder_name\tsuperfamily\tfamily\tsubfamily\ttribe\tgenus\tspecies\tauthor\tSTG_TIME_STAMP",
            "Herpestes major\tspecies\tCarnivora\tHerpestoidea\tHerpestidae\tHerpestinae\t\tHerpestes\tmajor\tNew Author\t2024-01-01",
            "Newcanis novus\tspecies\tCarnivora\tCanidoidea\tCanidae\tCaninae\tCanini\tNewcanis\tnovus\tA. Researcher\t2024-01-01",
        ]
    )
    synonyms_tsv = "\n".join(
        [
            "syn_name\ttaxon_name\ttaxon_rank\torder_name\tsuperfamily\tfamily\tsubfamily\ttribe\tgenus\tspecies\tauthor\tSTG_TIME_STAMP",
            "Herpestes majorus\tHerpestes major\tspecies\tCarnivora\tHerpestoidea\tHerpestidae\tHerpestinae\t\tHerpestes\tmajorus\tUpdated Syn Author\t2024-01-01",
            "Newcanis junior\tNewcanis novus\tspecies\tCarnivora\tCanidoidea\tCanidae\tCaninae\tCanini\tNewcanis\tjunior\tB. Res\t2024-01-01",
        ]
    )

    http_get = _http_get_factory(
        {
            "https://example.com/accepted.tsv": accepted_tsv,
            "https://example.com/synonyms.tsv": synonyms_tsv,
        }
    )

    service = NowTaxonomySyncService(http_get=http_get)

    preview = service.preview()
    assert preview.counts == {
        "created": 2,
        "updated": 2,
        "deactivated": 1,
        "synonym_links": 2,
        "issues": 0,
    }
    assert len(preview.accepted_to_create) == 1
    assert len(preview.synonyms_to_create) == 1

    result = service.sync(apply=True)
    assert result.import_log is not None
    result.import_log.refresh_from_db()
    assert result.import_log.counts["created"] == 2
    assert result.import_log.counts["updated"] == 2
    assert result.import_log.counts["deactivated"] == 1
    assert TaxonomyImport.objects.count() == 1

    accepted_existing.refresh_from_db()
    assert accepted_existing.author_year == "New Author"
    assert accepted_existing.is_active is True
    assert accepted_existing.source_version == "2024-01-01"
    assert accepted_existing.order == "Carnivora"
    assert accepted_existing.superfamily == "Herpestoidea"
    assert accepted_existing.family == "Herpestidae"
    assert accepted_existing.subfamily == "Herpestinae"
    assert accepted_existing.genus == "Herpestes"
    assert accepted_existing.species == "major"

    synonym_existing.refresh_from_db()
    assert synonym_existing.author_year == "Updated Syn Author"
    assert synonym_existing.is_active is True
    assert synonym_existing.accepted_taxon == accepted_existing
    assert synonym_existing.order == "Carnivora"
    assert synonym_existing.family == "Herpestidae"
    assert synonym_existing.genus == "Herpestes"

    created_synonym = Taxon.objects.get(external_id="NOW:syn:species:Newcanis junior::accepted:Newcanis novus")
    created_accepted = Taxon.objects.get(external_id="NOW:species:Newcanis novus")
    assert created_synonym.accepted_taxon == created_accepted
    assert created_accepted.order == "Carnivora"
    assert created_accepted.superfamily == "Canidoidea"
    assert created_accepted.family == "Canidae"
    assert created_accepted.subfamily == "Caninae"
    assert created_accepted.tribe == "Canini"
    assert created_accepted.genus == "Newcanis"
    assert created_accepted.species == "novus"

    to_deactivate.refresh_from_db()
    assert to_deactivate.is_active is False

    post_preview = service.preview()
    assert post_preview.counts == {
        "created": 0,
        "updated": 0,
        "deactivated": 0,
        "synonym_links": 0,
        "issues": 0,
    }


@pytest.mark.django_db
@override_settings(
    TAXON_NOW_ACCEPTED_URL="https://example.com/accepted.tsv",
    TAXON_NOW_SYNONYMS_URL="https://example.com/synonyms.tsv",
    TAXON_SYNC_DEACTIVATE_MISSING=True,
)
def test_now_sync_skips_subranks_and_limits_lower_taxonomy(db):
    _field_slip("Felidae")
    _field_slip("Theria")
    accepted_tsv = "\n".join(
        [
            "taxon_name\ttaxon_rank\torder_name\tsuperfamily\tfamily\tsubfamily\ttribe\tgenus\tspecies\tauthor\tSTG_TIME_STAMP",
            "Theria\tsubclass\tTheria\t\t\t\t\t\t\tA. Person\t2024-02-01",
            "Felidae\tfamily\tCarnivora\tFeliformia\tFelidae\t\t\t\t\tB. Person\t2024-02-01",
        ]
    )
    synonyms_tsv = "\n".join(
        [
            "syn_name\ttaxon_name\ttaxon_rank\torder_name\tsuperfamily\tfamily\tsubfamily\ttribe\tgenus\tspecies\tauthor\tSTG_TIME_STAMP",
        ]
    )

    http_get = _http_get_factory(
        {
            "https://example.com/accepted.tsv": accepted_tsv,
            "https://example.com/synonyms.tsv": synonyms_tsv,
        }
    )

    service = NowTaxonomySyncService(http_get=http_get)
    preview = service.preview()

    assert len(preview.accepted_to_create) == 1
    family_record = preview.accepted_to_create[0]
    assert family_record.name == "Felidae"
    assert family_record.rank == "family"
    assert family_record.taxonomy["order"] == "Carnivora"
    assert family_record.taxonomy["superfamily"] == "Feliformia"
    assert family_record.taxonomy["family"] == "Felidae"
    assert family_record.taxonomy["genus"] == ""
    assert family_record.taxonomy["species"] == ""


@pytest.mark.django_db
@override_settings(
    TAXON_NOW_ACCEPTED_URL="https://example.com/accepted.tsv",
    TAXON_NOW_SYNONYMS_URL="https://example.com/synonyms.tsv",
    TAXON_SYNC_DEACTIVATE_MISSING=True,
)
def test_now_sync_records_issue_when_missing_accepted(db):
    _field_slip("Alpha beta")
    _field_slip("Missing target")
    accepted_tsv = "\n".join(
        [
            "taxon_name\ttaxon_rank\tauthor\tSTG_TIME_STAMP",
            "Alpha beta\tspecies\tAuthor\t2024-01-01",
        ]
    )
    synonyms_tsv = "\n".join(
        [
            "syn_name\ttaxon_name\ttaxon_rank\tauthor\tSTG_TIME_STAMP",
            "Missing target\tGhost species\tspecies\tSomeone\t2024-01-01",
        ]
    )
    http_get = _http_get_factory(
        {
            "https://example.com/accepted.tsv": accepted_tsv,
            "https://example.com/synonyms.tsv": synonyms_tsv,
        }
    )

    service = NowTaxonomySyncService(http_get=http_get)
    preview = service.preview()

    assert preview.counts["issues"] == 1
    assert preview.synonyms_to_create == []
    assert preview.synonyms_to_update == []
    assert preview.issues[0].code == "missing-accepted"


@pytest.mark.django_db
@pytest.mark.parametrize("reassign_synonym", [False, True], ids=["accepted-id", "synonym-target"])
@override_settings(TAXON_SYNC_DEACTIVATE_MISSING=True)
def test_fallback_matched_taxon_stays_active_after_id_change(db, reassign_synonym):
    service = NowTaxonomySyncService(http_get=lambda url: None)
    accepted = list(service._parse_accepted(io.StringIO(
        "taxon_name\ttaxon_rank\tfamily\nAlpha beta\tspecies\tAlphidae\nAlpha gamma\tspecies\tAlphidae\n"
    )))
    existing = [build_taxon_from_record(record, status=TaxonStatus.ACCEPTED) for record in accepted]
    for taxon in existing:
        taxon.save()
    synonyms = []
    if reassign_synonym:
        old_synonym = list(service._parse_synonyms(io.StringIO(
            "syn_name\ttaxon_name\ttaxon_rank\nAlpha delta\tAlpha beta\tspecies\n"
        ), accepted))[0]
        matched = build_taxon_from_record(
            old_synonym, status=TaxonStatus.SYNONYM, accepted_taxon=existing[0]
        )
        matched.save()
        synonyms = list(service._parse_synonyms(io.StringIO(
            "syn_name\ttaxon_name\ttaxon_rank\nAlpha delta\tAlpha gamma\tspecies\n"
        ), accepted))
        desired_id = synonyms[0].external_id
    else:
        matched = existing[0]
        matched.external_id = "old-id-format"
        matched.save()
        desired_id = accepted[0].external_id

    obsolete_record = list(service._parse_accepted(io.StringIO(
        "taxon_name\ttaxon_rank\tfamily\nObsolete species\tspecies\tAlphidae\n"
    )))[0]
    obsolete = build_taxon_from_record(obsolete_record, status=TaxonStatus.ACCEPTED)
    obsolete.save()
    original_pk = matched.pk

    preview = service._build_preview(accepted, synonyms)
    assert preview.counts["created"] == 0
    assert preview.counts["updated"] == 1
    assert [taxon.pk for taxon in preview.to_deactivate] == [obsolete.pk]

    import_log = service._apply(preview)
    assert import_log.counts["deactivated"] == 1
    matched.refresh_from_db()
    obsolete.refresh_from_db()
    assert matched.pk == original_pk
    assert matched.external_id == desired_id
    assert matched.is_active is True
    assert obsolete.is_active is False
    if reassign_synonym:
        assert matched.accepted_taxon_id == existing[1].pk
    repeated = service._build_preview(accepted, synonyms)
    assert repeated.counts["created"] == 0
    assert repeated.counts["updated"] == 0
    assert repeated.counts["deactivated"] == 0


def _field_slip(name):
    return FieldSlip.objects.create(
        field_number="scope-test", verbatim_taxon=name, verbatim_element="tooth"
    )


def _scope_service():
    return NowTaxonomySyncService(http_get=_http_get_factory({
        "https://example.com/accepted.tsv": (
            "taxon_name\ttaxon_rank\tfamily\torder_name\n"
            "Alpha beta\tspecies\tAlphidae\tCarnivora\n"
            "Other species\tspecies\tAlphidae\tCarnivora\n"
            "Carnivora\torder\t\tCarnivora\n"
        ),
        "https://example.com/synonyms.tsv": (
            "syn_name\ttaxon_name\ttaxon_rank\n"
            "Alpha old\tAlpha beta\tspecies\n"
            "Alpha unused\tAlpha beta\tspecies\n"
        ),
    }))


@pytest.mark.django_db
@override_settings(
    TAXON_NOW_ACCEPTED_URL="https://example.com/accepted.tsv",
    TAXON_NOW_SYNONYMS_URL="https://example.com/synonyms.tsv",
)
@pytest.mark.parametrize("source", ["empty", "field-slip", "identification", "legacy-identification", "taxon", "drawer"])
def test_sync_only_imports_locally_recorded_names(db, source):
    if source == "field-slip":
        _field_slip("  ALPHA   beta  ")
    elif source in {"identification", "legacy-identification"}:
        user = get_user_model().objects.get(username="sync-now-user")
        collection = Collection.objects.create(abbreviation="TX", description="Taxon tests")
        locality = Locality.objects.create(abbreviation="TL", name="Taxon locality")
        accession = Accession.objects.create(
            collection=collection, specimen_prefix=locality, specimen_no=1, accessioned_by=user
        )
        row = AccessionRow.objects.create(accession=accession)
        ident = Identification.objects.create(accession_row=row, taxon_verbatim="Alpha beta")
        if source == "legacy-identification":
            Identification.objects.filter(pk=ident.pk).update(taxon_verbatim=None)
    elif source in {"taxon", "drawer"}:
        taxon = Taxon.objects.create(
            taxon_name="Carnivora", taxon_rank="order", order="Carnivora"
        )
        if source == "drawer":
            drawer = DrawerRegister.objects.create(code="TX", description="Test", estimated_documents=1)
            drawer.taxa.add(taxon)

    service = _scope_service()
    preview = service.preview()
    expected = set() if source == "empty" else {"Carnivora" if source in {"taxon", "drawer"} else "Alpha beta"}
    if source in {"taxon", "drawer"}:
        assert preview.accepted_to_create == []
        assert {u.record.name for u in preview.accepted_to_update} == expected
        service.sync(apply=True)
        taxon.refresh_from_db()
        assert taxon.external_source == TaxonExternalSource.NOW
        assert Taxon.objects.count() == 1
    else:
        assert {r.name for r in preview.accepted_to_create} == expected
    assert preview.synonyms_to_create == []
    assert preview.to_deactivate == []
    assert preview.issues == []
    if source in {"empty", "field-slip", "identification", "legacy-identification"}:
        service.sync(apply=True)
        assert set(Taxon.objects.values_list("taxon_name", flat=True)) == expected
        assert service.preview().counts["created"] == 0


@pytest.mark.django_db
@override_settings(
    TAXON_NOW_ACCEPTED_URL="https://example.com/accepted.tsv",
    TAXON_NOW_SYNONYMS_URL="https://example.com/synonyms.tsv",
)
def test_local_synonym_imports_only_its_required_accepted_name(db):
    _field_slip("Alpha old")
    service = _scope_service()
    preview = service.preview()
    assert [r.name for r in preview.accepted_to_create] == ["Alpha beta"]
    assert [r.name for r in preview.synonyms_to_create] == ["Alpha old"]
    service.sync(apply=True)
    synonym = Taxon.objects.get(taxon_name="Alpha old")
    assert synonym.accepted_taxon.taxon_name == "Alpha beta"
    assert set(Taxon.objects.values_list("taxon_name", flat=True)) == {"Alpha old", "Alpha beta"}
    assert service.preview().counts["created"] == 0


def test_now_synonym_uses_accepted_taxon_with_matching_rank():
    service = NowTaxonomySyncService(http_get=lambda url: None)
    accepted = list(service._parse_accepted(io.StringIO(
        "taxon_name\ttaxon_rank\tfamily\n"
        "Duplicatus\tgenus\tGenus family\n"
        "Duplicatus\tspecies\tSpecies family\n"
    )))
    synonym = list(service._parse_synonyms(io.StringIO(
        "syn_name\ttaxon_name\ttaxon_rank\n"
        "Old duplicatus\tDuplicatus\tspecies\n"
    ), accepted))[0]

    species = next(record for record in accepted if record.rank == "species")
    assert synonym.accepted_external_id == species.external_id
    assert synonym.taxonomy["family"] == "Species family"


@pytest.mark.django_db
def test_source_id_conflict_is_reported_without_deactivation(db):
    service = NowTaxonomySyncService(http_get=lambda url: None)
    old = Taxon.objects.create(
        taxon_name="Old name", taxon_rank="species", external_source=TaxonExternalSource.NOW,
        external_id="NOW:species:New name",
    )
    current = Taxon.objects.create(taxon_name="New name", taxon_rank="species")
    incoming = list(service._parse_accepted(io.StringIO(
        "taxon_name\ttaxon_rank\nNew name\tspecies\n"
    )))

    preview = service._build_preview(incoming, [])
    assert preview.accepted_to_create == []
    assert preview.accepted_to_update == []
    assert [issue.code for issue in preview.issues] == ["source-id-conflict"]
    assert preview.to_deactivate == []
    assert Taxon.objects.filter(pk__in=[old.pk, current.pk], is_active=True).count() == 2
